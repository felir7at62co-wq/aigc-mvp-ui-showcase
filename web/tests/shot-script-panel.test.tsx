import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { Segment } from '../src/api/types'
import { ShotScriptPanel } from '../src/features/video-generation/ShotScriptPanel'

const segments = [
  { id: '01-001', shot_id: 'shot-001', order: 0, deleted: false, trim_in: 0, trim_out: 5, source_video: 'a.mp4' },
  { id: '01-002', shot_id: 'shot-002', order: 1, deleted: false, trim_in: 0, trim_out: 4, source_video: 'b.mp4' },
] as Segment[]

const script = '镜头1：推门进入\n出镜人物【主角】\n画面描述：【中景缓慢推进】\n\n镜头2：回头\n出镜人物【主角】\n画面描述：【近景紧张神情】'

describe('ShotScriptPanel', () => {
  it('renders each complete shot block instead of the timeline prompt summary', () => {
    render(<ShotScriptPanel script={script} segments={segments} selectedId="01-001" onSelect={vi.fn()} />)
    expect(screen.getByRole('button', { name: /shot-001/ })).toHaveTextContent('镜头1：')
    expect(screen.getByRole('button', { name: /shot-001/ })).toHaveTextContent('推门进入')
    expect(screen.getByRole('button', { name: /shot-001/ })).toHaveTextContent('出镜人物【主角】')
    expect(screen.getByRole('button', { name: /shot-002/ })).toHaveTextContent('画面描述：【近景紧张神情】')
    expect(document.querySelectorAll('.video-shot-item')).toHaveLength(2)
  })

  it('scrolls the matching script block into view after timeline selection', () => {
    const scrollIntoView = vi.fn()
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { callback(0); return 1 })
    Element.prototype.scrollIntoView = scrollIntoView
    const view = render(<ShotScriptPanel script={script} segments={segments} selectedId="01-001" onSelect={vi.fn()} />)
    scrollIntoView.mockClear()

    view.rerender(<ShotScriptPanel script={script} segments={segments} selectedId="01-002" onSelect={vi.fn()} />)

    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'nearest' })
    vi.unstubAllGlobals()
  })

  it('selects the nearest timeline segment when the script list is scrolled', () => {
    const onSelect = vi.fn()
    render(<ShotScriptPanel script={script} segments={segments} selectedId={null} onSelect={onSelect} />)
    const list = screen.getByTestId('shot-script-scroll')
    const items = Array.from(list.querySelectorAll<HTMLElement>('[data-shot-number]'))
    Object.defineProperty(items[0], 'offsetTop', { value: 0 })
    Object.defineProperty(items[1], 'offsetTop', { value: 180 })
    Object.defineProperty(list, 'scrollTop', { value: 170, writable: true })

    fireEvent.scroll(list)

    expect(onSelect).toHaveBeenCalledWith('01-002')
  })
})
