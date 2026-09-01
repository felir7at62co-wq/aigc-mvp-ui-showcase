from pathlib import Path

from agents.asset_description_extractor import (
    AssetDescriptionExtractor,
    AssetPromptBuilder,
)


class _FakeLLM:
    def __init__(self):
        self.messages = None
        self.image_calls = 0

    def generate(self, messages, max_tokens=None, temperature=None):
        self.messages = messages
        return (
            "江蓁的新独立创意工作室|创意园区工作室门口,创意园区工作室内部|20|"
            "玻璃幕墙创意园区工作室，含门口和内部办公区，影视写实风格"
        )

    def generate_with_images(self, **_kwargs):
        self.image_calls += 1
        return "vision should not be used in this test"


class _ReextractLLM:
    def __init__(self, text_response, visual_response=None, visual_error=None):
        self.text_response = text_response
        self.visual_response = visual_response
        self.visual_error = visual_error
        self.image_calls = []

    def generate(self, messages, max_tokens=None, temperature=None):
        return self.text_response

    def generate_with_images(self, **kwargs):
        self.image_calls.append(kwargs)
        if self.visual_error:
            raise self.visual_error
        return self.visual_response


def test_scene_reextract_injects_existing_images_and_prompt_mentions(tmp_path):
    assets = tmp_path / "assets"
    scenes = assets / "scene"
    episodes = tmp_path / "episodes"
    prompts = tmp_path / "prompts"
    scenes.mkdir(parents=True)
    episodes.mkdir()
    prompts.mkdir()
    (scenes / "江蓁的新独立创意工作室.png").write_bytes(b"fake-image")
    (assets / "scene_prompts.txt").write_text(
        "江蓁的新独立创意工作室|工作室|13|旧玻璃幕墙工作室描述\n",
        encoding="utf-8",
    )
    (episodes / "20.txt").write_text("婆婆来到创意园区工作室门口。", encoding="utf-8")
    (prompts / "20.txt").write_text(
        "镜头1：\n核心场景：创意园区工作室门口\n\n"
        "镜头2：\n核心场景：创意园区工作室内部\n",
        encoding="utf-8",
    )
    llm = _FakeLLM()
    extractor = AssetDescriptionExtractor(
        llm,
        AssetPromptBuilder(user_template="{screenplay_text}\n{extra_context}"),
    )

    result = extractor.extract(
        str(episodes),
        str(assets / "scene_prompts.txt.extracting"),
        prompts_dir=str(prompts),
        scene_image_dir=str(scenes),
        category="scene",
        use_image_vision=False,
    )

    assert result["success"] is True
    assert llm.image_calls == 0
    user_content = llm.messages[-1]["content"]
    assert "已有带图场景资产" in user_content
    assert "江蓁的新独立创意工作室.png" in user_content
    assert "旧玻璃幕墙工作室描述" in user_content
    assert "镜头脚本中出现过的核心场景叫法" in user_content
    assert "创意园区工作室门口" in user_content
    assert "创意园区工作室内部" in user_content


def test_character_reextract_keeps_costume_variant_images(tmp_path):
    assets = tmp_path / "assets"
    characters = assets / "character"
    episodes = tmp_path / "episodes"
    characters.mkdir(parents=True)
    episodes.mkdir()
    (characters / "江蓁寿宴服装.png").write_bytes(b"fake-image")
    (assets / "character_prompts.txt").write_text(
        "江蓁寿宴服装|江蓁寿宴造型|01,02|寿宴服装角色变体描述足够长\n",
        encoding="utf-8",
    )
    (episodes / "01.txt").write_text("江蓁参加家庭寿宴。", encoding="utf-8")
    llm = _FakeLLM()
    extractor = AssetDescriptionExtractor(
        llm,
        AssetPromptBuilder(user_template="{screenplay_text}\n{extra_context}"),
    )

    result = extractor.extract(
        str(episodes),
        str(assets / "character_prompts.txt.extracting"),
        char_image_dir=str(characters),
        category="character",
        use_image_vision=False,
    )

    assert result["success"] is True
    assert llm.image_calls == 0
    user_content = llm.messages[-1]["content"]
    assert "已有带图角色资产" in user_content
    assert "江蓁寿宴服装.png" in user_content
    assert "作为独立角色资产输出" in user_content


def test_asset_extractor_strips_explicit_binding_markers_from_character_names(tmp_path):
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "13.txt").write_text(
        "镜头1：\n出镜人物【婆婆@婆婆、江蓁】\n",
        encoding="utf-8",
    )
    extractor = AssetDescriptionExtractor(_FakeLLM(), AssetPromptBuilder())

    names = extractor._extract_character_names_from_prompts(str(prompts))
    parsed = extractor._parse_response(
        "婆婆@婆婆|许母|13|单张角色设定图，真人影视写实风格，老年女性\n"
    )

    assert "婆婆@婆婆" not in names
    assert "婆婆" in names
    assert parsed[0][0] == "婆婆"


def test_failed_character_vision_preserves_existing_prompt_and_script_metadata(tmp_path):
    assets = tmp_path / "assets"
    characters = assets / "character"
    episodes = tmp_path / "episodes"
    characters.mkdir(parents=True)
    episodes.mkdir()
    (characters / "江蓁.png").write_bytes(b"fake-image")
    old_prompt = "用户图片对应的米色西装长直发角色视觉提示词"
    (assets / "character_prompts.txt").write_text(
        f"江蓁|我,蓁蓁|01,02|{old_prompt}\n",
        encoding="utf-8",
    )
    (episodes / "13.txt").write_text("江蓁走进包厢。", encoding="utf-8")
    llm = _ReextractLLM(
        "江蓁|女主|13|剧本模型生成的冲突外观提示词",
        visual_error=RuntimeError("vision unavailable"),
    )
    extractor = AssetDescriptionExtractor(llm, AssetPromptBuilder())

    result = extractor.extract(
        str(episodes),
        str(assets / "character_prompts.txt.extracting"),
        char_image_dir=str(characters),
        category="character",
        use_image_vision=True,
    )

    assert result["success"] is True
    output = (assets / "character_prompts.txt.extracting").read_text(encoding="utf-8")
    assert f"江蓁|女主|13|{old_prompt}" in output
    assert "剧本模型生成的冲突外观提示词" not in output


def test_prop_reextract_uses_image_prompt_but_keeps_script_metadata(tmp_path):
    assets = tmp_path / "assets"
    props = assets / "prop"
    episodes = tmp_path / "episodes"
    props.mkdir(parents=True)
    episodes.mkdir()
    (props / "泛黄存折.png").write_bytes(b"fake-image")
    (assets / "prop_prompts.txt").write_text(
        "泛黄存折|旧存折|13|旧道具提示词\n",
        encoding="utf-8",
    )
    (episodes / "13.txt").write_text("公公拿出泛黄的存折。", encoding="utf-8")
    visual_prompt = "一本泛黄磨损的老式银行存折，纸张陈旧，边缘起毛，真人影视写实风格"
    llm = _ReextractLLM(
        "泛黄存折|存折,秘密存折|13,14|剧本模型生成的详细道具外观描述文本",
        visual_response=visual_prompt,
    )
    extractor = AssetDescriptionExtractor(llm, AssetPromptBuilder())

    result = extractor.extract(
        str(episodes),
        str(assets / "prop_prompts.txt.extracting"),
        prop_image_dir=str(props),
        category="prop",
        use_image_vision=True,
    )

    assert result["success"] is True
    assert len(llm.image_calls) == 1
    output = (assets / "prop_prompts.txt.extracting").read_text(encoding="utf-8")
    assert f"泛黄存折|存折,秘密存折|13,14|{visual_prompt}" in output


def test_scene_vision_preserves_layout_without_forcing_birds_eye_or_story_time(tmp_path):
    image = tmp_path / "scene.png"
    image.write_bytes(b"fake-image")
    llm = _ReextractLLM(
        "",
        visual_response="深色木饰面的中餐厅独立包厢，暖色灯光，真人影视写实风格",
    )
    extractor = AssetDescriptionExtractor(llm, AssetPromptBuilder())

    extractor.describe_scene_from_image(str(image), "中餐厅豪华包厢")

    prompt = llm.image_calls[0]["prompt"]
    assert "详细的中文描述" in prompt
    assert "必须全程使用简体中文" in prompt
    assert "top-down view" not in prompt
    assert "bird's eye" not in prompt
    assert "空间结构" in prompt
    assert "具体镜头的昼夜" in prompt


def test_visual_description_accepts_valid_chinese_or_english_output():
    assert AssetDescriptionExtractor._is_valid_visual_description(
        "a luxurious wood-paneled private dining room, photorealistic"
    ) is True
    assert AssetDescriptionExtractor._is_valid_visual_description(
        "豪华中餐厅独立包厢，深色木饰面与暖色灯光，真人影视写实风格"
    ) is True


def test_character_vision_treats_multi_view_sheet_as_one_person(tmp_path):
    image = tmp_path / "character.png"
    image.write_bytes(b"fake-image")
    llm = _ReextractLLM(
        "",
        visual_response="一名身穿米色西装的东亚女性，黑色长发，真人影视写实风格",
    )
    extractor = AssetDescriptionExtractor(llm, AssetPromptBuilder())

    extractor.describe_from_image(str(image), "江蓁")

    prompt = llm.image_calls[0]["prompt"]
    assert "详细的中文描述" in prompt
    assert "必须全程使用简体中文" in prompt
    assert "多视角" in prompt
    assert "同一个人物" in prompt
    assert "只描述图片中实际可见的一套" in prompt


def test_visual_only_asset_preserves_existing_aliases_and_episode_scope(tmp_path):
    assets = tmp_path / "assets"
    characters = assets / "character"
    episodes = tmp_path / "episodes"
    characters.mkdir(parents=True)
    episodes.mkdir()
    (characters / "江蓁寿宴服装.png").write_bytes(b"fake-image")
    (assets / "character_prompts.txt").write_text(
        "江蓁寿宴服装|江蓁寿宴造型,江蓁包厢服装|01,02,03|原有服装外观提示词足够长度\n",
        encoding="utf-8",
    )
    (episodes / "13.txt").write_text("本集没有寿宴服装。", encoding="utf-8")
    visual_prompt = "一名身穿浅色正式宴会服装的东亚女性，黑色长发，真人影视写实风格"
    llm = _ReextractLLM(
        "陈静|陈总监|13|干练短发女性角色外观描述足够长度",
        visual_response=visual_prompt,
    )
    extractor = AssetDescriptionExtractor(llm, AssetPromptBuilder())

    extractor.extract(
        str(episodes),
        str(assets / "character_prompts.txt.extracting"),
        char_image_dir=str(characters),
        category="character",
        use_image_vision=True,
    )

    output = (assets / "character_prompts.txt.extracting").read_text(encoding="utf-8")
    assert (
        f"江蓁寿宴服装|江蓁寿宴造型,江蓁包厢服装|01,02,03|{visual_prompt}"
        in output
    )


def test_visual_and_text_failure_still_preserves_existing_image_asset(tmp_path):
    assets = tmp_path / "assets"
    props = assets / "prop"
    episodes = tmp_path / "episodes"
    props.mkdir(parents=True)
    episodes.mkdir()
    (props / "泛黄存折.png").write_bytes(b"fake-image")
    old_prompt = "泛黄纸张封面的老式银行存折道具视觉提示词"
    (assets / "prop_prompts.txt").write_text(
        f"泛黄存折|旧存折|13|{old_prompt}\n",
        encoding="utf-8",
    )
    (episodes / "13.txt").write_text("公公拿出存折。", encoding="utf-8")
    llm = _ReextractLLM(
        "模型没有返回合法的四列资产记录",
        visual_error=RuntimeError("vision unavailable"),
    )
    extractor = AssetDescriptionExtractor(llm, AssetPromptBuilder())

    result = extractor.extract(
        str(episodes),
        str(assets / "prop_prompts.txt.extracting"),
        prop_image_dir=str(props),
        category="prop",
        use_image_vision=True,
    )

    assert result["success"] is True
    output = (assets / "prop_prompts.txt.extracting").read_text(encoding="utf-8")
    assert f"泛黄存折|旧存折|13|{old_prompt}" in output


def test_same_asset_with_blank_script_metadata_falls_back_field_by_field(tmp_path):
    assets = tmp_path / "assets"
    scenes = assets / "scene"
    episodes = tmp_path / "episodes"
    scenes.mkdir(parents=True)
    episodes.mkdir()
    (scenes / "中餐厅豪华包厢.png").write_bytes(b"fake-image")
    (assets / "scene_prompts.txt").write_text(
        "中餐厅豪华包厢|酒店包厢,圆桌包厢|01,02,13|原场景视觉提示词足够长度\n",
        encoding="utf-8",
    )
    (episodes / "13.txt").write_text("众人在包厢争执。", encoding="utf-8")
    visual_prompt = "豪华中餐厅独立包厢，深色木饰面与暖色灯光，真人影视写实风格"
    llm = _ReextractLLM(
        "中餐厅豪华包厢|||剧本模型生成的场景外观描述足够长度",
        visual_response=visual_prompt,
    )
    extractor = AssetDescriptionExtractor(llm, AssetPromptBuilder())

    extractor.extract(
        str(episodes),
        str(assets / "scene_prompts.txt.extracting"),
        scene_image_dir=str(scenes),
        category="scene",
        use_image_vision=True,
    )

    output = (assets / "scene_prompts.txt.extracting").read_text(encoding="utf-8")
    assert (
        f"中餐厅豪华包厢|酒店包厢,圆桌包厢|01,02,13|{visual_prompt}"
        in output
    )
