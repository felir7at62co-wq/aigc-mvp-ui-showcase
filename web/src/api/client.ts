export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request(path: string, init: RequestInit = {}): Promise<unknown> {
  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...(init.body ? { 'Content-Type': 'application/json' } : {}),
    ...(init.headers as Record<string, string> | undefined),
  }
  const response = await fetch(path, { ...init, headers })
  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    const message =
      payload && typeof payload === 'object' && 'error' in payload
        ? String((payload as { error: unknown }).error)
        : `${response.status} ${response.statusText}`
    throw new ApiError(response.status, message)
  }
  return payload
}

export function apiGet<T>(path: string): Promise<T> {
  return request(path) as Promise<T>
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return request(path, {
    method: 'POST',
    body: body === undefined ? undefined : JSON.stringify(body),
  }) as Promise<T>
}

export function apiPut<T>(path: string, body?: unknown): Promise<T> {
  return request(path, {
    method: 'PUT',
    body: body === undefined ? undefined : JSON.stringify(body),
  }) as Promise<T>
}

export function apiDelete<T>(path: string): Promise<T> {
  return request(path, { method: 'DELETE' }) as Promise<T>
}

export function mediaUrl(project: string, relativePath: string): string {
  return `/api/projects/${encodeURIComponent(project)}/media/${relativePath}`
}
