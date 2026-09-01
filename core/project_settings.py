"""Safe project-level media preferences; credentials are environment-only."""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any, Mapping


ASPECT_RATIOS = ("16:9", "9:16", "1:1", "4:3", "3:4", "21:9")
RESOLUTIONS = ("480p", "720p", "1080p")

DEFAULT_PROJECT_SETTINGS: dict[str, Any] = {
    "video_model": "seedance-2-0-official",
    "image_model": "gpt-image-2-official",
    "generation_mode": "reference",
    "aspect_ratio": "9:16",
    "resolution": "720p",
    "batch_duration": 15,
    "prompt_prefix": "",
}


def _settings_path(project_dir: str) -> str:
    return os.path.join(os.path.abspath(project_dir), "project_settings.json")


def _validated_visible_values(values: Mapping[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    if "aspect_ratio" in values:
        ratio = str(values["aspect_ratio"]).strip()
        if ratio not in ASPECT_RATIOS:
            raise ValueError(f"不支持的视频尺寸: {ratio}")
        result["aspect_ratio"] = ratio
    if "resolution" in values:
        resolution = str(values["resolution"]).strip()
        if resolution not in RESOLUTIONS:
            raise ValueError(f"不支持的清晰度: {resolution}")
        result["resolution"] = resolution
    if "prompt_prefix" in values:
        result["prompt_prefix"] = str(values["prompt_prefix"]).strip()
    return result


def load_project_settings(project_dir: str) -> dict[str, Any]:
    settings = dict(DEFAULT_PROJECT_SETTINGS)
    try:
        with open(_settings_path(project_dir), "r", encoding="utf-8") as handle:
            stored = json.load(handle)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return settings
    if isinstance(stored, dict):
        try:
            settings.update(_validated_visible_values(stored))
        except ValueError:
            pass
    return settings


def save_project_settings(project_dir: str, values: Mapping[str, Any]) -> dict[str, Any]:
    settings = load_project_settings(project_dir)
    settings.update(_validated_visible_values(values))
    for key in ("video_model", "image_model", "generation_mode", "batch_duration"):
        settings[key] = DEFAULT_PROJECT_SETTINGS[key]

    os.makedirs(project_dir, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", delete=False, dir=project_dir, suffix=".tmp"
    ) as handle:
        json.dump(settings, handle, ensure_ascii=False, indent=2)
        temporary = handle.name
    os.replace(temporary, _settings_path(project_dir))
    return settings
