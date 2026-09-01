"""Reusable synchronous step execution with cancellation and traceable results."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Mapping, Optional, Sequence


@dataclass
class RunSummary:
    success: bool
    completed: int = 0
    failed: int = 0
    cancelled: int = 0
    elapsed_ms: int = 0
    results: Dict[str, Dict[str, Any]] = field(default_factory=dict)


class StepRunner:
    """Run one operation for an exact episode whitelist."""

    def __init__(self, step_id: str, operation: Callable[..., Mapping[str, Any]]):
        self.step_id = step_id
        self.operation = operation
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    def run(
        self,
        project: Any,
        episode_ids: Sequence[str],
        options: Optional[Mapping[str, Any]] = None,
        callbacks: Optional[Mapping[str, Callable[..., None]]] = None,
    ) -> RunSummary:
        started = time.monotonic()
        summary = RunSummary(success=True)
        options = dict(options or {})
        callbacks = dict(callbacks or {})
        ids = list(dict.fromkeys(str(value) for value in episode_ids))
        for index, episode_id in enumerate(ids):
            if self._cancelled.is_set():
                summary.cancelled += len(ids) - index
                summary.success = False
                break
            self._emit(callbacks, "status", episode_id, "running", "")
            project.set_artifact(episode_id, self.step_id, "running")
            try:
                result = dict(self.operation(project, episode_id, options, self._cancelled))
                success = bool(result.get("success", True))
                if success:
                    status = str(result.get("status", "review"))
                    project.set_artifact(
                        episode_id, self.step_id, status,
                        input_hash=str(result.get("input_hash", "")),
                        config_hash=str(result.get("config_hash", "")),
                        output_path=str(result.get("output_path", "")),
                        metadata=dict(result.get("metadata", {})),
                    )
                    summary.completed += 1
                    self._emit(callbacks, "status", episode_id, status, "")
                else:
                    error = str(result.get("error", "执行失败"))
                    project.set_artifact(episode_id, self.step_id, "failed", error=error)
                    summary.failed += 1
                    summary.success = False
                    self._emit(callbacks, "status", episode_id, "failed", error)
                summary.results[episode_id] = result
            except Exception as exc:
                error = str(exc)
                project.set_artifact(episode_id, self.step_id, "failed", error=error)
                summary.results[episode_id] = {"success": False, "error": error}
                summary.failed += 1
                summary.success = False
                self._emit(callbacks, "status", episode_id, "failed", error)
            self._emit(callbacks, "progress", index + 1, len(ids), episode_id)
        summary.elapsed_ms = int((time.monotonic() - started) * 1000)
        return summary

    @staticmethod
    def _emit(callbacks: Mapping[str, Callable[..., None]], name: str, *args: Any) -> None:
        callback = callbacks.get(name)
        if callback:
            callback(*args)
