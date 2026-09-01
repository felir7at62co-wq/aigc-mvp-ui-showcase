import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { DashboardPage } from '../src/pages/DashboardPage'

function mockFetchSequence(responses: unknown[]) {
  const queue = [...responses]
  vi.stubGlobal('fetch', vi.fn(async () => {
    const payload = queue.shift() ?? { projects: [] }
    return { ok: true, status: 200, json: async () => payload } as Response
  }))
}

function renderDashboard(entry = '/projects/P') {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/projects/:projectName" element={<DashboardPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('DashboardPage', () => {
  it('渲染阶段状态卡与任务队列', async () => {
    mockFetchSequence([
      { name: 'P', episode_count: 8, episodes: { total: 8, by_status: {} }, steps: {
        import_script: { status: 'completed' },
        prompt: { status: 'running' },
        asset: { status: 'pending' },
        shot_match: { status: 'pending' },
        video: { status: 'pending' },
        timeline: { status: 'pending' },
        preview: { status: 'pending' },
        export: { status: 'pending' },
      } },
      { tasks: [{ id: 't1', project: 'P', step: 'prompt', episode_ids: ['01'], status: 'running', created_at: 0, finished_at: null, error: '', results: {}, failures: {} }] },
      { episodes: [{ episode_id: '01' }, { episode_id: '02' }] },
    ])
    renderDashboard()
    await waitFor(() => expect(screen.getByText('剧本导入')).toBeTruthy())
    expect(screen.getByText('剧本导入').closest('.phase-item')).toHaveAttribute(
      'aria-current',
      'step',
    )
    // 摘要卡标题与状态徽章都可能出现"已完成/进行中"，用 getAllByText 断言存在
    expect(screen.getAllByText('已完成').length).toBeGreaterThan(0)
    expect(screen.getAllByText('进行中').length).toBeGreaterThan(0)
    await waitFor(() => expect(screen.getByText('t1')).toBeTruthy())
    expect(screen.getByText('prompt')).toBeTruthy()
    await waitFor(() => expect(screen.getByText('第 01 集')).toBeTruthy())
    expect(screen.getByRole('link', { name: /第 01 集/ })).toHaveAttribute(
      'href', '/projects/P/episodes/01',
    )
    vi.unstubAllGlobals()
  })

  it('显示集数摘要', async () => {
    mockFetchSequence([
      { name: 'P', episode_count: 8, episodes: { total: 8, by_status: { pending: 8 } }, steps: {} },
      { tasks: [] },
      { episodes: [] },
    ])
    renderDashboard()
    await waitFor(() => expect(screen.getByText('8 集')).toBeTruthy())
    vi.unstubAllGlobals()
  })

  it('根据侧栏 stage 参数高亮中央生产阶段且不显示音频阶段', async () => {
    mockFetchSequence([
      { name: 'P', episode_count: 1, episodes: { total: 1, by_status: {} }, steps: {
        video: { status: 'pending' },
        shot_match: { status: 'pending' },
        asset: { status: 'running' },
        prompt: { status: 'completed' },
        import_script: { status: 'completed' },
      } },
      { tasks: [] },
      { episodes: [{ episode_id: '01' }] },
    ])

    renderDashboard('/projects/P?stage=asset')

    const assetLabel = await screen.findByText('资产生成')
    expect(assetLabel.closest('.phase-item')).toHaveAttribute('aria-current', 'step')
    expect(
      within(assetLabel.closest('.phase-item') as HTMLElement).getByRole('link', { name: '进入' }),
    ).toHaveAttribute('href', '/projects/P/assets')
    const phaseCard = screen.getByText('生产阶段').closest('.phase-card')
    expect(
      Array.from(phaseCard!.querySelectorAll('.phase-label')).map((item) => item.textContent),
    ).toEqual(['剧本导入', '资产生成', '视频生成'])
    expect(screen.queryByText('音频生成')).not.toBeInTheDocument()
    expect(screen.queryByText(/PPT.*分镜/)).not.toBeInTheDocument()
    expect(screen.queryByText('提示词提取')).not.toBeInTheDocument()
    expect(screen.queryByText('镜头脚本与匹配')).not.toBeInTheDocument()
    expect(screen.queryByText('时间线')).not.toBeInTheDocument()
    expect(screen.queryByText('成片预览')).not.toBeInTheDocument()
    expect(screen.queryByText('导出交付')).not.toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  it('视频生成阶段聚焦集列表', async () => {
    mockFetchSequence([
      { name: 'P', episode_count: 1, episodes: { total: 1, by_status: {} }, steps: {} },
      { tasks: [] },
      { episodes: [{ episode_id: '01' }] },
    ])

    renderDashboard('/projects/P?stage=video')

    await screen.findByText('第 01 集')
    expect(screen.getByText('集列表').closest('.episodes-card')).toHaveClass('episodes-card-focused')
    vi.unstubAllGlobals()
  })

  it('设置步骤显示明确的配置占位说明', async () => {
    mockFetchSequence([
      { name: 'P', episode_count: 1, episodes: { total: 1, by_status: {} }, steps: {} },
      { tasks: [] },
      { episodes: [] },
    ])

    renderDashboard('/projects/P?stage=settings')

    expect(await screen.findByText('项目设置')).toBeInTheDocument()
    expect(screen.getByText(/暂由项目配置文件管理/)).toBeInTheDocument()
    vi.unstubAllGlobals()
  })
})
