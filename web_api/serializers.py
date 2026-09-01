"""JSON serializers for Web API responses."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from core.project import Project, migrate_legacy_state
from core.script_source import ProjectScriptSource


def project_list_item(project_dir: str, name: str) -> Dict[str, Any]:
    state_file = os.path.join(project_dir, "state.json")
    return {
        "name": name,
        "created_at": _state_value(state_file, "created_at", ""),
        "updated_at": _state_value(state_file, "updated_at", ""),
    }


def project_summary(project: Project) -> Dict[str, Any]:
    source = ProjectScriptSource(project.project_dir)
    try:
        episode_count = len(source.segments())
    except (OSError, ValueError, KeyError):
        episode_count = int(project.state.episode_count or 0)
    return {
        "name": project.state.name,
        "created_at": project.state.created_at,
        "updated_at": project.state.updated_at,
        "episode_count": episode_count,
        "episodes": {
            "total": episode_count,
            "by_status": _episode_status_counts(project),
        },
        "steps": _aggregated_steps(project),
    }


def _aggregated_steps(project: Project) -> Dict[str, Dict[str, Any]]:
    """Aggregate per-episode manifest statuses into project-level statuses."""
    view = migrate_legacy_state(project.project_dir)
    source = ProjectScriptSource(project.project_dir)
    try:
        episode_ids = [segment.episode_id for segment in source.segments()]
    except (OSError, ValueError):
        episode_ids = []
    if not episode_ids:
        return view

    from core.step_registry import WEB_PRODUCTION_STEP_IDS

    for step in WEB_PRODUCTION_STEP_IDS:
        statuses = [project.manifest.get(episode_id, step).status for episode_id in episode_ids]
        if any(status == "failed" for status in statuses):
            view[step] = {"status": "failed", "error": "存在失败任务"}
        elif any(status == "running" for status in statuses):
            view[step] = {"status": "running"}
        elif any(status == "review" for status in statuses):
            view[step] = {"status": "review"}
        elif all(status == "completed" for status in statuses):
            view[step] = {"status": "completed"}
        else:
            view[step] = {"status": "pending"}
    return view


def episode_list(project: Project) -> List[Dict[str, Any]]:
    source = ProjectScriptSource(project.project_dir)
    return [
        {
            "episode_id": segment.episode_id,
            "marker": segment.marker,
            "line_range": [segment.start_line, segment.end_line],
            "shot_match_status": project.manifest.get(segment.episode_id, "shot_match").status,
        }
        for segment in source.segments()
    ]


def episode_detail(project: Project, episode_id: str) -> Dict[str, Any]:
    source = ProjectScriptSource(project.project_dir)
    segment = source.segment(episode_id)
    return {
        "episode_id": segment.episode_id,
        "text": segment.text,
        "line_range": [segment.start_line, segment.end_line],
        "artifacts": {
            step: _artifact_summary(project, episode_id, step)
            for step in (
                "import_script", "prompt", "asset", "shot_match",
                "video", "timeline", "preview", "export",
            )
        },
    }


def _artifact_summary(project: Project, episode_id: str, step: str) -> Dict[str, Any]:
    record = project.manifest.get(episode_id, step)
    return {
        "status": record.status,
        "output_path": record.output_path,
        "error": record.error,
        "updated_at": record.updated_at,
        "metadata": dict(record.metadata),
    }


def _episode_status_counts(project: Project) -> Dict[str, int]:
    source = ProjectScriptSource(project.project_dir)
    try:
        episode_ids = [segment.episode_id for segment in source.segments()]
    except (OSError, ValueError):
        episode_ids = []
    counts: Dict[str, int] = {}
    for episode_id in episode_ids:
        status = project.manifest.get(episode_id, "shot_match").status
        counts[status] = counts.get(status, 0) + 1
    return counts


def _state_value(state_file: str, key: str, default: str) -> str:
    try:
        with open(state_file, "r", encoding="utf-8") as handle:
            return str(json.load(handle).get(key, default) or default)
    except (OSError, ValueError):
        return default
