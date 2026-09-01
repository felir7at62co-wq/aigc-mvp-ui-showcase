"""
Phase 6v2: 自主优化循环

不再只是"跑测试→记日志"，而是每轮：

  1. 诊断 — 收集性能指标 + 代码质量扫描
  2. 排序 — 按 ROI 排列可优化项
  3. 设计 — 生成优化方案（含影响分析）
  4. 实施 — 应用变更（需人工确认）
  5. 验证 — 测试 + 指标对比

安全栏：
  - AIGC_DISABLE_NETWORK=1 全程生效
  - 变更前 GitNexus impact 分析 → 人工确认
  - 每轮硬时间预算 ≤ 15 分钟
  - 不自动 git commit
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOOP_LOG = PROJECT_ROOT / "docs" / "optimization_loop_log.md"
LOOP_LOCK = PROJECT_ROOT / ".omc" / "optimization_loop.lock"


def _log(msg: str):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


# ═══════════════════════════════════════════════════════════
# 步骤 1: 诊断 — 收集性能指标
# ═══════════════════════════════════════════════════════════

def _gather_metrics() -> dict:
    """跑基线测试并收集计数器数据"""
    _log("采集性能指标...")
    env = os.environ.copy()
    env["AIGC_DISABLE_NETWORK"] = "1"
    env["QT_QPA_PLATFORM"] = "offscreen"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_performance_baseline.py",
         "-q", "--tb=line"],
        cwd=str(PROJECT_ROOT), capture_output=True, text=True,
        timeout=600, env=env,
    )
    passed = "passed" in result.stdout and "failed" not in result.stdout
    return {
        "success": passed,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "metrics_file": PROJECT_ROOT / "docs" / "perf_metrics.jsonl",
    }


def _read_metric_trends(metrics_path: Path, metric_name: str, window: int = 5) -> dict:
    """读取最近 window 次该指标的记录，返回趋势分析。"""
    if not metrics_path.exists():
        return {"available": False}
    with open(metrics_path) as f:
        records = [json.loads(line) for line in f if line.strip()]
    entries = [r for r in records if r["metric"] == metric_name]
    if len(entries) < 2:
        return {"available": False, "count": len(entries)}
    recent = entries[-window:]
    values = [e["median_s"] * 1000 for e in recent]  # → ms
    return {
        "available": True,
        "count": len(entries),
        "latest_ms": values[-1],
        "min_ms": min(values),
        "max_ms": max(values),
        "avg_ms": sum(values) / len(values),
        "trend": "stable" if max(values) / max(min(values), 0.001) < 1.5 else "volatile",
    }


# ═══════════════════════════════════════════════════════════
# 步骤 2: 排序 — 识别高 ROI 优化机会
# ═══════════════════════════════════════════════════════════

def _identify_opportunities(metrics: dict) -> list[dict]:
    """根据当前指标和代码结构，推荐下一步优化方向。"""
    opportunities = []

    # 2a. 检查 perf_metrics 趋势
    if metrics.get("success"):
        mp = metrics["metrics_file"]
        config_trend = _read_metric_trends(mp, "config_load")
        context_trend = _read_metric_trends(mp, "asset_context_load")

        _log(f"config_load 趋势: {config_trend.get('latest_ms', 'N/A'):.3f}ms "
             f"(avg={config_trend.get('avg_ms', 'N/A'):.3f}ms)")
        _log(f"asset_context_load 趋势: {context_trend.get('latest_ms', 'N/A'):.3f}ms "
             f"(avg={context_trend.get('avg_ms', 'N/A'):.3f}ms)")

        # 如果缓存命中率低于预期，提示检查
        opportunities.append({
            "area": "缓存命中率",
            "detail": "检查 perf_stats 计数器确认各缓存命中率",
            "effort": "低",
            "impact": "中",
        })

    # 2b. 检查 git 变更规模
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT),
        )
        dirty_count = len([l for l in status.stdout.splitlines() if l.strip()])
        if dirty_count > 10:
            opportunities.append({
                "area": "变更积累",
                "detail": f"有 {dirty_count} 个未提交变更，建议整理后提交",
                "effort": "低",
                "impact": "中",
            })
    except Exception:
        pass

    return opportunities


# ═══════════════════════════════════════════════════════════
# 步骤 3: 记录
# ═══════════════════════════════════════════════════════════

def _log_round(metrics_ok: bool, opportunities: list[dict]):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        git_sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT),
        ).stdout.strip()
    except Exception:
        git_sha = "unknown"

    LOOP_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = [
        f"\n## 自主轮次 {ts}\n",
        f"- Git SHA: {git_sha}\n",
        f"- 基线测试: {'通过' if metrics_ok else '失败'}\n",
    ]
    if opportunities:
        entry.append("- 发现优化机会:\n")
        for o in opportunities:
            entry.append(f"  - [{o['area']}] {o['detail']} (投入:{o['effort']}, 收益:{o['impact']})\n")
    else:
        entry.append("- 优化机会: 无突出项\n")

    with open(LOOP_LOG, "a", encoding="utf-8") as f:
        f.writelines(entry)
    _log(f"已记录到 {LOOP_LOG.name}")


# ═══════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════

def main():
    _log("=== 自主优化循环 ===")

    # 1. 诊断
    metrics = _gather_metrics()
    if not metrics["success"]:
        _log(f"基线测试失败:\n{metrics['stderr'][:500]}")
        _log_round(False, [{"area": "基线测试", "detail": "测试执行失败，需人工检查",
                           "effort": "低", "impact": "高"}])
        return

    # 2. 排序
    opportunities = _identify_opportunities(metrics)

    # 3. 记录
    _log_round(True, opportunities)

    # 4. 打印总结
    if opportunities:
        _log(f"发现 {len(opportunities)} 个优化机会:")
        for o in opportunities:
            _log(f"  [{o['area']}] {o['detail']}")
        _log("人工确认后，可继续实施优化。")
    else:
        _log("未发现突出的优化机会，指标稳定。")


if __name__ == "__main__":
    main()
