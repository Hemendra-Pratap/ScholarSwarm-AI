import React, { useState } from 'react'
import {
  Search,
  Sparkles,
  MapPin,
  GraduationCap,
  Sliders,
  AlertCircle,
  Loader2,
  ShieldCheck,
} from 'lucide-react'
import type { StudentProfileRead, ResearchRunExecutionRequest } from '../types/api'

interface ResearchWorkspaceProps {
  confirmedProfile: StudentProfileRead | null
  isRunning: boolean
  onStartRun: (request: ResearchRunExecutionRequest) => void
  onNavigateToUpload: () => void
}

export const ResearchWorkspace: React.FC<ResearchWorkspaceProps> = ({
  confirmedProfile,
  isRunning,
  onStartRun,
  onNavigateToUpload,
}) => {
  const [query, setQuery] = useState<string>('')
  const [destinationsInput, setDestinationsInput] = useState<string>(
    (confirmedProfile?.target_destinations || []).join(', '),
  )
  const [studyLevel, setStudyLevel] = useState<string>(
    confirmedProfile?.degree_program?.toLowerCase().includes('phd')
      ? 'phd'
      : confirmedProfile?.degree_program?.toLowerCase().includes('master')
      ? 'master'
      : 'master',
  )
  const [maxCandidates, setMaxCandidates] = useState<number>(8)
  const [maxShortlist, setMaxShortlist] = useState<number>(5)
  const [validationError, setValidationError] = useState<string | null>(null)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()

    if (!confirmedProfile) {
      setValidationError('A confirmed student profile is required before initiating research.')
      return
    }

    if (!query.trim() || query.trim().length < 2) {
      setValidationError('Please enter a research topic or scholarship search query (at least 2 characters).')
      return
    }

    setValidationError(null)

    const parsedDestinations = destinationsInput
      .split(',')
      .map((d) => d.trim())
      .filter(Boolean)

    const request: ResearchRunExecutionRequest = {
      profile_id: confirmedProfile.id,
      discovery: {
        query: query.trim(),
        destinations: parsedDestinations,
        study_level: studyLevel || null,
        max_candidates: maxCandidates,
      },
      max_shortlist_size: maxShortlist,
    }

    onStartRun(request)
  }

  return (
    <div className="bg-surface-card rounded-2xl border border-surface-border p-6 shadow-sm space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-surface-border pb-4">
        <div>
          <div className="flex items-center space-x-2">
            <span className="flex items-center justify-center w-6 h-6 rounded-full bg-brand-indigo text-white text-xs font-bold">
              3
            </span>
            <h2 className="text-base font-semibold text-brand-navy">
              Autonomous Scholarship Research Workspace
            </h2>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Formulate targeted research queries executed across multi-agent discovery, verification, eligibility auditing, and ranking.
          </p>
        </div>

        {confirmedProfile ? (
          <div className="flex items-center space-x-2 bg-slate-50 border border-slate-200 px-3 py-1.5 rounded-lg text-xs">
            <ShieldCheck className="h-4 w-4 text-emerald-600" />
            <span className="text-slate-700 font-medium">Profile: {confirmedProfile.name}</span>
          </div>
        ) : (
          <button
            type="button"
            onClick={onNavigateToUpload}
            className="text-xs text-brand-indigo hover:underline font-medium"
          >
            ← Upload & Confirm Profile First
          </button>
        )}
      </div>

      {!confirmedProfile && (
        <div className="bg-amber-50/70 border border-amber-200 rounded-xl p-4 text-xs text-amber-800 flex items-start space-x-3">
          <AlertCircle className="h-5 w-5 text-amber-600 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <div className="font-semibold text-amber-900">
              No Confirmed Student Profile Active
            </div>
            <p className="text-amber-700">
              ScholarSwarm AI evaluates deterministic eligibility criteria against authentic student qualifications. Please upload and confirm your profile in Step 1 & 2 before starting a research run.
            </p>
            <button
              type="button"
              onClick={onNavigateToUpload}
              className="mt-2 inline-flex items-center text-xs font-semibold text-brand-indigo hover:text-brand-indigo/80"
            >
              Upload Profile Now →
            </button>
          </div>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-5">
        <div>
          <label className="block text-xs font-semibold text-slate-700 mb-1.5">
            Scholarship / Fellowship Research Intent
          </label>
          <div className="relative">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g. DAAD postgraduate computer science scholarships in Germany for international students"
              disabled={isRunning || !confirmedProfile}
              className="w-full text-xs rounded-xl border border-surface-border pl-9 pr-4 py-2.5 bg-white focus:outline-none focus:ring-1 focus:ring-brand-indigo disabled:opacity-60 disabled:cursor-not-allowed shadow-xs"
            />
          </div>
          <p className="text-[11px] text-slate-400 mt-1">
            Natural language query describing program target, field of study, funding level, or region.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1 flex items-center space-x-1">
              <MapPin className="h-3.5 w-3.5 text-slate-400" />
              <span>Target Countries</span>
            </label>
            <input
              type="text"
              value={destinationsInput}
              onChange={(e) => setDestinationsInput(e.target.value)}
              placeholder="e.g. Germany, UK"
              disabled={isRunning || !confirmedProfile}
              className="w-full text-xs rounded-lg border border-surface-border px-3 py-2 bg-white focus:outline-none focus:ring-1 focus:ring-brand-indigo disabled:opacity-60"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1 flex items-center space-x-1">
              <GraduationCap className="h-3.5 w-3.5 text-slate-400" />
              <span>Degree Level</span>
            </label>
            <select
              value={studyLevel}
              onChange={(e) => setStudyLevel(e.target.value)}
              disabled={isRunning || !confirmedProfile}
              className="w-full text-xs rounded-lg border border-surface-border px-3 py-2 bg-white focus:outline-none focus:ring-1 focus:ring-brand-indigo disabled:opacity-60"
            >
              <option value="bachelor">Bachelor / Undergraduate</option>
              <option value="master">Master / Postgraduate</option>
              <option value="phd">PhD / Doctoral</option>
              <option value="postdoc">Postdoctoral / Fellow</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1 flex items-center space-x-1">
              <Sliders className="h-3.5 w-3.5 text-slate-400" />
              <span>Candidates / Shortlist</span>
            </label>
            <div className="flex space-x-2">
              <select
                value={maxCandidates}
                onChange={(e) => setMaxCandidates(Number(e.target.value))}
                disabled={isRunning || !confirmedProfile}
                className="w-1/2 text-xs rounded-lg border border-surface-border px-2 py-2 bg-white focus:outline-none focus:ring-1 focus:ring-brand-indigo disabled:opacity-60"
                title="Max Discovered Candidates"
              >
                <option value={5}>5 disc</option>
                <option value={8}>8 disc</option>
                <option value={10}>10 disc</option>
              </select>

              <select
                value={maxShortlist}
                onChange={(e) => setMaxShortlist(Number(e.target.value))}
                disabled={isRunning || !confirmedProfile}
                className="w-1/2 text-xs rounded-lg border border-surface-border px-2 py-2 bg-white focus:outline-none focus:ring-1 focus:ring-brand-indigo disabled:opacity-60"
                title="Max Shortlist Size"
              >
                <option value={3}>Top 3</option>
                <option value={5}>Top 5</option>
                <option value={10}>Top 10</option>
              </select>
            </div>
          </div>
        </div>

        {validationError && (
          <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700 flex items-start space-x-2">
            <AlertCircle className="h-4 w-4 shrink-0 mt-0.5 text-red-600" />
            <span>{validationError}</span>
          </div>
        )}

        <div className="pt-2 flex flex-col sm:flex-row items-center justify-between gap-4 border-t border-surface-border">
          <div className="text-[11px] text-slate-400">
            Stages executed: Validation → Discovery → Official Verification → Eligibility Audit → Deterministic Ranking
          </div>

          <button
            type="submit"
            disabled={isRunning || !confirmedProfile}
            className="w-full sm:w-auto inline-flex items-center justify-center space-x-2 px-6 py-2.5 rounded-xl bg-brand-indigo text-white text-xs font-semibold hover:bg-brand-indigo/90 disabled:opacity-50 disabled:cursor-not-allowed transition shadow-sm"
          >
            {isRunning ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>Executing Multi-Agent Swarm...</span>
              </>
            ) : (
              <>
                <Sparkles className="h-4 w-4" />
                <span>Launch Research Run</span>
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  )
}
