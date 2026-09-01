"""Read-only migration view from legacy state.json to Web steps."""

import json
import os

from core.project import Project, WEB_STEPS, migrate_legacy_state


def _write_state(project_dir, steps):
    os.makedirs(project_dir, exist_ok=True)
    with open(os.path.join(project_dir, "state.json"), "w", encoding="utf-8") as handle:
        json.dump({"name": "p", "steps": steps}, handle, ensure_ascii=False)


def test_web_steps_constant_order():
    assert WEB_STEPS == (
        "import_script", "prompt", "asset", "shot_match",
        "video", "timeline", "preview", "export",
    )


def test_migrate_legacy_state_maps_statuses(tmp_path):
    _write_state(tmp_path, {
        "script": {"status": "completed"},
        "prompt": {"status": "completed"},
        "web_video": {"status": "failed", "error": "timeout"},
        "draft": {"status": "completed"},
    })
    view = migrate_legacy_state(str(tmp_path))
    assert view["import_script"]["status"] == "completed"
    assert view["prompt"]["status"] == "completed"
    assert view["video"]["status"] == "failed"
    assert view["video"]["error"] == "timeout"
    assert view["export"]["status"] == "completed"
    assert view["timeline"]["status"] == "pending"
    assert view["preview"]["status"] == "pending"


def test_migrate_legacy_state_keeps_legacy_file_untouched(tmp_path):
    _write_state(tmp_path, {"script": {"status": "completed"}})
    migrate_legacy_state(str(tmp_path))
    with open(os.path.join(tmp_path, "state.json"), "r", encoding="utf-8") as handle:
        data = json.load(handle)
    assert data["steps"]["script"]["status"] == "completed"


def test_migrate_legacy_state_without_state_file(tmp_path):
    view = migrate_legacy_state(str(tmp_path / "missing"))
    assert all(view[step]["status"] == "pending" for step in WEB_STEPS)


def test_project_web_steps_returns_migrated_view(tmp_path):
    _write_state(tmp_path, {"web_video": {"status": "completed"}})
    project = Project(str(tmp_path))
    project._load_state()
    view = project.web_steps()
    assert view["video"]["status"] == "completed"
