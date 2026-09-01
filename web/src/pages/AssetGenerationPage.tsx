import { useCallback, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  createAsset,
  deleteAsset,
  fetchAssetCatalog,
  fetchEpisodes,
  submitTask,
  updateAsset,
  uploadAssetImage,
} from '../api/projects'
import type { AssetCategory, AssetInput, AssetRecord } from '../api/types'
import { Button } from '../components/Button'
import { EmptyState } from '../components/EmptyState'
import { AssetCard } from '../features/assets/AssetCard'
import { AssetEditorDialog } from '../features/assets/AssetEditorDialog'
import { ASSET_CATEGORIES, toggleAssetSelection } from '../features/assets/model'
import { usePolling } from '../hooks/usePolling'

const EMPTY_CATALOG = { character: [], scene: [], prop: [] }

export function AssetGenerationPage() {
  const { projectName = '' } = useParams()
  const [category, setCategory] = useState<AssetCategory>('character')
  const [selected, setSelected] = useState<Record<AssetCategory, Set<string>>>(() => ({
    character: new Set(), scene: new Set(), prop: new Set(),
  }))
  const [editorOpen, setEditorOpen] = useState(false)
  const [editing, setEditing] = useState<AssetRecord | null>(null)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  const catalogLoader = useCallback(() => fetchAssetCatalog(projectName), [projectName])
  const episodesLoader = useCallback(() => fetchEpisodes(projectName), [projectName])
  const { data: catalogData, error, refresh } = usePolling(catalogLoader, 5000)
  const { data: episodeData } = usePolling(episodesLoader, 10000)
  const catalog = catalogData ?? EMPTY_CATALOG
  const assets = catalog[category]
  const selectedNames = selected[category]
  const categoryLabel = ASSET_CATEGORIES.find((item) => item.id === category)?.label ?? ''

  function setCategorySelection(next: Set<string>) {
    setSelected((current) => ({ ...current, [category]: next }))
  }

  async function runAction(action: () => Promise<void>, successMessage: string) {
    setBusy(true)
    setMessage('')
    try {
      await action()
      refresh()
      setMessage(successMessage)
    } catch (actionError) {
      setMessage(actionError instanceof Error ? actionError.message : String(actionError))
    } finally {
      setBusy(false)
    }
  }

  async function handleSave(input: AssetInput) {
    await runAction(async () => {
      if (editing) await updateAsset(projectName, category, editing.name, input)
      else await createAsset(projectName, { ...input, category })
      setEditorOpen(false)
      setEditing(null)
    }, editing ? '资产信息已更新' : '资产已添加')
  }

  async function handleGenerate() {
    if (!selectedNames.size) return
    const episodeIds = (episodeData?.episodes ?? []).map((episode) => episode.episode_id)
    await runAction(async () => {
      const task = await submitTask(projectName, 'asset', episodeIds, {
        category,
        asset_names: [...selectedNames],
      })
      setMessage(`资产生成任务已提交：${task.task_id}`)
    }, '资产生成任务已提交')
  }

  return (
    <div className="asset-generation-page">
      <header className="asset-generation-head">
        <div>
          <span className="asset-generation-kicker">剧本导入完成 · 下一步</span>
          <h1>资产生成</h1>
          <p>自动提取角色、场景和道具提示词，选择卡片批量生成或上传资产图片。</p>
        </div>
        <div className="asset-generation-head-actions">
          <Button type="button" variant="secondary" onClick={() => setMessage('重新提取接口正在迁移到 Web，当前资产数据不会被覆盖。')}>重新提取</Button>
          <Button type="button" variant="secondary" onClick={() => setMessage('自定义 TXT 导入将在接入提取服务后开放。')}>导入自定义 TXT</Button>
          <Button type="button" variant="secondary" onClick={() => setMessage('提取模板继续使用项目 prompts 配置，本页暂不直接修改服务器文件。')}>编辑提取模板</Button>
        </div>
      </header>

      {message && <div className="asset-generation-message" role="status">{message}</div>}

      <section className="asset-generation-manager glass-panel" aria-label="资产生成管理">
        <div className="asset-generation-tabs" role="tablist" aria-label="资产类别">
          {ASSET_CATEGORIES.map((item) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={category === item.id}
              className={category === item.id ? 'active' : ''}
              onClick={() => setCategory(item.id)}
            >
              {item.label}<span>{catalog[item.id].length}</span>
            </button>
          ))}
        </div>

        <div className="asset-generation-toolbar">
          <Button type="button" disabled={!selectedNames.size || busy} onClick={() => void handleGenerate()}>
            生成选中{categoryLabel}
          </Button>
          <Button type="button" variant="secondary" disabled={busy} onClick={refresh}>刷新</Button>
          <label className="btn btn-secondary btn-md asset-import-button">
            智能导入图片
            <input
              className="visually-hidden"
              type="file"
              multiple
              accept="image/png,image/jpeg,image/webp"
              aria-label={`批量导入${categoryLabel}图片`}
              onChange={(event) => {
                const files = Array.from(event.target.files ?? [])
                void runAction(async () => {
                  for (const file of files) {
                    const assetName = file.name.replace(/\.[^.]+$/, '')
                    await uploadAssetImage(projectName, category, assetName, file)
                  }
                }, `已导入 ${files.length} 张${categoryLabel}图片`)
                event.target.value = ''
              }}
            />
          </label>
          <Button type="button" variant="secondary" onClick={() => setCategorySelection(new Set(assets.map((asset) => asset.name)))}>全选</Button>
          <Button type="button" variant="secondary" onClick={() => setCategorySelection(new Set())}>取消全选</Button>
          <span className="asset-generation-count">共 {assets.length} 个{categoryLabel}资产，已选 {selectedNames.size} 个</span>
        </div>

        {error && <div className="form-error">资产加载失败：{error}</div>}
        {!catalogData && !error && <EmptyState message="正在读取资产…" />}

        <div className="asset-generation-grid" role="tabpanel" aria-label={`${categoryLabel}资产`}>
          <button
            type="button"
            className="asset-generation-add"
            aria-label="添加资产"
            onClick={() => { setEditing(null); setEditorOpen(true) }}
          >
            <b>＋</b><span>添加资产</span>
          </button>
          {assets.map((asset) => (
            <AssetCard
              key={asset.name}
              projectName={projectName}
              asset={asset}
              selected={selectedNames.has(asset.name)}
              onToggle={() => setCategorySelection(toggleAssetSelection(selectedNames, asset.name))}
              onEdit={() => { setEditing(asset); setEditorOpen(true) }}
              onDelete={() => {
                if (!window.confirm(`确定删除${categoryLabel}资产“${asset.name}”吗？`)) return
                void runAction(
                  () => deleteAsset(projectName, category, asset.name).then(() => undefined),
                  `已删除资产：${asset.name}`,
                )
              }}
              onUpload={(file) => void runAction(
                () => uploadAssetImage(projectName, category, asset.name, file).then(() => undefined),
                `已更新${asset.name}的资产图片`,
              )}
            />
          ))}
        </div>
      </section>

      {editorOpen && (
        <AssetEditorDialog
          asset={editing}
          onClose={() => { setEditorOpen(false); setEditing(null) }}
          onSave={handleSave}
        />
      )}
    </div>
  )
}
