import type { HealthResponse } from '../types/api'

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
