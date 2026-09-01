"""Parse complete shot blocks and group them into Seedance 15-second tasks."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable


@dataclass(frozen=True)
class ShotBlock:
    number: int
    text: str
    duration: float


_HEADING = re.compile(r"(?m)^\s*镜头\s*(\d+)\s*[：:]")
_DURATION = re.compile(r"(?:建议)?时长\s*[：:]?\s*(\d+(?:\.\d+)?)\s*(?:秒|s)\b", re.I)


def parse_shot_blocks(script: str, fallback_duration: float = 5.0) -> list[ShotBlock]:
    source = str(script or "")
    headings = list(_HEADING.finditer(source))
    result: list[ShotBlock] = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(source)
        text = source[heading.start():end].strip()
        duration_match = _DURATION.search(text)
        duration = float(duration_match.group(1)) if duration_match else float(fallback_duration)
        result.append(ShotBlock(int(heading.group(1)), text, max(0.1, min(duration, 15.0))))
    return result


def group_shots(shots: Iterable[ShotBlock], max_duration: float = 15.0) -> list[list[ShotBlock]]:
    batches: list[list[ShotBlock]] = []
    current: list[ShotBlock] = []
    current_duration = 0.0
    for shot in shots:
        if current and current_duration + shot.duration > max_duration + 1e-6:
            batches.append(current)
            current = []
            current_duration = 0.0
        current.append(shot)
        current_duration += shot.duration
    if current:
        batches.append(current)
    return batches


def build_batch_prompt(shots: Iterable[ShotBlock], prefix: str = "") -> str:
    selected = list(shots)
    total = sum(shot.duration for shot in selected)
    parts: list[str] = []
    if str(prefix).strip():
        parts.append(f"全局镜头要求：{str(prefix).strip()}")
    parts.append(
        f"请在一个连续视频中完成以下 {len(selected)} 个镜头，总时长 {total:.1f} 秒。"
        "严格按顺序呈现，按镜头边界自然切镜，保持人物、服装、场景和道具连续一致。"
    )
    parts.extend(shot.text for shot in selected)
    return "\n\n".join(parts)
