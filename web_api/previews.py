"""预览蓝图：触发渲染、查询状态、获取预览视频。"""
from __future__ import annotations

from flask import Blueprint, jsonify

from core.manifest import ProjectManifest
from web_api import tasks as tasks_module
from web_api.operations import OPERATIONS
from web_api.projects import _load_project

blueprint = Blueprint("previews", __name__, url_prefix="/api/projects/<name>/preview")


@blueprint.post("/<episode_id>")
def trigger_preview(name: str, episode_id: str):
    project = _load_project(name)
    if project is None:
        return jsonify({"error": "项目不存在"}), 404
    task_id = tasks_module.queue.submit(project.project_dir, "preview", [episode_id], {},
                                        OPERATIONS["preview"])
    return jsonify({"task_id": task_id, "status": "queued"}), 202


@blueprint.get("/<episode_id>")
def get_preview(name: str, episode_id: str):
    project = _load_project(name)
    if project is None:
        return jsonify({"error": "项目不存在"}), 404
    record = ProjectManifest(project.project_dir).get(episode_id, "preview")
    return jsonify({
        "status": record.status,
        "preview_path": record.output_path,
        "error": record.error,
        "updated_at": record.updated_at,
        "metadata": dict(record.metadata),
    })
