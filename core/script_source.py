"""Canonical project screenplay source used for episode splitting and visual production."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass
from typing import List

from agents.script_processor import DEFAULT_FILTER_OPTIONS, ScriptProcessor, read_script


@dataclass(frozen=True)
class SourceSegment:
    episode_id: str
    marker: str
    text: str
    start_line: int
    end_line: int
    source_sha256: str


class ProjectScriptSource:
    """Own and expose the immutable source screenplay for visual production."""

    def __init__(self, project_dir: str):
        self.project_dir = os.path.abspath(project_dir)
        self.source_dir = os.path.join(self.project_dir, "source")
        self.analysis_dir = os.path.join(self.project_dir, "analysis")
        self.normalized_path = os.path.join(self.source_dir, "normalized.txt")
        self.segments_path = os.path.join(self.analysis_dir, "source_segments.json")
        self.segment_dir = os.path.join(self.analysis_dir, "episodes")

    def initialize(self, source_path: str) -> str:
        if not os.path.isfile(source_path):
            raise FileNotFoundError(source_path)
        os.makedirs(self.source_dir, exist_ok=True)
        os.makedirs(self.segment_dir, exist_ok=True)
        extension = os.path.splitext(source_path)[1].lower()
        original_path = os.path.join(self.source_dir, f"original{extension}")
        for filename in os.listdir(self.source_dir):
            old_path = os.path.join(self.source_dir, filename)
            if filename.startswith("original.") and old_path != original_path:
                try:
                    os.remove(old_path)
                except OSError:
                    pass
        if os.path.abspath(source_path) != os.path.abspath(original_path):
            _copy_atomic(source_path, original_path)

        text = read_script(original_path)["text"]
        _write_text_atomic(self.normalized_path, text)
        disabled_filters = {key: False for key in DEFAULT_FILTER_OPTIONS}
        analysis = ScriptProcessor(disabled_filters).analyze(original_path)
        segments = []
        current_files = set()
        for episode in analysis.episodes:
            segment_text = episode.original_content.strip()
            filename = f"{episode.number}.txt"
            current_files.add(filename)
            _write_text_atomic(os.path.join(self.segment_dir, filename), segment_text)
            segments.append(SourceSegment(
                episode_id=episode.number,
                marker=episode.marker,
                text=segment_text,
                start_line=episode.source_start_line,
                end_line=episode.source_start_line + max(0, len(segment_text.splitlines()) - 1),
                source_sha256=_sha256_text(segment_text),
            ))
        for filename in os.listdir(self.segment_dir):
            if filename.endswith(".txt") and filename not in current_files:
                os.remove(os.path.join(self.segment_dir, filename))
        _write_json_atomic(self.segments_path, {
            "version": 1,
            "source_path": original_path,
            "source_sha256": _sha256_text(text),
            "segments": [asdict(item) for item in segments],
        })
        return original_path

    def ensure(self, fallback_path: str = "") -> None:
        if os.path.isfile(self.normalized_path) and os.path.isfile(self.segments_path):
            return
        if fallback_path and os.path.isfile(fallback_path):
            self.initialize(fallback_path)
            return
        legacy_dir = os.path.join(self.project_dir, "episodes")
        legacy_files = (
            sorted(name for name in os.listdir(legacy_dir) if name.endswith(".txt"))
            if os.path.isdir(legacy_dir) else []
        )
        if legacy_files:
            os.makedirs(self.source_dir, exist_ok=True)
            legacy_path = os.path.join(self.source_dir, "original.txt")
            parts = []
            for filename in legacy_files:
                with open(os.path.join(legacy_dir, filename), "r", encoding="utf-8") as handle:
                    parts.append(f"第{os.path.splitext(filename)[0]}集\n{handle.read().strip()}")
            _write_text_atomic(legacy_path, "\n\n".join(parts))
            self.initialize(legacy_path)
            return
        raise FileNotFoundError("项目缺少原始剧本，请重新导入")

    def full_text(self) -> str:
        with open(self.normalized_path, "r", encoding="utf-8") as handle:
            return handle.read()

    def source_hash(self) -> str:
        with open(self.segments_path, "r", encoding="utf-8") as handle:
            return str(json.load(handle).get("source_sha256", ""))

    def segments(self) -> List[SourceSegment]:
        with open(self.segments_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return [SourceSegment(**item) for item in data.get("segments", [])]

    def segment(self, episode_id: str) -> SourceSegment:
        for item in self.segments():
            if item.episode_id == str(episode_id):
                return item
        raise KeyError(f"原始剧本中不存在第{episode_id}集")

    def visual_episodes_dir(self) -> str:
        return self.segment_dir


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _copy_atomic(source: str, destination: str) -> None:
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(destination), suffix=".tmp")
    os.close(fd)
    try:
        shutil.copy2(source, temp_path)
        os.replace(temp_path, destination)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def _write_text_atomic(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False,
                                     dir=os.path.dirname(path), suffix=".tmp") as handle:
        handle.write(text)
        temp_path = handle.name
    os.replace(temp_path, path)


def _write_json_atomic(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False,
                                     dir=os.path.dirname(path), suffix=".tmp") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        temp_path = handle.name
    os.replace(temp_path, path)
