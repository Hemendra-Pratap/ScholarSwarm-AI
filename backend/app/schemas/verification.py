from datetime import datetime
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.common import UTCDateTime
from app.schemas.discovery import DiscoveredCandidate


class SourceClassification(str, Enum):
    """Classification of an inspected web source."""
    OFFICIAL = "official"
    THIRD_PARTY = "third_party"
    UNCERTAIN = "uncertain"


class ClaimOutcome(str, Enum):
    """Outcome of verifying an individual factual claim against fetched page text."""
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"


class VerificationReportStatus(str, Enum):
    """Overall verification status for a candidate opportunity."""
    VERIFIED = "verified"
    PARTIALLY_VERIFIED = "partially_verified"
    UNVERIFIED = "unverified"
    CONFLICTING = "conflicting"
    SOURCE_INACCESSIBLE = "source_inaccessible"


class SourceAssessment(BaseModel):
    """Assessment of an individual source page fetched or examined for verification."""
    source_url: str = Field(..., description="URL of the examined source")
    title: str | None = Field(default=None, description="Page title if retrieved")
    retrieval_status: str = Field(..., description="Page retrieval status (e.g. success, timeout, blocked_url)")
    classification: SourceClassification = Field(..., description="Official, third-party, or uncertain classification")
    reason: str = Field(..., description="Concise explanation supporting the classification")
    retrieved_at: UTCDateTime = Field(..., description="Timestamp of retrieval attempt in UTC")
    is_discovered_official_source: bool = Field(
        default=False,
        description="True if source was found via official-source search, False if candidate original URL"
    )
    warnings: list[str] = Field(default_factory=list, description="Warnings or issues encountered during assessment")

    model_config = ConfigDict(extra="forbid")


class ClaimAssessment(BaseModel):
    """Verification assessment of a specific factual claim."""
    claim_type: str = Field(
        ...,
        description="Type of claim (e.g., opportunity_name, institution, destination_country, study_level, funding, deadline)"
    )
    claimed_value: str | None = Field(default=None, description="Original claimed value from discovery candidate")
    outcome: ClaimOutcome = Field(..., description="Verification outcome for this claim")
    source_url: str | None = Field(default=None, description="Source URL where evidence was found or evaluated")
    excerpt: str | None = Field(default=None, description="Verbatim excerpt from official page supporting or contradicting claim")
    explanation: str = Field(..., description="Concise rationale explaining the outcome")

    model_config = ConfigDict(extra="forbid")


class CandidateVerificationReport(BaseModel):
    """Verification evaluation report for a single discovered candidate."""
    candidate_name: str = Field(..., description="Opportunity name of the evaluated candidate")
    original_source_url: str = Field(..., description="Original source URL from discovery")
    overall_status: VerificationReportStatus = Field(..., description="Overall verification status")
    source_assessments: list[SourceAssessment] = Field(default_factory=list, description="All sources assessed")
    claim_assessments: list[ClaimAssessment] = Field(default_factory=list, description="Claim-level verification results")
    verified_official_url: str | None = Field(
        default=None,
        description="Official institution/program URL confirmed during verification, if established"
    )
    warnings: list[str] = Field(default_factory=list, description="Notices or warnings specific to this candidate")
    verified_at: UTCDateTime = Field(..., description="Timestamp of verification in UTC")

    model_config = ConfigDict(extra="forbid")


class VerificationRequest(BaseModel):
    """Request contract for the official-source verification agent."""
    candidates: list[DiscoveredCandidate] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="Bounded list of discovered candidate opportunities to verify (1 to 10)"
    )

    model_config = ConfigDict(extra="forbid")


class VerificationResponse(BaseModel):
    """Output contract containing verification reports for all submitted candidates."""
    reports: list[CandidateVerificationReport] = Field(
        default_factory=list,
        description="Per-candidate verification reports"
    )
    total_candidates_processed: int = Field(default=0, ge=0, description="Total candidates evaluated")
    executed_at: UTCDateTime = Field(..., description="Timestamp when verification completed in UTC")
    warnings: list[str] = Field(default_factory=list, description="Overall process warnings or issues")

    model_config = ConfigDict(extra="forbid")
