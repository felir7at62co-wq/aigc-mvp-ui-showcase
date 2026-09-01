"""Shared parsing and editing helpers for shot-script text."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ShotParseResult:
    shots: List[str]
    format_name: str
    recognized: bool
    warnings: List[str] = field(default_factory=list)
    shot_numbers: List[int] = field(default_factory=list)
    raw_sections: List[str] = field(default_factory=list)
    spans: List[Tuple[int, int]] = field(default_factory=list, repr=False)


_FORMATS = (
    (
        "N画面描述",
        re.compile(
            r"(?m)^\s*\*\*\s*(\d+)\s*画面描述\s*[：:]?\s*\*\*\s*"
        ),
    ),
    (
        "镜头N",
        re.compile(
            r"(?m)^\s*(?:【|\[)?\s*镜头\s*(\d+)\s*(?:】|\])?\s*[：:;；]?\s*"
        ),
    ),
    (
        "镜头序号",
        re.compile(r"(?m)^\s*镜头序号\s*[：:]\s*(\d+)\s*[：:;；]?\s*"),
    ),
    (
        "编号列表",
        re.compile(r"(?m)^\s*(\d+)\s*[.、]\s+"),
    ),
    (
        "分号编号",
        re.compile(
            r"(?m)^\s*(\d+)\s*(?:镜头序号\s*[：:]\s*\d+\s*)?[；;]\s*"
        ),
    ),
)


def analyze_shots(text: str, delimiter: Optional[str] = None) -> ShotParseResult:
    """Parse shot boundaries and report whether a real format was recognized."""
    source = text or ""
    if not source.strip():
        return ShotParseResult([], "empty", False, ["镜头脚本为空"])

    if delimiter:
        try:
            pattern = re.compile(delimiter, re.M)
            result = _analyze_with_pattern(source, pattern, "自定义分隔符")
            if result.recognized:
                return result
        except re.error as exc:
            logger.warning("自定义镜头分隔符无效: %s", exc)

    for format_name, pattern in _FORMATS:
        result = _analyze_with_pattern(source, pattern, format_name)
        if result.recognized:
            return result

    logger.warning("无法解析镜头脚本格式，兼容接口将全文视为一个镜头")
    return ShotParseResult(
        shots=[source.strip()],
        format_name="unrecognized",
        recognized=False,
        warnings=["未识别到明确的镜头边界"],
        shot_numbers=[1],
        raw_sections=[source.strip()],
        spans=[(0, len(source))],
    )


def parse_shots(text: str, delimiter: Optional[str] = None) -> List[str]:
    """Backward-compatible list-only parser used by generation code."""
    return analyze_shots(text, delimiter).shots


def replace_shot(text: str, sequential_index: int, replacement: str) -> str:
    """Replace one parsed section by its 1-based output index."""
    result = analyze_shots(text)
    if not result.recognized or not 1 <= sequential_index <= len(result.spans):
        raise ValueError(f"找不到镜头 {sequential_index}")
    start, end = result.spans[sequential_index - 1]
    value = replacement.strip()
    if end < len(text) and not value.endswith("\n"):
        value += "\n\n"
    return text[:start] + value + text[end:]


def _analyze_with_pattern(
    text: str, pattern: re.Pattern, format_name: str
) -> ShotParseResult:
    matches = list(pattern.finditer(text))
    if not matches:
        return ShotParseResult([], format_name, False)

    shots: List[str] = []
    numbers: List[int] = []
    raw_sections: List[str] = []
    spans: List[Tuple[int, int]] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end():end].strip()
        if not body:
            continue
        number = _match_number(match, len(shots) + 1)
        shots.append(body)
        numbers.append(number)
        raw_sections.append(text[start:end].strip())
        spans.append((start, end))

    if not shots:
        return ShotParseResult([], format_name, False, ["镜头标题后没有正文"])

    warnings: List[str] = []
    if len(numbers) != len(set(numbers)):
        warnings.append("镜头编号存在重复，将按出现顺序映射为图片 1..N")
    elif numbers != list(range(1, len(numbers) + 1)):
        warnings.append("镜头编号不连续，将按出现顺序映射为图片 1..N")
    preamble = text[:matches[0].start()].strip()
    if preamble:
        warnings.append("首个镜头前存在说明文字，生成时不会作为独立镜头")
    return ShotParseResult(
        shots=shots,
        format_name=format_name,
        recognized=True,
        warnings=warnings,
        shot_numbers=numbers,
        raw_sections=raw_sections,
        spans=spans,
    )


def _match_number(match: re.Match, fallback: int) -> int:
    try:
        return int(match.group(1))
    except (IndexError, TypeError, ValueError):
        return fallback
