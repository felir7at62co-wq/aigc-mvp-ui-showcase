import type { ChangeEvent } from 'react'
import type { Segment, Transition } from '../api/types'
import { Button } from './Button'

const TRANSITION_OPTIONS: Array<{ value: Transition['type']; label: string }> = [
  { value: 'hard', label: '硬切' },
  { value: 'crossfade', label: '交叉淡化' },
  { value: 'fade_black', label: '淡入黑' },
]

interface SegmentInspectorProps {
  segment: Segment | null
  script?: string
  onChange?: (transition: Transition) => void
  onRegenerate?: () => void
  onReplaceVideo?: (file: File) => void
  onDelete?: (segmentId: string) => void
  onRestore?: (segmentId: string) => void
}

export function SegmentInspector({
  segment,
  script,
  onChange,
  onRegenerate,
  onReplaceVideo,
  onDelete,
  onRestore,
}: SegmentInspectorProps) {
  if (!segment) {
    return <div className="empty-state">点击视频轨道中的片段查看详情</div>
  }

  function handleReplace(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (file) onReplaceVideo?.(file)
    event.target.value = ''
  }

  const transition = segment.transition_to_next
  return (
    <div className={`inspector${segment.deleted ? ' inspector-deleted' : ''}`}>
      <div className="inspector-title-row">
        <h4>{segment.shot_id}</h4>
        {segment.deleted && <span className="inspector-deleted-label">已删除</span>}
      </div>
      <dl className="inspector-grid">
        <dt>脚本</dt>
        <dd>{segment.prompt || '—'}</dd>
        <dt>源视频</dt>
        <dd>{segment.source_video || '—'}</dd>
        <dt>裁剪</dt>
        <dd>
          {segment.trim_in.toFixed(2)}s → {segment.trim_out.toFixed(2)}s（{segment.selected_version}）
        </dd>
        <dt>资产</dt>
        <dd>{segment.asset_ids.length ? segment.asset_ids.join('、') : '—'}</dd>
        <dt>转场</dt>
        <dd>
          <select
            aria-label="转场"
            value={transition.type}
            onChange={(event) => {
              const type = event.target.value as Transition['type']
              onChange?.({ type, duration: type === 'hard' ? 0 : 0.35 })
            }}
          >
            {TRANSITION_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
          {transition.type !== 'hard' && (
            <span className="transition-duration">{transition.duration.toFixed(2)}s</span>
          )}
        </dd>
      </dl>

      {script !== undefined && (
        <details className="script-details">
          <summary>查看完整镜头脚本</summary>
          <pre className="script-pre">{script || '暂无脚本内容'}</pre>
        </details>
      )}

      <div className="inspector-actions">
        {onRegenerate && (
          <Button variant="secondary" size="sm" type="button" onClick={onRegenerate}>
            重新生成此片段
          </Button>
        )}
        {onReplaceVideo && (
          <label className="btn btn-secondary btn-sm file-button">
            替换视频
            <input
              className="visually-hidden"
              type="file"
              accept=".mp4,.webm,.mov"
              aria-label="替换视频文件"
              onChange={handleReplace}
            />
          </label>
        )}
        {!segment.deleted && onDelete && (
          <Button variant="danger" size="sm" type="button" onClick={() => onDelete(segment.id)}>
            删除片段
          </Button>
        )}
        {segment.deleted && onRestore && (
          <Button variant="secondary" size="sm" type="button" onClick={() => onRestore(segment.id)}>
            恢复片段
          </Button>
        )}
      </div>
    </div>
  )
}
