import os
import threading
from types import SimpleNamespace

from core.project import Project
from core.project_settings import save_project_settings
from core.shot_match_manifest import save_match_manifest
from web_api.operations import _batch_reference_paths, op_video


def test_video_operation_generates_one_fifteen_second_batch_and_splits_shots(
    tmp_path, monkeypatch
):
    script = tmp_path / "script.txt"
    script.write_text("第1集\n内容", encoding="utf-8")
    project = Project.create(str(tmp_path), "P", str(script))
    prompts = project.get_step_dir("prompt")
    (tmp_path / "P" / "assets" / "character" / "主角.png").write_bytes(b"png")
    with open(os.path.join(prompts, "01.txt"), "w", encoding="utf-8") as handle:
        handle.write("""镜头1：进入\n时长：5秒\n出镜人物【主角】\n核心场景：室内\n
镜头2：回头\n时长：5秒\n出镜人物【主角】\n核心场景：室内\n
镜头3：离开\n时长：5秒\n出镜人物【主角】\n核心场景：室内\n""")
    save_match_manifest(project.project_dir, "01", {
        "version": 1,
        "episode": "01",
        "shots": [
            {"shot": number, "characters": [{"name": "主角", "matched": True}], "scene": {}, "props": []}
            for number in (1, 2, 3)
        ],
    })
    save_project_settings(project.project_dir, {"prompt_prefix": "电影感"})

    calls = {"uploads": [], "generations": [], "splits": []}

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def upload_file(self, path):
            calls["uploads"].append(path)
            return "https://cdn/ref.png"

        def generate_video_and_wait(self, **kwargs):
            calls["generations"].append(kwargs)
            os.makedirs(os.path.dirname(kwargs["output_path"]), exist_ok=True)
            with open(kwargs["output_path"], "wb") as handle:
                handle.write(b"batch")
            return {"task_id": "t", "output_path": kwargs["output_path"]}

    def fake_split(self, source, segments, output_dir):
        calls["splits"].append((source, segments, output_dir))
        os.makedirs(output_dir, exist_ok=True)
        outputs = []
        for filename, _duration in segments:
            path = os.path.join(output_dir, filename)
            with open(path, "wb") as handle:
                handle.write(b"clip")
            outputs.append(path)
        return outputs

    monkeypatch.setattr("core.yunying_media_client.YunyingMediaClient", FakeClient)
    monkeypatch.setattr("core.ffmpeg_runner.FFmpegRunner.split_segments", fake_split)
    monkeypatch.setattr("web_api.operations._config", lambda: SimpleNamespace(
        media=SimpleNamespace(
            api_key="x", base_url="https://example/v1",
            video_model="seedance-2-0-official", image_model="gpt-image-2-official",
            timeout=10, poll_interval=0, request_timeout=1,
        ),
        ffmpeg_path="",
    ))

    result = op_video(project, "01", {}, threading.Event())

    assert result["success"] is True
    assert result["metadata"] == {"generated": 3, "batches": 1}
    assert len(calls["uploads"]) == 1
    assert len(calls["generations"]) == 1
    generation = calls["generations"][0]
    assert generation["duration"] == 15
    assert generation["mode"] == "reference"
    assert generation["images"] == ["https://cdn/ref.png"]
    assert "全局镜头要求：电影感" in generation["prompt"]
    assert calls["splits"][0][1] == [
        ("001.mp4", 5.0), ("002.mp4", 5.0), ("003.mp4", 5.0),
    ]


def test_reference_images_are_capped_at_seedance_limit(tmp_path):
    project_dir = tmp_path / "project"
    characters = project_dir / "assets" / "character"
    characters.mkdir(parents=True)
    records = []
    for index in range(12):
        name = f"角色{index:02d}"
        (characters / f"{name}.png").write_bytes(b"png")
        records.append({"name": name})

    paths = _batch_reference_paths(str(project_dir), [{
        "characters": records,
        "scene": {},
        "props": [],
    }])

    assert len(paths) == 9
