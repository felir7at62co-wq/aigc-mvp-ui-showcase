# AIGC Pipeline 性能优化方案 v2

> 本文档是 v1 方案的修订版。修订依据为对实际代码的逐项核实（核实日期 2026-07-24）。
> 相对 v1 的主要变更：
>
> 1. **新增 Phase 0（基线 + 埋点）并置于一切改动之前** —— 否则"优化前后对比"和 loop 的"历史最佳"无数据来源。
> 2. **修正 6 处会导致真 bug 的设计缺陷**（陈旧缩略图、config 缓存不失效、Session 线程安全、白图过期无 fallback、目录快照失效、硬时间断言不可靠）。
> 3. **砍掉 4.2（`_ep_texts` LRU）** —— ROI 为负。
> 4. **新增 3.3 的上传缓存扩大项**（角色/场景图按 path+mtime 缓存 file_name）—— 比白图持久化收益更大。
> 5. **Phase 6 loop 重新设计** —— 废弃 `time.sleep` 脚本，改为 cron 哨兵 / goal-turn 循环 + 结构化指标 + 参数文件，loop 永不碰 git。
>
> v1 中经核实成立的内容（问题定位、大部分优化点、文件归属）原样保留。

---

## Context

AIGC Pipeline 是一个 PyQt6 桌面应用，用于 AI 短剧自动化生产。用户反馈程序存在 UI 卡顿、加载缓慢、操作不流畅的问题。本方案通过系统性的性能分析，识别出四大类瓶颈：UI 线程阻塞、I/O 重复读写、Worker 重复初始化、内存管理缺失。目标是让程序达到高效、高质、丝滑流畅的用户体验。

任务边界：

- 优化 PyQt6 前端 UI 响应和渲染性能
- 优化 Worker/Agent 后端处理效率
- 优化文件 I/O 和缓存策略
- 优化内存使用
- 不改变现有业务逻辑和 API 接口
- 不引入新的外部依赖（基准测试只用 stdlib + pytest，不加 pytest-benchmark）
- **loop 自动化不执行任何 git 变更操作**（commit/stash/reset/rebase 一律需人工）

关键代码事实（已核实，后续各节引用）：

- 所有再生成图片都经 `os.replace` **原地覆盖同路径文件**（`workers.py:1358-1363` shot、`:1890-1891` asset、`:1446-1459` char），且扩展名可能变化（旧扩展名文件会被删除）。→ 一切按路径缓存的设计都必须处理失效。
- `load_config()`（`core/config.py:138`）返回**可变 dataclass** `PipelineConfig`；workers/agents 只读，但 UI 会改并 `save_config`（`steps/step_settings.py:312-353`、`steps/step_04_audio.py:71-74`）。
- `RunningHubClient` 共享一个 `requests.Session`（`core/runninghub_client.py:81-85`），**无线程锁**；现有 `ThreadPoolExecutor` 仅存在于 `batch_run` 内（:662）。
- `SingleShotRegenWorker` 每重生成 1 镜：串行重传全部角色图（`workers.py:1253-1262`）+ 场景图（:1268-1277）+ 白图（:1281-1296），并新建 `StoryboardGenerator` 解析两份 workflow JSON（:1298）。
- step_08 没有 `_rebuild_grid` 函数；网格重建内联在 `_show_episode`（`steps/step_08_storyboard.py:1041-1075`）并在 :1367-1376 重复一份。
- step_06 有两处 `set_image`：`AssetCard.set_image`（:583）和 `AssetImagePicker.set_image`（:153）。
- 已有先例可复用：`LLMCache.get_cache()` 单例（`core/llm_cache.py:335`）；150ms 防抖（`step_07_shot.py:34-37`、`step_08_storyboard.py:717-719`）；`load_or_build_asset_context` 已有磁盘缓存（`core/asset_context.py:67-77`）。
- 已有同日 loop 计划 `docs/superpowers/plans/2026-07-24-loop-debug-v2.md`，其单实例锁 / 人工确认门禁约定本方案复用，不造平行标准。

---

## Phase 0: 基线与埋点（新增，必须先做）

> 在未修改的代码上采集"优化前"基线。跳过本阶段，Phase 5 的对比报告和 Phase 6 的 loop 判定都是空话。

### 0.1 性能基线测试

编写 `tests/test_performance_baseline.py`，只用 stdlib（`time.perf_counter` + `json` + `statistics`），GUI 部分 `QT_QPA_PLATFORM=offscreen`（沿用现有测试惯例）：

- Config 加载耗时（`load_config` 含 YAML 解析）
- Asset context 加载耗时（含 `json.loads`）
- QPixmap 加载 + 缩放耗时（1x1 / 小尺寸测试图）
- 网格卡片重建耗时 + **QPixmap 构造次数**（计数，确定性指标）
- 状态同步耗时 + `state.json` 读取次数

每个指标：**warm-up 1 次 + 重复 N≥5 次，记录中位数和 stddev**。结果追加写入 `docs/perf_metrics.jsonl`，每行含：`timestamp`、`git_sha`、指标名、中位数、stddev、重复次数。**不解析 pytest stdout 作为指标来源。**

验证：在未修改代码上运行一次，`perf_metrics.jsonl` 产生首条基线记录。

### 0.2 可观测性埋点

为后续所有缓存预埋计数器（模块级 `{"hits": N, "misses": N}` dict，环境变量如 `AIGC_PERF_STATS=1` 控制是否输出到日志）；为慢操作预埋阈值日志（`QElapsedTimer`，超过阈值打 WARNING，如单卡片渲染 >50ms、状态同步 >100ms）。

涉及文件：暂不改动业务代码，只在 `core/` 新增一个轻量 `perf_stats.py` 工具模块（计数器 + 计时上下文管理器），供 Phase 1-4 的缓存实现引用。

验证：`AIGC_PERF_STATS=1` 运行测试，日志出现计数器输出。

### 0.3 禁网 guard

在 `LLMClient` 和 `RunningHubClient` 的构造或请求入口处检查环境变量 `AIGC_DISABLE_NETWORK=1`，置位时直接抛异常。保证 Phase 6 的 loop 反复跑测试时**绝无可能**触发真实 API 计费。

涉及文件：`core/llm_client.py`、`core/runninghub_client.py`（各加一处守卫，约 5 行）。

验证：置位环境变量后运行相关测试，断言网络调用被拦截；不置位时行为不变。

---

## Phase 1: UI 流畅度优化（最高 ROI）

### 1.1 QPixmap 缩略图缓存（修正版）

问题：每次卡片创建/重建时，`QPixmap(path)` 从磁盘解码完整图片再缩放（`step_06_asset_generation.py:56-71`、`:583-596`，`step_08_storyboard.py:140-148`、`:1212-1220`）。一张 5MB 图片在 UI 线程解码耗时 50-200ms，网格 15+ 张卡片时明显卡顿。

方案：模块级缩略图缓存，**key 为 `(path, width, height, mtime, size)`** —— mtime/size 必须入 key，否则角色/场景/分镜图再生成（`os.replace` 原地覆盖）后会显示陈旧图。或者采用另一等价方案：key 不含 mtime，但在 `shot_done` / `asset_status` / `char_status` 信号处理处显式失效对应条目。二选一，必须在代码注释中写明选用哪种及原因。

同时：

- 缓存加 **LRU 上限**（如 200 条），无界 dict 与 Phase 4 的内存目标自相矛盾。
- 注释注明 QPixmap 仅允许在 GUI 线程创建/使用，本缓存不得被 Worker 线程触碰。
- 命中计数接入 Phase 0 的 `perf_stats`。

涉及文件：

- `steps/step_06_asset_generation.py` — `_set_preview_pixmap()`、`AssetCard.set_image()`、`AssetImagePicker.set_image()`（:153，v1 遗漏）
- `steps/step_08_storyboard.py` — `ShotCard.set_image()`、`_add_asset_tile()`、预览对话框 `_set_image`（:85-95，v1 遗漏）

验证：切换集数时卡片渲染无明显闪烁；缓存命中率 >80%；**再生成某张图后 UI 显示的是新图**（回归用例，v1 缺失）。

### 1.2 增量网格更新（代替销毁-重建）

问题：`_show_episode()` 用 `deleteLater()` 销毁所有卡片再重建，每张卡片重新分配 QPixmap，触发 GC 和 layout 重算。

方案：diff 更新：保留已存在且路径未变的卡片，仅创建新卡片、移除多余卡片；已存在卡片只在图片变化时调 `set_image()`。

涉及文件（修正 v1 引用）：

- `steps/step_08_storyboard.py` — `_show_episode()`（:1041-1075）及 :1367-1376 的重复段（无 `_rebuild_grid` 函数）
- `steps/step_06_asset_generation.py` — `_rebuild_cards()`（:977）

验证：集数切换时 Widget 创建数从 N 降至 diff count（用 Phase 0 计数器断言，确定性指标）。

### 1.3 状态同步去抖动（修正版）

问题：`_sync_step_status_from_project()`（`main_window.py:238`）在步骤切换、Worker 完成、窗口激活时都被调用，每次同步读 `state.json` 并遍历文件系统。

方案：300ms trailing 防抖（`QTimer`，项目已有 150ms 先例），但**仅合并被动触发**（窗口激活、文件 watcher）；Worker 完成等用户可感知的状态变更保持即时执行，避免"任务完成了状态栏却延迟 300ms"的新体感问题。

涉及文件：`main_window.py` — `_sync_step_status_from_project()`

验证：快速切换步骤时实际执行次数合并为 1 次；Worker 完成时状态即时更新。

### 1.4 项目列表缓存（补充失效说明）

问题：`_refresh_project_combo()`（`main_window.py:373`）在 showEvent 和 `changeEvent(ActivationChange)`（:457-460）都扫描 `projects_root/`，Alt-Tab 也触发。

方案：缓存项目列表，仅在项目创建/删除时刷新，窗口激活不做 I/O。**已知取舍**：用户在文件管理器里手动增删项目目录时列表不自动更新 —— 需保留一个手动刷新入口（刷新按钮或 F5），并在代码注释中说明。

涉及文件：`main_window.py` — `_refresh_project_combo()`、`_on_project_created()`、`_on_delete_project()`

验证：Alt-Tab 不触发 `os.listdir()`（计数器断言）。

---

## Phase 2: I/O 效率优化

### 2.1 Config 缓存（修正版）

问题：每个 Worker 在 `_run_impl()` 中独立 `load_config()`（`workers.py:318/476/795/1488/1308/1615`），重复 YAML 解析 + `load_dotenv`。

方案：模块级缓存，**key 为 `(config_path, mtime)`**（`lru_cache` 只按 path 不含 mtime，不能直接用）；或按 path 缓存 + 在 `save_config` 中显式失效。**失效是必须的**：`step_settings.py:312-353`、`step_04_audio.py:71-74` 会修改并保存 config，缓存不失效则 Worker 静默使用旧 API key/URL（v1 未处理此正确性问题）。

另外：返回的是**可变 dataclass 的共享实例**，多 Worker 并发只读目前安全，但为防未来有人写 `cfg.xxx = ...` 污染全局，二选一：返回 `copy.deepcopy`（开销小，config 不大）或将 dataclass 改 frozen（改动面大，需评估）。推荐 deepcopy。

涉及文件：`core/config.py` — `load_config()`；`save_config` 或 `steps/step_settings.py` 保存路径（加失效调用）

验证：连续调用只解析一次 YAML（计数器断言命中率 >90%）；**修改并保存 config 后，下一次 `load_config` 返回新值**（回归用例，v1 缺失）。

### 2.2 资产上下文内存缓存（收益修正）

问题：`load_or_build_asset_context()` 每次调用都读 `asset_context.json` 并 JSON 解析。

方案：模块级缓存 `_context_cache: dict[str, tuple[float, dict]]`，key 为 project_dir，value 为 (mtime, context)，mtime 变化自动失效。

**收益修正**（核实后）：该函数已有磁盘缓存（`core/asset_context.py:67-77`），本项省的是进程内重复 `json.loads` 和版本校验，收益比 v1 描述的小，但仍成立且实现简单，保留。

涉及文件：`core/asset_context.py` — `load_or_build_asset_context()`

验证：同一 project_dir 连续调用直接内存返回；文件变更后返回新内容。

### 2.3 选集 JSON 批量写入

问题：`update_selection_status()`（`step_06_asset_generation.py:1455`）每次单个资产选中状态改变就触发原子写（含 fsync），50 个资产全选 = 50 次 fsync。

方案：500ms 延迟写定时器，积累更新批量写入一次。**注意退出安全**：应用关闭时若定时器未触发，需在 `closeEvent` 中 flush，防止最后的选择丢失（v1 未提）。

涉及文件：`steps/step_06_asset_generation.py` — `update_selection_status()`、`_persist_selection()`（:1429）、`closeEvent`

验证：全选 50 个资产写入次数从 50 降至 1（计数器断言）；关闭应用后 `selections.json` 包含最后的状态。

### 2.4 目录扫描缓存（补充失效说明）

问题：`_find_image()`（`step_06_asset_generation.py:928`）为每个资产名检查 4 种扩展名 × N 个别名，`_rebuild_cards()` 重建 30 张卡片产生 120+ 次 `os.path.isfile()`。

方案：`load_descriptions()` 时一次性 `os.listdir()` 到 set，`_find_image()` 查内存集合。**失效说明**：资产再生成可能改变扩展名（`workers.py:1360-1363` 会删除旧扩展名文件），因此目录快照必须在资产再生成完成信号处刷新（或按目录 mtime 校验）（v1 未处理，会找不到新生成的图）。

涉及文件：`steps/step_06_asset_generation.py` — `_find_image()`、`load_descriptions()`、再生成完成信号处理处

验证：`os.path.isfile` 调用从 120+ 降至 1 次 `os.listdir()`；**再生成一张改了扩展名的图后仍能正确显示**（回归用例，v1 缺失）。

---

## Phase 3: Worker/API 处理效率

### 3.1 LLM 客户端复用

问题：每个 Worker 在 `_run_impl()` 中独立创建 `LLMClient`（构造含 OpenAI client 初始化 + LLMCache sqlite 句柄，`core/llm_client.py:110-123`）。

方案：`core/llm_client.py` 新增 `get_shared_llm_client()` 工厂，`threading.Lock` 保证线程安全。`LLMCache.get_cache()` 单例（`core/llm_cache.py:335`）是现成先例，模式照抄。OpenAI SDK v2 client 本身线程安全，可共享。

涉及文件：`core/llm_client.py`；`workers.py` 各 Worker 的 `_run_impl()`（:318/476/795/1488/1308/1615）

验证：多 Worker 并行时 LLMClient 实例数 = 1。

### 3.2 RunningHub 图片上传并发化（补充线程安全）

问题：角色图、场景图串行上传（`workers.py:712-725`、`:741-754`、`:1253-1262`、`:1268-1277`）。

方案：`ThreadPoolExecutor` 并发上传，并发数 3-5。**前置条件**：`RunningHubClient` 共享 `requests.Session` 且无锁（`core/runninghub_client.py:81`），`requests.Session` 不保证线程安全 —— 先给 session 的 post/get 加锁（或用 `threading.local` 的 per-thread session），再开并发，否则把现状风险放大。加锁后并发上传的实际加速会打折扣，预期从"串行 60s → 并发 15s"修正为"→ 20-30s"，仍值得做。

涉及文件：`core/runninghub_client.py`（session 锁）；`workers.py` 上传循环

验证：并发上传无 405/5xx 异常率上升；总耗时显著低于串行。

### 3.3 上传 file_name 缓存（扩大版，含原白图项）

问题（v1 已识别）：每次分镜生成都创建 1024x1024 白色 PNG → 上传 → 删除，约 2-3 秒浪费。
问题（v1 遗漏，**收益更大**）：`SingleShotRegenWorker` 每重生成 1 镜就串行重传**全部**角色图 + 场景图（`workers.py:1253-1296`）——这些图内容没变，file_name 完全可复用。

方案：统一的**上传缓存**：`dict[(path, mtime, size)] -> (file_name, upload_time)`，持久化到项目目录外的缓存文件（如 `data/upload_cache.json`）。白图作为固定 path 的特殊条目同样走此缓存。上传前查缓存，命中直接用。

**必须有 fallback**：服务端 file_name 过期时间未验证（v1 的"24 小时"是假设），提交 workflow 时若因 file_name 失效报错，需自动重新上传并重试一次，同时失效缓存条目。无此 fallback，本项会从优化变成稳定性 bug 源。

涉及文件：`workers.py` — `StoryboardWorker._run_impl()`、`SingleShotRegenWorker._run_impl()` 的上传部分；新增缓存读写（可放 `core/runninghub_client.py` 或独立小模块）

验证：同一项目第二次运行 / 单镜重生成时上传次数 ≈ 0；file_name 失效时能自动重传成功（用 mock 模拟 404/失效响应的测试）。

### 3.4 Workflow JSON 解析缓存

问题：`StoryboardGenerator.__init__()`（`agents/storyboard_generator.py:229-326`）每次实例化都重读并解析 workflow JSON（`_find_prompt_node` 等）；单镜重生成也要解析两份 workflow。

方案：模块级缓存已解析的 workflow 结构，按 `(path, mtime)` 索引。

涉及文件：`agents/storyboard_generator.py`

验证：同一 workflow 文件 JSON 读取次数降至 1（计数器断言）。

---

## Phase 4: 内存与启动优化

### 4.1 步骤页面延迟初始化

问题：`_build_step_pages()`（`main_window.py:133`）启动时创建全部 7 个步骤 Widget，每个 50-200ms。

方案：`QStackedWidget` 按需创建，首次切换才构造，已创建的保留。**前置检查**：确认没有跨步骤的信号连接依赖"所有页面已构造"（如有，改为懒连接或在首次创建时补连）。

涉及文件：`main_window.py` — `_build_step_pages()`、`_on_step_selected()`

验证：启动只创建默认页；启动时间减少（以 Phase 0 基线对比）；各步骤功能无回归（跑现有 GUI 测试）。

### 4.2 （已删除）`_ep_texts` LRU

v1 方案：只保留当前集前后各 1 集文本在内存。
**删除理由**：50 集剧本全文约 10-20MB，对桌面应用可忽略；按需读盘反而给集数切换引入新的 I/O 延迟（与 Phase 1 目标冲突）；且 `refresh_from_disk()`（`step_07_shot.py:106-125`）当前是一次性全量读，改成 LRU 的复杂度和回归风险换不来可感知的收益。ROI 为负，不做。

---

## Phase 5: 综合测试与报告

### 5.1 优化后对比测量

基线已在 Phase 0 采集。本步在 Phase 1-4 全部完成后重跑 `tests/test_performance_baseline.py`，同一台机器、同样的 N 次重复，结果追加进 `docs/perf_metrics.jsonl`。

### 5.2 UI 响应性测试（断言修正）

时间类硬断言（<16ms / <100ms）在 offscreen/CI 环境噪声大、不可靠，**改为断言确定性指标**：

- 集数切换时 QPixmap 构造次数 ≤ diff count（不触发全网格重建）
- Alt-Tab / 窗口激活时 `os.listdir` 调用次数 = 0
- 快速切换 N 步时状态同步实际执行次数 = 1
- `load_config` 连续调用时 `yaml.safe_load` 实际执行次数 = 1

时间类数字（步骤切换 <50ms 等）只写入 `perf_metrics.jsonl` 做趋势观察，并保留人工冒烟确认，不作为 CI 硬断言。

### 5.3 性能报告

生成 `docs/performance_report.md`：优化前后 `perf_metrics.jsonl` 对比表、各项优化效果量化、已知取舍（1.4 手动刷新、3.2 锁开销）、后续建议。

---

## Phase 6: 优化 Loop（重新设计）

### v1 设计的问题（为什么改）

1. `goal_optimization_loop.py` 只实现了"跑 pytest + 记日志 + 失败 break"，流程图里的对比/回滚/调参全部缺席 —— 是"测试日志循环"，不是优化循环。
2. `time.sleep(20*60)` 前台脚本：终端关即死、无单实例锁、无状态持久化，还会阻塞 goal turn 数小时。运行环境（goal turn / cron）已提供调度和持久化，不需自造。
3. "退化→回滚最近改动"未定义且危险：自动 git 变更可能毁掉未提交工作，且违反 CLAUDE.md 的 commit 门禁（`detect_changes` + 人工确认）。
4. 单次 wall-clock 在 Windows 上噪声远大于 5% 阈值，"预测收益 >5%"不可执行。
5. 无停止规则、无单轮预算、无观测埋点（Phase 0 补齐）、无禁网硬保证（Phase 0 补齐）。

### 新设计：载体二选一

**方案 A —— cron 回归哨兵（推荐）**
优化实施作为一个 goal（Phase 0→5 顺序完成即结束）；之后创建一个 recurring cron（如每 30 分钟，避开整点/半点），fire 时执行一轮"评估+判定"（见下）。连续 K=2 轮无退化无新机会 → 删除 cron，loop 结束。goal 与 watch 解耦。

**方案 B —— loop 即 goal**
最贴合"每次 loop 一个 goal"的原始想法：创建一个 goal，其每一轮 = 一个 goal turn（runtime 自动 continuation，无需 sleep），turn 内执行一轮"评估+判定+安全微调"，满足停止规则时 `UpdateGoal(complete)`。

两种载体共享同一套轮次逻辑：

### 每轮逻辑（约 ≤10 分钟硬预算）

1. **评估**：`AIGC_DISABLE_NETWORK=1 python -m pytest tests/test_performance_baseline.py` → 指标追加进 `docs/perf_metrics.jsonl`；同时读取各缓存 hits/misses 计数器和慢操作 WARNING 日志。
2. **对比基线**：任一关键指标 > 基线 + max(15%, 2σ) → 判定**退化**：停止 loop，在 `docs/optimization_loop_log.md` 标注嫌疑变更（git sha / 参数），报告给人，**不自动回滚**。
3. **提升** → 更新 best 快照。
4. **持平** → 只在 `perf_tuning.json`（新增，运行时读取）的**白名单键**内做一次**单变量**试探：`cache_ttl` / `debounce_ms` / `upload_concurrency`。下一轮测量决定保留或还原（还原 = 改回 JSON 值，零 git 风险）。非白名单改动一律不做，只记录为"建议"写入日志。
5. **记录**：`docs/optimization_loop_log.md` 追加：时间戳、指标摘要、判定、改动、结果。

### 停止规则

成功标准全部达标 且 连续 2 轮无退化无新机会 → 完成；轮次上限（如 8 轮）兜底；退化 → 立即停止等人。

### 安全栏

- 单实例锁文件（复用 loop-debug-v2 计划的约定）
- 工作区脏（有未提交改动）时只测不改
- 全程 `AIGC_DISABLE_NETWORK=1`（Phase 0.3 的 guard 保证）
- loop 永不执行任何 git 变更；代码改动前 GitNexus `impact`、commit 前 `detect_changes`，且 commit 必须人工确认
- 每轮硬时间预算 ≤10 分钟

---

## 验证方案

### 测试资源约束（沿用 v1）

- 单次测试不超过 1 集数据规模；全套测试数据 ≤5 集
- mock/fake 替代真实 API（LLM、RunningHub），外加 Phase 0.3 的禁网 guard 双保险
- 测试图用 1x1 像素或小尺寸占位图；测试剧本用最小有效文本

### 整体验证流程

1. `python -m pytest tests/ -v` 现有套件无回归
2. Phase 0 基线已采集；Phase 1-4 完成后跑对比基准（1 集测试数据）
3. 手动冒烟：1 集测试项目走完整流程（创建项目 → 拆分剧本 → 资产生成 → 分镜生成），切换步骤/集数/刷新，观察流畅度 —— **"无闪烁"只能由此确认，自动化替代不了**
4. 检查日志无异常错误/性能 WARNING
5. Phase 6 loop 运行期间自动回归，日志完整

### 成功标准（修正版）

- 步骤切换无可见延迟（人工冒烟确认；<50ms 写入 metrics 做趋势参考，不做硬断言）
- 集数切换卡片渲染无闪烁（人工冒烟）
- 资产网格重建耗时较基线减少 50%+（`perf_metrics.jsonl` 对比，中位数）
- Worker 并行时 LLMClient 实例数 = 1
- Config / Asset Context 文件不重复读取（计数器断言）
- **再生成图片后 UI 显示新图、config 保存后 Worker 用新值、改扩展名再生成后找图正确**（三条新增正确性回归用例）
- 所有现有测试保持通过
- loop 日志完整记录每轮指标与判定

---

## 编码要求（沿用 v1 并补充）

- 遵循项目 CLAUDE.md：先思考再编码、简洁优先、外科手术式修改、目标驱动
- 修改前运行 GitNexus `impact` 分析 blast radius；修改后运行 `detect_changes` 确认影响范围
- **commit 一律需人工确认，任何自动化（含 Phase 6 loop）不得执行 git 变更**
- 每项优化附带对应计数器/回归用例，验证方式必须是指标断言而非肉眼估计（肉眼估计仅限"无闪烁"类人工冒烟项）
