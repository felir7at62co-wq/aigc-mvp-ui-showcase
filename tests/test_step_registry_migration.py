"""新 Web 生产步骤语义：import_script/prompt/asset/shot_match/video/timeline/preview/export。"""
from core.step_registry import (
    WEB_PRODUCTION_STEP_IDS,
    WEB_STEP_DEFINITIONS,
    downstream_steps,
)


def test_web_step_ids_exact_order():
    assert WEB_PRODUCTION_STEP_IDS == (
        "import_script", "prompt", "asset", "shot_match",
        "video", "timeline", "preview", "export",
    )


def test_web_steps_exactly_match_current_visual_pipeline():
    ids = {step.id for step in WEB_STEP_DEFINITIONS}
    assert ids == {
        "import_script", "prompt", "asset", "shot_match", "video",
        "timeline", "preview", "export", "settings",
    }


def test_web_dependencies_follow_the_integrated_video_pipeline():
    by_id = {step.id: step for step in WEB_STEP_DEFINITIONS}
    assert by_id["import_script"].dependencies == ()
    assert by_id["prompt"].dependencies == ("import_script",)
    assert by_id["asset"].dependencies == ("import_script",)
    assert by_id["shot_match"].dependencies == ("prompt", "asset")
    assert by_id["video"].dependencies == ("shot_match",)
    assert by_id["timeline"].dependencies == ("video",)
    assert by_id["preview"].dependencies == ("timeline",)
    assert by_id["export"].dependencies == ("timeline",)


def test_downstream_steps_uses_web_registry():
    affected = downstream_steps("import_script", WEB_STEP_DEFINITIONS)
    assert "import_script" in affected
    assert "prompt" in affected
    assert "asset" in affected
    assert "shot_match" in affected
    assert "video" in affected
    assert "timeline" in affected
    assert "preview" in affected
    assert "export" in affected
