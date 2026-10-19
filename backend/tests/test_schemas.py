from datetime import datetime, timezone
import uuid
import pytest
from pydantic import ValidationError

from app.schemas.student_profile import (
    StudentProfileCreate,
    StudentProfileRead,
    AcademicScore,
    BudgetConstraint,
    ProjectExperience,
)
from app.schemas.opportunity import (
    OpportunityCreate,
    OpportunityRead,
    FundingDetail,
    FundingType,
    VerificationStatus,
)
from app.schemas.evidence_source import (
    EvidenceSourceCreate,
    EvidenceSourceRead,
    SourceVerificationStatus,
)
from app.schemas.eligibility_assessment import (
    EligibilityAssessmentCreate,
    EligibilityAssessmentRead,
    EligibilityCriterion,
    EligibilityStatus,
    CriterionType,
)
from app.schemas.research_run import (
    ResearchRunCreate,
    ResearchRunRead,
    ResearchRunStatus,
)


# ==============================================================================
# Student Profile Validation Tests
# ==============================================================================

def test_valid_student_profile_with_arbitrary_student():
    """Verify that a student profile unrelated to Rahul (e.g., Sarah from Brazil) is accepted."""
    profile_data = {
        "name": "Sarah Chen",
        "degree_program": "B.Sc. Data Science",
        "field_of_study": "Statistics & AI",
        "institution": "University of Sao Paulo",
        "country": "Brazil",
        "academic_stage": "final_year_undergraduate",
        "academic_score": {"score": 8.8, "scale": 10.0},
        "target_destinations": ["Germany", "Sweden"],
        "academic_interests": ["Reinforcement Learning", "Bioinformatics"],
        "projects_experiences": [
            {
                "title": "Genomic Sequence Transformer",
                "role": "Lead Researcher",
                "summary": "Trained transformer model for gene classification",
                "technologies": ["Python", "PyTorch"],
            }
        ],
        "budget_constraint": {
            "max_annual_budget": 5000.0,
            "currency": "EUR",
            "requires_full_funding": True,
            "notes": "Needs living stipend support",
        },
        "public_profile_urls": ["https://github.com/sarahchen"],
    }
    profile = StudentProfileCreate(**profile_data)
    assert profile.name == "Sarah Chen"
    assert profile.country == "Brazil"
    assert profile.academic_score.score == 8.8
    assert profile.academic_score.scale == 10.0
    assert len(profile.projects_experiences) == 1
    assert profile.budget_constraint.requires_full_funding is True


def test_student_profile_missing_optional_fields():
    """Verify missing optional profile information remains explicitly None and is not invented."""
    profile = StudentProfileCreate()
    assert profile.name is None
    assert profile.degree_program is None
    assert profile.field_of_study is None
    assert profile.institution is None
    assert profile.country is None
    assert profile.academic_stage is None
    assert profile.academic_score is None
    assert profile.budget_constraint is None
    assert profile.target_destinations == []
    assert profile.academic_interests == []
    assert profile.projects_experiences == []
    assert profile.public_profile_urls == []


def test_student_profile_rejects_extra_fields():
    """Verify extra/unjustified fields are forbidden."""
    with pytest.raises(ValidationError):
        StudentProfileCreate(
            name="Test Student",
            invented_field="some value",  # Should trigger ValidationError due to extra='forbid'
        )


def test_student_profile_rejects_invalid_urls():
    """Verify invalid URLs are rejected."""
    with pytest.raises(ValidationError):
        StudentProfileCreate(
            name="Test",
            public_profile_urls=["not-a-valid-url"],
        )


# ==============================================================================
# Opportunity Validation Tests
# ==============================================================================

def test_valid_opportunity_payload():
    """Verify valid opportunity creation with full details."""
    opp_data = {
        "name": "DAAD Helmut-Schmidt-Programme",
        "institution": "DAAD / German Universities",
        "destination_country": "Germany",
        "official_url": "https://www.daad.de/en/study-and-research-in-germany/scholarships/",
        "funding": {
            "funding_type": FundingType.FULL,
            "amount": 934.0,
            "currency": "EUR",
            "period": "per_month",
        },
        "deadline": datetime(2026, 7, 31, 23, 59, 59, tzinfo=timezone.utc),
        "verification_status": VerificationStatus.VERIFIED,
    }
    opp = OpportunityCreate(**opp_data)
    assert opp.name == "DAAD Helmut-Schmidt-Programme"
    assert opp.destination_country == "Germany"
    assert opp.funding.funding_type == FundingType.FULL
    assert opp.funding.amount == 934.0
    assert opp.verification_status == VerificationStatus.VERIFIED


def test_opportunity_missing_deadline_and_funding_semantics():
    """Missing deadline and funding must remain explicitly unknown.
    Never interpret a missing deadline as open or unknown funding as full funding.
    """
    opp = OpportunityCreate(
        name="Global Master Fellowship",
        institution="Technical University of Munich",
        destination_country="Germany",
    )
    assert opp.deadline is None
    assert opp.funding is None
    assert opp.verification_status == VerificationStatus.UNVERIFIED


def test_opportunity_rejects_invalid_verification_status():
    """Verify invalid verification statuses are rejected."""
    with pytest.raises(ValidationError):
        OpportunityCreate(
            name="Test Scholarship",
            institution="Test University",
            destination_country="Canada",
            verification_status="guaranteed_admission",  # Invalid enum value
        )


# ==============================================================================
# Evidence Source Validation Tests
# ==============================================================================

def test_evidence_source_traceability():
    """Verify evidence retains exact source URL, excerpt, and timestamp."""
    opp_id = uuid.uuid4()
    now_utc = datetime.now(timezone.utc)
    source_data = {
        "opportunity_id": opp_id,
        "source_url": "https://www.daad.de/helmut-schmidt",
        "title": "DAAD Helmut Schmidt Official Guidelines",
        "claim_supported": "Monthly stipend amount is 934 EUR",
        "excerpt": "Scholarship recipients receive a monthly allowance of 934 euros.",
        "retrieved_at": now_utc,
        "published_date": datetime(2026, 1, 15, tzinfo=timezone.utc),
        "verification_status": SourceVerificationStatus.VERIFIED,
    }
    source = EvidenceSourceCreate(**source_data)
    assert source.opportunity_id == opp_id
    assert str(source.source_url) == "https://www.daad.de/helmut-schmidt"
    assert "934 euros" in source.excerpt
    assert source.claim_supported == "Monthly stipend amount is 934 EUR"
    assert source.retrieved_at == now_utc


def test_evidence_source_rejects_invalid_url():
    """Verify invalid source URL is rejected."""
    with pytest.raises(ValidationError):
        EvidenceSourceCreate(
            opportunity_id=uuid.uuid4(),
            source_url="not-a-valid-url",
            claim_supported="Valid claim",
            excerpt="Valid excerpt",
            retrieved_at=datetime.now(timezone.utc),
        )


# ==============================================================================
# Eligibility Assessment Validation Tests
# ==============================================================================

def test_eligibility_status_values_and_distinction():
    """Verify exact statuses: met, not_met, unknown, not_applicable.
    Unknown must never be confused with not_met or met.
    """
    c_met = EligibilityCriterion(
        requirement="Minimum Bachelor degree in CS or related field",
        status=EligibilityStatus.MET,
        supporting_evidence="Holds B.Tech in Computer Science",
        criterion_type=CriterionType.ADMISSION,
    )
    c_unknown = EligibilityCriterion(
        requirement="IELTS score of 7.0 or higher",
        status=EligibilityStatus.UNKNOWN,
        reason="No language test scores provided in student profile",
        criterion_type=CriterionType.ADMISSION,
    )
    c_not_met = EligibilityCriterion(
        requirement="Maximum family income under 30,000 EUR",
        status=EligibilityStatus.NOT_MET,
        reason="Reported family budget exceeds ceiling",
        criterion_type=CriterionType.SCHOLARSHIP,
    )
    c_na = EligibilityCriterion(
        requirement="German language proficiency (DSH-2)",
        status=EligibilityStatus.NOT_APPLICABLE,
        reason="Program is taught 100% in English",
        criterion_type=CriterionType.ADMISSION,
    )

    assert c_met.status == EligibilityStatus.MET
    assert c_unknown.status == EligibilityStatus.UNKNOWN
    assert c_not_met.status == EligibilityStatus.NOT_MET
    assert c_na.status == EligibilityStatus.NOT_APPLICABLE

    # Verify unknown != not_met and unknown != met
    assert c_unknown.status != c_not_met.status
    assert c_unknown.status != c_met.status


def test_eligibility_rejects_invalid_status():
    """Verify invalid eligibility statuses are strictly rejected."""
    with pytest.raises(ValidationError):
        EligibilityCriterion(
            requirement="Must have 8.0 CGPA",
            status="almost_met",  # Invalid status
        )


def test_eligibility_keeps_admission_and_scholarship_distinct():
    """Verify criteria can distinguish between admission criteria and scholarship criteria."""
    assessment = EligibilityAssessmentCreate(
        opportunity_id=uuid.uuid4(),
        student_profile_id=uuid.uuid4(),
        criteria=[
            EligibilityCriterion(
                requirement="B.Sc. Degree in CS",
                status=EligibilityStatus.MET,
                criterion_type=CriterionType.ADMISSION,
            ),
            EligibilityCriterion(
                requirement="Merit-based top 5% rank",
                status=EligibilityStatus.UNKNOWN,
                criterion_type=CriterionType.SCHOLARSHIP,
            ),
        ],
    )
    assert assessment.criteria[0].criterion_type == CriterionType.ADMISSION
    assert assessment.criteria[1].criterion_type == CriterionType.SCHOLARSHIP


# ==============================================================================
# Research Run Validation Tests
# ==============================================================================

def test_research_run_valid_lifecycle_statuses():
    """Verify research run accepts valid statuses: queued, running, completed, failed, partial."""
    for valid_status in [
        ResearchRunStatus.QUEUED,
        ResearchRunStatus.RUNNING,
        ResearchRunStatus.COMPLETED,
        ResearchRunStatus.FAILED,
        ResearchRunStatus.PARTIAL,
    ]:
        run = ResearchRunCreate(
            profile_id=uuid.uuid4(),
            status=valid_status,
        )
        assert run.status == valid_status


def test_research_run_rejects_invalid_status():
    """Verify invalid lifecycle status is rejected."""
    with pytest.raises(ValidationError):
        ResearchRunCreate(status="in_limbo")
