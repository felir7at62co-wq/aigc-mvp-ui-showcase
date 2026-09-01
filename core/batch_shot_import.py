"""Batch shot-script import with previewable decisions and transactional apply."""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Iterable, List, Mapping, Optional

from agents.asset_txt_analyzer import read_asset_txt
from agents.shot_parser import ShotParseResult, analyze_shots
from core.script_source import ProjectScriptSource


VALID_ACTIONS = {"import", "replace", "skip"}


@dataclass
class BatchImportItem:
    item_id: str
    source_path: str
    file_name: str
    detected_number: Optional[int] = None
    target_episode: str = ""
    text: str = ""
    source_sha256: str = ""
    existing_text: str = ""
    existing_sha256: str = ""
    shot_count: int = 0
    format_name: str = ""
    warnings: List[str] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)
    status: str = "invalid"  # valid / invalid / collision
    default_action: str = "skip"

    @property
    def can_apply(self) -> bool:
        return self.status in {"valid", "collision"} and not self.issues


@dataclass
class BatchImportAnalysis:
    project_dir: str
    created_at: str
    items: List[BatchImportItem]

    @property
    def valid_count(self) -> int:
        return sum(1 for item in self.items if item.can_apply)


@dataclass
class BatchImportResult:
    success: bool
    imported_episodes: List[str] = field(default_factory=list)
    skipped_count: int = 0
    error: str = ""


class BatchShotImporter:
    """Analyze numeric TXT names and atomically publish confirmed shot scripts."""

    def analyze(self, project, paths: Iterable[str]) -> BatchImportAnalysis:
        project_dir = _project_dir(project)
        source = ProjectScriptSource(project_dir)
        source.ensure()
        episode_map: Dict[int, List[str]] = {}
        for filename in os.listdir(source.visual_episodes_dir()):
            stem, extension = os.path.splitext(filename)
            if extension.lower() == ".txt" and stem.isdigit():
                episode_map.setdefault(int(stem), []).append(stem)

        items: List[BatchImportItem] = []
        for index, path in enumerate(_expand_paths(paths)):
            items.append(self._analyze_file(project_dir, path, episode_map, index))

        by_episode: Dict[str, List[BatchImportItem]] = {}
        for item in items:
            if item.target_episode and item.status == "valid":
                by_episode.setdefault(item.target_episode, []).append(item)
        for duplicates in by_episode.values():
            if len(duplicates) > 1:
                for item in duplicates:
                    item.status = "collision"
                    item.warnings.append("多个文件映射到同一项目集数，请只选择其中一个")

        return BatchImportAnalysis(
            project_dir=project_dir,
            created_at=datetime.now().isoformat(timespec="seconds"),
            items=items,
        )

    def apply(
        self,
        project,
        analysis: BatchImportAnalysis,
        decisions: Mapping[str, str],
    ) -> BatchImportResult:
        project_dir = _project_dir(project)
        if os.path.abspath(project_dir) != os.path.abspath(analysis.project_dir):
            raise ValueError("导入分析不属于当前项目")

        selected: List[BatchImportItem] = []
        skipped = 0
        targets = set()
        for item in analysis.items:
            action = str(decisions.get(item.item_id, item.default_action))
            if action not in VALID_ACTIONS:
                raise ValueError(f"无效导入动作: {action}")
            if action == "skip":
                skipped += 1
                continue
            if not item.can_apply:
                raise ValueError(f"{item.file_name} 无法导入: {'；'.join(item.issues)}")
            if item.target_episode in targets:
                raise ValueError(f"多个文件同时写入第{item.target_episode}集")
            targets.add(item.target_episode)
            if item.existing_text and action != "replace":
                raise ValueError(f"第{item.target_episode}集已存在，必须明确选择替换")
            selected.append(item)

        if not selected:
            return BatchImportResult(True, skipped_count=skipped)

        prompts_dir = os.path.join(project_dir, "prompts")
        os.makedirs(prompts_dir, exist_ok=True)
        watched_paths = [
            os.path.join(prompts_dir, f"{item.target_episode}.txt") for item in selected
        ] + [
            os.path.join(project_dir, "manifest.json"),
            os.path.join(project_dir, "state.json"),
        ]
        snapshots = {path: _read_bytes(path) for path in watched_paths}

        try:
            for item in selected:
                target = os.path.join(prompts_dir, f"{item.target_episode}.txt")
                current_hash = _sha256_bytes(_read_bytes(target) or b"")
                if current_hash != item.existing_sha256:
                    raise ValueError(
                        f"第{item.target_episode}集镜头脚本在预览后已变化，请重新分析"
                    )
            for item in selected:
                target = os.path.join(prompts_dir, f"{item.target_episode}.txt")
                _write_text_atomic(target, item.text)

            from core.project import Project

            project_model = Project.load(project_dir)
            for item in selected:
                target = os.path.join(prompts_dir, f"{item.target_episode}.txt")
                project_model.mark_stale(item.target_episode, "prompt")
                project_model.set_artifact(
                    item.target_episode,
                    "prompt",
                    "completed",
                    input_hash=item.source_sha256,
                    output_path=os.path.relpath(target, project_dir),
                    metadata={
                        "source": "batch_imported_txt",
                        "source_file": item.file_name,
                        "shot_count": item.shot_count,
                        "format": item.format_name,
                    },
                )
        except Exception as exc:
            for path, content in snapshots.items():
                _restore_bytes(path, content)
            return BatchImportResult(False, skipped_count=skipped, error=str(exc))

        return BatchImportResult(
            True,
            imported_episodes=[item.target_episode for item in selected],
            skipped_count=skipped,
        )

    @staticmethod
    def _analyze_file(
        project_dir: str,
        path: str,
        episode_map: Mapping[int, List[str]],
        index: int,
    ) -> BatchImportItem:
        absolute = os.path.abspath(path)
        filename = os.path.basename(absolute)
        item = BatchImportItem(
            item_id=f"{index}:{absolute}",
            source_path=absolute,
            file_name=filename,
        )
        stem, extension = os.path.splitext(filename)
        if extension.lower() != ".txt" or not stem.isdigit():
            item.issues.append("文件名必须是纯数字 TXT，例如 1.txt 或 01.txt")
            return item
        item.detected_number = int(stem)
        matches = episode_map.get(item.detected_number, [])
        if not matches:
            item.issues.append("项目中不存在对应集数")
            return item
        if len(matches) > 1:
            item.issues.append("项目内存在多个等价集号，无法确定目标")
            return item
        item.target_episode = matches[0]
        try:
            item.text = read_asset_txt(absolute)
        except (OSError, UnicodeError, ValueError) as exc:
            item.issues.append(str(exc))
            return item
        item.source_sha256 = _sha256_text(item.text)
        parsed: ShotParseResult = analyze_shots(item.text)
        item.shot_count = len(parsed.shots)
        item.format_name = parsed.format_name
        item.warnings.extend(parsed.warnings)
        if not parsed.recognized or item.shot_count < 2:
            item.issues.append("必须至少包含两个可识别镜头")
            return item
        target = os.path.join(project_dir, "prompts", f"{item.target_episode}.txt")
        if os.path.isfile(target):
            with open(target, "r", encoding="utf-8") as handle:
                item.existing_text = handle.read()
        item.existing_sha256 = _sha256_text(item.existing_text)
        item.default_action = "skip" if item.existing_text else "import"
        item.status = "valid"
        return item


def _project_dir(project) -> str:
    value = getattr(project, "project_dir", project)
    if not value:
        raise ValueError("未选择项目")
    return os.path.abspath(str(value))


def _expand_paths(paths: Iterable[str]) -> List[str]:
    expanded: List[str] = []
    seen = set()
    for raw in paths:
        path = os.path.abspath(str(raw))
        candidates = (
            [os.path.join(path, name) for name in sorted(os.listdir(path))]
            if os.path.isdir(path) else [path]
        )
        for candidate in candidates:
            if candidate not in seen and os.path.isfile(candidate):
                seen.add(candidate)
                expanded.append(candidate)
    return expanded


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _read_bytes(path: str) -> Optional[bytes]:
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except FileNotFoundError:
        return None


def _write_text_atomic(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", delete=False, dir=os.path.dirname(path), suffix=".tmp"
    ) as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
        temp_path = handle.name
    os.replace(temp_path, path)


def _restore_bytes(path: str, content: Optional[bytes]) -> None:
    if content is None:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "wb", delete=False, dir=os.path.dirname(path), suffix=".restore"
    ) as handle:
        handle.write(content)
        temp_path = handle.name
    os.replace(temp_path, path)
