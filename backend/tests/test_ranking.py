from datetime import datetime, timezone
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
    CandidateOpportunityInput,
    DeadlineFeasibilityStatus,
    RankingRequest,
    RankingResponse,
)
from app.schemas.student_profile import (
    AcademicScore,
    BudgetConstraint,
    ProjectExperience,
    StudentProfileBase,
)
from app.services.ranking_agent import COMPONENT_WEIGHTS, RankingAndStrategyAgent


client = TestClient(app)


def make_sample_profile(
    score: float = 3.8,
    scale: float | None = 4.0,
    field_of_study: str | None = "Computer Science",
    country: str | None = "India",
    target_destinations: list[str] | None = None,
    requires_full_funding: bool | None = None,
    projects: list[ProjectExperience] | None = None,
) -> StudentProfileBase:
    return StudentProfileBase(
        name="Taylor Student",
        degree_program="Bachelor of Science",
        field_of_study=field_of_study,
        institution="National Tech Institute",
        country=country,
        academic_stage="final_year_undergraduate",
        academic_score=AcademicScore(score=score, scale=scale) if score is not None else None,
        target_destinations=target_destinations or ["Germany", "Canada"],
        academic_interests=["Artificial Intelligence", "Robotics"],
        budget_constraint=BudgetConstraint(
            requires_full_funding=requires_full_funding,
            max_annual_budget=5000.0 if not requires_full_funding else 0.0,
            currency="USD",
        ) if requires_full_funding is not None else None,
        projects_experiences=projects or [
            ProjectExperience(
                title="Autonomous Mobile Robot",
                role="Lead Programmer",
                summary="Built ROS2-based mapping and navigation system.",
                technologies=["ROS2", "Python", "Robotics"],
            )
        ],
    )


def make_sample_opportunity(
    name: str = "TUM Excellence Master Fellowship",
    institution: str = "Technical University of Munich",
    destination_country: str = "Germany",
    funding_type: FundingType = FundingType.FULL,
    deadline: datetime | None = datetime(2026, 12, 1, 0, 0, tzinfo=timezone.utc),
) -> OpportunityBase:
    return OpportunityBase(
        name=name,
        institution=institution,
        destination_country=destination_country,
        official_url="https://www.tum.de/fellowships",
        funding=FundingDetail(funding_type=funding_type, amount=12000.0, currency="EUR", period="per_year"),
        deadline=deadline,
        verification_status=VerificationStatus.VERIFIED,
    )


# --- 1. Eligibility Gating Tests ---

@pytest.mark.anyio
async def test_eligible_candidate_enters_recommended_shortlist():
    agent = RankingAndStrategyAgent()
    profile = make_sample_profile()
    opp = make_sample_opportunity()
    cand = CandidateOpportunityInput(
        opportunity=opp,
        eligibility_classification=OverallEligibilityClassification.ELIGIBLE,
    )
    request = RankingRequest(
        student_profile=profile,
        candidates=[cand],
        reference_date=datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc),
    )
    response = await agent.rank(request)
    assert len(response.recommended_shortlist) == 1
    assert response.recommended_shortlist[0].opportunity.name == opp.name
    assert response.recommended_shortlist[0].rank == 1
    assert response.recommended_shortlist[0].eligibility_classification == OverallEligibilityClassification.ELIGIBLE
    assert len(response.excluded_opportunities) == 0


@pytest.mark.anyio
async def test_ineligible_candidate_excluded_despite_high_fit_score():
    agent = RankingAndStrategyAgent()
    profile = make_sample_profile(score=4.0, scale=4.0)  # perfect GPA and fit
    opp = make_sample_opportunity()
    cand = CandidateOpportunityInput(
        opportunity=opp,
        eligibility_classification=OverallEligibilityClassification.INELIGIBLE,
        disqualifying_criteria=["Must hold EU citizenship (student is citizen of India)."],
    )
    request = RankingRequest(
        student_profile=profile,
        candidates=[cand],
        reference_date=datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc),
    )
    response = await agent.rank(request)
    # INELIGIBLE must NEVER be in recommended shortlist
    assert len(response.recommended_shortlist) == 0
    assert len(response.excluded_opportunities) == 1
    excl = response.excluded_opportunities[0]
    assert excl.opportunity_name == opp.name
    assert "Eligibility failure" in excl.exclusion_reason
    assert "EU citizenship" in excl.disqualifying_criteria[0]


@pytest.mark.anyio
async def test_needs_review_candidate_surfaced_in_review_not_recommended():
    agent = RankingAndStrategyAgent()
    profile = make_sample_profile()
    opp = make_sample_opportunity()
    cand = CandidateOpportunityInput(
        opportunity=opp,
        eligibility_classification=OverallEligibilityClassification.NEEDS_REVIEW,
        unknown_criteria=["Language proficiency certificate (IELTS/TOEFL) verification needed."],
    )
    request = RankingRequest(
        student_profile=profile,
        candidates=[cand],
        reference_date=datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc),
    )
    response = await agent.rank(request)
    assert len(response.recommended_shortlist) == 0
    assert len(response.needs_review_shortlist) == 1
    review_item = response.needs_review_shortlist[0]
    assert review_item.eligibility_classification == OverallEligibilityClassification.NEEDS_REVIEW
    assert "Language proficiency" in review_item.unknown_criteria[0]


@pytest.mark.anyio
async def test_all_ineligible_yields_valid_empty_recommended_shortlist():
    agent = RankingAndStrategyAgent()
    profile = make_sample_profile()
    cand1 = CandidateOpportunityInput(
        opportunity=make_sample_opportunity(name="Award A"),
        eligibility_classification=OverallEligibilityClassification.INELIGIBLE,
        disqualifying_criteria=["Ineligible criterion 1"],
    )
    cand2 = CandidateOpportunityInput(
        opportunity=make_sample_opportunity(name="Award B"),
        eligibility_classification=OverallEligibilityClassification.INELIGIBLE,
        disqualifying_criteria=["Ineligible criterion 2"],
    )
    request = RankingRequest(student_profile=profile, candidates=[cand1, cand2])
    response = await agent.rank(request)
    assert len(response.recommended_shortlist) == 0
    assert len(response.excluded_opportunities) == 2


# --- 2. Deterministic Scoring & Weights Tests ---

def test_component_weights_sum_to_one():
    total = sum(COMPONENT_WEIGHTS.values())
    assert abs(total - 1.0) < 0.0001
    assert COMPONENT_WEIGHTS["academic_fit"] == 0.35
    assert COMPONENT_WEIGHTS["experience_fit"] == 0.25
    assert COMPONENT_WEIGHTS["funding_fit"] == 0.25
    assert COMPONENT_WEIGHTS["deadline_fit"] == 0.15


@pytest.mark.anyio
async def test_identical_inputs_produce_identical_scores():
    agent = RankingAndStrategyAgent()
    profile = make_sample_profile()
    opp1 = make_sample_opportunity(name="Opportunity Alpha")
    opp2 = make_sample_opportunity(name="Opportunity Beta")
    cand1 = CandidateOpportunityInput(opportunity=opp1, eligibility_classification=OverallEligibilityClassification.ELIGIBLE)
    cand2 = CandidateOpportunityInput(opportunity=opp2, eligibility_classification=OverallEligibilityClassification.ELIGIBLE)
    
    req1 = RankingRequest(
        student_profile=profile,
        candidates=[cand1, cand2],
        reference_date=datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc),
    )
    req2 = RankingRequest(
        student_profile=profile,
        candidates=[cand1, cand2],
        reference_date=datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc),
    )
    res1 = await agent.rank(req1)
    res2 = await agent.rank(req2)
    assert res1.recommended_shortlist[0].fit_score == res2.recommended_shortlist[0].fit_score
    assert [x.opportunity.name for x in res1.recommended_shortlist] == [x.opportunity.name for x in res2.recommended_shortlist]


@pytest.mark.anyio
async def test_partial_score_coverage_tracking():
    agent = RankingAndStrategyAgent()
    # Profile with missing academic score and missing experience
    profile = StudentProfileBase(
        name="Empty Profile Student",
        target_destinations=["Germany"],
    )
    # Opportunity with unknown funding and unverified deadline
    opp = OpportunityBase(
        name="Minimal Award",
        institution="Berlin University",
        destination_country="Germany",
        funding=None,
        deadline=None,
    )
    cand = CandidateOpportunityInput(
        opportunity=opp,
        eligibility_classification=OverallEligibilityClassification.ELIGIBLE,
    )
    request = RankingRequest(
        student_profile=profile,
        candidates=[cand],
        reference_date=datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc),
    )
    response = await agent.rank(request)
    assert len(response.recommended_shortlist) == 1
    item = response.recommended_shortlist[0]
    # Funding and deadline are unknown; coverage should be < 100%
    assert item.score_coverage_pct < 100.0
    assert item.score_components["funding_fit"].is_known is False
    assert item.score_components["deadline_fit"].is_known is False


# --- 3. Deadlines & Feasibility Tests ---

@pytest.mark.anyio
async def test_confirmed_closed_deadline_is_excluded():
    agent = RankingAndStrategyAgent()
    profile = make_sample_profile()
    opp = make_sample_opportunity(deadline=datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc))
    cand = CandidateOpportunityInput(
        opportunity=opp,
        eligibility_classification=OverallEligibilityClassification.ELIGIBLE,
    )
    # Reference date is AFTER the deadline -> Closed!
    request = RankingRequest(
        student_profile=profile,
        candidates=[cand],
        reference_date=datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc),
    )
    response = await agent.rank(request)
    assert len(response.recommended_shortlist) == 0
    assert len(response.excluded_opportunities) == 1
    excl = response.excluded_opportunities[0]
    assert excl.deadline_feasibility == DeadlineFeasibilityStatus.CLOSED
    assert "Application deadline closed" in excl.exclusion_reason


@pytest.mark.anyio
async def test_closing_soon_deadline_triggers_critical_action():
    agent = RankingAndStrategyAgent()
    profile = make_sample_profile()
    # Deadline is 5 days after reference date
    opp = make_sample_opportunity(deadline=datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc))
    cand = CandidateOpportunityInput(
        opportunity=opp,
        eligibility_classification=OverallEligibilityClassification.ELIGIBLE,
    )
    request = RankingRequest(
        student_profile=profile,
        candidates=[cand],
        reference_date=datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc),
    )
    response = await agent.rank(request)
    assert len(response.recommended_shortlist) == 1
    item = response.recommended_shortlist[0]
    assert item.deadline_feasibility == DeadlineFeasibilityStatus.CLOSING_SOON
    # High/Critical priority action should exist
    critical_actions = [a for a in response.prioritized_action_plan if a.priority == ActionItemPriority.CRITICAL]
    assert len(critical_actions) >= 1
    assert "Expedite" in critical_actions[0].title


# --- 4. Funding Alignment Tests ---

@pytest.mark.anyio
async def test_full_funding_matches_student_full_funding_constraint():
    agent = RankingAndStrategyAgent()
    profile = make_sample_profile(requires_full_funding=True)
    opp = make_sample_opportunity(funding_type=FundingType.FULL)
    cand = CandidateOpportunityInput(opportunity=opp, eligibility_classification=OverallEligibilityClassification.ELIGIBLE)
    request = RankingRequest(
        student_profile=profile,
        candidates=[cand],
        reference_date=datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc),
    )
    response = await agent.rank(request)
    item = response.recommended_shortlist[0]
    assert item.score_components["funding_fit"].raw_score == 100.0


@pytest.mark.anyio
async def test_partial_funding_conflicts_with_full_funding_constraint():
    agent = RankingAndStrategyAgent()
    profile = make_sample_profile(requires_full_funding=True)
    opp = make_sample_opportunity(funding_type=FundingType.PARTIAL)
    cand = CandidateOpportunityInput(opportunity=opp, eligibility_classification=OverallEligibilityClassification.ELIGIBLE)
    request = RankingRequest(
        student_profile=profile,
        candidates=[cand],
        reference_date=datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc),
    )
    response = await agent.rank(request)
    item = response.recommended_shortlist[0]
    assert item.score_components["funding_fit"].raw_score == 40.0
    assert any("Student requires full funding" in g for g in item.main_gaps)


# --- 5. Shortlist Bounding & Deduplication Tests ---

@pytest.mark.anyio
async def test_max_shortlist_size_enforced():
    agent = RankingAndStrategyAgent()
    profile = make_sample_profile()
    candidates = [
        CandidateOpportunityInput(
            opportunity=make_sample_opportunity(name=f"Scholarship #{i}"),
            eligibility_classification=OverallEligibilityClassification.ELIGIBLE,
        )
        for i in range(1, 8)
    ]
    request = RankingRequest(
        student_profile=profile,
        candidates=candidates,
        max_shortlist_size=3,
        reference_date=datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc),
    )
    response = await agent.rank(request)
    assert len(response.recommended_shortlist) == 3
    assert [item.rank for item in response.recommended_shortlist] == [1, 2, 3]


@pytest.mark.anyio
async def test_duplicate_candidate_opportunities_skipped():
    agent = RankingAndStrategyAgent()
    profile = make_sample_profile()
    opp1 = make_sample_opportunity(name="DAAD Master Fellowship", institution="DAAD")
    opp2 = make_sample_opportunity(name="DAAD Master Fellowship", institution="DAAD")  # Duplicate!
    cand1 = CandidateOpportunityInput(opportunity=opp1, eligibility_classification=OverallEligibilityClassification.ELIGIBLE)
    cand2 = CandidateOpportunityInput(opportunity=opp2, eligibility_classification=OverallEligibilityClassification.ELIGIBLE)
    request = RankingRequest(
        student_profile=profile,
        candidates=[cand1, cand2],
        reference_date=datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc),
    )
    response = await agent.rank(request)
    assert len(response.recommended_shortlist) == 1
    assert any("Duplicate opportunity" in w for w in response.warnings)


# --- 6. API Route Integration Tests ---

def test_api_route_rank_endpoint_success():
    payload = {
        "student_profile": {
            "name": "Jordan Smith",
            "degree_program": "B.Tech Computer Science",
            "field_of_study": "Computer Science",
            "institution": "IIT Delhi",
            "country": "India",
            "academic_stage": "final_year_undergraduate",
            "academic_score": {"score": 3.9, "scale": 4.0},
            "target_destinations": ["Germany"],
            "academic_interests": ["Machine Learning"],
            "projects_experiences": [],
            "public_profile_urls": [],
        },
        "candidates": [
            {
                "opportunity": {
                    "name": "DAAD Postgraduate Scholarship",
                    "institution": "DAAD Germany",
                    "destination_country": "Germany",
                    "official_url": "https://www.daad.de/pg",
                    "funding": {"funding_type": "full", "amount": 10000.0, "currency": "EUR"},
                    "deadline": "2026-11-30T00:00:00Z",
                    "verification_status": "verified",
                },
                "eligibility_classification": "eligible",
                "disqualifying_criteria": [],
                "unknown_criteria": [],
                "evidence_caveats": [],
            }
        ],
        "max_shortlist_size": 5,
        "reference_date": "2026-10-01T00:00:00Z",
    }
    res = client.post("/api/v1/research/rank", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "recommended_shortlist" in data
    assert len(data["recommended_shortlist"]) == 1
    assert data["recommended_shortlist"][0]["rank"] == 1
    assert data["recommended_shortlist"][0]["opportunity"]["name"] == "DAAD Postgraduate Scholarship"
    assert "configured_weights" in data
    assert "disclaimer" in data


def test_api_route_rank_endpoint_rejects_empty_candidates():
    payload = {
        "student_profile": {
            "name": "Jordan Smith",
        },
        "candidates": [],  # Min length 1
    }
    res = client.post("/api/v1/research/rank", json=payload)
    assert res.status_code == 422


# --- Regression Tests for Academic Score & Scale Grounding ---

@pytest.mark.anyio
async def test_academic_score_missing_scale_does_not_fabricate_four_scale_or_ratio():
    agent = RankingAndStrategyAgent()
    # Score 9.01 without scale (e.g., 10-point scale)
    profile = make_sample_profile(score=9.01, scale=None)
    opp = make_sample_opportunity()
    cand = CandidateOpportunityInput(
        opportunity=opp,
        eligibility_classification=OverallEligibilityClassification.ELIGIBLE,
    )
    request = RankingRequest(
        student_profile=profile,
        candidates=[cand],
        reference_date=datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc),
    )
    response = await agent.rank(request)
    assert len(response.recommended_shortlist) == 1
    item = response.recommended_shortlist[0]
    strengths_joined = " ".join(item.main_strengths)
    gaps_joined = " ".join(item.main_gaps)

    # Must NOT claim 9.01/4.0 or fabricated 100%
    assert "9.01/4.0" not in strengths_joined
    assert "100%" not in strengths_joined
    # Must report documented score with unstated scale
    assert "9.01" in strengths_joined
    assert "grading scale unstated" in strengths_joined


@pytest.mark.anyio
async def test_academic_score_valid_explicit_scale_preserved():
    agent = RankingAndStrategyAgent()
    # Explicit 9.01 out of 10.0 scale
    profile = make_sample_profile(score=9.01, scale=10.0)
    opp = make_sample_opportunity()
    cand = CandidateOpportunityInput(
        opportunity=opp,
        eligibility_classification=OverallEligibilityClassification.ELIGIBLE,
    )
    request = RankingRequest(
        student_profile=profile,
        candidates=[cand],
        reference_date=datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc),
    )
    response = await agent.rank(request)
    assert len(response.recommended_shortlist) == 1
    item = response.recommended_shortlist[0]
    strengths_joined = " ".join(item.main_strengths)

    # Preserves explicit scale and accurate ratio (90%)
    assert "9.01/10.0 (90%)" in strengths_joined


@pytest.mark.anyio
async def test_academic_score_inconsistent_scale_score_exceeds_scale():
    agent = RankingAndStrategyAgent()
    # Erroneous input: score 5.0 on scale 4.0
    profile = make_sample_profile(score=5.0, scale=4.0)
    opp = make_sample_opportunity()
    cand = CandidateOpportunityInput(
        opportunity=opp,
        eligibility_classification=OverallEligibilityClassification.ELIGIBLE,
    )
    request = RankingRequest(
        student_profile=profile,
        candidates=[cand],
        reference_date=datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc),
    )
    response = await agent.rank(request)
    assert len(response.recommended_shortlist) == 1
    item = response.recommended_shortlist[0]
    strengths_joined = " ".join(item.main_strengths)
    gaps_joined = " ".join(item.main_gaps)

    # Must NOT emit invalid fraction in strengths
    assert "5.0/4.0" not in strengths_joined
    # Must identify gap requiring transcript verification
    assert "exceeds stated scale" in gaps_joined
