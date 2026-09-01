import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { ExportPanel } from '../src/components/ExportPanel'
import { SegmentInspector } from '../src/components/SegmentInspector'
import type { Segment } from '../src/api/types'

const segment: Segment = {
  id: '01-001',
  shot_id: 'shot-001',
  source_video: 'a.mp4',
  prompt: 'first shot',
  asset_ids: ['character-main'],
  trim_in: 0,
  trim_out: 5,
  order: 0,
  selected_version: 'v1',
  deleted: false,
  transition_to_next: { type: 'hard', duration: 0 },
}

describe('SegmentInspector', () => {
  it('shows segment details and expandable script content', () => {
    render(<SegmentInspector segment={segment} script="full shot script" />)

    expect(screen.getByText('shot-001')).toBeTruthy()
    expect(screen.getByText('first shot')).toBeTruthy()
    expect(screen.getByText('character-main')).toBeTruthy()
    fireEvent.click(screen.getByText('查看完整镜头脚本'))
    expect(screen.getByText('full shot script')).toBeTruthy()
  })

  it('reports a transition change with the default transition duration', () => {
    const onChange = vi.fn()
    render(<SegmentInspector segment={segment} onChange={onChange} />)

    fireEvent.change(screen.getByLabelText('转场'), { target: { value: 'crossfade' } })
    expect(onChange).toHaveBeenCalledWith({ type: 'crossfade', duration: 0.35 })
  })

  it('offers delete and restore actions for the current segment state', () => {
    const onDelete = vi.fn()
    const onRestore = vi.fn()
    const { rerender } = render(<SegmentInspector segment={segment} onDelete={onDelete} />)

    fireEvent.click(screen.getByRole('button', { name: '删除片段' }))
    expect(onDelete).toHaveBeenCalledWith('01-001')

    rerender(
      <SegmentInspector
        segment={{ ...segment, deleted: true }}
        onRestore={onRestore}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: '恢复片段' }))
    expect(onRestore).toHaveBeenCalledWith('01-001')
  })
})

describe('ExportPanel', () => {
  it('renders both export actions and their statuses', () => {
    render(
      <ExportPanel
        mp4Status="completed"
        draftStatus="failed"
        onExportMp4={vi.fn()}
        onExportDraft={vi.fn()}
      />,
    )

    expect(screen.getByRole('button', { name: '导出 MP4' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '导出剪映工程' })).toBeTruthy()
    expect(screen.getAllByTestId('status-badge')).toHaveLength(2)
  })

  it('calls the matching export callback', () => {
    const onMp4 = vi.fn()
    const onDraft = vi.fn()
    render(
      <ExportPanel
        mp4Status="pending"
        draftStatus="pending"
        onExportMp4={onMp4}
        onExportDraft={onDraft}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: '导出 MP4' }))
    fireEvent.click(screen.getByRole('button', { name: '导出剪映工程' }))
    expect(onMp4).toHaveBeenCalledTimes(1)
    expect(onDraft).toHaveBeenCalledTimes(1)
  })
})
