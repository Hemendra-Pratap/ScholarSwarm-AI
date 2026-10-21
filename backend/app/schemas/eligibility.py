from enum import Enum
from typing import Any
import uuid
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.common import UTCDateTime
from app.schemas.eligibility_assessment import EligibilityStatus
from app.schemas.student_profile import StudentProfileBase
from app.schemas.verification import CandidateVerificationReport, SourceClassification


class CriterionScope(str, Enum):
    """Explicit scope for evaluated eligibility criteria."""
    ADMISSION = "admission"
    SCHOLARSHIP = "scholarship"
    BOTH = "both"


class RuleOperator(str, Enum):
    """Supported deterministic comparison operators."""
    GREATER_THAN_OR_EQUAL = ">="
    GREATER_THAN = ">"
    LESS_THAN_OR_EQUAL = "<="
    LESS_THAN = "<"
    EQUALS = "=="
    CONTAINS = "contains"
    IN_LIST = "in"


class OverallEligibilityClassification(str, Enum):
    """Typed conservative overall classification."""
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    NEEDS_REVIEW = "needs_review"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    NOT_ASSESSABLE = "not_assessable"


class CriterionRuleDefinition(BaseModel):
    """Structured rule definition for deterministic comparison against student profile."""
    target_field: str = Field(..., description="Student profile attribute (e.g., 'academic_score', 'degree_program', 'country', 'academic_stage')")
    operator: RuleOperator = Field(..., description="Deterministic comparison operator")
    expected_value: Any = Field(..., description="Expected value or boundary threshold (e.g. 3.5, 'undergraduate', ['Germany', 'France'])")
    scale: float | None = Field(default=None, description="Explicit scale for numeric scores (e.g. 4.0 or 10.0)")

    model_config = ConfigDict(extra="forbid")


class EvaluatedCriterion(BaseModel):
    """Complete auditable evaluation of a single eligibility criterion."""
    criterion_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Stable criterion identifier")
    description: str = Field(..., min_length=1, max_length=500, description="Clear, human-readable criterion description")
    category: str = Field(default="general", description="Criterion category (e.g. 'gpa', 'study_level', 'nationality', 'field_of_study')")
    scope: CriterionScope = Field(..., description="Explicit scope: admission, scholarship, or both")
    mandatory: bool = Field(default=True, description="Whether this criterion is mandatory for eligibility")
    
    # Rule comparison (optional structured rule; if None, treated as unsupported/unstructured)
    rule: CriterionRuleDefinition | None = Field(default=None, description="Structured rule comparison definition")
    
    # Evidence provenance
    source_url: str | None = Field(default=None, description="Source URL where evidence excerpt was found")
    evidence_excerpt: str | None = Field(default=None, description="Official excerpt supporting the criterion")
    is_official_evidence: bool = Field(default=False, description="Whether the evidence comes from a verified official source")
    
    # Outcome
    outcome: EligibilityStatus = Field(..., description="Criterion outcome: met, not_met, unknown, not_applicable")
    reason: str = Field(..., description="Concise rationale explaining the comparison or determination")
    student_value: Any | None = Field(default=None, description="Student profile value extracted and compared")
    
    model_config = ConfigDict(extra="forbid")


class ScopeAuditResult(BaseModel):
    """Audit result for a specific scope (admission or scholarship)."""
    scope: CriterionScope = Field(..., description="Scope of this sub-assessment (admission or scholarship)")
    overall_classification: OverallEligibilityClassification = Field(..., description="Overall classification for this scope")
    total_criteria: int = Field(default=0, ge=0)
    met_count: int = Field(default=0, ge=0)
    not_met_count: int = Field(default=0, ge=0)
    unknown_count: int = Field(default=0, ge=0)
    not_applicable_count: int = Field(default=0, ge=0)
    disqualifying_criteria: list[str] = Field(default_factory=list, description="IDs or descriptions of failed mandatory criteria")
    unknown_mandatory_criteria: list[str] = Field(default_factory=list, description="IDs or descriptions of unverified or missing mandatory criteria")
    follow_up_requirements: list[str] = Field(default_factory=list, description="Specific student information or official evidence required")

    model_config = ConfigDict(extra="forbid")


class EligibilityAuditRequest(BaseModel):
    """Request contract for eligibility audit."""
    opportunity_name: str = Field(..., min_length=1, max_length=500, description="Opportunity name or program title")
    institution: str | None = Field(default=None, description="University or granting institution")
    student_profile: StudentProfileBase = Field(..., description="Complete or partial student profile data")
    criteria: list[EvaluatedCriterion] = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Explicit criteria list with rules, scope, and evidence to be evaluated"
    )
    verification_report: CandidateVerificationReport | None = Field(
        default=None,
        description="Optional M6 verification report for the opportunity to cross-check official sources"
    )
    conflicting_profile_fields: list[str] = Field(
        default_factory=list,
        description="Field names known to have conflicting or unresolved values in the student profile"
    )

    model_config = ConfigDict(extra="forbid")


class EligibilityAuditResponse(BaseModel):
    """Output contract for eligibility audit."""
    opportunity_name: str = Field(..., description="Opportunity name evaluated")
    institution: str | None = Field(default=None, description="Institution evaluated")
    admission_assessment: ScopeAuditResult | None = Field(
        default=None,
        description="Detailed assessment for admission criteria if any were present"
    )
    scholarship_assessment: ScopeAuditResult | None = Field(
        default=None,
        description="Detailed assessment for scholarship criteria if any were present"
    )
    overall_classification: OverallEligibilityClassification = Field(
        ...,
        description="Combined conservative classification across all applicable scopes"
    )
    evaluated_criteria: list[EvaluatedCriterion] = Field(
        default_factory=list,
        description="Full auditable criterion evaluations with outcomes, reasons, and evidence provenance"
    )
    disqualifying_criteria: list[str] = Field(
        default_factory=list,
        description="All failed mandatory criteria across scopes"
    )
    unknown_criteria: list[str] = Field(
        default_factory=list,
        description="All unknown criteria requiring follow-up"
    )
    evidence_caveats: list[str] = Field(
        default_factory=list,
        description="Caveats regarding evidence quality, unverified sources, or missing official corroboration"
    )
    is_incomplete: bool = Field(
        default=False,
        description="True if mandatory criteria remain unknown or unverified"
    )
    evaluated_at: UTCDateTime = Field(..., description="Timestamp of evaluation in UTC")

    model_config = ConfigDict(extra="forbid")
