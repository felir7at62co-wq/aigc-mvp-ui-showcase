import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  fetchEpisodeExports,
  fetchEpisodes,
  fetchPreview,
  fetchShotScript,
  fetchTimeline,
  saveTimeline,
  submitTask,
  triggerExport,
  triggerPreview,
  uploadEpisodeVideo,
} from '../api/projects'
import { mediaUrl } from '../api/client'
import type { Segment, TimelineManifest } from '../api/types'
import { Button } from '../components/Button'
import { EmptyState } from '../components/EmptyState'
import { ExportPanel } from '../components/ExportPanel'
import { SegmentInspector } from '../components/SegmentInspector'
import { StatusBadge } from '../components/StatusBadge'
import { TimelineEditor } from '../components/TimelineEditor'
import { VideoPlayer, type VideoPlayerHandle } from '../components/VideoPlayer'
import { AssetMatchPanel } from '../features/video-generation/AssetMatchPanel'
import { EpisodeRail } from '../features/video-generation/EpisodeRail'
import { EpisodeScriptPanel } from '../features/video-generation/EpisodeScriptPanel'
import { ShotScriptPanel } from '../features/video-generation/ShotScriptPanel'
import {
  findShotMatch,
  firstActiveSegmentId,
  shotNumberFromId,
} from '../features/video-generation/model'
import { usePolling } from '../hooks/usePolling'

export function EpisodeStudioPage() {
  const { projectName = '', episodeId = '' } = useParams()
  const playerRef = useRef<VideoPlayerHandle | null>(null)

  const timelineLoader = useCallback(
    () => fetchTimeline(projectName, episodeId),
    [projectName, episodeId],
  )
  const previewLoader = useCallback(
    () => fetchPreview(projectName, episodeId),
    [projectName, episodeId],
  )
  const exportsLoader = useCallback(
    () => fetchEpisodeExports(projectName),
    [projectName],
  )
  const shotScriptLoader = useCallback(
    () => fetchShotScript(projectName, episodeId),
    [projectName, episodeId],
  )
  const episodesLoader = useCallback(
    () => fetchEpisodes(projectName),
    [projectName],
  )

  const { data: timeline, error: timelineError, refresh: refreshTimeline } = usePolling(timelineLoader, 20000)
  const { data: preview, refresh: refreshPreview } = usePolling(previewLoader, 3000)
  const { data: exportData, refresh: refreshExports } = usePolling(exportsLoader, 5000)
  const { data: shotScript } = usePolling(shotScriptLoader, 60000)
  const { data: episodesData } = usePolling(episodesLoader, 10000)

  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [message, setMessage] = useState('')

  useEffect(() => {
    setSelectedId(null)
    setCurrentTime(0)
  }, [episodeId])

  useEffect(() => {
    if (!timeline) return
    const selectionExists = timeline.segments.some(
      (segment) => segment.id === selectedId && !segment.deleted,
    )
    if (!selectionExists) setSelectedId(firstActiveSegmentId(timeline))
  }, [selectedId, timeline])

  const selected: Segment | null =
    timeline?.segments.find((segment) => segment.id === selectedId) ?? null
  const selectedShotNumber = selected ? shotNumberFromId(selected.shot_id) : null
  const selectedMatch = selected ? findShotMatch(shotScript?.match, selected.shot_id) : null

  async function handleCreateTimeline() {
    try {
      await saveTimeline(projectName, episodeId, {
        episode_id: episodeId,
        version: 0,
        fps: 30,
        width: 1080,
        height: 1920,
        create_if_missing: true,
      })
      refreshTimeline()
      const previewTask = await triggerPreview(projectName, episodeId)
      setMessage(`视频轨道已初始化，预览任务 ${previewTask.task_id}`)
      refreshPreview()
    } catch (err) {
      setMessage(err instanceof Error ? err.message : String(err))
    }
  }

  function segmentStart(segmentId: string): number {
    if (!timeline) return 0
    const active = timeline.segments
      .filter((segment) => !segment.deleted)
      .sort((a, b) => a.order - b.order)
    const index = active.findIndex((segment) => segment.id === segmentId)
    if (index < 0) return 0
    return active.slice(0, index).reduce((start, segment) => {
      const segmentDuration = Math.max(0, segment.trim_out - segment.trim_in)
      const overlap = segment.transition_to_next.type === 'crossfade'
        ? segment.transition_to_next.duration
        : 0
      return Math.max(0, start + segmentDuration - overlap)
    }, 0)
  }

  function handleSelect(segmentId: string) {
    setSelectedId(segmentId)
    handleSeek(segmentStart(segmentId))
  }

  async function handleCommit(next: TimelineManifest) {
    try {
      await saveTimeline(projectName, episodeId, next)
      refreshTimeline()
      const previewTask = await triggerPreview(projectName, episodeId)
      setMessage(`已保存（v${next.version}），预览任务 ${previewTask.task_id}`)
      refreshPreview()
    } catch (err) {
      setMessage(err instanceof Error ? err.message : String(err))
    }
  }

  async function handleDelete(segmentId: string) {
    if (!timeline) return
    await handleCommit({
      ...timeline,
      segments: timeline.segments.map((segment) =>
        segment.id === segmentId ? { ...segment, deleted: true } : segment,
      ),
    })
  }

  async function handleRestore(segmentId: string) {
    if (!timeline) return
    await handleCommit({
      ...timeline,
      segments: timeline.segments.map((segment) =>
        segment.id === segmentId ? { ...segment, deleted: false } : segment,
      ),
    })
  }

  function handleSeek(seconds: number) {
    playerRef.current?.seek(seconds)
    setCurrentTime(seconds)
  }

  async function handleRunPreparation(step: 'prompt' | 'shot_match', label: string) {
    try {
      const task = await submitTask(projectName, step, [episodeId])
      setMessage(`${label}任务已提交：${task.task_id}`)
    } catch (err) {
      setMessage(err instanceof Error ? err.message : String(err))
    }
  }

  async function handleRegenerate() {
    if (!selected) return
    const shotNumber = shotNumberFromId(selected.shot_id)
    try {
      await submitTask(projectName, 'video', [episodeId], {
        shots: shotNumber === null ? [] : [shotNumber],
      })
      setMessage(`已提交 ${selected.shot_id} 的视频生成任务`)
    } catch (err) {
      setMessage(err instanceof Error ? err.message : String(err))
    }
  }

  async function handleReplaceVideo(file: File) {
    if (!selected || !timeline) return
    try {
      const result = await uploadEpisodeVideo(projectName, episodeId, file)
      await handleCommit({
        ...timeline,
        segments: timeline.segments.map((segment) =>
          segment.id === selected.id ? { ...segment, source_video: result.video_path } : segment,
        ),
      })
    } catch (err) {
      setMessage(err instanceof Error ? err.message : String(err))
    }
  }

  async function handleExportDraft() {
    try {
      await triggerExport(projectName, [episodeId], `${projectName}_`)
      refreshExports()
      setMessage('剪映工程导出任务已提交')
    } catch (err) {
      setMessage(err instanceof Error ? err.message : String(err))
    }
  }

  const fallbackDuration = timeline?.segments
    .filter((segment) => !segment.deleted)
    .reduce((sum, segment) => sum + Math.max(0, segment.trim_out - segment.trim_in), 0) ?? 0
  const selectedVideoUrl = selected?.source_video
    ? mediaUrl(projectName, selected.source_video)
    : ''
  const episodePreviewUrl = preview?.preview_path
    ? mediaUrl(projectName, preview.preview_path)
    : ''
  const previewUrl = selectedVideoUrl || episodePreviewUrl
  const exportStatus = exportData?.episodes[episodeId] ?? {
    status: 'pending',
    output_path: '',
    error: '',
  }
  const segments = timeline?.segments ?? []
  const episodes = episodesData?.episodes ?? []

  return (
    <div className="video-generation-page">
      {message && <div className="video-workbench-message">{message}</div>}

      <div className="video-generation-layout">
        <EpisodeRail
          projectName={projectName}
          currentEpisodeId={episodeId}
          episodes={episodes}
        />

        <EpisodeScriptPanel
          episodeId={episodeId}
          script={shotScript?.script ?? ''}
          currentShotNumber={selectedShotNumber}
        />

        <main className="video-production-area">
          <header className="video-workbench-head">
            <div>
              <span className="video-workbench-kicker">视频生成</span>
              <h1>第 {episodeId} 集</h1>
            </div>
            <div className="video-workbench-actions">
              <StatusBadge status={preview?.status ?? 'pending'} />
              <Button
                variant="secondary"
                size="sm"
                type="button"
                onClick={() => void handleRunPreparation('prompt', '镜头脚本生成')}
              >
                生成镜头脚本
              </Button>
              <Button
                variant="secondary"
                size="sm"
                type="button"
                onClick={() => void handleRunPreparation('shot_match', '资产匹配更新')}
              >
                更新资产匹配
              </Button>
              <Button
                type="button"
                disabled={!selected}
                onClick={() => void handleRegenerate()}
              >
                生成当前镜头视频
              </Button>
            </div>
          </header>

          <div className="video-production-upper">
            <ShotScriptPanel
              script={shotScript?.script ?? ''}
              segments={segments}
              selectedId={selectedId}
              onSelect={handleSelect}
            />

            <AssetMatchPanel
              shot={selectedMatch}
              fallbackAssetIds={selected?.asset_ids ?? []}
            />

            <section className="video-production-panel video-preview-panel" aria-label="视频预览">
              <header className="video-panel-head">
                <h2>视频预览</h2>
                <span>{selected?.shot_id ?? '当前分集'}</span>
              </header>
              <div className="video-preview-body">
                {previewUrl ? (
                  <VideoPlayer
                    ref={playerRef}
                    src={previewUrl}
                    onReady={setDuration}
                    onTimeUpdate={setCurrentTime}
                  />
                ) : (
                  <EmptyState message="当前镜头还没有视频，确认脚本与资产后即可生成。" />
                )}
              </div>
              <footer className="video-preview-foot">
                <span>{selected?.source_video ? '镜头视频' : '分集预览'}</span>
                <span>{selected ? `${Math.max(0, selected.trim_out - selected.trim_in).toFixed(1)} 秒` : '等待选择镜头'}</span>
              </footer>
            </section>
          </div>

          <section className="video-timeline-panel" aria-label="视频轨道">
            <header className="video-panel-head video-timeline-head">
              <div>
                <h2>视频轨道</h2>
                <span>镜头视频生成后在这里完成排序、裁剪和导出</span>
              </div>
              {!timeline && !timelineError && <StatusBadge status="pending" />}
            </header>

            {timelineError && (
              <div className="timeline-error-state video-timeline-empty">
                <div className="form-error">视频轨道加载失败：{timelineError}</div>
                <Button type="button" onClick={() => void handleCreateTimeline()}>
                  初始化视频轨道
                </Button>
              </div>
            )}

            {timeline && (
              <>
                <div className="video-timeline-editor-wrap">
                  <TimelineEditor
                    timeline={timeline}
                    selectedId={selectedId}
                    currentTime={currentTime}
                    duration={duration || fallbackDuration}
                    onSelect={handleSelect}
                    onCommit={handleCommit}
                    onSeek={handleSeek}
                  />
                </div>
                <div className="video-timeline-tools">
                  <div className="video-timeline-inspector">
                    <SegmentInspector
                      segment={selected}
                      script={selected ? shotScript?.script ?? '' : undefined}
                      onDelete={selected && !selected.deleted ? handleDelete : undefined}
                      onRestore={selected?.deleted ? handleRestore : undefined}
                      onChange={(transition) => {
                        if (!selected || !timeline) return
                        void handleCommit({
                          ...timeline,
                          segments: timeline.segments.map((segment) =>
                            segment.id === selected.id
                              ? { ...segment, transition_to_next: transition }
                              : segment,
                          ),
                        })
                      }}
                      onRegenerate={selected ? handleRegenerate : undefined}
                      onReplaceVideo={selected ? handleReplaceVideo : undefined}
                    />
                  </div>
                  <div className="video-timeline-export">
                    <ExportPanel
                      mp4Status={preview?.status ?? 'pending'}
                      draftStatus={exportStatus.status}
                      onExportMp4={() => void handleCommit(timeline)}
                      onExportDraft={() => void handleExportDraft()}
                    />
                  </div>
                </div>
              </>
            )}
          </section>
        </main>
      </div>
    </div>
  )
}
