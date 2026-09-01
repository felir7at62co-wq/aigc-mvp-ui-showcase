import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { TimelineEditor } from '../src/components/TimelineEditor'
import type { TimelineManifest } from '../src/api/types'

function makeTimeline(): TimelineManifest {
  return {
    episode_id: '01',
    version: 1,
    fps: 30,
    width: 1080,
    height: 1920,
    segments: [
      {
        id: '01-001',
        shot_id: 'shot-001',
        source_video: 'a.mp4',
        prompt: 'first shot',
        asset_ids: [],
        trim_in: 0,
        trim_out: 5,
        order: 0,
        selected_version: 'v1',
        deleted: false,
        transition_to_next: { type: 'hard', duration: 0 },
      },
      {
        id: '01-002',
        shot_id: 'shot-002',
        source_video: 'b.mp4',
        prompt: 'second shot',
        asset_ids: [],
        trim_in: 0,
        trim_out: 4,
        order: 1,
        selected_version: 'v1',
        deleted: false,
        transition_to_next: { type: 'hard', duration: 0 },
      },
    ],
    preview_video: '',
    jianying_project: '',
  }
}

describe('TimelineEditor', () => {
  it('renders segments and selects a segment', () => {
    const onSelect = vi.fn()
    render(
      <TimelineEditor
        timeline={makeTimeline()}
        selectedId={null}
        currentTime={0}
        duration={9}
        onSelect={onSelect}
        onCommit={vi.fn()}
        onSeek={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByText('shot-001'))
    expect(onSelect).toHaveBeenCalledWith('01-001')
  })

  it('commits a changed trim value after dragging a trim handle', () => {
    const onCommit = vi.fn()
    render(
      <TimelineEditor
        timeline={makeTimeline()}
        selectedId="01-001"
        currentTime={0}
        duration={9}
        onSelect={vi.fn()}
        onCommit={onCommit}
        onSeek={vi.fn()}
      />,
    )
    const handle = screen.getByTestId('trim-in-01-001')

    fireEvent.mouseDown(handle, { clientX: 0 })
    fireEvent.mouseMove(window, { clientX: 40 })
    fireEvent.mouseUp(window)

    expect(onCommit).toHaveBeenCalled()
    const updated = onCommit.mock.calls[0][0] as TimelineManifest
    expect(updated.segments.find((segment) => segment.id === '01-001')?.trim_in).toBeGreaterThan(0)
  })

  it('seeks when the ruler is clicked', () => {
    const onSeek = vi.fn()
    render(
      <TimelineEditor
        timeline={makeTimeline()}
        selectedId={null}
        currentTime={0}
        duration={9}
        onSelect={vi.fn()}
        onCommit={vi.fn()}
        onSeek={onSeek}
      />,
    )

    fireEvent.click(screen.getByTestId('timeline-ruler'), { clientX: 120 })
    expect(onSeek).toHaveBeenCalledWith(expect.any(Number))
  })

  it('commits a new order when one segment is dropped onto another', () => {
    const onCommit = vi.fn()
    render(
      <TimelineEditor
        timeline={makeTimeline()}
        selectedId={null}
        currentTime={0}
        duration={9}
        onSelect={vi.fn()}
        onCommit={onCommit}
        onSeek={vi.fn()}
      />,
    )
    const dataTransfer = {
      getData: vi.fn(() => '01-002'),
      setData: vi.fn(),
    }

    fireEvent.drop(screen.getByText('shot-001'), { dataTransfer })

    const updated = onCommit.mock.calls[0][0] as TimelineManifest
    expect(updated.segments.find((segment) => segment.id === '01-002')?.order).toBe(0)
    expect(updated.segments.find((segment) => segment.id === '01-001')?.order).toBe(1)
  })

  it('keeps deleted segments visible with a deleted style', () => {
    const timeline = makeTimeline()
    timeline.segments[1].deleted = true
    render(
      <TimelineEditor
        timeline={timeline}
        selectedId={null}
        currentTime={0}
        duration={5}
        onSelect={vi.fn()}
        onCommit={vi.fn()}
        onSeek={vi.fn()}
      />,
    )

    expect(screen.getByText('shot-002').closest('[data-segment-id="01-002"]')).toHaveClass('deleted')
  })
})
