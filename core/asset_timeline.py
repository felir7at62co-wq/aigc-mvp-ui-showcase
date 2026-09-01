"""Cached, lightweight screenplay timeline used by asset matching."""
from __future__ import annotations
import hashlib, json, re
from pathlib import Path
from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class TimelineEvent:
    episode: str
    text: str
    keywords: tuple[str, ...]

@dataclass(frozen=True)
class AssetTimeline:
    source_hash: str
    events: tuple[TimelineEvent, ...]
    def candidates(self, label: str) -> list[TimelineEvent]:
        terms = {x for x in re.split(r"[_\-—－\s]+", str(label or "")) if len(x) >= 2}
        if not terms: return list(self.events)
        return [event for event in self.events if any(term in event.text for term in terms)] or list(self.events)
    def as_dict(self): return {"source_hash": self.source_hash, "events":[asdict(x) for x in self.events]}

def build_timeline(project_dir: str) -> AssetTimeline:
    root=Path(project_dir); source=root/"source"/"normalized.txt"
    text=source.read_text(encoding="utf-8-sig") if source.is_file() else ""
    digest=hashlib.sha256(text.encode("utf-8")).hexdigest()
    events=[]
    chunks=re.split(r"(?=第\s*\d+\s*集)", text)
    for chunk in chunks:
        match=re.search(r"第\s*(\d+)\s*集", chunk)
        if not match: continue
        body=chunk.strip(); keywords=tuple(sorted(set(re.findall(r"[\u4e00-\u9fff]{2,6}", body))))
        events.append(TimelineEvent(f"{int(match.group(1)):02d}", body, keywords))
    return AssetTimeline(digest, tuple(events))

def load_or_build_timeline(project_dir: str, refresh: bool=False) -> AssetTimeline:
    path=Path(project_dir)/"assets"/"asset_timeline.json"
    current=build_timeline(project_dir)
    if not refresh and path.is_file():
        try:
            data=json.loads(path.read_text(encoding="utf-8"))
            if data.get("source_hash")==current.source_hash:
                return AssetTimeline(current.source_hash, tuple(TimelineEvent(**x) for x in data.get("events", [])))
        except (OSError, ValueError, TypeError): pass
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(current.as_dict(),ensure_ascii=False,indent=2),encoding="utf-8")
    return current
