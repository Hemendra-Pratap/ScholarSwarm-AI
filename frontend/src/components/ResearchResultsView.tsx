import React, { useState } from 'react'
import {
  Award,
  Calendar,
  CheckCircle2,
  ExternalLink,
  DollarSign,
  AlertTriangle,
  HelpCircle,
  XCircle,
  ChevronDown,
  ChevronUp,
  ShieldAlert,
} from 'lucide-react'
import type {
  ResearchRunExecutionResponse,
  OverallEligibilityClassification,
  DeadlineFeasibilityStatus,
} from '../types/api'

interface ResearchResultsViewProps {
  results: ResearchRunExecutionResponse
}

export const ResearchResultsView: React.FC<ResearchResultsViewProps> = ({ results }) => {
  const [activeTab, setActiveTab] = useState<'recommended' | 'review' | 'excluded' | 'actions' | 'discovery'>(
    'recommended',
  )
  const [expandedOpportunity, setExpandedOpportunity] = useState<string | null>(null)

  const ranking = results.ranking
  const recommended = ranking?.recommended_shortlist || []
  const needsReview = ranking?.needs_review_shortlist || []
  const excluded = ranking?.excluded_opportunities || []
  const actionPlan = ranking?.prioritized_action_plan || []
  const candidates = results.candidates || []

  const toggleExpand = (name: string) => {
    setExpandedOpportunity(expandedOpportunity === name ? null : name)
  }

  const getEligibilityBadge = (classification: OverallEligibilityClassification) => {
    switch (classification) {
      case 'eligible':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            <CheckCircle2 className="h-3 w-3" />
            <span>Eligible</span>
          </span>
        )
      case 'needs_review':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
            <HelpCircle className="h-3 w-3" />
            <span>Needs Review</span>
          </span>
        )
      case 'ineligible':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-red-50 text-red-700 border border-red-200">
            <XCircle className="h-3 w-3" />
            <span>Ineligible</span>
          </span>
        )
      case 'insufficient_evidence':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-purple-50 text-purple-700 border border-purple-200">
            <AlertTriangle className="h-3 w-3" />
            <span>Insufficient Evidence</span>
          </span>
        )
      default:
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-50 text-slate-600 border border-slate-200">
            <span>{classification}</span>
          </span>
        )
    }
  }

  const getFeasibilityBadge = (status: DeadlineFeasibilityStatus) => {
    switch (status) {
      case 'open':
        return (
          <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
            Open
          </span>
        )
      case 'closing_soon':
        return (
          <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-amber-50 text-amber-700 border border-amber-200">
            Closing Soon
          </span>
        )
      case 'closed':
        return (
          <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-red-50 text-red-700 border border-red-200">
            Closed
          </span>
        )
      default:
        return (
          <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-slate-50 text-slate-600 border border-slate-200">
            Deadline Unknown
          </span>
        )
    }
  }

  return (
    <div className="bg-surface-card rounded-2xl border border-surface-border p-6 shadow-sm space-y-6">
      {/* Header & Truthful Status Summary */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-surface-border pb-4">
        <div>
          <div className="flex items-center space-x-2">
            <span className="flex items-center justify-center w-6 h-6 rounded-full bg-brand-indigo text-white text-xs font-bold">
              4
            </span>
            <h2 className="text-base font-semibold text-brand-navy">
              Research Findings & Strategic Action Plan
            </h2>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Deterministic matching results based strictly on verified official records and confirmed student profile data.
          </p>
        </div>

        {ranking && (
          <div className="flex items-center space-x-3 text-xs">
            <span className="text-slate-500">
              Methodology: <strong className="text-brand-navy">{ranking.methodology}</strong>
            </span>
            <span className="text-slate-300">|</span>
            <span className="text-slate-500 font-mono text-[11px]">
              {new Date(results.executed_at).toLocaleString()}
            </span>
          </div>
        )}
      </div>

      {/* Warnings & Exclusions Notice */}
      {results.warnings && results.warnings.length > 0 && (
        <div className="bg-amber-50/70 border border-amber-200 rounded-xl p-3 text-xs text-amber-800 space-y-1">
          <div className="flex items-center space-x-1.5 font-semibold">
            <AlertTriangle className="h-4 w-4 text-amber-600" />
            <span>Process Warnings & Advisory Notices:</span>
          </div>
          <ul className="list-disc list-inside space-y-0.5 text-amber-700 pl-1">
            {results.warnings.map((w, idx) => (
              <li key={idx}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Mandatory Disclaimer */}
      {ranking?.disclaimer && (
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 text-[11px] text-slate-500 flex items-start space-x-2">
          <ShieldAlert className="h-4 w-4 text-slate-400 shrink-0 mt-0.5" />
          <span>{ranking.disclaimer}</span>
        </div>
      )}

      {/* Navigation Tabs */}
      <div className="flex flex-wrap gap-2 border-b border-surface-border pb-3">
        <button
          type="button"
          onClick={() => setActiveTab('recommended')}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition ${
            activeTab === 'recommended'
              ? 'bg-brand-navy text-white shadow-xs'
              : 'text-slate-600 hover:text-brand-navy hover:bg-surface-warm'
          }`}
        >
          Recommended Opportunities ({recommended.length})
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('review')}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition ${
            activeTab === 'review'
              ? 'bg-brand-navy text-white shadow-xs'
              : 'text-slate-600 hover:text-brand-navy hover:bg-surface-warm'
          }`}
        >
          Needs Review ({needsReview.length})
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('excluded')}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition ${
            activeTab === 'excluded'
              ? 'bg-brand-navy text-white shadow-xs'
              : 'text-slate-600 hover:text-brand-navy hover:bg-surface-warm'
          }`}
        >
          Excluded Opportunities ({excluded.length})
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('actions')}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition ${
            activeTab === 'actions'
              ? 'bg-brand-navy text-white shadow-xs'
              : 'text-slate-600 hover:text-brand-navy hover:bg-surface-warm'
          }`}
        >
          Prioritized Action Plan ({actionPlan.length})
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('discovery')}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition ${
            activeTab === 'discovery'
              ? 'bg-brand-navy text-white shadow-xs'
              : 'text-slate-600 hover:text-brand-navy hover:bg-surface-warm'
          }`}
        >
          All Candidates Discovered ({candidates.length})
        </button>
      </div>

      {/* Tab 1: Recommended Opportunities */}
      {activeTab === 'recommended' && (
        <div className="space-y-4">
          {recommended.length === 0 ? (
            <div className="text-center py-10 bg-surface-warm/40 rounded-xl border border-dashed border-surface-border text-slate-500 space-y-1">
              <Award className="mx-auto h-8 w-8 text-slate-400 mb-2" />
              <div className="text-sm font-semibold text-brand-navy">No Recommended Matches Found</div>
              <p className="text-xs text-slate-400 max-w-md mx-auto">
                No opportunities met 100% of the verified mandatory eligibility requirements. Check the "Needs Review" tab for opportunities with unverified criteria or "Excluded" for details.
              </p>
            </div>
          ) : (
            recommended.map((item) => (
              <div
                key={item.opportunity.name}
                className="bg-white rounded-xl border border-surface-border p-5 hover:border-brand-indigo/40 transition shadow-xs space-y-3"
              >
                <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
                  <div className="space-y-1">
                    <div className="flex items-center space-x-2">
                      <span className="flex items-center justify-center w-6 h-6 rounded-md bg-brand-navy text-white text-xs font-bold">
                        #{item.rank}
                      </span>
                      <h4 className="text-sm font-bold text-brand-navy">
                        {item.opportunity.name}
                      </h4>
                      {item.opportunity.official_url && (
                        <a
                          href={item.opportunity.official_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-brand-indigo hover:text-brand-indigo/80 inline-flex items-center"
                          title="View Official Source"
                        >
                          <ExternalLink className="h-3.5 w-3.5" />
                        </a>
                      )}
                    </div>
                    <div className="text-xs text-slate-500">
                      {item.opportunity.institution} • {item.opportunity.destination_country}
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    {getEligibilityBadge(item.eligibility_classification)}
                    {getFeasibilityBadge(item.deadline_feasibility)}
                    <div className="px-3 py-1 rounded-lg bg-brand-indigo-subtle border border-brand-indigo/20 text-brand-indigo text-xs font-bold">
                      Fit: {item.fit_score.toFixed(1)} / 100
                    </div>
                  </div>
                </div>

                {/* Score Explanation & Component Weights */}
                <p className="text-xs text-slate-600 bg-surface-warm/50 p-2.5 rounded-lg border border-surface-border/50">
                  {item.score_explanation}
                </p>

                {/* Funding & Deadline Summaries */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                  <div className="bg-slate-50 p-2.5 rounded-lg border border-slate-200">
                    <div className="font-semibold text-slate-700 flex items-center space-x-1 mb-1">
                      <DollarSign className="h-3.5 w-3.5 text-emerald-600" />
                      <span>Funding Coverage</span>
                    </div>
                    <p className="text-slate-600">{item.funding_summary}</p>
                  </div>

                  <div className="bg-slate-50 p-2.5 rounded-lg border border-slate-200">
                    <div className="font-semibold text-slate-700 flex items-center space-x-1 mb-1">
                      <Calendar className="h-3.5 w-3.5 text-amber-600" />
                      <span>Deadline Status</span>
                    </div>
                    <p className="text-slate-600">{item.deadline_summary}</p>
                  </div>
                </div>

                {/* Expand / Collapse Details Button */}
                <div className="pt-2 flex justify-between items-center text-xs">
                  <button
                    type="button"
                    onClick={() => toggleExpand(item.opportunity.name)}
                    className="inline-flex items-center space-x-1 text-brand-indigo hover:underline font-medium"
                  >
                    <span>
                      {expandedOpportunity === item.opportunity.name
                        ? 'Hide Audit Breakdown'
                        : 'Show Audit Breakdown & Next Actions'}
                    </span>
                    {expandedOpportunity === item.opportunity.name ? (
                      <ChevronUp className="h-3.5 w-3.5" />
                    ) : (
                      <ChevronDown className="h-3.5 w-3.5" />
                    )}
                  </button>

                  <span className="text-[11px] text-slate-400">
                    Coverage: {Math.round(item.score_coverage_pct)}% data assessable
                  </span>
                </div>

                {/* Expanded Breakdown */}
                {expandedOpportunity === item.opportunity.name && (
                  <div className="mt-3 pt-3 border-t border-surface-border space-y-3 text-xs bg-surface-warm/30 p-3 rounded-lg">
                    {/* Strengths & Gaps */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div>
                        <div className="font-semibold text-emerald-800 mb-1">
                          Key Strengths:
                        </div>
                        <ul className="list-disc list-inside space-y-0.5 text-slate-600">
                          {item.main_strengths.map((str, idx) => (
                            <li key={idx}>{str}</li>
                          ))}
                        </ul>
                      </div>

                      <div>
                        <div className="font-semibold text-amber-800 mb-1">
                          Areas to Clarify / Gaps:
                        </div>
                        <ul className="list-disc list-inside space-y-0.5 text-slate-600">
                          {item.main_gaps.map((gap, idx) => (
                            <li key={idx}>{gap}</li>
                          ))}
                        </ul>
                      </div>
                    </div>

                    {/* Recommended Actions */}
                    {item.recommended_actions.length > 0 && (
                      <div className="mt-3">
                        <div className="font-semibold text-brand-navy mb-1.5">
                          Opportunity Action Items:
                        </div>
                        <div className="space-y-1.5">
                          {item.recommended_actions.map((act, idx) => (
                            <div
                              key={idx}
                              className="bg-white p-2.5 rounded border border-surface-border text-xs space-y-0.5"
                            >
                              <div className="flex items-center justify-between">
                                <span className="font-semibold text-brand-navy">
                                  {act.title}
                                </span>
                                <span className="text-[10px] uppercase font-bold text-slate-400">
                                  {act.priority} priority
                                </span>
                              </div>
                              <p className="text-slate-600 text-[11px]">{act.reason}</p>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      )}

      {/* Tab 2: Needs Review Shortlist */}
      {activeTab === 'review' && (
        <div className="space-y-4">
          {needsReview.length === 0 ? (
            <div className="text-center py-10 bg-surface-warm/40 rounded-xl border border-dashed border-surface-border text-slate-500">
              No opportunities currently flagged for review.
            </div>
          ) : (
            needsReview.map((item) => (
              <div
                key={item.opportunity.name}
                className="bg-white rounded-xl border border-amber-200/60 p-5 hover:border-amber-400 transition shadow-xs space-y-3"
              >
                <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
                  <div className="space-y-1">
                    <div className="flex items-center space-x-2">
                      <span className="flex items-center justify-center w-6 h-6 rounded-md bg-amber-600 text-white text-xs font-bold">
                        #{item.rank}
                      </span>
                      <h4 className="text-sm font-bold text-brand-navy">
                        {item.opportunity.name}
                      </h4>
                      {item.opportunity.official_url && (
                        <a
                          href={item.opportunity.official_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-brand-indigo hover:text-brand-indigo/80 inline-flex items-center"
                        >
                          <ExternalLink className="h-3.5 w-3.5" />
                        </a>
                      )}
                    </div>
                    <div className="text-xs text-slate-500">
                      {item.opportunity.institution} • {item.opportunity.destination_country}
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    {getEligibilityBadge(item.eligibility_classification)}
                    <div className="px-3 py-1 rounded-lg bg-amber-50 border border-amber-200 text-amber-800 text-xs font-bold">
                      Fit: {item.fit_score.toFixed(1)} / 100
                    </div>
                  </div>
                </div>

                <p className="text-xs text-slate-600 bg-amber-50/40 p-2.5 rounded-lg border border-amber-200/50">
                  {item.score_explanation}
                </p>

                {item.unknown_criteria.length > 0 && (
                  <div className="bg-amber-50 border border-amber-200 rounded-lg p-2.5 text-xs text-amber-800">
                    <span className="font-semibold">Unresolved Criteria: </span>
                    <span>{item.unknown_criteria.join(', ')}</span>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      )}

      {/* Tab 3: Excluded Opportunities */}
      {activeTab === 'excluded' && (
        <div className="space-y-4">
          {excluded.length === 0 ? (
            <div className="text-center py-10 bg-surface-warm/40 rounded-xl border border-dashed border-surface-border text-slate-500">
              No candidate opportunities were excluded during eligibility auditing.
            </div>
          ) : (
            excluded.map((item) => (
              <div
                key={item.opportunity_name}
                className="bg-white rounded-xl border border-red-200 p-4 space-y-2 opacity-90"
              >
                <div className="flex items-center justify-between">
                  <h4 className="text-sm font-bold text-brand-navy">
                    {item.opportunity_name}
                  </h4>
                  {getEligibilityBadge(item.eligibility_classification)}
                </div>
                <div className="text-xs text-slate-500">{item.institution}</div>
                <div className="p-2.5 bg-red-50/80 rounded border border-red-200 text-xs text-red-800">
                  <span className="font-semibold text-red-900">Exclusion Reason: </span>
                  <span>{item.exclusion_reason}</span>
                </div>
                {item.disqualifying_criteria.length > 0 && (
                  <div className="text-[11px] text-red-700">
                    Failed criteria: {item.disqualifying_criteria.join(', ')}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      )}

      {/* Tab 4: Prioritized Action Plan */}
      {activeTab === 'actions' && (
        <div className="space-y-3">
          {actionPlan.length === 0 ? (
            <div className="text-center py-10 bg-surface-warm/40 rounded-xl border border-dashed border-surface-border text-slate-500">
              No specific action items required.
            </div>
          ) : (
            actionPlan.map((action, idx) => (
              <div
                key={idx}
                className="bg-white rounded-xl border border-surface-border p-4 shadow-xs space-y-1"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-2">
                    <span className="flex items-center justify-center w-5 h-5 rounded-full bg-brand-indigo-subtle text-brand-indigo font-bold text-[10px]">
                      {idx + 1}
                    </span>
                    <h4 className="text-xs font-bold text-brand-navy">
                      {action.title}
                    </h4>
                  </div>
                  <span
                    className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                      action.priority === 'critical'
                        ? 'bg-red-100 text-red-800'
                        : action.priority === 'high'
                        ? 'bg-amber-100 text-amber-800'
                        : 'bg-slate-100 text-slate-700'
                    }`}
                  >
                    {action.priority} priority
                  </span>
                </div>
                <p className="text-xs text-slate-600 pl-7">{action.reason}</p>
                {action.opportunity_name && (
                  <div className="text-[11px] text-slate-400 pl-7">
                    Target Opportunity: <strong>{action.opportunity_name}</strong>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      )}

      {/* Tab 5: All Discovered Candidates */}
      {activeTab === 'discovery' && (
        <div className="space-y-3">
          {candidates.length === 0 ? (
            <div className="text-center py-10 bg-surface-warm/40 rounded-xl border border-dashed border-surface-border text-slate-500">
              No raw candidates recorded.
            </div>
          ) : (
            candidates.map((cand, idx) => (
              <div
                key={idx}
                className="bg-white rounded-xl border border-surface-border p-4 space-y-2 text-xs"
              >
                <div className="flex items-center justify-between">
                  <h4 className="font-bold text-brand-navy">
                    {cand.opportunity.name}
                  </h4>
                  <a
                    href={cand.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-brand-indigo hover:underline inline-flex items-center space-x-1"
                  >
                    <span>Source</span>
                    <ExternalLink className="h-3 w-3" />
                  </a>
                </div>
                <p className="text-slate-600 text-[11px]">{cand.snippet || 'No snippet available.'}</p>
                <div className="text-[10px] text-slate-400">
                  Extracted fields: {cand.extracted_fields.join(', ') || 'none'} • Missing: {cand.missing_fields.join(', ') || 'none'}
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}
