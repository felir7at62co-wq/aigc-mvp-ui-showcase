"""Project routes: create, list, detail, and delete."""

from __future__ import annotations

import os
import shutil
import tempfile

from flask import Blueprint, jsonify, request

from core.paths import get_projects_root
from core.project import Project
from core.project_settings import load_project_settings, save_project_settings

PROJECTS_ROOT = get_projects_root()
blueprint = Blueprint("projects", __name__, url_prefix="/api/projects")


@blueprint.get("")
def list_projects():
    from web_api.serializers import project_list_item

    items = []
    if os.path.isdir(PROJECTS_ROOT):
        for name in sorted(os.listdir(PROJECTS_ROOT)):
            project_dir = os.path.join(PROJECTS_ROOT, name)
            if os.path.isfile(os.path.join(project_dir, "state.json")):
                items.append(project_list_item(project_dir, name))
    return jsonify({"projects": items})


@blueprint.post("")
def create_project():
    name = (request.form.get("name") or "").strip()
    if not name:
        return jsonify({"error": "缺少项目名称"}), 400
    uploaded = request.files.get("script")
    if uploaded is None or not uploaded.filename:
        return jsonify({"error": "缺少剧本文件"}), 400

    os.makedirs(PROJECTS_ROOT, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "wb", delete=False, suffix=os.path.splitext(uploaded.filename)[1] or ".txt"
    ) as handle:
        uploaded.save(handle.name)
        script_path = handle.name
    try:
        project = Project.create(PROJECTS_ROOT, name, script_path)
    except FileNotFoundError as exc:
        return jsonify({"error": f"剧本读取失败: {exc}"}), 400
    finally:
        try:
            os.remove(script_path)
        except OSError:
            pass

    from core.manifest import ArtifactRecord
    from core.script_source import ProjectScriptSource

    source = ProjectScriptSource(project.project_dir)
    for segment in source.segments():
        project.manifest.set(
            segment.episode_id,
            "import_script",
            ArtifactRecord(
                status="completed",
                output_path=os.path.join("episodes", f"{segment.episode_id}.txt"),
            ),
        )
    project.manifest.save()

    try:
        save_project_settings(project.project_dir, {
            "aspect_ratio": request.form.get("aspect_ratio", "9:16"),
            "resolution": request.form.get("resolution", "720p"),
            "prompt_prefix": request.form.get("prompt_prefix", ""),
        })
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    from web_api.serializers import project_summary

    return jsonify(project_summary(project)), 201


@blueprint.get("/<name>")
def get_project(name: str):
    project = _load_project(name)
    if project is None:
        return jsonify({"error": "项目不存在"}), 404
    from web_api.serializers import project_summary

    return jsonify(project_summary(project))


@blueprint.get("/<name>/settings")
def get_project_settings(name: str):
    project = _load_project(name)
    if project is None:
        return jsonify({"error": "项目不存在"}), 404
    payload = load_project_settings(project.project_dir)
    payload["api_configured"] = bool(os.getenv("YUNYING_API_KEY", "").strip())
    return jsonify(payload)


@blueprint.put("/<name>/settings")
def update_project_settings(name: str):
    project = _load_project(name)
    if project is None:
        return jsonify({"error": "项目不存在"}), 404
    try:
        payload = save_project_settings(project.project_dir, request.get_json(silent=True) or {})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    payload["api_configured"] = bool(os.getenv("YUNYING_API_KEY", "").strip())
    return jsonify(payload)


@blueprint.delete("/<name>")
def delete_project(name: str):
    project = _load_project(name)
    if project is None:
        return jsonify({"error": "项目不存在"}), 404
    shutil.rmtree(project.project_dir, ignore_errors=True)
    return jsonify({"ok": True})


def _load_project(name: str):
    safe_name = os.path.basename(str(name))
    project_dir = os.path.join(PROJECTS_ROOT, safe_name)
    if not os.path.isfile(os.path.join(project_dir, "state.json")):
        return None
    try:
        return Project.load(project_dir)
    except FileNotFoundError:
        return None
