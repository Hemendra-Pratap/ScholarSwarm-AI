from datetime import datetime, timezone
import uuid
from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from app.schemas.common import UTCDateTime


class AcademicScore(BaseModel):
    """Academic score representation with optional scale."""
    score: float = Field(..., description="Numerical score or grade point average")
    scale: float | None = Field(default=None, description="Maximum scale if known, e.g. 10.0 or 4.0")

    model_config = ConfigDict(extra="forbid")


class BudgetConstraint(BaseModel):
    """Student budget or funding constraint information when provided."""
    max_annual_budget: float | None = Field(default=None, ge=0, description="Maximum annual personal budget")
    currency: str | None = Field(default=None, max_length=10, description="Currency code (e.g., USD, EUR, CAD, INR)")
    requires_full_funding: bool | None = Field(default=None, description="Whether student requires 100% funding coverage")
    notes: str | None = Field(default=None, max_length=1000, description="Specific funding considerations or restrictions")

    model_config = ConfigDict(extra="forbid")


class ProjectExperience(BaseModel):
    """Summary of relevant student project, research, or work experience."""
    title: str = Field(..., min_length=1, max_length=255, description="Project or experience title")
    role: str | None = Field(default=None, max_length=255, description="Role in the project")
    summary: str | None = Field(default=None, max_length=2000, description="Concise description or summary of achievements")
    technologies: list[str] = Field(default_factory=list, description="Technologies or domains involved")

    model_config = ConfigDict(extra="forbid")


class StudentProfileBase(BaseModel):
    """Base schema for student profile."""
    name: str | None = Field(default=None, min_length=1, max_length=255)
    degree_program: str | None = Field(default=None, max_length=255, description="Current or completed degree/program")
    field_of_study: str | None = Field(default=None, max_length=255, description="Primary field of study")
    institution: str | None = Field(default=None, max_length=255, description="Current or graduated institution")
    country: str | None = Field(default=None, max_length=100, description="Student's country/location when provided")
    academic_stage: str | None = Field(default=None, max_length=100, description="E.g., final_year_undergraduate, graduate")
    academic_score: AcademicScore | None = Field(default=None, description="Academic score/scale if known")
    target_destinations: list[str] = Field(default_factory=list, description="Target study destination countries")
    academic_interests: list[str] = Field(default_factory=list, description="Academic and research interest areas")
    projects_experiences: list[ProjectExperience] = Field(default_factory=list, description="Relevant project and experience summaries")
    budget_constraint: BudgetConstraint | None = Field(default=None, description="Budget or funding constraints if supplied")
    public_profile_urls: list[HttpUrl] = Field(default_factory=list, description="Explicitly supplied public URLs")

    model_config = ConfigDict(extra="forbid")


class StudentProfileCreate(StudentProfileBase):
    """Schema for creating a student profile."""
    id: uuid.UUID | None = Field(default=None, description="Optional client-specified UUID")


class StudentProfileUpdate(BaseModel):
    """Schema for updating an existing student profile."""
    name: str | None = None
    degree_program: str | None = None
    field_of_study: str | None = None
    institution: str | None = None
    country: str | None = None
    academic_stage: str | None = None
    academic_score: AcademicScore | None = None
    target_destinations: list[str] | None = None
    academic_interests: list[str] | None = None
    projects_experiences: list[ProjectExperience] | None = None
    budget_constraint: BudgetConstraint | None = None
    public_profile_urls: list[HttpUrl] | None = None

    model_config = ConfigDict(extra="forbid")


class StudentProfileRead(StudentProfileBase):
    """Validated read representation of a student profile."""
    id: uuid.UUID
    created_at: UTCDateTime
    updated_at: UTCDateTime

    model_config = ConfigDict(from_attributes=True, extra="forbid")
