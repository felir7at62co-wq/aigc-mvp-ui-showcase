"""Create a Jianying draft from the integrated, video-only timeline."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pyJianYingDraft as draft
from pyJianYingDraft.time_util import Timerange


class DraftInputError(ValueError):
    """Raised when the prepared video materials are incomplete."""


def _load_timeline(path: Path) -> dict[int, dict[str, int]]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DraftInputError(f"读取视频时间线失败: {exc}") from exc

    clips: dict[int, dict[str, int]] = {}
    for item in payload.get("clips", []):
        try:
            shot = int(item["shot"])
            start_us = int(item["start_us"])
            duration_us = int(item["duration_us"])
        except (KeyError, TypeError, ValueError):
            continue
        if shot > 0 and duration_us > 0:
            clips[shot] = {"start_us": start_us, "duration_us": duration_us}
    return clips


def _number(path: Path) -> int:
    match = re.search(r"(\d+)", path.stem)
    return int(match.group(1)) if match else 0


def _episode_ids(media_root: Path, seq: str | None) -> list[str]:
    if seq:
        return [str(seq).zfill(2)]
    return sorted(path.name for path in media_root.iterdir() if path.is_dir())


def _remove_existing_draft(drafts_root: Path, draft_name: str) -> None:
    target = (drafts_root / draft_name).resolve()
    root = drafts_root.resolve()
    if target.parent != root:
        raise DraftInputError("草稿输出路径越界")
    if target.is_dir():
        shutil.rmtree(target)
    elif target.exists():
        raise DraftInputError(f"草稿路径不是目录: {target}")


def generate_draft(
    drafts_dir: str,
    materials_dir: str,
    name_prefix: str = "",
    template_dir: str | None = None,
    seq: str | None = None,
) -> dict:
    """Generate video-only drafts; kept signature-compatible with the Web API."""
    del template_dir
    try:
        drafts_root = Path(drafts_dir)
        materials_root = Path(materials_dir)
        media_root = materials_root / "02_media"
        timeline_root = materials_root / "05_timeline"
        if not media_root.is_dir():
            raise DraftInputError("缺少视频素材目录 02_media")
        drafts_root.mkdir(parents=True, exist_ok=True)

        created = 0
        for episode in _episode_ids(media_root, seq):
            episode_dir = media_root / episode
            videos = sorted(
                (path for path in episode_dir.iterdir()
                 if path.is_file() and path.suffix.lower() in {".mp4", ".mov", ".webm", ".m4v"}),
                key=lambda path: (_number(path), path.name),
            )
            if not videos:
                raise DraftInputError(f"第 {episode} 集没有可导出的视频片段")

            timeline = _load_timeline(timeline_root / f"{episode}.timeline.json")
            draft_name = f"{name_prefix}{episode}"
            _remove_existing_draft(drafts_root, draft_name)
            script = draft.DraftFolder(str(drafts_root)).create_draft(
                draft_name, width=1920, height=1080,
            )
            script.maintrack_adsorb = False
            script.add_track(draft.TrackType.video, "视频轨道")

            fallback_start = 0
            for index, video_path in enumerate(videos, start=1):
                clip = timeline.get(index, {})
                start_us = int(clip.get("start_us", fallback_start))
                material = draft.VideoMaterial(str(video_path))
                duration_us = int(clip.get("duration_us", material.duration))
                if duration_us <= 0:
                    raise DraftInputError(f"{video_path.name} 时长无效")
                segment = draft.VideoSegment(
                    material,
                    Timerange(start_us, duration_us),
                )
                script.add_segment(segment, "视频轨道")
                fallback_start = start_us + duration_us

            script.save()
            created += 1

        return {"success": True, "drafts_created": created}
    except DraftInputError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        return {"success": False, "error": f"剪映工程生成失败: {exc}"}
