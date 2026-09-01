import { useCallback } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import {
  fetchEpisodes,
  fetchProjectSummary,
  fetchTasks,
  submitTask,
} from '../api/projects'
import type { ProjectSummary, TaskRecord } from '../api/types'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { EmptyState } from '../components/EmptyState'
import { StatusBadge } from '../components/StatusBadge'
import { usePolling } from '../hooks/usePolling'
import { workflowStepHref } from '../app-shell/workflow'

const STEP_LABELS: Record<string, string> = {
  import_script: '剧本导入',
  asset: '资产生成',
  video: '视频生成',
}

const RUNNABLE_STEPS = new Set(['asset', 'video'])
const VISIBLE_STEP_ORDER = ['import_script', 'asset', 'video']

const WORKFLOW_STAGE_TO_STEP: Record<string, string> = {
  project: 'import_script',
  asset: 'asset',
  video: 'video',
}

const DASHBOARD_STAGES = new Set([
  'project',
  'asset',
  'video',
  'settings',
])

export function DashboardPage() {
  const { projectName = '' } = useParams()
  const [searchParams] = useSearchParams()
  const requestedStage = searchParams.get('stage')
  const activeStage = requestedStage && DASHBOARD_STAGES.has(requestedStage)
    ? requestedStage
    : 'project'
  const focusedStep = WORKFLOW_STAGE_TO_STEP[activeStage] ?? null
  const summaryLoader = useCallback(() => fetchProjectSummary(projectName), [projectName])
  const tasksLoader = useCallback(() => fetchTasks(projectName), [projectName])
  const episodesLoader = useCallback(() => fetchEpisodes(projectName), [projectName])
  const { data: summary, error: summaryError } = usePolling(summaryLoader, 3000)
  const { data: taskList, refresh: refreshTasks } = usePolling(tasksLoader, 3000)
  const { data: episodesData } = usePolling(episodesLoader, 10000)
  const tasks: TaskRecord[] = taskList ?? []
  const project: ProjectSummary | null = summary ?? null
  const episodeIds: string[] = (episodesData?.episodes ?? []).map((item) => item.episode_id)

  async function handleRunStep(step: string) {
    await submitTask(projectName, step, episodeIds)
    refreshTasks()
  }

  return (
    <div className="page">
      <div className="page-head">
        <h2>{project?.name ?? projectName}</h2>
      </div>

      {summaryError && <div className="form-error">加载失败：{summaryError}</div>}
      {!project && !summaryError && <EmptyState message="加载中…" />}

      {project && (
        <>
          <div className="summary-grid">
            <Card title="集数">
              <div className="summary-number">{project.episodes.total} 集</div>
            </Card>
            <Card title="待处理">
              <div className="summary-number">{project.episodes.by_status.pending ?? 0}</div>
            </Card>
            <Card title="进行中">
              <div className="summary-number">{project.episodes.by_status.running ?? 0}</div>
            </Card>
            <Card title="已完成">
              <div className="summary-number">{project.episodes.by_status.completed ?? 0}</div>
            </Card>
          </div>

          <Card title="生产阶段" className="phase-card">
            <div className="phase-grid">
              {VISIBLE_STEP_ORDER.flatMap((step) => {
                const state = project.steps[step]
                if (!state) return []
                return [(
                <div
                  key={step}
                  id={`phase-${step}`}
                  className={`phase-item${focusedStep === step ? ' phase-item-focused' : ''}`}
                  aria-current={focusedStep === step ? 'step' : undefined}
                >
                  <div className="phase-label">{STEP_LABELS[step] ?? step}</div>
                  <StatusBadge status={state.status} />
                  {step === 'asset' || step === 'video' ? (
                    <Link
                      className="btn btn-secondary btn-sm"
                      to={workflowStepHref(projectName, step === 'asset' ? 'asset' : 'video')}
                    >
                      进入
                    </Link>
                  ) : RUNNABLE_STEPS.has(step) ? (
                    <Button variant="secondary" size="sm" onClick={() => handleRunStep(step)}>
                      运行
                    </Button>
                  ) : (
                    <span className="phase-hint">
                      {step === 'import_script' ? '导入时自动完成' : '在编辑台内创建'}
                    </span>
                  )}
                </div>
                )]
              })}
            </div>
          </Card>

          {activeStage === 'settings' && (
            <Card title="项目设置" className="settings-card settings-card-focused">
              <p className="settings-placeholder">
                设置暂由项目配置文件管理；本版本保留配置入口位置，不新增配置 API。
              </p>
            </Card>
          )}

          <Card
            title="集列表"
            className={`episodes-card${activeStage === 'video' ? ' episodes-card-focused' : ''}`}
          >
            {episodesData?.episodes.length === 0 && <EmptyState message="暂无分集" />}
            <div className="episode-grid">
              {episodesData?.episodes.map((episode) => (
                <Link
                  key={episode.episode_id}
                  to={`/projects/${encodeURIComponent(projectName)}/episodes/${episode.episode_id}`}
                  className="episode-link"
                >
                  <span className="episode-id">第 {episode.episode_id} 集</span>
                  <StatusBadge status={episode.shot_match_status} />
                </Link>
              ))}
            </div>
          </Card>

          <Card title="任务队列">
            {tasks.length === 0 && <EmptyState message="暂无任务" />}
            <table className="task-table">
              <thead>
                <tr><th>任务</th><th>步骤</th><th>集</th><th>状态</th><th>错误</th></tr>
              </thead>
              <tbody>
                {tasks.map((task) => (
                  <tr key={task.id}>
                    <td>{task.id}</td>
                    <td>{task.step}</td>
                    <td>{task.episode_ids.join(', ')}</td>
                    <td><StatusBadge status={task.status} /></td>
                    <td className="task-error">{task.error}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </>
      )}
    </div>
  )
}
