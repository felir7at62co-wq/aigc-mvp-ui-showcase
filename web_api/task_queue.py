"""进程内任务队列：线程池执行 StepRunner 契约操作。

任务状态在内存（易失），产物状态持久在项目 manifest.json。
取消：queue.cancel() 置位 cancel_event 并调用 StepRunner.cancel()，
操作通过 cancelled.is_set() 协作式中断。
"""
from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from core.step_runner import StepRunner

Operation = Callable[..., Dict[str, Any]]


@dataclass
class TaskRecord:
    id: str
    project_dir: str
    step: str
    episode_ids: List[str]
    status: str = "queued"          # queued | running | completed | failed | cancelled
    created_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    error: str = ""
    results: Dict[str, str] = field(default_factory=dict)   # episode_id -> output_path
    failures: Dict[str, str] = field(default_factory=dict)  # episode_id -> error
    cancel_event: threading.Event = field(default_factory=threading.Event)
    runner: Any = None              # 运行时绑定的 StepRunner（用于真正中断）


class TaskQueue:
    def __init__(self, max_workers: int = 3):
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._records: Dict[str, TaskRecord] = {}
        self._lock = threading.Lock()

    def submit(
        self,
        project_dir: str,
        step: str,
        episode_ids: List[str],
        options: Dict[str, Any],
        operation: Operation,
    ) -> str:
        task_id = uuid.uuid4().hex[:12]
        record = TaskRecord(id=task_id, project_dir=project_dir, step=step,
                            episode_ids=list(episode_ids))
        with self._lock:
            self._records[task_id] = record
        self._executor.submit(self._run, record, operation, options)
        return task_id

    def _run(self, record: TaskRecord, operation: Operation, options: Dict[str, Any]):
        from core.project import Project
        record.status = "running"
        runner: Optional[StepRunner] = None
        try:
            project = Project.load(record.project_dir)
            runner = StepRunner(record.step, operation)
            with self._lock:
                record.runner = runner
            summary = runner.run(
                project,
                record.episode_ids,
                options,
                callbacks={"status": lambda ep, status, error: None},
            )
            record.finished_at = time.time()
            if summary.cancelled or record.status == "cancelled":
                record.status = "cancelled"
                record.error = "已取消"
            elif summary.success:
                record.status = "completed"
                record.results = {
                    ep: str(result.get("output_path", ""))
                    for ep, result in summary.results.items()
                }
            else:
                record.status = "failed"
                record.failures = {
                    ep: str(result.get("error", "执行失败"))
                    for ep, result in summary.results.items()
                    if not result.get("success", True)
                }
                record.error = "；".join(record.failures.values())[:500]
        except Exception as exc:
            record.status = "failed"
            record.error = str(exc)[:500]
        finally:
            record.finished_at = record.finished_at or time.time()
            with self._lock:
                record.runner = None

    def get(self, task_id: str) -> Optional[TaskRecord]:
        with self._lock:
            return self._records.get(task_id)

    def list(self) -> List[Dict[str, Any]]:
        with self._lock:
            items = sorted(self._records.values(), key=lambda r: r.created_at, reverse=True)
        return [self._to_dict(item) for item in items]

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            record = self._records.get(task_id)
            if record is None or record.status not in ("queued", "running"):
                return False
            record.status = "cancelled"
            record.cancel_event.set()
            runner = record.runner
        if runner is not None:
            runner.cancel()
        return True

    @staticmethod
    def _to_dict(record: TaskRecord) -> Dict[str, Any]:
        return {
            "id": record.id,
            "project": record.project_dir,
            "step": record.step,
            "episode_ids": list(record.episode_ids),
            "status": record.status,
            "created_at": record.created_at,
            "finished_at": record.finished_at,
            "error": record.error,
            "results": dict(record.results),
            "failures": dict(record.failures),
        }
