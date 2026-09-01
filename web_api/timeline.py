"""时间线蓝图：GET 读取 / PUT 创建或更新（模型层，渲染在 P2）。"""
from __future__ import annotations

import json
import os
import subprocess

from flask import Blueprint, jsonify, request

from core.paths import get_ffprobe_path
from core.timeline import (
    Segment,
    TimelineManifest,
    Transition,
    build_initial_timeline,
    load_timeline,
    save_timeline,
    validate_timeline,
)
from web_api.projects import _load_project

blueprint = Blueprint("timeline", __name__, url_prefix="/api/projects/<name>/timeline")


@blueprint.get("/<episode_id>")
def get_timeline(name: str, episode_id: str):
    project = _load_project(name)
    if project is None:
        return jsonify({"error": "项目不存在"}), 404
    timeline = load_timeline(project.project_dir, episode_id)
    if timeline is None:
        return jsonify({"error": "时间线不存在"}), 404
    return jsonify(_to_dict(timeline))


@blueprint.put("/<episode_id>")
def put_timeline(name: str, episode_id: str):
    project = _load_project(name)
    if project is None:
        return jsonify({"error": "项目不存在"}), 404
    payload = request.get_json(silent=True) or {}
    existing = load_timeline(project.project_dir, episode_id)
    if existing is None:
        if "segments" in payload:
            # 客户端提交了完整时间线内容：直接按内容校验，无需 create_if_missing
            existing = TimelineManifest(episode_id=str(episode_id))
        elif not payload.get("create_if_missing"):
            return jsonify({"error": "时间线不存在，需 create_if_missing=true"}), 404
        else:
            videos = _episode_videos(project, episode_id)
            if not videos:
                return jsonify({"error": "该集还没有视频文件，无法创建时间线"}), 400
            try:
                durations = _probe_durations(project, episode_id, videos)
            except RuntimeError as exc:
                return jsonify({"error": str(exc)}), 400
            existing = build_initial_timeline(
                episode_id=episode_id,
                fps=int(payload.get("fps", 30)),
                width=int(payload.get("width", 1080)),
                height=int(payload.get("height", 1920)),
                videos=videos,
                durations=durations,
            )
    timeline = _from_dict(existing, payload)
    errors = validate_timeline(timeline)
    if errors:
        return jsonify({"error": "时间线校验失败", "errors": errors}), 400
    save_timeline(project.project_dir, episode_id, timeline)
    return jsonify(_to_dict(load_timeline(project.project_dir, episode_id)))


def _episode_videos(project, episode_id: str):
    directory = project.get_episode_dir("web_video", int(episode_id))
    files = sorted(
        name for name in os.listdir(directory)
        if name.lower().endswith((".mp4", ".webm", ".mov"))
    )
    relative = os.path.join("web_video", f"{int(episode_id):02d}")
    return [f"{relative.replace(os.sep, '/')}/{name}" for name in files]


def _probe_durations(project, episode_id: str, videos) -> list:
    """用 ffprobe 读取每个视频的真实时长；失败抛 RuntimeError。"""
    durations = []
    for video in videos:
        path = os.path.join(project.project_dir, video.replace("/", os.sep))
        result = subprocess.run(
            [get_ffprobe_path(), "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", path],
            capture_output=True, timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f"无法探测视频时长: {video}")
        data = json.loads(result.stdout.decode("utf-8", errors="replace"))
        streams = data.get("streams", [])
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
        duration = float(
            data.get("format", {}).get("duration")
            or video_stream.get("duration")
            or 0.0
        )
        if duration <= 0:
            raise RuntimeError(f"视频时长非法: {video}")
        durations.append(duration)
    return durations


def _from_dict(timeline: TimelineManifest, payload: dict) -> TimelineManifest:
    if "segments" not in payload:
        return timeline
    segments = []
    for index, raw in enumerate(payload["segments"]):
        transition = Transition(
            **raw.get("transition_to_next", {"type": "hard", "duration": 0.0})
        )
        segments.append(Segment(
            id=str(raw.get("id", f"{timeline.episode_id}-{index + 1:03d}")),
            shot_id=str(raw.get("shot_id", "")),
            source_video=str(raw.get("source_video", "")),
            prompt=str(raw.get("prompt", "")),
            asset_ids=list(raw.get("asset_ids", [])),
            trim_in=float(raw.get("trim_in", 0.0)),
            trim_out=float(raw.get("trim_out", 0.0)),
            order=int(raw.get("order", index)),
            selected_version=str(raw.get("selected_version", "v1")),
            deleted=bool(raw.get("deleted", False)),
            transition_to_next=transition,
        ))
    timeline.segments = segments
    return timeline


def _to_dict(timeline: TimelineManifest) -> dict:
    from dataclasses import asdict
    return asdict(timeline)
