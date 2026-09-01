# Video Generation Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the approved integrated video-generation workbench in the existing React Web app.

**Architecture:** Keep the existing route and API layer, add focused presentation helpers/components for episode navigation, script, shot, asset, preview, and timeline areas, and compose them in `EpisodeStudioPage`. Reduce only the user-facing workflow navigation while retaining backend task compatibility.

**Tech Stack:** React 19, React Router 7, TypeScript 5.8, Vite 7, Vitest, Testing Library.

---

### Task 1: Lock the new navigation behavior with tests

**Files:**
- Modify: `web/tests/app-shell.test.tsx`
- Modify: `web/tests/pages.test.tsx`
- Modify: `web/tests/dashboard.test.tsx`

- [ ] **Step 1: Write failing expectations**

```tsx
expect(labels).toEqual(['创建项目', '资产生成', '视频生成', '设置'])
expect(screen.getByRole('link', { name: /视频生成/ })).toHaveAttribute('aria-current', 'step')
expect(navigateTarget).toContain('?stage=asset')
```

- [ ] **Step 2: Run the focused tests and confirm they fail for the old seven-step workflow**

Run: `pnpm test -- tests/app-shell.test.tsx tests/pages.test.tsx tests/dashboard.test.tsx`

Expected: FAIL because the old navigation still includes prompt, shot matching, and editing.

- [ ] **Step 3: Implement the minimal workflow and redirect changes**

```ts
export const WORKFLOW_STEPS = [
  { id: 'project', label: '创建项目' },
  { id: 'asset', label: '资产生成' },
  { id: 'video', label: '视频生成' },
  { id: 'settings', label: '设置' },
]
```

- [ ] **Step 4: Run the focused tests and confirm they pass**

Run: `pnpm test -- tests/app-shell.test.tsx tests/pages.test.tsx tests/dashboard.test.tsx`

Expected: PASS.

### Task 2: Add script and selected-shot view helpers

**Files:**
- Create: `web/src/features/video-generation/model.ts`
- Create: `web/tests/video-generation-model.test.ts`

- [ ] **Step 1: Write failing helper tests**

```ts
expect(shotNumberFromId('shot-003')).toBe(3)
expect(findShotMatch(manifest, 'shot-003')?.shot).toBe(3)
expect(scriptSections('镜头 001\n内容\n镜头 002\n内容')).toHaveLength(2)
```

- [ ] **Step 2: Run and confirm module-not-found failure**

Run: `pnpm test -- tests/video-generation-model.test.ts`

Expected: FAIL because the helper module does not exist.

- [ ] **Step 3: Implement pure helpers**

```ts
export function shotNumberFromId(value: string): number | null {
  const match = value.match(/\d+/)
  return match ? Number(match[0]) : null
}
```

- [ ] **Step 4: Run helper tests**

Run: `pnpm test -- tests/video-generation-model.test.ts`

Expected: PASS.

### Task 3: Lock the integrated workbench structure with a page test

**Files:**
- Modify: `web/tests/episode-studio.test.tsx`

- [ ] **Step 1: Add failing layout and synchronization assertions**

```tsx
expect(screen.getByRole('navigation', { name: '分集' })).toBeInTheDocument()
expect(screen.getByRole('region', { name: '分集剧本' })).toBeInTheDocument()
expect(screen.getByRole('region', { name: '镜头脚本' })).toBeInTheDocument()
expect(screen.getByRole('region', { name: '资产匹配' })).toBeInTheDocument()
expect(screen.getByRole('region', { name: '视频预览' })).toBeInTheDocument()
expect(screen.getByRole('region', { name: '视频轨道' })).toBeInTheDocument()
```

- [ ] **Step 2: Run and confirm failure against the old editor layout**

Run: `pnpm test -- tests/episode-studio.test.tsx`

Expected: FAIL because the page still renders the old two-column editor.

- [ ] **Step 3: Add selected-shot and episode-switch expectations**

Use URL-aware fetch fixtures for episodes, timeline, shot script, videos, preview, and exports so the test is stable regardless of polling effect order.

- [ ] **Step 4: Re-run and preserve the expected red state**

Run: `pnpm test -- tests/episode-studio.test.tsx`

Expected: FAIL only for missing workbench UI.

### Task 4: Implement focused workbench panels and compose the page

**Files:**
- Create: `web/src/features/video-generation/EpisodeRail.tsx`
- Create: `web/src/features/video-generation/EpisodeScriptPanel.tsx`
- Create: `web/src/features/video-generation/ShotScriptPanel.tsx`
- Create: `web/src/features/video-generation/AssetMatchPanel.tsx`
- Modify: `web/src/pages/EpisodeStudioPage.tsx`

- [ ] **Step 1: Add the episode loader and default selection behavior**

```tsx
const episodesLoader = useCallback(() => fetchEpisodes(projectName), [projectName])
useEffect(() => {
  if (!selectedId && timeline) setSelectedId(firstActiveSegmentId(timeline))
}, [selectedId, timeline])
```

- [ ] **Step 2: Render the approved column structure**

```tsx
<div className="video-generation-layout">
  <EpisodeRail />
  <EpisodeScriptPanel />
  <main className="video-production-area">
    <div className="video-production-upper">
      <ShotScriptPanel />
      <AssetMatchPanel />
      <VideoPreviewPanel />
    </div>
    <section aria-label="视频轨道">...</section>
  </main>
</div>
```

- [ ] **Step 3: Integrate existing timeline editing and export actions into the bottom panel**

Keep `TimelineEditor`, `SegmentInspector`, `saveTimeline`, preview refresh, regeneration, replacement, delete/restore, and export handlers connected to their existing APIs.

- [ ] **Step 4: Run the page tests**

Run: `pnpm test -- tests/episode-studio.test.tsx tests/timeline-editor.test.tsx`

Expected: PASS.

### Task 5: Apply the approved visual layout

**Files:**
- Modify: `web/src/styles/tokens.css`

- [ ] **Step 1: Add namespaced workbench styles**

```css
.video-generation-layout { display: grid; grid-template-columns: 188px minmax(270px, .86fr) minmax(700px, 2.35fr); }
.video-production-upper { display: grid; grid-template-columns: minmax(245px, .92fr) minmax(220px, .82fr) minmax(330px, 1.24fr); }
.video-timeline-panel { grid-column: 1 / -1; }
```

- [ ] **Step 2: Remove the obsolete old studio two-column layout rules**

Delete `.studio-grid`, `.studio-left`, and `.studio-right` rules after the new page no longer references them.

- [ ] **Step 3: Run component and page tests**

Run: `pnpm test -- tests/episode-studio.test.tsx tests/components.test.tsx tests/timeline-editor.test.tsx`

Expected: PASS.

### Task 6: Full verification and copy-ready build

**Files:**
- Generated: `web/dist/**`

- [ ] **Step 1: Run the full Web test suite**

Run: `pnpm test`

Expected: all tests pass.

- [ ] **Step 2: Run the production build**

Run: `pnpm build`

Expected: TypeScript and Vite build exit with status 0.

- [ ] **Step 3: Audit removed user-facing terminology**

Run: `rg -n '音频生成|音色|分镜图片|转视频|剪辑拼装' web/src web/tests`

Expected: no obsolete workflow labels; “剪辑拼装” may only appear in historical docs, not the active Web UI.

- [ ] **Step 4: Verify the final change scope**

Because this copied directory has no Git metadata or GitNexus index, list changed files and report that `detect_changes()` and commits are unavailable instead of claiming Git-based verification.

