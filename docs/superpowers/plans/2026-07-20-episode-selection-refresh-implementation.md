# Episode Selection, Refresh, and Shot Quality Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make project episodes permanently visible and multi-selectable on the shot-script and storyboard pages, synchronize UI state with disk changes, and prevent invalid one-shot LLM outputs from being published.

**Architecture:** Add a pure episode-state service as the single source for disk-derived status, plus one reusable PyQt episode selector. Pass an explicit episode whitelist through the worker into the prompt generator. Treat generated shot text as an unpublished candidate until format, count, content, and reference audits all pass.

**Tech Stack:** Python 3.12, PyQt6, `QFileSystemWatcher`, pytest/unittest, existing `ProjectScriptSource`, `PromptGenerator`, and worker signal architecture.

**Repository note:** The worktree already contains extensive user changes. Do not create commits or stage files during this plan; verify and report only the exact files changed by these tasks.

---

## File structure

- Create `core/episode_status.py`: pure disk-to-status projection used by both pages and sidebar reconciliation.
- Create `steps/episode_selector.py`: reusable episode tile selector with status text and selection helpers.
- Modify `agents/prompt_generator.py`: exact selected-episode filtering, final validation result, non-conflicting retry feedback, atomic publication.
- Modify `workers.py`: load the configured shot prompt template and pass `selected_episodes` into the generator.
- Modify `steps/step_07_shot.py`: replace single-value combo/results-only tabs with all-episode tiles and disk refresh.
- Modify `steps/step_08_storyboard.py`: build all episode choices from the project episode list and preflight missing/invalid prompts.
- Modify `main_window.py`: refresh the visible step from disk on navigation and reconcile sidebar state.
- Create/update tests in `tests/test_prompt_generation_quality_gate.py`, `tests/test_episode_status.py`, `tests/test_episode_selector.py`, and `tests/test_ui_selection.py`.

### Task 1: Pure episode status projection

**Files:**
- Create: `core/episode_status.py`
- Create: `tests/test_episode_status.py`

- [ ] **Step 1: Write failing tests for stable episode inventory and prompt/storyboard states**

```python
def test_episode_inventory_survives_missing_prompts(tmp_path):
    project = make_project(tmp_path, episodes=["01", "02", "03"])
    (project / "prompts" / "01.txt").write_text(valid_shots(5), encoding="utf-8")
    states = EpisodeStatusService(str(project)).snapshot()
    assert list(states) == ["01", "02", "03"]
    assert states["01"].prompt_status == "completed"
    assert states["02"].prompt_status == "pending"

def test_storyboard_becomes_partial_after_image_delete(tmp_path):
    project = make_project(tmp_path, episodes=["01"])
    (project / "prompts" / "01.txt").write_text(valid_shots(3), encoding="utf-8")
    write_images(project / "storyboard" / "01", [1, 2, 3])
    (project / "storyboard" / "01" / "2.jpg").unlink()
    state = EpisodeStatusService(str(project)).snapshot()["01"]
    assert state.storyboard_status == "partial"
    assert state.storyboard_count == 2
    assert state.expected_shots == 3
```

- [ ] **Step 2: Run the tests and confirm RED**

Run: `python -m pytest tests/test_episode_status.py -q`

Expected: import failure because `core.episode_status` does not exist.

- [ ] **Step 3: Implement the status service**

```python
@dataclass(frozen=True)
class EpisodeState:
    episode: str
    prompt_status: str
    shot_count: int
    storyboard_status: str
    storyboard_count: int
    expected_shots: int

class EpisodeStatusService:
    def __init__(self, project_dir: str):
        self.project_dir = project_dir

    def episode_ids(self) -> list[str]:
        source = ProjectScriptSource(self.project_dir)
        source.ensure()
        root = source.visual_episodes_dir()
        return sorted(
            Path(name).stem.zfill(2)
            for name in os.listdir(root)
            if name.lower().endswith(".txt") and Path(name).stem.isdigit()
        )

    def snapshot(self) -> dict[str, EpisodeState]:
        return {episode: self._state_for(episode) for episode in self.episode_ids()}
```

`_state_for` must call `analyze_shots`, require `recognized=True`, continuous shot numbers, and at least the configured minimum. It must count only numeric image filenames whose numbers are expected by the prompt.

- [ ] **Step 4: Run the status tests and confirm GREEN**

Run: `python -m pytest tests/test_episode_status.py -q`

Expected: all tests pass.

### Task 2: Prompt generator selection and publish quality gate

**Files:**
- Modify: `agents/prompt_generator.py:291-427`
- Modify: `agents/prompt_generator.py:434-546`
- Modify: `agents/prompt_generator.py:744-804`
- Create: `tests/test_prompt_generation_quality_gate.py`

- [ ] **Step 1: Write failing tests for exact selection and invalid final output**

```python
def test_process_generates_only_selected_episodes(tmp_path):
    episodes = make_episode_files(tmp_path, ["01", "02", "03"])
    generator = PromptGenerator(FakeLLM(valid_shots(5)))
    result = generator.process(
        str(episodes), str(tmp_path / "prompts"),
        selected_episodes=["02"], skip_existing=False,
    )
    assert result["generated"] == 1
    assert (tmp_path / "prompts" / "02.txt").exists()
    assert not (tmp_path / "prompts" / "01.txt").exists()

def test_one_shot_final_retry_is_not_published(tmp_path):
    episodes = make_episode_files(tmp_path, ["01"])
    generator = PromptGenerator(FakeLLM(one_shot_text()))
    result = generator.process(str(episodes), str(tmp_path / "prompts"), skip_existing=False)
    assert result["success"] is False
    assert not (tmp_path / "prompts" / "01.txt").exists()

def test_failed_regeneration_preserves_valid_existing_file(tmp_path):
    output = tmp_path / "prompts" / "01.txt"
    output.parent.mkdir()
    output.write_text(valid_shots(5), encoding="utf-8")
    generator = PromptGenerator(FakeLLM(one_shot_text()))
    generator.process(str(make_episode_files(tmp_path, ["01"])), str(output.parent), skip_existing=False)
    assert output.read_text(encoding="utf-8") == valid_shots(5)
```

- [ ] **Step 2: Run the tests and confirm RED**

Run: `python -m pytest tests/test_prompt_generation_quality_gate.py -q`

Expected: selected whitelist is unsupported and invalid output is written.

- [ ] **Step 3: Return a structured generation outcome**

```python
@dataclass(frozen=True)
class ShotGenerationOutcome:
    text: str
    valid: bool
    issues: tuple[str, ...]
    attempts: int
```

Change `_generate_single` to return this object. After the final retry, return `valid=False` with the last complete issue list rather than returning raw text as success.

- [ ] **Step 4: Remove contradictory retry feedback**

```python
shot_count_issue = any("镜头数不足" in issue or "只有" in issue for issue in format_issues + audit_issues)
if reference_issues:
    all_issues.append("【资产引用问题】")
    all_issues.extend(f"- {issue}" for issue in reference_issues)
    if not shot_count_issue:
        all_issues.append("请保持镜头数量和剧情不变，只修正引用名称。")
```

Update content auditing to accept direct `旁白：` and dialogue lines. Require `analyze_shots(result).recognized`; call `_estimate_shot_range` and report the actual expected lower bound.

- [ ] **Step 5: Filter by exact selected episodes and publish atomically**

Add `selected_episodes: Optional[List[str]] = None` to `process`. Normalize to two digits, reject unknown requested episodes, and filter `filtered_episode_files` before creating futures.

Only when `outcome.valid` is true:

```python
fd, temp_path = tempfile.mkstemp(prefix=f".{ep_num}.", suffix=".tmp", dir=output_dir)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(outcome.text)
    os.replace(temp_path, output_path)
finally:
    if os.path.exists(temp_path):
        os.unlink(temp_path)
```

On invalid outcome, return `success=False`, `shot_count`, and joined issues without touching `output_path`.

- [ ] **Step 6: Run quality-gate tests and existing prompt tests**

Run: `python -m pytest tests/test_prompt_generation_quality_gate.py tests/test_reference_audit.py tests/test_asset_txt_and_shot_import.py -q`

Expected: all pass.

### Task 3: Worker uses configured template and real selection

**Files:**
- Modify: `workers.py:469-608`
- Update: `tests/test_media_prompt_storyboard.py`

- [ ] **Step 1: Write a failing worker wiring test**

```python
def test_shot_worker_passes_template_and_selected_episodes(self):
    worker = ShotScriptWorker(project_dir, {"selected_episodes": ["02", "05"]})
    with patch("workers.PromptGenerator.process") as process:
        run_worker_impl(worker)
    assert process.call_args.kwargs["selected_episodes"] == ["02", "05"]
    assert captured_builder.schema.min_shots == 5
```

- [ ] **Step 2: Run the test and confirm RED**

Run: `python -m pytest tests/test_media_prompt_storyboard.py -q`

Expected: `selected_episodes` is absent and the default builder is used.

- [ ] **Step 3: Wire the template and selection**

```python
from agents.prompt_generator import PromptBuilder
builder = PromptBuilder.from_file(config.prompt_template_path)
generator = PromptGenerator(llm, prompt_builder=builder)
result = generator.process(
    episodes_dir=episodes_dir,
    output_dir=prompts_dir,
    selected_episodes=selected or None,
    ...,
)
```

Remove the worker-only `txt_files` filtering as a generation control; keep it only for emitting the selected result files.

- [ ] **Step 4: Run worker tests and confirm GREEN**

Run: `python -m pytest tests/test_media_prompt_storyboard.py -q`

Expected: all pass.

### Task 4: Reusable episode tile selector

**Files:**
- Create: `steps/episode_selector.py`
- Create: `tests/test_episode_selector.py`

- [ ] **Step 1: Write failing offscreen Qt tests**

```python
def test_selector_keeps_all_episode_ids(qapp):
    selector = EpisodeSelector()
    selector.set_episodes({"01": pending_state(), "02": completed_state(9)})
    assert selector.episode_ids() == ["01", "02"]

def test_only_pending_selects_pending_invalid_and_failed(qapp):
    selector = EpisodeSelector()
    selector.set_episodes(test_states())
    selector.select_pending()
    assert selector.selected_episodes() == ["02", "03", "05"]
```

- [ ] **Step 2: Run and confirm RED**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_episode_selector.py -q`

Expected: import failure.

- [ ] **Step 3: Implement the shared selector**

`EpisodeSelector(QWidget)` must expose:

```python
selection_changed = pyqtSignal(list)
episode_activated = pyqtSignal(str)

def set_episodes(self, states: Mapping[str, EpisodeState]) -> None: ...
def selected_episodes(self) -> list[str]: ...
def episode_ids(self) -> list[str]: ...
def select_all(self) -> None: ...
def clear_selection(self) -> None: ...
def select_pending(self) -> None: ...
def set_running(self, episodes: Iterable[str]) -> None: ...
```

Use checkable `QToolButton` tiles in a wrapping `QGridLayout`, retaining selection for episode IDs that still exist after refresh.

- [ ] **Step 4: Run selector tests and confirm GREEN**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_episode_selector.py -q`

Expected: all pass.

### Task 5: Shot-script page all-episode view and refresh

**Files:**
- Modify: `steps/step_07_shot.py`
- Update: `tests/test_ui_selection.py`

- [ ] **Step 1: Write failing UI tests**

```python
def test_shot_page_shows_all_project_episodes_without_prompts(qapp, project):
    write_episode_files(project, ["01", "02", "03"])
    widget = Step07ShotWidget()
    widget.set_project(str(project))
    assert widget._episode_selector.episode_ids() == ["01", "02", "03"]

def test_refresh_clears_deleted_prompt_content(qapp, project):
    write_prompt(project, "02", valid_shots(5))
    widget = loaded_shot_widget(project)
    os.unlink(project / "prompts" / "02.txt")
    widget.refresh_from_disk()
    assert widget._ep_texts.get("02", "") == ""
```

- [ ] **Step 2: Run and confirm RED**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_ui_selection.py -q`

Expected: no shared selector or `refresh_from_disk` exists.

- [ ] **Step 3: Replace the processing combo with EpisodeSelector**

Create the selector in `_create_controls_widget`, connect `episode_activated` to the content view, and make `do_run` use `selected_episodes()`.

Implement:

```python
def refresh_from_disk(self):
    states = EpisodeStatusService(self.project_dir).snapshot() if self.project_dir else {}
    self._episode_selector.set_episodes(states)
    self._ep_texts = {
        ep: Path(self.project_dir, "prompts", f"{ep}.txt").read_text(encoding="utf-8")
        for ep in states
        if Path(self.project_dir, "prompts", f"{ep}.txt").is_file()
    }
    self._render_current_episode()
```

Use one editable/read-only content pane or stable per-episode tabs, but rebuild them from the complete episode list and display an empty state when text is absent.

- [ ] **Step 4: Add directory watching with debounce**

Watch the visual episode directory and `prompts` directory. Connect `directoryChanged` to a single-shot `QTimer(150ms)` whose timeout calls `refresh_from_disk`. Re-add watched directories after project changes.

- [ ] **Step 5: Run shot-page tests and confirm GREEN**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_ui_selection.py -q`

Expected: all pass.

### Task 6: Storyboard page all-episode view and prompt preflight

**Files:**
- Modify: `steps/step_08_storyboard.py`
- Update: `tests/test_ui_selection.py`

- [ ] **Step 1: Write failing storyboard UI tests**

```python
def test_storyboard_page_lists_episodes_without_prompts(qapp, project):
    write_episode_files(project, ["01", "02"])
    widget = loaded_storyboard_widget(project)
    assert widget._episode_selector.episode_ids() == ["01", "02"]

def test_storyboard_preflight_excludes_missing_and_invalid_prompts(qapp, project):
    write_prompt(project, "01", valid_shots(5))
    write_prompt(project, "02", one_shot_text())
    valid, blocked = widget._partition_selected_episodes(["01", "02", "03"])
    assert valid == ["01"]
    assert blocked == {"02": "镜头脚本无效", "03": "缺少镜头脚本"}
```

- [ ] **Step 2: Run and confirm RED**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_ui_selection.py -q`

Expected: storyboard choices still come from `prompts`.

- [ ] **Step 3: Use shared selector and status service**

Replace `_rebuild_episode_checkboxes` and the prompt-derived combo with `EpisodeSelector`. The viewer combo may remain, but populate it from `EpisodeStatusService.episode_ids()`.

Implement `_partition_selected_episodes` and make `do_run` submit only valid episodes after a single consolidated warning. If no valid episodes remain, stop without creating `StoryboardWorker`.

- [ ] **Step 4: Prebuild missing image cards**

In `_show_episode`, parse the valid prompt first and create one `ShotCard` per expected shot. Apply existing images by numeric filename; leave absent images with `set_pending()` rather than omitting the card.

- [ ] **Step 5: Add watcher and refresh hooks**

Watch `prompts`, `storyboard`, and the current episode output directory. Debounce to `refresh_from_disk`; call the same method on worker completion and stop.

- [ ] **Step 6: Run storyboard UI tests and confirm GREEN**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_ui_selection.py tests/test_storyboard_batching.py -q`

Expected: all pass.

### Task 7: Navigation refresh and sidebar reconciliation

**Files:**
- Modify: `main_window.py:168-182`
- Modify: `main_window.py:210-273`
- Update: `tests/test_gui_smoke.py`

- [ ] **Step 1: Write a failing navigation refresh test**

```python
def test_selecting_step_refreshes_visible_widget_from_disk(window):
    target = window.step_widgets[4]
    target.refresh_from_disk = Mock()
    window._step_list.setCurrentRow(4)
    target.refresh_from_disk.assert_called_once()
```

- [ ] **Step 2: Run and confirm RED**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_gui_smoke.py -q`

Expected: page selection does not call refresh.

- [ ] **Step 3: Refresh visible pages and reconcile status**

After switching the stack page:

```python
widget = self.step_widgets[row]
refresh = getattr(widget, "refresh_from_disk", None)
if callable(refresh):
    refresh()
```

Update `_sync_step_status_from_project` so prompt/storyboard counts are derived from `EpisodeStatusService.snapshot()` before rendering sidebar completion.

- [ ] **Step 4: Run GUI smoke tests and confirm GREEN**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_gui_smoke.py tests/test_ui_selection.py -q`

Expected: all pass.

### Task 8: Full verification

**Files:**
- Verify all files modified above.

- [ ] **Step 1: Compile changed Python modules**

Run:

`python -m py_compile core/episode_status.py steps/episode_selector.py agents/prompt_generator.py workers.py steps/step_07_shot.py steps/step_08_storyboard.py main_window.py`

Expected: exit code 0.

- [ ] **Step 2: Run the complete test suite**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests -q`

Expected: all tests pass with no failures.

- [ ] **Step 3: Perform a focused manual disk-refresh smoke test**

Use a temporary project with three episodes. Open both pages, externally create and delete `prompts/02.txt` and `storyboard/02/1.jpg`, and verify the episode tile and card state update without changing projects or restarting the UI.

- [ ] **Step 4: Review the final diff without staging**

Run: `git diff -- core/episode_status.py steps/episode_selector.py agents/prompt_generator.py workers.py steps/step_07_shot.py steps/step_08_storyboard.py main_window.py tests/test_episode_status.py tests/test_prompt_generation_quality_gate.py tests/test_episode_selector.py tests/test_ui_selection.py tests/test_gui_smoke.py`

Expected: only scoped changes, no unrelated user edits rewritten.
