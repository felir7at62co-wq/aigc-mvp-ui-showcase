from core.video_batches import build_batch_prompt, group_shots, parse_shot_blocks


SCRIPT = """镜头1：推门进入
时长：4秒
出镜人物【主角】
画面描述：【中景】

镜头2：回头
建议时长 6s
出镜人物【主角】
画面描述：【近景】

镜头3：看向窗外
时长：5秒
出镜人物【主角】
画面描述：【特写】

镜头4：离开
出镜人物【主角】
画面描述：【远景】"""


def test_parse_complete_shot_blocks_and_durations():
    shots = parse_shot_blocks(SCRIPT)
    assert [shot.number for shot in shots] == [1, 2, 3, 4]
    assert [shot.duration for shot in shots] == [4.0, 6.0, 5.0, 5.0]
    assert shots[0].text.startswith("镜头1：")
    assert "画面描述：【中景】" in shots[0].text


def test_groups_consecutive_shots_up_to_fifteen_seconds():
    batches = group_shots(parse_shot_blocks(SCRIPT), max_duration=15)
    assert [[shot.number for shot in batch] for batch in batches] == [[1, 2, 3], [4]]


def test_build_batch_prompt_keeps_complete_blocks_and_prefix():
    shots = parse_shot_blocks(SCRIPT)[:2]
    prompt = build_batch_prompt(shots, "电影感，保持人物一致")
    assert prompt.startswith("全局镜头要求：电影感，保持人物一致")
    assert "镜头1：推门进入" in prompt
    assert "镜头2：回头" in prompt
    assert "总时长 10.0 秒" in prompt
    assert "按镜头边界自然切镜" in prompt
