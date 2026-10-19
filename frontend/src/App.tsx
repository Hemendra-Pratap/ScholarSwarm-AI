import { useState, useEffect } from 'react'
import { Header } from './components/Header'
import { HeroOverview } from './components/HeroOverview'
import { HealthStatusCard } from './components/HealthStatusCard'
import { fetchBackendHealth } from './lib/api'
import type { HealthResponse, HealthStatusState } from './types/api'
import { ShieldAlert, Cpu } from 'lucide-react'

export function App() {
  const [status, setStatus] = useState<HealthStatusState>('loading')
  const [data, setData] = useState<HealthResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [latencyMs, setLatencyMs] = useState<number | null>(null)
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false)

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

  return (
    <div className="min-h-screen flex flex-col bg-surface-warm text-brand-navy">
      <Header status={status} latencyMs={latencyMs} />

      <main className="flex-1 max-w-6xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 sm:py-12 space-y-10">
        {/* Core Value Proposition & 4-Step Pipeline */}
        <HeroOverview />

        {/* Real Backend Health Status Integration */}
        <div className="max-w-3xl mx-auto w-full">
          <HealthStatusCard
            status={status}
            data={data}
            error={error}
            latencyMs={latencyMs}
            isRefreshing={isRefreshing}
            onRefresh={handleManualRefresh}
          />
        </div>

        {/* Foundation Architecture Guarantees */}
        <div className="max-w-3xl mx-auto w-full bg-surface-card rounded-xl border border-surface-border p-5 text-xs text-slate-600 space-y-3">
          <div className="flex items-center space-x-2 font-semibold text-brand-navy">
            <Cpu className="h-4 w-4 text-brand-indigo" />
            <span>Milestone 1 Architecture Baseline</span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-slate-500">
            <div className="flex items-start space-x-2">
              <span className="text-brand-teal font-bold">✓</span>
              <span>Backend: FastAPI with structured Pydantic models</span>
            </div>
            <div className="flex items-start space-x-2">
              <span className="text-brand-teal font-bold">✓</span>
              <span>Frontend: React 19 + TypeScript + Vite + Tailwind v3</span>
            </div>
            <div className="flex items-start space-x-2">
              <span className="text-brand-teal font-bold">✓</span>
              <span>Isolated Git repository with protected parent boundaries</span>
            </div>
            <div className="flex items-start space-x-2">
              <span className="text-brand-teal font-bold">✓</span>
              <span>Deterministic Python scoring; zero LLM self-validation</span>
            </div>
          </div>
          <div className="pt-2 border-t border-surface-border flex items-center text-slate-400 text-[11px]">
            <ShieldAlert className="h-3.5 w-3.5 mr-1.5 text-slate-400 shrink-0" />
            <span>
              Acceptance criteria: Never fabricate admission, funding, or deadlines.
            </span>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-surface-border bg-surface-card py-6 text-center text-xs text-slate-400">
        <div className="max-w-6xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-2">
          <span>ScholarSwarm AI — TetraNoodle AI Hackathon 2026</span>
          <span>Lightweight, verifiable multi-agent research architecture</span>
        </div>
      </footer>
    </div>
  )
}

export default App
