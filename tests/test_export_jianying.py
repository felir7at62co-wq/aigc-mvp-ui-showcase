"""时间线 -> 剪映工程：纯视频素材整理 + 语义时间线 + generate_draft。"""
import json
import os

import pytest

from core.export_jianying import export_jianying, prepare_episode_materials
from core.ffmpeg_runner import FFmpegRunner
from core.timeline import build_initial_timeline, save_timeline, trim_segment


@pytest.fixture(scope="module")
def runner():
    return FFmpegRunner()


@pytest.fixture()
def project_with_timeline(runner, tmp_path):
    project_dir = tmp_path / "project"
    web_video = project_dir / "web_video" / "01"
    web_video.mkdir(parents=True)
    for index, color in enumerate(("red", "blue"), start=1):
        runner.run([
            "-f", "lavfi", "-i", f"color=c={color}:s=160x90:r=15:d=2",
            "-pix_fmt", "yuv420p", "-y", str(web_video / f"{index:03d}.mp4"),
        ])
    timeline = build_initial_timeline("01", 30, 160, 90,
                                      ["web_video/01/001.mp4", "web_video/01/002.mp4"],
                                      durations=[2.0, 2.0])
    trim_segment(timeline, timeline.segments[0].id, 0.5, 1.5)
    save_timeline(str(project_dir), "01", timeline)
    return str(project_dir)


def test_prepare_materials_layout(project_with_timeline, tmp_path):
    materials_root = str(tmp_path / "materials")
    result = prepare_episode_materials(project_with_timeline, "01", materials_root)
    assert result["success"] is True
    # 当前约定只导出视频轨道，不创建任何音频目录或占位音轨。
    assert not os.path.exists(os.path.join(materials_root, "01_audio"))
    media = sorted(os.listdir(os.path.join(materials_root, "02_media", "01")))
    assert media == ["01.mp4", "02.mp4"]  # 按时间线顺序编号
    # 预裁剪保留 trim_in：第一个片段时长 ≈ 1.0
    first_probe = FFmpegRunner().probe(os.path.join(materials_root, "02_media", "01", "01.mp4"))
    assert first_probe["duration"] == pytest.approx(1.0, abs=0.2)
    assert os.path.isfile(os.path.join(materials_root, "05_timeline", "01.timeline.json"))


def test_semantic_timeline_json(project_with_timeline, tmp_path):
    materials_root = str(tmp_path / "materials")
    prepare_episode_materials(project_with_timeline, "01", materials_root)
    with open(os.path.join(materials_root, "05_timeline", "01.timeline.json"),
              "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    clips = payload["clips"]
    assert len(clips) == 2
    first = next(c for c in clips if c["shot"] == 1)
    assert first["duration_us"] == 1_000_000  # 裁剪后 1 秒
    assert first["start_us"] == 0
    second = next(c for c in clips if c["shot"] == 2)
    assert second["start_us"] == 1_000_000   # 紧随第一段


def test_export_jianying_returns_result_dict(project_with_timeline, tmp_path):
    result = export_jianying(
        project_with_timeline, "01",
        drafts_dir=str(tmp_path / "drafts"),
        prefix="测试_",
    )
    # generate_draft 返回 {"success": bool, ...}；无模板环境下允许失败但必须是该字典形状
    assert isinstance(result, dict)
    assert "success" in result
