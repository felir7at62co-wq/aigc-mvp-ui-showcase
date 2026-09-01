from pathlib import Path
import re

from agents.prompt_generator import (
    PromptBuilder,
    PromptGenerator,
    PromptSchema,
    ShotGenerationOutcome,
)


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses) if isinstance(responses, (list, tuple)) else [responses]
        self.calls = []

    def generate(self, messages, max_tokens=None, temperature=None, use_cache=None):
        self.calls.append(messages)
        index = min(len(self.calls) - 1, len(self.responses) - 1)
        return self.responses[index]


def make_episode_files(tmp_path: Path, episodes: list[str]) -> Path:
    root = tmp_path / "episodes"
    root.mkdir(exist_ok=True)
    screenplay = "\n".join(f"旁白：这是原文第{number}段。" for number in range(1, 6))
    for episode in episodes:
        (root / f"{episode}.txt").write_text(screenplay, encoding="utf-8")
    return root


def valid_shots(count: int = 5, *, dialogue: bool = False) -> str:
    sections = []
    for number in range(1, count + 1):
        voice_line = (
            f"测试角色：这是第{number}句台词。"
            if dialogue and number % 2 == 0
            else f"旁白：这是第{number}段旁白。"
        )
        sections.append("\n".join([
            f"镜头{number}：", "出镜人物【测试角色】", "核心场景：测试场景",
            "关键道具【无】", f"画面描述：【真人短剧风格 + 中景 + 第{number}个镜头】",
            "音效：环境声", voice_line,
        ]))
    return "\n\n".join(sections)


def one_shot_text() -> str:
    return "\n".join([
        "镜头1：", "出镜人物【未知角色】", "核心场景：未知场景", "关键道具【未知道具】",
        "画面描述：【真人短剧风格 + 中景 + 单个镜头】", "音效：环境声", "旁白：只生成了一个镜头。",
    ])


def make_generator(llm) -> PromptGenerator:
    # Unit tests use compact 5-shot fixtures for speed/readability; production
    # reads prompts/default_shot_prompt.txt, which is locked to 13-18 shots.
    return PromptGenerator(llm, prompt_builder=PromptBuilder(schema=PromptSchema(min_shots=5, max_shots=18)))


def test_process_generates_only_selected_episodes(tmp_path):
    episodes = make_episode_files(tmp_path, ["01", "02", "03"])
    output = tmp_path / "prompts"
    llm = FakeLLM(valid_shots())
    result = make_generator(llm).process(str(episodes), str(output), selected_episodes=["02"], skip_existing=False)
    assert result["success"] is True
    assert result["generated"] == 1
    assert len(llm.calls) == 1
    assert (output / "02.txt").exists()
    assert not (output / "01.txt").exists()
    assert not (output / "03.txt").exists()


def test_process_rejects_unknown_selected_episode(tmp_path):
    episodes = make_episode_files(tmp_path, ["01", "02"])
    output = tmp_path / "prompts"
    llm = FakeLLM(valid_shots())
    result = make_generator(llm).process(str(episodes), str(output), selected_episodes=["99"], skip_existing=False)
    assert result["success"] is False
    assert "未知集数" in result["error"]
    assert "99" in result["error"]
    assert not llm.calls


def test_explicit_empty_selection_generates_nothing(tmp_path):
    episodes = make_episode_files(tmp_path, ["01", "02"])
    output = tmp_path / "prompts"
    llm = FakeLLM(valid_shots())
    result = make_generator(llm).process(
        str(episodes), str(output), selected_episodes=[], skip_existing=False
    )
    assert result["generated"] == 0
    assert not llm.calls
    assert not list(output.glob("*.txt"))


def test_single_digit_source_is_published_with_normalized_episode_name(tmp_path):
    episodes = make_episode_files(tmp_path, ["2"])
    output = tmp_path / "prompts"
    result = make_generator(FakeLLM(valid_shots())).process(
        str(episodes), str(output), selected_episodes=["02"], skip_existing=False
    )
    assert result["success"] is True
    assert (output / "02.txt").exists()
    assert not (output / "2.txt").exists()


def test_one_shot_final_retry_is_not_published(tmp_path):
    episodes = make_episode_files(tmp_path, ["01"])
    output = tmp_path / "prompts"
    result = make_generator(FakeLLM(one_shot_text())).process(str(episodes), str(output), skip_existing=False)
    assert result["success"] is False
    assert result["failed"] == 1
    assert result["results"][0]["shot_count"] == 1
    assert "镜头数不足" in result["results"][0]["error"]
    assert not (output / "01.txt").exists()


def test_failed_regeneration_preserves_valid_existing_file(tmp_path):
    episodes = make_episode_files(tmp_path, ["01"])
    output = tmp_path / "prompts" / "01.txt"
    output.parent.mkdir()
    existing = valid_shots()
    output.write_text(existing, encoding="utf-8")
    result = make_generator(FakeLLM(one_shot_text())).process(str(episodes), str(output.parent), skip_existing=False)
    assert result["success"] is False
    assert output.read_text(encoding="utf-8") == existing
    assert not list(output.parent.glob(".01.*.tmp"))


def test_content_audit_accepts_direct_narration_and_dialogue_lines():
    generator = make_generator(FakeLLM(valid_shots(dialogue=True)))
    screenplay = "\n".join(["旁白：第一段。", "测试角色：第二段。", "旁白：第三段。", "测试角色：第四段。", "旁白：第五段。"])
    passed, issues = generator._audit_shot_script(valid_shots(dialogue=True), screenplay)
    assert passed, issues


def test_content_audit_does_not_block_visual_only_shots():
    no_voice = "\n\n".join(
        "\n".join([
            f"镜头{number}：", "出镜人物【测试角色】", "核心场景：测试场景",
            "关键道具【无】", f"画面描述：【第{number}个镜头】", "音效：环境声",
        ])
        for number in range(1, 6)
    )
    generator = make_generator(FakeLLM(no_voice))
    screenplay = "\n".join(f"旁白：原文第{number}段。" for number in range(1, 6))

    passed, issues = generator._audit_shot_script(no_voice, screenplay)

    assert passed, issues


def test_retry_feedback_does_not_preserve_invalid_shot_count():
    llm = FakeLLM(one_shot_text())
    generator = make_generator(llm)
    generator._character_guide = [{"name": "正式角色", "episodes": ["01"], "aliases": []}]
    generator._scene_guide = [{"name": "正式场景", "episodes": ["01"], "aliases": []}]
    generator._prop_guide = [{"name": "正式道具", "episodes": ["01"], "aliases": []}]
    outcome = generator._generate_single("\n".join(f"旁白：原文第{number}段。" for number in range(1, 6)), 1)
    assert isinstance(outcome, ShotGenerationOutcome)
    assert outcome.valid is False
    assert len(llm.calls) >= 2
    retry_prompt = llm.calls[1][-1]["content"]
    assert "镜头数不足" in retry_prompt
    assert "请保持镜头数量和剧情不变，只修正引用名称。" not in retry_prompt


def test_auto_fixed_alias_is_validated_as_final_candidate(monkeypatch):
    alias_script = valid_shots().replace("测试角色", "小测")
    generator = make_generator(FakeLLM(alias_script))
    generator._character_guide = [
        {"name": "测试角色", "episodes": ["01"], "aliases": ["小测"]}
    ]
    seen = []
    original_validate = generator._validate_output

    def capture(candidate):
        seen.append(candidate)
        return original_validate(candidate)

    monkeypatch.setattr(generator, "_validate_output", capture)
    outcome = generator._generate_single(
        "\n".join(f"旁白：原文第{number}段。" for number in range(1, 6)), 1
    )
    assert outcome.valid is True
    assert seen
    assert all("出镜人物【小测】" not in candidate for candidate in seen)
    assert "出镜人物【测试角色】" in outcome.text


def test_non_name_reference_issue_does_not_request_name_only_fix():
    broken = valid_shots().replace("关键道具【无】\n", "", 1)
    llm = FakeLLM(broken)
    generator = make_generator(llm)
    generator._generate_single(
        "\n".join(f"旁白：原文第{number}段。" for number in range(1, 6)), 1
    )
    retry_prompt = llm.calls[1][-1]["content"]
    assert "缺少: 关键道具" in retry_prompt
    assert "请保持镜头数量和剧情不变，只修正引用名称。" not in retry_prompt


def test_name_issue_with_visual_only_shots_requests_name_only_fix():
    no_voice = "\n\n".join(
        "\n".join([
            f"镜头{number}：", "出镜人物【未知角色】", "核心场景：测试场景",
            "关键道具【无】", f"画面描述：【第{number}个镜头】",
        ])
        for number in range(1, 6)
    )
    llm = FakeLLM(no_voice)
    generator = make_generator(llm)
    generator._character_guide = [
        {"name": "正式角色", "episodes": ["01"], "aliases": []}
    ]
    generator._generate_single(
        "\n".join(f"旁白：原文第{number}段。" for number in range(1, 6)), 1
    )
    retry_prompt = llm.calls[1][-1]["content"]
    assert "超过半数镜头缺少台词/旁白内容" not in retry_prompt
    assert "请保持镜头数量和剧情不变，只修正引用名称。" in retry_prompt


def test_stage_words_attached_to_character_name_are_auto_fixed():
    script = valid_shots().replace("出镜人物【测试角色】", "出镜人物【后期测试角色】")
    generator = make_generator(FakeLLM(script))
    generator._character_guide = [
        {"name": "测试角色", "episodes": ["01"], "aliases": []}
    ]

    fixed, issues = generator._audit_and_fix_references(script, 1)

    assert not issues
    assert "出镜人物【后期测试角色】" not in fixed
    assert "出镜人物【测试角色】" in fixed


def test_process_rejects_invalid_max_concurrency(tmp_path):
    episodes = make_episode_files(tmp_path, ["01"])
    llm = FakeLLM(valid_shots())
    result = make_generator(llm).process(
        str(episodes), str(tmp_path / "prompts"), max_concurrency=0
    )
    assert result["success"] is False
    assert "正整数" in result["error"]
    assert not llm.calls


def test_reference_audit_uses_custom_schema_delimiter():
    numbered = re.sub(r"镜头(\d+)：", r"\1. ", valid_shots())
    builder = PromptBuilder(schema=PromptSchema(
        delimiter=r"(?m)^\s*(\d+)\.\s+", min_shots=5, max_shots=18
    ))
    generator = PromptGenerator(FakeLLM(numbered), prompt_builder=builder)
    outcome = generator._generate_single(
        "\n".join(f"旁白：原文第{number}段。" for number in range(1, 6)), 1
    )
    assert outcome.valid is True
    assert outcome.text.startswith("1. ")


def test_legacy_visual_detail_fields_are_satisfied_by_picture_description():
    schema = PromptSchema(
        min_shots=5,
        max_shots=18,
        required_fields=[
            "出镜人物【",
            "核心场景：",
            "关键道具【",
            "画面描述：【",
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
        ],
    )
    generator = PromptGenerator(
        FakeLLM(valid_shots()),
        prompt_builder=PromptBuilder(schema=schema),
    )

    passed, issues = generator._validate_output(valid_shots())

    assert passed, issues


def test_default_shot_template_uses_lightweight_schema():
    template_path = Path(__file__).resolve().parents[1] / "prompts" / "default_shot_prompt.txt"
    builder = PromptBuilder.from_file(str(template_path))

    assert builder.schema.required_fields == [
        "出镜人物【",
        "核心场景：",
        "关键道具【",
        "画面描述：【",
    ]
    assert builder.schema.min_shots == 13
    assert builder.schema.max_shots == 18
    assert "风格：【" not in builder.schema.required_fields
