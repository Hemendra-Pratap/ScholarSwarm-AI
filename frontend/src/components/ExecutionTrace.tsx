import React from 'react'
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Clock,
  ShieldAlert,
  Activity,
  RotateCcw,
} from 'lucide-react'
import type { WorkflowEvent, WorkflowStage, WorkflowEventType } from '../types/api'

interface ExecutionTraceProps {
  events: WorkflowEvent[]
  runId?: string
  status?: string
  isPartial?: boolean
  failureSummary?: string | null
}

const STAGE_LABELS: Record<WorkflowStage, string> = {
  initialization: 'Initialization',
  validation: 'Profile & Request Validation',
  discovery: 'Scholarship Discovery',
  verification: 'Official Source Verification',
  eligibility: 'Deterministic Eligibility Audit',
  ranking: 'Ranking & Strategy Formulation',
  completed: 'Execution Finished',
  failed: 'Workflow Terminated',
}

export const ExecutionTrace: React.FC<ExecutionTraceProps> = ({
  events,
  runId,
  status,
  isPartial,
  failureSummary,
}) => {
  if (!events || events.length === 0) {
    return null
  }

  // Sort strictly by sequence number to preserve truthful order
  const sortedEvents = [...events].sort((a, b) => a.sequence_number - b.sequence_number)

  const getEventBadge = (type: WorkflowEventType) => {
    switch (type) {
      case 'stage_completed':
        return (
          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[10px] font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
            <CheckCircle2 className="h-3 w-3" />
            <span>Completed</span>
          </span>
        )
      case 'stage_started':
        return (
          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[10px] font-medium bg-blue-50 text-blue-700 border border-blue-200">
            <Activity className="h-3 w-3" />
            <span>Started</span>
          </span>
        )
      case 'stage_skipped':
        return (
          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[10px] font-medium bg-slate-50 text-slate-600 border border-slate-200">
            <span>Skipped</span>
          </span>
        )
      case 'stage_retrying':
        return (
          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[10px] font-medium bg-amber-50 text-amber-700 border border-amber-200">
            <RotateCcw className="h-3 w-3" />
            <span>Retrying</span>
          </span>
        )
      case 'stage_partial':
        return (
          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[10px] font-medium bg-amber-50 text-amber-700 border border-amber-200">
            <AlertTriangle className="h-3 w-3" />
            <span>Partial</span>
          </span>
        )
      case 'stage_failed':
      case 'workflow_terminated':
        return (
          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[10px] font-medium bg-red-50 text-red-700 border border-red-200">
            <XCircle className="h-3 w-3" />
            <span>Failed</span>
          </span>
        )
      default:
        return null
    }
  }

  return (
    <div className="bg-surface-card rounded-2xl border border-surface-border p-6 shadow-sm space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b border-surface-border pb-3">
        <div className="flex items-center space-x-2">
          <Activity className="h-4 w-4 text-brand-indigo" />
          <h3 className="text-sm font-semibold text-brand-navy">
            Swarm Execution Trace & Audit Trail
          </h3>
        </div>

        <div className="flex items-center space-x-2 text-xs">
          {runId && (
            <span className="text-slate-500 font-mono text-[11px]">
              Run: {runId.slice(0, 8)}...
            </span>
          )}
          {status && (
            <span
              className={`px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider ${
                status === 'completed' && !isPartial
                  ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                  : isPartial
                  ? 'bg-amber-50 text-amber-700 border border-amber-200'
                  : 'bg-red-50 text-red-700 border border-red-200'
              }`}
            >
              {isPartial ? 'Partial Success' : status}
            </span>
          )}
        </div>
      </div>

      {failureSummary && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-3 text-xs text-red-800 flex items-start space-x-2">
          <ShieldAlert className="h-4 w-4 text-red-600 shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold text-red-900">Failure Summary: </span>
            <span>{failureSummary}</span>
          </div>
        </div>
      )}

      {/* Sequential Event Timeline */}
      <div className="relative pl-4 border-l-2 border-slate-200 space-y-4 my-2">
        {sortedEvents.map((ev) => (
          <div key={ev.event_id || `${ev.sequence_number}-${ev.timestamp}`} className="relative group">
            {/* Dot marker */}
            <div className="absolute -left-[21px] top-1.5 w-2.5 h-2.5 rounded-full bg-slate-300 group-hover:bg-brand-indigo transition-colors" />

            <div className="bg-surface-warm/60 rounded-xl p-3 border border-surface-border/60 hover:border-surface-border transition space-y-1">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center space-x-2">
                  <span className="text-[11px] font-mono text-slate-400 font-semibold">
                    #{ev.sequence_number}
                  </span>
                  <span className="text-xs font-semibold text-brand-navy">
                    {STAGE_LABELS[ev.stage] || ev.stage}
                  </span>
                  {getEventBadge(ev.event_type)}
                </div>

                <div className="flex items-center space-x-2 text-[10px] text-slate-400 font-mono">
                  <Clock className="h-3 w-3" />
                  <span>{new Date(ev.timestamp).toLocaleTimeString()}</span>
                  {ev.retry_attempt && ev.retry_attempt > 0 && (
                    <span className="text-amber-600 font-bold">
                      (Retry {ev.retry_attempt})
                    </span>
                  )}
                  {ev.error_code && (
                    <span className="text-red-500 font-bold">
                      [{ev.error_code}]
                    </span>
                  )}
                </div>
              </div>

              <p className="text-xs text-slate-600 font-sans mt-0.5">
                {ev.message}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
