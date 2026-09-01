"""导出蓝图：触发导出、查询各集导出状态。"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from core.manifest import ProjectManifest
from web_api import tasks as tasks_module
from web_api.operations import OPERATIONS
from web_api.projects import _load_project

blueprint = Blueprint("exports", __name__, url_prefix="/api/projects/<name>/exports")


@blueprint.post("")
def trigger_export(name: str):
    project = _load_project(name)
    if project is None:
        return jsonify({"error": "项目不存在"}), 404
    payload = request.get_json(silent=True) or {}
    episodes = [str(value) for value in (payload.get("episodes") or [])]
    if not episodes:
        return jsonify({"error": "缺少集数列表"}), 400
    options = {"drafts_dir": payload.get("drafts_dir", ""),
               "prefix": payload.get("prefix", "")}
    task_id = tasks_module.queue.submit(project.project_dir, "export", episodes, options,
                                        OPERATIONS["export"])
    return jsonify({"task_id": task_id, "status": "queued"}), 202


@blueprint.get("")
def list_exports(name: str):
    project = _load_project(name)
    if project is None:
        return jsonify({"error": "项目不存在"}), 404
    manifest = ProjectManifest(project.project_dir)
    episodes = {}
    for episode_id, records in manifest.data.get("episodes", {}).items():
        record = records.get("export")
        if isinstance(record, dict):
            episodes[episode_id] = {
                "status": record.get("status", "pending"),
                "output_path": record.get("output_path", ""),
                "error": record.get("error", ""),
                "updated_at": record.get("updated_at", ""),
            }
    return jsonify({"episodes": episodes})
