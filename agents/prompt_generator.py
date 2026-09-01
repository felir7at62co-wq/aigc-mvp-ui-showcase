"""
AIGC Pipeline — Step 3: 镜头脚本生成 Agent

由原镜头提示词模块演进而来:
  - src/shot_generator.py → ShotGenerator._generate_single, _chunked_generate
  - src/prompt_builder.py → PromptBuilder
  - src/ai_client.py → AIClient (已迁移到 core/llm_client.py)

功能: 读取分集文本 → LLM 生成镜头脚本 → 写入 prompts/ 目录
"""
import os
import re
import logging
import tempfile
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List, Optional, Tuple

from core.llm_client import LLMClient, estimate_tokens

logger = logging.getLogger(__name__)

_LEGACY_VISUAL_DETAIL_FIELDS = {
    "风格：【",
    "景别：【",
    "构图：【",
    "机位：【",
    "角度：【",
    "镜头类型：【",
    "运镜：【",
    "视觉重点：【",
    "角色状态追踪：【",
    "台词/旁白对应：【",
}


# ========== Schema 声明 ==========

@dataclass
class PromptSchema:
    """
    镜头脚本输出格式校验规则。

    可从模板文件的 ---SCHEMA--- 段加载，也可使用默认值。
    默认值与现有硬编码 DEFAULT_USER_INSTRUCTION 中的 "镜头N：" 格式兼容。
    """
    # 镜头分隔符正则（用于拆分镜头块）
    delimiter: str = r"镜头\s*\d+\s*[：:]?"
    # 每个镜头块中必须出现的字段（子串匹配）
    required_fields: List[str] = field(default_factory=lambda: [
        "出镜人物【", "核心场景", "关键道具【", "画面描述：【"
    ])
    # 全局必需字段（在输出开头部分出现）
    header_fields: List[str] = field(default_factory=lambda: ["出镜人物【"])
    # 最少/最多镜头数
    min_shots: int = 13
    max_shots: int = 18

    @classmethod
    def from_text(cls, text: str) -> "PromptSchema":
        """从 ---SCHEMA--- 段的文本解析 schema 配置。"""
        schema = cls()
        for line in text.strip().splitlines():
            line = line.strip()
            # 跳过注释和空行
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if not value:
                continue

            if key == "delimiter":
                schema.delimiter = value
            elif key == "min_shots":
                try:
                    schema.min_shots = int(value)
                except ValueError:
                    logger.warning(f"Schema min_shots 值无效: {value}，使用默认值")
            elif key == "max_shots":
                try:
                    schema.max_shots = int(value)
                except ValueError:
                    logger.warning(f"Schema max_shots 值无效: {value}，使用默认值")
            elif key == "required_fields":
                # 格式: required_fields: 后跟多行 "  - xxx"
                # 这里处理单行内联列表的情况不太适用，
                # 改在 _parse_schema_block 中处理多行列表
                pass
            elif key == "header_fields":
                pass

        return schema
    @classmethod
    def _parse_schema_block(cls, text: str) -> "PromptSchema":
        """
        解析完整 schema 文本块，支持多行列表字段。

        格式示例:
            delimiter: \\*\\*\\s*\\d+\\s*\\*\\*画面描述[：:]
            required_fields:
              - 画面描述
              - 出镜人物【
            header_fields:
              - 出镜人物【
              - 出镜场景
            min_shots: 3
            max_shots: 18
        """
        schema = cls()
        lines = text.strip().splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            i += 1
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                continue

            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()

            # 检查是否为列表字段（值为空，下一行以 - 开头）
            if not value and i < len(lines) and lines[i].strip().startswith("-"):
                items = []
                while i < len(lines) and lines[i].strip().startswith("-"):
                    item = lines[i].strip().lstrip("-").strip()
                    if item:
                        items.append(item)
                    i += 1
                if key == "required_fields":
                    schema.required_fields = items
                elif key == "header_fields":
                    schema.header_fields = items
                continue

            if key == "delimiter":
                schema.delimiter = value
            elif key == "min_shots":
                try:
                    schema.min_shots = int(value)
                except ValueError:
                    logger.warning(f"Schema min_shots 值无效: {value}，使用默认值")
            elif key == "max_shots":
                try:
                    schema.max_shots = int(value)
                except ValueError:
                    logger.warning(f"Schema max_shots 值无效: {value}，使用默认值")

        return schema


@dataclass(frozen=True)
class ShotGenerationOutcome:
    """Unpublished result of one episode's generation and audits."""

    text: str
    valid: bool
    issues: tuple[str, ...]
    attempts: int


# ========== 默认提示词模板 ==========

DEFAULT_SYSTEM_PROMPT = """你是一位专业的影视分镜脚本编剧，擅长将剧本/剧情文本转化为详细的镜头脚本。
你必须严格根据提供的剧本原文内容进行镜头脚本生成，不要添加原文中没有的情节。
输出格式必须清晰、结构化，便于导演和分镜师直接使用。
注意区分台词和旁白——台词以外的文本均为旁白。"""

DEFAULT_USER_TEMPLATE = """以下是剧本第{episode_number}集的内容：

---剧本开始---
{screenplay_text}
---剧本结束---

{character_roster}请根据以上剧本内容，{user_instruction}"""

DEFAULT_USER_INSTRUCTION = (
    "严格根据上述全部文本内容生成对应的镜头脚本。"
    "台词以外的文本均为旁白。一段旁白/台词对应1-2个镜头,"
    "总时长不超过180秒，镜头数范围13-18个（不少于13个、不超过18个），"
    "内容必须包括且不仅限于：镜头N（如镜头1、镜头2...）；出镜人物【】；核心场景；关键道具【】；"
    "画面描述：【真人短剧风格 + 景别 + 人物站位（左/右/前/后） "
    "+ 角色关系（对峙/对话/围观） + 视线关系（A看B/B看A） "
    "+ 核心动作或情绪 + ；音效。标出哪个角色的台词，不要用表格\n\n"
    "【格式要求】\n"
    "1. 每个镜头必须以\"镜头N：\"开头（N为阿拉伯数字，从1开始递增）\n"
    "2. 出镜人物必须使用中文方括号【】包裹，多个角色用顿号、分隔，只能写本集角色正式名或无\n"
    "3. 核心场景只能写本集场景正式名；关键道具【】只能写本集道具正式名或无\n"
    "4. 别名只帮助理解剧本，不允许作为最终输出名；已有阶段正式名时禁止输出基础名\n"
    "5. 无人物的空镜请写 出镜人物【无】；无关键道具请写 关键道具【无】\n\n"
    "【输出示例】\n"
    "镜头1：\n"
    "出镜人物【沈凌霜、苏念初】\n"
    "核心场景：豪华客厅\n"
    "关键道具【无】\n"
    "画面描述：【真人短剧风格 + 近景 + 沈凌霜站左侧、苏念初站右侧 "
    "+ 对峙关系 + 沈凌霜怒视苏念初 + 沈凌霜握紧拳头、表情愤怒】\n"
    "音效：紧张的背景音乐\n"
    "沈凌霜：你到底还想隐瞒多久？\n\n"
    "镜头2：\n"
    "出镜人物【苏念初】\n"
    "核心场景：豪华客厅\n"
    "关键道具【无】\n"
    "画面描述：【真人短剧风格 + 特写 + 苏念初面部 + 惊慌失措的表情 + 眼神闪躲】\n"
    "音效：心跳声加速\n"
    "旁白：苏念初的脸上闪过一丝慌张。"
)


class PromptBuilder:
    """提示词构建器"""

    def __init__(
        self,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        user_template: str = DEFAULT_USER_TEMPLATE,
        user_instruction: str = DEFAULT_USER_INSTRUCTION,
        schema: Optional[PromptSchema] = None,
    ):
        self.system_prompt = system_prompt
        self.user_template = user_template
        self.user_instruction = user_instruction
        self.schema = schema or PromptSchema()

    def build(
        self, screenplay_text: str, episode_number: int = 1,
        character_roster: str = "",
    ) -> List[dict]:
        """构建 OpenAI 格式 messages"""
        user_content = self.user_template.replace(
            "{episode_number}", str(episode_number)
        ).replace(
            "{screenplay_text}", screenplay_text
        ).replace(
            "{character_roster}", character_roster
        ).replace(
            "{user_instruction}", self.user_instruction
        )
        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_content},
        ]

    @classmethod
    def from_file(cls, path: str, user_instruction: Optional[str] = None) -> "PromptBuilder":
        """从模板文件加载（支持 ---SYSTEM---、---USER---、---SCHEMA--- 段）"""
        if not os.path.exists(path):
            logger.warning(f"模板文件不存在: {path}，使用默认模板")
            return cls(user_instruction=user_instruction or DEFAULT_USER_INSTRUCTION)

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        system = DEFAULT_SYSTEM_PROMPT
        template = DEFAULT_USER_TEMPLATE
        instruction = user_instruction or DEFAULT_USER_INSTRUCTION
        schema = PromptSchema()

        # 提取 ---SCHEMA--- 段（如果存在）
        schema_text = ""
        if "---SCHEMA---" in content:
            main_part, _, schema_text = content.partition("---SCHEMA---")
            content = main_part  # 剩余部分继续解析 SYSTEM/USER
            schema = PromptSchema._parse_schema_block(schema_text)
            logger.info(
                f"已加载 Schema: delimiter={schema.delimiter!r}, "
                f"required_fields={schema.required_fields}, "
                f"shots={schema.min_shots}-{schema.max_shots}"
            )

        if "---SYSTEM---" in content and "---USER---" in content:
            parts = content.split("---USER---")
            system = parts[0].replace("---SYSTEM---", "").strip()
            template = parts[1].strip()
        else:
            instruction = content.strip()

        return cls(
            system_prompt=system,
            user_template=template,
            user_instruction=instruction,
            schema=schema,
        )


class PromptGenerator:
    """
    Step 3: 镜头脚本生成 Agent

    流程: 读取分集文本 → 构建 prompt → 调用 LLM → 写入镜头脚本
    """

    def __init__(
        self,
        llm_client: LLMClient,
        prompt_builder: Optional[PromptBuilder] = None,
        context_window: int = 32000,
    ):
        self.llm = llm_client
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.context_window = context_window
        self._character_names: List[str] = []
        self._synopsis: str = ""
        self._character_guide: List[dict] = []
        self._scene_guide: List[dict] = []
        self._prop_guide: List[dict] = []

    def process(
        self,
        episodes_dir: str,
        output_dir: str,
        skip_existing: bool = True,
        character_names: Optional[List[str]] = None,
        on_progress: Optional[callable] = None,
        start_episode: int = 1,
        end_episode: int = 999,
        synopsis: str = "",
        character_guide: Optional[List[dict]] = None,
        scene_guide: Optional[List[dict]] = None,
        prop_guide: Optional[List[dict]] = None,
        selected_episodes: Optional[List[str]] = None,
        max_concurrency: int = 5,
    ) -> Dict[str, Any]:
        """
        批量生成镜头脚本（多集并行）。

        参数:
            episodes_dir: 分集文本目录 (episodes/)
            output_dir: 输出目录 (prompts/)
            skip_existing: 跳过已存在
            character_names: 来自 asset 的角色名列表，用于约束镜头脚本中的角色名
            on_progress: (current, total, episode_num)
            start_episode: 起始集数
            end_episode: 结束集数
            synopsis: 剧情简介全文
            character_guide: 角色出场指引列表，每项 {"name", "aliases", "episodes", "desc"}
            max_concurrency: 最大并行集数

        返回:
            {"success": True, "generated": int, "skipped": int, "failed": int, "results": [...]}
        """
        self._character_names = character_names or []
        self._synopsis = synopsis
        self._character_guide = character_guide or []
        self._scene_guide = scene_guide or []
        self._prop_guide = prop_guide or []
        os.makedirs(output_dir, exist_ok=True)
        if not isinstance(max_concurrency, int) or isinstance(max_concurrency, bool) or max_concurrency < 1:
            error = "max_concurrency 必须是正整数"
            return {"success": False, "generated": 0, "skipped": 0,
                    "failed": 0, "error": error, "results": []}

        episode_files = sorted(
            f for f in os.listdir(episodes_dir) if f.lower().endswith(".txt")
        )
        available_files: Dict[str, str] = {}
        for filename in episode_files:
            stem = os.path.splitext(filename)[0]
            if stem.isdigit():
                available_files.setdefault(f"{int(stem):02d}", filename)

        selected_ids: Optional[set[str]] = None
        if selected_episodes is not None:
            selected_ids = set()
            invalid_requested = []
            for value in selected_episodes:
                raw = str(value).strip()
                if not raw.isdigit():
                    invalid_requested.append(raw or repr(value))
                else:
                    selected_ids.add(f"{int(raw):02d}")
            if invalid_requested:
                error = "集数格式无效: " + "、".join(invalid_requested)
                return {"success": False, "generated": 0, "skipped": 0,
                        "failed": 0, "error": error, "results": []}
            unknown = sorted(selected_ids.difference(available_files), key=int)
            if unknown:
                error = "未知集数: " + "、".join(unknown)
                return {"success": False, "generated": 0, "skipped": 0,
                        "failed": 0, "error": error, "results": []}

        filtered_episode_files = []
        for normalized, filename in sorted(available_files.items(), key=lambda item: int(item[0])):
            ep_int = int(normalized)
            if start_episode <= ep_int <= end_episode and (
                selected_ids is None or normalized in selected_ids
            ):
                filtered_episode_files.append((normalized, filename))

        if not filtered_episode_files:
            logger.warning(f"未找到 {start_episode}-{end_episode} 范围的分集文本: {episodes_dir}")
            return {"success": True, "generated": 0, "skipped": 0, "failed": 0, "results": []}

        total = len(filtered_episode_files)
        generated = 0
        skipped = 0
        failed = 0
        results = [None] * total

        # 并行生成
        workers = min(max_concurrency, total) if total > 0 else 1
        logger.info(f"并行生成镜头脚本: {total}集, {workers}线程")

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {}
            for idx, (normalized, ep_file) in enumerate(filtered_episode_files):
                future = pool.submit(
                    self._process_one_episode, ep_file, episodes_dir, output_dir,
                    skip_existing, normalized
                )
                futures[future] = (idx, ep_file)

            for future in as_completed(futures):
                idx, ep_file = futures[future]
                try:
                    result = future.result()
                    results[idx] = result
                    if result.get("skipped"):
                        skipped += 1
                        logger.info(f"跳过: {result['episode']}")
                    elif result.get("success"):
                        generated += 1
                        logger.info(f"第{result['episode']}集镜头脚本: {result['char_count']} 字符")
                    else:
                        failed += 1
                        logger.error(f"第{result['episode']}集生成失败: {result.get('error')}")
                except Exception as e:
                    failed += 1
                    ep_num = os.path.splitext(ep_file)[0]
                    results[idx] = {"episode": ep_num, "success": False, "error": str(e)}
                    logger.error(f"第{ep_num}集异常: {e}")

                if on_progress:
                    done = generated + skipped + failed
                    on_progress(done, total, results[idx].get("episode", ""))

        success = failed == 0
        errors = [
            str(result.get("error", "")) for result in results
            if result and not result.get("success") and result.get("error")
        ]
        logger.info(
            f"镜头脚本生成完成: 成功={generated}, 跳过={skipped}, 失败={failed}"
        )
        return {
            "success": success,
            "generated": generated,
            "skipped": skipped,
            "failed": failed,
            "results": results,
            "error": "；".join(errors),
        }

    MAX_FORMAT_RETRIES = 2
    MAX_AUDIT_RETRIES = 2

    def _process_one_episode(
        self, ep_file: str, episodes_dir: str, output_dir: str, skip_existing: bool,
        normalized_episode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """处理单集：读文本 → 生成 → 写入（给 ThreadPoolExecutor 调用）"""
        ep_num = normalized_episode or os.path.splitext(ep_file)[0]
        output_path = os.path.join(output_dir, f"{ep_num}.txt")

        text_path = os.path.join(episodes_dir, ep_file)
        with open(text_path, "r", encoding="utf-8") as f:
            text = f.read().strip()

        if not text:
            return {"episode": ep_num, "success": True, "skipped": True}

        if skip_existing and os.path.exists(output_path):
            # 旧脚本只在通过完整审计时跳过；失败时保留原文件并返回失败，
            # 让 UI 明确提示用户主动重新生成，而不是把无效文件当成完成。
            try:
                with open(output_path, "r", encoding="utf-8-sig") as handle:
                    existing = handle.read().strip()
                format_ok, format_issues = self._validate_output(existing)
                _fixed, reference_issues = self._audit_and_fix_references(existing, int(ep_num))
                content_ok, content_issues = self._audit_shot_script(existing, text)
                issues = list(format_issues) + list(reference_issues) + list(content_issues)
                if format_ok and content_ok and not reference_issues:
                    return {"episode": ep_num, "success": True, "skipped": True}
                return {
                    "episode": ep_num,
                    "success": False,
                    "skipped": False,
                    "error": "已有镜头脚本审核未通过：" + "；".join(issues),
                    "existing_invalid": True,
                }
            except OSError as exc:
                logger.warning("读取已有第%s集镜头脚本失败，将重新生成: %s", ep_num, exc)

        ep_int = int(ep_num)
        outcome = self._generate_single(text, ep_int)
        if not outcome.valid:
            from agents.shot_parser import analyze_shots
            analysis = analyze_shots(outcome.text, self.schema.delimiter)
            failed_path = os.path.join(output_dir, f"{ep_num}.failed.txt")
            try:
                with open(failed_path, "w", encoding="utf-8") as handle:
                    handle.write(outcome.text or "")
                logger.warning("第%s集失败候选已保存: %s", ep_num, failed_path)
            except OSError as exc:
                logger.warning("第%s集失败候选保存失败: %s", ep_num, exc)
            return {
                "episode": ep_num,
                "success": False,
                "shot_count": len(analysis.shots),
                "attempts": outcome.attempts,
                "error": "；".join(outcome.issues) or "镜头脚本审核未通过",
            }

        fd, temp_path = tempfile.mkstemp(
            prefix=f".{ep_num}.", suffix=".tmp", dir=output_dir
        )
        try:
            handle = os.fdopen(fd, "w", encoding="utf-8")
            fd = -1
            with handle:
                handle.write(outcome.text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, output_path)
        finally:
            if fd >= 0:
                os.close(fd)
            if os.path.exists(temp_path):
                os.unlink(temp_path)

        return {"episode": ep_num, "success": True,
                "char_count": len(outcome.text), "attempts": outcome.attempts}

    @property
    def schema(self) -> PromptSchema:
        """获取当前 prompt builder 的 schema 配置"""
        return self.prompt_builder.schema

    def _validate_output(self, result: str) -> Tuple[bool, List[str]]:
        """
        逐镜头校验 LLM 输出，返回 (是否通过, 问题列表)。

        校验维度:
          1. 全局 header 字段（出镜人物、出镜场景等）
          2. 镜头拆分 + 镜头数范围
          3. 逐镜头必需字段
        """
        from agents.shot_parser import analyze_shots

        schema = self.schema
        issues = []

        # 1. 全局 header 校验（取前500字符）
        header = result[:500]
        for hf in schema.header_fields:
            if hf not in header:
                issues.append(f"输出开头缺少全局字段: {hf}")

        # 2. 镜头拆分
        analysis = analyze_shots(result, schema.delimiter)
        shots = analysis.shots
        if not analysis.recognized:
            issues.append("未识别到明确的镜头边界")

        # 3. 镜头数范围校验
        if schema.min_shots > 0 and len(shots) < schema.min_shots:
            issues.append(f"镜头数不足: {len(shots)} < 最少{schema.min_shots}")
        if schema.max_shots > 0 and len(shots) > schema.max_shots:
            issues.append(f"镜头数过多: {len(shots)} > 最多{schema.max_shots}")

        # 4. 逐镜头必需字段校验（最多报10条，避免反馈爆炸）
        field_issues = []
        for i, shot in enumerate(shots):
            for rf in schema.required_fields:
                if not self._required_field_present(shot, rf):
                    field_issues.append(f"镜头{i+1} 缺少: {rf}")
        issues.extend(field_issues[:10])
        if len(field_issues) > 10:
            issues.append(f"...及另外 {len(field_issues) - 10} 个字段缺失")

        return (len(issues) == 0, issues)

    @staticmethod
    def _required_field_present(shot: str, required_field: str) -> bool:
        """Return whether a required field is present, with legacy visual-schema tolerance."""
        if required_field in shot:
            return True
        if required_field in _LEGACY_VISUAL_DETAIL_FIELDS and "画面描述：【" in shot:
            # 旧模板曾把风格/景别/构图/机位等拆成独立字段；新版把这些内容压回
            # 画面描述，避免 LLM 输出过长且反复因漏字段重试。
            return True
        return False

    def _estimate_shot_range(self, text: str) -> Tuple[int, int]:
        """
        根据剧本文本估算合理镜头数范围（覆盖率守卫）。

        规则:
        - 统计台词行数 (含"：" 或 ":" 的对话行)
        - 统计叙述段落数 (双换行分隔)
        - 每1-2个台词/旁白段落对应1个镜头
        - 下限 = max(ceil(content_units * 0.4), 3)
        - 上限 = min(ceil(content_units * 1.5), schema.max_shots)

        返回:
            (最少镜头数估计, 最多镜头数估计)
        """
        import math
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        # 台词行：包含中文冒号/英文冒号且冒号前为短角色名
        dialogue_lines = len([
            line for line in lines
            if re.match(r'^.{1,10}[：:]', line)
        ])
        # 叙述段落
        paragraphs = len([p for p in text.split('\n\n') if p.strip()])

        content_units = max(dialogue_lines + paragraphs, 3)

        min_shots = max(math.ceil(content_units * 0.4), 3)
        max_shots = min(math.ceil(content_units * 1.5), self.schema.max_shots)

        return (min_shots, max_shots)

    def _audit_shot_script(self, result: str, original_text: str) -> Tuple[bool, List[str]]:
        """审核镜头脚本内容质量（覆盖率、重复度、完整性）"""
        from agents.shot_parser import analyze_shots
        issues = []

        analysis = analyze_shots(result, self.schema.delimiter)
        shots = analysis.shots
        if not analysis.recognized:
            return (False, ["未识别到明确的镜头边界"])
        if not shots:
            return (False, ["无法解析出任何镜头"])

        structural_labels = {
            "出镜人物", "出镜场景", "核心场景", "关键道具", "画面描述", "音效",
            "风格", "景别", "构图", "机位", "角度", "镜头类型", "运镜", "视觉重点",
            "角色状态追踪", "台词/旁白对应", "镜头序号", "时长",
        }
        vo_refs = []
        referenced_shots = 0
        for s in shots:
            shot_refs = [
                match.group(1).strip()
                for match in re.finditer(r"台词/旁白对应\s*[：:]\s*【(.+?)】", s)
                if match.group(1).strip()
            ]
            has_content = bool(shot_refs)
            for line in s.splitlines():
                match = re.match(r"^\s*([^：:\n]{1,30})\s*[：:]\s*(.+?)\s*$", line)
                if not match:
                    continue
                label, content = match.group(1).strip(), match.group(2).strip()
                if label == "旁白":
                    has_content = True  # 旁白计入覆盖率
                    continue           # 但不参与多样性检查
                if content and label not in structural_labels:
                    shot_refs.append(content)
            if has_content:
                referenced_shots += 1
            if shot_refs:
                vo_refs.extend(shot_refs)

        # 2. 台词/旁白覆盖率不再作为阻断条件。
        # 有些分镜只需要画面、动作和音效推进剧情，不能因为半数镜头没有台词/旁白
        # 就判定整集镜头脚本失败。下面仍保留“复读/跳段”类硬问题检查。

        # 3. 检查引用唯一性（所有镜头都用同一段文本 = 跳段）
        unique_refs = set(vo_refs)
        if len(vo_refs) >= 3 and len(unique_refs) <= 1:
            issues.append(f"所有{len(vo_refs)}处台词/旁白引用都相同，可能遗漏了其他文本段落")

        # 4. 检查是否有同文本重复超过 3 次（仅针对短引用；长旁白贯穿多镜是合法手法）
        from collections import Counter
        ref_counts = Counter(vo_refs)
        for ref_text, count in ref_counts.most_common(2):
            if len(ref_text) >= 30:
                continue  # 长旁白贯穿多个镜头是合法手法，不算复读
            if count > len(shots) * 0.6 and len(vo_refs) > 2:
                issues.append(f"同一段文本被重复引用 {count}/{len(shots)} 次，缺乏多样性")
                break

        estimated_min, _estimated_max = self._estimate_shot_range(original_text)
        if len(shots) < estimated_min:
            issues.append(f"镜头数不足: {len(shots)} < 原文覆盖下限{estimated_min}")

        # 5. 检查镜头编号连续性（分段拼接后尤其容易跳号/重复）
        shot_nums = analysis.shot_numbers
        if shot_nums and len(shot_nums) > 1:
            expected = list(range(1, len(shot_nums) + 1))
            if shot_nums != expected:
                dupes = [n for n, c in Counter(shot_nums).items() if c > 1]
                missing = sorted(set(expected) - set(shot_nums))
                extra = sorted(set(shot_nums) - set(expected))
                detail_parts = []
                if dupes:
                    detail_parts.append(f"重复编号: {dupes[:5]}")
                if missing:
                    detail_parts.append(f"缺少编号: {missing[:5]}")
                if extra:
                    detail_parts.append(f"多余编号: {extra[:5]}")
                issues.append(
                    f"镜头编号不连续: 期望1-{len(shot_nums)}递增，实际{shot_nums[:8]}"
                    + ("..." if len(shot_nums) > 8 else "")
                    + ("；" + "；".join(detail_parts) if detail_parts else "")
                )

        return (len(issues) == 0, issues)

    @staticmethod
    def _norm_name(value: str) -> str:
        return re.sub(r"[\s_\-—－·]+", "", str(value or "").lower())

    @staticmethod
    def _base_name(name: str) -> str:
        return re.sub(
            r"[_\-—－]?(前期|中期|后期|青年期|中年期|老年期|幼年期|成年期)$",
            "",
            str(name or ""),
        )

    @staticmethod
    def _strip_stage_words(name: str) -> str:
        """Remove visual-stage words accidentally attached to a formal asset name."""
        value = str(name or "").strip()
        value = re.sub(
            r"^(前期|中期|后期|青年期|中年期|老年期|幼年期|成年期)[_\-\s—－]*",
            "",
            value,
        )
        value = re.sub(
            r"[_\-\s—－]*(前期|中期|后期|青年期|中年期|老年期|幼年期|成年期)$",
            "",
            value,
        )
        return value.strip()

    @staticmethod
    def _split_names(value: str) -> List[str]:
        names = []
        for raw in re.split(r"[、,，;；]+", str(value or "")):
            name = raw.strip()
            if name and name != "无":
                names.append(name)
        return names

    @staticmethod
    def _episode_items(
        items: List[dict], episode_number: int, *, include_unassigned: bool = True
    ) -> List[dict]:
        ep = str(episode_number).zfill(2)
        result = []
        for item in items or []:
            episodes = [str(e).zfill(2) for e in item.get("episodes", []) if str(e).strip()]
            if (include_unassigned and not episodes) or ep in episodes:
                result.append(item)
        return result

    @staticmethod
    def _item_aliases(item: dict) -> List[str]:
        aliases = item.get("strong_aliases")
        if aliases is None:
            aliases = item.get("aliases", [])
        return [str(alias).strip() for alias in aliases if str(alias).strip()]

    @staticmethod
    def _item_desc(item: dict) -> str:
        return str(
            item.get("visual_desc")
            or item.get("desc")
            or item.get("prompt")
            or ""
        ).strip()

    def _reference_indexes(self, episode_number: int) -> dict:
        chars = self._episode_items(self._character_guide, episode_number)
        # 场景是按集数注册的白名单。未标注集数的旧场景不能跨集全局暴露，
        # 否则模型会把上一集/别的集场景当成当前集场景。
        scenes = self._episode_items(
            self._scene_guide, episode_number, include_unassigned=False
        )
        props = self._episode_items(self._prop_guide, episode_number)

        def build(items: List[dict]) -> tuple[dict, dict]:
            allowed = {str(item.get("name", "")).strip(): item for item in items if item.get("name")}
            alias_map: dict[str, set[str]] = {}
            for name, item in allowed.items():
                for alias in self._item_aliases(item):
                    alias_map.setdefault(self._norm_name(alias), set()).add(name)
            return allowed, alias_map

        char_allowed, char_aliases = build(chars)
        scene_allowed, scene_aliases = build(scenes)
        prop_allowed, prop_aliases = build(props)

        base_to_stage: dict[str, set[str]] = {}
        for name in char_allowed:
            base = self._base_name(name)
            if base and base != name:
                base_to_stage.setdefault(self._norm_name(base), set()).add(name)

        return {
            "ep": str(episode_number).zfill(2),
            "characters": char_allowed,
            "character_aliases": char_aliases,
            "character_base_to_stage": base_to_stage,
            "scenes": scene_allowed,
            "scene_aliases": scene_aliases,
            "props": prop_allowed,
            "prop_aliases": prop_aliases,
        }

    def _resolve_reference_token(
        self,
        token: str,
        allowed: dict,
        alias_map: dict,
        *,
        base_to_stage: Optional[dict] = None,
    ) -> tuple[str, str]:
        token = str(token or "").strip()
        if not token or token == "无":
            return token, ""
        if token in allowed:
            return token, ""
        norm = self._norm_name(token)
        alias_candidates = alias_map.get(norm, set())
        if len(alias_candidates) == 1:
            return next(iter(alias_candidates)), "alias"
        stage_stripped = self._strip_stage_words(token)
        if stage_stripped and stage_stripped != token:
            if stage_stripped in allowed:
                return stage_stripped, "stage"
            stripped_norm = self._norm_name(stage_stripped)
            stripped_alias_candidates = alias_map.get(stripped_norm, set())
            if len(stripped_alias_candidates) == 1:
                return next(iter(stripped_alias_candidates)), "stage_alias"
        # 阶段资产存在时，基础名不是正式资产名，不能静默猜测阶段。
        return token, "unresolved"

    def _audit_and_fix_references(self, result: str, episode_number: int) -> Tuple[str, List[str]]:
        """Audit formal asset references before direct video generation."""
        from agents.shot_parser import analyze_shots

        indexes = self._reference_indexes(episode_number)
        ep = indexes["ep"]
        issues: List[str] = []
        analysis = analyze_shots(result, self.schema.delimiter)
        if not analysis.recognized:
            return result, ["无法解析出任何镜头"]

        shot_numbers = analysis.shot_numbers
        expected = list(range(1, len(shot_numbers) + 1))
        if shot_numbers != expected:
            issues.append(f"镜头编号不连续: 当前为 {shot_numbers}，应为 {expected}")

        def audit_shot(local: str, shot_no: int) -> str:

            char_match = re.search(r"出镜人物【([^】]*)】", local)
            if not char_match:
                issues.append(f"镜头{shot_no} 缺少: 出镜人物")
            else:
                raw = char_match.group(1).strip()
                if raw and raw != "无" and indexes["characters"]:
                    resolved_names = []
                    for token in self._split_names(raw):
                        resolved, reason = self._resolve_reference_token(
                            token,
                            indexes["characters"],
                            indexes["character_aliases"],
                            base_to_stage=indexes["character_base_to_stage"],
                        )
                        if reason == "unresolved":
                            issues.append(
                                f"镜头{shot_no} 出镜人物【{token}】不在第{ep}集角色白名单内，"
                                f"应从【{'、'.join(indexes['characters'])}】中选择。"
                            )
                        resolved_names.append(resolved)
                    if resolved_names:
                        local = local[:char_match.start(1)] + "、".join(resolved_names) + local[char_match.end(1):]

            scene_match = re.search(r"核心场景[：:]\s*([^；;\n\r]+)", local)
            if not scene_match:
                issues.append(f"镜头{shot_no} 缺少: 核心场景")
            elif indexes["scenes"]:
                scene = scene_match.group(1).strip()
                if re.search(
                    r"原文对应|可用场景|候选|应该使用|我需要|思考|分析|不确定|等一下|列表",
                    scene,
                ):
                    issues.append(
                        f"镜头{shot_no} 核心场景包含分析文本，必须只保留一个正式场景名"
                    )
                    resolved, reason = scene, "unresolved"
                else:
                    resolved, reason = self._resolve_reference_token(
                        scene, indexes["scenes"], indexes["scene_aliases"]
                    )
                if reason == "unresolved":
                    issues.append(
                        f"镜头{shot_no} 核心场景【{scene}】不在第{ep}集场景白名单内，"
                        f"应从【{'、'.join(indexes['scenes'])}】中选择。"
                    )
                elif resolved != scene:
                    local = local[:scene_match.start(1)] + resolved + local[scene_match.end(1):]
            elif scene_match:
                scene = scene_match.group(1).strip()
                if re.search(
                    r"原文对应|可用场景|候选|应该使用|我需要|思考|分析|不确定|等一下|列表",
                    scene,
                ):
                    issues.append(
                        f"镜头{shot_no} 核心场景包含分析文本，必须只保留一个正式场景名"
                    )

            prop_match = re.search(r"关键道具【([^】]*)】", local)
            if not prop_match:
                issues.append(f"镜头{shot_no} 缺少: 关键道具")
            else:
                raw = prop_match.group(1).strip()
                if raw and raw != "无" and indexes["props"]:
                    resolved_props = []
                    for token in self._split_names(raw):
                        resolved, reason = self._resolve_reference_token(
                            token, indexes["props"], indexes["prop_aliases"]
                        )
                        if reason == "unresolved":
                            issues.append(
                                f"镜头{shot_no} 关键道具【{token}】不在第{ep}集道具白名单内，"
                                f"应从【{'、'.join(indexes['props'])}】中选择。"
                            )
                        resolved_props.append(resolved)
                    if resolved_props:
                        local = local[:prop_match.start(1)] + "、".join(resolved_props) + local[prop_match.end(1):]

            if "画面描述：【" not in local:
                issues.append(f"镜头{shot_no} 缺少: 画面描述")
            if re.search(r"(ComfyUI_[^\s，。；;】]+|openapi/[^\s，。；;】]+)", local):
                issues.append(f"镜头{shot_no} 出现临时文件名，禁止进入最终镜头脚本。")
            return local

        fixed = result
        replacements = []
        for shot_no, body, (start, end) in zip(
            shot_numbers, analysis.shots, analysis.spans
        ):
            chunk = result[start:end]
            body_start = chunk.find(body)
            if body_start < 0:
                issues.append(f"镜头{shot_no} 正文定位失败")
                continue
            local = audit_shot(body, shot_no)
            replacements.append((start, end, chunk[:body_start] + local + chunk[body_start + len(body):]))
        for start, end, replacement in reversed(replacements):
            fixed = fixed[:start] + replacement + fixed[end:]
        return fixed, issues

    def _generate_single(self, text: str, episode_number: int) -> ShotGenerationOutcome:
        """
        生成单集镜头脚本（含格式校验 + 内容审核 + 自适应约束重试）。

        两步验证：先生成→格式校验→内容审核→都通过才放过。
        不通过时把具体问题注入约束列表，下次生成带着约束一起重试。
        """
        result = ""
        constraints = []  # 累积的自适应约束
        last_issues: List[str] = []
        max_retries = self.MAX_FORMAT_RETRIES + self.MAX_AUDIT_RETRIES

        for attempt in range(max_retries + 1):
            # 将累积约束拼成 feedback
            feedback = "\n\n".join(constraints) if constraints else ""

            result = self._do_generate(text, episode_number, feedback=feedback)

            # 先修正唯一别名，再对最终候选执行格式与内容审核。
            result, reference_issues = self._audit_and_fix_references(result, episode_number)
            format_passed, format_issues = self._validate_output(result)
            audit_passed, audit_issues = self._audit_shot_script(result, text)
            reference_passed = len(reference_issues) == 0

            if format_passed and audit_passed and reference_passed:
                if attempt > 0:
                    logger.info(f"第{episode_number}集第{attempt+1}次生成审核通过")
                return ShotGenerationOutcome(result, True, (), attempt + 1)

            # 收集本次所有问题 → 注入约束
            all_issues = []
            if not format_passed:
                all_issues.append("【格式问题】")
                all_issues.extend(f"- {issue}" for issue in format_issues)
            if not audit_passed:
                all_issues.append("【内容问题】")
                all_issues.extend(f"- {issue}" for issue in audit_issues)
            if not reference_passed:
                shot_count_issue = any(
                    "镜头数不足" in issue or "只有" in issue
                    for issue in format_issues + audit_issues
                )
                reference_name_only = all(
                    any(marker in issue for marker in (
                        "白名单", "正式名", "别名", "无法唯一"
                    ))
                    for issue in reference_issues
                )
                all_issues.append("【资产引用问题】")
                all_issues.extend(f"- {issue}" for issue in reference_issues)
                if (
                    not shot_count_issue
                    and not format_issues
                    and not audit_issues
                    and reference_name_only
                ):
                    all_issues.append("请保持镜头数量和剧情不变，只修正引用名称。")

            last_issues = list(format_issues) + list(audit_issues) + list(reference_issues)

            if attempt < max_retries:
                constraint = (
                    f"【第{attempt+1}次修正要求】以下问题必须修正：\n"
                    + "\n".join(all_issues)
                )
                if any("镜头数不足" in issue for issue in last_issues):
                    constraint += (
                        "\n【强制镜头数要求】必须完整重写为13-18个连续镜头，"
                        "每个镜头都以“镜头N：”开头。低于13个镜头无效；"
                        "短剧情也要拆分为人物反应、动作衔接、环境/道具特写、"
                        "手机语音/信息、进出场和视线关系等镜头。"
                    )
                constraints.append(constraint)
                logger.warning(
                    f"第{episode_number}集审核不通过 "
                    f"({len(format_issues)+len(audit_issues)+len(reference_issues)}个问题)，第{attempt+2}次重试..."
                )
            else:
                logger.warning(
                    f"第{episode_number}集重试{max_retries}次后仍有问题，不发布最后结果"
                )

        return ShotGenerationOutcome(
            text=result,
            valid=False,
            issues=tuple(last_issues),
            attempts=max_retries + 1,
        )

    @staticmethod
    def _script_scene_candidates(screenplay_text: str) -> List[str]:
        """Extract explicit location phrases as virtual scene names when the asset
        catalog has no scene record for this episode.  They are text-only candidates,
        never image references.
        """
        text = str(screenplay_text or "")
        candidates: List[str] = []
        for match in re.findall(r"(?:场景|地点|内景|外景)[：:]\s*([^\n\r，。；;]+)", text):
            value = match.strip(" []（）()")
            if value and value not in candidates:
                candidates.append(value)
        keyword_map = (
            ("急诊", "医院急诊"), ("住院", "医院病房"), ("医院", "医院"),
            ("宴会", "宴会厅"), ("寿宴", "寿宴现场"), ("餐厅", "餐厅"),
            ("包厢", "餐厅包厢"), ("工地", "建筑工地"),
        )
        for keyword, value in keyword_map:
            if keyword in text and value not in candidates:
                candidates.append(value)
        return candidates[:8]

    def _build_roster_text(self, episode_number: int = 0, screenplay_text: str = "") -> str:
        parts = []

        # 剧情简介
        if self._synopsis:
            parts.append("【剧情背景】\n" + self._synopsis.strip())

        ep_str = str(episode_number).zfill(2)
        ep_chars = self._episode_items(self._character_guide, episode_number)
        ep_scenes = self._episode_items(
            self._scene_guide, episode_number, include_unassigned=False
        )
        ep_props = self._episode_items(self._prop_guide, episode_number)

        if self._character_guide:
            if ep_chars:
                lines = []
                for c in ep_chars:
                    aliases = self._item_aliases(c)
                    alias_part = "、".join(aliases) if aliases else "无"
                    lines.append(
                        f"  正式名：{c['name']} | 别名：{alias_part} | 描述：{self._item_desc(c)}"
                    )
                parts.append(
                    f"【第{ep_str}集可用角色】\n"
                    + "\n".join(lines)
                )
            elif self._character_names:
                parts.append(
                    "【角色名称约束】出镜人物【】只能使用：" + "、".join(self._character_names)
                )
        elif self._character_names:
            parts.append(
                "【角色名称约束】出镜人物【】只能使用：" + "、".join(self._character_names)
            )

        if ep_scenes:
            lines = []
            for scene in ep_scenes:
                aliases = self._item_aliases(scene)
                alias_part = "、".join(aliases) if aliases else "无"
                lines.append(
                    f"  正式名：{scene['name']} | 别名：{alias_part} | 描述：{self._item_desc(scene)}"
                )
            parts.append(f"【第{ep_str}集可用场景】\n" + "\n".join(lines))
        else:
            candidates = self._script_scene_candidates(screenplay_text)
            if candidates:
                parts.append(
                    f"【第{ep_str}集剧本地点候选（文字场景，无参考图）】\n"
                    + "、".join(candidates)
                    + "\n只能从这些候选或剧本明确地点中选择，不得引用其他集场景。"
                )
            else:
                parts.append(
                    f"【第{ep_str}集场景白名单】资产库没有注册该集场景；"
                    "只能依据本集剧本文字填写场景正式名，禁止引用其他集场景或输出分析过程。"
                )

        if ep_props:
            lines = []
            for prop in ep_props:
                aliases = self._item_aliases(prop)
                alias_part = "、".join(aliases) if aliases else "无"
                allows_text = "是" if prop.get("allows_text") else "否"
                lines.append(
                    f"  正式名：{prop['name']} | 别名：{alias_part} | 允许文字：{allows_text} | 描述：{self._item_desc(prop)}"
                )
            parts.append(f"【第{ep_str}集可用道具】\n" + "\n".join(lines))

        if ep_chars or ep_scenes or ep_props:
            parts.append(
                "【资产引用硬规则】出镜人物【】只能写本集可用角色正式名或无；"
                "核心场景只能写本集可用场景正式名；关键道具【】只能写本集可用道具正式名或无。"
                "别名只帮助理解剧本，不允许作为最终输出名；已有阶段正式名时禁止输出基础名。"
                "泛称/弱称呼如我、他、她、爸、妈、老公、老板、男人、女人、孩子不得作为最终角色名。"
            )

        if not parts:
            return ""
        return "\n\n".join(parts) + "\n\n"

    def _do_generate(self, text: str, episode_number: int, feedback: str = "") -> str:
        """实际执行单次 LLM 镜头脚本生成，支持注入反馈信息"""
        safe_limit = int(self.context_window * 0.6)
        text_tokens = estimate_tokens(text)
        roster = self._build_roster_text(episode_number, text)

        # 将 feedback 追加在剧本文本之后
        gen_text = text
        if feedback:
            gen_text = text + "\n\n" + feedback

        # 动态输出 token 预算：按预估镜头数 × 250 token/镜，保底 4096
        _min, estimated_max = self._estimate_shot_range(text)
        dynamic_max_tokens = max(4096, estimated_max * 250, self.schema.max_shots * 250)

        if text_tokens <= safe_limit:
            messages = self.prompt_builder.build(gen_text, episode_number, character_roster=roster)
            return self.llm.generate(messages, max_tokens=dynamic_max_tokens)
        else:
            logger.warning(
                f"第{episode_number}集文本过长 ({text_tokens} tokens > {safe_limit})，"
                f"启用分段处理"
            )
            return self._chunked_generate(
                gen_text, episode_number, safe_limit,
                roster=roster, max_tokens=dynamic_max_tokens,
            )

    def _chunked_generate(
        self, text: str, episode_number: int, token_limit: int,
        roster: str = "",
        max_tokens: Optional[int] = None,
    ) -> str:
        """智能分段处理过长文本"""
        paragraphs = text.split("\n\n")
        chunks = []
        current_chunk = []
        current_tokens = 0

        for para in paragraphs:
            para_tokens = estimate_tokens(para)
            if current_tokens + para_tokens > token_limit and current_chunk:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = [para]
                current_tokens = para_tokens
            else:
                current_chunk.append(para)
                current_tokens += para_tokens

        if current_chunk:
            chunks.append("\n\n".join(current_chunk))

        logger.info(f"第{episode_number}集分为 {len(chunks)} 段处理")

        results = []
        for j, chunk in enumerate(chunks):
            context_note = (
                f"（注意：这是第{episode_number}集的第{j + 1}部分，"
                f"共{len(chunks)}部分。请仅为本段内容生成镜头脚本"
            )
            if j > 0:
                context_note += "，镜头编号请从前一部分的末尾继续递增"
            context_note += "。）\n\n"

            messages = self.prompt_builder.build(
                context_note + chunk, episode_number, character_roster=roster
            )
            result = self.llm.generate(messages, max_tokens=max_tokens)
            results.append(result)

        return "\n\n".join(results)
