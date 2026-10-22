from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.common import UTCDateTime
from app.schemas.discovery import DiscoveredCandidate, DiscoveryRequest, DiscoveryStatus
from app.schemas.eligibility import (
    EligibilityAuditResponse,
    EvaluatedCriterion,
    OverallEligibilityClassification,
)
from app.schemas.opportunity import OpportunityBase
from app.schemas.ranking import (
    ApplicationActionItem,
    CandidateOpportunityInput,
    ExcludedOpportunityItem,
    RankedOpportunityItem,
    RankingResponse,
)
from app.schemas.research_run import ResearchRunStatus
from app.schemas.student_profile import StudentProfileBase
from app.schemas.verification import (
    CandidateVerificationReport,
    VerificationReportStatus,
)


class WorkflowStage(str, Enum):
    """Named workflow stages reflecting current execution step."""
    INITIALIZATION = "initialization"
    VALIDATION = "validation"
    DISCOVERY = "discovery"
    VERIFICATION = "verification"
    ELIGIBILITY = "eligibility"
    RANKING = "ranking"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowEventType(str, Enum):
    """Event types emitted during workflow execution."""
    STAGE_STARTED = "stage_started"
    STAGE_COMPLETED = "stage_completed"
    STAGE_SKIPPED = "stage_skipped"
    STAGE_RETRYING = "stage_retrying"
    STAGE_PARTIAL = "stage_partial"
    STAGE_FAILED = "stage_failed"
    WORKFLOW_TERMINATED = "workflow_terminated"


class WorkflowEvent(BaseModel):
    """Structured, safe diagnostic event emitted on state transitions."""
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique event identifier")
    sequence_number: int = Field(..., ge=1, description="Stable monotonically increasing sequence index")
    run_id: str = Field(..., description="Run identifier")
    stage: WorkflowStage = Field(..., description="Stage where event occurred")
    event_type: WorkflowEventType = Field(..., description="Classification of event")
    timestamp: UTCDateTime = Field(default_factory=lambda: datetime.now(timezone.utc), description="UTC event timestamp")
    message: str = Field(..., max_length=500, description="Safe, concise diagnostic summary")
    retry_attempt: int | None = Field(default=None, ge=0, description="Retry attempt number if applicable")
    error_code: str | None = Field(default=None, max_length=100, description="Sanitized machine-readable error code if failed")

    model_config = ConfigDict(extra="forbid")


class MultiAgentWorkflowState(BaseModel):
    """Typed shared state container passed between LangGraph nodes."""
    run_id: str = Field(..., description="Unique run identifier")
    profile_id: str | None = Field(default=None, description="Persisted profile ID if confirmed in database")
    student_profile: StudentProfileBase = Field(..., description="Confirmed or validated input student profile")
    discovery_request: DiscoveryRequest = Field(..., description="Validated discovery intent and parameters")
    
    # Execution status and stage tracking
    current_stage: WorkflowStage = Field(default=WorkflowStage.INITIALIZATION, description="Current workflow stage")
    terminal_status: ResearchRunStatus = Field(default=ResearchRunStatus.RUNNING, description="Terminal or current lifecycle status")
    is_partial: bool = Field(default=False, description="Flag indicating partial results were produced")
    
    # Stage outputs
    discovery_status: DiscoveryStatus | None = Field(default=None, description="Outcome of scholarship discovery stage")
    discovered_candidates: list[DiscoveredCandidate] = Field(default_factory=list, description="Raw discovered candidates from M4")
    verification_reports: list[CandidateVerificationReport] = Field(default_factory=list, description="Candidate verification reports from M6")
    candidate_verification_map: dict[str, VerificationReportStatus] = Field(
        default_factory=dict,
        description="Keyed by candidate name/URL to its overall verification report status"
    )
    eligibility_assessments: list[EligibilityAuditResponse] = Field(
        default_factory=list,
        description="Deterministic eligibility audits from M7"
    )
    ranking_response: RankingResponse | None = Field(default=None, description="Ranking and application strategy output from M8")
    
    # Trace, retries, and errors
    events: list[WorkflowEvent] = Field(default_factory=list, description="Chronological, bounded execution trace events")
    warnings: list[str] = Field(default_factory=list, description="Aggregated process warnings and non-fatal caveats")
    retry_counts: dict[str, int] = Field(default_factory=dict, description="Transient retry counts tracked by stage name")
    sanitized_failure_info: str | None = Field(default=None, max_length=1000, description="Sanitized failure description if failed or partial")
    
    # Configurable runtime criteria override (used in deterministic tests or custom criterion definitions)
    custom_criteria: list[EvaluatedCriterion] | None = Field(
        default=None,
        description="Explicit criteria list to evaluate per opportunity during M7 audit, if provided"
    )
    max_shortlist_size: int = Field(default=5, ge=1, le=10, description="Max recommended shortlist size for ranking")
    reference_date: UTCDateTime | None = Field(default=None, description="Reference datetime for deadline feasibility checks")

    model_config = ConfigDict(extra="forbid")
