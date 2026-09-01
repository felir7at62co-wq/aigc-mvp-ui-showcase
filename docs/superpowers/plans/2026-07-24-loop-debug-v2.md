# 持续自主调试循环 v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立一个每 30 分钟运行一次的可暂停、可恢复、不会重叠执行的持续调试循环，在发现低风险问题时真正完成定位、修复和验证，并通过持久化问题缓存减少重复分析。

**Architecture:** 调度器每 30 分钟启动一次完整调试迭代；另有轻量监控负责发现项目变化，但不直接修改代码。通过单实例锁保证同一时间只有一轮运行。检测、分诊、修复、验证、缓存和状态持久化彼此分离。所有自动修改发生在专用 worktree/临时分支中，通过基线比较、GitNexus impact 和相关测试后才允许提交。

**Tech Stack:** Python、pytest、Git worktree/temporary branch、GitNexus、JSONL 状态日志、项目现有 Agent/命令系统。

---

## 运行规则

- 完整 Loop 默认每 30 分钟执行一次；单轮最长运行 25 分钟，超时后保存现场并安全退出。
- 轻量监控每 1～2 分钟运行一次，只检查 Git 状态、文件变化、上次失败测试和是否已有待处理 issue，不启动自动修复。
- 如果上一轮仍在运行，下一次完整 Loop 直接跳过，不排队、不并发。
- 首版只自动修复语法错误、导入错误和有明确失败测试支撑的局部错误。
- P0/P1（安全、数据破坏、资源泄露、架构级逻辑风险）只记录、暂停并请求人工确认。
- 每轮最多处理一个 issue；最多修改一个函数或一个局部逻辑，不以行数作为唯一安全边界。
- 不触碰用户当前工作区的未提交修改；自动修改只能发生在专用 worktree。
- 连续失败 2 次、同一 issue 尝试 3 次、累计自动修改 100 行或连续 clean 5 轮时暂停。

## 缓存命中策略

缓存的目标不是保存整段上下文，而是保存可复用的工程事实和失败经验。每个 issue 使用以下指纹去重：

```text
issue_hash = hash(错误类型 + 测试节点 + 标准化错误摘要 + 相关文件内容 hash)
```

每轮处理前按以下顺序读取缓存：

1. issue_hash 已成功修复且相关文件未变化：跳过重复分析。
2. issue_hash 曾失败 2 次且输入未变化：暂停该 issue，不再重复调用 Agent。
3. 相关文件发生变化：保留历史尝试，但重新允许分析。
4. 新 issue：建立问题记录，并保存测试节点、调用链、影响文件和验证命令。

每条缓存记录必须包含：`issue_hash`、`baseline_commit`、`affected_files`、`impact_summary`、`attempts`、`successful_fix`、`failed_approaches`、`verification_command`、`last_seen_at`。缓存只作为决策依据，不直接替代测试。

## 文件结构

- Create: `.claude/commands/loop-debug.md` — 单轮入口和安全策略
- Create: `.claude/loop-debug/runner.py` — 锁、30 分钟调度、阶段编排和超时
- Create: `.claude/loop-debug/detect.py` — 分层检测和基线差异
- Create: `.claude/loop-debug/state.py` — issue 去重、尝试次数、暂停状态
- Create: `.claude/loop-debug/worktree.py` — 专用 worktree 和临时提交管理
- Create: `tests/test_loop_debug_state.py` — 状态机测试
- Create: `tests/test_loop_debug_runner.py` — 锁、30 分钟窗口和停止条件测试
- Create: `tests/test_loop_debug_detect.py` — 检测结果归一化测试
- Create: `.omc/state/loop-debug-log.jsonl` — 运行时 JSONL 日志（不提交业务代码）
- Create: `memory/loop-debug-state.md` — 面向人工阅读的当前状态摘要和缓存命中统计
- Modify: `.claude/settings.local.json` — 仅在确认调度能力可用后添加 10 秒触发配置

### Task 1: 定义持久化状态和 issue 去重

**Files:**
- Create: `.claude/loop-debug/state.py`
- Test: `tests/test_loop_debug_state.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_issue_key_is_stable_for_same_failure():
    from loop_debug.state import issue_key
    assert issue_key("tests/test_a.py::test_x", "AssertionError: 1 != 2") == issue_key(
        "tests/test_a.py::test_x", "AssertionError: 1 != 2"
    )


def test_state_pauses_after_third_attempt():
    from loop_debug.state import LoopState
    state = LoopState()
    for _ in range(3):
        state.record_failure("issue-1", "same failure")
    assert state.paused is True
    assert state.pause_reason == "same_issue_failed_three_times"
```

- [ ] **Step 2: Run the focused test**

Run: `pytest tests/test_loop_debug_state.py -q`
Expected: FAIL because the state module does not exist.

- [ ] **Step 3: Implement the state machine**

Implement `issue_key(location, normalized_message)`, `LoopState.record_failure`, `record_success`, `mark_clean`, `to_json`, and `from_json`. Persist only deterministic issue keys, attempt counts, last error, affected files, baseline commit, clean count, paused flag, and pause reason.

- [ ] **Step 4: Run the focused test**

Run: `pytest tests/test_loop_debug_state.py -q`
Expected: PASS.

### Task 2: Implement layered detection

**Files:**
- Create: `.claude/loop-debug/detect.py`
- Test: `tests/test_loop_debug_detect.py`

- [ ] **Step 1: Write tests for result normalization**

```python
def test_syntax_error_is_p0_blocking_issue():
    from loop_debug.detect import normalize_issue
    issue = normalize_issue("py_compile", "app.py: invalid syntax")
    assert issue.priority == "P0-blocking"
    assert issue.auto_fixable is True


def test_security_issue_is_not_auto_fixable():
    from loop_debug.detect import normalize_issue
    issue = normalize_issue("security", "possible secret exposure")
    assert issue.priority == "P1-high"
    assert issue.auto_fixable is False
```

- [ ] **Step 2: Implement L0-L5 detection**

Implement: L0 lock/worktree/status checks; L1 `py_compile` and import checks; L2 `pytest --lf -x` with timeout; L3 affected-module tests; L4 full suite only when no active failure is known; L5 code/security review at a low frequency. Normalize all output into `Issue` records and compare against the stored baseline so pre-existing failures are not reported as newly introduced.

- [ ] **Step 3: Run focused detection tests**

Run: `pytest tests/test_loop_debug_detect.py -q`
Expected: PASS.

### Task 3: Add isolated worktree handling

**Files:**
- Create: `.claude/loop-debug/worktree.py`

- [ ] **Step 1: Implement safe lifecycle methods**

Provide `create_iteration_worktree()`, `clean_iteration_worktree()`, `commit_verified_change()`, and `discard_iteration_change()`. Validate every resolved path is inside the project’s dedicated loop directory. Never use `git stash` as the primary rollback mechanism.

- [ ] **Step 2: Add modification guards**

Reject changes to dependency manifests, settings, migrations, secrets, security configuration, and files outside the issue’s affected-file set. Reject more than one issue or more than one function-sized change per iteration.

- [ ] **Step 3: Verify Git behavior without mutating the user worktree**

Run: `git status --short`
Expected: the command shows the same user changes before and after a dry-run lifecycle test.

### Task 4: Implement the single-iteration runner

**Files:**
- Create: `.claude/loop-debug/runner.py`
- Test: `tests/test_loop_debug_runner.py`
- Create: `.claude/commands/loop-debug.md`

- [ ] **Step 1: Write lock and stop-condition tests**

```python
def test_second_iteration_skips_when_lock_is_held(tmp_path):
    from loop_debug.runner import IterationLock
    lock = IterationLock(tmp_path / "loop.lock")
    assert lock.acquire() is True
    assert IterationLock(tmp_path / "loop.lock").acquire() is False


def test_five_clean_rounds_pause():
    from loop_debug.state import LoopState
    state = LoopState()
    for _ in range(5):
        state.mark_clean()
    assert state.paused is True
```

- [ ] **Step 2: Implement the phase pipeline**

The runner must execute: acquire lock → enforce the 25-minute budget → read state, baseline and issue cache → fast detect → deduplicate and prioritize → pause on P0/P1 → select one auto-fixable issue → run GitNexus impact → delegate fix → run targeted tests and regression tests → commit only on success → update JSONL, issue cache and Markdown state → release lock.

- [ ] **Step 3: Add the command contract**

`/loop-debug --dry-run` detects and logs only. `/loop-debug --once` runs one guarded 30-minute iteration. `/loop-debug --monitor` performs only the lightweight 1～2 minute check. The scheduled form must call the same `--once` path and must never bypass the lock or verification gates.

- [ ] **Step 4: Run runner tests**

Run: `pytest tests/test_loop_debug_runner.py -q`
Expected: PASS.

### Task 5: Add scheduling and observability

**Files:**
- Modify: `.claude/settings.local.json`
- Create: `.omc/state/loop-debug-log.jsonl`
- Create: `memory/loop-debug-state.md`

- [ ] **Step 1: Dry-run the command**

Run: `/loop-debug --dry-run`
Expected: a structured result containing baseline commit, detected issues, selected issue, and whether the iteration would pause; no source file changes.

- [ ] **Step 2: Add lightweight monitoring**

Configure `/loop-debug --monitor` at a 1～2 minute interval. It may update “project changed” and “pending issue” state, but it must not modify source files or start a repair Agent.

- [ ] **Step 3: Add the 30-minute full Loop**

Configure a 30-minute trigger that invokes `/loop-debug --once`. The scheduler must not start a second process while the lock exists. If the scheduler cannot guarantee this, the runner lock remains the final authority and the duplicate invocation exits immediately.

- [ ] **Step 4: Verify operational safeguards and cache behavior**

Test: two simultaneous invocations, a pre-existing failing test, a P1 issue, a failed verification, an unchanged cached failure, a changed cached failure, and five clean rounds. Expected: no overlapping run, no false regression, no automatic P1 change, failed changes are discarded, unchanged failures are not re-analyzed, changed failures are re-evaluated, and clean state pauses.

### Task 6: Final verification and handoff

- [ ] **Step 1: Run all loop-debug tests**

Run: `pytest tests/test_loop_debug_*.py -q`
Expected: PASS.

- [ ] **Step 2: Run the project’s relevant regression tests**

Run: `pytest tests -q`
Expected: no new failures compared with the recorded baseline.

- [ ] **Step 3: Run GitNexus change detection**

Run: `node .gitnexus/run.cjs detect-changes`
Expected: only the intended loop-debug files and execution flows are affected.

- [ ] **Step 4: Perform a manual safety review**

Confirm that the scheduler can be stopped, the lock expires or can be safely recovered, the current user worktree is untouched, P0/P1 issues require human confirmation, and every automatic commit has a corresponding test result and JSONL record.

## Self-review checklist

- 30 分钟完整调度和 1～2 分钟轻量监控不会造成并发执行：Task 4、Task 5。
- 分层检测和基线差异：Task 2。
- 高风险问题人工确认：Task 2、Task 4、Task 5。
- worktree 隔离和可恢复提交：Task 3。
- 上下文/状态持久化：Task 1、Task 5。
- 问题指纹、失败经验和缓存命中：运行规则、缓存命中策略、Task 1、Task 4、Task 5。
- 停止条件和失败重试上限：Task 1、Task 4。
- 自动修复后的验证和 GitNexus 变更检查：Task 4、Task 6。
