export interface HealthResponse {
  status: string
  app_name: string
  version: string
}

export type HealthStatusState = 'loading' | 'waking' | 'online' | 'offline'

// --- Document Ingestion & Student Profile Types ---

export type DocumentType = 'resume' | 'transcript' | 'other'

export type IngestionStatus = 'success' | 'partial' | 'ocr_required' | 'unreadable'

export interface AcademicScore {
  score: number
  scale?: number | null
}

export interface BudgetConstraint {
  max_annual_budget?: number | null
  currency?: string | null
  requires_full_funding?: boolean | null
  notes?: string | null
}

export interface ProjectExperience {
  title: string
  role?: string | null
  summary?: string | null
  technologies?: string[]
}

export interface StudentProfileBase {
  name?: string | null
  degree_program?: string | null
  field_of_study?: string | null
  institution?: string | null
  country?: string | null
  academic_stage?: string | null
  academic_score?: AcademicScore | null
  target_destinations?: string[]
  academic_interests?: string[]
  projects_experiences?: ProjectExperience[]
  budget_constraint?: BudgetConstraint | null
  public_profile_urls?: string[]
}

export interface StudentProfileCreate extends StudentProfileBase {
  id?: string | null
}

export interface StudentProfileRead extends StudentProfileBase {
  id: string
  created_at: string
  updated_at: string
}

export interface FieldProvenance {
  field_name: string
  extracted_value: string
  source_document_type: DocumentType
  source_location?: string | null
  excerpt: string
  confidence: number
}

export interface ConflictingField {
  field_name: string
  conflicting_values: string[]
  reason: string
}

export interface IngestionResponse {
  status: IngestionStatus
  document_type: DocumentType
  candidate_profile: StudentProfileBase
  provenance: Record<string, FieldProvenance>
  missing_fields: string[]
  conflicts: ConflictingField[]
  warnings: string[]
  requires_human_review: boolean
}

// --- Research Run & Orchestration Types ---

export type ResearchRunStatus = 'queued' | 'running' | 'completed' | 'failed' | 'partial'

export type DiscoveryStatus =
  | 'success'
  | 'partial'
  | 'no_results'
  | 'provider_unavailable'
  | 'failed'

export type WorkflowStage =
  | 'initialization'
  | 'validation'
  | 'discovery'
  | 'verification'
  | 'eligibility'
  | 'ranking'
  | 'completed'
  | 'failed'

export type WorkflowEventType =
  | 'stage_started'
  | 'stage_completed'
  | 'stage_skipped'
  | 'stage_retrying'
  | 'stage_partial'
  | 'stage_failed'
  | 'workflow_terminated'

export interface WorkflowEvent {
  event_id: string
  sequence_number: number
  run_id: string
  stage: WorkflowStage
  event_type: WorkflowEventType
  timestamp: string
  message: string
  retry_attempt?: number | null
  error_code?: string | null
}

export type FundingType =
  | 'full'
  | 'partial'
  | 'tuition_only'
  | 'stipend_only'
  | 'research_assistantship'
  | 'teaching_assistantship'
  | 'loan'
  | 'unknown'

export type VerificationStatus =
  | 'unverified'
  | 'verified'
  | 'inaccessible'
  | 'contradictory'
  | 'expired'

export interface FundingDetail {
  funding_type: FundingType
  amount?: number | null
  currency?: string | null
  period?: string | null
}

export interface OpportunityBase {
  name: string
  institution: string
  destination_country: string
  official_url?: string | null
  funding?: FundingDetail | null
  deadline?: string | null
  verification_status: VerificationStatus
}

export interface DiscoveredCandidate {
  opportunity: OpportunityBase
  source_url: string
  source_title?: string | null
  snippet?: string | null
  search_query: string
  discovered_at: string
  extracted_fields: string[]
  missing_fields: string[]
  alternate_urls: string[]
  confidence_notes?: string | null
}

export type SourceClassification = 'official' | 'third_party' | 'uncertain'
export type ClaimOutcome = 'supported' | 'contradicted' | 'not_found' | 'ambiguous'
export type VerificationReportStatus =
  | 'verified'
  | 'partially_verified'
  | 'unverified'
  | 'conflicting'
  | 'source_inaccessible'

export interface SourceAssessment {
  source_url: string
  title?: string | null
  retrieval_status: string
  classification: SourceClassification
  reason: string
  retrieved_at: string
  is_discovered_official_source: boolean
  warnings: string[]
}

export interface ClaimAssessment {
  claim_type: string
  claimed_value?: string | null
  outcome: ClaimOutcome
  source_url?: string | null
  excerpt?: string | null
  explanation: string
}

export interface CandidateVerificationReport {
  candidate_name: string
  original_source_url: string
  overall_status: VerificationReportStatus
  source_assessments: SourceAssessment[]
  claim_assessments: ClaimAssessment[]
  verified_official_url?: string | null
  warnings: string[]
  verified_at: string
}

export type OverallEligibilityClassification =
  | 'eligible'
  | 'ineligible'
  | 'needs_review'
  | 'insufficient_evidence'
  | 'not_assessable'

export type CriterionScope = 'admission' | 'scholarship' | 'both'
export type EligibilityStatus = 'met' | 'not_met' | 'unknown' | 'not_applicable'

export interface EvaluatedCriterion {
  criterion_id: string
  description: string
  category: string
  scope: CriterionScope
  mandatory: boolean
  source_url?: string | null
  evidence_excerpt?: string | null
  is_official_evidence: boolean
  outcome: EligibilityStatus
  reason: string
  student_value?: unknown
}

export interface ScopeAuditResult {
  scope: CriterionScope
  overall_classification: OverallEligibilityClassification
  total_criteria: number
  met_count: number
  not_met_count: number
  unknown_count: number
  not_applicable_count: number
  disqualifying_criteria: string[]
  unknown_mandatory_criteria: string[]
  follow_up_requirements: string[]
}

export interface EligibilityAuditResponse {
  opportunity_name: string
  institution?: string | null
  admission_assessment?: ScopeAuditResult | null
  scholarship_assessment?: ScopeAuditResult | null
  overall_classification: OverallEligibilityClassification
  evaluated_criteria: EvaluatedCriterion[]
  disqualifying_criteria: string[]
  unknown_criteria: string[]
  evidence_caveats: string[]
}

export type DeadlineFeasibilityStatus =
  | 'open'
  | 'closing_soon'
  | 'closed'
  | 'unknown'
  | 'not_applicable'

export type ActionItemPriority = 'critical' | 'high' | 'medium' | 'low'
export type ActionItemStatus = 'required' | 'recommended' | 'verification_needed'

export interface ApplicationActionItem {
  title: string
  reason: string
  priority: ActionItemPriority
  status: ActionItemStatus
  opportunity_name?: string | null
  criterion_reference?: string | null
  source_url?: string | null
}

export interface ScoreComponentDetail {
  weight: number
  raw_score?: number | null
  weighted_score: number
  is_known: boolean
  explanation: string
}

export interface RankedOpportunityItem {
  opportunity: OpportunityBase
  rank: int
  fit_score: number
  max_score: number
  score_coverage_pct: number
  score_components: Record<string, ScoreComponentDetail>
  score_explanation: string
  eligibility_classification: OverallEligibilityClassification
  disqualifying_criteria: string[]
  unknown_criteria: string[]
  funding_summary: string
  deadline_summary: string
  deadline_feasibility: DeadlineFeasibilityStatus
  deadline_feasibility_reason: string
  main_strengths: string[]
  main_gaps: string[]
  recommended_actions: ApplicationActionItem[]
  evidence_references: string[]
  caveats: string[]
}

type int = number

export interface ExcludedOpportunityItem {
  opportunity_name: string
  institution: string
  exclusion_reason: string
  eligibility_classification: OverallEligibilityClassification
  deadline_feasibility: DeadlineFeasibilityStatus
  disqualifying_criteria: string[]
  fit_score?: number | null
  recommended_actions: ApplicationActionItem[]
}

export interface RankingResponse {
  recommended_shortlist: RankedOpportunityItem[]
  needs_review_shortlist: RankedOpportunityItem[]
  excluded_opportunities: ExcludedOpportunityItem[]
  prioritized_action_plan: ApplicationActionItem[]
  methodology: string
  configured_weights: Record<string, number>
  is_complete: boolean
  disclaimer: string
  warnings: string[]
  generated_at: string
}

export interface DiscoveryRequest {
  query: string
  destinations?: string[]
  study_level?: string | null
  max_candidates?: number
}

export interface ResearchRunExecutionRequest {
  student_profile?: StudentProfileBase | null
  profile_id?: string | null
  discovery: DiscoveryRequest
  max_shortlist_size?: number
  reference_date?: string | null
}

export interface ResearchRunExecutionResponse {
  run_id: string
  profile_id?: string | null
  status: ResearchRunStatus
  is_partial: boolean
  discovery_status?: DiscoveryStatus | null
  candidates: DiscoveredCandidate[]
  verification_reports: CandidateVerificationReport[]
  eligibility_assessments: EligibilityAuditResponse[]
  ranking?: RankingResponse | null
  events: WorkflowEvent[]
  warnings: string[]
  failure_summary?: string | null
  executed_at: string
}

export interface FactProvenanceItem {
  field_name: string
  value: string
  source: string
  is_verified: boolean
}

export interface SOPDraftRequest {
  student_profile: StudentProfileBase | StudentProfileRead
  opportunity: RankedOpportunityItem
  additional_notes?: string | null
}

export interface SOPDraftResponse {
  opportunity_name: string
  institution: string
  draft_text: string
  placeholders: string[]
  confirmed_facts_used: FactProvenanceItem[]
  unverified_claims: string[]
  source_citations: string[]
  disclaimer: string
}
