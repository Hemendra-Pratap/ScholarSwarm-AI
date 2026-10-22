import React, { useState, useMemo, useCallback } from 'react'
import {
  Sparkles,
  FileText,
  CheckCircle2,
  AlertTriangle,
  Copy,
  Check,
  Download,
  RotateCcw,
  ExternalLink,
  ShieldAlert,
  Search,
  Award,
  HelpCircle,
  Clock,
  Layers,
} from 'lucide-react'
import type {
  StudentProfileRead,
  ResearchRunExecutionResponse,
  RankedOpportunityItem,
  SOPDraftResponse,
} from '../types/api'
import { generateSOPDraft } from '../lib/api'
import { generateClientSOPDraft } from '../lib/sopGenerator'

interface SOPStudioProps {
  confirmedProfile: StudentProfileRead | null
  runResults: ResearchRunExecutionResponse | null
  initialOpportunityName?: string | null
  onNavigateToProfile?: () => void
  onNavigateToResearch?: () => void
}

export const SOPStudio: React.FC<SOPStudioProps> = ({
  confirmedProfile,
  runResults,
  initialOpportunityName,
  onNavigateToProfile,
  onNavigateToResearch,
}) => {
  // Flatten all available ranked opportunities
  const allOpportunities = useMemo<RankedOpportunityItem[]>(() => {
    if (!runResults?.ranking) return []
    const recommended = runResults.ranking.recommended_shortlist || []
    const review = runResults.ranking.needs_review_shortlist || []
    return [...recommended, ...review]
  }, [runResults])

  // Selected Opportunity initialization
  const initialOppName =
    initialOpportunityName && allOpportunities.some((o) => o.opportunity.name === initialOpportunityName)
      ? initialOpportunityName
      : allOpportunities.length > 0
        ? allOpportunities[0].opportunity.name
        : ''

  const [selectedOpportunityName, setSelectedOpportunityName] = useState<string>(initialOppName)
  const [prevInitialOppName, setPrevInitialOppName] = useState<string | null | undefined>(initialOpportunityName)
  const [additionalNotes, setAdditionalNotes] = useState<string>('')

  const selectedItem = useMemo(() => {
    return allOpportunities.find((o) => o.opportunity.name === selectedOpportunityName) || allOpportunities[0] || null
  }, [allOpportunities, selectedOpportunityName])

  // Initial draft generated synchronously to avoid cascading renders
  const initialDraft = useMemo(() => {
    if (confirmedProfile && selectedItem) {
      return generateClientSOPDraft(confirmedProfile, selectedItem, '')
    }
    return null
  }, [confirmedProfile, selectedItem])

  const [draftResponse, setDraftResponse] = useState<SOPDraftResponse | null>(initialDraft)
  const [draftText, setDraftText] = useState<string>(initialDraft?.draft_text || '')
  const [isGenerating, setIsGenerating] = useState<boolean>(false)
  const [isCopied, setIsCopied] = useState<boolean>(false)
  const [hasUserEdited, setHasUserEdited] = useState<boolean>(false)
  const [activeSideTab, setActiveSideTab] = useState<'facts' | 'placeholders' | 'audit'>('facts')

  // Synchronize when initialOpportunityName prop changes externally (e.g. user clicked "Draft SOP in Studio" on results card)
  if (initialOpportunityName !== prevInitialOppName) {
    setPrevInitialOppName(initialOpportunityName)
    if (initialOpportunityName && allOpportunities.some((o) => o.opportunity.name === initialOpportunityName)) {
      setSelectedOpportunityName(initialOpportunityName)
      const target = allOpportunities.find((o) => o.opportunity.name === initialOpportunityName)
      if (target && confirmedProfile) {
        const fresh = generateClientSOPDraft(confirmedProfile, target, additionalNotes)
        setDraftResponse(fresh)
        setDraftText(fresh.draft_text)
        setHasUserEdited(false)
      }
    }
  }

  // Draft generation handler (invoked on user action or opportunity change)
  const handleGenerateDraft = useCallback(
    async (targetItem: RankedOpportunityItem, notes?: string) => {
      if (!confirmedProfile) return

      setIsGenerating(true)
      setHasUserEdited(false)

      try {
        const result = await generateSOPDraft({
          student_profile: confirmedProfile,
          opportunity: targetItem,
          additional_notes: notes || undefined,
        })

        if (result.data) {
          setDraftResponse(result.data)
          setDraftText(result.data.draft_text)
        } else {
          const fallback = generateClientSOPDraft(confirmedProfile, targetItem, notes)
          setDraftResponse(fallback)
          setDraftText(fallback.draft_text)
        }
      } catch {
        const fallback = generateClientSOPDraft(confirmedProfile, targetItem, notes)
        setDraftResponse(fallback)
        setDraftText(fallback.draft_text)
      } finally {
        setIsGenerating(false)
      }
    },
    [confirmedProfile]
  )

  // Handle changing opportunity selection
  const handleSelectOpportunity = (name: string) => {
    setSelectedOpportunityName(name)
    const item = allOpportunities.find((o) => o.opportunity.name === name)
    if (item && confirmedProfile) {
      handleGenerateDraft(item, additionalNotes)
    }
  }

  // Handle copy to clipboard
  const handleCopy = async () => {
    if (!draftText) return
    try {
      await navigator.clipboard.writeText(draftText)
      setIsCopied(true)
      setTimeout(() => setIsCopied(false), 2000)
    } catch {
      // Fallback
      const ta = document.createElement('textarea')
      ta.value = draftText
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
      setIsCopied(true)
      setTimeout(() => setIsCopied(false), 2000)
    }
  }

  // Handle export as .txt
  const handleExportTxt = () => {
    if (!draftText || !selectedItem) return
    const sanitizedName = selectedItem.opportunity.name.replace(/[^a-zA-Z0-9_-]/g, '_').slice(0, 40)
    const filename = `SOP_Draft_${sanitizedName}.txt`
    const blob = new Blob([draftText], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  }

  // Handle reset to template
  const handleReset = () => {
    if (!selectedItem || !confirmedProfile) return
    handleGenerateDraft(selectedItem, additionalNotes)
  }

  // Metrics
  const wordCount = useMemo(() => {
    if (!draftText.trim()) return 0
    return draftText.trim().split(/\s+/).length
  }, [draftText])

  const characterCount = draftText.length

  // Count remaining placeholders in current text
  const remainingPlaceholdersCount = useMemo(() => {
    const matches = draftText.match(/\[(?:STUDENT_INPUT|MISSING|VERIFY):[^\]]+\]/g)
    return matches ? matches.length : 0
  }, [draftText])

  // 1. Missing Confirmed Profile Empty State
  if (!confirmedProfile) {
    return (
      <div className="bg-white rounded-2xl border border-surface-border p-8 sm:p-12 text-center space-y-4 shadow-xs">
        <div className="mx-auto flex items-center justify-center w-12 h-12 rounded-full bg-amber-50 text-amber-600 border border-amber-200">
          <FileText className="h-6 w-6" />
        </div>
        <div className="space-y-1 max-w-md mx-auto">
          <h3 className="text-base font-bold text-brand-navy">Confirmed Student Profile Required</h3>
          <p className="text-xs text-slate-500">
            Statement of Purpose drafting relies strictly on confirmed qualifications to prevent hallucinations.
            Please review and confirm your student profile in Step 1 first.
          </p>
        </div>
        {onNavigateToProfile && (
          <button
            type="button"
            onClick={onNavigateToProfile}
            className="inline-flex items-center space-x-1.5 px-4 py-2 rounded-lg bg-brand-indigo text-white text-xs font-semibold hover:bg-brand-indigo/90 shadow-xs transition"
          >
            <span>Go to Step 1: Student Profile</span>
            <span>→</span>
          </button>
        )}
      </div>
    )
  }

  // 2. Missing Research Results Empty State
  if (!runResults || allOpportunities.length === 0) {
    return (
      <div className="bg-white rounded-2xl border border-surface-border p-8 sm:p-12 text-center space-y-4 shadow-xs">
        <div className="mx-auto flex items-center justify-center w-12 h-12 rounded-full bg-blue-50 text-brand-indigo border border-blue-200">
          <Search className="h-6 w-6" />
        </div>
        <div className="space-y-1 max-w-md mx-auto">
          <h3 className="text-base font-bold text-brand-navy">Research Swarm Results Required</h3>
          <p className="text-xs text-slate-500">
            SOP Studio drafts statements tailored to specific, verified opportunities. Launch a research query in
            Step 2 to discover and audit opportunities for your profile.
          </p>
        </div>
        {onNavigateToResearch && (
          <button
            type="button"
            onClick={onNavigateToResearch}
            className="inline-flex items-center space-x-1.5 px-4 py-2 rounded-lg bg-brand-indigo text-white text-xs font-semibold hover:bg-brand-indigo/90 shadow-xs transition"
          >
            <span>Go to Step 2: Research Workspace</span>
            <span>→</span>
          </button>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Component Header Card */}
      <div className="bg-white rounded-2xl border border-surface-border p-5 sm:p-6 shadow-xs space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="flex items-center space-x-3">
            <span className="flex items-center justify-center w-7 h-7 rounded-full bg-brand-navy text-white text-xs font-bold">
              4
            </span>
            <div>
              <h2 className="text-base font-bold text-brand-navy flex items-center space-x-2">
                <span>Application Studio & SOP Drafting</span>
                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-brand-teal/10 text-brand-teal border border-brand-teal/20">
                  Zero Hallucination
                </span>
              </h2>
              <p className="text-xs text-slate-500">
                Draft an academic statement grounded exclusively in your confirmed facts and verified opportunity criteria.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={handleCopy}
              disabled={!draftText}
              className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg border border-surface-border bg-surface-warm text-slate-700 hover:text-brand-navy hover:bg-slate-100 text-xs font-semibold transition disabled:opacity-50"
            >
              {isCopied ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
              <span>{isCopied ? 'Copied!' : 'Copy Statement'}</span>
            </button>

            <button
              type="button"
              onClick={handleExportTxt}
              disabled={!draftText}
              className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg border border-surface-border bg-surface-warm text-slate-700 hover:text-brand-navy hover:bg-slate-100 text-xs font-semibold transition disabled:opacity-50"
            >
              <Download className="h-3.5 w-3.5 text-brand-indigo" />
              <span>Export .txt</span>
            </button>

            <button
              type="button"
              onClick={handleReset}
              disabled={isGenerating || !selectedItem}
              className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg border border-surface-border bg-surface-warm text-slate-700 hover:text-brand-navy hover:bg-slate-100 text-xs font-semibold transition disabled:opacity-50"
              title="Regenerate template from confirmed facts"
            >
              <RotateCcw className={`h-3.5 w-3.5 ${isGenerating ? 'animate-spin' : ''}`} />
              <span>Reset to Template</span>
            </button>
          </div>
        </div>

        {/* Opportunity Selector Ribbon */}
        <div className="pt-3 border-t border-surface-border/70 space-y-3">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <label htmlFor="sop-opportunity-select" className="text-xs font-semibold text-slate-700 flex items-center space-x-1.5">
              <Award className="h-4 w-4 text-brand-indigo" />
              <span>Select Researched Opportunity:</span>
            </label>
            <div className="text-[11px] text-slate-400">
              {allOpportunities.length} opportunities available from swarm discovery
            </div>
          </div>

          <div className="flex flex-col sm:flex-row gap-2">
            <select
              id="sop-opportunity-select"
              value={selectedOpportunityName}
              onChange={(e) => handleSelectOpportunity(e.target.value)}
              className="flex-1 px-3 py-2 text-xs rounded-xl border border-surface-border bg-white text-brand-navy font-medium focus:ring-2 focus:ring-brand-indigo/20 focus:border-brand-indigo transition outline-none"
            >
              {allOpportunities.map((item) => (
                <option key={item.opportunity.name} value={item.opportunity.name}>
                  #{item.rank} — {item.opportunity.name} ({item.opportunity.institution}, {item.opportunity.destination_country}) — Fit: {item.fit_score.toFixed(1)}/100
                </option>
              ))}
            </select>
          </div>

          {/* Selected Opportunity Overview Badge */}
          {selectedItem && (
            <div className="bg-surface-warm/60 rounded-xl p-3 border border-surface-border/70 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs">
              <div className="space-y-0.5">
                <div className="font-bold text-brand-navy flex items-center space-x-2">
                  <span>{selectedItem.opportunity.name}</span>
                  {selectedItem.opportunity.official_url && (
                    <a
                      href={selectedItem.opportunity.official_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-brand-indigo hover:text-brand-indigo/80 inline-flex items-center"
                      title="Visit official portal"
                    >
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  )}
                </div>
                <div className="text-slate-500 text-[11px]">
                  {selectedItem.opportunity.institution} • {selectedItem.opportunity.destination_country} • Funding: {selectedItem.funding_summary}
                </div>
              </div>

              <div className="flex items-center space-x-2">
                <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-brand-indigo-subtle text-brand-indigo border border-brand-indigo/20">
                  Fit: {selectedItem.fit_score.toFixed(1)}/100
                </span>
                <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                  {selectedItem.eligibility_classification}
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Optional Custom Notes Input */}
        <div className="pt-2">
          <details className="group text-xs">
            <summary className="cursor-pointer text-slate-500 hover:text-brand-navy font-medium flex items-center space-x-1.5 select-none">
              <span className="text-brand-indigo font-bold">＋</span>
              <span>Add custom student focus notes or specific areas to highlight (optional)</span>
            </summary>
            <div className="mt-2 space-y-2 pt-2 border-t border-surface-border/50">
              <textarea
                value={additionalNotes}
                onChange={(e) => setAdditionalNotes(e.target.value)}
                placeholder="E.g., Emphasize my interest in machine learning architectures and distributed consensus systems..."
                rows={2}
                maxLength={2000}
                className="w-full p-2.5 rounded-lg border border-surface-border text-xs text-brand-navy placeholder-slate-400 focus:ring-2 focus:ring-brand-indigo/20 focus:border-brand-indigo outline-none"
              />
              <div className="flex justify-end">
                <button
                  type="button"
                  onClick={() => selectedItem && handleGenerateDraft(selectedItem, additionalNotes)}
                  disabled={isGenerating || !selectedItem}
                  className="px-3 py-1 rounded-md bg-brand-navy text-white text-[11px] font-semibold hover:bg-brand-navy/90 transition disabled:opacity-50"
                >
                  Apply Notes to Draft
                </button>
              </div>
            </div>
          </details>
        </div>
      </div>

      {/* Main Studio Workspace: Editor + Evidence Provenance Panel */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Area: Editable Statement Editor (7 cols on lg) */}
        <div className="lg:col-span-7 bg-white rounded-2xl border border-surface-border p-5 sm:p-6 shadow-xs space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <Sparkles className="h-4 w-4 text-brand-indigo" />
              <h3 className="text-xs font-bold text-brand-navy uppercase tracking-wider">
                Application Statement Editor
              </h3>
            </div>

            <div className="flex items-center space-x-2 text-[11px]">
              <span className="text-slate-400 font-mono">
                {wordCount} words • {characterCount} chars
              </span>
              {remainingPlaceholdersCount > 0 ? (
                <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full font-semibold bg-amber-50 text-amber-700 border border-amber-200">
                  <AlertTriangle className="h-3 w-3" />
                  <span>{remainingPlaceholdersCount} placeholders remaining</span>
                </span>
              ) : (
                <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                  <CheckCircle2 className="h-3 w-3" />
                  <span>All placeholders complete</span>
                </span>
              )}
            </div>
          </div>

          {/* Statement Editor Textarea */}
          <div className="relative">
            <textarea
              value={draftText}
              onChange={(e) => {
                setDraftText(e.target.value)
                setHasUserEdited(true)
              }}
              rows={22}
              className="w-full p-4 rounded-xl border border-surface-border font-mono text-xs text-brand-navy leading-relaxed bg-surface-warm/30 focus:bg-white focus:ring-2 focus:ring-brand-indigo/20 focus:border-brand-indigo outline-none transition resize-y shadow-inner"
              placeholder="Your statement draft will appear here..."
              spellCheck={true}
            />
          </div>

          <div className="flex flex-col sm:flex-row sm:items-center justify-between text-[11px] text-slate-400 gap-2 pt-1">
            <div className="flex items-center space-x-1.5">
              <Search className="h-3.5 w-3.5 text-slate-400" />
              <span>
                Look for <code className="bg-amber-50 text-amber-800 px-1 py-0.2 rounded border border-amber-200">[STUDENT_INPUT: ...]</code> or <code className="bg-red-50 text-red-800 px-1 py-0.2 rounded border border-red-200">[MISSING: ...]</code>
              </span>
            </div>
            {hasUserEdited && (
              <span className="text-brand-indigo font-medium">✓ Unsaved manual edits in editor</span>
            )}
          </div>
        </div>

        {/* Right Area: Evidence & Fact Provenance Panel (5 cols on lg) */}
        <div className="lg:col-span-5 bg-white rounded-2xl border border-surface-border p-5 sm:p-6 shadow-xs space-y-4">
          <div className="flex items-center justify-between border-b border-surface-border pb-3">
            <div className="flex items-center space-x-2">
              <Layers className="h-4 w-4 text-brand-teal" />
              <h3 className="text-xs font-bold text-brand-navy uppercase tracking-wider">
                Provenance & Evidence Audit
              </h3>
            </div>
          </div>

          {/* Navigation Sub-Tabs */}
          <div className="flex space-x-1 bg-surface-warm p-1 rounded-xl border border-surface-border text-xs">
            <button
              type="button"
              onClick={() => setActiveSideTab('facts')}
              className={`flex-1 py-1.5 rounded-lg font-semibold transition text-center ${
                activeSideTab === 'facts'
                  ? 'bg-white text-brand-navy shadow-xs'
                  : 'text-slate-500 hover:text-brand-navy'
              }`}
            >
              Confirmed Facts ({draftResponse?.confirmed_facts_used.length || 0})
            </button>

            <button
              type="button"
              onClick={() => setActiveSideTab('placeholders')}
              className={`flex-1 py-1.5 rounded-lg font-semibold transition text-center ${
                activeSideTab === 'placeholders'
                  ? 'bg-white text-brand-navy shadow-xs'
                  : 'text-slate-500 hover:text-brand-navy'
              }`}
            >
              Action Items ({draftResponse?.placeholders.length || 0})
            </button>

            <button
              type="button"
              onClick={() => setActiveSideTab('audit')}
              className={`flex-1 py-1.5 rounded-lg font-semibold transition text-center ${
                activeSideTab === 'audit'
                  ? 'bg-white text-brand-navy shadow-xs'
                  : 'text-slate-500 hover:text-brand-navy'
              }`}
            >
              Swarm Audit ({draftResponse?.source_citations.length || 0})
            </button>
          </div>

          {/* Tab 1: Confirmed Facts */}
          {activeSideTab === 'facts' && (
            <div className="space-y-2.5 max-h-[500px] overflow-y-auto pr-1">
              <p className="text-[11px] text-slate-500">
                These facts are extracted directly from your verified student profile and official opportunity records.
              </p>
              {draftResponse?.confirmed_facts_used && draftResponse.confirmed_facts_used.length > 0 ? (
                draftResponse.confirmed_facts_used.map((item, idx) => (
                  <div
                    key={idx}
                    className="p-2.5 rounded-xl border border-surface-border bg-surface-warm/40 space-y-1 text-xs"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-brand-navy flex items-center space-x-1.5">
                        <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 shrink-0" />
                        <span>{item.field_name}</span>
                      </span>
                      <span className="text-[10px] text-slate-400">{item.source}</span>
                    </div>
                    <div className="text-slate-600 pl-5 text-[11px] font-mono break-words">
                      {item.value}
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-center py-6 text-slate-400 text-xs">
                  No confirmed facts loaded.
                </div>
              )}
            </div>
          )}

          {/* Tab 2: Action Items & Placeholders */}
          {activeSideTab === 'placeholders' && (
            <div className="space-y-2.5 max-h-[500px] overflow-y-auto pr-1">
              <p className="text-[11px] text-slate-500">
                To guarantee zero hallucination, the draft contains placeholders where personal narrative or prerequisite verification is required from you.
              </p>
              {draftResponse?.placeholders && draftResponse.placeholders.length > 0 ? (
                draftResponse.placeholders.map((ph, idx) => (
                  <div
                    key={idx}
                    className="p-2.5 rounded-xl border border-amber-200 bg-amber-50/50 space-y-1 text-xs"
                  >
                    <div className="font-semibold text-amber-900 flex items-start space-x-1.5">
                      <AlertTriangle className="h-3.5 w-3.5 text-amber-600 shrink-0 mt-0.5" />
                      <span className="break-words font-mono text-[11px]">{ph}</span>
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-center py-6 text-slate-400 text-xs">
                  No placeholders remaining!
                </div>
              )}
            </div>
          )}

          {/* Tab 3: Swarm Audit & Citations */}
          {activeSideTab === 'audit' && (
            <div className="space-y-3 max-h-[500px] overflow-y-auto pr-1 text-xs">
              <div>
                <h4 className="font-semibold text-brand-navy mb-1.5 flex items-center space-x-1">
                  <ExternalLink className="h-3.5 w-3.5 text-brand-indigo" />
                  <span>Official Evidence URLs Cited</span>
                </h4>
                {draftResponse?.source_citations && draftResponse.source_citations.length > 0 ? (
                  <ul className="space-y-1">
                    {draftResponse.source_citations.map((cite, idx) => (
                      <li key={idx}>
                        <a
                          href={cite}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-brand-indigo hover:underline break-all text-[11px] inline-flex items-center space-x-1"
                        >
                          <span>{cite}</span>
                          <ExternalLink className="h-3 w-3 shrink-0" />
                        </a>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-slate-400 text-[11px]">No external URLs cited.</p>
                )}
              </div>

              {selectedItem?.main_strengths && selectedItem.main_strengths.length > 0 && (
                <div className="pt-2 border-t border-surface-border">
                  <h4 className="font-semibold text-brand-navy mb-1 flex items-center space-x-1">
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                    <span>Audited Profile Strengths</span>
                  </h4>
                  <ul className="list-disc pl-4 space-y-0.5 text-slate-600 text-[11px]">
                    {selectedItem.main_strengths.map((s, idx) => (
                      <li key={idx}>{s}</li>
                    ))}
                  </ul>
                </div>
              )}

              {selectedItem?.main_gaps && selectedItem.main_gaps.length > 0 && (
                <div className="pt-2 border-t border-surface-border">
                  <h4 className="font-semibold text-amber-900 mb-1 flex items-center space-x-1">
                    <HelpCircle className="h-3.5 w-3.5 text-amber-600" />
                    <span>Identified Gaps & Follow-ups</span>
                  </h4>
                  <ul className="list-disc pl-4 space-y-0.5 text-amber-800 text-[11px]">
                    {selectedItem.main_gaps.map((g, idx) => (
                      <li key={idx}>{g}</li>
                    ))}
                  </ul>
                </div>
              )}

              {selectedItem?.caveats && selectedItem.caveats.length > 0 && (
                <div className="pt-2 border-t border-surface-border">
                  <h4 className="font-semibold text-slate-700 mb-1 flex items-center space-x-1">
                    <Clock className="h-3.5 w-3.5 text-slate-500" />
                    <span>Audit Caveats</span>
                  </h4>
                  <ul className="list-disc pl-4 space-y-0.5 text-slate-500 text-[11px]">
                    {selectedItem.caveats.map((c, idx) => (
                      <li key={idx}>{c}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Mandatory Safety & Student Control Notice */}
      <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 text-xs text-slate-600 space-y-2">
        <div className="flex items-center space-x-2 font-bold text-slate-800">
          <ShieldAlert className="h-4 w-4 text-amber-600" />
          <span>Mandatory Student Review & Safety Policy</span>
        </div>
        <p className="text-[11px] leading-relaxed text-slate-500">
          This application statement was assembled using strictly verified data and explicit placeholders.
          <strong> ScholarSwarm AI never submits applications, contacts university admissions, or transmits your personal profile to third parties. </strong>
          You maintain full ownership and control over your narrative. Always review, personalize, and verify your materials prior to official submission.
        </p>
      </div>
    </div>
  )
}
export default SOPStudio
