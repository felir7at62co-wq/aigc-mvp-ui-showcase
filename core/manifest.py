"""Atomic, backward-compatible project artifact manifest."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional

from core.step_registry import downstream_steps


VALID_STATUSES = {
    "pending", "queued", "running", "validating", "review",
    "completed", "failed", "cancelled", "stale",
}


@dataclass
class ArtifactRecord:
    status: str = "pending"
    input_hash: str = ""
    config_hash: str = ""
    output_path: str = ""
    error: str = ""
    updated_at: str = ""
    duration_ms: int = 0
    retries: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ArtifactRecord":
        values = {key: data.get(key, default) for key, default in {
            "status": "pending", "input_hash": "", "config_hash": "",
            "output_path": "", "error": "", "updated_at": "",
            "duration_ms": 0, "retries": 0, "metadata": {},
        }.items()}
        if values["status"] not in VALID_STATUSES:
            values["status"] = "pending"
        return cls(**values)


class ProjectManifest:
    VERSION = 1

    def __init__(self, project_dir: str):
        self.project_dir = os.path.abspath(project_dir)
        self.path = os.path.join(self.project_dir, "manifest.json")
        self.data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                data.setdefault("version", self.VERSION)
                data.setdefault("episodes", {})
                data.setdefault("steps", {})
                return data
        except (OSError, json.JSONDecodeError):
            pass
        return {"version": self.VERSION, "created_at": _now(), "episodes": {}, "steps": {}}

    def save(self) -> None:
        self.data["updated_at"] = _now()
        os.makedirs(self.project_dir, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", delete=False, dir=self.project_dir, suffix=".tmp"
        ) as handle:
            json.dump(self.data, handle, ensure_ascii=False, indent=2)
            temp_path = handle.name
        os.replace(temp_path, self.path)

    def get(self, episode_id: str, step_id: str) -> ArtifactRecord:
        raw = self.data.get("episodes", {}).get(str(episode_id), {}).get(step_id, {})
        return ArtifactRecord.from_dict(raw)

    def set(self, episode_id: str, step_id: str, record: ArtifactRecord) -> None:
        if record.status not in VALID_STATUSES:
            raise ValueError(f"无效产物状态: {record.status}")
        record.updated_at = _now()
        episodes = self.data.setdefault("episodes", {})
        episodes.setdefault(str(episode_id), {})[step_id] = asdict(record)

    def set_step(self, step_id: str, status: str, **metadata: Any) -> None:
        if status not in VALID_STATUSES:
            raise ValueError(f"无效步骤状态: {status}")
        self.data.setdefault("steps", {})[step_id] = {
            "status": status, "updated_at": _now(), **metadata,
        }

    def mark_stale(self, episode_id: str, from_step: str) -> List[str]:
        from core.step_registry import WEB_STEP_BY_ID, WEB_STEP_DEFINITIONS, downstream_steps

        if from_step in WEB_STEP_BY_ID:
            definitions = WEB_STEP_DEFINITIONS
        else:
            definitions = None
        changed: List[str] = []
        for step_id in (
            downstream_steps(from_step, definitions)
            if definitions else downstream_steps(from_step)
        ):
            record = self.get(episode_id, step_id)
            if record.status != "pending" or record.input_hash or record.output_path:
                record.status = "stale"
                record.error = "输入或配置已变化"
                self.set(episode_id, step_id, record)
                changed.append(step_id)
        return changed

    def sync_episode_hashes(self, hashes: Mapping[str, str]) -> Dict[str, List[str]]:
        stale: Dict[str, List[str]] = {}
        episodes = self.data.setdefault("episodes", {})
        for episode_id, digest in hashes.items():
            current = self.get(episode_id, "script")
            if current.input_hash and current.input_hash != digest:
                stale[episode_id] = self._mark_visual_stale(episode_id)
            self.set(episode_id, "script", ArtifactRecord(
                status="completed", input_hash=digest,
                output_path=os.path.join("episodes", f"{episode_id}.txt"),
            ))
        for removed in set(episodes) - set(hashes):
            stale[removed] = self._mark_visual_stale(removed)
        return stale

    def _mark_visual_stale(self, episode_id: str) -> List[str]:
        changed = [
            *self.mark_stale(episode_id, "prompt"),
            *self.mark_stale(episode_id, "asset"),
        ]
        return list(dict.fromkeys(changed))


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
