from dataclasses import dataclass, field
import io
import zipfile
import fitz  # PyMuPDF
import docx
from app.core.config import settings


class IngestionError(Exception):
    """Base exception for document parsing and ingestion failures."""
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class OCRRequiredError(IngestionError):
    """Raised when a document appears to be scanned/image-only and requires OCR."""
    def __init__(self, message: str = "Scanned document detected. Optical Character Recognition (OCR) is required."):
        super().__init__(message, status_code=422)


@dataclass
class TextSegment:
    """A segment of extracted document text with its location."""
    text: str
    location: str


@dataclass
class DocumentExtractionResult:
    """Result of low-level document text extraction."""
    segments: list[TextSegment] = field(default_factory=list)
    total_characters: int = 0
    page_or_element_count: int = 0
    is_scanned: bool = False

    @property
    def full_text(self) -> str:
        return "\n".join(seg.text for seg in self.segments)


class DocumentParser:
    """Secure parser for PDF and DOCX files applying resource and size limits."""

    @staticmethod
    def detect_format(content: bytes) -> str:
        """Inspect file signature to detect true format."""
        if content.startswith(b"%PDF-"):
            return "pdf"
        if content.startswith(b"PK\x03\x04"):
            # Check if it has word/document.xml inside
            try:
                with zipfile.ZipFile(io.BytesIO(content), "r") as zf:
                    namelist = zf.namelist()
                    if "word/document.xml" in namelist or any(n.startswith("word/") for n in namelist):
                        return "docx"
            except Exception:
                pass
        return "unsupported"

    @classmethod
    def parse_pdf(cls, content: bytes) -> DocumentExtractionResult:
        """Extract text from PDF using PyMuPDF safely."""
        try:
            doc = fitz.open(stream=content, filetype="pdf")
        except Exception:
            raise IngestionError("Corrupted or unreadable PDF document.", status_code=400)

        try:
            if doc.is_encrypted:
                raise IngestionError("Encrypted or password-protected PDFs are not supported.", status_code=400)

            page_count = len(doc)
            if page_count == 0:
                raise IngestionError("PDF document contains no pages.", status_code=400)

            if page_count > settings.MAX_PDF_PAGES:
                raise IngestionError(
                    f"PDF page count exceeds maximum allowable limit ({settings.MAX_PDF_PAGES} pages).",
                    status_code=413,
                )

            segments: list[TextSegment] = []
            total_chars = 0
            has_images = False

            for page_index in range(page_count):
                page = doc.load_page(page_index)
                page_text = page.get_text("text").strip()
                if page_text:
                    segments.append(TextSegment(text=page_text, location=f"Page {page_index + 1}"))
                    total_chars += len(page_text)

                # Check if page has images
                if not has_images and len(page.get_images()) > 0:
                    has_images = True

            # Detect scanned/image-only PDF: very little or no text (< 50 chars), but has pages or images
            if total_chars < 50:
                raise OCRRequiredError()

            return DocumentExtractionResult(
                segments=segments,
                total_characters=total_chars,
                page_or_element_count=page_count,
                is_scanned=False,
            )
        finally:
            doc.close()

    @classmethod
    def parse_docx(cls, content: bytes) -> DocumentExtractionResult:
        """Extract text from DOCX safely with zip bomb protection."""
        # 1. Zip bomb / archive expansion check
        try:
            with zipfile.ZipFile(io.BytesIO(content), "r") as zf:
                total_uncompressed = sum(info.file_size for info in zf.infolist())
                if total_uncompressed > settings.MAX_DOCX_UNCOMPRESSED_BYTES:
                    raise IngestionError(
                        "DOCX archive expansion exceeds allowable safety limits.",
                        status_code=413,
                    )
        except IngestionError:
            raise
        except Exception:
            raise IngestionError("Corrupted or malformed DOCX document.", status_code=400)

        # 2. Extract paragraphs and tables using python-docx
        try:
            doc = docx.Document(io.BytesIO(content))
        except Exception:
            raise IngestionError("Unable to parse DOCX document structure.", status_code=400)

        segments: list[TextSegment] = []
        total_chars = 0

        # Paragraphs
        for p_idx, para in enumerate(doc.paragraphs):
            text = para.text.strip()
            if text:
                segments.append(TextSegment(text=text, location=f"Paragraph {p_idx + 1}"))
                total_chars += len(text)

        # Tables
        for t_idx, table in enumerate(doc.tables):
            for r_idx, row in enumerate(table.rows):
                row_cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if row_cells:
                    # Deduplicate repeated adjacent cells from merged columns
                    deduped_cells = []
                    for c in row_cells:
                        if not deduped_cells or deduped_cells[-1] != c:
                            deduped_cells.append(c)
                    row_text = " | ".join(deduped_cells)
                    segments.append(TextSegment(text=row_text, location=f"Table {t_idx + 1}, Row {r_idx + 1}"))
                    total_chars += len(row_text)

        if total_chars == 0:
            raise IngestionError("DOCX document contains no readable text.", status_code=400)

        return DocumentExtractionResult(
            segments=segments,
            total_characters=total_chars,
            page_or_element_count=len(segments),
            is_scanned=False,
        )
