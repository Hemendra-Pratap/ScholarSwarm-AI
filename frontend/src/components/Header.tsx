import React from 'react'
import { GraduationCap, ShieldCheck, Server } from 'lucide-react'
import type { HealthStatusState } from '../types/api'

interface HeaderProps {
  status: HealthStatusState
  latencyMs: number | null
}

export const Header: React.FC<HeaderProps> = ({ status, latencyMs }) => {
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
                : status === 'loading'
                ? 'bg-slate-100 text-slate-700 border-slate-200'
                : 'bg-rose-50 text-rose-800 border-rose-200'
            }`}
          >
            <span
              className={`h-2 w-2 rounded-full mr-2 ${
                status === 'online'
                  ? 'bg-emerald-500'
                  : status === 'loading'
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
                : 'Backend Offline'}
            </span>
          </div>

          <div className="hidden md:flex items-center text-xs text-slate-400 pl-2 border-l border-surface-border">
            <ShieldCheck className="h-3.5 w-3.5 mr-1 text-brand-teal" />
            <span>Evidence-first architecture</span>
          </div>
        </div>
      </div>
    </header>
  )
}
