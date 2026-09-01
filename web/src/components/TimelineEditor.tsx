import { useRef } from 'react'
import type { MouseEvent as ReactMouseEvent } from 'react'
import type { Segment, TimelineManifest } from '../api/types'

const PX_PER_SECOND = 60

interface TimelineEditorProps {
  timeline: TimelineManifest
  selectedId: string | null
  currentTime: number
  duration: number
  onSelect: (segmentId: string) => void
  onCommit: (timeline: TimelineManifest) => void
  onSeek: (seconds: number) => void
}

export function TimelineEditor({
  timeline,
  selectedId,
  currentTime,
  duration,
  onSelect,
  onCommit,
  onSeek,
}: TimelineEditorProps) {
  const rulerRef = useRef<HTMLDivElement | null>(null)
  const orderedSegments = [...timeline.segments].sort((a, b) => a.order - b.order)
  const totalWidth = Math.max(240, duration * PX_PER_SECOND)

  function handleRulerClick(event: ReactMouseEvent<HTMLDivElement>) {
    const rect = rulerRef.current?.getBoundingClientRect()
    if (!rect) return
    const seconds = (event.clientX - rect.left) / PX_PER_SECOND
    onSeek(Math.max(0, Math.min(duration, seconds)))
  }

  function updateSegment(segmentId: string, patch: Partial<Pick<Segment, 'trim_in' | 'trim_out'>>) {
    onCommit({
      ...timeline,
      segments: timeline.segments.map((segment) =>
        segment.id === segmentId ? { ...segment, ...patch } : segment,
      ),
    })
  }

  function commitReorder(draggedId: string, targetId: string) {
    const activeIds = orderedSegments
      .filter((segment) => !segment.deleted)
      .map((segment) => segment.id)
    const from = activeIds.indexOf(draggedId)
    const to = activeIds.indexOf(targetId)
    if (from < 0 || to < 0 || from === to) return
    activeIds.splice(from, 1)
    activeIds.splice(to, 0, draggedId)
    const nextOrder = new Map(activeIds.map((id, index) => [id, index]))
    onCommit({
      ...timeline,
      segments: timeline.segments.map((segment) => {
        const next = nextOrder.get(segment.id)
        return next === undefined ? segment : { ...segment, order: next }
      }),
    })
  }

  return (
    <div className="timeline-editor">
      <div
        ref={rulerRef}
        data-testid="timeline-ruler"
        className="timeline-ruler"
        style={{ width: totalWidth }}
        onClick={handleRulerClick}
      >
        <div
          className="timeline-playhead"
          style={{ left: Math.max(0, Math.min(duration, currentTime)) * PX_PER_SECOND }}
        />
      </div>
      <div className="timeline-track" style={{ width: totalWidth }}>
        {orderedSegments.map((segment, index) => {
          const offset = orderedSegments
            .slice(0, index)
            .reduce((sum, item) => sum + Math.max(0.1, item.trim_out - item.trim_in), 0)
          const width = Math.max(28, (segment.trim_out - segment.trim_in) * PX_PER_SECOND)
          const isDeleted = segment.deleted
          return (
            <div
              key={segment.id}
              data-segment-id={segment.id}
              className={[
                'timeline-segment',
                selectedId === segment.id ? 'selected' : '',
                isDeleted ? 'deleted' : '',
              ].filter(Boolean).join(' ')}
              style={{ left: offset * PX_PER_SECOND, width }}
              onClick={(event) => {
                event.stopPropagation()
                onSelect(segment.id)
              }}
              draggable={!isDeleted}
              onDragStart={(event) => event.dataTransfer.setData('text/plain', segment.id)}
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => {
                event.preventDefault()
                commitReorder(event.dataTransfer.getData('text/plain'), segment.id)
              }}
            >
              <span className="segment-label">{segment.shot_id}</span>
              <span className="segment-duration">
                {Math.max(0, segment.trim_out - segment.trim_in).toFixed(1)}s
              </span>
              {!isDeleted && (
                <>
                  <div
                    data-testid={`trim-in-${segment.id}`}
                    className="trim-handle trim-in"
                    onMouseDown={(event) => {
                      event.stopPropagation()
                      startTrim(event, segment, 'in', updateSegment)
                    }}
                  />
                  <div
                    data-testid={`trim-out-${segment.id}`}
                    className="trim-handle trim-out"
                    onMouseDown={(event) => {
                      event.stopPropagation()
                      startTrim(event, segment, 'out', updateSegment)
                    }}
                  />
                </>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function startTrim(
  event: ReactMouseEvent,
  segment: Pick<Segment, 'id' | 'trim_in' | 'trim_out'>,
  edge: 'in' | 'out',
  update: (id: string, patch: Partial<Pick<Segment, 'trim_in' | 'trim_out'>>) => void,
) {
  const startX = event.clientX
  const original = edge === 'in' ? segment.trim_in : segment.trim_out

  function onMove(moveEvent: globalThis.MouseEvent) {
    const delta = (moveEvent.clientX - startX) / PX_PER_SECOND
    const value = Math.max(0, original + delta)
    if (edge === 'in') {
      update(segment.id, { trim_in: Math.min(value, segment.trim_out - 0.1) })
    } else {
      update(segment.id, { trim_out: Math.max(value, segment.trim_in + 0.1) })
    }
  }

  function onUp() {
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
  }

  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}
