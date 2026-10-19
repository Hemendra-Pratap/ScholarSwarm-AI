from datetime import datetime
from enum import Enum
import uuid
from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from app.schemas.common import UTCDateTime


class SourceVerificationStatus(str, Enum):
    ACCESSIBLE = "accessible"
    INACCESSIBLE = "inaccessible"
    TIMEOUT = "timeout"
    VERIFIED = "verified"
    UNVERIFIED = "unverified"


class EvidenceSourceBase(BaseModel):
    """Base evidence source data contract."""
    opportunity_id: uuid.UUID = Field(..., description="Associated opportunity ID")
    source_url: HttpUrl = Field(..., description="Direct authoritative URL")
    title: str | None = Field(default=None, max_length=500, description="Source page title or publisher")
    claim_supported: str = Field(..., min_length=1, max_length=500, description="Specific claim, requirement, or criterion supported")
    excerpt: str = Field(..., min_length=1, max_length=2000, description="Concise evidence excerpt from source")
    retrieved_at: UTCDateTime = Field(..., description="Timestamp when evidence was retrieved")
    published_date: UTCDateTime | None = Field(default=None, description="Published or last updated date if available")
    verification_status: SourceVerificationStatus = Field(
        default=SourceVerificationStatus.UNVERIFIED,
        description="Source accessibility/verification status"
    )

    model_config = ConfigDict(extra="forbid")


class EvidenceSourceCreate(EvidenceSourceBase):
    id: uuid.UUID | None = Field(default=None, description="Optional client-specified UUID")


class EvidenceSourceRead(EvidenceSourceBase):
    id: uuid.UUID
    created_at: UTCDateTime

    model_config = ConfigDict(from_attributes=True, extra="forbid")
