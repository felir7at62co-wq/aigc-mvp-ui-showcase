import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { ProjectsPage } from '../src/pages/ProjectsPage'

function mockFetch(payload: unknown) {
  vi.stubGlobal('fetch', vi.fn(async () => ({
    ok: true,
    status: 200,
    json: async () => payload,
  } as Response)))
}

describe('ProjectsPage', () => {
  it('渲染项目列表与创建入口', async () => {
    mockFetch({ projects: [{ name: '测试剧', created_at: '2026-08-15T10:00:00' }] })
    render(<MemoryRouter><ProjectsPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText('测试剧')).toBeTruthy())
    expect(screen.getByText('新建项目')).toBeTruthy()
    vi.unstubAllGlobals()
  })

  it('创建时提交 multipart 表单', async () => {
    const fetchMock = vi.fn(async (_url: string | URL | Request, _init?: RequestInit) => ({
      ok: true, status: 201,
      json: async () => ({ name: '新剧', episode_count: 2, steps: {} }),
    } as Response))
    vi.stubGlobal('fetch', fetchMock)
    function LocationProbe() {
      const location = useLocation()
      return <div data-testid="location-probe">{location.pathname}{location.search}</div>
    }

    render(
      <MemoryRouter>
        <Routes>
          <Route path="/" element={<ProjectsPage />} />
          <Route path="/projects/:projectName" element={<LocationProbe />} />
          <Route path="/projects/:projectName/assets" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>,
    )
    fireEvent.click(screen.getByText('新建项目'))
    const nameInput = await screen.findByPlaceholderText('项目名称')
    const file = new File(['第1集\n内容'], '新剧.txt', { type: 'text/plain' })
    const fileInput = screen
      .getByRole('button', { name: '上传剧本文件' })
      .querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(fileInput, { target: { files: [file] } })
    expect(nameInput).toHaveValue('新剧')
    fireEvent.change(nameInput, { target: { value: '新剧修改版' } })
    fireEvent.change(screen.getByLabelText('视频尺寸'), { target: { value: '16:9' } })
    fireEvent.change(screen.getByLabelText('清晰度'), { target: { value: '1080p' } })
    fireEvent.change(screen.getByLabelText('镜头提示词前缀'), {
      target: { value: '电影感，保持角色一致' },
    })
    expect(screen.queryByLabelText('剧集数')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('每集分镜数')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('主模型')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('生成方式')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '创建' }))
    await waitFor(() => {
      // 首次挂载会先 GET /api/projects（usePolling），需找到 POST 调用
      const postCall = fetchMock.mock.calls.find(
        (call) => (call[1] as RequestInit | undefined)?.method === 'POST',
      ) as unknown as [string, RequestInit] | undefined
      expect(postCall).toBeTruthy()
      expect(postCall![0]).toBe('/api/projects')
      expect(postCall![1].body).toBeInstanceOf(FormData)
      const body = postCall![1].body as FormData
      expect(body.get('name')).toBe('新剧修改版')
      expect(body.get('aspect_ratio')).toBe('16:9')
      expect(body.get('resolution')).toBe('1080p')
      expect(body.get('prompt_prefix')).toBe('电影感，保持角色一致')
    })
    expect(await screen.findByTestId('location-probe')).toHaveTextContent(
      '/projects/%E6%96%B0%E5%89%A7/assets',
    )
    vi.unstubAllGlobals()
  })

  it('创建项目以全屏 Portal 弹窗展示并支持遮罩关闭', async () => {
    mockFetch({ projects: [] })
    const { container } = render(<MemoryRouter><ProjectsPage /></MemoryRouter>)

    fireEvent.click(screen.getByText('新建项目'))

    const dialog = await screen.findByRole('dialog', { name: '创建项目' })
    const backdrop = screen.getByTestId('create-project-backdrop')
    expect(document.body).toContainElement(backdrop)
    expect(container.querySelector('.project-create-backdrop')).toBeNull()
    expect(screen.getByRole('button', { name: '上传剧本文件' })).toBeVisible()
    expect(document.body.style.overflow).toBe('hidden')

    fireEvent.click(dialog)
    expect(screen.getByRole('dialog', { name: '创建项目' })).toBeTruthy()
    fireEvent.click(backdrop)
    expect(screen.queryByRole('dialog', { name: '创建项目' })).toBeNull()
    expect(document.body.style.overflow).toBe('')
    vi.unstubAllGlobals()
  })

  it('支持把剧本拖入上传框并显示文件名和自动填写项目名', async () => {
    mockFetch({ projects: [] })
    render(<MemoryRouter><ProjectsPage /></MemoryRouter>)
    fireEvent.click(screen.getByText('新建项目'))

    const dropzone = await screen.findByRole('button', { name: '上传剧本文件' })
    const file = new File(['第1集\n内容'], '拖拽新剧.txt', { type: 'text/plain' })
    fireEvent.drop(dropzone, { dataTransfer: { files: [file] } })

    expect(screen.getByText('拖拽新剧.txt')).toBeVisible()
    expect(screen.getByPlaceholderText('项目名称')).toHaveValue('拖拽新剧')
    vi.unstubAllGlobals()
  })

  it('拒绝不支持的剧本文件格式', async () => {
    mockFetch({ projects: [] })
    render(<MemoryRouter><ProjectsPage /></MemoryRouter>)
    fireEvent.click(screen.getByText('新建项目'))

    const dropzone = await screen.findByRole('button', { name: '上传剧本文件' })
    const file = new File(['内容'], '错误格式.pdf', { type: 'application/pdf' })
    fireEvent.drop(dropzone, { dataTransfer: { files: [file] } })

    expect(screen.getByText('仅支持 .txt 或 .docx 剧本文件')).toBeVisible()
    expect(screen.getByPlaceholderText('项目名称')).toHaveValue('')
    vi.unstubAllGlobals()
  })
})
