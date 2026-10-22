from pydantic import BaseModel, ConfigDict, Field
from app.schemas.student_profile import StudentProfileBase
from app.schemas.ranking import RankedOpportunityItem


class SOPDraftRequest(BaseModel):
    """Request to draft an application statement for a selected opportunity."""
    student_profile: StudentProfileBase = Field(..., description="Confirmed student profile facts")
    opportunity: RankedOpportunityItem = Field(..., description="Selected ranked opportunity record")
    additional_notes: str | None = Field(default=None, max_length=2000, description="Optional student-provided notes or focus areas")

    model_config = ConfigDict(extra="forbid")


class FactProvenanceItem(BaseModel):
    """Provenance record tracking the origin and verification status of a datum used in drafting."""
    field_name: str = Field(..., description="Name of the attribute or section")
    value: str = Field(..., description="Confirmed value or verified text")
    source: str = Field(..., description="Origin source (e.g. 'Confirmed Student Profile', 'Verified Official URL')")
    is_verified: bool = Field(..., description="True if grounded in verified evidence, False if user claim or placeholder")

    model_config = ConfigDict(extra="forbid")


class SOPDraftResponse(BaseModel):
    """Defensible, transparent SOP/application statement draft."""
    opportunity_name: str = Field(..., description="Target opportunity name")
    institution: str = Field(..., description="Target institution name")
    draft_text: str = Field(..., description="Complete editable application statement draft with explicit placeholders")
    placeholders: list[str] = Field(default_factory=list, description="Explicit placeholders requiring student completion")
    confirmed_facts_used: list[FactProvenanceItem] = Field(default_factory=list, description="Source-backed confirmed facts used in the draft")
    unverified_claims: list[str] = Field(default_factory=list, description="Unverified claims or potential gaps flagged for student review")
    source_citations: list[str] = Field(default_factory=list, description="Official source evidence URLs cited in the draft")
    disclaimer: str = Field(..., description="Mandatory safety advisory reminding student that draft requires review and system never submits")

    model_config = ConfigDict(extra="forbid")
