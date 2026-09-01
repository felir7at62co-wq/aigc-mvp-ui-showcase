"""
AIGC Pipeline — 资产描述自动提取器

使用 LLM 从剧本中自动提取角色、场景描述，
生成 asset_descriptions.txt 供 AssetGenerator 使用。

当镜头脚本已生成时，会从中提取角色名册注入 LLM 提示词，
确保资产名称与镜头脚本保持一致（解决角色名不匹配问题）。

提示词模板: prompts/default_asset_prompt.txt（可编辑）
输出格式: 每行 名称|别名|出场集数|中文描述prompt
"""
import os
import re
import logging
from typing import Dict, Any, Optional, List, Set

from core.llm_client import LLMClient, estimate_tokens

logger = logging.getLogger(__name__)


# ========== 默认提示词（代码内置兜底） ==========

DEFAULT_SYSTEM_PROMPT = (
    "你是一位专业的影视美术指导和AI图像生成专家。"
    "你擅长从剧本中提取角色和场景，"
    "并为每个资产生成适合AI图像生成（Stable Diffusion / ComfyUI）的中文描述prompt。"
    "你的输出必须严格遵守指定格式，每行一个资产，使用 | 分隔名称和描述。"
)

DEFAULT_USER_TEMPLATE = """以下是一部短剧的完整剧本：

---剧本开始---
{screenplay_text}
---剧本结束---

请从剧本中提取{user_instruction}"""

DEFAULT_USER_INSTRUCTION = (
    "提取所有有名字的角色和关键场景，并为每个资产生成中文描述。\n"
    "注意：不要提取道具、服饰、车辆等非角色非场景的物品。\n\n"
    "要求：\n"
    "1. 角色描述包含：种族、性别、年龄、发型、五官特征、服装风格、表情/气质\n"
    "2. 场景描述包含：地点类型、光线、氛围、建筑/装饰风格、时间（日/夜）\n"
    "3. 所有描述必须用中文\n"
    "4. 不限制角色和场景数量；关键角色和关键场景都必须保留。\n"
    "5. 第二列必须填写该角色或场景在剧本中能唯一指向它的称呼、代称、身份词，用逗号分隔；泛称不要注册为强别名。\n"
    "6. 第三列必须填写该角色或场景实际出现的所有集数，用逗号分隔，两位数字；场景不能因为没有参考图而留空。\n\n"
    "输出格式（每行一个，用 | 分隔四列）：\n"
    "角色中文名|别名1,别名2|01,02,03|角色中文描述，详细外貌，写实风格\n"
    "场景中文名|场景别名|01,02,03|场景中文描述，地点，光线，写实风格\n\n"
    "完成角色和场景描述后，继续输出以下段落：\n\n"
    "===剧情简介===\n"
    "（不少于200字，详细描述全剧核心剧情、主要冲突和人物关系）"
)


class AssetPromptBuilder:
    """资产提取提示词构建器（与 PromptBuilder 同款模式）"""

    def __init__(
        self,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        user_template: str = DEFAULT_USER_TEMPLATE,
        user_instruction: str = DEFAULT_USER_INSTRUCTION,
    ):
        self.system_prompt = system_prompt
        self.user_template = user_template
        self.user_instruction = user_instruction

    def build(
        self,
        screenplay_text: str,
        character_roster: str = "",
        extra_context: str = "",
    ) -> List[dict]:
        """
        构建 OpenAI 格式 messages。

        参数:
            screenplay_text: 剧本文本
            character_roster: 从镜头脚本提取的角色名册（可选）
                如果模板中有 {character_roster} 占位符则替换；
                如果没有占位符但有角色名册，则在剧本文本后注入。
            extra_context: 分类提取的额外上下文（例如已有带图场景资产）
        """
        user_content = self.user_template.replace(
            "{screenplay_text}", screenplay_text
        )

        # 注入角色名册
        if "{character_roster}" in user_content:
            user_content = user_content.replace(
                "{character_roster}", character_roster
            )
        elif character_roster:
            # 模板中无占位符，在剧本文本后追加
            user_content = user_content + "\n" + character_roster

        if extra_context:
            if "{extra_context}" in user_content:
                user_content = user_content.replace("{extra_context}", extra_context)
            else:
                user_content = user_content + "\n" + extra_context

        # 兼容旧模板：替换 user_instruction 占位符（外模板不再使用此占位符）
        if "{user_instruction}" in user_content:
            effective_instruction = character_roster + extra_context + self.user_instruction
            user_content = user_content.replace(
                "{user_instruction}", effective_instruction
            )

        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_content},
        ]

    @classmethod
    def from_file(
        cls, path: str, user_instruction: Optional[str] = None
    ) -> "AssetPromptBuilder":
        """从模板文件加载。

        外部模板包含完整的 SYSTEM 和 USER 提示词，
        直接使用模板内容，不注入额外指令。
        """
        if not os.path.exists(path):
            logger.warning(f"模板文件不存在: {path}，使用默认模板")
            return cls(
                user_instruction=user_instruction or DEFAULT_USER_INSTRUCTION
            )

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        system = DEFAULT_SYSTEM_PROMPT
        template = DEFAULT_USER_TEMPLATE

        if "---SYSTEM---" in content and "---USER---" in content:
            parts = content.split("---USER---")
            system = parts[0].replace("---SYSTEM---", "").strip()
            template = parts[1].strip()
        else:
            # 无分隔符：整个文件作为 user_template
            template = content.strip()

        return cls(
            system_prompt=system,
            user_template=template,
            user_instruction=user_instruction or "",
        )


class AssetDescriptionExtractor:
    """
    从剧本中 LLM 提取角色/场景/道具描述

    流程: 读取分集文本 → 拼接 → 构建 prompt → 调 LLM → 解析 → 写入描述文件
    """

    def __init__(
        self,
        llm_client: LLMClient,
        prompt_builder: AssetPromptBuilder,
        max_input_chars: int = 20000,
    ):
        self.llm_client = llm_client
        self.prompt_builder = prompt_builder
        self.max_input_chars = max_input_chars

    def extract(
        self,
        episodes_dir: str,
        output_path: str,
        prompts_dir: Optional[str] = None,
        char_image_dir: Optional[str] = None,
        scene_image_dir: Optional[str] = None,
        prop_image_dir: Optional[str] = None,
        category: str = "all",
        use_image_vision: bool = True,
    ) -> Dict[str, Any]:
        """
        从分集文本中提取资产描述。

        参数:
            episodes_dir: 分集文本目录 (episodes/)
            output_path: 输出描述文件路径 (asset_descriptions.txt)
            prompts_dir: 镜头脚本目录 (prompts/)，如果提供则从中提取角色名册注入LLM
            char_image_dir: 角色图片目录 (assets/character/)，如果提供则优先用 vision LLM 分析图片生成描述
            scene_image_dir: 场景图片目录 (assets/scene/)，如果提供则优先用 vision LLM 分析场景图片生成描述
            prop_image_dir: 道具图片目录 (assets/prop/)，如果提供则优先用 vision LLM 分析图片生成描述
            category: 提取类别 — "all" (角色+场景), "character", "scene", "prop"
            use_image_vision: 是否逐张调用视觉 LLM 重新分析已有图片。

        返回:
            {"success": True, "asset_count": int, "path": str}
        """
        # 读取所有分集文本
        script_text = self._read_episodes(episodes_dir)
        if not script_text:
            return {"success": False, "error": "未找到分集文本"}

        logger.info(
            f"资产提取({category}): 剧本 {len(script_text)} 字, "
            f"截取前 {self.max_input_chars} 字"
        )

        # 截取（角色通常在前几集出场）
        if len(script_text) > self.max_input_chars:
            script_text = script_text[: self.max_input_chars]

        # ========== 第一步：有图片的角色 → vision LLM 生成描述 ==========
        vision_descriptions: Dict[str, tuple] = {}
        failed_vision_names = set()
        if use_image_vision and category in ("all", "character") and char_image_dir and os.path.isdir(char_image_dir):
            img_files = [
                f for f in os.listdir(char_image_dir)
                if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
            ]
            if img_files:
                logger.info(f"发现 {len(img_files)} 张角色图片，优先用视觉分析生成描述")
                for img_file in sorted(img_files):
                    char_name = os.path.splitext(img_file)[0]
                    img_path = os.path.join(char_image_dir, img_file)
                    try:
                        item = self.describe_from_image(img_path, char_name)
                        if self._is_valid_visual_description(item[3]):
                            vision_descriptions[char_name] = item
                        else:
                            failed_vision_names.add(char_name)
                            logger.warning(f"视觉分析返回无效描述 {char_name}")
                    except Exception as e:
                        failed_vision_names.add(char_name)
                        logger.warning(f"视觉分析失败 {char_name}: {e}")

        # ========== 第一步b：有图片的场景 → vision LLM 生成描述 ==========
        scene_vision_descriptions: Dict[str, tuple] = {}
        if use_image_vision and category in ("all", "scene") and scene_image_dir and os.path.isdir(scene_image_dir):
            img_files = [
                f for f in os.listdir(scene_image_dir)
                if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
            ]
            if img_files:
                logger.info(f"发现 {len(img_files)} 张场景图片，优先用视觉分析生成描述")
                for img_file in sorted(img_files):
                    scene_name = os.path.splitext(img_file)[0]
                    img_path = os.path.join(scene_image_dir, img_file)
                    try:
                        item = self.describe_scene_from_image(img_path, scene_name)
                        if self._is_valid_visual_description(item[3]):
                            scene_vision_descriptions[scene_name] = item
                        else:
                            failed_vision_names.add(scene_name)
                            logger.warning(f"场景视觉分析返回无效描述 {scene_name}")
                    except Exception as e:
                        failed_vision_names.add(scene_name)
                        logger.warning(f"场景视觉分析失败 {scene_name}: {e}")

        # ========== 第一步c：有图片的道具 → vision LLM 生成描述 ==========
        prop_vision_descriptions: Dict[str, tuple] = {}
        if use_image_vision and category in ("all", "prop") and prop_image_dir and os.path.isdir(prop_image_dir):
            img_files = [
                f for f in os.listdir(prop_image_dir)
                if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
            ]
            if img_files:
                logger.info(f"发现 {len(img_files)} 张道具图片，优先用视觉分析生成描述")
                for img_file in sorted(img_files):
                    prop_name = os.path.splitext(img_file)[0]
                    img_path = os.path.join(prop_image_dir, img_file)
                    try:
                        item = self.describe_prop_from_image(img_path, prop_name)
                        if self._is_valid_visual_description(item[3]):
                            prop_vision_descriptions[prop_name] = item
                        else:
                            failed_vision_names.add(prop_name)
                            logger.warning(f"道具视觉分析返回无效描述 {prop_name}")
                    except Exception as e:
                        failed_vision_names.add(prop_name)
                        logger.warning(f"道具视觉分析失败 {prop_name}: {e}")

        # ========== 第二步：LLM 从剧本提取 ==========
        # 从镜头脚本提取角色名册（仅角色提取时）
        character_roster = ""
        if category in ("all", "character") and prompts_dir and os.path.isdir(prompts_dir):
            char_names = self._extract_character_names_from_prompts(prompts_dir)
            if char_names:
                character_roster = (
                    "【重要】以下是镜头脚本中出现的角色名，"
                    "你提取的角色名必须与以下名称完全一致，不要使用简称、别名或其他变体：\n"
                    + "、".join(char_names)
                    + "\n\n"
                )
                logger.info(
                    f"角色名册注入: {len(char_names)} 个角色 — {', '.join(char_names[:10])}"
                    + ("..." if len(char_names) > 10 else "")
                )

        extra_context = ""
        if category in ("all", "character"):
            extra_context = self._build_character_reextract_context(
                char_image_dir=char_image_dir,
                output_path=output_path,
            )
            if extra_context:
                logger.info("角色重提取上下文已注入: %d 字", len(extra_context))
        if category in ("all", "scene"):
            scene_context = self._build_scene_reextract_context(
                scene_image_dir=scene_image_dir,
                output_path=output_path,
                prompts_dir=prompts_dir,
            )
            if scene_context:
                extra_context += scene_context
                logger.info("场景重提取上下文已注入: %d 字", len(scene_context))

        messages = self.prompt_builder.build(
            script_text,
            character_roster,
            extra_context=extra_context,
        )

        logger.info(f"正在调用 LLM 提取{category}资产描述...")
        response = self.llm_client.generate(
            messages=messages,
            max_tokens=4096,
            temperature=0.3,
        )

        # 分割 LLM 输出的两个部分（仅 all/character 包含剧情简介）
        if category == "prop":
            assets_text = response.strip()
            synopsis_text = ""
        else:
            assets_text, synopsis_text = self._split_response_sections(response)

        llm_descriptions = self._parse_response(assets_text)
        # 旧模板和部分模型会把场景第三列留空。用分集原文做一次确定性补全，
        # 这样场景白名单可以按集数过滤，且不会因为缺少参考图而跨集误用。
        episode_texts = self._read_episode_texts(episodes_dir)
        if episode_texts:
            llm_descriptions = self._fill_missing_episode_numbers(
                llm_descriptions, episode_texts
            )
        assets_dir = os.path.dirname(output_path)

        category_prompt_filename = {
            "character": "character_prompts.txt",
            "scene": "scene_prompts.txt",
            "prop": "prop_prompts.txt",
        }.get(category, "asset_descriptions.txt")
        existing_records = self._read_prompt_records_for_context(
            output_path, category_prompt_filename
        )
        has_failed_visual_fallback = any(
            existing_records.get(name, {}).get("prompt")
            for name in failed_vision_names
        )

        has_any = bool(
            llm_descriptions
            or vision_descriptions
            or scene_vision_descriptions
            or prop_vision_descriptions
            or has_failed_visual_fallback
        )
        if not has_any:
            logger.warning(f"LLM 未返回有效的{category}资产描述")
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(f"# LLM 原始输出（请手动修正格式为 名称|描述）:\n")
                f.write(response)
            return {
                "success": False,
                "error": "LLM 输出格式不符合预期，已写入原始输出供检查",
                "path": output_path,
            }

        # ========== 第三步：合并 — vision 优先，失败保留旧外观 ==========
        merged: Dict[str, tuple] = {}

        def visual_record_with_existing_metadata(name: str, item: tuple) -> tuple:
            """视觉只负责外观；旧记录负责图片资产的别名和集数。"""
            _v_name, v_aliases, v_episodes, v_prompt = item
            old = existing_records.get(name, {})
            return (
                name,
                old.get("aliases", "") or v_aliases,
                old.get("episodes", "") or v_episodes,
                v_prompt,
            )

        def visual_record_with_script_metadata(
            name: str, aliases: str, episodes: str, item: tuple
        ) -> tuple:
            """本次剧本字段优先；逐字段缺失时保留旧元数据。"""
            _v_name, v_aliases, v_episodes, v_prompt = item
            old = existing_records.get(name, {})
            return (
                name,
                aliases or old.get("aliases", "") or v_aliases,
                episodes or old.get("episodes", "") or v_episodes,
                v_prompt,
            )

        for name, aliases, episodes, prompt in llm_descriptions:
            if name in vision_descriptions:
                merged[name] = visual_record_with_script_metadata(
                    name, aliases, episodes, vision_descriptions[name]
                )
                logger.info(f"角色 {name}: 使用视觉描述（别名/集数来自剧本）")
            elif name in scene_vision_descriptions:
                merged[name] = visual_record_with_script_metadata(
                    name, aliases, episodes, scene_vision_descriptions[name]
                )
                logger.info(f"场景 {name}: 使用视觉描述")
            elif name in prop_vision_descriptions:
                merged[name] = visual_record_with_script_metadata(
                    name, aliases, episodes, prop_vision_descriptions[name]
                )
                logger.info(f"道具 {name}: 使用视觉描述")
            elif name in failed_vision_names and existing_records.get(name, {}).get("prompt"):
                old = existing_records[name]
                merged[name] = (name, aliases or old.get("aliases", ""), episodes or old.get("episodes", ""), old["prompt"])
                logger.warning(f"资产 {name}: 视觉分析失败，保留原提示词")
            else:
                merged[name] = (name, aliases, episodes, prompt)

        for name in vision_descriptions:
            if name not in merged:
                merged[name] = visual_record_with_existing_metadata(
                    name, vision_descriptions[name]
                )
                logger.info(f"角色 {name}: 仅视觉描述（剧本中未提取到）")

        for name in scene_vision_descriptions:
            if name not in merged:
                merged[name] = visual_record_with_existing_metadata(
                    name, scene_vision_descriptions[name]
                )
                logger.info(f"场景 {name}: 仅视觉描述（剧本中未提取到）")

        for name in prop_vision_descriptions:
            if name not in merged:
                merged[name] = visual_record_with_existing_metadata(
                    name, prop_vision_descriptions[name]
                )
                logger.info(f"道具 {name}: 仅视觉描述（剧本中未提取到）")

        for name in failed_vision_names:
            if name not in merged and existing_records.get(name, {}).get("prompt"):
                old = existing_records[name]
                merged[name] = (
                    name,
                    old.get("aliases", ""),
                    old.get("episodes", ""),
                    old["prompt"],
                )
                logger.warning(f"资产 {name}: 视觉分析失败且剧本未提取，保留原记录")

        descriptions = list(merged.values())

        # 写入描述文件
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(
                "# 自动提取的资产描述（可手动编辑后重新运行）\n"
                "# 格式: 名称|别名|出场集数（逗号分隔）|英文描述prompt\n\n"
            )
            for item in descriptions:
                name, aliases, episodes, prompt = item
                f.write(f"{name}|{aliases}|{episodes}|{prompt}\n")

        if synopsis_text and category != "prop":
            synopsis_path = os.path.join(assets_dir, "synopsis.txt")
            with open(synopsis_path, "w", encoding="utf-8") as f:
                f.write(synopsis_text.strip())
            logger.info(f"剧情简介已写入: {synopsis_path}")

        vision_count = len(vision_descriptions)
        scene_vision_count = len(scene_vision_descriptions)
        prop_vision_count = len(prop_vision_descriptions)
        llm_count = len(llm_descriptions)
        logger.info(
            f"{category}资产描述已提取: {len(descriptions)} 个 "
            f"(角色视觉: {vision_count}, 场景视觉: {scene_vision_count}, "
            f"道具视觉: {prop_vision_count}, 视觉回退: {len(failed_vision_names)}, "
            f"剧本: {llm_count}) → {output_path}"
        )

        return {
            "success": True,
            "asset_count": len(descriptions),
            "path": output_path,
        }

    def describe_from_image(
        self,
        image_path: str,
        character_name: str,
        aliases: str = "",
        episodes: str = "",
    ) -> tuple:
        """
        用 vision LLM 分析角色图片，生成匹配图片的描述词。

        返回 (name, aliases, episodes, new_description)。
        """
        system_prompt = (
            "你是一位专业的影视造型师和AI图像生成专家。"
            "请仔细观察图片中人物的所有外貌特征，"
            "生成用于 Stable Diffusion / ComfyUI 的中文视觉描述提示词。"
        )
        user_prompt = (
            f"请分析图中「{character_name}」这个角色的所有外貌特征，"
            "生成一段详细的中文描述，用于 AI 图像生成。\n\n"
            "描述必须包含以下方面：\n"
            "1. 种族和性别\n"
            "2. 大致年龄\n"
            "3. 发型和发色\n"
            "4. 五官特征（眼睛、鼻子、嘴唇等）\n"
            "5. 服装风格和颜色\n"
            "6. 气质和表情\n\n"
            "要求：\n"
            "- 如果图片是半身像加正面/侧面/背面等多视角设定图，全部视为同一个人物\n"
            "- 只描述图片中实际可见的一套年龄、发型和服装，不补写前期/后期或其他造型\n"
            "- 不描述白底、分栏、视图布局、文字、边框或水印\n"
            "- 必须全程使用简体中文，只输出中文描述文本，不要编号、不要解释\n"
            "- 描述末尾加“真人影视写实风格”\n"
            "- 不要包含角色中文名"
        )

        logger.info(f"视觉分析: {character_name} ← {image_path}")
        description = self.llm_client.generate_with_images(
            prompt=user_prompt,
            image_paths=[image_path],
            system_prompt=system_prompt,
            max_tokens=1024,
            temperature=0.3,
        )

        description = description.strip()
        logger.info(f"视觉分析完成: {character_name} → {description[:80]}...")
        return (character_name, aliases, episodes, description)

    def describe_scene_from_image(
        self,
        image_path: str,
        scene_name: str,
        aliases: str = "",
        episodes: str = "",
    ) -> tuple:
        """
        用 vision LLM 分析场景图片，生成匹配图片的描述词（顶视图视角）。

        返回 (name, aliases, episodes, new_description)。
        """
        system_prompt = (
            "你是一位专业的影视美术指导和AI图像生成专家。"
            "请仔细观察图片中的场景环境，"
            "生成用于 Stable Diffusion / ComfyUI 的中文视觉描述提示词。"
        )
        user_prompt = (
            f"请分析图中「{scene_name}」这个场景的所有环境特征，"
            "生成一段详细的中文描述，用于 AI 图像生成。\n\n"
            "描述必须包含以下方面：\n"
            "1. 地点类型（室内/室外、具体场所）\n"
            "2. 光线和氛围\n"
            "3. 建筑/装饰风格\n"
            "4. 颜色基调\n"
            "5. 参考图片中可见的光线状态\n\n"
            "要求：\n"
            "- 忠实描述图片可见的空间结构、装修、材质、陈设和主色调\n"
            "- 不强制改变图片机位，不添加图片中不存在的房间或区域\n"
            "- 图片的昼夜只作为参考画面状态；具体镜头的昼夜、天气和剧情氛围由镜头脚本决定\n"
            "- 不描述白边、拼图布局、文字、Logo、水印或界面元素\n"
            "- 必须全程使用简体中文，只输出中文描述文本，不要编号、不要解释\n"
            "- 描述末尾加“真人影视写实风格”\n"
            "- 不要包含场景中文名"
        )

        logger.info(f"场景视觉分析: {scene_name} ← {image_path}")
        description = self.llm_client.generate_with_images(
            prompt=user_prompt,
            image_paths=[image_path],
            system_prompt=system_prompt,
            max_tokens=1024,
            temperature=0.3,
        )

        description = description.strip()
        logger.info(f"场景视觉分析完成: {scene_name} → {description[:80]}...")
        return (scene_name, aliases, episodes, description)

    def describe_prop_from_image(
        self,
        image_path: str,
        prop_name: str,
        aliases: str = "",
        episodes: str = "",
    ) -> tuple:
        """用 vision LLM 分析道具图片，只描述道具本体。"""
        system_prompt = (
            "你是一位专业的影视道具师和AI图像生成专家。"
            "请只观察图片中的主要道具本体，不要描述人物、手、桌面、摄影背景、"
            "展示架、边框、水印或无关文字。"
        )
        user_prompt = (
            f"请分析图中「{prop_name}」这个道具，生成用于 AI 图像生成的详细中文描述。\n\n"
            "描述道具类别、形状、材质、颜色、纹理、磨损状态和可识别结构。\n"
            "如果图片是多视角设定图，将其视为同一个道具。\n"
            "除非文字本身是该剧情道具的核心内容，否则忽略图片中的文字。\n"
            "必须全程使用简体中文，只输出中文描述文本，不要编号、不要解释、不要包含资产名；"
            "末尾加“真人影视写实风格”。"
        )
        logger.info(f"道具视觉分析: {prop_name} ← {image_path}")
        description = self.llm_client.generate_with_images(
            prompt=user_prompt,
            image_paths=[image_path],
            system_prompt=system_prompt,
            max_tokens=1024,
            temperature=0.3,
        ).strip()
        logger.info(f"道具视觉分析完成: {prop_name} → {description[:80]}...")
        return (prop_name, aliases, episodes, description)

    @staticmethod
    def _is_valid_visual_description(description: str) -> bool:
        """拒绝空白、过短或明显的模型错误响应。"""
        text = str(description or "").strip()
        if len(text) < 20:
            return False
        lowered = text.lower()
        error_markers = (
            "vision unavailable",
            "unable to analyze",
            "cannot analyze",
            "无法分析",
            "无法识别",
            "抱歉",
        )
        return not any(marker in lowered for marker in error_markers)

    def _find_character_image(
        self, char_image_dir: str, character_name: str
    ) -> Optional[str]:
        """在角色图目录中查找匹配的图片文件，支持多种扩展名。"""
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            path = os.path.join(char_image_dir, character_name + ext)
            if os.path.isfile(path):
                return path
        return None

    def _split_response_sections(self, response: str):
        """
        将 LLM 响应拆分为两部分：资产描述、剧情简介。
        返回 (assets_text, synopsis_text)。
        """
        synopsis_marker = "===剧情简介==="

        assets_text   = response
        synopsis_text = ""

        if synopsis_marker in response:
            assets_text, _, synopsis_text = response.partition(synopsis_marker)

        return assets_text.strip(), synopsis_text.strip()

    def _read_episodes(self, episodes_dir: str) -> str:
        """读取所有分集文本并拼接"""
        if not os.path.exists(episodes_dir):
            return ""
        if os.path.isfile(episodes_dir):
            try:
                with open(episodes_dir, "r", encoding="utf-8") as handle:
                    return handle.read().strip()
            except OSError as exc:
                logger.warning("读取标准化剧本失败: %s", exc)
                return ""

        texts = []
        files = sorted(
            f
            for f in os.listdir(episodes_dir)
            if f.endswith(".txt")
        )

        for filename in files:
            filepath = os.path.join(episodes_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if content:
                    ep_num = os.path.splitext(filename)[0]
                    texts.append(f"--- 第{ep_num}集 ---\n{content}")
            except Exception as e:
                logger.warning(f"读取 {filename} 失败: {e}")

        return "\n\n".join(texts)

    def _read_episode_texts(self, episodes_dir: str) -> Dict[str, str]:
        """Return normalized episode number -> raw text for deterministic asset scoping."""
        if not os.path.isdir(episodes_dir):
            return {}
        result: Dict[str, str] = {}
        for filename in os.listdir(episodes_dir):
            if not filename.lower().endswith(".txt"):
                continue
            stem = os.path.splitext(filename)[0]
            match = re.search(r"(\d+)", stem)
            if not match:
                continue
            episode = str(int(match.group(1))).zfill(2)
            try:
                with open(os.path.join(episodes_dir, filename), "r", encoding="utf-8") as handle:
                    result[episode] = handle.read()
            except OSError as exc:
                logger.warning("读取分集文本失败 %s: %s", filename, exc)
        return result

    def _build_scene_reextract_context(
        self,
        *,
        scene_image_dir: str = "",
        output_path: str = "",
        prompts_dir: str = "",
    ) -> str:
        image_records = self._read_existing_scene_image_records(
            scene_image_dir, output_path
        )
        scene_mentions = self._extract_scene_mentions_from_prompts(prompts_dir)
        if not image_records and not scene_mentions:
            return ""

        parts = [
            "\n\n【场景重提取附加规则】",
            "你正在重新提取场景资产。请把已有场景图片视为必须保留的资产，不要丢弃。",
            "如果剧本或镜头脚本中的地点只是已有图片场景的门口、内部、窗前、角落、同一空间不同机位，请把这些叫法放入该场景的别名列，不要另起新资产。",
            "输出仍然严格使用：场景中文名|别名1,别名2|01,02,03|场景中文描述。",
            "场景中文名优先沿用已有图片文件名，除非旧名明显错误；已有图片文件名本身必须至少出现在正式名或别名中。",
        ]
        if image_records:
            parts.append("\n【已有带图场景资产】")
            for record in image_records[:80]:
                parts.append(
                    f"- 图片文件名：{record['image_name']} | 旧名称：{record['name']} | "
                    f"旧别名：{record['aliases'] or '无'} | 旧集数：{record['episodes'] or '无'} | "
                    f"旧描述：{record['prompt'] or '无'}"
                )
        if scene_mentions:
            parts.append("\n【镜头脚本中出现过的核心场景叫法】")
            for name, episodes in scene_mentions[:160]:
                parts.append(f"- {name} | 出现集数：{','.join(episodes)}")
        return "\n".join(parts) + "\n\n"

    def _build_character_reextract_context(
        self,
        *,
        char_image_dir: str = "",
        output_path: str = "",
    ) -> str:
        image_records = self._read_existing_image_records(
            char_image_dir, output_path, "character_prompts.txt"
        )
        if not image_records:
            return ""
        parts = [
            "\n\n【角色重提取附加规则】",
            "你正在重新提取角色资产。已有角色图片文件名代表必须保留的角色资产，不要丢弃。",
            "如果图片名是“人物名+服装/造型/礼服/套装/制服/常服/寿宴”等明显造型变化，请把它作为独立角色资产输出，而不是合并回基础人物。",
            "例如：江蓁、江蓁寿宴服装 可以同时存在；镜头脚本后续会按正式名直接匹配对应图片。",
            "输出仍然严格使用：角色中文名|别名1,别名2|01,02,03|角色中文描述。",
        ]
        parts.append("\n【已有带图角色资产】")
        for record in image_records[:120]:
            parts.append(
                f"- 图片文件名：{record['image_name']} | 旧名称：{record['name']} | "
                f"旧别名：{record['aliases'] or '无'} | 旧集数：{record['episodes'] or '无'} | "
                f"旧描述：{record['prompt'] or '无'}"
            )
        return "\n".join(parts) + "\n\n"

    def _read_existing_scene_image_records(
        self, scene_image_dir: str, output_path: str
    ) -> List[dict]:
        return self._read_existing_image_records(
            scene_image_dir, output_path, "scene_prompts.txt"
        )

    def _read_existing_image_records(
        self, image_dir: str, output_path: str, category_prompt_filename: str
    ) -> List[dict]:
        if not image_dir or not os.path.isdir(image_dir):
            return []
        prompt_records = self._read_prompt_records_for_context(
            output_path, category_prompt_filename
        )
        records = []
        for filename in sorted(os.listdir(image_dir)):
            if not filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                continue
            name = os.path.splitext(filename)[0]
            old = prompt_records.get(name, {})
            records.append({
                "image_name": filename,
                "name": name,
                "aliases": old.get("aliases", ""),
                "episodes": old.get("episodes", ""),
                "prompt": old.get("prompt", ""),
            })
        return records

    def _read_prompt_records_for_context(
        self, output_path: str, category_prompt_filename: str = "scene_prompts.txt"
    ) -> Dict[str, dict]:
        candidates = []
        if output_path:
            candidates.append(output_path)
            if output_path.endswith(".extracting"):
                candidates.append(output_path[: -len(".extracting")])
            assets_dir = os.path.dirname(output_path)
            candidates.append(os.path.join(assets_dir, category_prompt_filename))
            candidates.append(os.path.join(assets_dir, "asset_descriptions.txt"))
        records: Dict[str, dict] = {}
        for path in candidates:
            if not path or not os.path.isfile(path):
                continue
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    parsed = self._parse_response(handle.read())
            except OSError:
                continue
            for name, aliases, episodes, prompt in parsed:
                records.setdefault(name, {
                    "aliases": aliases,
                    "episodes": episodes,
                    "prompt": prompt,
                })
        return records

    @staticmethod
    def _extract_scene_mentions_from_prompts(prompts_dir: str) -> List[tuple]:
        if not prompts_dir or not os.path.isdir(prompts_dir):
            return []
        mentions: Dict[str, set] = {}
        for filename in sorted(os.listdir(prompts_dir)):
            if not filename.lower().endswith(".txt"):
                continue
            match = re.search(r"(\d+)", filename)
            episode = str(int(match.group(1))).zfill(2) if match else ""
            path = os.path.join(prompts_dir, filename)
            try:
                with open(path, "r", encoding="utf-8-sig") as handle:
                    text = handle.read()
            except OSError:
                continue
            for scene in re.findall(r"核心场景[：:]\s*([^\n\r；;]+)", text):
                name = scene.strip()
                if not name or name == "无":
                    continue
                mentions.setdefault(name, set())
                if episode:
                    mentions[name].add(episode)
        return [
            (name, sorted(episodes, key=lambda value: int(value)))
            for name, episodes in sorted(mentions.items())
        ]

    @staticmethod
    def _fill_missing_episode_numbers(
        descriptions: List[tuple], episode_texts: Dict[str, str]
    ) -> List[tuple]:
        """Fill empty episode columns from formal names/strong aliases in episode text.

        This is intentionally deterministic. It does not invent an episode for an
        asset that cannot be found; such records remain unassigned and are excluded
        from per-episode scene rosters.
        """
        completed: List[tuple] = []
        for name, aliases, episodes, prompt in descriptions:
            existing = {str(ep).zfill(2) for ep in str(episodes or "").split(",") if str(ep).strip()}
            if not existing:
                candidates = [str(name).strip()]
                candidates.extend(
                    alias.strip() for alias in re.split(r"[,，、|/]", str(aliases or "")) if alias.strip()
                )
                for episode, text in episode_texts.items():
                    if any(token and token in text for token in candidates):
                        existing.add(episode)
            normalized = ",".join(sorted(existing, key=lambda value: int(value)))
            completed.append((name, aliases, normalized, prompt))
        return completed

    def _parse_response(self, response: str) -> List[tuple]:
        """
        解析 LLM 输出，支持三种格式：
          旧格式（2列）: 名称|描述
          旧格式（3列）: 名称|别名|描述
          新格式（4列）: 名称|别名|出场集数|描述

        返回 [(name, aliases_str, episodes_str, prompt), ...] 列表。
        """
        descriptions = []

        for line in response.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "|" not in line:
                continue

            parts = line.split("|")
            name = parts[0].strip()
            if not name:
                continue
            name = self._strip_explicit_asset_binding(name)

            if len(parts) == 2:
                # 旧格式兼容：名称|描述
                prompt = parts[1].strip()
                aliases = ""
                episodes = ""
            elif len(parts) >= 4:
                # 新格式：名称|别名|出场集数|描述
                aliases = parts[1].strip()
                episodes = parts[2].strip()
                prompt = "|".join(parts[3:]).strip()
            elif len(parts) == 3:
                # 旧格式：名称|别名|描述（无出场集数）
                aliases = parts[1].strip()
                episodes = ""
                prompt = parts[2].strip()
            else:
                continue

            if name and prompt and len(prompt) >= 10:
                descriptions.append((name, aliases, episodes, prompt))

        return descriptions

    def _extract_character_names_from_prompts(
        self, prompts_dir: str
    ) -> List[str]:
        """
        从所有镜头脚本中提取去重的角色名列表。

        扫描 prompts/ 目录下所有 .txt 文件，
        用正则提取 出镜人物【角色A、角色B】 中的角色名。

        返回: 去重排序后的角色名列表
        """
        SKIP_NAMES: Set[str] = {"无", "环境", "无（环境）", "无（纯环境）"}

        all_chars: Set[str] = set()

        try:
            prompt_files = sorted(
                f for f in os.listdir(prompts_dir)
                if f.endswith(".txt")
            )
        except OSError as e:
            logger.warning(f"读取镜头脚本目录失败: {e}")
            return []

        for filename in prompt_files:
            filepath = os.path.join(prompts_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    text = f.read()
            except Exception as e:
                logger.warning(f"读取镜头脚本 {filename} 失败: {e}")
                continue

            # 提取 出镜人物【...】 中的角色名
            for match in re.finditer(r"出镜人物【([^】]+)】", text):
                raw_names = match.group(1).split("、")
                for name in raw_names:
                    name = name.strip()
                    name = self._strip_explicit_asset_binding(name)
                    # 去除包裹的括号
                    name = re.sub(r'^[（(](.+)[）)]$', r'\1', name)
                    # 去除修饰前缀
                    name = re.sub(
                        r'^(回忆中的|想象中的|年轻时的|幻觉中的|少年时代的|小时候的)',
                        '', name
                    )
                    # 去除引号
                    name = name.strip('""\u201c\u201d')

                    if name and name not in SKIP_NAMES and len(name) >= 2:
                        all_chars.add(name)

        return sorted(all_chars)

    @staticmethod
    def _strip_explicit_asset_binding(name: str) -> str:
        value = str(name or "").strip()
        if "@" in value:
            explicit = value.rsplit("@", 1)[1].strip()
            if explicit:
                return explicit
        return value
