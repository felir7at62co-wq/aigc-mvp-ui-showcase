"""资产蓝图：复用 core.asset_catalog 的 CRUD。"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from flask import Blueprint, jsonify, request

from web_api.projects import _load_project

blueprint = Blueprint("assets", __name__, url_prefix="/api/projects/<name>/assets")


@blueprint.get("")
def list_assets(name: str):
    project = _load_project(name)
    if project is None:
        return jsonify({"error": "项目不存在"}), 404
    from core.asset_context import build_asset_context
    from core.asset_image_import import VALID_CATEGORIES, VALID_EXTENSIONS

    context = build_asset_context(project.project_dir)
    result = {category: [] for category in sorted(VALID_CATEGORIES)}
    assets_root = Path(project.project_dir, "assets")
    for category in result:
        by_name = {
            str(record.get("name", "")): dict(record)
            for record in context.get("assets", {}).get(category, [])
            if record.get("name")
        }
        image_dir = assets_root / category
        if image_dir.is_dir():
            for image_path in sorted(image_dir.iterdir(), key=lambda item: item.name):
                if not image_path.is_file() or image_path.suffix.lower() not in VALID_EXTENSIONS:
                    continue
                record = by_name.setdefault(image_path.stem, {
                    "name": image_path.stem,
                    "aliases": [],
                    "episodes": [],
                    "prompt": "",
                    "category": category,
                })
                record["image_path"] = image_path.relative_to(
                    Path(project.project_dir)
                ).as_posix()
        for record in by_name.values():
            record.setdefault("image_path", "")
            result[category].append(record)
        result[category].sort(key=lambda item: str(item.get("name", "")))
    return jsonify({"assets": result})


@blueprint.post("")
def create_asset(name: str):
    project = _load_project(name)
    if project is None:
        return jsonify({"error": "项目不存在"}), 404
    payload = request.get_json(silent=True) or {}
    from core.asset_catalog import add_asset
    try:
        record = add_asset(
            project.project_dir,
            str(payload.get("category", "")),
            name=str(payload.get("name", "")),
            aliases=str(payload.get("aliases", "")),
            episodes=str(payload.get("episodes", "")),
            prompt=str(payload.get("prompt", "")),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"asset": record}), 201


@blueprint.post("/<category>/<asset_name>")
def update_asset(name: str, category: str, asset_name: str):
    project = _load_project(name)
    if project is None:
        return jsonify({"error": "项目不存在"}), 404
    payload = request.get_json(silent=True) or {}
    from core.asset_catalog import update_asset
    try:
        record = update_asset(
            project.project_dir,
            category,
            original_name=asset_name,
            name=str(payload.get("name", asset_name)),
            aliases=str(payload.get("aliases", "")),
            episodes=str(payload.get("episodes", "")),
            prompt=str(payload.get("prompt", "")),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"asset": record})


@blueprint.post("/<category>/<asset_name>/image")
def upload_asset_image(name: str, category: str, asset_name: str):
    project = _load_project(name)
    if project is None:
        return jsonify({"error": "项目不存在"}), 404
    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        return jsonify({"error": "缺少图片文件"}), 400

    suffix = os.path.splitext(uploaded.filename)[1] or ".upload"
    temporary_path = ""
    try:
        with tempfile.NamedTemporaryFile("wb", delete=False, suffix=suffix) as handle:
            uploaded.save(handle.name)
            temporary_path = handle.name
        from core.asset_image_import import import_asset_image

        image_path = import_asset_image(
            project.project_dir, category, asset_name, temporary_path
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    finally:
        if temporary_path:
            try:
                os.remove(temporary_path)
            except OSError:
                pass
    relative = Path(image_path).relative_to(Path(project.project_dir)).as_posix()
    return jsonify({"image_path": relative})


@blueprint.delete("/<category>/<asset_name>")
def delete_asset(name: str, category: str, asset_name: str):
    project = _load_project(name)
    if project is None:
        return jsonify({"error": "项目不存在"}), 404
    from core.asset_catalog import delete_asset
    try:
        delete_asset(project.project_dir, category, asset_name)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True})
