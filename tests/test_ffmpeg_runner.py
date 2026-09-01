"""Tests for bundled ffmpeg/ffprobe discovery and execution."""

import os

import pytest

from core.ffmpeg_runner import FFmpegError, FFmpegRunner


@pytest.fixture(scope="module")
def runner():
    return FFmpegRunner()


def test_discovers_bundled_ffmpeg(runner):
    assert runner.ffmpeg and runner.ffprobe
    assert os.path.isfile(runner.ffmpeg)
    assert os.path.isfile(runner.ffprobe)


def test_probe_tiny_generated_video(runner, tmp_path):
    output = tmp_path / "tiny.mp4"
    runner.run([
        "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=15:duration=1",
        "-pix_fmt", "yuv420p", "-y", str(output),
    ])
    info = runner.probe(str(output))
    assert info["duration"] == pytest.approx(1.0, abs=0.1)
    assert info["width"] == 160
    assert info["height"] == 90


def test_run_failure_raises(runner, tmp_path):
    with pytest.raises(FFmpegError):
        runner.run(["-i", "/nonexistent.mp4", "-y", str(tmp_path / "x.mp4")])


def test_probe_missing_file_returns_none(runner):
    assert runner.probe("N:/definitely/missing.mp4") is None


def test_split_segments_uses_cumulative_start_times(tmp_path, monkeypatch):
    source = tmp_path / "batch.mp4"
    source.write_bytes(b"video")
    runner = FFmpegRunner()
    calls = []

    def fake_run(args, timeout=3600):
        calls.append(args)

    monkeypatch.setattr(runner, "run", fake_run)
    outputs = runner.split_segments(
        str(source),
        [("001.mp4", 4.0), ("002.mp4", 6.0), ("003.mp4", 5.0)],
        str(tmp_path / "clips"),
    )

    assert [args[args.index("-ss") + 1] for args in calls] == ["0.000", "4.000", "10.000"]
    assert [args[args.index("-t") + 1] for args in calls] == ["4.000", "6.000", "5.000"]
    assert [os.path.basename(path) for path in outputs] == ["001.mp4", "002.mp4", "003.mp4"]
