import { render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { vi } from 'vitest'
import { AppShell } from '../src/app-shell/AppShell'

vi.mock('../src/api/projects', () => ({
  fetchProjects: vi.fn().mockResolvedValue([
    {
      name: 'demo-project',
      created_at: '2026-08-25T00:00:00Z',
      updated_at: '2026-08-25T00:00:00Z',
    },
  ]),
}))

function renderShell(entry: string) {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/" element={<AppShell />}>
          <Route path="projects/:projectName" element={<div>项目工作区</div>} />
          <Route path="projects/:projectName/assets" element={<div>资产生成页</div>} />
          <Route path="projects/:projectName/video" element={<div>视频生成入口</div>} />
          <Route path="projects/:projectName/settings" element={<div>设置页</div>} />
          <Route
            path="projects/:projectName/episodes/:episodeId"
            element={<div>单集编辑台</div>}
          />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

describe('AppShell', () => {
  it('展示精简后的四个流程步骤', async () => {
    renderShell('/projects/demo-project?stage=asset')

    const navigation = await screen.findByRole('navigation', { name: '流程步骤' })
    const labels = within(navigation)
      .getAllByRole('link')
      .map((link) => link.textContent?.replace(/^\d+/, '').trim())

    expect(labels).toEqual([
      '创建项目',
      '资产生成',
      '视频生成',
      '设置',
    ])
    expect(navigation).not.toHaveTextContent('音频生成')
    expect(navigation).not.toHaveTextContent('PPT')
    expect(screen.getByLabelText('当前项目')).toBeInTheDocument()
    expect(screen.getByText('当前项目：demo-project')).toBeInTheDocument()
    expect(screen.getByText('当前步骤：资产生成')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /资产生成/ })).toHaveAttribute(
      'href',
      '/projects/demo-project/assets',
    )
    expect(screen.getByRole('link', { name: /视频生成/ })).toHaveAttribute(
      'href',
      '/projects/demo-project/video',
    )
    expect(screen.getByRole('link', { name: /设置/ })).toHaveAttribute(
      'href',
      '/projects/demo-project/settings',
    )
  })

  it('进入单集工作台时自动高亮视频生成', async () => {
    renderShell('/projects/demo-project/episodes/ep-001')

    expect(await screen.findByRole('link', { name: /视频生成/ })).toHaveAttribute(
      'aria-current',
      'step',
    )
  })

  it('在视频和设置独立页面高亮对应步骤', async () => {
    const { unmount } = renderShell('/projects/demo-project/video')
    expect(await screen.findByRole('link', { name: /视频生成/ })).toHaveAttribute(
      'aria-current',
      'step',
    )
    unmount()

    renderShell('/projects/demo-project/settings')
    expect(await screen.findByRole('link', { name: /设置/ })).toHaveAttribute(
      'aria-current',
      'step',
    )
  })
})
