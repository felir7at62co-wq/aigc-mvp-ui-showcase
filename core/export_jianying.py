"""Export the integrated video timeline as a video-only Jianying draft."""

from __future__ import annotations

import json
import os
import shutil
from typing import Any, Dict

from core.ffmpeg_runner import FFmpegRunner
from core.timeline import Segment, load_timeline


def prepare_episode_materials(
    project_dir: str,
    episode_id: str,
    materials_root: str,
) -> Dict[str, Any]:
    timeline = load_timeline(project_dir, episode_id)
    if timeline is None:
        return {"success": False, "error": f"时间线不存在: {episode_id}"}
    segments = sorted(
        (segment for segment in timeline.segments if not segment.deleted),
        key=lambda segment: segment.order,
    )
    if not segments:
        return {"success": False, "error": "时间线没有可用片段"}

    episode = str(episode_id).zfill(2)
    media_dir = os.path.join(materials_root, "02_media", episode)
    timeline_dir = os.path.join(materials_root, "05_timeline")
    os.makedirs(media_dir, exist_ok=True)
    os.makedirs(timeline_dir, exist_ok=True)

    runner = FFmpegRunner()
    clips = []
    start_us = 0
    total = 0.0
    for index, segment in enumerate(segments, start=1):
        source = os.path.join(project_dir, segment.source_video.replace("/", os.sep))
        if not os.path.isfile(source):
            return {"success": False, "error": f"源视频不存在: {segment.source_video}"}
        if segment.duration <= 0:
            return {"success": False, "error": f"{segment.id}: 零时长片段"}

        target = os.path.join(media_dir, f"{index:02d}.mp4")
        if segment.trim_in <= 0.01:
            shutil.copy2(source, target)
        else:
            try:
                runner.run([
                    "-ss", f"{segment.trim_in:.3f}", "-i", source,
                    "-t", f"{segment.duration:.3f}",
                    "-c:v", "libx264", "-preset", "veryfast",
                    "-pix_fmt", "yuv420p", "-an", "-y", target,
                ])
            except Exception as exc:
                return {"success": False, "error": f"{segment.id} 预裁剪失败: {exc}"}

        duration_us = int(segment.duration * 1_000_000)
        clips.append({
            "shot": _shot_number(segment),
            "start_us": start_us,
            "duration_us": duration_us,
        })
        start_us += duration_us
        total += segment.duration

    timeline_path = os.path.join(timeline_dir, f"{episode}.timeline.json")
    with open(timeline_path, "w", encoding="utf-8") as handle:
        json.dump({"clips": clips}, handle, ensure_ascii=False, indent=2)
    return {"success": True, "materials_dir": materials_root, "duration": total}


def export_jianying(
    project_dir: str,
    episode_id: str,
    drafts_dir: str = "",
    prefix: str = "",
) -> Dict[str, Any]:
    """Generate one Jianying draft containing only the current video track."""
    if not drafts_dir:
        drafts_dir = os.path.join(
            os.path.expanduser("~"),
            "AppData", "Local", "JianyingPro", "User Data",
            "Projects", "com.lveditor.draft",
        )
    materials_root = os.path.join(project_dir, "materials_tmp")
    prepared = prepare_episode_materials(project_dir, episode_id, materials_root)
    if not prepared["success"]:
        return prepared

    episode = str(episode_id).zfill(2)
    from tools.jianying_draft import generate_draft

    result = generate_draft(
        drafts_dir=drafts_dir,
        materials_dir=materials_root,
        name_prefix=prefix,
        seq=episode,
    )
    result["draft_path"] = os.path.join(drafts_dir, f"{prefix}{episode}")
    result["draft_name"] = f"{prefix}{episode}"
    return result


def _shot_number(segment: Segment) -> int:
    import re

    match = re.search(r"(\d+)", segment.shot_id)
    return int(match.group(1)) if match else 0
