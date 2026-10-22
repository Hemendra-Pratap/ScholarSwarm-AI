from datetime import datetime
import uuid
from pydantic import BaseModel, ConfigDict, Field
from app.graph.state import WorkflowEvent, WorkflowStage
from app.schemas.common import UTCDateTime
from app.schemas.discovery import DiscoveredCandidate, DiscoveryRequest, DiscoveryStatus
from app.schemas.eligibility import EligibilityAuditResponse
from app.schemas.ranking import RankingResponse
from app.schemas.research_run import ResearchRunStatus
from app.schemas.student_profile import StudentProfileBase
from app.schemas.verification import CandidateVerificationReport


class ResearchRunExecutionRequest(BaseModel):
    """Input contract for running multi-agent scholarship research."""
    student_profile: StudentProfileBase | None = Field(
        default=None,
        description="Direct student profile data when initiating research without pre-persisting"
    )
    profile_id: uuid.UUID | None = Field(
        default=None,
        description="Reference to an already confirmed and persisted student profile in the database"
    )
    discovery: DiscoveryRequest = Field(
        ...,
        description="Natural language research intent and bounded search options"
    )
    max_shortlist_size: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum recommended opportunities for the application strategy shortlist"
    )
    reference_date: UTCDateTime | None = Field(
        default=None,
        description="Reference date for deadline feasibility checks (defaults to current time in UTC)"
    )

    model_config = ConfigDict(extra="forbid")


class ResearchRunExecutionResponse(BaseModel):
    """Output contract returning truthful multi-agent research results and stage execution trace."""
    run_id: str = Field(..., description="Unique run identifier")
    profile_id: str | None = Field(default=None, description="Associated confirmed student profile ID if applicable")
    status: ResearchRunStatus = Field(..., description="Truthful terminal or execution status (completed, partial, failed)")
    is_partial: bool = Field(..., description="Whether the run produced partial results due to a stage error or provider limitation")
    
    # Truthful results across stages
    discovery_status: DiscoveryStatus | None = Field(default=None, description="Outcome of discovery stage")
    candidates: list[DiscoveredCandidate] = Field(default_factory=list, description="Candidate opportunities discovered")
    verification_reports: list[CandidateVerificationReport] = Field(
        default_factory=list,
        description="Official-source verification reports associated with candidates"
    )
    eligibility_assessments: list[EligibilityAuditResponse] = Field(
        default_factory=list,
        description="Deterministic eligibility audits associated with candidates"
    )
    ranking: RankingResponse | None = Field(
        default=None,
        description="Ranking and application strategy recommendations when successfully produced"
    )
    
    # Traceability and transparency
    events: list[WorkflowEvent] = Field(
        default_factory=list,
        description="Structured stage events and execution trace"
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Aggregated process warnings, caveats, and skipped stage notices"
    )
    failure_summary: str | None = Field(
        default=None,
        description="Sanitized top-level failure message if failed or partial"
    )
    executed_at: UTCDateTime = Field(..., description="Timestamp when response was assembled in UTC")

    model_config = ConfigDict(extra="forbid")
