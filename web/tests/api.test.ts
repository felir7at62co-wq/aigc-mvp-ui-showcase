import { describe, expect, it, vi } from 'vitest'
import { apiGet } from '../src/api/client'
import {
  fetchEpisodeExports,
  fetchEpisodeVideos,
  fetchAssetCatalog,
  fetchProjects,
  fetchProjectSummary,
  fetchShotScript,
  fetchTasks,
  submitTask,
  uploadEpisodeVideo,
  uploadAssetImage,
  createAsset,
  updateAsset,
  deleteAsset,
} from '../src/api/projects'

function mockFetchOnce(payload: unknown, status = 200) {
  vi.stubGlobal('fetch', vi.fn(async () => ({
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  } as Response)))
}

describe('api client', () => {
  it('apiGet 解析 JSON 并带 JSON 头', async () => {
    mockFetchOnce({ ok: true })
    const result = await apiGet('/api/health')
    expect(result).toEqual({ ok: true })
    const [url, init] = vi.mocked(fetch).mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/health')
    expect((init.headers as Record<string, string>)['Accept']).toBe('application/json')
    vi.unstubAllGlobals()
  })

  it('非 2xx 抛出带状态错误', async () => {
    mockFetchOnce({ error: '项目不存在' }, 404)
    await expect(apiGet('/api/projects/N')).rejects.toMatchObject({ status: 404 })
    vi.unstubAllGlobals()
  })
})

describe('projects api', () => {
  it('fetchProjects 返回列表', async () => {
    mockFetchOnce({ projects: [{ name: 'A' }] })
    const projects = await fetchProjects()
    expect(projects).toEqual([{ name: 'A' }])
    vi.unstubAllGlobals()
  })

  it('submitTask 提交步骤任务', async () => {
    mockFetchOnce({ task_id: 't1' }, 202)
    const result = await submitTask('P', 'shot_match', ['01'])
    expect(result).toEqual({ task_id: 't1' })
    vi.unstubAllGlobals()
  })

  it('fetchTasks 过滤指定项目', async () => {
    mockFetchOnce({ tasks: [{ id: 'a', project: 'P', step: 'video', status: 'running' }] })
    const tasks = await fetchTasks('P')
    expect(tasks).toHaveLength(1)
    expect(tasks[0].status).toBe('running')
    vi.unstubAllGlobals()
  })

  it('fetchProjectSummary 聚合状态', async () => {
    mockFetchOnce({ name: 'P', episode_count: 8, steps: {} })
    const summary = await fetchProjectSummary('P')
    expect(summary.name).toBe('P')
    expect(summary.episode_count).toBe(8)
    vi.unstubAllGlobals()
  })

  it('fetches episode videos from the episode endpoint', async () => {
    mockFetchOnce({ videos: ['web_video/01/001.mp4'] })

    await expect(fetchEpisodeVideos('A project', '01')).resolves.toEqual({
      videos: ['web_video/01/001.mp4'],
    })
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe(
      '/api/projects/A%20project/episodes/01/videos',
    )
    vi.unstubAllGlobals()
  })

  it('uploads an episode video as multipart form data', async () => {
    mockFetchOnce({ video_path: 'web_video/01/uploaded.mp4' }, 201)
    const file = new File(['video'], 'replacement.mp4', { type: 'video/mp4' })

    await expect(uploadEpisodeVideo('P', '01', file)).resolves.toEqual({
      video_path: 'web_video/01/uploaded.mp4',
    })
    const [, init] = vi.mocked(fetch).mock.calls[0] as unknown as [string, RequestInit]
    expect(init.method).toBe('POST')
    expect(init.body).toBeInstanceOf(FormData)
    vi.unstubAllGlobals()
  })

  it('fetches shot script and export status with typed payloads', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ episode_id: '01', script: 'shot', match: null }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ episodes: { '01': { status: 'completed', output_path: '', error: '' } } }),
      } as Response)
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchShotScript('P', '01')).resolves.toMatchObject({ episode_id: '01' })
    await expect(fetchEpisodeExports('P')).resolves.toMatchObject({ episodes: { '01': { status: 'completed' } } })
    const calls = fetchMock.mock.calls as unknown as Array<[RequestInfo | URL, RequestInit | undefined]>
    expect(calls.map(([url]) => url)).toEqual([
      '/api/projects/P/shots/01',
      '/api/projects/P/exports',
    ])
    vi.unstubAllGlobals()
  })

  it('loads and mutates project assets through encoded paths', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ assets: { character: [], scene: [], prop: [] } }) } as Response)
      .mockResolvedValueOnce({ ok: true, status: 201, json: async () => ({ asset: { name: '主角' } }) } as Response)
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ asset: { name: '新主角' } }) } as Response)
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ ok: true }) } as Response)
    vi.stubGlobal('fetch', fetchMock)

    await fetchAssetCatalog('A project')
    await createAsset('A project', {
      category: 'character', name: '主角', aliases: '阿主', episodes: '01', prompt: '足够长度的角色资产生成提示词。',
    })
    await updateAsset('A project', 'character', '主角', {
      name: '新主角', aliases: '', episodes: '01', prompt: '更新后的角色资产生成提示词。',
    })
    await deleteAsset('A project', 'character', '新主角')

    const calls = fetchMock.mock.calls as unknown as Array<[string, RequestInit]>
    expect(calls.map(([url]) => url)).toEqual([
      '/api/projects/A%20project/assets',
      '/api/projects/A%20project/assets',
      '/api/projects/A%20project/assets/character/%E4%B8%BB%E8%A7%92',
      '/api/projects/A%20project/assets/character/%E6%96%B0%E4%B8%BB%E8%A7%92',
    ])
    expect(JSON.parse(String(calls[1][1].body))).toMatchObject({ category: 'character', name: '主角' })
    vi.unstubAllGlobals()
  })

  it('uploads an asset image as multipart form data', async () => {
    mockFetchOnce({ image_path: 'assets/character/主角.png' })
    const file = new File(['image'], 'portrait.png', { type: 'image/png' })

    await uploadAssetImage('P', 'character', '主角', file)

    const [url, init] = vi.mocked(fetch).mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/projects/P/assets/character/%E4%B8%BB%E8%A7%92/image')
    expect(init.method).toBe('POST')
    expect(init.body).toBeInstanceOf(FormData)
    vi.unstubAllGlobals()
  })
})
