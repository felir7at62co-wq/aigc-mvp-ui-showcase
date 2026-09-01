import { useCallback, useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate, useParams } from 'react-router-dom'
import { fetchProjects, type ProjectListItem } from '../api/projects'
import { usePolling } from '../hooks/usePolling'
import {
  activeWorkflowStep,
  WORKFLOW_STEPS,
  workflowStepHref,
} from './workflow'

export function AppShell() {
  const navigate = useNavigate()
  const location = useLocation()
  const params = useParams()
  const active = params.projectName ?? ''
  const currentStepId = activeWorkflowStep(location.pathname, location.search)
  const currentStep = WORKFLOW_STEPS.find((step) => step.id === currentStepId)!

  const loader = useCallback(() => fetchProjects(), [])
  const { data } = usePolling(loader, 15000)
  const projects: ProjectListItem[] = data ?? []

  const [selected, setSelected] = useState(active)
  useEffect(() => setSelected(active), [active])

  return (
    <div className="app-shell">
      <header className="topbar glass-panel glass-strong">
        <NavLink to="/" className="brand">AIGC 短剧生产工作台</NavLink>
        <div className="topbar-project-controls">
          <label className="project-select-label" htmlFor="project-select">当前项目</label>
          <select
            id="project-select"
            className="project-select"
            value={selected}
            onChange={(event) => {
              const value = event.target.value
              setSelected(value)
              if (value) navigate(workflowStepHref(value, 'project'))
              else navigate('/')
            }}
          >
            <option value="">选择项目…</option>
            {projects.map((project) => (
              <option key={project.name} value={project.name}>{project.name}</option>
            ))}
          </select>
          <NavLink to="/" className="topbar-project-link">项目列表</NavLink>
        </div>
      </header>
      <div className={`shell-body${active ? '' : ' shell-body--project-list'}`}>
        {active && (
          <nav className="workflow-sidebar glass-panel glass-strong" aria-label="流程步骤">
            <div className="workflow-sidebar-title">
              <span>流程步骤</span>
              <span className="workflow-sidebar-count">{WORKFLOW_STEPS.length} 步</span>
            </div>
            <div className="workflow-step-list">
              {WORKFLOW_STEPS.map((step, index) => {
                const isCurrent = currentStepId === step.id
                return (
                  <Link
                    key={step.id}
                    to={workflowStepHref(active, step.id)}
                    aria-current={isCurrent ? 'step' : undefined}
                    className={`workflow-step${isCurrent ? ' active' : ''}`}
                  >
                    <span className="workflow-step-index">{index + 1}</span>
                    <span className="workflow-step-label">{step.label}</span>
                    <span className="workflow-step-dot" aria-hidden="true" />
                  </Link>
                )
              })}
            </div>
          </nav>
        )}
        <main className="shell-main">
          <Outlet />
        </main>
      </div>
      <footer className="shell-statusbar glass-panel glass-strong">
        <span>当前项目：{active || '未选择项目'}</span>
        <span>当前步骤：{active ? currentStep.label : '项目列表'}</span>
        <span className="shell-ready"><span aria-hidden="true">●</span> Web 工作台就绪</span>
      </footer>
    </div>
  )
}
