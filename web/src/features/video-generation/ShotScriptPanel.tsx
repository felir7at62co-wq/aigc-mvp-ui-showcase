import { useEffect, useMemo, useRef } from 'react'
import type { UIEvent } from 'react'
import type { Segment } from '../../api/types'
import { scriptSections, shotNumberFromId } from './model'

interface ShotScriptPanelProps {
  script: string
  segments: Segment[]
  selectedId: string | null
  onSelect: (segmentId: string) => void
}

export function ShotScriptPanel({ script, segments, selectedId, onSelect }: ShotScriptPanelProps) {
  const ordered = useMemo(() => [...segments].sort((a, b) => a.order - b.order), [segments])
  const sections = useMemo(() => scriptSections(script), [script])
  const itemRefs = useRef(new Map<number, HTMLElement>())
  const suppressNextScroll = useRef(false)
  const selectedSegment = ordered.find((segment) => segment.id === selectedId)
  const selectedShotNumber = selectedSegment ? shotNumberFromId(selectedSegment.shot_id) : null

  function segmentForShot(shotNumber: number | null) {
    if (shotNumber === null) return null
    return ordered.find((segment) => shotNumberFromId(segment.shot_id) === shotNumber) ?? null
  }

  useEffect(() => {
    if (selectedShotNumber === null) return
    const item = itemRefs.current.get(selectedShotNumber)
    if (!item?.scrollIntoView) return
    suppressNextScroll.current = true
    item.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    requestAnimationFrame(() => { suppressNextScroll.current = false })
  }, [selectedShotNumber])

  function handleScroll(event: UIEvent<HTMLDivElement>) {
    if (suppressNextScroll.current) {
      suppressNextScroll.current = false
      return
    }
    const container = event.currentTarget
    let nearest: { shotNumber: number; distance: number } | null = null
    for (const [shotNumber, item] of itemRefs.current) {
      const distance = Math.abs(item.offsetTop - container.scrollTop)
      if (!nearest || distance < nearest.distance) nearest = { shotNumber, distance }
    }
    const segment = segmentForShot(nearest?.shotNumber ?? null)
    if (segment && segment.id !== selectedId) onSelect(segment.id)
  }

  return (
    <section className="video-production-panel video-shot-panel" aria-label="镜头脚本">
      <header className="video-panel-head">
        <h2>镜头脚本</h2>
        <span>{sections.length} 个镜头</span>
      </header>
      <div className="video-shot-list" data-testid="shot-script-scroll" onScroll={handleScroll}>
        {sections.length === 0 && <div className="video-panel-empty">请先生成镜头脚本。</div>}
        {sections.map((section, index) => {
          const shotNumber = section.shotNumber ?? index + 1
          const segment = segmentForShot(shotNumber)
          const completeBlock = `镜头${shotNumber}：${section.body ? `\n${section.body}` : ''}`
          return (
            <button
              key={`${shotNumber}-${index}`}
              ref={(element) => {
                if (element) itemRefs.current.set(shotNumber, element)
                else itemRefs.current.delete(shotNumber)
              }}
              data-shot-number={shotNumber}
              type="button"
              aria-label={`${segment?.shot_id ?? `shot-${String(shotNumber).padStart(3, '0')}`} 镜头${shotNumber}`}
              className={`video-shot-item${selectedShotNumber === shotNumber ? ' active' : ''}${segment?.deleted ? ' deleted' : ''}`}
              onClick={() => { if (segment) onSelect(segment.id) }}
            >
              <span className="video-shot-item-head">
                <strong>镜头 {String(shotNumber).padStart(3, '0')}</strong>
                <small>{segment ? `${Math.max(0, segment.trim_out - segment.trim_in).toFixed(1)} 秒` : '等待视频'}</small>
              </span>
              <pre className="video-shot-script-block">{completeBlock}</pre>
              <span className="video-shot-meta">
                {segment?.source_video ? '视频已生成' : '等待生成'}
                {segment?.deleted ? ' · 已从轨道移除' : ''}
              </span>
            </button>
          )
        })}
      </div>
    </section>
  )
}
