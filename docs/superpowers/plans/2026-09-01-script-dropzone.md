# Script Dropzone Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the native script file button with a clickable and draggable upload field.

**Architecture:** A focused `ScriptFileDropzone` component owns the hidden file input and drag state, then emits a validated file to `ProjectsPage`. Existing form state, automatic project naming, and multipart submission remain unchanged.

**Tech Stack:** React 19, TypeScript, CSS, Vitest, Testing Library

---

### Task 1: Define upload behavior with tests

**Files:**
- Modify: `web/tests/pages.test.tsx`

- [ ] Add a test that opens the project dialog, finds the dropzone by accessible label, drops `新剧.txt`, and verifies both `新剧.txt` and the auto-filled project name.
- [ ] Add a test that drops `新剧.pdf` and verifies the unsupported-format error while the project name stays empty.
- [ ] Run `npm test -- --run tests/pages.test.tsx` and confirm the tests fail because the dropzone does not exist.

### Task 2: Implement the dropzone

**Files:**
- Create: `web/src/components/ScriptFileDropzone.tsx`
- Modify: `web/src/pages/ProjectsPage.tsx`
- Modify: `web/src/styles/tokens.css`

- [ ] Implement a label-backed hidden `input[type=file]` accepting `.txt,.docx`, plus `dragenter`, `dragover`, `dragleave`, and `drop` handling.
- [ ] Validate the file extension before calling `onFileChange`; call `onError` for unsupported files.
- [ ] Replace the native input in `ProjectsPage` and reuse one file-selection handler for click and drop paths.
- [ ] Add default, hover, drag-active, selected-file, and visually-hidden input styles.
- [ ] Run `npm test -- --run tests/pages.test.tsx` and confirm all page tests pass.

### Task 3: Verify the full UI

**Files:**
- Test: `web/tests/pages.test.tsx`

- [ ] Run `npm test -- --run` and require zero failures.
- [ ] Run `npm run build` and require exit code zero.
- [ ] Open the local project page, confirm the native button is absent, and verify the full upload field is visible and clickable.

No commit step is included because this workspace is not a Git repository.
