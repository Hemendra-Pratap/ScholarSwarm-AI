import React from 'react'
import { CheckCircle2, AlertTriangle, RefreshCw, Server, ArrowUpRight } from 'lucide-react'
import type { HealthResponse, HealthStatusState } from '../types/api'
import { API_BASE_URL } from '../lib/api'

interface HealthStatusCardProps {
  status: HealthStatusState
  data: HealthResponse | null
  error: string | null
  latencyMs: number | null
  isRefreshing: boolean
  onRefresh: () => void
}

export const HealthStatusCard: React.FC<HealthStatusCardProps> = ({
  status,
  data,
  error,
  latencyMs,
  isRefreshing,
  onRefresh,
}) => {
  return (
    <div className="bg-surface-card rounded-xl border border-surface-border p-6 shadow-sm">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-5 border-b border-surface-border">
        <div className="flex items-center space-x-3">
          <div
            className={`p-2.5 rounded-lg ${
              status === 'online'
                ? 'bg-brand-emerald-subtle text-brand-emerald'
                : status === 'loading' || status === 'waking'
                ? 'bg-slate-100 text-slate-500'
                : 'bg-rose-50 text-rose-600'
            }`}
          >
            <Server className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-brand-navy">
              Backend Service Integration
            </h2>
            <p className="text-xs text-slate-500 font-mono">
              Target endpoint: <span className="text-slate-700">{API_BASE_URL}/api/v1/health</span>
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={onRefresh}
          disabled={isRefreshing}
          className="inline-flex items-center justify-center px-3.5 py-2 text-xs font-medium rounded-lg text-brand-navy bg-surface-muted hover:bg-slate-200/80 active:bg-slate-300/80 border border-surface-border transition-colors disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-brand-indigo/20"
        >
          <RefreshCw
            className={`h-3.5 w-3.5 mr-2 ${
              isRefreshing ? 'animate-spin text-brand-indigo' : 'text-slate-500'
            }`}
          />
          <span>{isRefreshing ? 'Pinging Service...' : 'Check Connection'}</span>
        </button>
      </div>

      <div className="mt-5 space-y-4">
        {status === 'online' && data ? (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="p-3.5 rounded-lg bg-surface-muted border border-surface-border">
              <span className="text-xs font-medium text-slate-500 uppercase tracking-wider block">
                Health Status
              </span>
              <div className="mt-1 flex items-center space-x-1.5 text-emerald-700 font-semibold text-sm">
                <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />
                <span className="capitalize">{data.status} (HTTP 200)</span>
              </div>
            </div>

            <div className="p-3.5 rounded-lg bg-surface-muted border border-surface-border">
              <span className="text-xs font-medium text-slate-500 uppercase tracking-wider block">
                Service Identity
              </span>
              <span className="mt-1 block text-sm font-semibold text-brand-navy">
                {data.app_name} <span className="text-xs font-normal text-slate-500">v{data.version}</span>
              </span>
            </div>

            <div className="p-3.5 rounded-lg bg-surface-muted border border-surface-border">
              <span className="text-xs font-medium text-slate-500 uppercase tracking-wider block">
                Round-Trip Latency
              </span>
              <span className="mt-1 block text-sm font-semibold text-brand-navy">
                {latencyMs !== null ? `${latencyMs} ms` : '—'}
              </span>
            </div>
          </div>
        ) : status === 'loading' || status === 'waking' ? (
          <div className="p-6 rounded-lg bg-surface-muted border border-surface-border text-center">
            <div className="inline-flex items-center space-x-2 text-slate-600 text-sm">
              <RefreshCw className="h-4 w-4 animate-spin text-brand-indigo" />
              <span>
                {status === 'waking'
                  ? 'Waking up backend… Retrying automatically.'
                  : 'Querying backend health endpoint...'}
              </span>
            </div>
          </div>
        ) : (
          <div className="p-4 rounded-lg bg-rose-50 border border-rose-200">
            <div className="flex items-start space-x-3">
              <AlertTriangle className="h-5 w-5 text-rose-600 shrink-0 mt-0.5" />
              <div className="text-sm">
                <p className="font-semibold text-rose-900">
                  Backend connection failed
                </p>
                <p className="text-xs text-rose-700 mt-0.5">
                  {error || 'Unable to reach the FastAPI service.'}
                </p>
                <p className="mt-2 text-xs text-rose-700">
                  Backend taking a nap? We're on Render's free tier — billionaire server budget not included. Give it around 45 seconds to wake up.
                </p>
                <div className="mt-3 text-xs bg-white/70 p-2.5 rounded border border-rose-200 font-mono text-slate-800">
                  <p className="font-sans font-medium text-slate-600 mb-1">To start the local backend service:</p>
                  <code>cd backend && .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000</code>
                </div>
              </div>
            </div>
          </div>
        )}

        <div className="pt-2 flex flex-wrap items-center justify-between text-xs text-slate-500 border-t border-surface-border">
          <span>FastAPI + Python 3.11</span>
          <a
            href={`${API_BASE_URL}/docs`}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center text-brand-indigo hover:text-brand-indigo-hover hover:underline"
          >
            <span>Open FastAPI Interactive Swagger Docs</span>
            <ArrowUpRight className="h-3 w-3 ml-0.5" />
          </a>
        </div>
      </div>
    </div>
  )
}
