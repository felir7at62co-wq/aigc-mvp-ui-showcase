"""Episode list and detail routes."""

from __future__ import annotations

import os
import time

from flask import Blueprint, jsonify, request

from web_api.projects import _load_project

blueprint = Blueprint(
    "episodes",
    __name__,
    url_prefix="/api/projects/<name>/episodes",
)


@blueprint.get("")
def list_episodes(name: str):
    project = _load_project(name)
    if project is None:
        return jsonify({"error": "项目不存在"}), 404

    from web_api.serializers import episode_list

    return jsonify({"episodes": episode_list(project)})


@blueprint.get("/<episode_id>")
def get_episode(name: str, episode_id: str):
    project = _load_project(name)
    if project is None:
        return jsonify({"error": "项目不存在"}), 404

    from web_api.serializers import episode_detail

    try:
        return jsonify(episode_detail(project, episode_id))
    except KeyError:
        return jsonify({"error": f"第{episode_id}集不存在"}), 404


@blueprint.get("/<episode_id>/videos")
def list_episode_videos(name: str, episode_id: str):
    project = _load_project(name)
    if project is None:
        return jsonify({"error": "项目不存在"}), 404
    directory = project.get_episode_dir("web_video", int(episode_id))
    files = sorted(
        filename for filename in os.listdir(directory)
        if filename.lower().endswith((".mp4", ".webm", ".mov"))
    )
    prefix = f"web_video/{int(episode_id):02d}"
    return jsonify({"videos": [f"{prefix}/{filename}" for filename in files]})


@blueprint.post("/<episode_id>/videos")
def upload_episode_video(name: str, episode_id: str):
    project = _load_project(name)
    if project is None:
        return jsonify({"error": "项目不存在"}), 404
    file = request.files.get("file")
    if file is None or not file.filename:
        return jsonify({"error": "缺少视频文件"}), 400
    extension = os.path.splitext(file.filename)[1].lower()
    if extension not in (".mp4", ".webm", ".mov"):
        return jsonify({"error": "仅支持 mp4/webm/mov"}), 400
    directory = project.get_episode_dir("web_video", int(episode_id))
    filename = f"uploaded-{int(time.time())}{extension}"
    file.save(os.path.join(directory, filename))
    return jsonify({"video_path": f"web_video/{int(episode_id):02d}/{filename}"}), 201
