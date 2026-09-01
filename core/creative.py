"""Versioned creative bible, assets, shots, and generation variants."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping


@dataclass
class ProjectBible:
    characters: str = ""
    world: str = ""
    narrative_tone: str = ""
    banned_terms: str = ""
    pronunciations: Dict[str, str] = field(default_factory=dict)
    target_episode_seconds: int = 90


@dataclass
class AssetRecord:
    id: str
    type: str
    version: int = 1
    prompt: str = ""
    references: List[str] = field(default_factory=list)
    status: str = "pending"
    files: List[str] = field(default_factory=list)
    fixed_description: str = ""
    negative_prompt: str = ""


@dataclass
class ShotRecord:
    id: str
    episode_id: str
    duration: float
    characters: List[str] = field(default_factory=list)
    action: str = ""
    camera: str = ""
    dialogue: str = ""
    scene: str = ""
    emotion: str = ""


@dataclass
class GenerationVariant:
    id: str
    parent_id: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    output: str = ""
    review_status: str = "pending"
    replacement_reason: str = ""


class CreativeStore:
    def __init__(self, project_dir: str):
        self.path = os.path.join(project_dir, "creative.json")
        self.data = self._load()

    def _load(self) -> Dict[str, Any]:
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError):
            pass
        return {"version": 1, "bible": {}, "assets": {}, "shots": {}, "variants": {}}

    def bible(self) -> ProjectBible:
        raw = self.data.get("bible", {})
        allowed = ProjectBible.__dataclass_fields__
        return ProjectBible(**{key: value for key, value in raw.items() if key in allowed})

    def save_bible(self, bible: ProjectBible) -> None:
        self.data["bible"] = asdict(bible)
        self.save()

    def put_asset(self, asset: AssetRecord) -> None:
        current = self.data.setdefault("assets", {}).get(asset.id)
        if current and current.get("status") == "completed" and asset.version <= current.get("version", 1):
            raise ValueError("已确认资产必须使用更高版本，不能静默覆盖")
        self.data["assets"][asset.id] = asdict(asset)
        self.save()

    def put_shot(self, shot: ShotRecord) -> List[str]:
        warnings = validate_shot(shot)
        self.data.setdefault("shots", {})[shot.id] = asdict(shot)
        self.save()
        return warnings

    def put_variant(self, variant: GenerationVariant) -> None:
        self.data.setdefault("variants", {})[variant.id] = asdict(variant)
        self.save()

    def save(self) -> None:
        directory = os.path.dirname(self.path)
        os.makedirs(directory, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", delete=False, dir=directory, suffix=".tmp"
        ) as handle:
            json.dump(self.data, handle, ensure_ascii=False, indent=2)
            temp_path = handle.name
        os.replace(temp_path, self.path)


def validate_shot(shot: ShotRecord) -> List[str]:
    warnings: List[str] = []
    if shot.duration <= 0:
        warnings.append("镜头时长必须大于 0")
    if shot.duration > 15:
        warnings.append("单镜时长超过 15 秒")
    if not shot.action and not shot.dialogue:
        warnings.append("镜头缺少动作和台词")
    if not shot.scene:
        warnings.append("镜头未指定场景")
    return warnings
