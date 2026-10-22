import datetime
from datetime import timezone
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.discovery import (
    DiscoveryRequest,
    DiscoveryResponse,
    DiscoveryStatus,
)
from app.schemas.opportunity import FundingType, VerificationStatus
from app.schemas.research import (
    SearchRequest,
    SearchResponse,
    SearchResultItem,
    SearchStatus,
)
from app.services.discovery_agent import (
    ScholarshipDiscoveryAgent,
    normalize_source_url,
)
from app.services.search_provider import SearchProvider

client = TestClient(app)


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(timezone.utc)


class FakeSearchProvider(SearchProvider):
    """Deterministic fake search provider for testing without external networks."""

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


# ==============================================================================
# Unit & Functional Tests for ScholarshipDiscoveryAgent
# ==============================================================================

@pytest.mark.anyio
async def test_valid_search_result_becomes_candidate():
    """Verify that a valid search result item is correctly parsed into a candidate opportunity."""
    item = SearchResultItem(
        url="https://www.daad.de/en/study-and-research-in-germany/scholarships/",
        title="DAAD Helmut-Schmidt-Programme Master Scholarships",
        snippet="Fully funded master scholarships for students from developing countries to study in Germany.",
        score=0.95,
        published_date="2026-01-15",
    )
    fake_provider = FakeSearchProvider(default_results=[item])
    agent = ScholarshipDiscoveryAgent(search_provider=fake_provider)

    req = DiscoveryRequest(
        query="Helmut Schmidt master scholarships",
        destinations=["Germany"],
        study_level="master",
    )
    response = await agent.discover(req)

    assert response.status == DiscoveryStatus.SUCCESS
    assert len(response.candidates) == 1
    candidate = response.candidates[0]

    assert candidate.source_url == "https://www.daad.de/en/study-and-research-in-germany/scholarships/"
    assert "Helmut-Schmidt" in candidate.opportunity.name
    assert candidate.opportunity.destination_country == "Germany"
    assert candidate.opportunity.verification_status == VerificationStatus.UNVERIFIED
    # Funding detected honestly from 'fully funded'
    assert candidate.opportunity.funding is not None
    assert candidate.opportunity.funding.funding_type == FundingType.FULL
    # Extracted fields should include name, official_url, destination_country, funding
    assert "funding" in candidate.extracted_fields
    assert "deadline" in candidate.missing_fields
    assert candidate.opportunity.deadline is None


@pytest.mark.anyio
async def test_missing_fields_remain_unknown_no_fabrication():
    """Verify missing fields (funding, deadline, institution) remain unknown and are not fabricated."""
    item = SearchResultItem(
        url="https://example.org/programs/info",
        title="International Studies",
        snippet="Information about graduate programs for international candidates.",
        score=0.5,
    )
    fake_provider = FakeSearchProvider(default_results=[item])
    agent = ScholarshipDiscoveryAgent(search_provider=fake_provider)

    req = DiscoveryRequest(query="international studies")
    response = await agent.discover(req)

    assert response.status == DiscoveryStatus.SUCCESS
    assert len(response.candidates) == 1
    cand = response.candidates[0]

    # No deadline fabricated
    assert cand.opportunity.deadline is None
    assert "deadline" in cand.missing_fields

    # No funding fabricated
    assert cand.opportunity.funding is None
    assert "funding" in cand.missing_fields

    # Destination country fallback indicates international / unverified
    assert cand.opportunity.destination_country == "International / Multiple"
    assert "destination_country" in cand.missing_fields


@pytest.mark.anyio
async def test_search_queries_are_bounded():
    """Verify query generation is strictly bounded to a configurable small number (default <= 3)."""
    fake_provider = FakeSearchProvider(default_results=[])
    agent = ScholarshipDiscoveryAgent(search_provider=fake_provider)

    req = DiscoveryRequest(
        query="Robotics computer science research funding",
        destinations=["Germany", "Sweden", "Netherlands", "UK", "Canada"],
        study_level="postgraduate",
    )
    queries = agent.generate_search_queries(req, max_queries=3)
    assert 1 <= len(queries) <= 3

    resp = await agent.discover(req)
    assert len(fake_provider.call_history) <= 3
    assert len(resp.queries_executed) <= 3


@pytest.mark.anyio
async def test_duplicate_urls_are_consolidated():
    """Verify candidate deduplication by normalized canonical URL preserves alternate URLs."""
    items = [
        SearchResultItem(
            url="https://www.example.edu/scholarship/",
            title="Excellence Scholarship",
            snippet="First snippet from search query 1.",
        ),
        SearchResultItem(
            url="http://example.edu/scholarship",  # Same destination, normalized http/https & www
            title="Excellence Scholarship",
            snippet="Second snippet from search query 2.",
        ),
        SearchResultItem(
            url="https://example.edu/scholarship#apply",  # Fragment difference
            title="Excellence Scholarship",
            snippet="Third snippet with fragment.",
        ),
    ]
    fake_provider = FakeSearchProvider(default_results=items)
    agent = ScholarshipDiscoveryAgent(search_provider=fake_provider)

    req = DiscoveryRequest(query="excellence scholarship")
    resp = await agent.discover(req)

    assert resp.status == DiscoveryStatus.SUCCESS
    assert len(resp.candidates) == 1
    cand = resp.candidates[0]
    assert len(cand.alternate_urls) >= 1


@pytest.mark.anyio
async def test_similar_distinct_awards_not_incorrectly_merged():
    """Verify distinct awards at the same institution or distinct URLs are preserved."""
    items = [
        SearchResultItem(
            url="https://www.ox.ac.uk/scholarships/clarendon",
            title="Clarendon Scholarship Oxford",
            snippet="Prestigious graduate scholarship at Oxford.",
        ),
        SearchResultItem(
            url="https://www.ox.ac.uk/scholarships/rhodes",
            title="Rhodes Scholarship Oxford",
            snippet="Global postgraduate scholarship at Oxford.",
        ),
    ]
    fake_provider = FakeSearchProvider(default_results=items)
    agent = ScholarshipDiscoveryAgent(search_provider=fake_provider)

    req = DiscoveryRequest(query="Oxford scholarships")
    resp = await agent.discover(req)

    assert resp.status == DiscoveryStatus.SUCCESS
    assert len(resp.candidates) == 2
    names = [c.opportunity.name for c in resp.candidates]
    assert any("Clarendon" in n for n in names)
    assert any("Rhodes" in n for n in names)


@pytest.mark.anyio
async def test_missing_provider_configuration():
    """Verify provider not configured returns explicit provider_unavailable status with 0 candidates."""
    fake_provider = FakeSearchProvider(default_status=SearchStatus.PROVIDER_NOT_CONFIGURED)
    agent = ScholarshipDiscoveryAgent(search_provider=fake_provider)

    req = DiscoveryRequest(query="machine learning scholarships")
    resp = await agent.discover(req)

    assert resp.status == DiscoveryStatus.PROVIDER_UNAVAILABLE
    assert resp.total_candidates == 0
    assert len(resp.candidates) == 0
    assert resp.error_message is not None
    assert "Search provider is not configured" in resp.error_message


@pytest.mark.anyio
async def test_provider_failures_handling():
    """Verify authentication, rate limit, timeout, and connection errors fail gracefully without raising."""
    for fail_status in [
        SearchStatus.AUTHENTICATION_ERROR,
        SearchStatus.RATE_LIMITED,
        SearchStatus.TIMEOUT,
        SearchStatus.CONNECTION_ERROR,
        SearchStatus.PROVIDER_ERROR,
    ]:
        fake_provider = FakeSearchProvider(default_status=fail_status)
        agent = ScholarshipDiscoveryAgent(search_provider=fake_provider)

        req = DiscoveryRequest(query="bioinformatics scholarship")
        resp = await agent.discover(req)

        assert resp.status == DiscoveryStatus.FAILED
        assert resp.total_candidates == 0
        assert len(resp.warnings) >= 1


@pytest.mark.anyio
async def test_one_query_fails_while_another_succeeds_partial_results():
    """Verify useful partial candidates are preserved when one search query fails and another succeeds."""
    valid_item = SearchResultItem(
        url="https://www.tudelft.nl/en/education/practical-matters/scholarships/justus-louise-van-effen",
        title="Justus & Louise van Effen Excellence Scholarships",
        snippet="Fully funded MSc scholarships at TU Delft in the Netherlands.",
    )
    # Setup canned responses where query 1 fails and query 2 succeeds
    canned = {
        "TU Delft master scholarships": SearchResponse(
            status=SearchStatus.TIMEOUT,
            query="TU Delft master scholarships",
            results=[],
            retrieved_at=utcnow(),
            error_message="Provider timeout",
        ),
        "official master scholarships international students Netherlands": SearchResponse(
            status=SearchStatus.SUCCESS,
            query="official master scholarships international students Netherlands",
            results=[valid_item],
            total_results=1,
            retrieved_at=utcnow(),
        ),
        "government funding scholarship master Netherlands": SearchResponse(
            status=SearchStatus.RATE_LIMITED,
            query="government funding scholarship master Netherlands",
            results=[],
            retrieved_at=utcnow(),
            error_message="Rate limited",
        ),
    }

    fake_provider = FakeSearchProvider(canned_responses=canned)
    agent = ScholarshipDiscoveryAgent(search_provider=fake_provider)

    req = DiscoveryRequest(
        query="TU Delft master scholarships",
        destinations=["Netherlands"],
        study_level="master",
    )
    resp = await agent.discover(req)

    # Partial status: some queries had warnings/errors, but useful candidates were found
    assert resp.status == DiscoveryStatus.PARTIAL
    assert len(resp.candidates) == 1
    assert "Delft" in resp.candidates[0].opportunity.name or "tudelft" in resp.candidates[0].opportunity.institution.lower()
    assert len(resp.warnings) >= 2


@pytest.mark.anyio
async def test_empty_search_results_return_no_results():
    """Verify clean search with 0 hits returns NO_RESULTS rather than fabricated data."""
    fake_provider = FakeSearchProvider(default_status=SearchStatus.SUCCESS, default_results=[])
    agent = ScholarshipDiscoveryAgent(search_provider=fake_provider)

    req = DiscoveryRequest(query="very specific obscure query with zero results")
    resp = await agent.discover(req)

    assert resp.status == DiscoveryStatus.NO_RESULTS
    assert resp.total_candidates == 0
    assert len(resp.candidates) == 0


@pytest.mark.anyio
async def test_results_without_usable_urls_ignored():
    """Verify search results without usable or valid HTTP/HTTPS URLs are discarded."""
    items = [
        SearchResultItem(url="", title="Empty URL"),
        SearchResultItem(url="javascript:alert(1)", title="Javascript URL"),
        SearchResultItem(url="ftp://ftp.example.org", title="FTP URL"),
    ]
    fake_provider = FakeSearchProvider(default_results=items)
    agent = ScholarshipDiscoveryAgent(search_provider=fake_provider)

    req = DiscoveryRequest(query="test invalid items")
    resp = await agent.discover(req)

    assert resp.status == DiscoveryStatus.NO_RESULTS
    assert resp.total_candidates == 0


@pytest.mark.anyio
async def test_deterministic_output_ordering():
    """Verify discovered candidates are ordered deterministically by name and URL."""
    items = [
        SearchResultItem(url="https://b.edu/scholarship", title="Beta Scholarship"),
        SearchResultItem(url="https://a.edu/scholarship", title="Alpha Scholarship"),
        SearchResultItem(url="https://c.edu/scholarship", title="Gamma Scholarship"),
    ]
    fake_provider = FakeSearchProvider(default_results=items)
    agent = ScholarshipDiscoveryAgent(search_provider=fake_provider)

    req = DiscoveryRequest(query="greek scholarships")
    resp = await agent.discover(req)

    assert len(resp.candidates) == 3
    names = [c.opportunity.name for c in resp.candidates]
    assert names == ["Alpha Scholarship", "Beta Scholarship", "Gamma Scholarship"]


@pytest.mark.anyio
async def test_different_student_intent_without_rahul_assumptions():
    """Verify discovery works generically for completely different academic profiles (e.g. Arts in France)."""
    item = SearchResultItem(
        url="https://www.campusfrance.org/en/eiffel-scholarship-program-excellence",
        title="Eiffel Scholarship Program of Excellence",
        snippet="French Ministry for Europe and Foreign Affairs scholarship for master and PhD in France.",
    )
    fake_provider = FakeSearchProvider(default_results=[item])
    agent = ScholarshipDiscoveryAgent(search_provider=fake_provider)

    req = DiscoveryRequest(
        query="fine arts and design scholarships",
        destinations=["France"],
        study_level="master",
    )
    resp = await agent.discover(req)

    assert resp.status == DiscoveryStatus.SUCCESS
    assert len(resp.candidates) == 1
    assert resp.candidates[0].opportunity.destination_country == "France"
    assert "Eiffel" in resp.candidates[0].opportunity.name


# ==============================================================================
# API Route Endpoint Tests (/api/v1/research/discover)
# ==============================================================================

def test_api_route_discover_endpoint_validation():
    """Verify /api/v1/research/discover request validation."""
    # Query too short (< 2 characters)
    resp = client.post("/api/v1/research/discover", json={"query": "a"})
    assert resp.status_code == 422

    # Negative max_candidates
    resp = client.post("/api/v1/research/discover", json={"query": "scholarships", "max_candidates": 0})
    assert resp.status_code == 422

    # Extra forbidden field
    resp = client.post("/api/v1/research/discover", json={"query": "scholarships", "unsupported_field": True})
    assert resp.status_code == 422


def test_api_route_discover_endpoint_unconfigured_default():
    """Verify /api/v1/research/discover returns provider_unavailable when Tavily key is unconfigured."""
    from app.api.routes.research import get_search_provider
    from app.services.search_provider import TavilySearchProvider

    app.dependency_overrides[get_search_provider] = lambda: TavilySearchProvider(api_key=None)
    try:
        resp = client.post(
            "/api/v1/research/discover",
            json={
                "query": "international scholarships in computer science",
                "destinations": ["Germany"],
                "study_level": "master",
                "max_candidates": 5,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "provider_unavailable"
        assert data["total_candidates"] == 0
        assert len(data["candidates"]) == 0
        assert "Search provider is not configured" in data["error_message"]
    finally:
        app.dependency_overrides.pop(get_search_provider, None)
