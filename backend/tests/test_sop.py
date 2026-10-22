"""Tests for SOP drafting service and API endpoint."""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.schemas.eligibility import OverallEligibilityClassification
from app.schemas.opportunity import (
    FundingDetail,
    FundingType,
    OpportunityBase,
    VerificationStatus,
)
from app.schemas.ranking import (
    ActionItemPriority,
    ActionItemStatus,
    ApplicationActionItem,
    DeadlineFeasibilityStatus,
    RankedOpportunityItem,
    ScoreComponentDetail,
)
from app.schemas.sop import SOPDraftRequest, SOPDraftResponse
from app.schemas.student_profile import (
    AcademicScore,
    BudgetConstraint,
    ProjectExperience,
    StudentProfileBase,
)
from app.services.sop_service import MANDATORY_DISCLAIMER, generate_sop_draft

client = TestClient(app)


def make_test_profile(
    name: str | None = "Alex Mercer",
    degree: str | None = "Bachelor of Science in Informatics",
    field: str | None = "Computer Science",
    institution: str | None = "Technical University of Munich",
    score: float | None = 3.9,
    scale: float | None = 4.0,
    interests: list[str] | None = None,
    projects: list[ProjectExperience] | None = None,
) -> StudentProfileBase:
    return StudentProfileBase(
        name=name,
        degree_program=degree,
        field_of_study=field,
        institution=institution,
        country="Germany",
        academic_stage="final_year_undergraduate",
        academic_score=AcademicScore(score=score, scale=scale) if score is not None else None,
        target_destinations=["Germany", "Switzerland"],
        academic_interests=interests if interests is not None else ["Machine Learning", "Distributed Systems"],
        projects_experiences=projects if projects is not None else [
            ProjectExperience(
                title="Distributed Consensus Engine",
                role="Lead Developer",
                summary="Implemented Raft consensus in Rust with formal TLA+ verification.",
                technologies=["Rust", "TLA+", "gRPC"],
            )
        ],
        budget_constraint=BudgetConstraint(
            requires_full_funding=True,
            max_annual_budget=0.0,
            currency="EUR",
            notes="Requires full scholarship coverage.",
        ),
        public_profile_urls=[],
    )


def make_test_ranked_item(
    name: str = "ETH Zurich Excellence Scholarship",
    institution: str = "ETH Zurich",
    country: str = "Switzerland",
    official_url: str = "https://ethz.ch/en/studies/financial/excellence-scholarship.html",
    fit_score: float = 94.5,
    main_strengths: list[str] | None = None,
    main_gaps: list[str] | None = None,
    verification_status: VerificationStatus = VerificationStatus.VERIFIED,
) -> RankedOpportunityItem:
    return RankedOpportunityItem(
        opportunity=OpportunityBase(
            name=name,
            institution=institution,
            destination_country=country,
            official_url=official_url,
            funding=FundingDetail(
                funding_type=FundingType.FULL,
                amount=24000.0,
                currency="CHF",
                period="per_year",
            ),
            verification_status=verification_status,
            deadline=None,
        ),
        rank=1,
        fit_score=fit_score,
        max_score=100.0,
        score_coverage_pct=100.0,
        score_components={
            "academic_fit": ScoreComponentDetail(
                weight=0.35,
                raw_score=95.0,
                weighted_score=33.25,
                is_known=True,
                explanation="High academic score alignment.",
            ),
            "experience_fit": ScoreComponentDetail(
                weight=0.25,
                raw_score=90.0,
                weighted_score=22.5,
                is_known=True,
                explanation="Strong technical project portfolio.",
            ),
            "funding_fit": ScoreComponentDetail(
                weight=0.25,
                raw_score=100.0,
                weighted_score=25.0,
                is_known=True,
                explanation="Full funding covers student requirements.",
            ),
            "deadline_fit": ScoreComponentDetail(
                weight=0.15,
                raw_score=92.0,
                weighted_score=13.8,
                is_known=True,
                explanation="Open deadline with sufficient runway.",
            ),
        },
        score_explanation="Top recommendation with excellent academic alignment and full funding coverage.",
        eligibility_classification=OverallEligibilityClassification.ELIGIBLE,
        disqualifying_criteria=[],
        unknown_criteria=[],
        funding_summary="Full scholarship: 100% tuition coverage and CHF 12,000 semester stipend.",
        deadline_summary="Deadline: December 15, 2026 (Feasible).",
        deadline_feasibility=DeadlineFeasibilityStatus.OPEN,
        deadline_feasibility_reason="Deadline is over 60 days away.",
        main_strengths=main_strengths or [
            "Matches target field of Computer Science",
            "Exceeds minimum academic GPA threshold",
            "Full funding matches zero personal budget requirement",
        ],
        main_gaps=main_gaps or [],
        recommended_actions=[
            ApplicationActionItem(
                title="Prepare certified academic transcripts",
                reason="Official university application requires stamped copies",
                priority=ActionItemPriority.HIGH,
                status=ActionItemStatus.REQUIRED,
                opportunity_name=name,
            )
        ],
        evidence_references=[official_url],
        caveats=[],
    )


def test_sop_draft_service_full_profile():
    profile = make_test_profile()
    item = make_test_ranked_item()
    request = SOPDraftRequest(
        student_profile=profile,
        opportunity=item,
        additional_notes="Emphasize systems programming interest.",
    )

    response = generate_sop_draft(request)
    assert response.opportunity_name == "ETH Zurich Excellence Scholarship"
    assert response.institution == "ETH Zurich"
    assert "Alex Mercer" in response.draft_text
    assert "ETH Zurich Excellence Scholarship" in response.draft_text
    assert "3.9 / 4.0" in response.draft_text
    assert "Distributed Consensus Engine" in response.draft_text
    assert "Emphasize systems programming interest" in response.draft_text
    assert response.disclaimer == MANDATORY_DISCLAIMER
    assert MANDATORY_DISCLAIMER in response.draft_text
    assert len(response.confirmed_facts_used) >= 7
    assert len(response.source_citations) >= 1
    # Check that goals are NOT hallucinated but requested via placeholder
    assert any("genuine post-graduation" in p for p in response.placeholders)


def test_sop_draft_missing_facts_have_placeholders_never_hallucinated():
    # Profile with missing score, degree, and projects
    profile = make_test_profile(
        name=None,
        degree=None,
        field=None,
        institution=None,
        score=None,
        scale=None,
        interests=[],
        projects=[],
    )
    item = make_test_ranked_item()
    request = SOPDraftRequest(student_profile=profile, opportunity=item)

    response = generate_sop_draft(request)
    # Confirm explicit placeholders were inserted and no fake score was invented
    assert "[STUDENT_INPUT: Your Full Name]" in response.placeholders
    assert "[MISSING: Confirmed GPA/marks and grading scale]" in response.placeholders
    assert "[MISSING: Current or prior degree program]" in response.placeholders
    assert "[MISSING: Primary field of study]" in response.placeholders
    assert "[MISSING: Undergraduate/prior institution name]" in response.placeholders

    # Text contains explicit placeholders
    assert "[MISSING: Insert confirmed GPA/percentage" in response.draft_text
    assert "[STUDENT_INPUT: 1-2 major academic or capstone projects" in response.draft_text


def test_sop_draft_with_gaps_and_actions():
    profile = make_test_profile()
    item = make_test_ranked_item(
        main_gaps=["Requires GRE Quantitative >= 165", "Requires 2 academic letters of recommendation"]
    )
    request = SOPDraftRequest(student_profile=profile, opportunity=item)

    response = generate_sop_draft(request)
    assert len(response.unverified_claims) >= 2
    assert any("Requires GRE Quantitative" in u for u in response.unverified_claims)
    assert any("Address prerequisite/evidence for: Requires GRE Quantitative" in p for p in response.placeholders)
    assert "Requires GRE Quantitative >= 165" in response.draft_text


def test_sop_draft_api_endpoint_success():
    profile = make_test_profile()
    item = make_test_ranked_item()
    payload = {
        "student_profile": profile.model_dump(mode="json"),
        "opportunity": item.model_dump(mode="json"),
        "additional_notes": "Focused on research.",
    }

    resp = client.post("/api/v1/sop/draft", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["opportunity_name"] == "ETH Zurich Excellence Scholarship"
    assert data["institution"] == "ETH Zurich"
    assert "Alex Mercer" in data["draft_text"]
    assert len(data["confirmed_facts_used"]) > 0
    assert data["disclaimer"] == MANDATORY_DISCLAIMER


def test_sop_draft_api_endpoint_validation_error():
    # Sending missing opportunity should return 422
    resp = client.post("/api/v1/sop/draft", json={"student_profile": {}})
    assert resp.status_code == 422


def test_sop_draft_provenance_verified_vs_unverified_opportunity():
    profile = make_test_profile()

    # 1. Verified opportunity
    verified_item = make_test_ranked_item(verification_status=VerificationStatus.VERIFIED)
    resp_verified = generate_sop_draft(SOPDraftRequest(student_profile=profile, opportunity=verified_item))

    opp_fact = next(f for f in resp_verified.confirmed_facts_used if f.field_name == "Target Opportunity")
    inst_fact = next(f for f in resp_verified.confirmed_facts_used if f.field_name == "Target Institution")
    assert opp_fact.is_verified is True
    assert "Verified Official Source" in opp_fact.source
    assert inst_fact.is_verified is True
    assert inst_fact.source == "Verified Official Source"

    # 2. Unverified opportunity
    unverified_item = make_test_ranked_item(verification_status=VerificationStatus.UNVERIFIED)
    resp_unverified = generate_sop_draft(SOPDraftRequest(student_profile=profile, opportunity=unverified_item))

    opp_fact_unv = next(f for f in resp_unverified.confirmed_facts_used if f.field_name == "Target Opportunity")
    inst_fact_unv = next(f for f in resp_unverified.confirmed_facts_used if f.field_name == "Target Institution")
    assert opp_fact_unv.is_verified is False
    assert "Verified Official Source" not in opp_fact_unv.source
    assert inst_fact_unv.is_verified is False
    assert inst_fact_unv.source == "Opportunity Record"

    # 3. Inaccessible/uncertain opportunity
    inaccessible_item = make_test_ranked_item(verification_status=VerificationStatus.INACCESSIBLE)
    resp_inaccessible = generate_sop_draft(SOPDraftRequest(student_profile=profile, opportunity=inaccessible_item))

    opp_fact_inacc = next(f for f in resp_inaccessible.confirmed_facts_used if f.field_name == "Target Opportunity")
    inst_fact_inacc = next(f for f in resp_inaccessible.confirmed_facts_used if f.field_name == "Target Institution")
    assert opp_fact_inacc.is_verified is False
    assert inst_fact_inacc.is_verified is False
