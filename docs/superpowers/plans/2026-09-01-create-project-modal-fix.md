# 创建项目悬浮窗修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将创建项目界面改为真正覆盖浏览器视口的悬浮窗，确保剧本文件选择器始终可见，并消除未被遮罩的大块白色区域。

**Architecture:** 新建 `CreateProjectModal` 组件，通过 React Portal 渲染到 `document.body`，彻底脱离 `.page` 的 transform 动画和 `.shell-main` 的滚动裁切。`ProjectsPage` 保留全部表单状态与提交逻辑，仅把现有表单作为 children 传入 Modal。

**Tech Stack:** React 19、TypeScript、React DOM Portal、Vitest、Testing Library、CSS

---

### Task 1: Portal 悬浮窗行为

**Files:**
- Create: `web/src/components/CreateProjectModal.tsx`
- Modify: `web/src/pages/ProjectsPage.tsx`
- Modify: `web/src/styles/tokens.css`
- Test: `web/tests/pages.test.tsx`

- [ ] **Step 1: 写 Portal 与关闭行为的失败测试**

在 `web/tests/pages.test.tsx` 新增测试：

```tsx
it('创建项目以全屏 Portal 弹窗展示并支持遮罩关闭', async () => {
  mockFetch({ projects: [] })
  const { container } = render(<MemoryRouter><ProjectsPage /></MemoryRouter>)
  fireEvent.click(screen.getByText('新建项目'))

  const dialog = await screen.findByRole('dialog', { name: '创建项目' })
  const backdrop = screen.getByTestId('create-project-backdrop')
  expect(document.body).toContainElement(backdrop)
  expect(container.querySelector('.project-create-backdrop')).toBeNull()
  expect(screen.getByLabelText('剧本文件')).toBeVisible()
  expect(document.body.style.overflow).toBe('hidden')

  fireEvent.click(dialog)
  expect(screen.getByRole('dialog', { name: '创建项目' })).toBeTruthy()
  fireEvent.click(backdrop)
  expect(screen.queryByRole('dialog', { name: '创建项目' })).toBeNull()
  expect(document.body.style.overflow).toBe('')
})
```

- [ ] **Step 2: 运行测试并确认 RED**

Run:

```powershell
cd web
npm test -- --run tests/pages.test.tsx
```

Expected: FAIL，因为当前弹窗仍位于 `.page` 内，没有 dialog 语义、Portal、遮罩关闭和背景滚动锁定。

- [ ] **Step 3: 实现最小 Portal 组件**

创建 `CreateProjectModal.tsx`：

```tsx
import { useEffect, type MouseEvent, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

type Props = { title: string; onClose: () => void; children: ReactNode }

export function CreateProjectModal({ title, onClose, children }: Props) {
  useEffect(() => {
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = previous }
  }, [])

  function handleBackdrop(event: MouseEvent<HTMLDivElement>) {
    if (event.target === event.currentTarget) onClose()
  }

  return createPortal(
    <div className="project-create-backdrop" data-testid="create-project-backdrop" onClick={handleBackdrop}>
      <section className="project-create-dialog glass-panel glass-strong" role="dialog" aria-modal="true" aria-label={title}>
        {children}
      </section>
    </div>,
    document.body,
  )
}
```

在 `ProjectsPage.tsx` 中用 `CreateProjectModal` 包裹原表单，并让“取消”调用统一的关闭函数。保留文件选择、自动命名和创建逻辑。

- [ ] **Step 4: 调整视口与滚动样式**

在 `tokens.css` 中保证：

```css
.project-create-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: grid;
  place-items: center;
  min-width: 100vw;
  min-height: 100dvh;
  padding: 24px;
  overflow-y: auto;
  background: rgba(15, 23, 42, 0.48);
}
.project-create-dialog {
  width: min(720px, 100%);
  max-height: calc(100dvh - 48px);
  overflow-y: auto;
  padding: var(--space-4) var(--space-5);
}
```

- [ ] **Step 5: 运行聚焦测试并确认 GREEN**

Run:

```powershell
cd web
npm test -- --run tests/pages.test.tsx
```

Expected: `pages.test.tsx` 全部通过。

- [ ] **Step 6: 运行完整前端验证**

Run:

```powershell
cd web
npm test -- --run
npm run build
```

Expected: 全部 Vitest 测试通过，Vite 构建成功。

- [ ] **Step 7: 范围审计**

确认只修改弹窗组件、项目页、弹窗样式、测试和本次文档；由于当前副本没有 Git/GitNexus 元数据，用 `rg` 引用扫描和测试结果替代 `detect_changes()`。
