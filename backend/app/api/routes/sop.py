"""API routes for Statement of Purpose (SOP) Studio drafting and fact auditing."""

import logging
from fastapi import APIRouter, HTTPException, status
from app.schemas.sop import SOPDraftRequest, SOPDraftResponse
from app.services.sop_service import generate_sop_draft

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sop", tags=["SOP Studio"])


@router.post(
    "/draft",
    response_model=SOPDraftResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate evidence-grounded SOP draft",
    description=(
        "Assembles a structured SOP/application statement draft using exclusively "
        "confirmed student-profile facts and evidence-backed opportunity criteria. "
        "Never fabricates facts, achievements, or goals. Employs explicit placeholders "
        "where facts are unverified or missing."
    ),
)
async def draft_sop(request: SOPDraftRequest) -> SOPDraftResponse:
    """Generate an editable, evidence-grounded statement of purpose draft."""
    try:
        response = generate_sop_draft(request)
        logger.info(
            "Drafted SOP for opportunity '%s' with %d confirmed facts and %d placeholders",
            response.opportunity_name,
            len(response.confirmed_facts_used),
            len(response.placeholders),
        )
        return response
    except Exception as exc:
        logger.error("Failed to generate SOP draft: %s", exc, exc_info=False)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to generate application draft from the provided profile and opportunity data.",
        ) from None
