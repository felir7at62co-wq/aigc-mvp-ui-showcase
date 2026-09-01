import { useEffect, useState } from 'react'
import type { AssetInput, AssetRecord } from '../../api/types'
import { Button } from '../../components/Button'

export function AssetEditorDialog({
  asset,
  onClose,
  onSave,
}: {
  asset: AssetRecord | null
  onClose: () => void
  onSave: (input: AssetInput) => Promise<void>
}) {
  const [name, setName] = useState('')
  const [aliases, setAliases] = useState('')
  const [episodes, setEpisodes] = useState('')
  const [prompt, setPrompt] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setName(asset?.name ?? '')
    setAliases(asset?.aliases.join('、') ?? '')
    setEpisodes(asset?.episodes.join(',') ?? '')
    setPrompt(asset?.prompt ?? '')
  }, [asset])

  return (
    <div className="asset-editor-backdrop" role="presentation">
      <form
        className="asset-editor-dialog glass-panel glass-strong"
        role="dialog"
        aria-modal="true"
        aria-label={asset ? `编辑${asset.name}` : '添加资产'}
        onSubmit={async (event) => {
          event.preventDefault()
          setSaving(true)
          try {
            await onSave({ name, aliases, episodes, prompt })
          } finally {
            setSaving(false)
          }
        }}
      >
        <header>
          <h2>{asset ? '编辑资产' : '添加资产'}</h2>
          <button type="button" aria-label="关闭" onClick={onClose}>×</button>
        </header>
        <label>资产名称<input aria-label="资产名称" value={name} onChange={(event) => setName(event.target.value)} required /></label>
        <label>资产别名<input aria-label="资产别名" value={aliases} onChange={(event) => setAliases(event.target.value)} /></label>
        <label>出场集数<input aria-label="出场集数" value={episodes} onChange={(event) => setEpisodes(event.target.value)} placeholder="例如：01,02,03" /></label>
        <label>生成提示词<textarea aria-label="生成提示词" value={prompt} onChange={(event) => setPrompt(event.target.value)} required minLength={10} rows={5} /></label>
        <footer>
          <Button type="button" variant="secondary" onClick={onClose}>取消</Button>
          <Button type="submit" disabled={saving}>{saving ? '保存中…' : '保存资产'}</Button>
        </footer>
      </form>
    </div>
  )
}
