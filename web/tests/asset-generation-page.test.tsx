import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AssetGenerationPage } from '../src/pages/AssetGenerationPage'

const apiMocks = vi.hoisted(() => ({
  fetchAssetCatalog: vi.fn(),
  fetchEpisodes: vi.fn(),
  submitTask: vi.fn(),
  createAsset: vi.fn(),
  updateAsset: vi.fn(),
  deleteAsset: vi.fn(),
  uploadAssetImage: vi.fn(),
}))

vi.mock('../src/api/projects', () => apiMocks)

const catalog = {
  character: [
    {
      name: '主角', aliases: ['阿主'], episodes: ['01', '02'],
      prompt: '一位穿白色风衣的年轻主角，电影感灯光。',
      category: 'character' as const, image_path: 'assets/character/主角.png',
    },
    {
      name: '配角', aliases: [], episodes: ['01'],
      prompt: '一位穿深色夹克的中年配角，写实电影风格。',
      category: 'character' as const, image_path: '',
    },
  ],
  scene: [{
    name: '老街', aliases: [], episodes: ['01'], prompt: '潮湿老街夜景与暖色路灯。',
    category: 'scene' as const, image_path: '',
  }],
  prop: [],
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/projects/P/assets']}>
      <Routes>
        <Route path="/projects/:projectName/assets" element={<AssetGenerationPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('AssetGenerationPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.fetchAssetCatalog.mockResolvedValue(catalog)
    apiMocks.fetchEpisodes.mockResolvedValue({
      episodes: [{ episode_id: '01' }, { episode_id: '02' }],
    })
    apiMocks.submitTask.mockResolvedValue({ task_id: 'asset-task', status: 'queued' })
    apiMocks.createAsset.mockResolvedValue({ asset: { name: '新角色' } })
    apiMocks.updateAsset.mockResolvedValue({ asset: { name: '主角' } })
    apiMocks.deleteAsset.mockResolvedValue({ ok: true })
    apiMocks.uploadAssetImage.mockResolvedValue({ image_path: 'assets/character/主角.png' })
  })

  it('renders category tabs and generates only selected assets', async () => {
    renderPage()

    expect(await screen.findByRole('heading', { name: '资产生成' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /角色/ })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: /场景/ })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /道具/ })).toBeInTheDocument()
    const card = screen.getByRole('article', { name: '资产 主角' })
    expect(within(card).getByText('别名：阿主')).toBeInTheDocument()
    expect(within(card).getByText('集数：01, 02')).toBeInTheDocument()

    fireEvent.click(within(card).getByRole('button', { name: '选择主角' }))
    fireEvent.click(screen.getByRole('button', { name: '生成选中角色' }))

    await waitFor(() => expect(apiMocks.submitTask).toHaveBeenCalledWith(
      'P', 'asset', ['01', '02'],
      { category: 'character', asset_names: ['主角'] },
    ))
  })

  it('switches category and supports adding an asset', async () => {
    renderPage()
    await screen.findByText('主角')

    fireEvent.click(screen.getByRole('tab', { name: /场景/ }))
    expect(await screen.findByText('老街')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: /角色/ }))
    fireEvent.click(screen.getByRole('button', { name: '添加资产' }))
    fireEvent.change(screen.getByLabelText('资产名称'), { target: { value: '新角色' } })
    fireEvent.change(screen.getByLabelText('资产别名'), { target: { value: '新人' } })
    fireEvent.change(screen.getByLabelText('出场集数'), { target: { value: '02' } })
    fireEvent.change(screen.getByLabelText('生成提示词'), {
      target: { value: '一位穿浅色西装的年轻角色，写实电影风格。' },
    })
    fireEvent.click(screen.getByRole('button', { name: '保存资产' }))

    await waitFor(() => expect(apiMocks.createAsset).toHaveBeenCalledWith('P', {
      category: 'character', name: '新角色', aliases: '新人', episodes: '02',
      prompt: '一位穿浅色西装的年轻角色，写实电影风格。',
    }))
  })

  it('uploads and deletes an existing asset', async () => {
    vi.stubGlobal('confirm', vi.fn(() => true))
    renderPage()
    const card = await screen.findByRole('article', { name: '资产 主角' })
    const file = new File(['image'], 'portrait.png', { type: 'image/png' })

    fireEvent.change(within(card).getByLabelText('上传主角图片'), {
      target: { files: [file] },
    })
    await waitFor(() => expect(apiMocks.uploadAssetImage).toHaveBeenCalledWith(
      'P', 'character', '主角', file,
    ))

    fireEvent.click(within(card).getByRole('button', { name: '删除主角' }))
    await waitFor(() => expect(apiMocks.deleteAsset).toHaveBeenCalledWith(
      'P', 'character', '主角',
    ))
    vi.unstubAllGlobals()
  })
})
