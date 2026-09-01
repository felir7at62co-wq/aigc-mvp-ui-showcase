import json

import pytest

from core.project_settings import (
    DEFAULT_PROJECT_SETTINGS,
    load_project_settings,
    save_project_settings,
)


def test_missing_settings_file_returns_fixed_defaults(tmp_path):
    assert load_project_settings(str(tmp_path)) == DEFAULT_PROJECT_SETTINGS


def test_save_settings_keeps_fixed_generation_fields(tmp_path):
    result = save_project_settings(
        str(tmp_path),
        {
            "aspect_ratio": "21:9",
            "resolution": "1080p",
            "prompt_prefix": "  电影质感  ",
            "video_model": "not-allowed",
            "generation_mode": "text-to-video",
            "batch_duration": 5,
        },
    )

    assert result["aspect_ratio"] == "21:9"
    assert result["resolution"] == "1080p"
    assert result["prompt_prefix"] == "电影质感"
    assert result["video_model"] == "seedance-2-0-official"
    assert result["image_model"] == "gpt-image-2-official"
    assert result["generation_mode"] == "reference"
    assert result["batch_duration"] == 15
    assert json.loads((tmp_path / "project_settings.json").read_text("utf-8")) == result


@pytest.mark.parametrize("field,value", [("aspect_ratio", "2:1"), ("resolution", "4k")])
def test_invalid_visible_setting_is_rejected(tmp_path, field, value):
    with pytest.raises(ValueError):
        save_project_settings(str(tmp_path), {field: value})
