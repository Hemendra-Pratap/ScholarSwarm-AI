from datetime import datetime
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.common import UTCDateTime
from app.schemas.opportunity import OpportunityBase


class DiscoveryStatus(str, Enum):
    """Execution status for the scholarship discovery process."""
    SUCCESS = "success"
    PARTIAL = "partial"
    NO_RESULTS = "no_results"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    FAILED = "failed"


class DiscoveredCandidate(BaseModel):
    """Discovered candidate scholarship or program opportunity extracted from search results."""
    # Extracted candidate facts (honestly mapped to OpportunityBase or left unknown)
    opportunity: OpportunityBase = Field(..., description="Normalized candidate opportunity fields")
    
    # Source provenance and raw snippet facts
    source_url: str = Field(..., description="Canonical source URL where opportunity was found")
    source_title: str | None = Field(default=None, description="Title of the source search result or page")
    snippet: str | None = Field(default=None, description="Raw summary snippet from search result")
    search_query: str = Field(..., description="Query that led to this candidate")
    discovered_at: UTCDateTime = Field(..., description="Timestamp of discovery in UTC")
    
    # Transparency and extraction uncertainty
    extracted_fields: list[str] = Field(default_factory=list, description="Fields explicitly extracted from source content")
    missing_fields: list[str] = Field(default_factory=list, description="Fields that could not be determined and remain unknown")
    alternate_urls: list[str] = Field(default_factory=list, description="Consolidated alternate URLs for duplicate candidates")
    confidence_notes: str | None = Field(default=None, description="Notes on extraction uncertainty or heuristics used")

    model_config = ConfigDict(extra="forbid")


class DiscoveryRequest(BaseModel):
    """Input contract for the scholarship discovery agent."""
    query: str = Field(
        ...,
        min_length=2,
        max_length=300,
        description="Natural-language research intent or scholarship query (e.g., 'DAAD computer science master scholarships')"
    )
    destinations: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="Optional list of destination countries or regions"
    )
    study_level: str | None = Field(
        default=None,
        max_length=100,
        description="Optional target degree or study level (e.g., 'master', 'postgraduate', 'phd')"
    )
    max_candidates: int = Field(
        default=10,
        ge=1,
        le=30,
        description="Maximum number of candidate opportunities to return"
    )

    model_config = ConfigDict(extra="forbid")


class DiscoveryResponse(BaseModel):
    """Output contract containing discovered candidate opportunities and execution metadata."""
    status: DiscoveryStatus = Field(..., description="Discovery outcome status")
    candidates: list[DiscoveredCandidate] = Field(default_factory=list, description="Deduplicated candidate opportunities")
    total_candidates: int = Field(default=0, ge=0, description="Total count of unique candidates returned")
    queries_executed: list[str] = Field(default_factory=list, description="List of search queries generated and executed")
    executed_at: UTCDateTime = Field(..., description="Timestamp when discovery completed in UTC")
    warnings: list[str] = Field(default_factory=list, description="Notices, warnings, or partial query failure reports")
    error_message: str | None = Field(default=None, description="Sanitized top-level error message on complete failure")

    model_config = ConfigDict(extra="forbid")
