from datetime import datetime
from enum import Enum
import uuid
from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from app.schemas.common import UTCDateTime


class FundingType(str, Enum):
    FULL = "full"
    PARTIAL = "partial"
    TUITION_ONLY = "tuition_only"
    STIPEND_ONLY = "stipend_only"
    RESEARCH_ASSISTANTSHIP = "research_assistantship"
    TEACHING_ASSISTANTSHIP = "teaching_assistantship"
    LOAN = "loan"
    UNKNOWN = "unknown"


class VerificationStatus(str, Enum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    INACCESSIBLE = "inaccessible"
    CONTRADICTORY = "contradictory"
    EXPIRED = "expired"


class FundingDetail(BaseModel):
    """Structured funding detail when known."""
    funding_type: FundingType = Field(default=FundingType.UNKNOWN, description="Funding category/type")
    amount: float | None = Field(default=None, ge=0, description="Funding amount when known")
    currency: str | None = Field(default=None, max_length=10, description="Currency code (e.g. EUR, USD, CAD)")
    period: str | None = Field(default=None, max_length=100, description="Funding period, e.g. per_year, one_time, per_month")

    model_config = ConfigDict(extra="forbid")


class OpportunityBase(BaseModel):
    """Base opportunity contract."""
    name: str = Field(..., min_length=1, max_length=500, description="Opportunity or scholarship name")
    institution: str = Field(..., min_length=1, max_length=500, description="University or granting institution")
    destination_country: str = Field(..., min_length=1, max_length=100, description="Host/destination country")
    official_url: HttpUrl | None = Field(default=None, description="Official opportunity or admissions URL")
    funding: FundingDetail | None = Field(default=None, description="Funding information where known")
    deadline: UTCDateTime | None = Field(default=None, description="Specific deadline date/time where known")
    verification_status: VerificationStatus = Field(
        default=VerificationStatus.UNVERIFIED,
        description="Official source verification status"
    )

    model_config = ConfigDict(extra="forbid")


class OpportunityCreate(OpportunityBase):
    id: uuid.UUID | None = Field(default=None, description="Optional client-specified UUID")


class OpportunityUpdate(BaseModel):
    name: str | None = None
    institution: str | None = None
    destination_country: str | None = None
    official_url: HttpUrl | None = None
    funding: FundingDetail | None = None
    deadline: UTCDateTime | None = None
    verification_status: VerificationStatus | None = None

    model_config = ConfigDict(extra="forbid")


class OpportunityRead(OpportunityBase):
    id: uuid.UUID
    created_at: UTCDateTime
    updated_at: UTCDateTime

    model_config = ConfigDict(from_attributes=True, extra="forbid")
