import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { EpisodeStudioPage } from '../src/pages/EpisodeStudioPage'

const timeline = {
  episode_id: '01',
  version: 1,
  fps: 30,
  width: 1080,
  height: 1920,
  segments: [
    {
      id: '01-001',
      shot_id: 'shot-001',
      source_video: 'a.mp4',
      prompt: 'first shot',
      asset_ids: [],
      trim_in: 0,
      trim_out: 5,
      order: 0,
      selected_version: 'v1',
      deleted: false,
      transition_to_next: { type: 'hard', duration: 0 },
    },
    {
      id: '01-002',
      shot_id: 'shot-002',
      source_video: 'b.mp4',
      prompt: 'second shot',
      asset_ids: [],
      trim_in: 0,
      trim_out: 4,
      order: 1,
      selected_version: 'v1',
      deleted: false,
      transition_to_next: { type: 'hard', duration: 0 },
    },
  ],
  preview_video: '',
  jianying_project: '',
}

function response(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

function mockFetchSequence(responses: Array<{ body: unknown; status?: number }>) {
  const queue = [...responses]
  const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => {
    const next = queue.shift() ?? { body: {} }
    return response(next.body, next.status)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function renderStudio() {
  return render(
    <MemoryRouter initialEntries={['/projects/P/episodes/01']}>
      <Routes>
        <Route path="/projects/:projectName/episodes/:episodeId" element={<EpisodeStudioPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

function initialResponses(first: { body: unknown; status?: number } = { body: timeline }) {
  return [
    first,
    { body: { status: 'completed', preview_path: 'exports/01_preview.mp4', error: '', updated_at: '', metadata: {} } },
    { body: { episodes: { '01': { status: 'pending', output_path: '', error: '' } } } },
    { body: {
      episode_id: '01',
      script: '镜头1：\n画面描述：first shot\n\n镜头2：\n画面描述：second shot',
      match: {
        version: 1,
        episode: '01',
        shots: [
          {
            shot: 1,
            characters: [{ input: '沈砚', name: '沈砚', matched: true }],
            scene: { input: '老街', name: '老街', matched: true },
            props: [{ input: '长柄伞', name: '长柄伞', matched: true }],
          },
        ],
      },
    } },
    { body: {
      episodes: [
        { episode_id: '01', marker: '第一集', line_range: [1, 20], shot_match_status: 'completed' },
        { episode_id: '02', marker: '第二集', line_range: [21, 40], shot_match_status: 'pending' },
      ],
    } },
  ]
}

describe('EpisodeStudioPage', () => {
  it('renders the integrated episode, script, production, and timeline layout', async () => {
    mockFetchSequence(initialResponses())
    renderStudio()

    const episodeNavigation = await screen.findByRole('navigation', { name: '分集' })
    expect(within(episodeNavigation).getByRole('link', { name: /第 02 集/ })).toHaveAttribute(
      'href',
      '/projects/P/episodes/02',
    )
    expect(screen.getByRole('region', { name: '分集剧本' })).toBeTruthy()
    expect(screen.getByRole('region', { name: '镜头脚本' })).toBeTruthy()
    expect(screen.getByRole('region', { name: '资产匹配' })).toBeTruthy()
    expect(screen.getByRole('region', { name: '视频预览' })).toBeTruthy()
    expect(screen.getByRole('region', { name: '视频轨道' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '生成镜头脚本' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '更新资产匹配' })).toBeTruthy()
    expect(screen.getByText(/镜头1：/)).toHaveTextContent('画面描述：first shot')
    expect(await screen.findByText('沈砚')).toBeTruthy()
    expect(screen.getByTestId('video-element')).toBeTruthy()
    expect(screen.getByRole('button', { name: '导出剪映工程' })).toBeTruthy()
  })

  it('shows the initialization action for a missing timeline', async () => {
    mockFetchSequence(initialResponses({ body: { error: 'timeline missing' }, status: 404 }))
    renderStudio()

    await waitFor(() => expect(screen.getByRole('button', { name: '初始化视频轨道' })).toBeTruthy())
  })

  it('seeks the player to the selected segment start', async () => {
    mockFetchSequence(initialResponses())
    renderStudio()

    const shotPanel = await screen.findByRole('region', { name: '镜头脚本' })
    fireEvent.click(within(shotPanel).getByRole('button', { name: /shot-002/ }))

    expect((screen.getByTestId('video-element') as HTMLVideoElement).currentTime).toBe(5)
  })

  it('sends create_if_missing when initializing a missing timeline', async () => {
    const fetchMock = mockFetchSequence(initialResponses({ body: { error: 'timeline missing' }, status: 404 }))
    renderStudio()
    const button = await screen.findByRole('button', { name: '初始化视频轨道' })

    fireEvent.click(button)
    await waitFor(() => {
      const calls = fetchMock.mock.calls as unknown as Array<[RequestInfo | URL, RequestInit | undefined]>
      const putCall = calls.find(
        ([, init]) => init?.method === 'PUT',
      ) as [string, RequestInit] | undefined
      expect(putCall).toBeTruthy()
      expect(JSON.parse(String(putCall?.[1].body))).toMatchObject({ create_if_missing: true })
    })
  })
})
