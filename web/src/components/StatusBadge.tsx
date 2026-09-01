const STATUS_LABELS: Record<string, string> = {
  pending: '待处理',
  queued: '排队中',
  running: '进行中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
  stale: '已过期',
  review: '待确认',
  validating: '校验中',
}

const STATUS_TONE: Record<string, string> = {
  pending: 'muted',
  queued: 'muted',
  running: 'accent',
  validating: 'accent',
  completed: 'success',
  review: 'warn',
  stale: 'warn',
  failed: 'danger',
  cancelled: 'muted',
}

export function StatusBadge({ status }: { status: string }) {
  const tone = STATUS_TONE[status] ?? 'muted'
  const label = STATUS_LABELS[status] ?? status
  return (
    <span className={`status-badge status-${tone}`} data-testid="status-badge">
      {label}
    </span>
  )
}
