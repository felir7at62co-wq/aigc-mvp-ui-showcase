# AIGC MVP UI — 项目深度审核报告（v2.0 完善版）

**项目定位**：基于 PyQt6 的 AI 短剧自动化生产流水线，10 步可视化流水线从剧本到剪映成片全流程覆盖。

**审核日期**：2026-05-11

**总体评分：4/10**

**分项评分**：
| 维度 | 评分 | 说明 |
|------|------|------|
| 安全性 | 5/10 | 密钥未提交但报告明文曝光；API Key 跨服务回退 |
| 架构 | 3/10 | 两条执行路径各自为政；~5395 行死代码占比 24.8% |
| 代码质量 | 4/10 | Agent 层代码尚可，但 bug 较多，反模式普遍 |
| 测试覆盖 | 0/10 | 无测试目录、无 pytest、无 CI |
| 文档/结构 | 4/10 | 步骤映射混乱，死导入，空文件 |

**定量指标**：
- 项目总行数：21,758 行（60+ Python 文件）
- 死代码/未使用代码：**~5,395 行（24.8%）**
- 实锤 Bug：**12+** 个
- 文件 >1000 行：5 个（最大 1868 行）
- 测试覆盖率：**0%**

**亮点**：Agent 层代码质量尚可（ScreenplayAgent、DraftGenerator），Pipeline 引擎的自愈式错误处理、增量成本统计等设计思路正确。火山引擎/Seedance/RunningHub 多 API 集成具有一定复杂度。剪映草稿生成模块（jianying_draft.py）对 XML 模板的操作实现较为完整。

**问题**：存在严重的框架过度工程化（~5395 行死代码），两条执行路径各自为政（UI Worker 路径 vs PipelineEngine），架构一致性差（三套 DAG 定义），安全红线问题（API Key 曝光风险），零测试覆盖，多线程竞态条件，以及 12+ 个实锤 bug。

---

## 一、安全红线（必须立即修复）

### 1.1 API Key 历史记录风险

用户提供的报告中包含明文密钥：
```
RUNNINGHUB_API_KEY=[REDACTED-ROTATION-REQUIRED]
LLM_API_KEY=[REDACTED-ROTATION-REQUIRED]
TOTP_SECRET=[REDACTED-ROTATION-REQUIRED]
```

**现状**：
- `.env` 文件已在 `.gitignore` 中
- `git log --all -- .env` 返回空，确认从未被提交
- `.env` 当前不存在于磁盘上
- `config.yaml` 中 API Key 字段为空字符串 `""`

**风险等级**：**严重**

**风险**：报告本身包含了明文密钥。如果这份报告被分享（PR、文档、截图），密钥即刻泄露。TOTP_SECRET 可能用于 2FA 绕过，风险最高。

**建议**：
1. **立即轮换这三个密钥**
2. 不要在审计报告/文档中明文粘贴密钥
3. 确认 TOTP_SECRET 的用途——如果用于 2FA，风险等级最高

### 1.2 Seedance API Key 回退逻辑

`core/config.py:527-528`：
```python
if not cfg.web_video.api_key and cfg.llm.api_key:
    cfg.web_video.api_key = cfg.llm.api_key
```

**风险等级**：**中**

**风险**：LLM 的 API Key 自动作为 Seedance 视频生成 API Key 使用。这两个服务可能具有不同的权限范围——如果 Seedance API Key 泄露，影响面被 LLM 的权限放大。

### 1.3 config.yaml API Key 字段定义缺失

`config.yaml` 的 `web_video` 部分没有定义 `api_key` 字段，但 `step_settings.py:346` 允许编辑 "Seedance API Key" 并保存到 `cfg.web_video.api_key`。这导致：
- 用户通过 UI 配置的 Seedance API Key 无法持久化到默认配置结构
- 运行时通过 `_apply_env_overrides` 回退到 LLM API Key（行为不透明）

---

## 二、架构问题（高优先级）

### 2.1 UI 执行路径与 PipelineEngine 完全脱节 ★★★ 最大架构发现

项目存在两条**完全独立的执行路径**，这是原报告未发现的最严重架构问题。

**路径 A - UI Worker 路径（实际使用）**：
```
UI Step Widget → Worker (QThread) → Agent class + Client class
```
示例：`Step02SplitWidget` → `ScreenplayWorker` → `ScreenplayAgent` + `LLMClient`

**路径 B - PipelineEngine 路径（从未运行）**：
```
PipelineEngine.run() → _execute_step() → Agent class
```

**核查证据**：
- `PipelineEngine` 类（`core/pipeline_engine.py:342`，1509 行）**仅被 `core/ab_test.py`（死代码）导入**
- 没有任何 Worker、Step Widget、或 UI 代码导入或实例化 `PipelineEngine`
- 所谓的"10 步可视化流水线"实际上没有串联的流水线引擎——每个步骤独立运行，步骤间数据流转由 UI 信号手动管理
- **自愈式错误处理、增量成本统计、DAG 调度、并行执行**等核心功能从未在 UI 路径中生效

**影响**：
- `core/pipeline_engine.py` 是一份 1509 行的"文档"而非运行时代码
- UI 路径中没有任何错误恢复机制——如果一个 Agent 调用失败，没有重试逻辑
- 步骤间依赖关系完全由 Widget 代码手动维护（`main_window.py:178-181` 的信号连接）

**影响评估**：**严重**。项目核心引擎与 UI 界面毫无关联，意味着"10 步流水线"实际上只是 10 个独立的单步操作。

### 2.2 ~5395 行死代码框架（24.8%）

| 模块 | 行数 | 占总项目比例 | 状态 | 证据 |
|------|------|------------|------|------|
| `core/agent_bus.py` | 851 | 3.9% | 完全未使用 | 仅被 `ab_test.py` 引用，而 `ab_test.py` 本身也未使用 |
| `core/ab_test.py` | 1062 | 4.9% | 完全未使用 | 完整 A/B 测试框架，所有实验分支只有 `pass` 实现，未被任何实际代码引用 |
| `core/langgraph_nodes.py` | 705 | 3.2% | **有 bug，无法运行** | `DraftGenerator(jianji_tool_path=...)` 传参错误 |
| `core/langgraph_states.py` | 45 | 0.2% | 仅被其他 langgraph 文件引用 | 随 langgraph 整体不可用 |
| `core/langgraph_policies.py` | 87 | 0.4% | 仅被其他 langgraph 文件引用 | 同上，且有运行时副作用 |
| `core/langgraph_pipeline.py` | 243 | 1.1% | 有条件导入但从未成功运行 | 因 nodes 层 bug 无法执行 |
| `core/tool_registry.py` | 349 | 1.6% | 仅被 skills/ 和 tools/ 引用 | 无任何 Agent 使用 |
| `core/tools/draft_tools.py` | 355 | 1.6% | 未使用 | Agent 层直接调 LLM 和 RunningHub，绕过框架 |
| `core/tools/file_tools.py` | 385 | 1.8% | 未使用 | |
| `core/tools/llm_tools.py` | 259 | 1.2% | 未使用 | |
| `core/tools/runninghub_tools.py` | 233 | 1.1% | 未使用 | |
| `core/tools/sort_tools.py` | 223 | 1.0% | 未使用 | |
| `core/skills/*` (5 文件) | 598 | 2.7% | 未使用 | 无人引用 |
| **总计** | **~5395** | **24.8%** | | |

**与报告原估差异分析**：原文估算 ~5152 行，实际验证为 ~5395 行（多 ~243 行）。差异原因：
- 原报告可能遗漏了 `core/tools/sort_tools.py` (223 行)
- `core/tools/` 和 `core/skills/*` 的估算偏低

### 2.3 三套 DAG 定义描述同一流水线

| # | 位置 | 用途 | 内容 | 状态 |
|---|------|------|------|------|
| 1 | `core/project.py:33` STEPS 列表 | 定义步骤顺序 | `["script", "audio", "asset", "prompt", "storyboard", "web_video", "sort", "draft"]` | 被 UI 忽略 |
| 2 | `core/pipeline_engine.py:647-1000` `_execute_step()` if/elif 链 | 定义步骤→Agent 映射 | 8 个分支：script、audio、prompt、asset、storyboard、web_video、sort、draft | 从未被调用 |
| 3 | `core/langgraph_nodes.py` PipelineNodes 类 | 第三套节点定义 | 各有不同参数签名，存在 bug | 从未运行 |

**维护负担**：新增一步需改 3 个地方。且这 3 套定义**都是死代码**——UI 路径根本不使用它们。

### 2.4 UI 步骤与 Pipeline 步骤映射混乱

`main_window.py:20-31` 的 UI 步骤定义与 `core/project.py:33` 的 STEPS 列表之间存在深层映射错位：

| UI 显示名称 | UI 序号 | 文件名 | 对应 Worker | Pipeline 名称 | Pipeline 序号 |
|------------|--------|--------|------------|-------------|-------------|
| 创建项目 | ① | step_01_project.py | 无 Worker | — | — |
| 智能拆分 | ② | step_02_split.py | ScreenplayWorker | script | 1 |
| 生成音频 | ③ | step_04_audio.py | AudioWorker | audio | 2 |
| 角色提示词 | ④ | step_05_char_prompt.py | CharPromptWorker | asset(LLM阶段) | 3 |
| 角色三视图 | ⑤ | step_06_char_image.py | CharImageWorker | asset(图片阶段) | 3 |
| 镜头脚本 | ⑥ | step_07_shot.py | ShotScriptWorker | prompt | 4 |
| 分镜图片 | ⑦ | step_08_storyboard.py | StoryboardWorker | storyboard | 5 |
| 转视频 | ⑧ | step_09_video.py | VideoWorker | web_video | 6 |
| 剪辑拼装 | ⑨ | step_10_edit.py | EditWorker | sort + draft | 7 + 8 |
| 设置 | ⑩ | step_settings.py | 无 Worker | — | — |

**问题清单**：
1. **缺少 step_03**：`steps/` 目录从 step_02 跳到 step_04，无注释说明原因。`workers.py:147` 的注释仍标为"步骤 3：生成音频"，历史遗留：`_archive/step_agent.py` 是原来的 step_03
2. **"sort"和"draft"在 UI 中被合并到步骤"剪辑拼装"**，而 Pipeline 里是 2 个独立步骤
3. **"asset"在 Pipeline 中是单一步骤，在 UI 中被拆为"角色提示词"和"角色三视图"两步**
4. **step_settings.py:1 文档字符串错误**：写"步骤10"但实际 step_10 是"剪辑拼装"

### 2.5 Agent 层和 Tools 层重复实现

| 业务逻辑 | Agent 层实现（已使用） | Tool 层实现（死代码） |
|----------|----------------------|-------------------|
| 草稿生成 | `agents/draft_generator.py` | `core/tools/draft_tools.py`（355 行） |
| 视频排序 | `agents/video_sorter.py` | `core/tools/sort_tools.py`（223 行） |

同一业务逻辑在两个层各自独立实现，且 Tool 层版本从未被使用。

---

## 三、代码质量问题

### 3.1 Bug 清单

#### Bug 1：langgraph_nodes.py:494 参数名错误（原报告已发现）
```python
agent = DraftGenerator(jianji_tool_path=context.config.jianji_tool_path)
```
`DraftGenerator.__init__` 只接受 `ffmpeg_path`（`agents/draft_generator.py:23`），`jianji_tool_path` 不存在。运行必崩。

**关键补充**：由于 `LangGraphPipelineEngine`（`core/pipeline_engine.py:1369`）的 `use_langgraph` 默认 True，且此 bug 是 TypeError 而非 ImportError，**回退机制不会触发**——运行时直接崩溃。

**影响评估**：**高**。`LangGraphPipelineEngine.run()` 行 1431-1441 尝试调用 `self._langgraph_pipeline.run()` 时会崩溃。

#### Bug 2：audio_generator.py 双重初始化（原报告已发现）
`__init__`（第 50-52 行）：
```python
self.post_processor = AudioPostProcessor(ffmpeg_path=ffmpeg_path)
```
`process()`（第 93-95 行）：
```python
self.post_processor = AudioPostProcessor()  # 缺少 ffmpeg_path
```
第二次初始化缺少 `ffmpeg_path` 参数。`process(post_process=True)` 调用会覆盖正确的初始化。

**影响评估**：**中**。音频后处理可能因缺少 ffmpeg 路径而失败，但外表看不出来（静默覆盖）。

#### Bug 3：LLM 缓存单例不检查 cache_path（原报告已发现）
`core/llm_cache.py:322-323`：
```python
if cls._instance is None:
    cls._instance = LLMCache(cache_path)
return cls._instance
```
首次调用使用自定义路径后，后续 `get_cache()` 即使指定不同的 `cache_path` 也返回同一实例。

**影响评估**：**低**。项目中只有一处创建缓存实例的调用路径。

#### Bug 4：seedance_client.py 无锁计数器（原报告已发现）
`core/seedance_client.py:39-40`：`total_tasks` 和 `total_tokens` 在多线程调用时竞态。

**影响评估**：**中**。统计信息不准确，但不会导致功能故障。

#### Bug 5（新增）：_execute_step 中 `step == "prompt"` 使用 `if` 而非 `elif`
`core/pipeline_engine.py:753`：
```python
# 行 704: elif step == "audio":
# ... return
# 行 753: if step == "prompt":     <-- 应该是 elif 不是 if
# ... return
# 行 786: elif step == "asset":
```
其他 7 个分支全用 `elif`，仅此分支用 `if`。目前因每个分支都有 `return` 未触发故障，但若重构时修改了返回逻辑，会成为隐蔽 bug。

**影响评估**：**低**（但不可忽视，修改 `audio` 或 `script` 返回逻辑后会立刻触发）。

#### Bug 6（新增）：`on_step_end` 回调已布线但从未被调用
`core/pipeline_engine.py:420`（接受参数）→ 传播到 `_run_step`（行 548）和 `_run_parallel`（行 1026）→ **从未被调用**。
这是个半实现的废弃回调。

**影响评估**：**低**。不影响功能，但增加代码困惑度。

#### Bug 7（新增）：`_execute_step` 的 `video_dir` 参数是死参数
`core/pipeline_engine.py:648`：sort 步骤在行 978 重新派生自己的 `video_dir`，其他步骤不使用此参数。

**影响评估**：**低**。

#### Bug 8（新增）：`estimate_tokens` 死导入
`core/pipeline_engine.py:26`：
```python
from core.llm_client import LLMClient, estimate_tokens
```
`estimate_tokens` 在文件中从未被使用。成本估算使用硬编码数字（每集 5000 tokens）。

**影响评估**：**低**。

#### Bug 9（新增）：`main_window.py` 死导入
`main_window.py:13-16`：`QFont`、`QAction`、`import styles as S` 均未使用。

**影响评估**：**低**。

#### Bug 10（新增）：`step_settings.py` 文档字符串错误
`steps/step_settings.py:1`：写 "步骤10" 但步骤 10 实际是 `step_10_edit.py`（剪辑拼装）。

#### Bug 11（新增）：`config.yaml` web_video 缺少 api_key 字段
`step_settings.py:346` 保存 `cfg.web_video.api_key` 但 `config.yaml` 没有定义此字段，导致配置无法正确持久化。

**影响评估**：**中**。用户通过 UI 配置的 Seedance API Key 可能丢失，运行时静默回退到 LLM key。

### 3.2 反模式

#### raise SystemExit 在库函数中（5 处，原估 4 处）
`tools/jianying_draft.py` 共 5 处：

| 行号 | 函数 | 代码 |
|------|------|------|
| 32 | `find_first_file()` | `raise SystemExit(f"No files in: {folder}")` |
| 520 | `find_material_folder_smart()` | `raise SystemExit("无法识别媒体素材文件夹...")` |
| 524 | `find_material_folder_smart()` | `raise SystemExit("媒体文件夹中没有找到有效的图片或视频文件")` |
| 535 | `find_material_folder_smart()` | `raise SystemExit("无法识别音频素材文件夹...")` |
| 573 | `main_with_args()` | `raise SystemExit("01* audio folder is empty")` |

另有 `generate_draft()`（行 1056-1060）捕获 SystemExit，但被包装函数直接调用会崩溃 GUI 应用。

**影响评估**：**高**。任何直接调用 `find_first_file()` 等工具函数的代码在 GUI 线程中会崩溃。

#### 运行时修改全局配置对象
`core/langgraph_policies.py:72`：
```python
context.config.runninghub.timeout *= 2
```
修改全局 `PipelineConfig` 实例的 `timeout` 属性，影响后续所有使用同一配置的代码。

**影响评估**：**高**。这是一种"函数副作用"——调用 PolicyEngine 的方法会永久改变全局状态。

#### Workers 取消模式不一致
`workers.py` 中 7 种不同的取消处理方式：

| Worker | 入口检查 | 回调检查 | 传播到 Client | 传播方式 |
|--------|---------|---------|-------------|---------|
| ScreenplayWorker | ✗ | ✗ | ✗ | N/A |
| AudioWorker | ✗ | ✓(不传播) | ✗ | 无 |
| CharPromptWorker | ✓ | ✗ | ✗ | 仅 return |
| CharImageWorker | ✓ | ✓ | ✓ | `rh._cancel_event.set()` |
| ShotScriptWorker | ✓ | ✗ | ✗ | 仅 return |
| StoryboardWorker | ✓ | ✓ | ✓ | `rh._cancel_event.set()` |
| VideoWorker | ✓ | ✓ | ✓ | `client.cancel()` |
| SingleVideoWorker | ✓ | ✓ | ✓ | `client.cancel()` |
| EditWorker | ✗ | ✗ | ✗ | N/A |
| SingleShotRegenWorker | ✓ | ✗ | ✓ | `rh._cancel_event.set()` |
| SingleCharRegenWorker | ✓ | ✗ | ✓ | `rh._cancel_event.set()` |

**3 种不同的传播方式**：
1. 访问私有属性：`rh._cancel_event.set()`（破坏封装）
2. 调用方法：`client.cancel()`（正确方式）
3. 完全不传播：用户点停止后，API 请求继续运行

**影响评估**：**高**。ScreenplayWorker 和 EditWorker 完全无法取消。AudioWorker 仅在回调触发时才可能取消，否则无视停止命令。

#### 导入脆弱性
`agents/draft_generator.py:145`：
```python
from tools.jianying_draft import generate_draft
```
依赖 `run_ui.py:9` 中 `sys.path.insert(0, ...)` 的路径操纵。直接运行 `python agents/draft_generator.py` 会失败。

#### Single*RegenWorker 跳过 _connect_worker
`SingleCharRegenWorker`、`SingleShotRegenWorker`、`SingleVideoWorker` 在 steps/*.py 中实例化时**未调用 `_connect_worker()`**：
- UI 进度条不更新
- 日志不显示
- `set_running(False)` 不触发
- `SingleVideoWorker` 行 569 甚至显式将 `completed` 连接到 `lambda ok, err: None`（无操作）

**影响评估**：**中**。重新生成单张图片/镜头/视频时，UI 状态不会正确更新。

### 3.3 文件过大

| 文件 | 行数 | 占总项目比例 | 问题 |
|------|------|------------|------|
| `agents/storyboard_generator.py` | 1868 | 8.6% | 混合 API 调用、图片处理、并发控制 |
| `core/pipeline_engine.py` | 1509 | 6.9% | 引擎 + 编排 + 自愈 + 步骤路由混合 |
| `workers.py` | 1203 | 5.5% | **12 个 Worker 类挤在一个文件** |
| `tools/jianying_draft.py` | 1062 | 4.9% | 草稿模板操作逻辑集中 |
| `core/ab_test.py` | 1062 | 4.9% | 实质是原型随机数据，从未使用 |

#### workers.py 内部结构分解
| 类 | 行号 | 行数 | 步骤 |
|---|------|------|------|
| BaseWorker | 18-48 | 31 | 基类 |
| ScreenplayWorker | 59-143 | 85 | 拆分剧本 |
| AudioWorker | 150-251 | 102 | 生成音频 |
| CharPromptWorker | 258-314 | 57 | 角色提示词 |
| CharImageWorker | 321-405 | 85 | 角色三视图 |
| ShotScriptWorker | 412-517 | 106 | 镜头脚本 |
| StoryboardWorker | 524-698 | 175 | 分镜图片（最大） |
| VideoWorker | 705-792 | 88 | 转视频 |
| SingleVideoWorker | 795-869 | 75 | 单镜头视频 |
| EditWorker | 876-942 | 67 | 剪辑拼装 |
| SingleShotRegenWorker | 949-1116 | 168 | 单镜头重新生成 |
| SingleCharRegenWorker | 1123-1202 | 80 | 单角色重新生成 |

#### 重复代码
`StoryboardWorker`（行 562-640）和 `SingleShotRegenWorker`（行 1016-1062）间 ~90 行上传角色参考图片、场景参考图片、白色占位图片到 RunningHub 的代码完全重复。

### 3.4 代码异味

- **空文件**：`steps/__init__.py` 0 行；`core/__init__.py` 仅 1 行
- **步骤名称字符串硬编码**："script"、"audio"等在 STEPS 列表、_execute_step 的 if/elif、STEP_DIRS 字典、Worker 内部等多处硬编码
- **`LangGraphPipelineEngine` 类名误差**：原报告称 `PipelineOrchestrator`，实际类名为 `LangGraphPipelineEngine`（行 1369）

---

## 四、缺失项

### 4.1 零测试覆盖
无 `tests/` 目录，无 pytest，无 CI 配置。

### 4.2 多线程竞态条件

| 位置 | 竞态资源 | 风险级别 | 触发路径 |
|------|---------|---------|---------|
| `core/llm_client.py:107-109` | `total_prompt_tokens` 等 3 个计数器 | 中 | `prompt_generator.py:346` ThreadPoolExecutor |
| `core/runninghub_client.py:53` | `total_tasks` | 中 | `web_video_generator.py:164` ThreadPoolExecutor |
| `core/seedance_client.py:39-40` | `total_tasks`, `total_tokens` | 中 | `web_video_generator.py:164` ThreadPoolExecutor |
| `core/seedance_client.py:42` | `self.session` (requests.Session) | 中 | 多线程 `generate_and_wait()` |
| `core/llm_cache.py` | SQLite 连接 | 中 | 多个 get/set 操作未启用 WAL |

### 4.3 缺少输入验证
- `agents/asset_generator.py:311`：直接 `open(script_file, "r")` 读取整个剧本文件，无大小限制
- `core/pipeline_engine.py:669`：`read_script()` 无大小限制
- `agents/screenplay_agent.py:167`：`_parse_response()` 直接解析 LLM 返回的 JSON，无长度检查

### 4.4 缺少步骤 03 的 UI 页面
`steps/` 目录中跳过 `step_03`。`workers.py:147` 注释仍标为"步骤 3：生成音频"。`_archive/step_agent.py` 是原来的 step_03（引导式 Agent 步骤），已被归档但 UI 序号未重新整理。

---

## 五、改进建议

### P0 - 立即执行（预估工时：30 分钟）

1. **密钥管理**：轮换 3 个密钥（RUNNINGHUB_API_KEY、LLM_API_KEY、TOTP_SECRET）
2. **报告安全**：不要在审计报告/文档中明文粘贴密钥

### P1 - 必须修复（预估工时：2-4 天）

3. **修复可运行的 Bug**（1 天）：
   - `audio_generator.py:93-95` 双重初始化
   - `pipeline_engine.py:753` `if` → `elif`
   - `step_settings.py:1` 文档字符串
   - `config.yaml` 添加 web_video.api_key 字段
   - `main_window.py` 移除死导入
   - `pipeline_engine.py:26` 移除死导入

4. **清理死代码框架（~5395 行）**（1 天）：
   - 删除：`core/agent_bus.py`、`core/ab_test.py`、`core/langgraph_*.py`
   - 删除：`core/tool_registry.py` + `core/tools/*`（5 文件）
   - 删除：`core/skills/*`（5 文件）
   - 保留 `pipeline_engine.py` + `project.py` 的 STEPS 作为文档参考

5. **统一取消模式**（0.5 天）：
   - ScreenplayWorker、EditWorker 添加取消检查
   - AudioWorker 添加入口取消检查
   - 所有 Worker 统一使用 `client.cancel()` 方法而非访问私有属性

6. **修复全局配置突变**（0.5 天）：
   - 删除 `langgraph_policies.py:72`（随 langgraph 一起删除即可）

7. **Single\*RegenWorker 修复**（0.5 天）：
   - 为 `SingleCharRegenWorker`、`SingleShotRegenWorker`、`SingleVideoWorker` 添加 `_connect_worker()` 调用

### P2 - 建议修复（预估工时：3-5 天）

8. **替换 jianying_draft.py 中的 raise SystemExit**：定义为 `JianyingDraftError(Exception)`
9. **给 LLMClient 等加线程锁**：为计数器添加 `threading.Lock`
10. **拆分大文件**（2 天）：
    - `workers.py` → `workers/` 目录，12 个类分到 12 个文件（或 4-5 个逻辑分组）
    - `storyboard_generator.py` 拆分 API 层和业务逻辑层
    - 提取 StoryboardWorker 和 SingleShotRegenWorker 的共用图片上传代码
11. **统一导入方式**：修复 `draft_generator.py:145` 的导入
12. **添加最小测试集**（1 天）：3-5 个冒烟测试（配置加载、JSON 解析、缓存读写）
13. **统一各 Agent 的返回字典 key**：`generated`、`episode_count`、`saved_count` 等
14. **LLM 缓存**：启用 SQLite WAL 模式（`PRAGMA journal_mode=WAL`）
15. **添加输入验证**：在读取文件/LLM 响应时添加大小限制
16. **为步骤名称添加集中定义**：使用常量或 Enum 代替字符串硬编码
17. **修复或删除 `core/agent_bus.py:19` 的自导入**：`from core.agent_bus import AgentBus` 是条件自导入
18. **架构决策**：明确选择一条执行路径（UI Worker 或 PipelineEngine），合并或删除另一条

---

## 附录 A：核查记录

### 已核实为正确的原报告结论
- [x] `.env` 在 `.gitignore` 中
- [x] `.env` 从未被提交到 git
- [x] `langgraph_nodes.py:494` 参数错误
- [x] `audio_generator.py` 双重初始化
- [x] `raise SystemExit` 在 GUI 库函数中（实为 5 处，原估 4 处）
- [x] `langgraph_policies.py` 运行时修改全局配置
- [x] 零测试覆盖
- [x] LLMClient 多线程竞态条件
- [x] 导入脆弱性
- [x] 文件过大
- [x] Agent 层和 Tool 层重复实现
- [x] 所有死代码模块核实为未使用

### 原报告有偏差的结论
| 项目 | 原报告 | 实际值 | 偏差原因 |
|------|--------|--------|---------|
| 死代码行数 | ~5152 行 | ~5395 行 | 遗漏 sort_tools.py(223)、draft_tools.py(355)、skills/* 估算偏低 |
| SystemExit 数量 | 4 处 | 5 处 | 遗漏第 535 行 |
| if/elif 链位置 | `_run_step()` | `_execute_step()` | `_run_step` 是错误处理包装器 |
| 类名 | PipelineOrchestrator | LangGraphPipelineEngine | 误读类名 |
| langgraph 回退行为 | ImportError 触发 | TypeError 触发（不会回退） | 低估了影响——不是导入问题而是参数类型错误 |

### 新增发现汇总（原报告未涉及）

#### Bug 类（7 个）
- `_execute_step` 中 `if`/`elif` 不一致（`core/pipeline_engine.py:753`）
- `on_step_end` 回调已布线但未被调用
- `_execute_step` 的 `video_dir` 参数是死参数
- `estimate_tokens` 死导入
- `main_window.py` 死导入（QFont、QAction、import styles）
- `step_settings.py` 文档字符串错误
- `config.yaml` web_video 缺少 api_key 字段

#### 架构类（4 个）
- UI 执行路径与 PipelineEngine 完全脱节（最大发现）
- Worker 取消机制 7 种不同模式
- 步骤映射混乱（UI 10 步 vs Pipeline 8 步）
- Single\*RegenWorker 跳过 _connect_worker 导致 UI 状态不一致

#### 代码质量类（2 个）
- StoryboardWorker 和 SingleShotRegenWorker 间 ~90 行重复代码
- ScreenplayWorker 和 EditWorker 完全无取消支持

## 附录 B：审核方法

本次审核通过以下方式进行：
1. **全局文件扫描**：遍历全部 60+ Python 文件，统计行数和代码结构
2. **引用追踪**：使用 grep 追踪每个模块的导入方，确认死代码范围
3. **Agent 辅助探索**：使用 3 个子 Agent 并行深入分析关键文件
4. **交叉验证**：不同 Agent 在部分发现上重叠（如死代码范围），结果相互印证
5. **git 历史审查**：检查 `.env` 是否被提交过
6. **风险分级**：根据"能否导致运行时崩溃/数据丢失"判断严重程度
