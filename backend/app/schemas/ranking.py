from datetime import datetime
from enum import Enum
from typing import Any
import uuid
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.common import UTCDateTime
from app.schemas.eligibility import OverallEligibilityClassification
from app.schemas.opportunity import OpportunityBase
from app.schemas.student_profile import StudentProfileBase


class DeadlineFeasibilityStatus(str, Enum):
    """Feasibility classification of an application deadline relative to a reference date."""
    OPEN = "open"
    CLOSING_SOON = "closing_soon"
    CLOSED = "closed"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class ActionItemPriority(str, Enum):
    """Priority level for recommended application strategy actions."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ActionItemStatus(str, Enum):
    """Status classification for next action items."""
    REQUIRED = "required"
    RECOMMENDED = "recommended"
    VERIFICATION_NEEDED = "verification_needed"


class ApplicationActionItem(BaseModel):
    """Deterministic, actionable next step for a student applying to an opportunity."""
    title: str = Field(..., min_length=1, max_length=255, description="Concise action item summary")
    reason: str = Field(..., max_length=1000, description="Reason tied to known profile gap, criterion, deadline, or evidence limitation")
    priority: ActionItemPriority = Field(..., description="Priority based on deadline or eligibility impact")
    status: ActionItemStatus = Field(..., description="Action requirement status")
    opportunity_name: str | None = Field(default=None, description="Associated opportunity name if specific to an award")
    criterion_reference: str | None = Field(default=None, description="Relevant criterion description or ID if applicable")
    source_url: str | None = Field(default=None, description="Official source URL for verification if available")

    model_config = ConfigDict(extra="forbid")


class ScoreComponentDetail(BaseModel):
    """Component score breakdown with weight and coverage indicators."""
    weight: float = Field(..., ge=0.0, le=1.0, description="Configured weight for this component")
    raw_score: float | None = Field(default=None, ge=0.0, le=100.0, description="Raw component score 0-100 when assessable, None if unknown")
    weighted_score: float = Field(default=0.0, ge=0.0, le=100.0, description="Weight * raw_score (or 0.0 if unknown)")
    is_known: bool = Field(..., description="Whether sufficient trustworthy data existed to score this component")
    explanation: str = Field(..., description="Concise rationale for component scoring and data coverage")

    model_config = ConfigDict(extra="forbid")


class RankedOpportunityItem(BaseModel):
    """Detailed ranked opportunity record in the recommendation or review shortlist."""
    opportunity: OpportunityBase = Field(..., description="Opportunity data")
    rank: int = Field(..., ge=1, description="Rank position in the shortlist")
    
    # Fit score and components
    fit_score: float = Field(..., ge=0.0, le=100.0, description="Overall weighted profile-fit score (0 to 100)")
    max_score: float = Field(default=100.0, description="Maximum theoretical score")
    score_coverage_pct: float = Field(..., ge=0.0, le=100.0, description="Percentage of component weights that were known/assessable")
    
    score_components: dict[str, ScoreComponentDetail] = Field(
        ...,
        description="Detailed breakdown by component: academic_fit, experience_fit, funding_fit, deadline_fit"
    )
    score_explanation: str = Field(..., description="Evidence-grounded explanation of profile fit score")
    
    # Eligibility preservation from M7
    eligibility_classification: OverallEligibilityClassification = Field(
        ...,
        description="Preserved M7 eligibility classification (eligible, needs_review, ineligible, etc.)"
    )
    disqualifying_criteria: list[str] = Field(
        default_factory=list,
        description="Unmet mandatory criteria that disqualify or impede the candidate"
    )
    unknown_criteria: list[str] = Field(
        default_factory=list,
        description="Unresolved unknown criteria requiring follow-up"
    )
    
    # Funding & Deadline details
    funding_summary: str = Field(..., description="Summary of funding alignment and evidence status")
    deadline_summary: str = Field(..., description="Summary of application deadline and evidence status")
    deadline_feasibility: DeadlineFeasibilityStatus = Field(..., description="Deadline status relative to reference date")
    deadline_feasibility_reason: str = Field(..., description="Explanation of deadline feasibility assessment")
    
    # Strengths, Gaps, Actions
    main_strengths: list[str] = Field(default_factory=list, description="Key profile-opportunity alignment factors")
    main_gaps: list[str] = Field(default_factory=list, description="Key gaps, missing prerequisites, or evidence limitations")
    recommended_actions: list[ApplicationActionItem] = Field(default_factory=list, description="Specific next steps for this opportunity")
    
    evidence_references: list[str] = Field(default_factory=list, description="Authoritative source URLs supporting claims")
    caveats: list[str] = Field(default_factory=list, description="Explicit cautions regarding incomplete or unverified information")

    model_config = ConfigDict(extra="forbid")


class ExcludedOpportunityItem(BaseModel):
    """Record of an opportunity excluded from the recommended shortlist."""
    opportunity_name: str = Field(..., description="Name of the excluded opportunity")
    institution: str = Field(..., description="Institution name")
    exclusion_reason: str = Field(..., description="Defensible reason for exclusion (e.g. confirmed ineligible, closed deadline)")
    eligibility_classification: OverallEligibilityClassification = Field(..., description="Preserved M7 eligibility status")
    deadline_feasibility: DeadlineFeasibilityStatus = Field(..., description="Deadline feasibility status")
    disqualifying_criteria: list[str] = Field(default_factory=list, description="Specific disqualifying criteria if failed")
    fit_score: float | None = Field(default=None, description="Profile fit score if computed before exclusion")
    recommended_actions: list[ApplicationActionItem] = Field(default_factory=list, description="Actions required if reconsideration is sought")

    model_config = ConfigDict(extra="forbid")


class CandidateOpportunityInput(BaseModel):
    """A candidate opportunity paired with its M7 eligibility assessment data."""
    opportunity: OpportunityBase = Field(..., description="Opportunity details")
    eligibility_classification: OverallEligibilityClassification = Field(
        ...,
        description="M7 overall eligibility classification"
    )
    disqualifying_criteria: list[str] = Field(
        default_factory=list,
        description="List of failed mandatory criteria from M7 audit"
    )
    unknown_criteria: list[str] = Field(
        default_factory=list,
        description="List of unknown or unverified criteria from M7 audit"
    )
    evidence_caveats: list[str] = Field(
        default_factory=list,
        description="Evidence caveats from M7 audit"
    )

    model_config = ConfigDict(extra="forbid")


class RankingRequest(BaseModel):
    """Request contract for the Ranking & Application Strategy Agent."""
    student_profile: StudentProfileBase = Field(..., description="Student profile data")
    candidates: list[CandidateOpportunityInput] = Field(
        ...,
        min_length=1,
        max_length=20,
        description="Bounded list of candidate opportunities with their M7 assessments"
    )
    max_shortlist_size: int = Field(default=5, ge=1, le=10, description="Maximum number of recommended opportunities to return")
    reference_date: UTCDateTime | None = Field(
        default=None,
        description="Reference date/time in UTC for deadline feasibility checks (defaults to now in UTC if None)"
    )

    model_config = ConfigDict(extra="forbid")


class RankingResponse(BaseModel):
    """Output contract containing ranked recommendations, review candidates, exclusions, and action items."""
    recommended_shortlist: list[RankedOpportunityItem] = Field(
        default_factory=list,
        description="Top recommended eligible opportunities sorted deterministically by profile-fit"
    )
    needs_review_shortlist: list[RankedOpportunityItem] = Field(
        default_factory=list,
        description="Promising opportunities with unresolved eligibility, missing evidence, or uncertain deadlines"
    )
    excluded_opportunities: list[ExcludedOpportunityItem] = Field(
        default_factory=list,
        description="Opportunities excluded due to confirmed ineligibility, closed deadlines, or severe gaps"
    )
    prioritized_action_plan: list[ApplicationActionItem] = Field(
        default_factory=list,
        description="Consolidated, prioritized next actions across all evaluated opportunities"
    )
    methodology: str = Field(default="deterministic_weighted_fit_v1", description="Ranking methodology identifier")
    configured_weights: dict[str, float] = Field(
        ...,
        description="Component weights used (academic_fit, experience_fit, funding_fit, deadline_fit)"
    )
    is_complete: bool = Field(
        ...,
        description="Whether full data was available for all candidates and recommendations"
    )
    disclaimer: str = Field(
        default="Fit scores reflect profile alignment with explicit criteria and do not represent scholarship award probability or guarantee funding.",
        description="Mandatory advisory statement regarding score interpretation"
    )
    warnings: list[str] = Field(default_factory=list, description="Process warnings or general caveats")
    generated_at: UTCDateTime = Field(..., description="Timestamp of ranking execution in UTC")

    model_config = ConfigDict(extra="forbid")
