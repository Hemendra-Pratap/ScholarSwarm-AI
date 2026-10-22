import { useState, useEffect } from 'react'
import { Header } from './components/Header'
import { HeroOverview } from './components/HeroOverview'
import { HealthStatusCard } from './components/HealthStatusCard'
import { ProfileUploadReview } from './components/ProfileUploadReview'
import { ResearchWorkspace } from './components/ResearchWorkspace'
import { ExecutionTrace } from './components/ExecutionTrace'
import { ResearchResultsView } from './components/ResearchResultsView'
import { fetchBackendHealth, executeResearchRun } from './lib/api'
import type {
  HealthResponse,
  HealthStatusState,
  StudentProfileRead,
  ResearchRunExecutionRequest,
  ResearchRunExecutionResponse,
} from './types/api'
import { ShieldAlert, Cpu, Sparkles, FileText, Search, BarChart3, AlertCircle } from 'lucide-react'

export function App() {
  const [status, setStatus] = useState<HealthStatusState>('loading')
  const [data, setData] = useState<HealthResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [latencyMs, setLatencyMs] = useState<number | null>(null)
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false)

  // Navigation tab for smooth desktop/mobile workflow
  const [activeWorkflowTab, setActiveWorkflowTab] = useState<'profile' | 'research' | 'results'>('profile')

  // Confirmed Profile State
  const [confirmedProfile, setConfirmedProfile] = useState<StudentProfileRead | null>(null)

  // Research Run State
  const [isRunning, setIsRunning] = useState<boolean>(false)
  const [runError, setRunError] = useState<string | null>(null)
  const [runResults, setRunResults] = useState<ResearchRunExecutionResponse | null>(null)

  const handleManualRefresh = async () => {
    setIsRefreshing(true)
    const result = await fetchBackendHealth()
    setData(result.data)
    setError(result.error)
    setLatencyMs(result.latencyMs)
    setStatus(result.data ? 'online' : 'offline')
    setIsRefreshing(false)
  }

  useEffect(() => {
    let active = true

    fetchBackendHealth().then((result) => {
      if (active) {
        setData(result.data)
        setError(result.error)
        setLatencyMs(result.latencyMs)
        setStatus(result.data ? 'online' : 'offline')
      }
    })

    return () => {
      active = false
    }
  }, [])

  const handleProfileConfirmed = (profile: StudentProfileRead) => {
    setConfirmedProfile(profile)
    setActiveWorkflowTab('research')
  }

  const handleStartResearch = async (request: ResearchRunExecutionRequest) => {
    setIsRunning(true)
    setRunError(null)

    const result = await executeResearchRun(request)
    setIsRunning(false)

    if (result.error) {
      setRunError(result.error)
      return
    }

    if (result.data) {
      setRunResults(result.data)
      setActiveWorkflowTab('results')
    }
  }

  return (
    <div className="min-h-screen flex flex-col bg-surface-warm text-brand-navy">
      <Header status={status} latencyMs={latencyMs} />

      <main className="flex-1 max-w-6xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 sm:py-12 space-y-8">
        {/* Core Value Proposition & 4-Step Pipeline */}
        <HeroOverview />

        {/* Workflow Stage Navigation Tabs */}
        <div className="border-b border-surface-border flex items-center justify-between pb-3">
          <div className="flex space-x-2 sm:space-x-4">
            <button
              type="button"
              onClick={() => setActiveWorkflowTab('profile')}
              className={`flex items-center space-x-2 pb-2 text-xs sm:text-sm font-semibold transition border-b-2 -mb-3 px-1 ${
                activeWorkflowTab === 'profile'
                  ? 'border-brand-indigo text-brand-indigo'
                  : 'border-transparent text-slate-500 hover:text-brand-navy'
              }`}
            >
              <FileText className="h-4 w-4" />
              <span>1. Student Profile & Review</span>
              {confirmedProfile && (
                <span className="w-2 h-2 rounded-full bg-emerald-500" title="Profile Confirmed" />
              )}
            </button>

            <button
              type="button"
              onClick={() => setActiveWorkflowTab('research')}
              className={`flex items-center space-x-2 pb-2 text-xs sm:text-sm font-semibold transition border-b-2 -mb-3 px-1 ${
                activeWorkflowTab === 'research'
                  ? 'border-brand-indigo text-brand-indigo'
                  : 'border-transparent text-slate-500 hover:text-brand-navy'
              }`}
            >
              <Search className="h-4 w-4" />
              <span>2. Research Workspace</span>
              {isRunning && (
                <span className="w-2 h-2 rounded-full bg-blue-500 animate-ping" />
              )}
            </button>

            <button
              type="button"
              onClick={() => setActiveWorkflowTab('results')}
              className={`flex items-center space-x-2 pb-2 text-xs sm:text-sm font-semibold transition border-b-2 -mb-3 px-1 ${
                activeWorkflowTab === 'results'
                  ? 'border-brand-indigo text-brand-indigo'
                  : 'border-transparent text-slate-500 hover:text-brand-navy'
              }`}
            >
              <BarChart3 className="h-4 w-4" />
              <span>3. Live Trace & Results</span>
              {runResults && (
                <span className="w-2 h-2 rounded-full bg-brand-indigo" />
              )}
            </button>
          </div>

          <div className="hidden sm:flex items-center space-x-2 text-xs text-slate-400">
            <Sparkles className="h-3.5 w-3.5 text-brand-indigo" />
            <span>Verifiable Multi-Agent Swarm</span>
          </div>
        </div>

        {/* Global Run Error Banner */}
        {runError && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-xs text-red-800 flex items-start space-x-3">
            <AlertCircle className="h-5 w-5 text-red-600 shrink-0 mt-0.5" />
            <div>
              <div className="font-semibold text-red-900">Research Run Execution Error</div>
              <p className="mt-0.5 text-red-700">{runError}</p>
            </div>
          </div>
        )}

        {/* Workflow Panels */}
        {activeWorkflowTab === 'profile' && (
          <ProfileUploadReview
            confirmedProfile={confirmedProfile}
            onProfileConfirmed={handleProfileConfirmed}
          />
        )}

        {activeWorkflowTab === 'research' && (
          <ResearchWorkspace
            confirmedProfile={confirmedProfile}
            isRunning={isRunning}
            onStartRun={handleStartResearch}
            onNavigateToUpload={() => setActiveWorkflowTab('profile')}
          />
        )}

        {activeWorkflowTab === 'results' && (
          <div className="space-y-6">
            {!runResults && !isRunning ? (
              <div className="bg-surface-card rounded-2xl border border-surface-border p-12 text-center text-slate-500 space-y-3">
                <Search className="mx-auto h-10 w-10 text-slate-400" />
                <h3 className="text-sm font-semibold text-brand-navy">
                  No Active Research Results Yet
                </h3>
                <p className="text-xs text-slate-400 max-w-md mx-auto">
                  Launch a research query from the Workspace tab to trigger the multi-agent discovery, verification, and ranking swarm.
                </p>
                <button
                  type="button"
                  onClick={() => setActiveWorkflowTab('research')}
                  className="inline-flex items-center space-x-1.5 px-4 py-2 rounded-lg bg-brand-indigo text-white text-xs font-semibold hover:bg-brand-indigo/90 shadow-xs"
                >
                  Go to Research Workspace →
                </button>
              </div>
            ) : null}

            {runResults && (
              <>
                <ExecutionTrace
                  events={runResults.events}
                  runId={runResults.run_id}
                  status={runResults.status}
                  isPartial={runResults.is_partial}
                  failureSummary={runResults.failure_summary}
                />

                <ResearchResultsView results={runResults} />
              </>
            )}
          </div>
        )}

        {/* Backend Connectivity Status */}
        <div className="pt-4 border-t border-surface-border">
          <HealthStatusCard
            status={status}
            data={data}
            error={error}
            latencyMs={latencyMs}
            isRefreshing={isRefreshing}
            onRefresh={handleManualRefresh}
          />
        </div>

        {/* Architecture Guarantees */}
        <div className="bg-surface-card rounded-xl border border-surface-border p-5 text-xs text-slate-600 space-y-3">
          <div className="flex items-center space-x-2 font-semibold text-brand-navy">
            <Cpu className="h-4 w-4 text-brand-indigo" />
            <span>ScholarSwarm AI Engineering & Safety Standards</span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-slate-500">
            <div className="flex items-start space-x-2">
              <span className="text-brand-teal font-bold">✓</span>
              <span>Backend: FastAPI with strict Pydantic contract validation</span>
            </div>
            <div className="flex items-start space-x-2">
              <span className="text-brand-teal font-bold">✓</span>
              <span>Profiles: Ingestion candidate preview with explicit human confirmation</span>
            </div>
            <div className="flex items-start space-x-2">
              <span className="text-brand-teal font-bold">✓</span>
              <span>Truthful progress: Real sequential events and error codes; zero fake loaders</span>
            </div>
            <div className="flex items-start space-x-2">
              <span className="text-brand-teal font-bold">✓</span>
              <span>Deterministic Python scoring: Transparent breakdown; zero LLM hallucination</span>
            </div>
          </div>
          <div className="pt-2 border-t border-surface-border flex items-center text-slate-400 text-[11px]">
            <ShieldAlert className="h-3.5 w-3.5 mr-1.5 text-slate-400 shrink-0" />
            <span>
              All eligibility evaluations reference authentic official requirements or cite evidence limitations defensibly.
            </span>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-surface-border bg-surface-card py-6 text-center text-xs text-slate-400">
        <div className="max-w-6xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-2">
          <span>ScholarSwarm AI — TetraNoodle AI Hackathon 2026</span>
          <span>Verified Multi-Agent Autonomous Scholarship Research Swarm</span>
        </div>
      </footer>
    </div>
  )
}

export default App
