import { useCallback } from 'react'
import { Navigate, useParams } from 'react-router-dom'
import { fetchEpisodes } from '../api/projects'
import { EmptyState } from '../components/EmptyState'
import { usePolling } from '../hooks/usePolling'

export function VideoEntryPage() {
  const { projectName = '' } = useParams()
  const loader = useCallback(() => fetchEpisodes(projectName), [projectName])
  const { data, error } = usePolling(loader, 10000)

  if (error) return <div className="form-error">加载分集失败：{error}</div>
  if (!data) return <EmptyState message="正在进入视频生成…" />
  const first = data.episodes[0]
  if (!first) return <EmptyState message="当前项目没有可生成的分集" />
  return <Navigate replace to={`/projects/${encodeURIComponent(projectName)}/episodes/${first.episode_id}`} />
}
