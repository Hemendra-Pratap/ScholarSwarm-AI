import type {
  HealthResponse,
  IngestionResponse,
  StudentProfileCreate,
  StudentProfileRead,
  ResearchRunExecutionRequest,
  ResearchRunExecutionResponse,
  DocumentType,
} from '../types/api'

export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ||
  'http://127.0.0.1:8000'

export interface HealthCheckResult {
  data: HealthResponse | null
  error: string | null
  latencyMs: number | null
}

export async function fetchBackendHealth(timeoutMs = 4000): Promise<HealthCheckResult> {
  const startTime = performance.now()
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs)

  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/health`, {
      method: 'GET',
      headers: {
        Accept: 'application/json',
      },
      signal: controller.signal,
    })

    const latencyMs = Math.round(performance.now() - startTime)

    if (!response.ok) {
      return {
        data: null,
        error: `HTTP error ${response.status}: ${response.statusText}`,
        latencyMs,
      }
    }

    const data: HealthResponse = await response.json()
    return {
      data,
      error: null,
      latencyMs,
    }
  } catch (err) {
    const latencyMs = Math.round(performance.now() - startTime)
    if (err instanceof DOMException && err.name === 'AbortError') {
      return {
        data: null,
        error: `Request timed out after ${timeoutMs}ms`,
        latencyMs,
      }
    }
    return {
      data: null,
      error: err instanceof Error ? err.message : 'Unknown network error',
      latencyMs,
    }
  } finally {
    clearTimeout(timeoutId)
  }
}

export interface IngestionResult {
  data: IngestionResponse | null
  error: string | null
}

export async function ingestDocument(
  file: File,
  documentType: DocumentType = 'resume',
  signal?: AbortSignal,
): Promise<IngestionResult> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('document_type', documentType)

  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/profiles/ingest`, {
      method: 'POST',
      body: formData,
      headers: {
        Accept: 'application/json',
      },
      signal,
    })

    if (!response.ok) {
      let detail = `Upload failed with HTTP ${response.status}`
      try {
        const errorBody = await response.json()
        if (errorBody && typeof errorBody.detail === 'string') {
          detail = errorBody.detail
        }
      } catch {
        // Fall back to generic message
      }
      return { data: null, error: detail }
    }

    const data: IngestionResponse = await response.json()
    return { data, error: null }
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      return { data: null, error: 'Upload cancelled' }
    }
    return {
      data: null,
      error: err instanceof Error ? err.message : 'Network error during ingestion',
    }
  }
}

export interface ConfirmProfileResult {
  data: StudentProfileRead | null
  error: string | null
}

export async function confirmProfile(
  profile: StudentProfileCreate,
  signal?: AbortSignal,
): Promise<ConfirmProfileResult> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/profiles/confirm`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify(profile),
      signal,
    })

    if (!response.ok) {
      let detail = `Profile confirmation failed with HTTP ${response.status}`
      try {
        const errorBody = await response.json()
        if (errorBody && typeof errorBody.detail === 'string') {
          detail = errorBody.detail
        }
      } catch {
        // Fall back to generic message
      }
      return { data: null, error: detail }
    }

    const data: StudentProfileRead = await response.json()
    return { data, error: null }
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      return { data: null, error: 'Confirmation cancelled' }
    }
    return {
      data: null,
      error: err instanceof Error ? err.message : 'Network error during profile confirmation',
    }
  }
}

export interface ResearchRunResult {
  data: ResearchRunExecutionResponse | null
  error: string | null
}

export async function executeResearchRun(
  request: ResearchRunExecutionRequest,
  signal?: AbortSignal,
): Promise<ResearchRunResult> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/research/runs`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify(request),
      signal,
    })

    if (!response.ok) {
      let detail = `Research run failed with HTTP ${response.status}`
      try {
        const errorBody = await response.json()
        if (errorBody && typeof errorBody.detail === 'string') {
          detail = errorBody.detail
        }
      } catch {
        // Fall back to generic message
      }
      return { data: null, error: detail }
    }

    const data: ResearchRunExecutionResponse = await response.json()
    return { data, error: null }
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      return { data: null, error: 'Research run cancelled' }
    }
    return {
      data: null,
      error: err instanceof Error ? err.message : 'Network error during research execution',
    }
  }
}
