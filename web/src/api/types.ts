export interface StepStateView {
  status: string
  error?: string | null
  output_count?: number
  legacy_step?: string
}

export interface ProjectSummary {
  name: string
  created_at: string
  updated_at: string
  episode_count: number
  episodes: { total: number; by_status: Record<string, number> }
  steps: Record<string, StepStateView>
}

export interface ProjectSettings {
  video_model: 'seedance-2-0-official'
  image_model: 'gpt-image-2-official'
  generation_mode: 'reference'
  aspect_ratio: '16:9' | '9:16' | '1:1' | '4:3' | '3:4' | '21:9'
  resolution: '480p' | '720p' | '1080p'
  batch_duration: 15
  prompt_prefix: string
  api_configured?: boolean
}

export type ProjectCreationSettings = Pick<
  ProjectSettings,
  'aspect_ratio' | 'resolution' | 'prompt_prefix'
>

export interface EpisodeSummary {
  episode_id: string
  marker: string
  line_range: [number, number]
  shot_match_status: string
}

export interface TaskRecord {
  id: string
  project: string
  step: string
  episode_ids: string[]
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
  created_at: number
  finished_at: number | null
  error: string
  results: Record<string, string>
  failures: Record<string, string>
}

export interface Transition {
  type: 'hard' | 'crossfade' | 'fade_black'
  duration: number
}

export interface Segment {
  id: string
  shot_id: string
  source_video: string
  prompt: string
  asset_ids: string[]
  trim_in: number
  trim_out: number
  order: number
  selected_version: string
  deleted: boolean
  transition_to_next: Transition
}

export interface TimelineManifest {
  episode_id: string
  version: number
  fps: number
  width: number
  height: number
  segments: Segment[]
  preview_video: string
  jianying_project: string
}

export interface TimelineCreateRequest {
  episode_id: string
  version: number
  fps: number
  width: number
  height: number
  create_if_missing: true
}

export interface PreviewStatus {
  status: string
  preview_path: string
  error: string
  updated_at: string
  metadata: Record<string, number | string>
}

export interface VideoFile {
  path: string
}

export interface MatchShot {
  shot: number
  characters: { input: string; name: string; matched: boolean }[]
  scene: { input: string; name: string; matched: boolean }
  props: { input: string; name: string; matched: boolean }[]
}

export interface MatchManifest {
  version: number
  episode: string
  shots: MatchShot[]
}

export interface ShotScript {
  episode_id: string
  script: string
  match: MatchManifest | null
}

export interface ExportStatus {
  status: string
  output_path: string
  error: string
}

export type AssetCategory = 'character' | 'scene' | 'prop'

export interface AssetRecord {
  name: string
  aliases: string[]
  episodes: string[]
  prompt: string
  category: AssetCategory
  image_path: string
}

export type AssetCatalog = Record<AssetCategory, AssetRecord[]>

export interface AssetInput {
  category?: AssetCategory
  name: string
  aliases: string
  episodes: string
  prompt: string
}
