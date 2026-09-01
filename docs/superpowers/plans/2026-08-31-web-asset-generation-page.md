# Web Asset Generation Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a functional card-based Web asset generation page and enforce the production order “剧本导入 → 资产生成 → 视频生成”.

**Architecture:** Add read/upload endpoints to the existing asset blueprint, preserving `core.asset_catalog` and `core.asset_image_import` as the data authority. Add a dedicated React route whose state is loaded from the API and whose generation actions use the existing task queue. Keep selection as page state and pass selected category/names through task options.

**Tech Stack:** Flask, Python pathlib/Pillow-backed asset import, React 19, TypeScript, React Router, Vitest/Testing Library, pytest.

---

### Task 1: Asset list and upload API

**Files:**
- Modify: `web_api/assets.py`
- Test: `tests/test_api_assets.py`

- [ ] Add failing tests proving `GET /api/projects/P/assets` returns the union of prompt records and image-only assets, and upload converts a valid image to `assets/<category>/<name>.png`.
- [ ] Run `python -m pytest tests/test_api_assets.py -q` and verify the new tests fail with 405/404.
- [ ] Add `list_assets()` using `load_or_build_asset_context`, merge each category with files from `VALID_EXTENSIONS`, and return relative `image_path` values.
- [ ] Add `upload_asset_image()` using a temporary upload file and `import_asset_image`; reject missing file, invalid category and invalid image with 400.
- [ ] Re-run `python -m pytest tests/test_api_assets.py -q` and verify all tests pass.

### Task 2: Filtered asset generation

**Files:**
- Modify: `web_api/operations.py`
- Test: `tests/test_api_assets.py`

- [ ] Add a failing unit test with a fake generator proving `options={"category":"character","asset_names":["主角"]}` excludes all other records.
- [ ] Run the focused pytest test and verify it fails because `op_asset` currently processes every missing asset.
- [ ] In `op_asset`, normalize the optional category and name filters, then apply them before calculating `missing`; preserve all-category behavior when options are absent.
- [ ] Re-run the focused test and existing Web API tests.

### Task 3: Workflow route and fixed stage order

**Files:**
- Modify: `web/src/app-shell/workflow.ts`
- Modify: `web/src/App.tsx`
- Modify: `web/src/pages/ProjectsPage.tsx`
- Modify: `web/src/pages/DashboardPage.tsx`
- Test: `web/tests/app-shell.test.tsx`
- Test: `web/tests/pages.test.tsx`
- Test: `web/tests/dashboard.test.tsx`

- [ ] Add failing tests proving the asset navigation link is `/projects/P/assets`, project creation redirects there, and phase labels render in import/asset/video order regardless of API object order.
- [ ] Run the three focused Vitest files and verify failures match the missing route/order behavior.
- [ ] Route asset workflow links to the dedicated path, detect `/assets` as active asset state, register `AssetGenerationPage`, redirect creation to it, and render Dashboard stages from `['import_script','asset','video']` rather than `Object.entries()`.
- [ ] Re-run the focused tests and verify they pass.

### Task 4: Frontend asset API and page model

**Files:**
- Modify: `web/src/api/types.ts`
- Modify: `web/src/api/projects.ts`
- Create: `web/src/features/assets/model.ts`
- Test: `web/tests/asset-model.test.ts`
- Test: `web/tests/api.test.ts`

- [ ] Add failing tests for category labels, selected-name toggling, API paths, JSON CRUD payloads and multipart upload.
- [ ] Run the focused tests and verify failures are caused by missing exports.
- [ ] Add `AssetCategory`, `AssetRecord`, `AssetCatalog`, list/create/update/delete/upload functions, and a pure `toggleAssetSelection` helper.
- [ ] Re-run the focused tests.

### Task 5: Functional asset generation page

**Files:**
- Create: `web/src/features/assets/AssetCard.tsx`
- Create: `web/src/features/assets/AssetEditorDialog.tsx`
- Create: `web/src/pages/AssetGenerationPage.tsx`
- Test: `web/tests/asset-generation-page.test.tsx`

- [ ] Add failing tests for the three tabs, real cards, add card, select/all/none, edit/delete/upload, and selected generation task options.
- [ ] Run the page test and verify it fails because the page/components do not exist.
- [ ] Implement polling catalog/tasks, category-local selection, CRUD modal, hidden image file inputs, task submission and user-visible messages. Disable generation when nothing is selected.
- [ ] Re-run the page test until green.

### Task 6: Asset page visual layout

**Files:**
- Modify: `web/src/styles/tokens.css`

- [ ] Add namespaced `.asset-generation-*` styles matching the reference: dense toolbar, tab strip, bordered management panel, horizontally responsive card grid, selected blue outline, image-first cards and dark/light token compatibility.
- [ ] Run TypeScript and page tests to ensure markup remains accessible.

### Task 7: Final verification

**Files:**
- Verify all changed files.

- [ ] Run `python -m pytest tests/test_api_assets.py -q`.
- [ ] Run `web/node_modules/.bin/vitest.cmd run` from `web`.
- [ ] Run `web/node_modules/.bin/tsc.cmd -b` from `web`.
- [ ] Run `web/node_modules/.bin/vite.cmd build` from `web`.
- [ ] Verify the development UI and API return HTTP 200.
- [ ] Run terminology and route audits with `rg`.

This copied workspace has no `.git` directory, so commit steps and GitNexus `detect_changes()` are unavailable; files remain in place for direct copying.
