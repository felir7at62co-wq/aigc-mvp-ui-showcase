from pathlib import Path

import pytest

from core.asset_context import load_or_build_asset_context
from core.asset_timeline import load_or_build_timeline


PROJECT = Path(r"E:\aigc-mvp-ui11\aigc-mvp-ui\projects\这顿饭我不做东")


@pytest.mark.skipif(not PROJECT.is_dir(), reason="sample project is not available")
def test_sample_project_timeline_and_asset_match():
    timeline = load_or_build_timeline(PROJECT)
    context = load_or_build_asset_context(PROJECT)

    assert len(timeline.events) == 40
    assert len(context["assets"]["character"]) >= 1
    assert len(context["assets"]["scene"]) >= 1
    assert len(context["assets"]["prop"]) >= 1

    character = context["assets"]["character"][0]
    assert character["name"]
    assert isinstance(character.get("episodes", []), list)
