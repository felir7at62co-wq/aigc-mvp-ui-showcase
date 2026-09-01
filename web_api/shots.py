"""镜头蓝图：镜头脚本文本 + 资产匹配清单。"""
from __future__ import annotations

import os

from flask import Blueprint, jsonify

from web_api.projects import _load_project

blueprint = Blueprint("shots", __name__, url_prefix="/api/projects/<name>/shots")


@blueprint.get("/<episode_id>")
def get_shot_script(name: str, episode_id: str):
    project = _load_project(name)
    if project is None:
        return jsonify({"error": "项目不存在"}), 404
    prompts_dir = project.get_step_dir("prompt")
    script_path = os.path.join(prompts_dir, f"{int(episode_id):02d}.txt")
    script = ""
    if os.path.isfile(script_path):
        with open(script_path, "r", encoding="utf-8") as handle:
            script = handle.read()
    from core.shot_match_manifest import load_match_manifest
    match = load_match_manifest(project.project_dir, episode_id)
    return jsonify({"episode_id": episode_id, "script": script, "match": match})
