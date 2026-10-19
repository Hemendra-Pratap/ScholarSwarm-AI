from datetime import datetime
from enum import Enum
import uuid
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.common import UTCDateTime


class EligibilityStatus(str, Enum):
    MET = "met"
    NOT_MET = "not_met"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class CriterionType(str, Enum):
    ADMISSION = "admission"
    SCHOLARSHIP = "scholarship"
    GENERAL = "general"


class EligibilityCriterion(BaseModel):
    """Assessment of a single eligibility criterion."""
    criterion_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Stable criterion identifier")
    criterion_type: CriterionType = Field(default=CriterionType.GENERAL, description="Distinct admission vs scholarship criterion")
    requirement: str = Field(..., min_length=1, max_length=500, description="Requirement statement")
    status: EligibilityStatus = Field(..., description="Evaluation status: met, not_met, unknown, not_applicable")
    reason: str | None = Field(default=None, max_length=2000, description="Explanatory rationale for the evaluation")
    supporting_evidence: str | None = Field(default=None, max_length=2000, description="Evidence excerpt or quote supporting status")
    evidence_source_id: uuid.UUID | None = Field(default=None, description="Optional foreign key link to EvidenceSource record")

    model_config = ConfigDict(extra="forbid")


class EligibilityAssessmentBase(BaseModel):
    """Base schema for eligibility assessment."""
    opportunity_id: uuid.UUID = Field(..., description="Evaluated opportunity ID")
    student_profile_id: uuid.UUID = Field(..., description="Student profile ID evaluated against")
    criteria: list[EligibilityCriterion] = Field(default_factory=list, description="Criterion-level assessments")
    notes: str | None = Field(default=None, max_length=2000, description="High-level assessor notes or observations")

    model_config = ConfigDict(extra="forbid")


class EligibilityAssessmentCreate(EligibilityAssessmentBase):
    id: uuid.UUID | None = Field(default=None, description="Optional client-specified UUID")


class EligibilityAssessmentRead(EligibilityAssessmentBase):
    id: uuid.UUID
    created_at: UTCDateTime
    updated_at: UTCDateTime

    model_config = ConfigDict(from_attributes=True, extra="forbid")
