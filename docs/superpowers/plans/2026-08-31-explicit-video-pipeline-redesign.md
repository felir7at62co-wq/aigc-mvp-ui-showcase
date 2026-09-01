# Explicit Video Pipeline Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the explicitly requested non-Agent workflow: simplified project creation, direct video/settings pages, Yunying media generation, 15-second batch cutting, and synchronized shot-script/timeline editing.

**Architecture:** Store project-specific video preferences in a small JSON settings file while keeping API credentials in environment variables only. Replace RunningHub and the legacy video client with one Yunying-compatible media client, group shots into 15-second generation batches, and split each completed batch into per-shot clips with FFmpeg. Keep the existing integrated episode studio as the video workspace and make script/timeline selection bidirectional.

**Tech Stack:** Python/Flask, React/TypeScript/Vite, pytest, Vitest/Testing Library, FFmpeg, OpenAI-compatible HTTP APIs.

---

### Task 1: Direct workflow navigation

**Files:**
- Modify: `web/src/app-shell/workflow.ts`
- Modify: `web/src/App.tsx`
- Create: `web/src/pages/VideoEntryPage.tsx`
- Create: `web/src/pages/SettingsPage.tsx`
- Test: `web/src/app-shell/workflow.test.ts`
- Test: `web/src/App.test.tsx`

- [ ] **Step 1: Write failing route tests**

Assert that `workflowStepHref("video", name)` returns `/projects/<name>/video`, settings returns `/projects/<name>/settings`, the video entry resolves the first episode, and settings renders a dedicated page.

- [ ] **Step 2: Run tests and confirm red**

Run: `npm test -- --run web/src/app-shell/workflow.test.ts web/src/App.test.tsx`

Expected: failures for missing direct routes.

- [ ] **Step 3: Add direct pages and route definitions**

Add `/projects/:projectName/video` and `/projects/:projectName/settings`. The video entry fetches episodes and redirects to the first `/episodes/:episodeId`; the settings page loads and saves project settings.

- [ ] **Step 4: Run focused tests and confirm green**

Run: `npm test -- --run web/src/app-shell/workflow.test.ts web/src/App.test.tsx`

Expected: all focused tests pass.

### Task 2: Project-level media settings and simplified creation

**Files:**
- Create: `core/project_settings.py`
- Modify: `web_api/projects.py`
- Modify: `web/src/api/projects.ts`
- Modify: `web/src/pages/ProjectsPage.tsx`
- Modify: `web/src/styles.css`
- Test: `tests/test_project_settings.py`
- Test: `tests/test_web_api_projects.py`
- Test: `web/src/pages/ProjectsPage.test.tsx`

- [ ] **Step 1: Write failing persistence and UI tests**

Cover defaults (`seedance-2-0-official`, `gpt-image-2-official`, `reference`, `9:16`, `720p`, `15`), validation, filename-derived editable name, absence of episode/shot/model/mode inputs, and submission of aspect ratio, resolution, and optional prompt prefix.

- [ ] **Step 2: Run focused tests and confirm red**

Run: `python -m pytest tests/test_project_settings.py tests/test_web_api_projects.py -q`

Run: `npm test -- --run web/src/pages/ProjectsPage.test.tsx`

Expected: failures for missing settings persistence and simplified modal.

- [ ] **Step 3: Implement settings persistence and API**

Create validated load/save helpers for `<project>/project_settings.json`; extend project creation FormData; add GET/PUT project settings endpoints; never return or persist an API key.

- [ ] **Step 4: Implement the creation modal**

Auto-fill project name from the selected script filename while allowing edits. Show only script, name, aspect ratio, resolution, and optional global shot prompt prefix. Keep model, reference mode, episode count, shot count, and batch duration hidden and defaulted.

- [ ] **Step 5: Run focused tests and confirm green**

Run both commands from Step 2 and expect all tests to pass.

### Task 3: Yunying-compatible media client

**Files:**
- Create: `core/yunying_media_client.py`
- Modify: `core/config.py`
- Modify: `config.yaml`
- Modify: `.env.example`
- Test: `tests/test_yunying_media_client.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing client tests**

Mock HTTP calls and assert `/files`, `/images/generations`, `/videos/generations`, and `/tasks/{id}` contracts; verify the base URL is normalized once, final output URLs are extracted, and missing `YUNYING_API_KEY` yields a safe configuration error without exposing a secret.

- [ ] **Step 2: Run focused tests and confirm red**

Run: `python -m pytest tests/test_yunying_media_client.py tests/test_config.py -q`

Expected: failures because the Yunying client/config do not exist.

- [ ] **Step 3: Implement the client and configuration**

Use `YUNYING_BASE_URL` with default `https://wy6688.token6688.com/v1` and `YUNYING_API_KEY` with no source default. Implement multipart upload, synchronous image generation, asynchronous video task polling, timeout handling, and streamed download. Set default models to the official Seedance 2.0 and GPT Image 2 variants.

- [ ] **Step 4: Run focused tests and confirm green**

Run the Step 2 command and expect all tests to pass.

### Task 4: Replace RunningHub asset generation

**Files:**
- Create: `agents/yunying_asset_generator.py`
- Modify: `web_api/operations.py`
- Modify: `core/tool_registry.py`
- Test: `tests/test_yunying_asset_generator.py`
- Test: `tests/test_web_api_operations.py`

- [ ] **Step 1: Write failing asset-generation tests**

Assert that selected character/scene/prop prompts call GPT Image 2 through the Yunying client, save generated images into the existing asset structure, and preserve manifest/UI compatibility.

- [ ] **Step 2: Run focused tests and confirm red**

Run: `python -m pytest tests/test_yunying_asset_generator.py tests/test_web_api_operations.py -q`

Expected: failures for the missing Yunying generator.

- [ ] **Step 3: Implement and wire the generator**

Generate one image per selected asset using project settings and existing prompt extraction. Decode `b64_json` or download `url`, save atomically, and update the existing asset manifests. Replace active `RunningHubClient`/`AssetGenerator` imports in operations.

- [ ] **Step 4: Run focused tests and confirm green**

Run the Step 2 command and expect all tests to pass.

### Task 5: Fifteen-second generation batches and FFmpeg splitting

**Files:**
- Create: `core/video_batches.py`
- Modify: `core/ffmpeg_runner.py`
- Modify: `web_api/operations.py`
- Test: `tests/test_video_batches.py`
- Test: `tests/test_ffmpeg_runner.py`
- Test: `tests/test_web_api_operations.py`

- [ ] **Step 1: Write failing batching tests**

Cover complete shot-block parsing, duration extraction, consecutive grouping up to 15 seconds, batch prompt construction with the optional prefix, reference asset collection, one API call per batch, and per-shot output names.

- [ ] **Step 2: Write failing FFmpeg split tests**

Mock process execution and assert each shot is cut from its cumulative start time for its requested duration, with generated trailing footage discarded.

- [ ] **Step 3: Run focused tests and confirm red**

Run: `python -m pytest tests/test_video_batches.py tests/test_ffmpeg_runner.py tests/test_web_api_operations.py -q`

Expected: failures for missing batching/splitting behavior.

- [ ] **Step 4: Implement batching and splitting**

Generate every batch at exactly 15 seconds in fixed reference mode. Upload unique matched asset images, download each batch to a private batch directory, and use the bundled FFmpeg runner to create one clip per shot in the existing `web_video/<episode>` output directory.

- [ ] **Step 5: Run focused tests and confirm green**

Run the Step 3 command and expect all tests to pass.

### Task 6: Complete shot scripts and timeline synchronization

**Files:**
- Modify: `web/src/pages/EpisodeStudioPage.tsx`
- Modify: `web/src/features/video-generation/ShotScriptPanel.tsx`
- Modify: `web/src/features/video-generation/model.ts`
- Modify: `web/src/components/TimelineEditor.tsx`
- Modify: `web/src/styles.css`
- Test: `web/src/pages/EpisodeStudioPage.test.tsx`
- Test: `web/src/features/video-generation/ShotScriptPanel.test.tsx`

- [ ] **Step 1: Write failing synchronization tests**

Assert that each panel item shows the full shot block with a subtle separator; selecting a timeline segment calls `scrollIntoView` for the matching script item; manual script scrolling selects the matching timeline segment without a feedback loop.

- [ ] **Step 2: Run focused tests and confirm red**

Run: `npm test -- --run web/src/pages/EpisodeStudioPage.test.tsx web/src/features/video-generation/ShotScriptPanel.test.tsx`

Expected: failures for missing full-block display and synchronization.

- [ ] **Step 3: Implement bidirectional synchronization**

Drive the script panel from parsed complete shot sections, map each shot number to its timeline segment, use refs for programmatic scrolling, and update timeline selection when the script viewport changes. Keep the three upper columns and lower track layout.

- [ ] **Step 4: Run focused tests and confirm green**

Run the Step 2 command and expect all tests to pass.

### Task 7: Remove RunningHub and obsolete workflow surfaces

**Files:**
- Delete: `core/runninghub_client.py`
- Delete or rewrite: `core/tools/runninghub_tools.py`
- Delete or rewrite: `core/skills/asset_generate_skill.py`
- Modify: `agents/storyboard_generator.py`
- Modify: `core/config.py`
- Modify: `config.yaml`
- Modify: `.env.example`
- Modify: affected tests and package manifests

- [ ] **Step 1: Add a source audit test/check**

Search executable source and configuration for `RunningHub`, `runninghub`, workflow IDs used only for generation, audio, voice, storyboard-image generation, and obsolete conversion/editing surfaces.

- [ ] **Step 2: Remove obsolete implementations and references**

Delete unreferenced RunningHub modules through patch edits, migrate any still-reachable callers to Yunying or remove them from registration, and keep episode splitting/import and integrated timeline editing intact.

- [ ] **Step 3: Re-run the audit**

Run: `rg -n -i "runninghub|audio generation|voice|音色|分镜图片|转视频" . -g '!node_modules/**' -g '!dist/**' -g '!docs/**'`

Expected: no executable generation/config/UI references; historical docs may remain excluded.

### Task 8: Full verification and runtime smoke test

**Files:**
- Modify only if verification exposes a regression.

- [ ] **Step 1: Run the full backend suite**

Run: `python -m pytest -q`

Expected: all tests pass.

- [ ] **Step 2: Run frontend tests and type/build checks**

Run: `npm test -- --run`

Run: `npm run build`

Expected: all tests pass and the production bundle builds.

- [ ] **Step 3: Run route/API smoke checks**

Verify project creation, settings GET/PUT, `/video` redirect, asset page, integrated episode page, and missing-key error behavior through localhost HTTP without invoking paid generation.

- [ ] **Step 4: Audit changed scope**

Because GitNexus and Git metadata are unavailable in this copy, enumerate modified files and search changed executable code for leaked secrets and obsolete providers. Confirm the user-provided key is absent from the workspace.

