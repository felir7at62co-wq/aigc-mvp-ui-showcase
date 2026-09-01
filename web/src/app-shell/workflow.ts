export type WorkflowStepId =
  | 'project'
  | 'asset'
  | 'video'
  | 'settings'

export interface WorkflowStep {
  id: WorkflowStepId
  label: string
}

export const WORKFLOW_STEPS: WorkflowStep[] = [
  { id: 'project', label: '创建项目' },
  { id: 'asset', label: '资产生成' },
  { id: 'video', label: '视频生成' },
  { id: 'settings', label: '设置' },
]

export function workflowStepHref(projectName: string, stepId: WorkflowStepId) {
  const root = `/projects/${encodeURIComponent(projectName)}`
  if (stepId === 'project') return root
  if (stepId === 'asset') return `${root}/assets`
  return `${root}/${stepId}`
}

export function activeWorkflowStep(pathname: string, search: string): WorkflowStepId {
  if (pathname.includes('/episodes/')) return 'video'
  if (pathname.endsWith('/video')) return 'video'
  if (pathname.endsWith('/assets')) return 'asset'
  if (pathname.endsWith('/settings')) return 'settings'

  const requested = new URLSearchParams(search).get('stage')
  return WORKFLOW_STEPS.some((step) => step.id === requested)
    ? (requested as WorkflowStepId)
    : 'project'
}
