"""Deterministic per-episode asset bindings for shot scripts.

The manifest is deliberately small: it records the formal asset names selected
for each shot. Image availability is resolved by direct video generation;
missing images remain text-only instead of falling back to another scene image.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable


def _norm(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip()).lower()


def _episodes(record: dict[str, Any]) -> set[str]:
    return {str(v).zfill(2) for v in record.get("episodes", []) if str(v).strip()}


def _resolve(token: str, records: Iterable[dict[str, Any]], episode: str) -> str | None:
    token = str(token or "").strip()
    if not token or token == "无":
        return None
    # The editor stores an explicit binding as 原文@正式资产名.  The right
    # side is authoritative and avoids ambiguous alias matching during render.
    if "@" in token:
        explicit = token.rsplit("@", 1)[1].strip()
        if explicit:
            token = explicit
    scoped = [r for r in records if not _episodes(r) or episode in _episodes(r)]
    exact = [r for r in scoped if str(r.get("name", "")).strip() == token]
    if len(exact) == 1:
        variant = _preferred_scoped_variant(token, exact[0], scoped)
        if variant:
            return variant
        return exact[0]["name"]
    norm_token = _norm(token)
    aliases = []
    for record in scoped:
        for alias in record.get("strong_aliases", record.get("aliases", [])) or []:
            if _norm(alias) == norm_token:
                aliases.append(record)
    return aliases[0].get("name") if len(aliases) == 1 else None


def _preferred_scoped_variant(
    token: str,
    exact_record: dict[str, Any],
    scoped_records: Iterable[dict[str, Any]],
) -> str | None:
    """Prefer episode-scoped costume/stage variants over the base role card.

    A shot script may naturally write 出镜人物【江蓁】, while the asset library
    contains an episode-specific independent card like 江蓁寿宴服装 with alias
    江蓁. In that case video generation should use the scoped variant image.
    """
    norm_token = _norm(token)
    variant_words = ("服装", "造型", "礼服", "套装", "常服", "制服", "寿宴", "包厢")
    candidates: list[dict[str, Any]] = []
    for record in scoped_records:
        if record is exact_record:
            continue
        name = str(record.get("name", "")).strip()
        aliases = [str(v).strip() for v in record.get("strong_aliases", record.get("aliases", [])) or []]
        searchable = [name, *aliases]
        if not any(_norm(v) == norm_token for v in aliases) and not name.startswith(token):
            continue
        if not any(word in v for v in searchable for word in variant_words):
            continue
        candidates.append(record)
    return candidates[0].get("name") if len(candidates) == 1 else None


def build_match_manifest(
    shot_script: str,
    episode: str,
    asset_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve all script references once and return a JSON-serializable manifest."""
    context = asset_context or {}
    assets = context.get("assets", {}) if isinstance(context, dict) else {}
    characters = list(assets.get("character", []) or [])
    scenes = list(assets.get("scene", []) or [])
    props = list(assets.get("prop", []) or [])
    ep = str(episode).zfill(2)
    shots: list[dict[str, Any]] = []
    blocks = re.split(r"(?=镜头\s*\d+\s*[：:])", str(shot_script or ""))
    for block in blocks:
        number = re.search(r"镜头\s*(\d+)", block)
        if not number:
            continue
        chars_match = re.search(r"出镜人物【([^】]*)】", block)
        scene_match = re.search(r"核心场景[：:]\s*([^\n\r]+)", block)
        props_match = re.search(r"关键道具【([^】]*)】", block)
        char_tokens = [] if not chars_match else [v.strip() for v in re.split(r"[、,，]+", chars_match.group(1)) if v.strip()]
        prop_tokens = [] if not props_match else [v.strip() for v in re.split(r"[、,，]+", props_match.group(1)) if v.strip()]
        scene_token = scene_match.group(1).strip() if scene_match else ""
        shots.append({
            "shot": int(number.group(1)),
            "characters": [
                {"input": token, "name": _resolve(token, characters, ep), "matched": bool(_resolve(token, characters, ep))}
                for token in char_tokens if token != "无"
            ],
            "scene": {
                "input": scene_token,
                "name": _resolve(scene_token, scenes, ep),
                "matched": bool(_resolve(scene_token, scenes, ep)),
            },
            "props": [
                {"input": token, "name": _resolve(token, props, ep), "matched": bool(_resolve(token, props, ep))}
                for token in prop_tokens if token != "无"
            ],
        })
    return {"version": 1, "episode": ep, "shots": shots}


def save_match_manifest(project_dir: str, episode: str, manifest: dict[str, Any]) -> str:
    path = Path(project_dir) / "matches" / f"{int(str(episode)):02d}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def load_match_manifest(project_dir: str, episode: str) -> dict[str, Any] | None:
    path = Path(project_dir) / "matches" / f"{int(str(episode)):02d}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("episode") == f"{int(str(episode)):02d}" else None


def delete_match_manifest(project_dir: str, episode: str) -> bool:
    path = Path(project_dir) / "matches" / f"{int(str(episode)):02d}.json"
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def prune_orphan_match_manifests(project_dir: str) -> int:
    """Delete match manifests whose prompts/{episode}.txt no longer exists."""
    matches_dir = Path(project_dir) / "matches"
    prompts_dir = Path(project_dir) / "prompts"
    if not matches_dir.is_dir():
        return 0
    removed = 0
    for path in matches_dir.glob("*.json"):
        if not path.stem.isdigit():
            continue
        prompt_path = prompts_dir / f"{int(path.stem):02d}.txt"
        if prompt_path.is_file():
            continue
        try:
            path.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def manifest_names(manifest: dict[str, Any], start: int = 0, end: int | None = None) -> tuple[set[str], set[str], set[str]]:
    shots = list(manifest.get("shots", []) or [])[start:end]
    chars: set[str] = set()
    scenes: set[str] = set()
    props: set[str] = set()
    for shot in shots:
        chars.update(v["name"] for v in shot.get("characters", []) if v.get("name"))
        scene = shot.get("scene", {})
        if scene.get("name"):
            scenes.add(scene["name"])
        props.update(v["name"] for v in shot.get("props", []) if v.get("name"))
    return chars, scenes, props
