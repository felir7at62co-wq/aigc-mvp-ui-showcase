import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { fetchProjectSettings, saveProjectSettings } from '../api/projects'
import type { ProjectSettings } from '../api/types'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { EmptyState } from '../components/EmptyState'
import { usePolling } from '../hooks/usePolling'

export function SettingsPage() {
  const { projectName = '' } = useParams()
  const loader = useCallback(() => fetchProjectSettings(projectName), [projectName])
  const { data, error, refresh } = usePolling(loader, 10000)
  const [form, setForm] = useState<ProjectSettings | null>(null)
  const [message, setMessage] = useState('')

  useEffect(() => { if (data) setForm(data) }, [data])

  async function handleSave() {
    if (!form) return
    await saveProjectSettings(projectName, {
      aspect_ratio: form.aspect_ratio,
      resolution: form.resolution,
      prompt_prefix: form.prompt_prefix,
    })
    setMessage('设置已保存')
    refresh()
  }

  if (error) return <div className="form-error">加载设置失败：{error}</div>
  if (!form) return <EmptyState message="正在加载项目设置…" />

  return (
    <div className="page settings-page">
      <div className="page-head"><h2>项目设置</h2></div>
      <Card title="视频生成设置">
        <div className="form-grid settings-form-grid">
          <label className="field">
            <span>视频尺寸</span>
            <select aria-label="视频尺寸" value={form.aspect_ratio} onChange={(event) => setForm({ ...form, aspect_ratio: event.target.value as ProjectSettings['aspect_ratio'] })}>
              {['9:16', '16:9', '1:1', '4:3', '3:4', '21:9'].map((ratio) => <option key={ratio}>{ratio}</option>)}
            </select>
          </label>
          <label className="field">
            <span>清晰度</span>
            <select aria-label="清晰度" value={form.resolution} onChange={(event) => setForm({ ...form, resolution: event.target.value as ProjectSettings['resolution'] })}>
              {['480p', '720p', '1080p'].map((resolution) => <option key={resolution}>{resolution}</option>)}
            </select>
          </label>
          <label className="field field-wide">
            <span>镜头提示词前缀（非必填）</span>
            <textarea aria-label="镜头提示词前缀" rows={5} value={form.prompt_prefix} placeholder="将自动加在每个镜头脚本前，例如：电影感，保持角色和服装一致" onChange={(event) => setForm({ ...form, prompt_prefix: event.target.value })} />
          </label>
        </div>
        <div className="settings-fixed-summary">
          固定使用 Seedance 2.0 · 参考图模式 · 每个生成子任务 15 秒
          <span className={form.api_configured ? 'configured' : 'not-configured'}>{form.api_configured ? '云映 API 已配置' : '云映 API 未配置'}</span>
        </div>
        {message && <div className="asset-generation-message">{message}</div>}
        <div className="form-actions"><Button onClick={handleSave}>保存设置</Button></div>
      </Card>
    </div>
  )
}
