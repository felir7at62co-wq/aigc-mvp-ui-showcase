"""LLM-backed normalization for arbitrary asset TXT files."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Callable, Iterable, List, Optional


VALID_CATEGORIES = {"character", "scene", "prop"}
CATEGORY_ALIASES = {
    "character": "character",
    "角色": "character",
    "人物": "character",
    "scene": "scene",
    "场景": "scene",
    "prop": "prop",
    "道具": "prop",
    "物品": "prop",
}


@dataclass
class AssetCandidate:
    category: str
    name: str
    aliases: List[str] = field(default_factory=list)
    episode_ids: List[str] = field(default_factory=list)
    prompt: str = ""
    source_excerpt: str = ""
    status: str = "valid"
    issues: List[str] = field(default_factory=list)

    def as_prompt_line(self) -> str:
        aliases = ",".join(_unique(self.aliases))
        episodes = ",".join(_unique(self.episode_ids))
        return f"{self.name.strip()}|{aliases}|{episodes}|{self.prompt.strip()}"


@dataclass
class AssetImportAnalysis:
    source_sha256: str
    candidates: List[AssetCandidate]
    warnings: List[str] = field(default_factory=list)


class AssetTxtAnalysisError(ValueError):
    """Raised when an imported TXT cannot be normalized safely."""


class AssetTxtAnalyzer:
    """Use the configured LLM to normalize arbitrary asset descriptions."""

    SYSTEM_PROMPT = (
        "你是影视资产资料整理员。用户会提供格式不固定的TXT，可能是表格、列表、"
        "Markdown、自然语言或混合格式。请只整理文本中明确存在的角色、场景和道具，"
        "不要补写文本没有提到的资产。必须返回JSON对象，不要返回Markdown。"
    )

    def __init__(self, llm_client, context_window: int = 32000):
        self.llm_client = llm_client
        available_tokens = max(3000, int(context_window or 32000) - 3000)
        self.max_chunk_chars = min(24000, max(4000, int(available_tokens / 1.5)))

    def analyze(
        self,
        text: str,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> AssetImportAnalysis:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        if not normalized.strip():
            raise AssetTxtAnalysisError("TXT 文件为空")

        candidates: List[AssetCandidate] = []
        warnings: List[str] = []
        chunks = list(_line_chunks(normalized, self.max_chunk_chars))
        for index, chunk in enumerate(chunks, 1):
            if is_cancelled and is_cancelled():
                raise AssetTxtAnalysisError("用户取消")
            messages = [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": self._build_instruction(chunk, index, len(chunks)),
                },
            ]
            try:
                response = self.llm_client.generate(
                    messages, temperature=0, use_cache=False
                )
                payload = _load_json_payload(response)
                raw_candidates = payload.get("candidates", [])
                if not isinstance(raw_candidates, list):
                    raise AssetTxtAnalysisError("AI 返回的 candidates 不是列表")
                for raw in raw_candidates:
                    if isinstance(raw, dict):
                        candidates.append(_candidate_from_dict(raw, normalized))
                for warning in payload.get("warnings", []):
                    if str(warning).strip():
                        warnings.append(str(warning).strip())
            except AssetTxtAnalysisError:
                raise
            except Exception as exc:
                raise AssetTxtAnalysisError(f"AI 识别失败: {exc}") from exc

        merged = _merge_candidates(candidates, normalized)
        if not merged:
            raise AssetTxtAnalysisError("AI 未识别出任何角色、场景或道具")
        if len(chunks) > 1:
            warnings.append(f"长文本已分为 {len(chunks)} 段识别并合并去重")
        return AssetImportAnalysis(
            source_sha256=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
            candidates=merged,
            warnings=_unique(warnings),
        )

    @staticmethod
    def _build_instruction(chunk: str, index: int, total: int) -> str:
        return f"""这是第 {index}/{total} 段资产资料：

---资料开始---
{chunk}
---资料结束---

请输出以下JSON结构：
{{
  "candidates": [
    {{
      "category": "character|scene|prop",
      "name": "资产名称",
      "aliases": ["别名"],
      "episode_ids": ["01"],
      "prompt": "可直接用于生图的详细提示词",
      "source_excerpt": "能在原资料中找到的短原文"
    }}
  ],
  "warnings": []
}}

规则：
1. category只能是character、scene或prop。
2. 不确定类别或名称时仍可列出，但必须在warnings说明。
3. source_excerpt必须尽量原样摘录，禁止虚构来源。
4. 不要因为格式不统一而漏掉明确列出的资产。
5. 不要输出剧情总结或JSON以外的文字。"""


def read_asset_txt(path: str) -> str:
    last_error = None
    for encoding in ("utf-8-sig", "gbk"):
        try:
            with open(path, "r", encoding=encoding) as handle:
                return handle.read()
        except UnicodeDecodeError as exc:
            last_error = exc
    raise AssetTxtAnalysisError(f"无法识别 TXT 编码: {last_error}")


def parse_existing_prompt_text(text: str, category: str) -> List[AssetCandidate]:
    result: List[AssetCandidate] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "|" not in line:
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) < 2 or not parts[0]:
            continue
        prompt = parts[-1]
        aliases = _split_values(parts[1]) if len(parts) >= 3 else []
        episodes = _split_values(parts[2]) if len(parts) >= 4 else []
        result.append(AssetCandidate(
            category=category,
            name=parts[0],
            aliases=aliases,
            episode_ids=episodes,
            prompt=prompt,
            source_excerpt="现有候选",
        ))
    return result


def normalize_asset_name(name: str) -> str:
    return re.sub(r"[\s\-_·•,，。:：'\"“”‘’()（）【】\[\]]+", "", name).lower()


def _candidate_from_dict(raw: dict, source_text: str) -> AssetCandidate:
    category_raw = str(raw.get("category", "")).strip().lower()
    category = CATEGORY_ALIASES.get(category_raw, category_raw)
    candidate = AssetCandidate(
        category=category,
        name=str(raw.get("name", "")).strip(),
        aliases=_as_list(raw.get("aliases", [])),
        episode_ids=_normalize_episodes(_as_list(raw.get("episode_ids", []))),
        prompt=str(raw.get("prompt", "")).strip(),
        source_excerpt=str(raw.get("source_excerpt", "")).strip(),
    )
    _validate_candidate(candidate, source_text)
    return candidate


def _validate_candidate(candidate: AssetCandidate, source_text: str) -> None:
    issues: List[str] = []
    invalid = False
    if candidate.category not in VALID_CATEGORIES:
        issues.append("类别不是角色、场景或道具")
        invalid = True
    if not candidate.name:
        issues.append("名称为空")
        invalid = True
    if not candidate.prompt:
        issues.append("提示词为空")
        invalid = True
    elif len(candidate.prompt) < 10:
        issues.append("提示词过短")
        invalid = True
    elif len(candidate.prompt) < 24:
        issues.append("提示词信息较少")
    if not candidate.source_excerpt:
        issues.append("缺少来源摘录")
    elif candidate.source_excerpt not in source_text:
        issues.append("来源摘录无法在原文中精确定位")
    candidate.issues = issues
    candidate.status = "invalid" if invalid else ("suspect" if issues else "valid")


def _merge_candidates(
    candidates: Iterable[AssetCandidate], source_text: str
) -> List[AssetCandidate]:
    merged: dict[tuple[str, str], AssetCandidate] = {}
    unnamed_index = 0
    for candidate in candidates:
        normalized_name = normalize_asset_name(candidate.name)
        if not normalized_name:
            unnamed_index += 1
            normalized_name = f"__unnamed_{unnamed_index}"
        key = (candidate.category, normalized_name)
        current = merged.get(key)
        if current is None:
            merged[key] = candidate
            continue
        current.aliases = _unique(current.aliases + candidate.aliases)
        current.episode_ids = _unique(current.episode_ids + candidate.episode_ids)
        if len(candidate.prompt) > len(current.prompt):
            current.prompt = candidate.prompt
        if not current.source_excerpt and candidate.source_excerpt:
            current.source_excerpt = candidate.source_excerpt
        _validate_candidate(current, source_text)
    return list(merged.values())


def _load_json_payload(response: str) -> dict:
    text = (response or "").strip()
    if not text:
        raise AssetTxtAnalysisError("AI 返回为空")
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S | re.I)
    if fenced:
        text = fenced.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start:end + 1]
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AssetTxtAnalysisError(f"AI 返回的 JSON 无法解析: {exc}") from exc
    if not isinstance(payload, dict):
        raise AssetTxtAnalysisError("AI 返回的根节点不是对象")
    return payload


def _line_chunks(text: str, max_chars: int) -> Iterable[str]:
    current: List[str] = []
    length = 0
    for line in text.splitlines(keepends=True):
        if current and length + len(line) > max_chars:
            yield "".join(current)
            current = []
            length = 0
        if len(line) > max_chars:
            if current:
                yield "".join(current)
                current = []
                length = 0
            for offset in range(0, len(line), max_chars):
                yield line[offset:offset + max_chars]
            continue
        current.append(line)
        length += len(line)
    if current:
        yield "".join(current)


def _as_list(value) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    return _split_values(str(value))


def _split_values(value: str) -> List[str]:
    return [part.strip() for part in re.split(r"[,，、;/；]+", value) if part.strip()]


def _normalize_episodes(values: List[str]) -> List[str]:
    result = []
    for value in values:
        match = re.search(r"\d+", value)
        if match:
            result.append(match.group(0).zfill(2))
        elif value:
            result.append(value)
    return _unique(result)


def _unique(values: Iterable[str]) -> List[str]:
    result = []
    seen = set()
    for value in values:
        item = str(value).strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result
