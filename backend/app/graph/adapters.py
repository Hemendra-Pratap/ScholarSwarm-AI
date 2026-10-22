from datetime import datetime, timezone
import logging
from typing import Any
import uuid

from app.schemas.discovery import DiscoveredCandidate
from app.schemas.eligibility import (
    CriterionRuleDefinition,
    CriterionScope,
    EligibilityAuditRequest,
    EligibilityAuditResponse,
    EvaluatedCriterion,
    OverallEligibilityClassification,
    RuleOperator,
)
from app.schemas.eligibility_assessment import EligibilityStatus
from app.schemas.opportunity import OpportunityBase, VerificationStatus
from app.schemas.ranking import CandidateOpportunityInput
from app.schemas.student_profile import StudentProfileBase
from app.schemas.verification import (
    CandidateVerificationReport,
    SourceClassification,
    VerificationReportStatus,
)

logger = logging.getLogger(__name__)


def build_candidate_key(name: str, institution: str | None = None) -> str:
    """Deterministic lookup key for an opportunity by normalized name and institution."""
    inst = (institution or "").strip().lower()
    return f"{name.strip().lower()}::{inst}"


def adapt_candidate_to_eligibility_criteria(
    candidate: DiscoveredCandidate,
    verification_report: CandidateVerificationReport | None,
) -> list[EvaluatedCriterion]:
    """
    Derive deterministic EvaluatedCriterion items for a discovered candidate based on its
    extracted facts and official verification evidence.
    
    If the candidate's claims have official verification corroboration, criteria are constructed
    with verified official source URLs and excerpts so M7 can validate them.
    If official verification is missing or unverified, evidence gates remain conservative.
    """
    opp = candidate.opportunity
    criteria: list[EvaluatedCriterion] = []
    
    # 1. Determine verified official URL and excerpt if corroboration succeeded
    verified_url: str | None = None
    if verification_report and verification_report.verified_official_url:
        verified_url = str(verification_report.verified_official_url)
    elif verification_report:
        for sa in verification_report.source_assessments:
            if sa.classification == SourceClassification.OFFICIAL:
                verified_url = str(sa.source_url)
                break
    if not verified_url and opp.official_url:
        # Check if original URL was marked official
        if verification_report:
            for sa in verification_report.source_assessments:
                if str(sa.source_url).rstrip("/") == str(opp.official_url).rstrip("/") and sa.classification == SourceClassification.OFFICIAL:
                    verified_url = str(opp.official_url)
                    break

    is_official = verified_url is not None

    # Criterion A: Destination / Country Alignment
    if opp.destination_country:
        excerpt_text = f"Opportunity offered in {opp.destination_country}."
        if verification_report:
            for ca in verification_report.claim_assessments:
                if ca.claim_type == "destination_country" and ca.excerpt:
                    excerpt_text = ca.excerpt
                    break

        criteria.append(
            EvaluatedCriterion(
                criterion_id=str(uuid.uuid4()),
                description=f"Destination country matches target: {opp.destination_country}",
                category="destination",
                scope=CriterionScope.BOTH,
                mandatory=True,
                rule=CriterionRuleDefinition(
                    target_field="target_destinations",
                    operator=RuleOperator.CONTAINS,
                    expected_value=opp.destination_country,
                ),
                source_url=verified_url or (str(opp.official_url) if opp.official_url else candidate.source_url),
                evidence_excerpt=excerpt_text,
                is_official_evidence=is_official,
                outcome=EligibilityStatus.UNKNOWN,
                reason="Derived from discovered candidate opportunity destination.",
            )
        )

    # Criterion B: Field of Study / Subject Area
    # If the student's field of study is known, evaluate whether candidate name/snippet contains it or matches
    criteria.append(
        EvaluatedCriterion(
            criterion_id=str(uuid.uuid4()),
            description=f"Candidate program at {opp.institution} aligns with academic field",
            category="field_of_study",
            scope=CriterionScope.ADMISSION,
            mandatory=False,
            rule=None,  # General domain fit assessed as unknown/informational unless structured
            source_url=verified_url or (str(opp.official_url) if opp.official_url else candidate.source_url),
            evidence_excerpt=candidate.snippet or f"Program offered at {opp.institution}.",
            is_official_evidence=is_official,
            outcome=EligibilityStatus.UNKNOWN,
            reason="Subject alignment is advisory and requires official syllabus review.",
        )
    )

    return criteria


def adapt_candidate_and_audit_to_ranking_input(
    candidate: DiscoveredCandidate,
    verification_report: CandidateVerificationReport | None,
    audit_response: EligibilityAuditResponse | None,
) -> CandidateOpportunityInput:
    """
    Safely adapt an individual candidate, its verification report, and its M7 eligibility audit
    into the CandidateOpportunityInput required by M8 Ranking.
    """
    opp = candidate.opportunity.model_copy()

    # Update opportunity verification status based on report if available
    if verification_report:
        if verification_report.overall_status == VerificationReportStatus.VERIFIED:
            opp.verification_status = VerificationStatus.VERIFIED
            if verification_report.verified_official_url:
                try:
                    from pydantic import HttpUrl, TypeAdapter
                    opp.official_url = TypeAdapter(HttpUrl).validate_python(verification_report.verified_official_url)
                except Exception:
                    pass
        elif verification_report.overall_status == VerificationReportStatus.CONFLICTING:
            opp.verification_status = VerificationStatus.CONTRADICTORY
        elif verification_report.overall_status == VerificationReportStatus.SOURCE_INACCESSIBLE:
            opp.verification_status = VerificationStatus.INACCESSIBLE
        else:
            # PARTIALLY_VERIFIED or UNVERIFIED map to UNVERIFIED on OpportunityBase
            opp.verification_status = VerificationStatus.UNVERIFIED
    else:
        opp.verification_status = VerificationStatus.UNVERIFIED

    if audit_response is not None:
        elig_classification = audit_response.overall_classification
        disqualifying = list(audit_response.disqualifying_criteria)
        unknown = list(audit_response.unknown_criteria)
        caveats = list(audit_response.evidence_caveats)
    else:
        # If audit did not run (e.g. skipped or not assessable), honestly classify as NOT_ASSESSABLE
        elig_classification = OverallEligibilityClassification.NOT_ASSESSABLE
        disqualifying = []
        unknown = ["Eligibility audit was not performed for this candidate."]
        caveats = ["Eligibility data unavailable."]

    return CandidateOpportunityInput(
        opportunity=opp,
        eligibility_classification=elig_classification,
        disqualifying_criteria=disqualifying,
        unknown_criteria=unknown,
        evidence_caveats=caveats,
    )
