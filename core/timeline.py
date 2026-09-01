"""每集 timeline.json 模型：原子读写、版本、校验、片段操作。

文件位置: {project_dir}/timeline/{episode_id}.json
原子写入 + 递增 version；所有编辑先改 manifest 再触发渲染。
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class Transition:
    type: str = "hard"            # hard | crossfade | fade_black
    duration: float = 0.0         # 秒；hard 时为 0

    def __post_init__(self):
        if self.type not in ("hard", "crossfade", "fade_black"):
            raise ValueError(f"不支持的转场类型: {self.type}")


@dataclass
class Segment:
    id: str
    shot_id: str
    source_video: str            # 相对项目目录
    prompt: str = ""
    asset_ids: List[str] = field(default_factory=list)
    trim_in: float = 0.0
    trim_out: float = 0.0
    order: int = 0
    selected_version: str = "v1"
    deleted: bool = False
    transition_to_next: Transition = field(default_factory=Transition)

    @property
    def duration(self) -> float:
        return max(0.0, self.trim_out - self.trim_in)


@dataclass
class TimelineManifest:
    episode_id: str
    version: int = 1
    fps: int = 30
    width: int = 1080
    height: int = 1920
    segments: List[Segment] = field(default_factory=list)
    preview_video: str = ""
    jianying_project: str = ""


def build_initial_timeline(
    episode_id: str,
    fps: int = 30,
    width: int = 1080,
    height: int = 1920,
    videos: Optional[List[str]] = None,
    durations: Optional[List[float]] = None,
) -> TimelineManifest:
    """从生成好的视频文件列表自动串接初始时间线（默认硬切、按文件名顺序）。

    ``durations[i]`` 是对应视频的时长（秒）；缺失时 trim_out 为 0，
    会被 ``validate_timeline`` 判为非法，调用方必须用 ffprobe 提供真实时长。
    新时间线从 version 0 开始，首次保存后写入 version 1。
    """
    segments: List[Segment] = []
    for index, video in enumerate(videos or [], start=1):
        duration = (
            float(durations[index - 1])
            if durations and index - 1 < len(durations)
            else 0.0
        )
        segments.append(
            Segment(
                id=f"{episode_id}-{index:03d}",
                shot_id=f"shot-{index:03d}",
                source_video=video,
                trim_out=duration,
                order=index - 1,
                selected_version="v1",
            )
        )
    return TimelineManifest(
        episode_id=str(episode_id),
        version=0,
        fps=fps,
        width=width,
        height=height,
        segments=segments,
    )


def validate_timeline(timeline: TimelineManifest) -> List[str]:
    """返回错误列表；空列表表示合法。"""
    errors: List[str] = []
    for segment in timeline.segments:
        if segment.deleted:
            continue
        if segment.trim_out <= segment.trim_in:
            errors.append(
                f"{segment.id}: 时长非法（trim_out={segment.trim_out} <= "
                f"trim_in={segment.trim_in}）"
            )
        if not segment.source_video:
            errors.append(f"{segment.id}: 缺少 source_video")

    for index, segment in enumerate(timeline.segments):
        if segment.deleted:
            continue
        transition = segment.transition_to_next
        if transition.type == "hard":
            continue
        available = segment.duration
        if index + 1 < len(timeline.segments):
            available = min(available, timeline.segments[index + 1].duration)
        if transition.duration <= 0 or transition.duration > available:
            errors.append(
                f"{segment.id}: 转场时长 {transition.duration}s 超出相邻片段可用时长 {available}s"
            )
    return errors


def load_timeline(project_dir: str, episode_id: str) -> Optional[TimelineManifest]:
    path = _timeline_path(project_dir, episode_id)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None

    segments = []
    for raw in data.get("segments", []):
        transition = Transition(**raw.get("transition_to_next", {}))
        segments.append(Segment(**{**raw, "transition_to_next": transition}))
    return TimelineManifest(
        episode_id=str(data.get("episode_id", episode_id)),
        version=int(data.get("version", 1)),
        fps=int(data.get("fps", 30)),
        width=int(data.get("width", 1080)),
        height=int(data.get("height", 1920)),
        segments=segments,
        preview_video=str(data.get("preview_video", "")),
        jianying_project=str(data.get("jianying_project", "")),
    )


def save_timeline(project_dir: str, episode_id: str, timeline: TimelineManifest) -> Path:
    timeline.version = int(timeline.version or 0) + 1
    directory = _timeline_dir(project_dir)
    path = _timeline_path(project_dir, episode_id)
    payload = {
        "episode_id": timeline.episode_id,
        "version": timeline.version,
        "fps": timeline.fps,
        "width": timeline.width,
        "height": timeline.height,
        "segments": [asdict(segment) for segment in timeline.segments],
        "preview_video": timeline.preview_video,
        "jianying_project": timeline.jianying_project,
    }
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", delete=False, dir=directory, suffix=".tmp"
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        temp_path = handle.name
    os.replace(temp_path, path)
    return path


def reorder_segments(timeline: TimelineManifest, segment_ids: List[str]) -> None:
    """按 ``segment_ids`` 重排，未列出的片段按原相对顺序追加到末尾。"""
    by_id = {segment.id: segment for segment in timeline.segments}
    ordered = [by_id[segment_id] for segment_id in segment_ids if segment_id in by_id]
    ordered_ids = {segment.id for segment in ordered}
    ordered.extend(segment for segment in timeline.segments if segment.id not in ordered_ids)
    for index, segment in enumerate(ordered):
        segment.order = index
    timeline.segments = ordered


def trim_segment(
    timeline: TimelineManifest,
    segment_id: str,
    trim_in: float,
    trim_out: float,
) -> None:
    for segment in timeline.segments:
        if segment.id == segment_id:
            segment.trim_in = float(trim_in)
            segment.trim_out = float(trim_out)
            return
    raise KeyError(f"片段不存在: {segment_id}")


def delete_segment(timeline: TimelineManifest, segment_id: str) -> None:
    for segment in timeline.segments:
        if segment.id == segment_id:
            segment.deleted = True
            return
    raise KeyError(f"片段不存在: {segment_id}")


def restore_segment(timeline: TimelineManifest, segment_id: str) -> None:
    for segment in timeline.segments:
        if segment.id == segment_id:
            segment.deleted = False
            return
    raise KeyError(f"片段不存在: {segment_id}")


def set_transition(
    timeline: TimelineManifest,
    segment_id: str,
    transition_type: str,
    duration: float,
) -> None:
    for segment in timeline.segments:
        if segment.id == segment_id:
            segment.transition_to_next = Transition(
                type=transition_type,
                duration=float(duration),
            )
            return
    raise KeyError(f"片段不存在: {segment_id}")


def _timeline_dir(project_dir: str) -> Path:
    directory = Path(project_dir) / "timeline"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _timeline_path(project_dir: str, episode_id: str) -> Path:
    return _timeline_dir(project_dir) / f"{int(str(episode_id)):02d}.json"
