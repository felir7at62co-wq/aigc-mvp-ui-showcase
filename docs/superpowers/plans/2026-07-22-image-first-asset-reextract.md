# Image-First Asset Re-extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing “重新提取” action derive prompts from existing character, scene, and prop images while preserving script-owned names, aliases, and episode scopes.

**Architecture:** Extend `AssetDescriptionExtractor`'s existing per-image vision path to all three categories and merge visual prompts deterministically with old/script metadata. Keep the UI flow unchanged; the worker enables vision only for explicit re-extraction, writes through the existing temporary file, and falls back to old/script prompts per failed image.

**Tech Stack:** Python 3.12, PyQt worker layer, existing multimodal `LLMClient`, pytest.

---

### Task 1: Character and scene metadata-safe vision fallback

**Files:**
- Modify: `agents/asset_description_extractor.py`
- Test: `tests/test_scene_reextract_context.py`

- [ ] Add failing tests proving a successful image description replaces only the prompt, and a failed visual call preserves the old prompt while retaining script/old aliases and episode scopes.
- [ ] Run `python -m pytest tests/test_scene_reextract_context.py -q` and confirm failures identify missing fallback behavior.
- [ ] Add a small prompt-validity check and deterministic old-record fallback in `AssetDescriptionExtractor.extract`.
- [ ] Re-run the focused tests and confirm they pass.

### Task 2: Prop image vision support

**Files:**
- Modify: `agents/asset_description_extractor.py`
- Test: `tests/test_scene_reextract_context.py`

- [ ] Add a failing test with an existing `assets/prop/<name>.png` and assert the visual prompt replaces the script prompt while name, aliases, and episodes remain script-owned.
- [ ] Run the focused test and confirm it fails because prop images are currently ignored.
- [ ] Add `prop_image_dir` to `extract`, implement `describe_prop_from_image`, collect per-image prop results, and merge them using the same deterministic rules.
- [ ] Re-run the focused tests and confirm they pass.

### Task 3: Enable image-first behavior from the re-extraction worker

**Files:**
- Modify: `workers.py`
- Test: `tests/test_asset_worker_safety.py`

- [ ] Replace the existing test that expects vision to be disabled with a failing test that asserts the worker supplies character, scene, and prop image directories and enables `use_image_vision`.
- [ ] Run `python -m pytest tests/test_asset_worker_safety.py -q` and confirm the new expectation fails.
- [ ] Update `AssetPromptWorker` to pass the prop directory and `use_image_vision=True`; keep category isolation and temporary-file replacement unchanged.
- [ ] Re-run worker safety tests and confirm they pass.

### Task 4: Regression verification

**Files:**
- Verify: `agents/asset_description_extractor.py`
- Verify: `workers.py`
- Verify: `tests/test_scene_reextract_context.py`
- Verify: `tests/test_asset_worker_safety.py`

- [ ] Run `python -m pytest tests/test_scene_reextract_context.py tests/test_asset_worker_safety.py tests/test_named_asset_import.py tests/test_asset_catalog.py -q`.
- [ ] Run `python -m pytest tests/test_storyboard_batching.py tests/test_scene_manifest_and_scope.py -q` to verify downstream matching and stale-storyboard behavior.
- [ ] Run GitNexus `detect-changes` if the repaired index is available; otherwise report that index failure and provide direct-call/test evidence.
- [ ] Review the final diff for unrelated changes and do not alter the user's project asset files.
