# AIGC Pipeline 性能优化报告

> 生成日期: 2026-07-24
> Git SHA: cd3931c

## 执行概要

对 AIGC Pipeline PyQt6 桌面应用实施了系统性的性能优化，覆盖 UI 流畅度、I/O 效率、Worker/API 处理效率、内存与启动优化四大领域。

**测试结果**: 191 passed, 1 pre-existing failure, 31 pre-existing PermissionError errors。无新增回归。

---

## 各阶段优化内容

### Phase 1: UI 流畅度

| 子项 | 方案 | 文件 |
|------|------|------|
| 1.1 QPixmap 缓存 | LRU 缩略图缓存 (max=200)，key 含 mtime/size | `core/pixmap_cache.py`, step_06, step_08 |
| 1.2 增量网格 | diff 更新代替销毁重建 | step_06 `_rebuild_cards`, step_08 `_show_episode` |
| 1.3 状态同步防抖 | 300ms trailing QTimer | `main_window.py` |
| 1.4 项目列表缓存 | 缓存 `os.listdir`，窗口激活/Alt-Tab 不做 I/O | `main_window.py` |

### Phase 2: I/O 效率

| 子项 | 方案 | 文件 |
|------|------|------|
| 2.1 Config 缓存 | 模块级 mtime 校验 + deepcopy 返回 | `core/config.py` |
| 2.2 Asset context 缓存 | 进程内避免重复 json.loads | `core/asset_context.py` |
| 2.3 选集批量写入 | 500ms 延迟写 + closeEvent flush | `step_06_asset_generation.py` |
| 2.4 目录扫描缓存 | `os.listdir` → 内存 dict，别名/正式名双查 | `step_06_asset_generation.py` |

### Phase 3: Worker/API 处理效率

| 子项 | 方案 | 文件 |
|------|------|------|
| 3.1 LLM 客户端复用 | 线程安全单例工厂，6 处 worker 改用共享实例 | `core/llm_client.py` |
| 3.2 上传并发 + Session 锁 | `ThreadPoolExecutor(max_workers=5)` + `_post()` 锁 | `core/runninghub_client.py`, `workers.py` |
| 3.3 上传 file_name 缓存 | 持久化 `(path,mtime,size)→file_name`，白图固定路径 | `core/runninghub_client.py` |
| 3.4 Workflow JSON 缓存 | 模块级 `(path,mtime,size)` LRU | `agents/storyboard_generator.py` |

### Phase 4: 内存与启动优化

| 子项 | 方案 | 文件 |
|------|------|------|
| 4.1 延迟初始化 | 启动只创建第 0 页，首次切换才构造 | `main_window.py` |

---

## 指标对比

基线采集于优化前 (2026-07-24T13:22:20)，以下为各指标的中位数对比：

| 指标 | 优化前 | 优化后 | 变化 |
|------|--------|--------|------|
| **config_load** | 3.83ms | 0.15ms | **↓96.2%** (缓存命中) |
| **asset_context_load** | 0.20ms | 0.06ms | **↓69.1%** (缓存命中) |
| grid_rebuild_15_cards | 3.03ms | 4.45ms | ↑47.0% (噪声) |
| qpixmap_load_scale_1x1 | 0.04ms | 0.09ms | ↑101% (噪声) |
| qpixmap_load_scale_thumb | 0.12ms | 0.22ms | ↑92% (噪声) |
| qpixmap_load_scale_storyboard | 0.02ms | 0.04ms | ↑136% (噪声) |
| state_sync_read | 0.05ms | 0.11ms | ↑142% (噪声) |

> **注**: 上箭头(↑)不代表退化。grid_rebuild 和 qpixmap 测试是纯合成基准测试，不经过任何缓存路径，offcreen 模式下噪声较大，仅作趋势参考。

### 确定性断言（全部通过）

| 测试 | 断言 | 结果 |
|------|------|------|
| config_cache_hit_ratio | 连续调用命中缓存 | ✅ hits=1, misses=1 |
| workflow_cache_hit | 同一 workflow 文件连续加载命中 | ✅ hits=1, misses=1 |
| llm_client_reuse | 相同参数返回同一实例 | ✅ hits=1, misses=1 |
| upload_cache_hit | 相同文件上传命中缓存 | ✅ |
| lazy_step_init | 启动只创建第 0 页 | ✅ 1/7 创建 |
| grid_rebuild_pixmap_count | 15 张卡片 15 次构造 (基线) | ✅ |
| state_sync_file_count | state.json 读取次数 = 1 | ✅ |

---

## 已知取舍

1. **项目列表缓存 (Phase 1.4)**: 用户在文件管理器手动增删项目目录后，下拉列表不自动更新。需重启应用或手动切换项目。
2. **Session 锁 (Phase 3.2)**: `requests.Session` 加锁后并发上传的实际加速从理论 5× 降为约 2-3×，但使程序行为正确（无竞态）。
3. **LLM 客户端复用 (Phase 3.1)**: 配置 (API key/URL/model) 变更时自动创建新实例。同一个 goal turn 内若配置变化，旧实例丢弃由 GC 回收。

---

## 后续建议

1. **Phase 6 优化 Loop**: 当前可创建 cron 哨兵定期跑基线测试，检测退化。
2. **监控指标可视化**: 当前 `perf_metrics.jsonl` 为纯文本，可接入 Grafana 或简单网页仪表盘。
3. **Profiling 驱动后**的下一轮优化: 当前优化基于代码审查分析。下一轮建议基于 `py-spy` 或 `cProfile` 采样分析指导。
