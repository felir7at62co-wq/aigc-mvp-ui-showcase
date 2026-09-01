"""任务蓝图：提交/查询/列表/取消。"""
from __future__ import annotations

import os

from flask import Blueprint, jsonify, request

from web_api.operations import OPERATIONS
from web_api.projects import _load_project
from web_api.task_queue import TaskQueue

queue = TaskQueue(max_workers=3)

blueprint = Blueprint("tasks", __name__, url_prefix="/api/projects/<name>/tasks")


@blueprint.post("")
def submit_task(name: str):
    project = _load_project(name)
    if project is None:
        return jsonify({"error": "项目不存在"}), 404
    payload = request.get_json(silent=True) or {}
    step = str(payload.get("step", "")).strip()
    if step not in OPERATIONS:
        return jsonify({"error": f"未知步骤: {step}", "available": sorted(OPERATIONS)}), 400
    episodes = [str(value) for value in (payload.get("episodes") or [])]
    if not episodes:
        return jsonify({"error": "缺少集数列表"}), 400
    options = payload.get("options") or {}
    task_id = queue.submit(project.project_dir, step, episodes, options, OPERATIONS[step])
    return jsonify({"task_id": task_id, "status": "queued"}), 202


@blueprint.get("")
def list_tasks(name: str):
    project = _load_project(name)
    if project is None:
        return jsonify({"error": "项目不存在"}), 404
    tasks = [item for item in queue.list() if item["project"] == project.project_dir]
    return jsonify({"tasks": tasks})


@blueprint.get("/<task_id>")
def get_task(name: str, task_id: str):
    record = queue.get(task_id)
    if record is None or record.project_dir != _project_dir(name):
        return jsonify({"error": "任务不存在"}), 404
    return jsonify(queue._to_dict(record))


@blueprint.post("/<task_id>/cancel")
def cancel_task(name: str, task_id: str):
    record = queue.get(task_id)
    if record is None or record.project_dir != _project_dir(name):
        return jsonify({"error": "任务不存在"}), 404
    ok = queue.cancel(task_id)
    return jsonify({"ok": ok})


def _project_dir(name: str) -> str:
    # 动态读取模块属性（测试会 monkeypatch PROJECTS_ROOT）
    from web_api.projects import PROJECTS_ROOT
    return os.path.join(PROJECTS_ROOT, os.path.basename(str(name)))
