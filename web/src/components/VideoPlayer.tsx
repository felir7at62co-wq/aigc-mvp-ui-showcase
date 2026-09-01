import { forwardRef, useImperativeHandle, useRef } from 'react'

export interface VideoPlayerHandle {
  seek: (seconds: number) => void
  play: () => void
  pause: () => void
  getCurrentTime: () => number
}

interface VideoPlayerProps {
  src: string
  onReady: (duration: number) => void
  onTimeUpdate?: (seconds: number) => void
  onEnded?: () => void
}

export const VideoPlayer = forwardRef<VideoPlayerHandle, VideoPlayerProps>(
  function VideoPlayer({ src, onReady, onTimeUpdate, onEnded }, ref) {
    const videoRef = useRef<HTMLVideoElement | null>(null)

    useImperativeHandle(ref, () => ({
      seek: (seconds) => {
        if (videoRef.current) videoRef.current.currentTime = Math.max(0, seconds)
      },
      play: () => {
        void videoRef.current?.play()
      },
      pause: () => {
        videoRef.current?.pause()
      },
      getCurrentTime: () => videoRef.current?.currentTime ?? 0,
    }))

    return (
      <video
        ref={videoRef}
        data-testid="video-element"
        className="player-video"
        src={src}
        controls
        playsInline
        onLoadedMetadata={(event) => onReady(event.currentTarget.duration)}
        onTimeUpdate={(event) => onTimeUpdate?.(event.currentTarget.currentTime)}
        onEnded={onEnded}
      />
    )
  },
)
