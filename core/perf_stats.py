"""
AIGC Pipeline — 性能计数器与计时工具模块（Phase 0.2）

用法:
    from core.perf_stats import perf_counter, Timer

    # 计数
    perf_counter["qpixmap_cache"].hit()
    perf_counter["qpixmap_cache"].miss()

    # 计时（带阈值 WARNING）
    with Timer("card_render", threshold_ms=50):
        render_card()

环境变量 AIGC_PERF_STATS=1 控制是否将计数器输出到日志。
"""
import os
import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

# ── 计数器 ──────────────────────────────────────────

_ENABLED = os.environ.get("AIGC_PERF_STATS") in ("1", "true", "yes")


class Counter:
    """单指标计数器，记录 hits 和 misses。"""

    def __init__(self):
        self.hits = 0
        self.misses = 0

    def hit(self, n: int = 1):
        self.hits += n

    def miss(self, n: int = 1):
        self.misses += n

    def total(self) -> int:
        return self.hits + self.misses

    def ratio(self) -> float:
        t = self.total()
        return self.hits / t if t else 0.0

    def reset(self):
        self.hits = 0
        self.misses = 0

    def __repr__(self) -> str:
        return f"Counter(hits={self.hits}, misses={self.misses}, ratio={self.ratio():.1%})"

    __dict__ = property(lambda self: {"hits": self.hits, "misses": self.misses})


class CounterRegistry(dict):
    """模块级计数器注册表，按名称自动创建 Counter（线程安全）。"""

    def __init__(self):
        super().__init__()
        self._lock = threading.Lock()

    def __missing__(self, key: str) -> Counter:
        with self._lock:
            # 双检锁：两个线程可能同时进入 __missing__
            if key not in self:
                self[key] = c = Counter()
                return c
            return self[key]


perf_counter: dict[str, Counter] = CounterRegistry()


# ── 计时器 ──────────────────────────────────────────

class Timer:
    """基于 time.monotonic 的计时段上下文管理器。

    超过 threshold_ms 时打 WARNING 日志（仅当 AIGC_PERF_STATS 启用时）。
    始终记录 elapsed_ms 到 __enter__ 返回的 timer 实例。
    """

    def __init__(self, label: str, threshold_ms: float = 0):
        self.label = label
        self.threshold_ms = threshold_ms
        self.elapsed_ms: float = 0.0

    def __enter__(self):
        self._start = time.monotonic()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.elapsed_ms = (time.monotonic() - self._start) * 1000.0
        if _ENABLED and self.threshold_ms and self.elapsed_ms > self.threshold_ms:
            logger.warning(
                "PERF: %s took %.1fms (threshold=%.0fms)",
                self.label, self.elapsed_ms, self.threshold_ms,
            )


# ── 日志转储（供 Phase 6 loop 采集） ───────────────

def dump_stats() -> dict[str, dict]:
    """返回所有计数器快照（供测试断言 / loop 日志使用）。"""
    return {name: {"hits": c.hits, "misses": c.misses}
            for name, c in perf_counter.items()}


def reset_all():
    """重置所有计数器。"""
    for c in perf_counter.values():
        c.reset()
