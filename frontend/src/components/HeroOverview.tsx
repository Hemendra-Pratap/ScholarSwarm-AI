import React from 'react'
import { FileText, Search, ShieldCheck, Sparkles, CheckCircle } from 'lucide-react'

const WORKFLOW_STEPS = [
  {
    step: '01',
    title: 'Student Profile & Provenance',
    description:
      'Deterministic document parsing (PDF/DOCX) extracts academic history and skills without hallucinating missing qualifications.',
    icon: FileText,
    accent: 'border-l-indigo-500',
  },
  {
    step: '02',
    title: 'Opportunity Discovery',
    description:
      'Scouts ≥10 real master\'s programs and scholarships across target destinations using official university and provider portals.',
    icon: Search,
    accent: 'border-l-teal-500',
  },
  {
    step: '03',
    title: 'Source Verification & Audit',
    description:
      'Audits primary university pages, checks deadlines and criteria, and flags missing or conflicting evidence honestly.',
    icon: ShieldCheck,
    accent: 'border-l-emerald-500',
  },
  {
    step: '04',
    title: 'Application Studio',
    description:
      'Generates defensible fit scores and assists with tailored SOP drafts connecting verified requirements to genuine experience.',
    icon: Sparkles,
    accent: 'border-l-amber-500',
  },
]

export const HeroOverview: React.FC = () => {
  return (
    <div className="space-y-8">
      {/* Hero Header */}
      <div className="text-center max-w-3xl mx-auto space-y-3">
        <div className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-brand-teal-subtle text-teal-800 border border-teal-200">
          <CheckCircle className="h-3.5 w-3.5 mr-1.5 text-brand-teal" />
          <span>TetraNoodle AI Hackathon 2026</span>
        </div>
        <h1 className="text-3xl sm:text-4xl font-bold text-brand-navy tracking-tight">
          Research Smarter. Fund Your Future.
        </h1>
        <p className="text-sm sm:text-base text-slate-600 leading-relaxed">
          ScholarSwarm AI orchestrates six specialized AI agents to help international students
          discover authentic master's programs, verify eligibility against official university sources,
          and prepare transparent application plans.
        </p>
      </div>

      {/* 4-Step Architecture Workflow Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {WORKFLOW_STEPS.map((item) => {
          const Icon = item.icon
          return (
            <div
              key={item.step}
              className={`bg-surface-card p-5 rounded-xl border border-surface-border border-l-4 ${item.accent} shadow-sm transition-all hover:shadow-md`}
            >
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-mono font-semibold text-slate-400">
                  STEP {item.step}
                </span>
                <div className="p-2 rounded-lg bg-surface-muted text-brand-navy">
                  <Icon className="h-4 w-4" />
                </div>
              </div>
              <h2 className="text-sm font-semibold text-brand-navy mb-1.5">
                {item.title}
              </h2>
              <p className="text-xs text-slate-500 leading-relaxed">
                {item.description}
              </p>
            </div>
          )
        })}
      </div>
    </div>
  )
}
