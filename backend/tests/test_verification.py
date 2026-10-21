import datetime
from datetime import timezone
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.discovery import DiscoveredCandidate, DiscoveryRequest
from app.schemas.opportunity import (
    FundingDetail,
    FundingType,
    OpportunityBase,
    VerificationStatus,
)
from app.schemas.research import (
    PageFetchResponse,
    RetrievalStatus,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
    SearchStatus,
)
from app.schemas.verification import (
    ClaimOutcome,
    SourceClassification,
    VerificationReportStatus,
    VerificationRequest,
)
from app.services.page_fetcher import PageFetcher
from app.services.search_provider import SearchProvider
from app.services.verification_agent import OfficialSourceVerificationAgent

client = TestClient(app)


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(timezone.utc)


class FakePageFetcher(PageFetcher):
    """Deterministic fake page fetcher returning canned HTML responses by URL."""

    def __init__(self, pages: dict[str, PageFetchResponse] | None = None):
        self.pages = pages or {}
        self.fetch_history: list[str] = []

    async def fetch(self, url: str, max_length: int | None = None) -> PageFetchResponse:
        self.fetch_history.append(url)
        clean = url.strip()
        if clean in self.pages:
            return self.pages[clean]

        return PageFetchResponse(
            status=RetrievalStatus.SUCCESS,
            url=url,
            final_url=url,
            title="Default Title",
            extracted_text="Default page body with general scholarship information.",
            retrieved_at=utcnow(),
        )


class FakeSearchProvider(SearchProvider):
    """Deterministic fake search provider for official source discovery."""

    def __init__(
        self,
        canned_responses: dict[str, SearchResponse] | None = None,
        default_status: SearchStatus = SearchStatus.SUCCESS,
        default_results: list[SearchResultItem] | None = None,
    ):
        self.canned_responses = canned_responses or {}
        self.default_status = default_status
        self.default_results = default_results or []
        self.call_history: list[SearchRequest] = []

    async def search(self, request: SearchRequest) -> SearchResponse:
        self.call_history.append(request)
        if request.query in self.canned_responses:
            return self.canned_responses[request.query]

        return SearchResponse(
            status=self.default_status,
            query=request.query,
            results=self.default_results,
            total_results=len(self.default_results),
            retrieved_at=utcnow(),
        )


def make_sample_candidate(
    name: str = "DAAD Helmut-Schmidt-Programme",
    institution: str = "DAAD",
    destination_country: str = "Germany",
    source_url: str = "https://www.daad.de/en/scholarships/",
    funding_type: FundingType = FundingType.FULL,
    deadline_iso: str | None = None,
) -> DiscoveredCandidate:
    """Helper to create a valid DiscoveredCandidate instance."""
    funding = (
        FundingDetail(funding_type=funding_type)
        if funding_type != FundingType.UNKNOWN
        else None
    )
    opp = OpportunityBase(
        name=name,
        institution=institution,
        destination_country=destination_country,
        official_url=source_url,
        funding=funding,
        deadline=datetime.datetime.fromisoformat(deadline_iso) if deadline_iso else None,
        verification_status=VerificationStatus.UNVERIFIED,
    )
    return DiscoveredCandidate(
        opportunity=opp,
        source_url=source_url,
        source_title=name,
        snippet="Snippet describing the scholarship",
        search_query="test search query",
        discovered_at=utcnow(),
    )


# ==============================================================================
# Unit & Functional Tests for OfficialSourceVerificationAgent
# ==============================================================================

@pytest.mark.anyio
async def test_candidate_original_source_is_official_and_supports_claims():
    """Verify that an official institutional source is directly assessed and supports claims."""
    url = "https://www.daad.de/en/study-and-research-in-germany/scholarships/"
    text = (
        "Welcome to the DAAD Helmut-Schmidt-Programme Master Scholarships. "
        "This program is designed for postgraduate study in Germany. "
        "The scholarship is fully funded covering monthly stipends and tuition fees. "
        "Application deadline: 31 July 2026. "
        "General eligibility criteria: Bachelor degree with above-average grades."
    )
    fake_fetcher = FakePageFetcher({
        url: PageFetchResponse(
            status=RetrievalStatus.SUCCESS,
            url=url,
            final_url=url,
            title="DAAD Helmut-Schmidt Scholarships",
            extracted_text=text,
            retrieved_at=utcnow(),
        )
    })
    fake_provider = FakeSearchProvider()
    agent = OfficialSourceVerificationAgent(page_fetcher=fake_fetcher, search_provider=fake_provider)

    candidate = make_sample_candidate(source_url=url, deadline_iso="2026-07-31T00:00:00+00:00")
    req = VerificationRequest(candidates=[candidate])
    resp = await agent.verify(req)

    assert len(resp.reports) == 1
    report = resp.reports[0]
    assert report.overall_status == VerificationReportStatus.VERIFIED
    assert report.verified_official_url == url
    assert len(report.source_assessments) == 1
    assert report.source_assessments[0].classification == SourceClassification.OFFICIAL
    assert not report.source_assessments[0].is_discovered_official_source

    # Check claims
    claim_types = {c.claim_type: c for c in report.claim_assessments}
    assert claim_types["opportunity_name"].outcome == ClaimOutcome.SUPPORTED
    assert claim_types["institution"].outcome == ClaimOutcome.SUPPORTED
    assert claim_types["destination_country"].outcome == ClaimOutcome.SUPPORTED
    assert claim_types["funding"].outcome == ClaimOutcome.SUPPORTED
    assert "fully funded" in claim_types["funding"].excerpt.lower()
    assert claim_types["deadline"].outcome == ClaimOutcome.SUPPORTED
    assert "31 July 2026" in claim_types["deadline"].excerpt
    assert claim_types["eligibility_requirements"].outcome == ClaimOutcome.SUPPORTED

    # No secondary search call was made because the initial source was already official
    assert len(fake_provider.call_history) == 0


@pytest.mark.anyio
async def test_third_party_discovery_leads_to_corroborating_official_source():
    """Verify that a third-party aggregator source triggers official source discovery and verification."""
    third_party_url = "https://www.scholars4dev.com/daad-scholarships"
    official_url = "https://www.daad.de/en/official-daad-info"

    fake_fetcher = FakePageFetcher({
        third_party_url: PageFetchResponse(
            status=RetrievalStatus.SUCCESS,
            url=third_party_url,
            final_url=third_party_url,
            title="Scholars4Dev Directory",
            extracted_text="Aggregator listing for DAAD master funding.",
            retrieved_at=utcnow(),
        ),
        official_url: PageFetchResponse(
            status=RetrievalStatus.SUCCESS,
            url=official_url,
            final_url=official_url,
            title="Official DAAD Portal",
            extracted_text="DAAD offers Helmut-Schmidt awards for studying in Germany. Fully funded.",
            retrieved_at=utcnow(),
        ),
    })

    fake_provider = FakeSearchProvider(default_results=[
        SearchResultItem(url=official_url, title="Official DAAD Site")
    ])

    agent = OfficialSourceVerificationAgent(page_fetcher=fake_fetcher, search_provider=fake_provider)
    candidate = make_sample_candidate(source_url=third_party_url)

    req = VerificationRequest(candidates=[candidate])
    resp = await agent.verify(req)

    assert len(resp.reports) == 1
    report = resp.reports[0]
    assert report.overall_status == VerificationReportStatus.VERIFIED
    assert report.verified_official_url == official_url
    assert len(report.source_assessments) == 2
    assert report.source_assessments[0].classification == SourceClassification.THIRD_PARTY
    assert report.source_assessments[1].classification == SourceClassification.OFFICIAL
    assert report.source_assessments[1].is_discovered_official_source
    assert len(fake_provider.call_history) == 1


@pytest.mark.anyio
async def test_uncertain_source_not_treated_as_official():
    """Verify that an uncertain domain is never treated as official."""
    uncertain_url = "https://unknown-scholarship-blog.info/article"
    fake_fetcher = FakePageFetcher({
        uncertain_url: PageFetchResponse(
            status=RetrievalStatus.SUCCESS,
            url=uncertain_url,
            final_url=uncertain_url,
            title="Random Blog",
            extracted_text="Some random unverified tips about studying abroad.",
            retrieved_at=utcnow(),
        )
    })
    # Search yields no official candidates
    fake_provider = FakeSearchProvider(default_results=[])
    agent = OfficialSourceVerificationAgent(page_fetcher=fake_fetcher, search_provider=fake_provider)

    candidate = make_sample_candidate(source_url=uncertain_url)
    req = VerificationRequest(candidates=[candidate])
    resp = await agent.verify(req)

    assert len(resp.reports) == 1
    report = resp.reports[0]
    assert report.overall_status == VerificationReportStatus.UNVERIFIED
    assert report.verified_official_url is None
    assert report.source_assessments[0].classification == SourceClassification.UNCERTAIN


@pytest.mark.anyio
async def test_inaccessible_official_page():
    """Verify that an inaccessible source produces SOURCE_INACCESSIBLE status."""
    inaccessible_url = "https://www.daad.de/down-page"
    fake_fetcher = FakePageFetcher({
        inaccessible_url: PageFetchResponse(
            status=RetrievalStatus.HTTP_ERROR,
            url=inaccessible_url,
            http_status=404,
            retrieved_at=utcnow(),
            error_message="HTTP 404 Not Found",
        )
    })
    fake_provider = FakeSearchProvider(default_results=[])
    agent = OfficialSourceVerificationAgent(page_fetcher=fake_fetcher, search_provider=fake_provider)

    candidate = make_sample_candidate(source_url=inaccessible_url)
    req = VerificationRequest(candidates=[candidate])
    resp = await agent.verify(req)

    assert len(resp.reports) == 1
    report = resp.reports[0]
    assert report.overall_status == VerificationReportStatus.SOURCE_INACCESSIBLE
    assert report.verified_official_url is None


@pytest.mark.anyio
async def test_search_provider_unconfigured():
    """Verify verification proceeds safely with fallback warnings when search provider is unconfigured."""
    third_party_url = "https://www.findamasters.com/scholarship-details"
    fake_fetcher = FakePageFetcher({
        third_party_url: PageFetchResponse(
            status=RetrievalStatus.SUCCESS,
            url=third_party_url,
            final_url=third_party_url,
            title="FindAMasters",
            extracted_text="Listing page on third-party aggregator.",
            retrieved_at=utcnow(),
        )
    })
    fake_provider = FakeSearchProvider(default_status=SearchStatus.PROVIDER_NOT_CONFIGURED)
    agent = OfficialSourceVerificationAgent(page_fetcher=fake_fetcher, search_provider=fake_provider)

    candidate = make_sample_candidate(source_url=third_party_url)
    req = VerificationRequest(candidates=[candidate])
    resp = await agent.verify(req)

    assert len(resp.reports) == 1
    report = resp.reports[0]
    assert report.overall_status == VerificationReportStatus.UNVERIFIED
    assert any("Initial source" in w for w in report.warnings)


@pytest.mark.anyio
async def test_partial_results_when_one_candidate_fails_and_another_succeeds():
    """Verify that an unexpected error on one candidate does not abort processing of remaining candidates."""
    url1 = "https://www.daad.de/program1"
    url2 = "https://www.daad.de/program2"

    class FailingPageFetcher(PageFetcher):
        async def fetch(self, url: str, max_length: int | None = None) -> PageFetchResponse:
            if "program1" in url:
                raise RuntimeError("Simulated unexpected network failure")
            return PageFetchResponse(
                status=RetrievalStatus.SUCCESS,
                url=url,
                final_url=url,
                title="DAAD Program 2",
                extracted_text="DAAD Helmut-Schmidt in Germany. Fully funded.",
                retrieved_at=utcnow(),
            )

    agent = OfficialSourceVerificationAgent(
        page_fetcher=FailingPageFetcher(),
        search_provider=FakeSearchProvider(),
    )

    c1 = make_sample_candidate(name="Failing Program", source_url=url1)
    c2 = make_sample_candidate(name="Succeeding Program", source_url=url2)

    req = VerificationRequest(candidates=[c1, c2])
    resp = await agent.verify(req)

    assert len(resp.reports) == 2
    assert resp.reports[0].overall_status == VerificationReportStatus.UNVERIFIED
    assert "Verification failed due to internal error" in resp.reports[0].warnings[0]
    assert resp.reports[1].overall_status == VerificationReportStatus.VERIFIED


@pytest.mark.anyio
async def test_contradictory_claim_with_evidence():
    """Verify that a claim directly contradicted by official text is marked CONTRADICTED."""
    url = "https://www.daad.de/scholarships/partial-award"
    # Candidate claimed fully funded, but page explicitly states partial scholarship
    text = "The Helmut-Schmidt scholarship is a partial scholarship covering only partial travel grants."
    fake_fetcher = FakePageFetcher({
        url: PageFetchResponse(
            status=RetrievalStatus.SUCCESS,
            url=url,
            final_url=url,
            title="DAAD Award",
            extracted_text=text,
            retrieved_at=utcnow(),
        )
    })
    agent = OfficialSourceVerificationAgent(
        page_fetcher=fake_fetcher,
        search_provider=FakeSearchProvider(),
    )

    candidate = make_sample_candidate(source_url=url, funding_type=FundingType.FULL)
    req = VerificationRequest(candidates=[candidate])
    resp = await agent.verify(req)

    report = resp.reports[0]
    assert report.overall_status == VerificationReportStatus.CONFLICTING
    funding_claim = next(c for c in report.claim_assessments if c.claim_type == "funding")
    assert funding_claim.outcome == ClaimOutcome.CONTRADICTED
    assert "partial scholarship" in funding_claim.excerpt.lower()


@pytest.mark.anyio
async def test_missing_facts_remain_unknown_not_fabricated():
    """Verify that unmentioned funding and deadlines remain NOT_FOUND without fabrication."""
    url = "https://www.daad.de/general-overview"
    text = "General overview of international studies at German universities."
    fake_fetcher = FakePageFetcher({
        url: PageFetchResponse(
            status=RetrievalStatus.SUCCESS,
            url=url,
            final_url=url,
            title="General Overview",
            extracted_text=text,
            retrieved_at=utcnow(),
        )
    })
    agent = OfficialSourceVerificationAgent(
        page_fetcher=fake_fetcher,
        search_provider=FakeSearchProvider(),
    )

    candidate = make_sample_candidate(source_url=url, funding_type=FundingType.UNKNOWN)
    req = VerificationRequest(candidates=[candidate])
    resp = await agent.verify(req)

    report = resp.reports[0]
    funding_claim = next(c for c in report.claim_assessments if c.claim_type == "funding")
    assert funding_claim.outcome == ClaimOutcome.NOT_FOUND
    deadline_claim = next(c for c in report.claim_assessments if c.claim_type == "deadline")
    assert deadline_claim.outcome == ClaimOutcome.NOT_FOUND


@pytest.mark.anyio
async def test_bounded_candidate_limit_enforced():
    """Verify that VerificationRequest rejects more than 10 candidates."""
    candidates = [
        make_sample_candidate(name=f"Candidate {i}", source_url=f"https://www.daad.de/{i}")
        for i in range(11)
    ]
    with pytest.raises(Exception):
        VerificationRequest(candidates=candidates)

    # Empty candidate list is also rejected
    with pytest.raises(Exception):
        VerificationRequest(candidates=[])


@pytest.mark.anyio
async def test_ssrf_and_blocked_urls_handled():
    """Verify that loopback / internal private IP addresses in source URL produce SOURCE_INACCESSIBLE."""
    blocked_url = "http://127.0.0.1:8000/internal-page"
    agent = OfficialSourceVerificationAgent(
        page_fetcher=PageFetcher(),  # Uses actual SSRF validator
        search_provider=FakeSearchProvider(default_results=[]),
    )
    candidate = make_sample_candidate(source_url=blocked_url)
    req = VerificationRequest(candidates=[candidate])
    resp = await agent.verify(req)

    assert len(resp.reports) == 1
    report = resp.reports[0]
    assert report.overall_status == VerificationReportStatus.SOURCE_INACCESSIBLE
    assert report.source_assessments[0].retrieval_status == RetrievalStatus.BLOCKED_URL.value


# ==============================================================================
# API Route Endpoint Tests (/api/v1/research/verify)
# ==============================================================================

def test_api_route_verify_endpoint_validation():
    """Verify /api/v1/research/verify validates request payload."""
    # Empty candidate list -> 422
    resp = client.post("/api/v1/research/verify", json={"candidates": []})
    assert resp.status_code == 422

    # Extra unknown field -> 422
    resp = client.post("/api/v1/research/verify", json={"candidates": [], "extra_field": "disallowed"})
    assert resp.status_code == 422


def test_api_route_verify_endpoint_execution():
    """Verify /api/v1/research/verify executes and returns structured verification response."""
    cand = make_sample_candidate()
    payload = {"candidates": [cand.model_dump(mode="json")]}

    resp = client.post("/api/v1/research/verify", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "reports" in data
    assert data["total_candidates_processed"] == 1
    assert data["reports"][0]["candidate_name"] == "DAAD Helmut-Schmidt-Programme"


# ==============================================================================
# Regression Test: M5 Carry-forward whitespace-only query validation
# ==============================================================================

def test_m5_whitespace_only_query_rejected():
    """Verify that whitespace-only queries in DiscoveryRequest are strictly rejected with ValueError."""
    # Pure spaces
    with pytest.raises(Exception):
        DiscoveryRequest(query="   ")

    # Tabs and spaces
    with pytest.raises(Exception):
        DiscoveryRequest(query="\t \n  ")

    # Valid query works
    req = DiscoveryRequest(query="  DAAD Master Scholarships  ")
    assert req.query == "DAAD Master Scholarships"

    # API returns HTTP 422 for whitespace-only query
    api_resp = client.post("/api/v1/research/discover", json={"query": "     "})
    assert api_resp.status_code == 422


# ==============================================================================
# Regression Tests: M6 Carry-forward Hardening
# ==============================================================================

def test_m6_generic_institution_name_does_not_corroborate_unrelated_domain():
    """Verify generic institution names like 'City' or 'Global College' do not match unrelated commercial domains."""
    agent = OfficialSourceVerificationAgent()

    # Generic word 'City' against 'citycommercialbank.com'
    classification, reason = agent.classify_source("https://citycommercialbank.com/offers", institution_name="City College")
    assert classification == SourceClassification.UNCERTAIN

    # Generic words 'Global College' against 'globaltelecom.com'
    classification, reason = agent.classify_source("https://globaltelecom.com/info", institution_name="Global College")
    assert classification == SourceClassification.UNCERTAIN

    # Genuine non-generic institution name matches
    classification, reason = agent.classify_source("https://oxford.ac.uk/study", institution_name="Oxford University")
    assert classification == SourceClassification.OFFICIAL


def test_m6_generic_first_word_does_not_falsely_verify_opportunity_name():
    """Verify that a generic first word like 'International' does not match if the distinctive name is missing."""
    agent = OfficialSourceVerificationAgent()
    cand = make_sample_candidate(name="International Excellence Rhodes Award")

    # Page contains 'international' and 'scholarship', but not 'Rhodes'
    page_text = "This international scholarship offers educational support to students worldwide."
    claims = agent.assess_claims(cand, "https://www.daad.de/info", page_text)
    name_claim = next(c for c in claims if c.claim_type == "opportunity_name")
    assert name_claim.outcome == ClaimOutcome.NOT_FOUND

    # Page contains the distinctive token 'Rhodes'
    page_text_with_distinctive = "The Rhodes scholarship offers support to students worldwide."
    claims_supported = agent.assess_claims(cand, "https://www.daad.de/info", page_text_with_distinctive)
    name_claim_supported = next(c for c in claims_supported if c.claim_type == "opportunity_name")
    assert name_claim_supported.outcome == ClaimOutcome.SUPPORTED
