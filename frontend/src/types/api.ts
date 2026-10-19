export interface HealthResponse {
  status: string
  app_name: string
  version: string
}

export type HealthStatusState = 'loading' | 'online' | 'offline'
