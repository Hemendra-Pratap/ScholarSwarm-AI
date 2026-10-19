from enum import Enum
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.student_profile import StudentProfileBase


class DocumentType(str, Enum):
    RESUME = "resume"
    TRANSCRIPT = "transcript"
    OTHER = "other"


class IngestionStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    OCR_REQUIRED = "ocr_required"
    UNREADABLE = "unreadable"


class FieldProvenance(BaseModel):
    """Provenance tracking for an individual extracted profile field."""
    field_name: str = Field(..., description="Target profile field name")
    extracted_value: str = Field(..., description="String representation of the extracted value")
    source_document_type: DocumentType = Field(..., description="Source document type: resume or transcript")
    source_location: str | None = Field(default=None, description="Location in document (e.g. 'Page 1' or 'Paragraph 3')")
    excerpt: str = Field(..., description="Concise textual context or excerpt from the document")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Heuristic extraction confidence")

    model_config = ConfigDict(extra="forbid")


class ConflictingField(BaseModel):
    """Record of ambiguous or conflicting values encountered during extraction."""
    field_name: str = Field(..., description="Target profile field name")
    conflicting_values: list[str] = Field(..., description="List of conflicting candidates observed")
    reason: str = Field(..., description="Explanation of why the conflict arose")

    model_config = ConfigDict(extra="forbid")


class IngestionResponse(BaseModel):
    """Result of document ingestion and deterministic candidate extraction."""
    status: IngestionStatus = Field(..., description="Extraction outcome")
    document_type: DocumentType = Field(..., description="Validated document type")
    candidate_profile: StudentProfileBase = Field(..., description="Candidate profile populated with extracted fields")
    provenance: dict[str, FieldProvenance] = Field(default_factory=dict, description="Per-field extraction provenance")
    missing_fields: list[str] = Field(default_factory=list, description="Profile fields left unpopulated/missing")
    conflicts: list[ConflictingField] = Field(default_factory=list, description="Ambiguous or conflicting fields")
    warnings: list[str] = Field(default_factory=list, description="Warnings or issues encountered during processing")
    requires_human_review: bool = Field(default=True, description="Whether human confirmation is required")

    model_config = ConfigDict(extra="forbid")
