"""
Phase 6v2: 自主优化循环诊断脚本

使用方式：在 Claude Code goal 中每轮执行：
  `python scripts/optimization_loop.py`

输出到 docs/optimization_loop_log.md 供 Claude 读取分析。

四维目标：
  - 效率 (Efficiency)    — 性能、速度、资源
  - 准确度 (Accuracy)    — 正确性、bug 减少
  - 美观度 (Aesthetics)  — UI 品质、用户体验
  - 质量 (Quality)       — 代码质量、测试覆盖、可维护性

每轮逻辑：
  1. 量化诊断 — 跑基线测试 + 计数器 + git 状态
  2. 变化量分析 — 对比上一轮指标
  3. 代码健康扫描 — 复杂度 / 重复 / 死代码提示
  4. 输出判断建议 — Claude 读取后决策
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
METRICS_PATH = PROJECT_ROOT / "docs" / "perf_metrics.jsonl"
LOG_PATH = PROJECT_ROOT / "docs" / "optimization_loop_log.md"
CURSOR_PATH = PROJECT_ROOT / ".omc" / "loop_state.json"


def _ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


# ═══════════════════════════════════════════════════════════
# 1. 量化诊断
# ═══════════════════════════════════════════════════════════

def _run_baseline() -> dict:
    _log("运行性能基线测试...")
    env = os.environ.copy()
    env["AIGC_DISABLE_NETWORK"] = "1"
    env["QT_QPA_PLATFORM"] = "offscreen"
    t0 = time.perf_counter()
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_performance_baseline.py",
         "-q", "--tb=line"],
        cwd=str(PROJECT_ROOT), capture_output=True, text=True,
        timeout=600, env=env,
    )
    elapsed = time.perf_counter() - t0
    return {
        "success": result.returncode == 0,
        "elapsed_s": round(elapsed, 1),
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _get_counter_report() -> dict:
    """从 perf_stats 采集缓存命中率。"""
    # 在子进程中导入 perf_stats 并 dump 计数器
    code = """
import sys, json
sys.path.insert(0, '.')
try:
    from core.perf_stats import perf_counter
    data = {}
    for name, c in perf_counter.items():
        total = c.hits + c.misses
        data[name] = {"hits": c.hits, "misses": c.misses,
                      "ratio": round(c.hits / total, 3) if total else 0}
    print(json.dumps(data, ensure_ascii=False))
except Exception as e:
    print(json.dumps({"error": str(e)}, ensure_ascii=False))
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=30,
    )
    try:
        return json.loads(result.stdout.strip())
    except (json.JSONDecodeError, ValueError):
        return {"error": "无法采集计数器"}


def _git_state() -> dict:
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT),
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT),
        ).stdout.strip()
        modified = len([l for l in status.splitlines() if l.strip()])
        return {"sha": sha, "dirty": modified > 0, "modified_count": modified}
    except Exception:
        return {"sha": "unknown", "dirty": False, "modified_count": 0}


# ═══════════════════════════════════════════════════════════
# 2. 变化量分析
# ═══════════════════════════════════════════════════════════

def _metric_history(name: str) -> list[float]:
    if not METRICS_PATH.exists():
        return []
    with open(METRICS_PATH) as f:
        records = [json.loads(l) for l in f if l.strip()]
    return [r["median_s"] * 1000 for r in records if r["metric"] == name]


def _load_cursor() -> dict:
    """读取上一轮状态指针。"""
    if CURSOR_PATH.exists():
        with open(CURSOR_PATH) as f:
            return json.load(f)
    return {}


def _save_cursor(state: dict):
    CURSOR_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CURSOR_PATH, "w") as f:
        json.dump(state, f, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════
# 3. 代码健康扫描
# ═══════════════════════════════════════════════════════════

def _scan_issues() -> list[dict]:
    """快速扫描代码中可优化的模式。"""
    issues = []
    # 查找 todo/fixme/hack 标记（使用临时文件避免引号转义问题）
    try:
        scan_code = PROJECT_ROOT / ".omc" / "_scan_todo.py"
        scan_code.parent.mkdir(parents=True, exist_ok=True)
        scan_code.write_text(
            "import re,glob\n"
            "all_py=' '.join(open(f,errors='ignore').read() "
            "for f in glob.glob('**/*.py',recursive=True))\n"
            "print(len(re.findall(r'(TODO|FIXME|HACK|XXX|OPTIMIZE)',all_py)))\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable, str(scan_code)],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=60,
        )
        count = int(result.stdout.strip())
        if count > 20:
            issues.append({"type": "tech_debt", "label": "代码标记", "detail": f"{count} 个 TODO/FIXME/HACK"})
        scan_code.unlink(missing_ok=True)
    except Exception:
        pass
    return issues


# ═══════════════════════════════════════════════════════════
# 4. 记录 & 建议
# ═══════════════════════════════════════════════════════════

def _assess_efficiency(metrics_history: dict) -> list[str]:
    """评估效率维度 — 只检查实际缓存优化的指标，排除合成基准噪声。"""
    CACHED_METRICS = {"config_load", "asset_context_load"}
    findings = []
    for name, vals in metrics_history.items():
        if name not in CACHED_METRICS:
            continue
        if len(vals) < 3:
            continue
        latest = vals[-1]
        prev = min(vals[:-1])
        # 变慢阈值：绝对 >0.5ms 且相对 >15%（排除亚毫秒级噪声）
        if latest > prev + max(prev * 0.15, 0.5):
            findings.append(f"{name} 退化: {latest:.3f}ms vs 最佳 {prev:.3f}ms")
    return findings


def write_report(baseline: dict, counters: dict, git: dict, issues: list[dict],
                 efficiency: list[str], round_num: int):
    ts = _ts()
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    log = [
        f"\n---\n## 自主轮次 #{round_num} ({ts})\n",
        f"Git SHA: {git['sha']}  |  未提交变更: {git['modified_count']} 个\n",
    ]
    if not baseline["success"]:
        log.append("### 基线测试: ❌ 失败\n")
    else:
        log.append(f"### 基线测试: ✅ 通过 ({baseline['elapsed_s']}s)\n")

    # 计数器
    if isinstance(counters, dict) and "error" not in counters:
        log.append("### 缓存命中率\n")
        log.append("| 缓存 | 命中 | 未命中 | 命中率 |\n|------|------|--------|--------|\n")
        for name in sorted(counters.keys()):
            c = counters[name]
            log.append(f"| {name} | {c['hits']} | {c['misses']} | {c['ratio']:.0%} |\n")

    # 效率退化检测
    if efficiency:
        log.append("### ⚠ 效率退化\n")
        for f in efficiency:
            log.append(f"- {f}\n")
    else:
        log.append("### 效率: 稳定\n")

    # 代码健康
    if issues:
        log.append("### 代码健康\n")
        for iss in issues:
            log.append(f"- [{iss['type']}] {iss['label']}: {iss['detail']}\n")
    else:
        log.append("### 代码健康: 无突出问题\n")

    # 开放问题 — 引导 Claude 下一轮方向
    log.append("### 建议下一轮方向\n")
    log.append("请分析上方数据，从以下维度中选择一个优化方向：\n\n")
    log.append("- **效率**: 检查缓存命中率低的组件，或 Profile 慢操作\n")
    log.append("- **准确度**: 检查 TODO/FIXME，修复已知 bug\n")
    log.append("- **美观度**: 审查 UI 样式一致性、布局、用户反馈\n")
    log.append("- **质量**: 补充测试覆盖、重构高复杂度函数\n")

    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.writelines(log)
    _log(f"已写入 {LOG_PATH.name}")


# ═══════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════

def main():
    cursor = _load_cursor()
    round_num = cursor.get("round", 0) + 1

    _log(f"=== 自主优化循环 #{round_num} ===")

    # 1. 基线测试
    baseline = _run_baseline()
    if not baseline["success"]:
        _log(f"基线测试失败:\n{baseline['stderr'][:500]}")

    # 2. 计数器
    counters = _get_counter_report()

    # 3. Git 状态
    git = _git_state()

    # 4. 代码健康
    issues = _scan_issues()

    # 5. 趋势分析
    metrics_history = {}
    for name in ("config_load", "asset_context_load", "grid_rebuild_15_cards"):
        vals = _metric_history(name)
        if vals:
            metrics_history[name] = vals

    # 6. 效率评估
    efficiency = _assess_efficiency(metrics_history)

    # 7. 写报告
    write_report(baseline, counters, git, issues, efficiency, round_num)
    _save_cursor({"round": round_num, "last_run": _ts()})

    # 8. 总结
    _log(f"轮次 #{round_num} 完成")
    if git["dirty"]:
        _log(f"工作区有 {git['modified_count']} 个未提交变更")
    if efficiency:
        _log(f"[WARN] 检测到 {len(efficiency)} 个效率退化")
    if isinstance(counters, dict) and "error" not in counters:
        ok = sum(1 for c in counters.values() if c["ratio"] >= 0.5)
        total = len(counters)
        _log(f"缓存健康: {ok}/{total} 命中率≥50%")


if __name__ == "__main__":
    main()
