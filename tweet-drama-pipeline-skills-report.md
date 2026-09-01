# 推文短剧 Pipeline Skills 盘点报告

> 盘查范围：E:/aigc-mvp-ui11/aigc-mvp-ui/（AIGC 桌面程序）
> 盘查日期：2026-07-28
> 目标：将每个生产步骤映射为 agent-facing skill，总控 skill `/推文ppt` 只负责串联子 skill

---

## 1. 当前程序步骤总览

### 1.1 UI 步骤（10 步）

| # | 步骤ID | UI 显示名称 | UI 文件 | Worker | 核心模块 | 输入 | 输出 | 调用LLM? | 固定程序? |
|---|--------|------------|---------|--------|---------|------|------|---------|----------|
| 1 | project | 创建项目 | `step_01_project.py` | — | `core/project.py` | 剧本文档(.docx/.txt) | 项目目录、state.json | ❌ | ✅ |
| 2 | script | 本地拆分与过滤 | `step_02_split.py` | `ScreenplayWorker` | `agents/script_processor.py` | 剧本路径 | `{project}/episodes/{01..N}.txt` + `manifest.json` | ❌ | ✅ 纯规则 |
| 3 | audio | 音频生成 | `step_04_audio.py` | `AudioWorker` | `agents/audio_generator.py`、`agents/audio_post_processor.py` | `episodes/*.txt`、音色配置 | `audio/*.flac` + `manifest.json` | ❌ | ✅ RunningHub TTS |
| 4 | asset | 资产生成 | `step_06_asset_generation.py` | `AssetPromptWorker`、`AssetImageWorker`、`SingleAssetRegenWorker`、`NamedAssetImportWorker` | `agents/asset_description_extractor.py`、`agents/asset_generator.py`、`agents/asset_checker.py` | 剧本全集文本 | `assets/{character,scene,prop}/{name}.jpg`、`asset_descriptions.txt`、`asset_context.json` | ✅ 提取角色/场景描述（可选） | ✅ 图生成(RunningHub) |
| 5 | prompt | 生成镜头脚本 | `step_07_shot.py` | `ShotScriptWorker` | `agents/prompt_generator.py` | `episodes/*.txt`、资产白名单 | `prompts/{ep}.txt` | ✅ LLM 生成 | ❌ |
| 6 | storyboard | 分镜图片 | `step_08_storyboard.py` | `StoryboardWorker`、`SingleShotRegenWorker` | `agents/storyboard_generator.py`、`agents/storyboard_checker.py` | `prompts/*.txt`、`asset_descriptions.txt`、`assets/character/*.jpg` | `storyboard/{ep}/{shot}.jpg` | ❌（质检可选LLM） | ✅ RunningHub 分镜工作流 |
| 7 | web_video | 转视频 | `step_09_video.py` | `VideoWorker`、`SingleVideoWorker`、`SortWorker` | `agents/web_video_generator.py`、`core/seedance_client.py` | `storyboard/*.jpg` | `web_video/*.mp4` | ❌ | ✅ Seedance API |
| 8 | sort | 视频排序（隐藏） | (无独立 step) | `SortWorker` | `agents/video_sorter.py`、`sort0.2/cli.py` | `web_video/`、`storyboard/` | `video/{ep}/`（按集整理） | ❌ | ✅ pHash 匹配 |
| 9 | draft | 剪辑拼装 | `step_10_edit.py` | `EditWorker` | `agents/draft_generator.py`、`tools/jianying_draft.py` | `audio/`、`web_video/` 或 `sort/` | 剪映草稿项目目录 | ❌ | ✅ 固定模板 |
| 10 | settings | 设置 | `step_settings.py` | — | `core/config.py` | 用户输入 | `config.yaml` | ❌ | ✅ |

### 1.2 步骤依赖图

```
project ──► script ──┬──► audio ──────────────────┐
                     │                             │
                     ├──► asset ──► prompt ──► storyboard ──► web_video ──► sort ──► draft
                     │         ↓         ↓                ↓
                     │   asset_description    shot_match_manifest   image2video
                     │   _extractor           _build_match_        (Seedance)
                     │   (LLM→描述)            manifest
                     │
                     └──► 可并行: audio + asset（都只依赖 script）
```

---

## 2. Skill 映射表

| 目标 Skill | 复用代码位置 | 输入 | 输出 | 质量守卫 | Codex职责 | 程序职责 | 抽离难度 |
|-----------|------------|------|------|---------|----------|---------|---------|
| **script-split** | `agents/script_processor.py` | 剧本路径(.docx/.txt) | `episodes/{ep}.txt`、`manifest.json` | 集数识别、重复集校验、正文为空/过短检测、下集预告过滤、版本前缀清理 | 复核少字/漏字、处理异常拆分 | 读取文件、正则拆分、过滤、写入 | ⭐ 低（纯规则+文件IO） |
| **asset-extract** | `agents/asset_description_extractor.py`、`prompts/default_asset_prompt.txt` | 剧本全文 | `asset_descriptions.txt`、`character_prompts.txt`、`scene_prompts.txt`、`prop_prompts.txt`、`asset_context.json` | 别名重复、集数冲突、阶段拆分合理性、描述长度 | 读取剧本→LLM提取角色/场景/道具描述→输出结构化文本 | 读取文件、写文件、构建asset_context.json、落盘 | ⭐⭐ 中（LLM+文件写） |
| **asset-generate** | `agents/asset_generator.py`、`core/runninghub_client.py`、`workflows/asset_generation.json` | 资产名+prompt+类别、RunningHub workflow_id | `assets/{character,scene,prop}/{name}.jpg` | 图片质量质检（可选LLM）、跳过已有、失败重试 | 可选：判断生成结果是否需重试 | 提交RunningHub、下载、命名、跳过检查、质检 | ⭐ 低（纯API调用） |
| **asset-vision-check** | `core/asset_image_import.py`、`agents/asset_description_extractor.py`(vision部分) | 用户上传的图片 | `assets/{category}/{name}.jpg`、更新后的描述文件和`asset_context.json` | 图片格式、尺寸、命名合规 | 看图→反推中文名+别名+集数+视觉提示词 | 图片复制/移动、更新清单 | ⭐⭐ 中（需要Codex视觉） |
| **shot-script-write** | `agents/prompt_generator.py`、`prompts/default_shot_prompt.txt`、`agents/shot_parser.py` | `episodes/{ep}.txt`、资产白名单 | `prompts/{ep}.txt` | 13-18镜头、连续编号、必填字段、角色/场景/道具正式名、格式校验 | 读剧本+资产图→LLM生成镜头脚本 | 读取episode、加载白名单、格式校验、写入 | ⭐⭐⭐ 高（核心LLM任务） |
| **shot-asset-match** | `core/shot_match_manifest.py`、`core/asset_context.py` | `prompts/{ep}.txt`、`asset_context.json` | `matches/{ep}.json` | 别名冲突分析、服装变体偏好、无匹配资产告警 | —（纯固定程序） | 解析脚本、匹配资产、构建manifest | ⭐ 低（纯数据匹配） |
| **storyboard-generate** | `agents/storyboard_generator.py`、`workflows/storyboard_4shot.json`、`workflows/storyboard_9shot.json` | `prompts/{ep}.txt`、`matches/{ep}.json`、角色参考图 | `storyboard/{ep}/{shot}.jpg` | RunningHub 失败重试、分镜质检（可选LLM） | 未来：Codex imagegen 替代RunningHub | 批量提交、下载、分批策略、角色参考图上传 | ⭐⭐ 中（API调用） |
| **storyboard-guard** | `agents/storyboard_checker.py` | 分镜图片+对应shot脚本 | 质检报告（九宫格、横图、文字、比例、风格） | 画面分割检测、字幕检测、横图检测、比例9:16、真人风格判定 | LLM视觉判断：图片是否有文字、是否是动漫、人物是否正确 | 程序化规则（比例、九宫格等） | ⭐⭐ 中（视觉LLM+规则） |
| **audio-generate** | `agents/audio_generator.py`、`agents/audio_post_processor.py`、`core/voice_library.py` | `audio/*.flac` + `manifest.json`、音色配置 | `audio/{ep}.*` | 去气口、静音裁剪、响度归一化 | 询问用户音色偏好、处理发音纠正 | TTS提交、下载、后处理、文件落盘 | ⭐ 低（纯API调用） |
| **draft-build** | `agents/draft_generator.py`、`tools/jianying_draft.py`、`agents/video_sorter.py` | 音频+视频素材 | 剪映草稿目录、materials目录 | 素材齐全性检查 | —（纯固定程序） | 素材整理、排序、剪映草稿生成 | ⭐ 低（固定工具链） |
| **project-inspect** | `core/episode_status.py`、`core/project.py`、`core/manifest.py` | 项目目录 | 状态报告 | 缺文件、错命名、数量不足、无效prompt | —（纯固定程序） | 扫描目录、比对预期、输出报告 | ⭐ 低（纯扫描） |

---

## 3. 每个 Skill 的详细设计草案

### 3.1 script-split

**触发场景**：用户上传剧本 → 需要按集拆分

**前置条件**：项目目录已创建，剧本文件存在于 `state.json` 的 `script_path`

**读取文件**：
- `{project}/state.json` → 获取 `script_path`
- `{script_path}` → 原始剧本 (.docx/.txt)

**写入文件**：
- `{project}/episodes/{ep}.txt` → 按清洗后的分集文本
- `{project}/episodes/manifest.json` → `{version, source_path, filter_options, episodes: {ep: {sha256, char_count}}}`

**调用函数/CLI**：
- `agents/script_processor.py` → `ScriptProcessor.analyze()` + `ScriptProcessor.save()`
- 纯本地正则，无网络调用

**Codex 职责**：
- 复核 `warnings` 字段：正文过短、集数跳跃、重复段落
- 处理脚本处理器无法自动分集的边界情况
- 决定是否启用/关闭特定 filter_option

**成功标准**：
- `episodes/` 下有 N 个 `.txt`，N == 预期集数
- 每个 `.txt` 非空且内容可读
- `manifest.json` 中的 `sha256` 与文件一致

**失败处理**：
- 重复集号 → 报错，要求用户修正源文件
- 空正文 → 报警告，人工确认
- 文件编码问题 → 重试 gb18030/utf-8-sig

---

### 3.2 asset-extract

**触发场景**：剧本拆分完成 → 需要提取角色/场景/道具描述

**前置条件**：`{project}/source/` 存在（通过 `ProjectScriptSource` 初始化）

**读取文件**：
- `{project}/source/normalized.txt` 或 `{project}/analysis/episodes/*.txt` → 剧本全文
- `{project}/prompts/*.txt`（可选，用于角色名册注入，确保资产名与镜头脚本一致）
- `prompts/default_asset_prompt.txt` 或 `prompts/default_character_prompt.txt` → LLM 提示词模板

**写入文件**：
- `{project}/assets/asset_descriptions.txt` → `名称|别名|集数|中文描述prompt`
- `{project}/assets/character_prompts.txt` → 同上，仅角色
- `{project}/assets/scene_prompts.txt` → 同上，仅场景
- `{project}/assets/prop_prompts.txt` → 同上，仅道具
- `{project}/assets/asset_context.json` → 结构化资产清单（版本4）

**调用函数**：
- `agents/asset_description_extractor.py` → `AssetDescriptionExtractor.extract()`（LLM 调用）
- `core/asset_context.py` → `load_or_build_asset_context()` → `build_asset_context()`（纯数据组装）
- `workers.py` 中的 `AssetPromptWorker`、`CharPromptWorker`（线程封装）

**Codex 职责**：
- **读剧本→LLM提取**：角色名称、别名、年龄段/阶段拆分、外貌描述；场景名称、地点风格、光线氛围
- 判断是否有阶段性变化（前期/中期/后期→拆成独立资产记录）
- 判断描述中是否有违规内容（文字、数字、年龄标签等）
- 当用户提供参考图时，**看图生成描述**（视觉能力替代纯文本LLM）

**固定程序职责**：
- 解析 LLM 返回的 `名称|别名|集数|描述` 格式行
- 写入 4 个文本文件
- 调用 `build_asset_context()` 扫描磁盘文件生成结构化 JSON
- 多阶段变体的索引合并

**成功标准**：
- `asset_descriptions.txt` 非空，每行格式正确
- `asset_context.json` 版本号为 4，包含所有资产条目
- 角色图、场景图、道具图类别不混

**失败处理**：
- LLM 返回格式不合规 → 重试（调整 prompt）
- 描述中含有违规文字 → Codex 自行修正

---

### 3.3 asset-generate

**触发场景**：资产描述提取完成 → 需要生成角色/场景/道具图片

**前置条件**：`asset_descriptions.txt` 或对应的 `*_prompts.txt` 存在

**读取文件**：
- `{project}/assets/{character_prompts,scene_prompts,prop_prompts}.txt` → 名称+prompt
- `config.yaml` → `workflow_ids.asset_generation`、`runninghub.*`
- `workflows/asset_generation.json` → RunningHub 工作流定义

**写入文件**：
- `{project}/assets/character/{name}.jpg`
- `{project}/assets/scene/{name}.jpg`
- `{project}/assets/prop/{name}.jpg`
- 更新 `asset_descriptions.txt`（图片路径列，可选）

**调用函数/CLI**：
- `agents/asset_generator.py` → `AssetGenerator.process()` 或 `process_from_file()`
- `core/runninghub_client.py` → `RunningHubClient.batch_run()`、`download_file()`
- `agents/asset_checker.py`（可选 LLM 质检）

**Codex 职责**：无。这是一步纯固定程序调用。

**固定程序职责**：
- 读取 description 文件，解析每行
- 对每个 asset 提交 RunningHub 工作流（prompt 注入 + 参数配置）
- 下载返回的图片，按规范命名存入对应子目录
- 跳过已有图片（可选）
- LLM 质检（可选，配置启用时）
- 更新 asset_context.json（新增图片路径字段）

**成功标准**：
- 每个角色/场景都有对应图片
- 图片格式为 jpg/png/webp，非空
- 图片名与资产名一致

**失败处理**：
- RunningHub 超时 → 重试（最多 3 次）
- 图片质量不合格 → 报告问题，手工或自动重生成
- 图片过小（< 512 bytes）→ 标记失败

---

### 3.4 shot-script-write

**触发场景**：资产提取完成 → 需要写每一集的镜头脚本

**前置条件**：`episodes/{ep}.txt` 和 `asset_context.json` 存在

**读取文件**：
- `{project}/episodes/{ep}.txt` → 该集文本
- `{project}/assets/asset_context.json` → 角色/场景/道具白名单（含正式名、别名、集数范围）
- `{project}/assets/{character,scene}/*.jpg`（可选，Codex 看图辅助写镜头）
- `prompts/default_shot_prompt.txt` → LLM 提示词模板

**写入文件**：
- `{project}/prompts/{ep}.txt` → 严格格式的镜头脚本

**调用函数**：
- `agents/prompt_generator.py` → `PromptGenerator.process()`（LLM 调用）
- `agents/shot_parser.py` → `analyze_shots()`（格式校验）
- `agents/asset_txt_analyzer.py` → `read_asset_txt()`（加载资产白名单）

**Codex 职责**：
- **读剧本资产→LLM写分镜**：逐集将剧本转化为 13-18 个镜头的结构化脚本
- 参考资产图片判断角色外貌、场景色调
- 确保：
  - 出镜人物【正式名】 使用白名单中的角色名
  - 核心场景使用白名单中的场景名
  - 关键道具【正式名】 使用白名单中的道具名
  - 画面描述包含：景别、角色站位、动作情绪、视线关系
  - 台词逐字原文引用
  - 旁白使用剧本原文
- 判断别名：剧本中的"我"、"他"等代称推断为正式名

**固定程序职责**：
- 加载 episode 文本
- 加载资产白名单（从 asset_context.json 中提取正式名列表）
- 解析 LLM 输出格式（镜头N：...）
- 格式校验：13-18 镜头、连续编号、必填字段存在
- 写入 `prompts/{ep}.txt`

**成功标准**：
- 每集有 13-18 个镜头
- 每个镜头编号连续，从 1 到 N
- 每个镜头包含 `出镜人物【】` `核心场景：` `关键道具【】` `画面描述：【】`
- 角色名、场景名、道具名均在白名单中
- 格式可被 `shot_parser.py` 正确解析

**失败处理**：
- LLM 输出格式错误 → 重试（更严格的指令）
- 镜头数不足 13 → 自动补充或重新生成
- 角色名不在白名单 → Codex 自行修正为最接近的正式名

---

### 3.5 storyboard-generate

**触发场景**：镜头脚本完成 → 需要为每个镜头生成图片

**前置条件**：`prompts/{ep}.txt` 和 `matches/{ep}.json` 存在

**读取文件**：
- `{project}/prompts/{ep}.txt` → 镜头脚本
- `{project}/matches/{ep}.json` → 资产匹配结果
- `{project}/assets/character/*.jpg` → 角色参考图
- `config.yaml` → `workflow_ids.storyboard_4shot`、`storyboard_9shot`

**写入文件**：
- `{project}/storyboard/{ep}/{shot_idx}.jpg`

**调用函数**：
- `agents/storyboard_generator.py` → `StoryboardGenerator.process()`
- `core/runninghub_client.py` → `batch_run()`、`upload_media()`
- `core/shot_match_manifest.py` → `build_match_manifest()`、`load_match_manifest()`、`save_match_manifest()`

**未来切换 Codex imagegen 时**：
- `core/gpt_storyboard_pack.py` → `export_gpt_storyboard_pack()`（输出每镜头的结构化 job）
- Codex 接收 job → 调用 imagegen → 图片 url 返回 → 固定工具下载落盘

**Codex 职责**（未来 imagegen 方案）：
- 接收 `{ep, shot_idx, prompt, reference_images}` 的 job 数组
- 调用 imagegen 生成每镜头图片
- 判断生成结果是否需要重试

**固定程序职责**（当前）：
- 智能分批（≤4→4shot，5-9→9shot，>9多批）
- 智能工作流选择（动作戏/对话戏/空镜）
- 上传角色参考图到 RunningHub
- 提交 RunningHub 工作流
- 下载图片，按 `{ep}/{shot_idx}.jpg` 命名
- 重试失败任务
- 可选 LLM 质检

**成功标准**：
- 每集每个镜头都有对应图片
- 图片比例 9:16
- 图片非空、非损坏
- 文件名与镜头索引一致

**失败处理**：
- RunningHub 失败 → 自动重试（带指数退避）
- 质检不通过 → 加入 constraint prefix 重新生成
- 参考图上传失败 → 忽略，使用无参考生成

---

## 4. 第一批优先实现建议

### 4.1 script-split（难度 ⭐）

**建议**：直接封装为 CLI 工具，Codex 通过 subprocess 调用。

**理由**：
- 已经 100% 纯规则，无需 LLM
- `ScriptProcessor` 输入输出清晰，无外部依赖
- 唯一需要 Codex 介入的是复核 warnings

**实现方式**：
```
twpipeline.py split --script <path> --output <dir> [--filter-options ...]
```

### 4.2 asset-extract（难度 ⭐⭐）

**建议**：Codex 直接读取剧本和 prompt 模板，调用 LLM 角色后生成结构化文本，固定工具负责写入文件系统和构建 `asset_context.json`。

**理由**：
- 核心是 LLM 阅读理解（Codex 强项）
- 目前 `AssetDescriptionExtractor` 有 44KB 代码，大量文件读写+LLM调用混合，需要拆分

**分离点**：
- Codex：读剧本 → LLM 提取 → 输出结构化文本（`名称|别名|集数|描述`）
- 程序：解析文本行 → 写入 `*_prompts.txt` → 调用 `build_asset_context()` → 写入 `asset_context.json`

### 4.3 asset-generate（难度 ⭐）

**建议**：封装为纯 CLI 工具，接收描述文件路径 + 类别参数。

**理由**：
- 纯 API 调用，无 LLM 参与
- `AssetGenerator` 接口已经很清晰

**实现方式**：
```
twpipeline.py asset-generate --descriptions <file> --category <character|scene|prop> --output <dir>
```

### 4.4 shot-script-write（难度 ⭐⭐⭐）

**建议**：核心 LLM 写作任务，Codex 主导。固定工具只做格式校验。

**理由**：
- 需要理解剧本内容、参考资产图片、遵循严格的格式约束
- 现在有 54KB 的 `prompt_generator.py`，大量代码在管理 LLM 调用+格式解析+重试逻辑

**分离点**：
- Codex：读 episode 文本 + 资产白名单 + 资产图片 → LLM 写镜头脚本
- 程序：`agents/shot_parser.py` 的 `analyze_shots()` 作为纯校验工具
- 程序：读结果 → 写入 `prompts/{ep}.txt`

### 4.5 storyboard-generate（难度 ⭐⭐）

**建议**：当前保持 RunningHub 方案（固定程序），后续切换 Codex imagegen。

**理由**：
- 当前链路成熟：`gpt_storyboard_pack.py` 已输出结构化 job
- 未来迁移到 Codex imagegen 时，将 `gpt_storyboard_pack` 的 job 直接喂给 Codex

**实现方式**：
```
twpipeline.py storyboard-export --project <dir> --episodes 01..N
# 输出 gpt_storyboard_pack.zip，含每镜头 prompt + 参考图
```

---

## 5. 风险和缺口

### 5.1 现有代码耦合点

| 位置 | 耦合问题 | 影响 |
|------|---------|------|
| `core/pipeline_engine.py` | 所有 Agent 都依赖 `PipelineConfig` 和 `Project`，解耦需要层间接口 | 无法单独调用单个 Agent |
| `agents/asset_description_extractor.py` | 44KB 单文件，LLM 调用+文件读写+格式解析混合 | 难以剥离出纯 LLM 部分 |
| `agents/prompt_generator.py` | 54KB 单文件，LLM+校验+重试+分批混合 | 同上 |
| `agents/storyboard_generator.py` | 128KB 单文件（最大），RunningHub 提交+分批+角色映射+重试混合 | 最难拆分 |
| `core/runninghub_client.py` | 43KB，所有 Agent 共享同一个 RunningHub 客户端 | 并发限制共享 |
| `steps/step_02_audio.py` | 把 `step_02_split` + `step_04_audio` 合并为一个新页面，但旧的独立页面还在 | 逻辑重复 |
| `steps/step_06_char_image.py` | 角色图片生成独立页面，与 `step_06_asset_generation.py` 功能重叠 | 功能重复 |

### 5.2 乱码/编码风险

| 场景 | 风险 | 当前处理 |
|------|------|---------|
| 剧本文件编码 | 用户上传的 `.txt` 可能为 GBK/GB18030/UTF-8-BOM | `read_script()` 按 utf-8-sig → utf-8 → gb18030 自动探测 |
| LLM 返回中文 | LLM 返回编码一致，无问题 | — |
| 文件名含特殊字符 | Windows 文件系统限制 | `INVALID_NAME_CHARS` 集和保留名检查 |
| 剪映草稿路径 | 草稿目录可能含中文 | 使用 UTF-8 |
| RunningHub 文件类型 | 音频下载格式配置为 `flac` | 在配置中指定 |

### 5.3 RunningHub 依赖风险

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| API 配额不足 | 资产/音频/分镜全部阻塞 | `usage_ledger.py` 跟踪消耗；`max_quality_retries` 限制重试 |
| 超时 | 长 prompt 生成超时 | 配置 `timeout: 600`、`poll_interval: 5`、`retry_count: 3` |
| 工作流变更 | 本地 `workflows/*.json` 与服务端不同步 | 使用 `workflow_id` + `workflow_path` 双配置 |
| 并发限制 | 同时提交过多任务被限流 | `max_concurrency: 5`（全局）、`max_concurrency: 3`（视频） |
| 下行带宽 | 批量下载图片/音频时 I/O 瓶颈 | 使用 `ThreadPoolExecutor` + 下载 retry |

### 5.4 Codex imagegen 批量生成限制

| 限制 | 说明 | 影响程度 |
|------|------|---------|
| 并发生成数 | Codex 无法同时生成 >5 张图片 | 逐镜生成时，13 镜/集 × N 集 = 时间较长 |
| 图生图支持 | Codex imagegen 是否支持 reference image + prompt | 若只支持文生图，参考图注入需额外处理 |
| 图片尺寸/比例 | 是否支持 9:16 竖屏 | 默认多为 1:1/4:3，可能需要后处理 |
| 一致性 | 同一角色在相邻镜头间外观是否一致 | 依赖 prompt 工程 + seed |
| 成本 | ≈ RunningHub 积分 vs Codex direct API cost | 需要实测对比 |

### 5.5 需要新增 CLI 的地方

| 功能 | 建议 CLI 名 | 说明 |
|------|-----------|------|
| 剧本拆分 | `twpipeline.py split` | 封装 `ScriptProcessor` |
| 资产提取 | （CLI 非必须） | Codex 直接生成文本，程序只写文件 |
| 资产生成 | `twpipeline.py asset-generate` | 封装 `AssetGenerator` |
| 镜头脚本检验 | `twpipeline.py validate-shot` | 封装 `shot_parser.py` 的格式校验 |
| 资产匹配 | `twpipeline.py match-assets` | 封装 `shot_match_manifest.py` |
| 分镜包导出 | `twpipeline.py export-storyboard-pack` | 封装 `gpt_storyboard_pack.py` |
| 音频生成 | `twpipeline.py audio-generate` | 封装 `AudioGenerator` |
| 视频排序 | `twpipeline.py video-sort` | 封装 `VideoSorterAgent` |
| 剪映草稿 | `twpipeline.py build-draft` | 封装 `DraftGenerator` |
| 项目检查 | `twpipeline.py inspect` | 封装 `EpisodeStatusService` |

---

## 附录：当前项目目录结构

```
{project}/
├── state.json                     # ProjectState（步骤状态、集数）
├── manifest.json                  # ProjectManifest（每集每步骤的 artifact 记录）
├── source/                        # ProjectScriptSource
│   └── original.{txt,docx}        # 原始剧本副本
├── analysis/                      # 剧本分析
│   ├── source_segments.json       # 分段元数据
│   └── episodes/{ep}.txt          # 原始分段文本（不经过滤，供 asset/LLM 使用）
├── episodes/                      # script 步骤输出（经过滤）
│   ├── {ep}.txt
│   └── manifest.json
├── audio/                         # audio 步骤输出
│   ├── {ep}.flac
│   └── manifest.json
├── assets/                        # asset 步骤输出
│   ├── asset_context.json         # 结构化资产索引（版本4）
│   ├── asset_descriptions.txt     # 全资产统一描述
│   ├── character_prompts.txt      # 角色描述
│   ├── scene_prompts.txt          # 场景描述
│   ├── prop_prompts.txt           # 道具描述
│   ├── character/{name}.jpg       # 角色图片
│   ├── scene/{name}.jpg           # 场景图片
│   └── prop/{name}.jpg            # 道具图片
├── prompts/                       # prompt 步骤输出
│   ├── {ep}.txt                   # 镜头脚本
│   └── prompt_manifest.json       # 可选
├── matches/                       # shot-asset-match 输出
│   └── {ep}.json                  # 镜头-资产绑定 manifest
├── storyboard/                    # storyboard 步骤输出
│   └── {ep}/{shot_idx}.jpg
├── web_video/                     # web_video 步骤输出
│   └── {ep}_{shot_idx}.mp4
├── video/                         # sort 步骤输出
│   └── {ep}/{filename}.mp4
├── draft/                         # draft 步骤输出（剪映草稿）
└── _materials/                    # 草稿素材暂存
```

---

## 附录：Skill 包目录结构建议

```
.agents/skills/推文短剧-pipeline/
├── SKILL.md                          # 总控 /推文ppt 工作流
├── references/
│   ├── project-layout.md             # 项目目录结构说明
│   ├── quality-gates.md              # 统一质量守卫规则
│   └── cli-contract.md               # CLI/MCP 输入输出约定
└── scripts/
    ├── twpipeline.py                 # 统一 CLI 入口
    ├── split.py                      # script-split
    ├── asset_generate.py             # asset-generate
    ├── asset_extract.py              # asset-extract（可选，非必需）
    ├── validate_shot.py              # shot 校验
    ├── match_assets.py               # shot-asset-match
    ├── export_storyboard_pack.py     # storyboard-generate 打包
    ├── audio_generate.py             # audio-generate
    ├── video_sort.py                 # 视频排序
    ├── build_draft.py                # 剪映草稿
    └── inspect.py                    # 项目检查
```
