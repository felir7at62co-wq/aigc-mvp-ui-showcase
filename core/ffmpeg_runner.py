"""Unified wrapper for bundled FFmpeg and FFprobe."""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Dict, List, Optional


class FFmpegError(RuntimeError):
    """Raised when FFmpeg cannot run successfully."""


class FFmpegRunner:
    def __init__(self, ffmpeg_path: str = "", ffprobe_path: str = ""):
        self.ffmpeg = self._resolve(ffmpeg_path, is_ffprobe=False)
        self.ffprobe = self._resolve(ffprobe_path, is_ffprobe=True)

    def _resolve(self, configured: str, is_ffprobe: bool) -> str:
        from core.paths import get_ffmpeg_path, get_ffprobe_path

        candidates = []
        if configured:
            candidates.append(configured)
        if is_ffprobe:
            candidates.append(os.environ.get("FFPROBE_BINARY", ""))
            candidates.append(get_ffprobe_path())
        else:
            candidates.append(os.environ.get("FFMPEG_BINARY", ""))
            candidates.append(get_ffmpeg_path())
        for candidate in candidates:
            if candidate and os.path.isfile(candidate):
                return candidate
        return candidates[-1] if candidates else ""

    def available(self) -> bool:
        return bool(self.ffmpeg and os.path.isfile(self.ffmpeg))

    def run(self, args: List[str], timeout: int = 3600) -> subprocess.CompletedProcess:
        if not self.available():
            raise FFmpegError(f"FFmpeg not found: {self.ffmpeg}")
        command = [self.ffmpeg, "-hide_banner", "-loglevel", "error", *args]
        try:
            result = subprocess.run(command, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise FFmpegError(f"FFmpeg timed out: {exc}") from exc
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace")[-2000:]
            raise FFmpegError(stderr or f"FFmpeg exited with {result.returncode}")
        return result

    def probe(self, path: str) -> Optional[Dict[str, Any]]:
        if not os.path.isfile(path):
            return None
        command = [
            self.ffprobe,
            "-v", "error",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            path,
        ]
        try:
            result = subprocess.run(command, capture_output=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0:
            return None
        try:
            data = json.loads(result.stdout.decode("utf-8", errors="replace"))
        except ValueError:
            return None
        streams = data.get("streams", [])
        video = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
        duration = float(
            data.get("format", {}).get("duration")
            or video.get("duration")
            or 0.0
        )
        return {
            "duration": duration,
            "width": int(video.get("width", 0)),
            "height": int(video.get("height", 0)),
            "fps": _fps(video.get("r_frame_rate", "0/1")),
            "codec": video.get("codec_name", ""),
        }

    def split_segments(
        self,
        source_path: str,
        segments: List[tuple[str, float]],
        output_dir: str,
    ) -> List[str]:
        """Accurately re-encode consecutive shot ranges from one generated batch."""
        if not os.path.isfile(source_path):
            raise FFmpegError(f"Source video not found: {source_path}")
        os.makedirs(output_dir, exist_ok=True)
        outputs: List[str] = []
        start = 0.0
        for filename, duration in segments:
            safe_name = os.path.basename(filename)
            output_path = os.path.join(output_dir, safe_name)
            self.run([
                "-ss", f"{start:.3f}",
                "-i", source_path,
                "-t", f"{float(duration):.3f}",
                "-map", "0:v:0",
                "-map", "0:a?",
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "18",
                "-c:a", "aac",
                "-movflags", "+faststart",
                "-y", output_path,
            ])
            outputs.append(output_path)
            start += float(duration)
        return outputs


def _fps(rate: str) -> float:
    try:
        numerator, denominator = rate.split("/")
        return float(numerator) / float(denominator)
    except (ValueError, ZeroDivisionError):
        return 0.0
