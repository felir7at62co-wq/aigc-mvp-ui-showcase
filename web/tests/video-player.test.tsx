import { createRef } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { VideoPlayer, type VideoPlayerHandle } from '../src/components/VideoPlayer'

describe('VideoPlayer', () => {
  it('renders the requested video source', () => {
    render(<VideoPlayer src="/preview.mp4" onReady={vi.fn()} />)
    expect((screen.getByTestId('video-element') as HTMLVideoElement).src).toContain('/preview.mp4')
  })

  it('reports metadata, time updates, and ended events', () => {
    const onReady = vi.fn()
    const onTimeUpdate = vi.fn()
    const onEnded = vi.fn()
    render(
      <VideoPlayer
        src="preview.mp4"
        onReady={onReady}
        onTimeUpdate={onTimeUpdate}
        onEnded={onEnded}
      />,
    )
    const video = screen.getByTestId('video-element') as HTMLVideoElement
    Object.defineProperty(video, 'duration', { value: 12.5, configurable: true })
    Object.defineProperty(video, 'currentTime', { value: 3.25, configurable: true, writable: true })

    fireEvent.loadedMetadata(video)
    fireEvent.timeUpdate(video)
    fireEvent.ended(video)

    expect(onReady).toHaveBeenCalledWith(12.5)
    expect(onTimeUpdate).toHaveBeenCalledWith(3.25)
    expect(onEnded).toHaveBeenCalledTimes(1)
  })

  it('exposes seek, playback, pause, and current-time controls through its ref', () => {
    const ref = createRef<VideoPlayerHandle>()
    render(<VideoPlayer ref={ref} src="preview.mp4" onReady={vi.fn()} />)
    const video = screen.getByTestId('video-element') as HTMLVideoElement
    const play = vi.fn(() => Promise.resolve())
    const pause = vi.fn()
    Object.defineProperty(video, 'play', { value: play, configurable: true })
    Object.defineProperty(video, 'pause', { value: pause, configurable: true })
    Object.defineProperty(video, 'currentTime', { value: 1.5, configurable: true, writable: true })

    ref.current?.seek(4)
    ref.current?.play()
    ref.current?.pause()

    expect(video.currentTime).toBe(4)
    expect(play).toHaveBeenCalledTimes(1)
    expect(pause).toHaveBeenCalledTimes(1)
    expect(ref.current?.getCurrentTime()).toBe(4)
  })
})
