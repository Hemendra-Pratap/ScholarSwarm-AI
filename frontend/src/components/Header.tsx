import React, { useEffect, useState } from 'react'
import { GraduationCap, ShieldCheck, Server, Sun, Moon } from 'lucide-react'
import type { HealthStatusState } from '../types/api'

interface HeaderProps {
  status: HealthStatusState
  latencyMs: number | null
  onRetry: () => void
}

export const Header: React.FC<HeaderProps> = ({ status, latencyMs, onRetry }) => {
  const [isDark, setIsDark] = useState(
    () => window.localStorage.getItem('scholarswarm-theme') === 'dark',
  )

  useEffect(() => {
    document.documentElement.classList.toggle('dark', isDark)
    window.localStorage.setItem('scholarswarm-theme', isDark ? 'dark' : 'light')
  }, [isDark])

  return (
    <header className="border-b border-surface-border bg-surface-card sticky top-0 z-10">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="h-10 w-10 rounded-lg bg-brand-navy flex items-center justify-center text-white shadow-sm">
            <GraduationCap className="h-6 w-6 text-brand-teal" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <span className="font-semibold text-lg text-brand-navy tracking-tight">
                ScholarSwarm AI
              </span>
              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-brand-indigo-subtle text-brand-indigo">
                Milestone 1
              </span>
            </div>
            <p className="text-xs text-slate-500 hidden sm:block">
              Research smarter. Fund your future.
            </p>
          </div>
        </div>

        {/* Live System Status Indicator */}
        <div className="flex items-center space-x-2">
          <div
            className={`inline-flex items-center px-3 py-1.5 rounded-full text-xs font-medium border ${
              status === 'online'
                ? 'bg-brand-emerald-subtle text-emerald-800 border-emerald-200'
                : status === 'loading' || status === 'waking'
                ? 'bg-slate-100 text-slate-700 border-slate-200'
                : 'bg-rose-50 text-rose-800 border-rose-200'
            }`}
          >
            <span
              className={`h-2 w-2 rounded-full mr-2 ${
                status === 'online'
                  ? 'bg-emerald-500'
                  : status === 'loading' || status === 'waking'
                  ? 'bg-slate-400 animate-pulse'
                  : 'bg-rose-500'
              }`}
              aria-hidden="true"
            />
            <Server className="h-3.5 w-3.5 mr-1 opacity-70" />
            <span>
              {status === 'online'
                ? `Backend Online${latencyMs !== null ? ` (${latencyMs}ms)` : ''}`
                : status === 'loading'
                ? 'Checking Backend...'
                : status === 'waking'
                ? 'Waking up backend…'
                : 'Backend Offline'}
            </span>
          </div>

          {status === 'offline' && (
            <button
              type="button"
              onClick={onRetry}
              className="text-xs font-medium text-brand-indigo hover:text-brand-indigo-hover focus:outline-none focus:ring-2 focus:ring-brand-indigo/20 rounded"
              aria-label="Retry backend health check"
            >
              Retry
            </button>
          )}

          <button
            type="button"
            onClick={() => setIsDark((dark) => !dark)}
            className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 hover:bg-surface-muted hover:text-brand-navy focus:outline-none focus:ring-2 focus:ring-brand-indigo/20"
            aria-label={`Switch to ${isDark ? 'light' : 'dark'} mode`}
            title={`Switch to ${isDark ? 'light' : 'dark'} mode`}
          >
            {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </button>

          <div className="hidden md:flex items-center text-xs text-slate-400 pl-2 border-l border-surface-border">
            <ShieldCheck className="h-3.5 w-3.5 mr-1 text-brand-teal" />
            <span>Evidence-first architecture</span>
          </div>
        </div>
      </div>
    </header>
  )
}
