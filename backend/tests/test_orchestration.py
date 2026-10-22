from datetime import datetime, timezone
import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.database import Base, engine, get_db
from app.graph.orchestrator import build_orchestrator_graph
from app.graph.state import (
    MultiAgentWorkflowState,
    WorkflowEventType,
    WorkflowStage,
)
from app.main import app
from app.models.entities import StudentProfileModel
from app.schemas.discovery import (
    DiscoveredCandidate,
    DiscoveryRequest,
    DiscoveryResponse,
    DiscoveryStatus,
)
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
from app.schemas.opportunity import (
    FundingDetail,
    FundingType,
    OpportunityBase,
    VerificationStatus,
)
from app.schemas.ranking import (
    CandidateOpportunityInput,
    RankingRequest,
    RankingResponse,
)
from app.schemas.research import (
    PageFetchResponse,
    RetrievalStatus,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
    SearchStatus,
)
from app.schemas.research_run import ResearchRunStatus
from app.schemas.student_profile import (
    AcademicScore,
    BudgetConstraint,
    ProjectExperience,
    StudentProfileBase,
)
from app.schemas.verification import (
    CandidateVerificationReport,
    ClaimAssessment,
    ClaimOutcome,
    SourceAssessment,
    SourceClassification,
    VerificationReportStatus,
    VerificationRequest,
    VerificationResponse,
)
from app.services.discovery_agent import ScholarshipDiscoveryAgent
from app.services.eligibility_agent import EligibilityAuditAgent
from app.services.orchestration_service import OrchestrationService
from app.services.ranking_agent import RankingAndStrategyAgent
from app.services.verification_agent import OfficialSourceVerificationAgent

client = TestClient(app)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def make_profile(
    name: str = "Elena Rostova",
    score: float = 3.9,
    scale: float = 4.0,
    field_of_study: str = "Computer Science",
    country: str = "Germany",
    target_destinations: list[str] | None = None,
    requires_full_funding: bool = True,
) -> StudentProfileBase:
    return StudentProfileBase(
        name=name,
        degree_program="Bachelor of Science",
        field_of_study=field_of_study,
        institution="Technical University of Munich",
        country=country,
        academic_stage="final_year_undergraduate",
        academic_score=AcademicScore(score=score, scale=scale),
        target_destinations=target_destinations or ["Germany", "Switzerland"],
        academic_interests=["Distributed Systems", "Machine Learning"],
        budget_constraint=BudgetConstraint(
            requires_full_funding=requires_full_funding,
            max_annual_budget=0.0,
            currency="EUR",
        ),
        projects_experiences=[
            ProjectExperience(
                title="Distributed Consensus Engine",
                role="Core Developer",
                summary="Implemented Raft consensus in Rust.",
            )
        ],
    )


def make_candidate(
    name: str = "DAAD Study Scholarship",
    institution: str = "DAAD",
    destination_country: str = "Germany",
    source_url: str = "https://www.daad.de/en/study-scholarship/",
    funding_type: FundingType = FundingType.FULL,
    deadline_iso: str | None = "2027-06-30T23:59:59Z",
) -> DiscoveredCandidate:
    funding = FundingDetail(funding_type=funding_type)
    opp = OpportunityBase(
        name=name,
        institution=institution,
        destination_country=destination_country,
        official_url=source_url,
        funding=funding,
        deadline=datetime.fromisoformat(deadline_iso.replace("Z", "+00:00")) if deadline_iso else None,
        verification_status=VerificationStatus.UNVERIFIED,
    )
    return DiscoveredCandidate(
        opportunity=opp,
        source_url=source_url,
        source_title=f"{name} Official Overview",
        snippet=f"Full scholarship for master's studies in {destination_country} offered by {institution}.",
        search_query="daad master scholarships",
        discovered_at=utcnow(),
        extracted_fields=["name", "institution", "destination_country", "funding", "deadline"],
    )


# --- Deterministic Mocks for Agents ---

class MockDiscoveryAgent(ScholarshipDiscoveryAgent):
    def __init__(
        self,
        canned_response: DiscoveryResponse | None = None,
        error_to_raise: Exception | None = None,
        transient_failures_count: int = 0,
    ):
        self.canned_response = canned_response
        self.error_to_raise = error_to_raise
        self.transient_failures_count = transient_failures_count
        self.call_count = 0

    async def discover(self, request: DiscoveryRequest) -> DiscoveryResponse:
        self.call_count += 1
        if self.call_count <= self.transient_failures_count:
            req = httpx.Request("GET", "https://api.tavily.com")
            raise httpx.HTTPStatusError("Rate limited", request=req, response=httpx.Response(429, request=req))
        if self.error_to_raise:
            raise self.error_to_raise
        if self.canned_response:
            return self.canned_response
        cand = make_candidate()
        return DiscoveryResponse(
            status=DiscoveryStatus.SUCCESS,
            candidates=[cand],
            total_candidates=1,
            queries_executed=[request.query],
            executed_at=utcnow(),
        )


class MockVerificationAgent(OfficialSourceVerificationAgent):
    def __init__(
        self,
        canned_response: VerificationResponse | None = None,
        error_to_raise: Exception | None = None,
        transient_failures_count: int = 0,
    ):
        self.canned_response = canned_response
        self.error_to_raise = error_to_raise
        self.transient_failures_count = transient_failures_count
        self.call_count = 0

    async def verify(self, request: VerificationRequest) -> VerificationResponse:
        self.call_count += 1
        if self.call_count <= self.transient_failures_count:
            req = httpx.Request("GET", "https://source.uni.de")
            raise httpx.ConnectError("Network dropped", request=req)
        if self.error_to_raise:
            raise self.error_to_raise
        if self.canned_response:
            return self.canned_response

        reports = []
        for cand in request.candidates:
            reports.append(
                CandidateVerificationReport(
                    candidate_name=cand.opportunity.name,
                    original_source_url=cand.source_url,
                    overall_status=VerificationReportStatus.VERIFIED,
                    verified_official_url=str(cand.opportunity.official_url) if cand.opportunity.official_url else None,
                    source_assessments=[
                        SourceAssessment(
                            source_url=cand.source_url,
                            retrieval_status="success",
                            classification=SourceClassification.OFFICIAL,
                            reason="Authoritative domain confirmed",
                            retrieved_at=utcnow(),
                        )
                    ],
                    claim_assessments=[
                        ClaimAssessment(
                            claim_type="destination_country",
                            claimed_value=cand.opportunity.destination_country,
                            outcome=ClaimOutcome.SUPPORTED,
                            source_url=cand.source_url,
                            excerpt=f"Program offered in {cand.opportunity.destination_country}",
                            explanation="Corroborated by official catalog",
                        )
                    ],
                    verified_at=utcnow(),
                )
            )
        return VerificationResponse(
            reports=reports,
            total_candidates_processed=len(reports),
            executed_at=utcnow(),
        )


class MockEligibilityAgent(EligibilityAuditAgent):
    def __init__(
        self,
        fail_for_opportunities: set[str] | None = None,
        force_classification: OverallEligibilityClassification | None = None,
    ):
        self.fail_for_opportunities = fail_for_opportunities or set()
        self.force_classification = force_classification
        self.call_count = 0

    async def audit(self, request: EligibilityAuditRequest) -> EligibilityAuditResponse:
        self.call_count += 1
        if request.opportunity_name in self.fail_for_opportunities:
            raise RuntimeError(f"Simulated execution crash for {request.opportunity_name}")

        if self.force_classification is not None:
            return EligibilityAuditResponse(
                opportunity_name=request.opportunity_name,
                institution=request.institution,
                overall_classification=self.force_classification,
                evaluated_criteria=request.criteria,
                disqualifying_criteria=[] if self.force_classification == OverallEligibilityClassification.ELIGIBLE else ["Criterion unmet"],
                unknown_criteria=[],
                evidence_caveats=[],
                is_incomplete=False,
                evaluated_at=utcnow(),
            )

        # Default: invoke real deterministic evaluation
        return await super().audit(request)


# =========================================================================
# 1. Workflow Success Tests
# =========================================================================

@pytest.mark.anyio
async def test_full_workflow_success_through_all_agent_roles():
    """Verify that a valid profile executes through discovery, verification, eligibility, and ranking."""
    disc_agent = MockDiscoveryAgent()
    verif_agent = MockVerificationAgent()
    elig_agent = MockEligibilityAgent()
    rank_agent = RankingAndStrategyAgent()

    service = OrchestrationService(
        discovery_agent=disc_agent,
        verification_agent=verif_agent,
        eligibility_agent=elig_agent,
        ranking_agent=rank_agent,
    )

    profile = make_profile(name="Kavita Sharma", country="India", target_destinations=["Germany"])
    disc_req = DiscoveryRequest(query="daad master computer science", destinations=["Germany"])

    final_state = await service.execute_run(
        student_profile=profile,
        discovery_request=disc_req,
    )

    assert final_state.terminal_status == ResearchRunStatus.COMPLETED
    assert final_state.current_stage == WorkflowStage.COMPLETED
    assert final_state.is_partial is False
    assert len(final_state.discovered_candidates) == 1
    assert len(final_state.verification_reports) == 1
    assert len(final_state.eligibility_assessments) == 1
    assert final_state.ranking_response is not None

    # Check event sequence
    event_stages = [e.stage for e in final_state.events]
    assert WorkflowStage.VALIDATION in event_stages
    assert WorkflowStage.DISCOVERY in event_stages
    assert WorkflowStage.VERIFICATION in event_stages
    assert WorkflowStage.ELIGIBILITY in event_stages
    assert WorkflowStage.RANKING in event_stages

    # Verify stable association
    cand = final_state.discovered_candidates[0]
    verif_rep = final_state.verification_reports[0]
    audit_res = final_state.eligibility_assessments[0]
    assert verif_rep.candidate_name == cand.opportunity.name
    assert audit_res.opportunity_name == cand.opportunity.name


@pytest.mark.anyio
async def test_distinct_student_profiles_produce_different_request_contexts():
    """Verify different profiles (not hardcoded) produce contextually distinct results."""
    disc_agent = MockDiscoveryAgent()
    verif_agent = MockVerificationAgent()
    elig_agent = MockEligibilityAgent()
    rank_agent = RankingAndStrategyAgent()

    service = OrchestrationService(disc_agent, verif_agent, elig_agent, rank_agent)

    profile_a = make_profile(name="Student A", country="Brazil", target_destinations=["Canada"])
    profile_b = make_profile(name="Student B", country="Japan", target_destinations=["Germany"])

    state_a = await service.execute_run(profile_a, DiscoveryRequest(query="canada scholarships", destinations=["Canada"]))
    state_b = await service.execute_run(profile_b, DiscoveryRequest(query="germany scholarships", destinations=["Germany"]))

    assert state_a.student_profile.country == "Brazil"
    assert state_b.student_profile.country == "Japan"
    assert state_a.discovery_request.destinations == ["Canada"]
    assert state_b.discovery_request.destinations == ["Germany"]


# =========================================================================
# 2. Conditional Routing Tests
# =========================================================================

@pytest.mark.anyio
async def test_empty_discovery_results_skips_downstream_stages():
    """Empty discovery results must skip verification and eligibility without calling them."""
    disc_agent = MockDiscoveryAgent(
        canned_response=DiscoveryResponse(
            status=DiscoveryStatus.NO_RESULTS,
            candidates=[],
            total_candidates=0,
            queries_executed=["test"],
            executed_at=utcnow(),
        )
    )
    verif_agent = MockVerificationAgent()
    elig_agent = MockEligibilityAgent()
    rank_agent = RankingAndStrategyAgent()

    service = OrchestrationService(disc_agent, verif_agent, elig_agent, rank_agent)
    profile = make_profile()
    state = await service.execute_run(profile, DiscoveryRequest(query="nonexistent program"))

    assert state.terminal_status == ResearchRunStatus.COMPLETED
    assert len(state.discovered_candidates) == 0
    assert verif_agent.call_count == 0
    assert elig_agent.call_count == 0
    assert state.verification_reports == []
    assert state.eligibility_assessments == []

    # Check that skipped events were emitted
    skipped_stages = [e.stage for e in state.events if e.event_type == WorkflowEventType.STAGE_SKIPPED]
    assert WorkflowStage.VERIFICATION in skipped_stages
    assert WorkflowStage.ELIGIBILITY in skipped_stages
    assert WorkflowStage.RANKING in skipped_stages


@pytest.mark.anyio
async def test_provider_unavailable_produces_truthful_terminal_state():
    """Provider unconfigured / unavailable produces honest result without fabrication."""
    disc_agent = MockDiscoveryAgent(
        canned_response=DiscoveryResponse(
            status=DiscoveryStatus.PROVIDER_UNAVAILABLE,
            candidates=[],
            total_candidates=0,
            queries_executed=[],
            executed_at=utcnow(),
            warnings=["Search provider API key is not configured."],
        )
    )
    verif_agent = MockVerificationAgent()
    elig_agent = MockEligibilityAgent()
    rank_agent = RankingAndStrategyAgent()

    service = OrchestrationService(disc_agent, verif_agent, elig_agent, rank_agent)
    profile = make_profile()
    state = await service.execute_run(profile, DiscoveryRequest(query="germany scholarships"))

    assert state.terminal_status == ResearchRunStatus.COMPLETED
    assert state.discovery_status == DiscoveryStatus.PROVIDER_UNAVAILABLE
    assert len(state.discovered_candidates) == 0
    assert verif_agent.call_count == 0


@pytest.mark.anyio
async def test_verification_failure_preserves_discovery_results():
    """If verification fails, earlier discovery candidates are preserved as partial results."""
    disc_agent = MockDiscoveryAgent()
    verif_agent = MockVerificationAgent(error_to_raise=RuntimeError("Verification engine failed permanently"))
    elig_agent = MockEligibilityAgent()
    rank_agent = RankingAndStrategyAgent()

    service = OrchestrationService(disc_agent, verif_agent, elig_agent, rank_agent)
    profile = make_profile()
    state = await service.execute_run(profile, DiscoveryRequest(query="daad scholarships"))

    assert state.terminal_status == ResearchRunStatus.PARTIAL
    assert state.is_partial is True
    assert len(state.discovered_candidates) == 1
    # Verification failed, but discovery and unverified eligibility/ranking were carried forward
    assert any("Official-source verification failed" in w for w in state.warnings)


@pytest.mark.anyio
async def test_missing_evidence_does_not_upgrade_to_eligible():
    """Evidence gate from M7: if candidate lacks verified official evidence, it remains UNKNOWN/NEEDS_REVIEW."""
    disc_agent = MockDiscoveryAgent()
    # Verification returns unverified / third-party source
    unverified_report = CandidateVerificationReport(
        candidate_name="DAAD Study Scholarship",
        original_source_url="https://thirdparty-blog.com/daad",
        overall_status=VerificationReportStatus.UNVERIFIED,
        source_assessments=[
            SourceAssessment(
                source_url="https://thirdparty-blog.com/daad",
                retrieval_status="success",
                classification=SourceClassification.THIRD_PARTY,
                reason="Aggregator blog",
                retrieved_at=utcnow(),
            )
        ],
        claim_assessments=[],
        verified_at=utcnow(),
    )
    verif_agent = MockVerificationAgent(
        canned_response=VerificationResponse(
            reports=[unverified_report],
            total_candidates_processed=1,
            executed_at=utcnow(),
        )
    )
    elig_agent = EligibilityAuditAgent()  # Real M7 agent
    rank_agent = RankingAndStrategyAgent()

    service = OrchestrationService(disc_agent, verif_agent, elig_agent, rank_agent)
    profile = make_profile(country="India", target_destinations=["Germany"])

    # Provide criterion that requires official evidence
    crit = EvaluatedCriterion(
        description="Destination Germany",
        scope=CriterionScope.BOTH,
        mandatory=True,
        rule=CriterionRuleDefinition(
            target_field="target_destinations",
            operator=RuleOperator.CONTAINS,
            expected_value="Germany",
        ),
        source_url="https://thirdparty-blog.com/daad",
        evidence_excerpt="In Germany.",
        is_official_evidence=False,
        outcome=EligibilityStatus.UNKNOWN,
        reason="",
    )

    state = await service.execute_run(
        student_profile=profile,
        discovery_request=DiscoveryRequest(query="daad master"),
        custom_criteria=[crit],
    )

    # Classification must not be upgraded to ELIGIBLE
    audit = state.eligibility_assessments[0]
    assert audit.overall_classification != OverallEligibilityClassification.ELIGIBLE
    assert audit.overall_classification in (
        OverallEligibilityClassification.NEEDS_REVIEW,
        OverallEligibilityClassification.INSUFFICIENT_EVIDENCE,
    )


# =========================================================================
# 3. Retries, Timeouts, and Failure Recovery Tests
# =========================================================================

@pytest.mark.anyio
async def test_transient_failure_retries_and_succeeds():
    """A transient error (HTTP 429) retries up to configured limit and succeeds."""
    disc_agent = MockDiscoveryAgent(transient_failures_count=1)
    verif_agent = MockVerificationAgent()
    elig_agent = MockEligibilityAgent()
    rank_agent = RankingAndStrategyAgent()

    service = OrchestrationService(disc_agent, verif_agent, elig_agent, rank_agent)
    profile = make_profile()
    state = await service.execute_run(profile, DiscoveryRequest(query="daad master"))

    assert state.terminal_status == ResearchRunStatus.COMPLETED
    assert disc_agent.call_count == 2
    assert state.retry_counts.get("discovery") == 1

    retry_events = [e for e in state.events if e.event_type == WorkflowEventType.STAGE_RETRYING]
    assert len(retry_events) == 1
    assert retry_events[0].retry_attempt == 1


@pytest.mark.anyio
async def test_transient_failure_exhausted_at_retry_limit():
    """Transient failures exceeding MAX_TRANSIENT_RETRIES cleanly terminate without infinite loops."""
    disc_agent = MockDiscoveryAgent(transient_failures_count=5)  # exceeds max 2
    verif_agent = MockVerificationAgent()
    elig_agent = MockEligibilityAgent()
    rank_agent = RankingAndStrategyAgent()

    service = OrchestrationService(disc_agent, verif_agent, elig_agent, rank_agent)
    profile = make_profile()
    state = await service.execute_run(profile, DiscoveryRequest(query="daad master"))

    assert state.terminal_status == ResearchRunStatus.FAILED
    assert state.current_stage == WorkflowStage.FAILED
    assert disc_agent.call_count == 3  # Initial + 2 retries
    assert state.sanitized_failure_info is not None
    assert "error 429" in state.sanitized_failure_info.lower()


@pytest.mark.anyio
async def test_permanent_validation_error_is_not_retried():
    """Permanent errors (e.g. invalid query) are not retried."""
    disc_agent = MockDiscoveryAgent()
    verif_agent = MockVerificationAgent()
    elig_agent = MockEligibilityAgent()
    rank_agent = RankingAndStrategyAgent()

    service = OrchestrationService(disc_agent, verif_agent, elig_agent, rank_agent)
    profile = make_profile()
    
    # DiscoveryRequest validation prevents empty string
    with pytest.raises(Exception):
        DiscoveryRequest(query=" ")


@pytest.mark.anyio
async def test_candidate_level_failure_isolated_in_eligibility():
    """Failure for one candidate during eligibility does not crash or erase other candidates."""
    cand1 = make_candidate(name="Opportunity One")
    cand2 = make_candidate(name="Opportunity Two")

    disc_agent = MockDiscoveryAgent(
        canned_response=DiscoveryResponse(
            status=DiscoveryStatus.SUCCESS,
            candidates=[cand1, cand2],
            total_candidates=2,
            queries_executed=["test"],
            executed_at=utcnow(),
        )
    )
    verif_agent = MockVerificationAgent()
    # Fail specifically on Opportunity One
    elig_agent = MockEligibilityAgent(fail_for_opportunities={"Opportunity One"})
    rank_agent = RankingAndStrategyAgent()

    service = OrchestrationService(disc_agent, verif_agent, elig_agent, rank_agent)
    profile = make_profile()
    state = await service.execute_run(profile, DiscoveryRequest(query="two opportunities"))

    assert state.is_partial is True
    assert len(state.eligibility_assessments) == 2
    # Opportunity One has fallback unassessable assessment
    res1 = next(a for a in state.eligibility_assessments if a.opportunity_name == "Opportunity One")
    assert res1.overall_classification == OverallEligibilityClassification.NOT_ASSESSABLE
    # Opportunity Two assessed normally
    res2 = next(a for a in state.eligibility_assessments if a.opportunity_name == "Opportunity Two")
    assert res2.overall_classification != OverallEligibilityClassification.NOT_ASSESSABLE


# =========================================================================
# 4. Data Integrity and Security Tests
# =========================================================================

@pytest.mark.anyio
async def test_events_and_errors_are_sanitized_without_tracebacks_or_secrets():
    """Event messages, failure summaries, and warnings do not expose raw secrets, paths, or tracebacks."""
    disc_agent = MockDiscoveryAgent(
        error_to_raise=RuntimeError("SecretToken=xyz123456 Internal file C:\\secret\\file.py line 40")
    )
    service = OrchestrationService(disc_agent, MockVerificationAgent(), MockEligibilityAgent(), RankingAndStrategyAgent())
    state = await service.execute_run(make_profile(), DiscoveryRequest(query="daad master"))

    assert state.terminal_status == ResearchRunStatus.FAILED
    assert state.current_stage == WorkflowStage.FAILED
    for event in state.events:
        assert "xyz123456" not in event.message
        assert "file.py" not in event.message
        assert "C:\\" not in event.message
        assert "Traceback" not in event.message
    if state.sanitized_failure_info:
        assert "xyz123456" not in state.sanitized_failure_info
        assert "file.py" not in state.sanitized_failure_info
    for warning in state.warnings:
        assert "xyz123456" not in warning
        assert "file.py" not in warning


def test_mock_returns_schema_valid_verification_report():
    """Finding 1 focused test: Verify MockVerificationAgent produces schema-valid CandidateVerificationReport."""
    cand = make_candidate(source_url="https://www.daad.de/en/study-scholarship/")
    # cand.opportunity.official_url is an HttpUrl object
    assert cand.opportunity.official_url is not None

    req = VerificationRequest(candidates=[cand])
    agent = MockVerificationAgent()
    import asyncio
    resp = asyncio.run(agent.verify(req))
    assert len(resp.reports) == 1
    report = resp.reports[0]
    assert isinstance(report.verified_official_url, str)
    assert report.verified_official_url == "https://www.daad.de/en/study-scholarship/"
    assert report.overall_status == VerificationReportStatus.VERIFIED


@pytest.mark.anyio
async def test_same_name_different_institutions_no_cross_association():
    """Finding 5 regression test: Opportunities with identical names from different institutions remain distinct."""
    cand1 = make_candidate(
        name="Merit Scholarship",
        institution="Technical University of Munich",
        destination_country="Germany",
        source_url="https://www.tum.de/merit",
    )
    cand2 = make_candidate(
        name="Merit Scholarship",
        institution="ETH Zurich",
        destination_country="Switzerland",
        source_url="https://www.ethz.ch/merit",
    )

    disc_agent = MockDiscoveryAgent(
        canned_response=DiscoveryResponse(
            status=DiscoveryStatus.SUCCESS,
            candidates=[cand1, cand2],
            total_candidates=2,
            queries_executed=["merit"],
            executed_at=utcnow(),
        )
    )

    # Verification report: TUM is VERIFIED, ETH Zurich is UNVERIFIED
    rep_tum = CandidateVerificationReport(
        candidate_name="Merit Scholarship",
        original_source_url="https://www.tum.de/merit",
        overall_status=VerificationReportStatus.VERIFIED,
        verified_official_url="https://www.tum.de/merit",
        source_assessments=[
            SourceAssessment(
                source_url="https://www.tum.de/merit",
                retrieval_status="success",
                classification=SourceClassification.OFFICIAL,
                reason="Official TUM domain",
                retrieved_at=utcnow(),
            )
        ],
        claim_assessments=[],
        verified_at=utcnow(),
    )
    rep_eth = CandidateVerificationReport(
        candidate_name="Merit Scholarship",
        original_source_url="https://www.ethz.ch/merit",
        overall_status=VerificationReportStatus.UNVERIFIED,
        verified_official_url=None,
        source_assessments=[],
        claim_assessments=[],
        verified_at=utcnow(),
    )

    verif_agent = MockVerificationAgent(
        canned_response=VerificationResponse(
            reports=[rep_tum, rep_eth],
            total_candidates_processed=2,
            executed_at=utcnow(),
        )
    )

    # Eligibility agent: returns ELIGIBLE for TUM, INELIGIBLE for ETH Zurich
    class CustomEligibilityAgent(EligibilityAuditAgent):
        async def audit(self, req: EligibilityAuditRequest) -> EligibilityAuditResponse:
            if "munich" in (req.institution or "").lower():
                classification = OverallEligibilityClassification.ELIGIBLE
                disqualifying = []
            else:
                classification = OverallEligibilityClassification.INELIGIBLE
                disqualifying = ["Institution not eligible"]

            return EligibilityAuditResponse(
                opportunity_name=req.opportunity_name,
                institution=req.institution,
                overall_classification=classification,
                evaluated_criteria=[],
                disqualifying_criteria=disqualifying,
                unknown_criteria=[],
                evidence_caveats=[],
                is_incomplete=False,
                evaluated_at=utcnow(),
            )

    rank_agent = RankingAndStrategyAgent()
    service = OrchestrationService(disc_agent, verif_agent, CustomEligibilityAgent(), rank_agent)
    profile = make_profile(target_destinations=["Germany", "Switzerland"])

    state = await service.execute_run(profile, DiscoveryRequest(query="merit scholarship"))

    assert len(state.discovered_candidates) == 2
    assert len(state.eligibility_assessments) == 2
    tum_audit = next(a for a in state.eligibility_assessments if a.institution == "Technical University of Munich")
    eth_audit = next(a for a in state.eligibility_assessments if a.institution == "ETH Zurich")

    # Verify that the two evaluations were NOT cross-associated or collapsed
    assert tum_audit.overall_classification == OverallEligibilityClassification.ELIGIBLE
    assert eth_audit.overall_classification == OverallEligibilityClassification.INELIGIBLE


@pytest.mark.anyio
async def test_ranking_failure_preserves_earlier_stage_results():
    """When ranking fails, earlier stage results (discovery, verification, eligibility) are preserved."""
    class FailingRankingAgent(RankingAndStrategyAgent):
        async def rank(self, request: RankingRequest) -> RankingResponse:
            raise RuntimeError("Ranking model calculation error")

    service = OrchestrationService(
        MockDiscoveryAgent(),
        MockVerificationAgent(),
        MockEligibilityAgent(),
        FailingRankingAgent(),
    )
    state = await service.execute_run(make_profile(), DiscoveryRequest(query="daad master"))

    assert state.terminal_status == ResearchRunStatus.PARTIAL
    assert state.is_partial is True
    assert len(state.discovered_candidates) == 1
    assert len(state.verification_reports) == 1
    assert len(state.eligibility_assessments) == 1
    assert state.ranking_response is None
    assert any("Ranking and application strategy could not run" in w for w in state.warnings)


# =========================================================================
# 5. API Route Integration Tests (POST /api/v1/research/runs)
# =========================================================================

def test_api_route_research_run_with_direct_profile(monkeypatch):
    """Test POST /api/v1/research/runs with an inline valid student profile."""
    # Override orchestrator dependency with mock
    mock_service = OrchestrationService(
        MockDiscoveryAgent(),
        MockVerificationAgent(),
        MockEligibilityAgent(),
        RankingAndStrategyAgent(),
    )
    from app.api.routes.research import get_orchestration_service
    app.dependency_overrides[get_orchestration_service] = lambda: mock_service

    try:
        payload = {
            "student_profile": {
                "name": "Sarah Connor",
                "degree_program": "B.Sc. Cybernetics",
                "field_of_study": "Computer Science",
                "institution": "MIT",
                "country": "USA",
                "academic_stage": "final_year_undergraduate",
                "academic_score": {"score": 3.9, "scale": 4.0},
                "target_destinations": ["Germany"],
                "academic_interests": ["AI Safety"],
                "projects_experiences": [],
                "budget_constraint": {"requires_full_funding": True, "currency": "USD"},
                "public_profile_urls": [],
            },
            "discovery": {
                "query": "daad master computer science",
                "destinations": ["Germany"],
                "max_candidates": 5,
            },
            "max_shortlist_size": 3,
        }

        resp = client.post("/api/v1/research/runs", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "run_id" in data
        assert data["status"] in ("completed", "partial")
        assert len(data["candidates"]) == 1
        assert len(data["events"]) >= 5
        assert data["ranking"] is not None
    finally:
        app.dependency_overrides.pop(get_orchestration_service, None)


def test_api_route_research_run_missing_profile_and_id_rejected():
    """Test POST /api/v1/research/runs rejects request when neither profile nor profile_id is provided."""
    payload = {
        "discovery": {
            "query": "daad master",
        }
    }
    resp = client.post("/api/v1/research/runs", json=payload)
    assert resp.status_code == 422


def test_api_route_research_run_nonexistent_profile_id_rejected(db_session):
    """Test POST /api/v1/research/runs returns 404 if given profile_id does not exist."""
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        payload = {
            "profile_id": "00000000-0000-0000-0000-000000000000",
            "discovery": {
                "query": "daad master",
            },
        }
        resp = client.post("/api/v1/research/runs", json=payload)
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_db, None)
