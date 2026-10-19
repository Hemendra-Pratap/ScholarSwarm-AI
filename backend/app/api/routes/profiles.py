import logging
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import get_db
from app.models.entities import StudentProfileModel
from app.schemas.ingestion import (
    DocumentType,
    IngestionResponse,
    IngestionStatus,
)
from app.schemas.student_profile import (
    StudentProfileBase,
    StudentProfileCreate,
    StudentProfileRead,
)
from app.services.document_parser import (
    DocumentParser,
    IngestionError,
    OCRRequiredError,
)
from app.services.profile_extractor import ProfileExtractor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/profiles", tags=["Student Profiles"])


@router.post(
    "/ingest",
    response_model=IngestionResponse,
    summary="Ingest Resume or Transcript Document",
    description="Upload a PDF or DOCX file to extract candidate student profile information with provenance. Does NOT persist confirmed profile automatically.",
)
async def ingest_document(
    file: UploadFile = File(..., description="Resume or academic transcript file (PDF or DOCX)"),
    document_type: DocumentType = Form(default=DocumentType.RESUME, description="Document type: resume or transcript"),
) -> IngestionResponse:
    # 1. Validate filename and extension
    filename = file.filename or ""
    lower_filename = filename.lower()
    if not (lower_filename.endswith(".pdf") or lower_filename.endswith(".docx")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file format. Only .pdf and .docx files are accepted.",
        )

    # 2. Bounded reading and file size check
    content = bytearray()
    chunk_size = 64 * 1024  # 64 KiB chunks
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        content.extend(chunk)
        if len(content) > settings.MAX_UPLOAD_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Upload exceeds maximum allowable size of {settings.MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)} MiB.",
            )

    content_bytes = bytes(content)
    if len(content_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    # 3. Detect format from magic bytes/signature
    detected_format = DocumentParser.detect_format(content_bytes)
    expected_format = "pdf" if lower_filename.endswith(".pdf") else "docx"
    if detected_format != expected_format:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File extension '.{expected_format}' does not match detected file content signature.",
        )

    # 4. Parse document safely
    try:
        if detected_format == "pdf":
            extraction_result = DocumentParser.parse_pdf(content_bytes)
        else:
            extraction_result = DocumentParser.parse_docx(content_bytes)
    except OCRRequiredError:
        return IngestionResponse(
            status=IngestionStatus.OCR_REQUIRED,
            document_type=document_type,
            candidate_profile=StudentProfileBase(),
            provenance={},
            missing_fields=[
                "name",
                "degree_program",
                "field_of_study",
                "institution",
                "country",
                "academic_stage",
                "academic_score",
                "target_destinations",
                "academic_interests",
                "projects_experiences",
                "budget_constraint",
                "public_profile_urls",
            ],
            conflicts=[],
            warnings=["Scanned or image-only document detected. OCR is required for text extraction."],
            requires_human_review=True,
        )
    except IngestionError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception:
        # Non-sensitive error message without internal paths or stack traces
        logger.exception("Unexpected error during document parsing")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unable to process document due to malformed or corrupted internal structure.",
        )

    # 5. Extract and normalize candidate profile
    response = ProfileExtractor.extract(extraction_result, document_type=document_type)
    return response


@router.post(
    "/confirm",
    response_model=StudentProfileRead,
    status_code=status.HTTP_201_CREATED,
    summary="Confirm and Persist Reviewed Student Profile",
    description="Persist an explicitly reviewed and confirmed student profile into the database.",
)
def confirm_profile(
    profile_in: StudentProfileCreate,
    db: Session = Depends(get_db),
) -> StudentProfileRead:
    # Convert validated schema into model dict
    profile_dict = profile_in.model_dump()
    profile_id = profile_dict.pop("id", None)

    # Convert nested sub-models to primitive dicts/lists for JSON storage
    db_profile = StudentProfileModel(
        id=profile_id or None,
        name=profile_dict.get("name"),
        degree_program=profile_dict.get("degree_program"),
        field_of_study=profile_dict.get("field_of_study"),
        institution=profile_dict.get("institution"),
        country=profile_dict.get("country"),
        academic_stage=profile_dict.get("academic_stage"),
        academic_score=profile_dict.get("academic_score"),
        target_destinations=profile_dict.get("target_destinations") or [],
        academic_interests=profile_dict.get("academic_interests") or [],
        projects_experiences=profile_dict.get("projects_experiences") or [],
        budget_constraint=profile_dict.get("budget_constraint"),
        public_profile_urls=[str(u) for u in profile_dict.get("public_profile_urls", [])],
    )

    db.add(db_profile)
    db.commit()
    db.refresh(db_profile)

    return StudentProfileRead.model_validate(db_profile)
