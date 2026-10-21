import pytest
from fastapi.testclient import TestClient
from app.main import app
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
from app.schemas.student_profile import (
    AcademicScore,
    BudgetConstraint,
    StudentProfileBase,
)
from app.schemas.verification import (
    CandidateVerificationReport,
    SourceAssessment,
    SourceClassification,
    VerificationReportStatus,
)
from app.services.eligibility_agent import EligibilityAuditAgent
from datetime import datetime, timezone


client = TestClient(app)


def make_sample_profile(
    score: float = 3.8,
    scale: float | None = 4.0,
    degree_program: str | None = "Bachelor of Science in Computer Science",
    field_of_study: str | None = "Computer Science",
    country: str | None = "India",
    academic_stage: str | None = "undergraduate",
    target_destinations: list[str] | None = None,
) -> StudentProfileBase:
    return StudentProfileBase(
        name="Alex Doe",
        degree_program=degree_program,
        field_of_study=field_of_study,
        institution="Apex Institute of Technology",
        country=country,
        academic_stage=academic_stage,
        academic_score=AcademicScore(score=score, scale=scale) if score is not None else None,
        target_destinations=target_destinations or ["Germany", "Canada"],
        academic_interests=["Artificial Intelligence", "Robotics"],
    )


def make_official_verification_report(
    official_url: str = "https://www.tum.de/scholarship-info",
) -> CandidateVerificationReport:
    return CandidateVerificationReport(
        candidate_name="TUM Merit Scholarship",
        original_source_url="https://daad.de/listing",
        overall_status=VerificationReportStatus.VERIFIED,
        source_assessments=[
            SourceAssessment(
                source_url=official_url,
                title="TUM Scholarship Official Page",
                retrieval_status="success",
                classification=SourceClassification.OFFICIAL,
                reason="Official institution domain verified",
                retrieved_at=datetime.now(timezone.utc),
                is_discovered_official_source=True,
            )
        ],
        claim_assessments=[],
        verified_official_url=official_url,
        warnings=[],
        verified_at=datetime.now(timezone.utc),
    )


# --- Criterion Semantics Tests ---

@pytest.mark.anyio
async def test_criterion_supported_rule_met():
    agent = EligibilityAuditAgent()
    profile = make_sample_profile(score=3.8, scale=4.0)
    criterion = EvaluatedCriterion(
        description="Minimum GPA of 3.5 on a 4.0 scale",
        scope=CriterionScope.SCHOLARSHIP,
        mandatory=True,
        rule=CriterionRuleDefinition(
            target_field="academic_score",
            operator=RuleOperator.GREATER_THAN_OR_EQUAL,
            expected_value=3.5,
            scale=4.0,
        ),
        source_url="https://www.tum.de/scholarship-info",
        evidence_excerpt="Applicants must have a minimum GPA of 3.5 out of 4.0.",
        is_official_evidence=True,
        outcome=EligibilityStatus.UNKNOWN,
        reason="",
    )
    request = EligibilityAuditRequest(
        opportunity_name="TUM Merit Scholarship",
        student_profile=profile,
        criteria=[criterion],
    )
    response = await agent.audit(request)
    assert response.overall_classification == OverallEligibilityClassification.ELIGIBLE
    res_crit = response.evaluated_criteria[0]
    assert res_crit.outcome == EligibilityStatus.MET
    assert "Satisfied" in res_crit.reason
    assert res_crit.student_value == {"score": 3.8, "scale": 4.0}


@pytest.mark.anyio
async def test_criterion_contradicted_not_met():
    agent = EligibilityAuditAgent()
    profile = make_sample_profile(score=3.2, scale=4.0)
    criterion = EvaluatedCriterion(
        description="Minimum GPA of 3.5 on a 4.0 scale",
        scope=CriterionScope.SCHOLARSHIP,
        mandatory=True,
        rule=CriterionRuleDefinition(
            target_field="academic_score",
            operator=RuleOperator.GREATER_THAN_OR_EQUAL,
            expected_value=3.5,
            scale=4.0,
        ),
        source_url="https://www.tum.de/scholarship-info",
        evidence_excerpt="Applicants must have a minimum GPA of 3.5 out of 4.0.",
        is_official_evidence=True,
        outcome=EligibilityStatus.UNKNOWN,
        reason="",
    )
    request = EligibilityAuditRequest(
        opportunity_name="TUM Merit Scholarship",
        student_profile=profile,
        criteria=[criterion],
    )
    response = await agent.audit(request)
    assert response.overall_classification == OverallEligibilityClassification.INELIGIBLE
    res_crit = response.evaluated_criteria[0]
    assert res_crit.outcome == EligibilityStatus.NOT_MET
    assert "Not satisfied" in res_crit.reason
    assert len(response.disqualifying_criteria) == 1


@pytest.mark.anyio
async def test_criterion_missing_student_data_yields_unknown():
    agent = EligibilityAuditAgent()
    profile = make_sample_profile(score=3.8, country=None)
    criterion = EvaluatedCriterion(
        description="Must be resident of Canada",
        scope=CriterionScope.ADMISSION,
        mandatory=True,
        rule=CriterionRuleDefinition(
            target_field="country",
            operator=RuleOperator.EQUALS,
            expected_value="Canada",
        ),
        source_url="https://www.ubc.ca/admission-rules",
        evidence_excerpt="Applicants must hold Canadian citizenship or permanent residency.",
        is_official_evidence=True,
        outcome=EligibilityStatus.UNKNOWN,
        reason="",
    )
    request = EligibilityAuditRequest(
        opportunity_name="UBC Graduate Admissions",
        student_profile=profile,
        criteria=[criterion],
    )
    response = await agent.audit(request)
    # Since country is None on profile, result must be unknown and prevent eligible
    assert response.overall_classification == OverallEligibilityClassification.INSUFFICIENT_EVIDENCE
    assert response.evaluated_criteria[0].outcome == EligibilityStatus.UNKNOWN
    assert "Missing required student profile attribute" in response.evaluated_criteria[0].reason
    assert response.is_incomplete is True


@pytest.mark.anyio
async def test_criterion_conflicting_profile_data_yields_unknown():
    agent = EligibilityAuditAgent()
    profile = make_sample_profile(country="India")
    criterion = EvaluatedCriterion(
        description="Residency requirement",
        scope=CriterionScope.ADMISSION,
        mandatory=True,
        rule=CriterionRuleDefinition(
            target_field="country",
            operator=RuleOperator.EQUALS,
            expected_value="India",
        ),
        source_url="https://www.iit.ac.in/rules",
        evidence_excerpt="Open to Indian nationals.",
        is_official_evidence=True,
        outcome=EligibilityStatus.UNKNOWN,
        reason="",
    )
    request = EligibilityAuditRequest(
        opportunity_name="IIT Fellowship",
        student_profile=profile,
        criteria=[criterion],
        conflicting_profile_fields=["country"],  # explicitly flagged conflicting
    )
    response = await agent.audit(request)
    assert response.evaluated_criteria[0].outcome == EligibilityStatus.UNKNOWN
    assert "conflicting or unresolved" in response.evaluated_criteria[0].reason
    assert response.overall_classification == OverallEligibilityClassification.INSUFFICIENT_EVIDENCE


@pytest.mark.anyio
async def test_unsupported_natural_language_criterion_yields_unknown():
    agent = EligibilityAuditAgent()
    profile = make_sample_profile()
    criterion = EvaluatedCriterion(
        description="Demonstrated exceptional leadership and civic engagement through extracurricular activities",
        scope=CriterionScope.SCHOLARSHIP,
        mandatory=True,
        rule=None,  # No deterministic rule
        source_url="https://www.rhodeshouse.ox.ac.uk",
        evidence_excerpt="Candidates must demonstrate energy to use one's talents to the full.",
        is_official_evidence=True,
        outcome=EligibilityStatus.UNKNOWN,
        reason="",
    )
    request = EligibilityAuditRequest(
        opportunity_name="Rhodes Trust",
        student_profile=profile,
        criteria=[criterion],
    )
    response = await agent.audit(request)
    assert response.evaluated_criteria[0].outcome == EligibilityStatus.UNKNOWN
    assert "Unsupported or unparsed natural-language criterion" in response.evaluated_criteria[0].reason


@pytest.mark.anyio
async def test_not_applicable_criterion_with_defensible_reason():
    agent = EligibilityAuditAgent()
    profile = make_sample_profile()
    criterion = EvaluatedCriterion(
        description="Work authorization for current full-time employees",
        scope=CriterionScope.ADMISSION,
        mandatory=True,
        rule=None,
        outcome=EligibilityStatus.NOT_APPLICABLE,
        reason="Student is applying as an undergraduate direct-entry applicant and is not an employed professional.",
    )
    request = EligibilityAuditRequest(
        opportunity_name="Direct Undergraduate Entry",
        student_profile=profile,
        criteria=[criterion],
    )
    response = await agent.audit(request)
    assert response.evaluated_criteria[0].outcome == EligibilityStatus.NOT_APPLICABLE
    assert "direct-entry applicant" in response.evaluated_criteria[0].reason
    assert response.overall_classification == OverallEligibilityClassification.NOT_ASSESSABLE


@pytest.mark.anyio
async def test_optional_unknown_criterion_remains_visible():
    agent = EligibilityAuditAgent()
    profile = make_sample_profile(score=3.8, scale=4.0)
    mandatory_crit = EvaluatedCriterion(
        description="Minimum GPA of 3.0",
        scope=CriterionScope.SCHOLARSHIP,
        mandatory=True,
        rule=CriterionRuleDefinition(
            target_field="academic_score",
            operator=RuleOperator.GREATER_THAN_OR_EQUAL,
            expected_value=3.0,
            scale=4.0,
        ),
        source_url="https://www.tum.de/scholarship-info",
        evidence_excerpt="Minimum GPA of 3.0 required.",
        is_official_evidence=True,
        outcome=EligibilityStatus.UNKNOWN,
        reason="",
    )
    optional_crit = EvaluatedCriterion(
        description="Optional GRE test score for bonus consideration",
        scope=CriterionScope.SCHOLARSHIP,
        mandatory=False,
        rule=None,  # Unsupported natural language or missing GRE
        source_url="https://www.tum.de/scholarship-info",
        evidence_excerpt="Optional GRE scores may be submitted.",
        is_official_evidence=True,
        outcome=EligibilityStatus.UNKNOWN,
        reason="",
    )
    request = EligibilityAuditRequest(
        opportunity_name="TUM Merit Scholarship",
        student_profile=profile,
        criteria=[mandatory_crit, optional_crit],
    )
    response = await agent.audit(request)
    # Mandatory is MET, optional is UNKNOWN -> Overall is ELIGIBLE because all mandatory are met!
    assert response.overall_classification == OverallEligibilityClassification.ELIGIBLE
    assert response.scholarship_assessment.overall_classification == OverallEligibilityClassification.ELIGIBLE
    # Optional criterion is still present in evaluated_criteria and marked unknown
    opt_evaluated = next(c for c in response.evaluated_criteria if not c.mandatory)
    assert opt_evaluated.outcome == EligibilityStatus.UNKNOWN
    assert response.is_incomplete is False


# --- Aggregation and Scope Separation Tests ---

@pytest.mark.anyio
async def test_admission_and_scholarship_scopes_kept_distinct():
    agent = EligibilityAuditAgent()
    profile = make_sample_profile(score=3.2, scale=4.0, country="India")

    # Admission criterion: Minimum GPA 3.0 (Met)
    admission_crit = EvaluatedCriterion(
        description="Admission minimum GPA 3.0",
        scope=CriterionScope.ADMISSION,
        mandatory=True,
        rule=CriterionRuleDefinition(
            target_field="academic_score",
            operator=RuleOperator.GREATER_THAN_OR_EQUAL,
            expected_value=3.0,
            scale=4.0,
        ),
        source_url="https://www.tum.de/admissions",
        evidence_excerpt="Minimum GPA of 3.0 required for program admission.",
        is_official_evidence=True,
        outcome=EligibilityStatus.UNKNOWN,
        reason="",
    )

    # Scholarship criterion: Minimum GPA 3.7 (Not Met)
    scholarship_crit = EvaluatedCriterion(
        description="Excellence Scholarship minimum GPA 3.7",
        scope=CriterionScope.SCHOLARSHIP,
        mandatory=True,
        rule=CriterionRuleDefinition(
            target_field="academic_score",
            operator=RuleOperator.GREATER_THAN_OR_EQUAL,
            expected_value=3.7,
            scale=4.0,
        ),
        source_url="https://www.tum.de/scholarships",
        evidence_excerpt="Minimum GPA of 3.7 required for the Excellence award.",
        is_official_evidence=True,
        outcome=EligibilityStatus.UNKNOWN,
        reason="",
    )

    request = EligibilityAuditRequest(
        opportunity_name="TUM MS Computer Science & Excellence Award",
        student_profile=profile,
        criteria=[admission_crit, scholarship_crit],
    )
    response = await agent.audit(request)

    # Admission should be ELIGIBLE, Scholarship should be INELIGIBLE
    assert response.admission_assessment is not None
    assert response.admission_assessment.overall_classification == OverallEligibilityClassification.ELIGIBLE
    assert response.scholarship_assessment is not None
    assert response.scholarship_assessment.overall_classification == OverallEligibilityClassification.INELIGIBLE
    # Combined overall must be conservatively INELIGIBLE (failed mandatory scholarship)
    assert response.overall_classification == OverallEligibilityClassification.INELIGIBLE


@pytest.mark.anyio
async def test_unknown_mandatory_criterion_prevents_eligible():
    agent = EligibilityAuditAgent()
    profile = make_sample_profile(score=3.8, scale=4.0)

    met_crit = EvaluatedCriterion(
        description="Minimum GPA 3.5",
        scope=CriterionScope.ADMISSION,
        mandatory=True,
        rule=CriterionRuleDefinition(
            target_field="academic_score",
            operator=RuleOperator.GREATER_THAN_OR_EQUAL,
            expected_value=3.5,
            scale=4.0,
        ),
        source_url="https://www.tum.de/admissions",
        evidence_excerpt="GPA 3.5 minimum.",
        is_official_evidence=True,
        outcome=EligibilityStatus.UNKNOWN,
        reason="",
    )
    unknown_crit = EvaluatedCriterion(
        description="Prerequisite coursework in operating systems",
        scope=CriterionScope.ADMISSION,
        mandatory=True,
        rule=None,  # cannot be verified from student profile directly
        source_url="https://www.tum.de/admissions",
        evidence_excerpt="Must have completed an operating systems course.",
        is_official_evidence=True,
        outcome=EligibilityStatus.UNKNOWN,
        reason="",
    )

    request = EligibilityAuditRequest(
        opportunity_name="TUM Admissions",
        student_profile=profile,
        criteria=[met_crit, unknown_crit],
    )
    response = await agent.audit(request)
    assert response.admission_assessment.overall_classification == OverallEligibilityClassification.NEEDS_REVIEW
    assert response.overall_classification == OverallEligibilityClassification.NEEDS_REVIEW
    assert response.is_incomplete is True


# --- Numeric and Scale Robustness Tests ---

@pytest.mark.anyio
async def test_incompatible_gpa_scales_yield_unknown():
    agent = EligibilityAuditAgent()
    # Student has 8.5 on a 10.0 scale
    profile = make_sample_profile(score=8.5, scale=10.0)
    # Criterion expects 3.5 on a 4.0 scale
    criterion = EvaluatedCriterion(
        description="Minimum GPA 3.5 on a 4.0 scale",
        scope=CriterionScope.ADMISSION,
        mandatory=True,
        rule=CriterionRuleDefinition(
            target_field="academic_score",
            operator=RuleOperator.GREATER_THAN_OR_EQUAL,
            expected_value=3.5,
            scale=4.0,
        ),
        source_url="https://www.stanford.edu/admissions",
        evidence_excerpt="GPA must be 3.5 on a 4.0 scale.",
        is_official_evidence=True,
        outcome=EligibilityStatus.UNKNOWN,
        reason="",
    )
    request = EligibilityAuditRequest(
        opportunity_name="Stanford Admissions",
        student_profile=profile,
        criteria=[criterion],
    )
    response = await agent.audit(request)
    assert response.evaluated_criteria[0].outcome == EligibilityStatus.UNKNOWN
    assert "Incompatible score scales" in response.evaluated_criteria[0].reason


@pytest.mark.anyio
async def test_missing_scale_yields_unknown():
    agent = EligibilityAuditAgent()
    # Student has 3.5 with no scale specified
    profile = make_sample_profile(score=3.5, scale=None)
    criterion = EvaluatedCriterion(
        description="Minimum GPA 3.0 on a 4.0 scale",
        scope=CriterionScope.ADMISSION,
        mandatory=True,
        rule=CriterionRuleDefinition(
            target_field="academic_score",
            operator=RuleOperator.GREATER_THAN_OR_EQUAL,
            expected_value=3.0,
            scale=4.0,
        ),
        source_url="https://www.tum.de/admissions",
        evidence_excerpt="GPA 3.0 on 4.0 scale.",
        is_official_evidence=True,
        outcome=EligibilityStatus.UNKNOWN,
        reason="",
    )
    request = EligibilityAuditRequest(
        opportunity_name="TUM Admissions",
        student_profile=profile,
        criteria=[criterion],
    )
    response = await agent.audit(request)
    assert response.evaluated_criteria[0].outcome == EligibilityStatus.UNKNOWN
    assert "Missing scale information" in response.evaluated_criteria[0].reason


# --- Evidence Quality Gate Tests ---

@pytest.mark.anyio
async def test_third_party_evidence_blocks_met_status():
    agent = EligibilityAuditAgent()
    profile = make_sample_profile(score=3.9, scale=4.0)

    # Criterion rule evaluates to true, but source is unverified/third-party blog
    criterion = EvaluatedCriterion(
        description="Minimum GPA 3.5",
        scope=CriterionScope.SCHOLARSHIP,
        mandatory=True,
        rule=CriterionRuleDefinition(
            target_field="academic_score",
            operator=RuleOperator.GREATER_THAN_OR_EQUAL,
            expected_value=3.5,
            scale=4.0,
        ),
        source_url="https://www.scholarshipportal.com/blog/tum-scholarships",
        evidence_excerpt="According to student blogs, a 3.5 GPA is required.",
        is_official_evidence=False,
        outcome=EligibilityStatus.UNKNOWN,
        reason="",
    )
    verification_report = CandidateVerificationReport(
        candidate_name="TUM Merit Scholarship",
        original_source_url="https://www.scholarshipportal.com/blog/tum-scholarships",
        overall_status=VerificationReportStatus.UNVERIFIED,
        source_assessments=[
            SourceAssessment(
                source_url="https://www.scholarshipportal.com/blog/tum-scholarships",
                retrieval_status="success",
                classification=SourceClassification.THIRD_PARTY,
                reason="Commercial aggregator blog, not official university domain",
                retrieved_at=datetime.now(timezone.utc),
            )
        ],
        claim_assessments=[],
        verified_at=datetime.now(timezone.utc),
    )

    request = EligibilityAuditRequest(
        opportunity_name="TUM Merit Scholarship",
        student_profile=profile,
        criteria=[criterion],
        verification_report=verification_report,
    )
    response = await agent.audit(request)
    # Because evidence is third-party, it cannot be confirmed as MET!
    assert response.evaluated_criteria[0].outcome == EligibilityStatus.UNKNOWN
    assert "third-party" in response.evaluated_criteria[0].reason
    assert response.overall_classification == OverallEligibilityClassification.INSUFFICIENT_EVIDENCE


@pytest.mark.anyio
async def test_missing_evidence_excerpt_blocks_met():
    agent = EligibilityAuditAgent()
    profile = make_sample_profile(score=3.9, scale=4.0)
    criterion = EvaluatedCriterion(
        description="Minimum GPA 3.5",
        scope=CriterionScope.SCHOLARSHIP,
        mandatory=True,
        rule=CriterionRuleDefinition(
            target_field="academic_score",
            operator=RuleOperator.GREATER_THAN_OR_EQUAL,
            expected_value=3.5,
            scale=4.0,
        ),
        source_url="https://www.tum.de/scholarships",
        evidence_excerpt=None,  # Missing excerpt!
        is_official_evidence=True,
        outcome=EligibilityStatus.UNKNOWN,
        reason="",
    )
    request = EligibilityAuditRequest(
        opportunity_name="TUM Merit Scholarship",
        student_profile=profile,
        criteria=[criterion],
    )
    response = await agent.audit(request)
    assert response.evaluated_criteria[0].outcome == EligibilityStatus.UNKNOWN
    assert "lacks required source URL or evidence excerpt" in response.evaluated_criteria[0].reason


# --- API Route Tests ---

def test_api_route_eligibility_audit_success():
    payload = {
        "opportunity_name": "TUM International Graduate Fellowship",
        "institution": "Technical University of Munich",
        "student_profile": {
            "name": "Jordan Smith",
            "degree_program": "Bachelor of Technology",
            "field_of_study": "Mechanical Engineering",
            "institution": "University of Delhi",
            "country": "India",
            "academic_stage": "graduate",
            "academic_score": {"score": 3.9, "scale": 4.0},
            "target_destinations": ["Germany"],
            "academic_interests": ["Thermodynamics"],
            "projects_experiences": [],
            "public_profile_urls": [],
        },
        "criteria": [
            {
                "description": "Minimum GPA 3.5 on 4.0 scale",
                "scope": "scholarship",
                "mandatory": True,
                "rule": {
                    "target_field": "academic_score",
                    "operator": ">=",
                    "expected_value": 3.5,
                    "scale": 4.0,
                },
                "source_url": "https://www.tum.de/fellowships",
                "evidence_excerpt": "Applicants must possess a GPA of at least 3.5 / 4.0.",
                "is_official_evidence": True,
                "outcome": "unknown",
                "reason": "",
            }
        ],
        "conflicting_profile_fields": [],
    }
    res = client.post("/api/v1/research/eligibility-audit", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["opportunity_name"] == "TUM International Graduate Fellowship"
    assert data["overall_classification"] == "eligible"
    assert data["scholarship_assessment"]["overall_classification"] == "eligible"
    assert data["evaluated_criteria"][0]["outcome"] == "met"


def test_api_route_eligibility_audit_empty_criteria_rejected():
    payload = {
        "opportunity_name": "TUM International Fellowship",
        "student_profile": {
            "name": "Jordan Smith",
            "academic_score": {"score": 3.9, "scale": 4.0},
        },
        "criteria": [],  # Min length is 1
    }
    res = client.post("/api/v1/research/eligibility-audit", json=payload)
    assert res.status_code == 422
