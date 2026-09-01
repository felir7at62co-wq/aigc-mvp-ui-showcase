import { apiDelete, apiGet, apiPost, apiPut } from './client'
import type {
  EpisodeSummary,
  ExportStatus,
  PreviewStatus,
  ProjectSummary,
  ShotScript,
  TaskRecord,
  TimelineCreateRequest,
  TimelineManifest,
  AssetCatalog,
  AssetCategory,
  AssetInput,
  AssetRecord,
  ProjectCreationSettings,
  ProjectSettings,
} from './types'

export interface ProjectListItem {
  name: string
  created_at: string
  updated_at: string
}

export function fetchProjects(): Promise<ProjectListItem[]> {
  return apiGet<{ projects: ProjectListItem[] }>('/api/projects').then(
    (payload) => payload.projects,
  )
}

export function fetchProjectSummary(name: string): Promise<ProjectSummary> {
  return apiGet(`/api/projects/${encodeURIComponent(name)}`)
}

export function createProject(
  name: string,
  scriptFile: File,
  settings: ProjectCreationSettings = {
    aspect_ratio: '9:16', resolution: '720p', prompt_prefix: '',
  },
): Promise<ProjectSummary> {
  const form = new FormData()
  form.append('name', name)
  form.append('script', scriptFile)
  form.append('aspect_ratio', settings.aspect_ratio)
  form.append('resolution', settings.resolution)
  form.append('prompt_prefix', settings.prompt_prefix)
  return fetch('/api/projects', { method: 'POST', body: form }).then(async (response) => {
    const payload = await response.json()
    if (!response.ok) {
      throw new Error(
        payload && typeof payload === 'object' && 'error' in payload
          ? String((payload as { error: unknown }).error)
          : `创建失败 ${response.status}`,
      )
    }
    return payload as ProjectSummary
  })
}

export function fetchProjectSettings(name: string): Promise<ProjectSettings> {
  return apiGet(`/api/projects/${encodeURIComponent(name)}/settings`)
}

export function saveProjectSettings(
  name: string,
  settings: ProjectCreationSettings,
): Promise<ProjectSettings> {
  return apiPut(`/api/projects/${encodeURIComponent(name)}/settings`, settings)
}

export function deleteProject(name: string): Promise<{ ok: boolean }> {
  return apiDelete(`/api/projects/${encodeURIComponent(name)}`)
}

export function fetchEpisodes(name: string): Promise<{ episodes: EpisodeSummary[] }> {
  return apiGet(`/api/projects/${encodeURIComponent(name)}/episodes`)
}

export function fetchEpisodeDetail(name: string, episodeId: string): Promise<unknown> {
  return apiGet(`/api/projects/${encodeURIComponent(name)}/episodes/${episodeId}`)
}

export function submitTask(
  name: string,
  step: string,
  episodes: string[],
  options: Record<string, unknown> = {},
): Promise<{ task_id: string; status: string }> {
  return apiPost(`/api/projects/${encodeURIComponent(name)}/tasks`, {
    step,
    episodes,
    options,
  })
}

export function fetchTasks(name: string): Promise<TaskRecord[]> {
  return apiGet(`/api/projects/${encodeURIComponent(name)}/tasks`).then(
    (payload) => (payload as { tasks: TaskRecord[] }).tasks,
  )
}

export function fetchTask(name: string, taskId: string): Promise<TaskRecord> {
  return apiGet(`/api/projects/${encodeURIComponent(name)}/tasks/${taskId}`)
}

export function fetchTimeline(name: string, episodeId: string): Promise<TimelineManifest> {
  return apiGet(`/api/projects/${encodeURIComponent(name)}/timeline/${episodeId}`)
}

export function saveTimeline(
  name: string,
  episodeId: string,
  timeline: TimelineManifest | TimelineCreateRequest,
): Promise<TimelineManifest> {
  return apiPut(`/api/projects/${encodeURIComponent(name)}/timeline/${episodeId}`, timeline)
}

export function triggerPreview(name: string, episodeId: string): Promise<{ task_id: string }> {
  return apiPost(`/api/projects/${encodeURIComponent(name)}/preview/${episodeId}`, {})
}

export function fetchPreview(name: string, episodeId: string): Promise<PreviewStatus> {
  return apiGet(`/api/projects/${encodeURIComponent(name)}/preview/${episodeId}`)
}

export function triggerExport(name: string, episodes: string[], prefix: string): Promise<{ task_id: string }> {
  return apiPost(`/api/projects/${encodeURIComponent(name)}/exports`, { episodes, prefix })
}

export function fetchExports(name: string): Promise<{
  episodes: Record<string, { status: string; output_path: string; error: string }>
}> {
  return apiGet(`/api/projects/${encodeURIComponent(name)}/exports`)
}

export function fetchEpisodeVideos(name: string, episodeId: string): Promise<{ videos: string[] }> {
  return apiGet(`/api/projects/${encodeURIComponent(name)}/episodes/${episodeId}/videos`)
}

export function uploadEpisodeVideo(
  name: string,
  episodeId: string,
  file: File,
): Promise<{ video_path: string }> {
  const form = new FormData()
  form.append('file', file)
  return fetch(`/api/projects/${encodeURIComponent(name)}/episodes/${episodeId}/videos`, {
    method: 'POST',
    body: form,
  }).then(async (response) => {
    const payload: unknown = await response.json().catch(() => null)
    if (!response.ok) {
      const error = payload && typeof payload === 'object' && 'error' in payload
        ? String((payload as { error: unknown }).error)
        : `Upload failed ${response.status}`
      throw new Error(error)
    }
    return payload as { video_path: string }
  })
}

export function fetchShotScript(name: string, episodeId: string): Promise<ShotScript> {
  return apiGet(`/api/projects/${encodeURIComponent(name)}/shots/${episodeId}`)
}

export function fetchEpisodeExports(name: string): Promise<{
  episodes: Record<string, ExportStatus>
}> {
  return apiGet(`/api/projects/${encodeURIComponent(name)}/exports`)
}

export function fetchAssetCatalog(name: string): Promise<AssetCatalog> {
  return apiGet<{ assets: AssetCatalog }>(
    `/api/projects/${encodeURIComponent(name)}/assets`,
  ).then((payload) => payload.assets)
}

export function createAsset(
  name: string,
  input: AssetInput & { category: AssetCategory },
): Promise<{ asset: AssetRecord }> {
  return apiPost(`/api/projects/${encodeURIComponent(name)}/assets`, input)
}

export function updateAsset(
  name: string,
  category: AssetCategory,
  originalName: string,
  input: AssetInput,
): Promise<{ asset: AssetRecord }> {
  return apiPost(
    `/api/projects/${encodeURIComponent(name)}/assets/${category}/${encodeURIComponent(originalName)}`,
    input,
  )
}

export function deleteAsset(
  name: string,
  category: AssetCategory,
  assetName: string,
): Promise<{ ok: boolean }> {
  return apiDelete(
    `/api/projects/${encodeURIComponent(name)}/assets/${category}/${encodeURIComponent(assetName)}`,
  )
}

export function uploadAssetImage(
  name: string,
  category: AssetCategory,
  assetName: string,
  file: File,
): Promise<{ image_path: string }> {
  const form = new FormData()
  form.append('file', file)
  return fetch(
    `/api/projects/${encodeURIComponent(name)}/assets/${category}/${encodeURIComponent(assetName)}/image`,
    { method: 'POST', body: form },
  ).then(async (response) => {
    const payload: unknown = await response.json().catch(() => null)
    if (!response.ok) {
      throw new Error(
        payload && typeof payload === 'object' && 'error' in payload
          ? String((payload as { error: unknown }).error)
          : `图片上传失败 ${response.status}`,
      )
    }
    return payload as { image_path: string }
  })
}
