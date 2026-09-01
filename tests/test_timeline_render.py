"""Tests for hard-cut timeline preview rendering."""

import os

import pytest

from core.ffmpeg_runner import FFmpegRunner
from core.timeline import build_initial_timeline, save_timeline, trim_segment
from core.timeline_render import render_preview


@pytest.fixture(scope="module")
def runner():
    return FFmpegRunner()


@pytest.fixture()
def clips(runner, tmp_path):
    """Create two two-second 160x90 clips and return project/path data."""
    project_dir = tmp_path / "project"
    web_video = project_dir / "web_video" / "01"
    web_video.mkdir(parents=True)
    paths = []
    for index, color in enumerate(("red", "blue"), start=1):
        path = web_video / f"{index:03d}.mp4"
        runner.run([
            "-f", "lavfi", "-i", f"color=c={color}:s=160x90:r=15:d=2",
            "-pix_fmt", "yuv420p", "-y", str(path),
        ])
        paths.append(f"web_video/01/{index:03d}.mp4")
    return str(project_dir), paths


def test_render_hard_cut_concat(clips, tmp_path):
    project_dir, videos = clips
    timeline = build_initial_timeline(
        "01", 30, 160, 90, videos, durations=[2.0, 2.0]
    )
    save_timeline(project_dir, "01", timeline)
    result = render_preview(project_dir, "01")
    assert result.success is True
    assert result.duration == pytest.approx(4.0, abs=0.3)
    assert os.path.isfile(result.preview_path)
    probe = FFmpegRunner().probe(result.preview_path)
    assert probe["width"] == 160


def test_render_respects_trims(clips, tmp_path):
    project_dir, videos = clips
    timeline = build_initial_timeline(
        "01", 30, 160, 90, videos, durations=[2.0, 2.0]
    )
    trim_segment(timeline, timeline.segments[0].id, 0.5, 1.5)
    save_timeline(project_dir, "01", timeline)
    result = render_preview(project_dir, "01")
    assert result.success is True
    assert result.duration == pytest.approx(3.0, abs=0.3)


def test_render_skips_deleted_segments(clips, tmp_path):
    project_dir, videos = clips
    timeline = build_initial_timeline(
        "01", 30, 160, 90, videos, durations=[2.0, 2.0]
    )
    from core.timeline import delete_segment

    delete_segment(timeline, timeline.segments[0].id)
    save_timeline(project_dir, "01", timeline)
    result = render_preview(project_dir, "01")
    assert result.duration == pytest.approx(2.0, abs=0.3)


def test_render_missing_timeline_fails(tmp_path):
    result = render_preview(str(tmp_path), "01")
    assert result.success is False


def test_render_crossfade(clips, tmp_path):
    from core.timeline import set_transition

    project_dir, videos = clips
    timeline = build_initial_timeline(
        "01", 30, 160, 90, videos, durations=[2.0, 2.0]
    )
    set_transition(timeline, timeline.segments[0].id, "crossfade", 0.5)
    save_timeline(project_dir, "01", timeline)
    result = render_preview(project_dir, "01")
    assert result.success is True
    assert result.duration == pytest.approx(3.5, abs=0.3)


def test_render_fade_black(clips, tmp_path):
    from core.timeline import set_transition

    project_dir, videos = clips
    timeline = build_initial_timeline(
        "01", 30, 160, 90, videos, durations=[2.0, 2.0]
    )
    set_transition(timeline, timeline.segments[0].id, "fade_black", 0.5)
    save_timeline(project_dir, "01", timeline)
    result = render_preview(project_dir, "01")
    assert result.success is True
    assert result.duration == pytest.approx(4.0, abs=0.3)

def test_render_success_writes_manifest(clips):
    from core.manifest import ProjectManifest
    from core.timeline_render import render_preview_with_manifest

    project_dir, videos = clips
    timeline = build_initial_timeline("01", 30, 160, 90, videos, durations=[2.0, 2.0])
    save_timeline(project_dir, "01", timeline)
    result = render_preview_with_manifest(project_dir, "01")
    assert result["success"] is True
    manifest = ProjectManifest(project_dir)
    record = manifest.get("01", "preview")
    assert record.status == "completed"
    assert record.output_path.startswith("exports/")
    assert os.path.isfile(os.path.join(project_dir, record.output_path))


def test_failed_render_keeps_previous_preview(clips):
    from core.manifest import ProjectManifest
    from core.timeline_render import render_preview_with_manifest

    project_dir, videos = clips
    timeline = build_initial_timeline("01", 30, 160, 90, videos, durations=[2.0, 2.0])
    save_timeline(project_dir, "01", timeline)
    first = render_preview_with_manifest(project_dir, "01")
    assert first["success"] is True
    preview_path = first["preview_path"]
    # 破坏源视频后重渲染应失败，但旧预览仍在且 manifest 保留旧路径
    source = os.path.join(project_dir, "web_video", "01", "001.mp4")
    os.remove(source)
    second = render_preview_with_manifest(project_dir, "01")
    assert second["success"] is False
    assert os.path.isfile(preview_path)
    manifest = ProjectManifest(project_dir)
    record = manifest.get("01", "preview")
    assert record.status == "failed"
    assert record.output_path.startswith("exports/")  # 旧路径保留，前端仍可播放
