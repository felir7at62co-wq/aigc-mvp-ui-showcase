import { useCallback, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  createProject,
  deleteProject,
  fetchProjects,
  type ProjectListItem,
} from '../api/projects'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { CreateProjectModal } from '../components/CreateProjectModal'
import { EmptyState } from '../components/EmptyState'
import { ScriptFileDropzone } from '../components/ScriptFileDropzone'
import { usePolling } from '../hooks/usePolling'

export function ProjectsPage() {
  const navigate = useNavigate()
  const loader = useCallback(() => fetchProjects(), [])
  const { data, error, refresh } = usePolling(loader, 10000)
  const projects: ProjectListItem[] = data ?? []

  const [showCreate, setShowCreate] = useState(false)
  const [name, setName] = useState('')
  const [script, setScript] = useState<File | null>(null)
  const [autoName, setAutoName] = useState('')
  const [aspectRatio, setAspectRatio] = useState<'9:16' | '16:9' | '1:1' | '4:3' | '3:4' | '21:9'>('9:16')
  const [resolution, setResolution] = useState<'480p' | '720p' | '1080p'>('720p')
  const [promptPrefix, setPromptPrefix] = useState('')
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState('')

  function handleScriptFile(nextFile: File) {
    setScript(nextFile)
    setFormError('')
    const derived = nextFile.name.replace(/\.[^.]+$/, '')
    if (!name || name === autoName) setName(derived)
    setAutoName(derived)
  }

  async function handleCreate() {
    if (!name.trim() || !script) {
      setFormError('请填写项目名称并选择剧本文件')
      return
    }
    setBusy(true)
    setFormError('')
    try {
      const summary = await createProject(name.trim(), script, {
        aspect_ratio: aspectRatio,
        resolution,
        prompt_prefix: promptPrefix,
      })
      setShowCreate(false)
      setName('')
      setScript(null)
      setAutoName('')
      setAspectRatio('9:16')
      setResolution('720p')
      setPromptPrefix('')
      refresh()
      navigate(`/projects/${encodeURIComponent(summary.name)}/assets`)
    } catch (err) {
      setFormError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  async function handleDelete(projectName: string) {
    if (!window.confirm(`删除项目「${projectName}」？此操作不可恢复。`)) return
    await deleteProject(projectName)
    refresh()
  }

  return (
    <div className="page">
      <div className="page-head">
        <h2>项目</h2>
        <Button onClick={() => setShowCreate(true)}>新建项目</Button>
      </div>

      {showCreate && (
        <CreateProjectModal title="创建项目" onClose={() => setShowCreate(false)}>
            <p className="project-create-subtitle">导入剧本后自动识别分集，并直接进入资产生成</p>
            <div className="form-grid project-create-grid">
              <label className="field field-wide">
                <span>剧本文件（.txt / .docx）</span>
                <ScriptFileDropzone
                  file={script}
                  onFileChange={handleScriptFile}
                  onError={setFormError}
                />
              </label>
              <label className="field field-wide">
                <span>项目名称</span>
                <input placeholder="项目名称" value={name} onChange={(event) => setName(event.target.value)} />
              </label>
              <label className="field">
                <span>视频尺寸</span>
                <select aria-label="视频尺寸" value={aspectRatio} onChange={(event) => setAspectRatio(event.target.value as typeof aspectRatio)}>
                  {['9:16', '16:9', '1:1', '4:3', '3:4', '21:9'].map((ratio) => <option key={ratio}>{ratio}</option>)}
                </select>
              </label>
              <label className="field">
                <span>清晰度</span>
                <select aria-label="清晰度" value={resolution} onChange={(event) => setResolution(event.target.value as typeof resolution)}>
                  {['480p', '720p', '1080p'].map((item) => <option key={item}>{item}</option>)}
                </select>
              </label>
              <label className="field field-wide">
                <span>镜头提示词前缀（非必填）</span>
                <textarea aria-label="镜头提示词前缀" rows={5} value={promptPrefix} onChange={(event) => setPromptPrefix(event.target.value)} placeholder="例如：电影感，保持角色和服装一致" />
              </label>
            </div>
            <div className="project-create-fixed">默认 Seedance 2.0 · 参考图模式 · 720p</div>
            {formError && <div className="form-error">{formError}</div>}
            <div className="form-actions">
              <Button variant="secondary" onClick={() => setShowCreate(false)}>取消</Button>
              <Button disabled={busy} onClick={handleCreate}>创建</Button>
            </div>
        </CreateProjectModal>
      )}

      {error && <div className="form-error">加载失败：{error}（请确认 Web API 已启动）</div>}
      {projects.length === 0 && !error && (
        <EmptyState message="还没有项目，点击「新建项目」导入剧本开始生产。" />
      )}
      <div className="project-grid">
        {projects.map((project) => (
          <Card key={project.name} title={project.name}>
            <div className="project-meta">创建于 {new Date(project.created_at).toLocaleString()}</div>
            <div className="card-actions">
              <Button variant="secondary" onClick={() => navigate(`/projects/${encodeURIComponent(project.name)}`)}>
                进入工作台
              </Button>
              <Button variant="danger" onClick={() => handleDelete(project.name)}>删除</Button>
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}
