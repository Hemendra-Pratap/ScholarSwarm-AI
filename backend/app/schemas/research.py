from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.common import UTCDateTime


class RetrievalStatus(str, Enum):
    """Status outcome for a web page retrieval attempt."""
    SUCCESS = "success"
    PARTIAL_CONTENT = "partial_content"
    UNSUPPORTED_CONTENT = "unsupported_content"
    TIMEOUT = "timeout"
    BLOCKED_URL = "blocked_url"
    HTTP_ERROR = "http_error"
    CONNECTION_ERROR = "connection_error"
    MALFORMED_CONTENT = "malformed_content"


class SearchStatus(str, Enum):
    """Status outcome for a search provider query."""
    SUCCESS = "success"
    PROVIDER_NOT_CONFIGURED = "provider_not_configured"
    AUTHENTICATION_ERROR = "authentication_error"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    CONNECTION_ERROR = "connection_error"
    PROVIDER_ERROR = "provider_error"
    MALFORMED_RESPONSE = "malformed_response"


class SearchResultItem(BaseModel):
    """Normalized search result item from an external search provider."""
    url: str = Field(..., description="Canonical source URL")
    title: str | None = Field(default=None, description="Page or resource title")
    snippet: str | None = Field(default=None, description="Concise search summary snippet")
    score: float | None = Field(default=None, description="Relevance score assigned by provider")
    published_date: str | None = Field(default=None, description="Published or indexed date if available")

    model_config = ConfigDict(extra="forbid")


class SearchRequest(BaseModel):
    """Request schema for querying the search provider."""
    query: str = Field(..., min_length=1, max_length=500, description="Search query string")
    max_results: int = Field(default=5, ge=1, le=20, description="Maximum number of results to return (1-20)")
    search_depth: str = Field(default="basic", pattern="^(basic|advanced)$", description="Search depth tier")
    include_domains: list[str] = Field(default_factory=list, description="Target domain constraints")
    exclude_domains: list[str] = Field(default_factory=list, description="Domains to exclude from results")

    model_config = ConfigDict(extra="forbid")


class SearchResponse(BaseModel):
    """Normalized response schema from the search provider."""
    status: SearchStatus = Field(..., description="Search execution outcome")
    query: str = Field(..., description="Original search query")
    results: list[SearchResultItem] = Field(default_factory=list, description="Normalized search results")
    total_results: int = Field(default=0, ge=0, description="Total count of results found")
    retrieved_at: UTCDateTime = Field(..., description="Timestamp of search execution in UTC")
    warnings: list[str] = Field(default_factory=list, description="Structured warnings or notices")
    error_message: str | None = Field(default=None, description="Sanitized error description on failure")

    model_config = ConfigDict(extra="forbid")


class PageFetchRequest(BaseModel):
    """Request schema for public web page retrieval."""
    url: str = Field(..., min_length=4, max_length=2083, description="Public HTTP/HTTPS URL to fetch")
    max_length: int | None = Field(default=None, ge=100, le=100000, description="Optional custom text length limit")

    model_config = ConfigDict(extra="forbid")


class PageFetchResponse(BaseModel):
    """Normalized response schema for public web page retrieval."""
    status: RetrievalStatus = Field(..., description="Page retrieval outcome")
    url: str = Field(..., description="Initial target URL requested")
    final_url: str | None = Field(default=None, description="Final canonical URL after permitted redirects")
    title: str | None = Field(default=None, description="Extracted HTML title where available")
    content_type: str | None = Field(default=None, description="HTTP Content-Type header of response")
    http_status: int | None = Field(default=None, description="HTTP response status code")
    extracted_text: str | None = Field(default=None, description="Cleaned readable text extracted from HTML")
    retrieved_at: UTCDateTime = Field(..., description="Timestamp of page retrieval in UTC")
    warnings: list[str] = Field(default_factory=list, description="Structured warnings or notices")
    error_message: str | None = Field(default=None, description="Sanitized error description on failure")

    model_config = ConfigDict(extra="forbid")
