# Continuous Wardrobe Matching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Match uploaded character/scene/prop images to existing formal assets and persistent story-event variants asynchronously, while retaining unmatched non-essential people in prompts without uploading reference images.

**Architecture:** Keep one formal identity per character and store each outfit/event as a `variant` with an effective episode/shot range. Build a lightweight project timeline index once from the screenplay; uploads query that index, then an optional small LLM resolver returns JSON with confidence. High-confidence matches are applied automatically, medium-confidence matches enter a review queue, and low-confidence matches remain unresolved. Storyboard application resolves the active variant first and only injects reference images for assets that actually exist.

**Tech Stack:** Existing Python/PyQt6 pipeline, `core.asset_context`, `core.asset_image_import`, `workers.py`, `agents.storyboard_generator`, JSON sidecar files, existing LLM client.

---

### Task 1: Variant and timeline data model

**Files:**
- Create: `core/asset_variants.py`
- Modify: `core/asset_context.py`
- Test: `tests/test_asset_variants.py`

- [x] Add tests for variant normalization, persistent ranges, and overlap resolution.
- [x] Implement `AssetVariant` with `variant_id`, `base_name`, `label`, `start_episode`, `start_event`, `start_shot`, `end_episode`, `continuity`, `confidence`, and `match_status`.
- [x] Implement deterministic `active_variant(variants, episode, shot, event_text)` priority: explicit shot range, episode range, then latest prior start.
- [x] Preserve old four-column TXT records as a default variant.
- [x] Run `python -m pytest tests/test_asset_variants.py -q`.

### Task 2: Project timeline index and background matcher

**Files:**
- Create: `core/asset_timeline.py`
- Create: `core/asset_match_queue.py`
- Modify: `core/asset_image_import.py`
- Test: `tests/test_asset_match_queue.py`

- [ ] Add a failing test where an uploaded image named `小红_宴会装.png` maps to formal base `小红`, starts at the event “参加寿宴”, and continues until the next variant.
- [ ] Build a cached timeline index keyed by base asset name and event keywords; invalidate it only when normalized screenplay content changes.
- [ ] Add asynchronous matching returning `pending`, `auto_confirmed`, `needs_confirmation`, or `unresolved` and a confidence score.
- [ ] Use deterministic filename/alias/phase matching first; call the LLM only with the candidate character timeline and the image metadata when deterministic matching is ambiguous.
- [x] Persist review items in `assets/match_review.json` without blocking the upload worker.
- [x] Run focused queue tests.

### Task 3: Asset import worker and review UI

**Files:**
- Modify: `workers.py`
- Modify: `steps/asset_import_dialog.py`
- Test: `tests/test_named_asset_import.py`

- [ ] Keep the existing user input “这是谁” as the identity hint; make phase/event fields optional.
- [ ] Start matching in the background after file copy/upload and emit progress/result signals.
- [ ] Auto-apply only high-confidence matches; display medium/low-confidence review rows with candidate, inferred start episode/event, and confidence.
- [ ] Allow confirmation to change the start episode/event and re-run range validation without re-uploading the image.
- [ ] Keep old import behavior when no timeline or LLM is available.
- [ ] Run asset import regression tests.

### Task 4: Preserve unmatched people and resolve active variants in storyboards

**Files:**
- Modify: `agents/storyboard_generator.py`
- Modify: `workers.py`
- Test: `tests/test_reference_audit.py`, `tests/test_storyboard_batching.py`

- [ ] Separate “textual appearance” from “reference-image injection”; do not delete a person merely because no asset image matches.
- [ ] Keep named minor people (nurse, waiter, family member, onlooker) in `出镜人物` and shot descriptions, while omitting them from LoadImage/CR replacement slots when no image exists.
- [ ] Resolve `active_variant()` by shot episode/event before selecting a reference image.
- [ ] Log unmatched people as `保留文字、无参考图，不上传` and reserve placeholder images only for workflow slots that require them.
- [ ] Run reference and storyboard batching tests.

### Task 5: Real-project dry run and full verification

**Files:**
- Create: `tests/test_real_project_asset_matching.py`
- Verify: project `E:\aigc-mvp-ui11\aigc-mvp-ui\projects\这顿饭我不做东`

- [x] Run a no-network dry run against the project assets and prompts; verify current variants, pending review items, and unmatched textual characters.
- [x] Compile changed modules.
- [x] Run `QT_QPA_PLATFORM=offscreen python -m pytest tests -q`.
- [x] Report auto-confirmed, review-needed, unresolved, and no-reference-but-retained counts.
