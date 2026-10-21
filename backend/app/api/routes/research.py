from fastapi import APIRouter, Depends, status
from app.schemas.research import (
    PageFetchRequest,
    PageFetchResponse,
    SearchRequest,
    SearchResponse,
)
from app.schemas.discovery import (
    DiscoveryRequest,
    DiscoveryResponse,
)
from app.schemas.verification import (
    VerificationRequest,
    VerificationResponse,
)
from app.schemas.eligibility import (
    EligibilityAuditRequest,
    EligibilityAuditResponse,
)
from app.services.page_fetcher import PageFetcher
from app.services.search_provider import SearchProvider, TavilySearchProvider
from app.services.discovery_agent import ScholarshipDiscoveryAgent
from app.services.verification_agent import OfficialSourceVerificationAgent
from app.services.eligibility_agent import EligibilityAuditAgent

router = APIRouter(prefix="/research", tags=["Research Tools"])


def get_search_provider() -> SearchProvider:
    """Dependency provider yielding the configured search provider adapter."""
    return TavilySearchProvider()


def get_page_fetcher() -> PageFetcher:
    """Dependency provider yielding the secure public page fetcher."""
    return PageFetcher()


def get_discovery_agent(
    provider: SearchProvider = Depends(get_search_provider),
) -> ScholarshipDiscoveryAgent:
    """Dependency provider yielding the scholarship discovery agent."""
    return ScholarshipDiscoveryAgent(search_provider=provider)


def get_verification_agent(
    fetcher: PageFetcher = Depends(get_page_fetcher),
    provider: SearchProvider = Depends(get_search_provider),
) -> OfficialSourceVerificationAgent:
    """Dependency provider yielding the official-source verification agent."""
    return OfficialSourceVerificationAgent(page_fetcher=fetcher, search_provider=provider)


def get_eligibility_agent() -> EligibilityAuditAgent:
    """Dependency provider yielding the eligibility audit agent."""
    return EligibilityAuditAgent()


@router.post(
    "/search",
    response_model=SearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Search External Web Resources",
    description="Query external search provider (Tavily) with structured request and normalized results. Returns provider_not_configured if API key is not set.",
)
async def search_web(
    request: SearchRequest,
    provider: SearchProvider = Depends(get_search_provider),
) -> SearchResponse:
    """Execute search query via configured search provider."""
    return await provider.search(request)


@router.post(
    "/fetch-page",
    response_model=PageFetchResponse,
    status_code=status.HTTP_200_OK,
    summary="Secure Public Page Retrieval",
    description="Retrieve and extract clean text from a public web page with strict SSRF defense, size bounds, and redirect validation.",
)
async def fetch_page(
    request: PageFetchRequest,
    fetcher: PageFetcher = Depends(get_page_fetcher),
) -> PageFetchResponse:
    """Fetch public web page text safely with SSRF protections."""
    return await fetcher.fetch(url=request.url, max_length=request.max_length)


@router.post(
    "/discover",
    response_model=DiscoveryResponse,
    status_code=status.HTTP_200_OK,
    summary="Discover Candidate Scholarships",
    description="Query search provider with bounded queries and extract normalized, deduplicated scholarship opportunities without fabrication.",
)
async def discover_scholarships(
    request: DiscoveryRequest,
    agent: ScholarshipDiscoveryAgent = Depends(get_discovery_agent),
) -> DiscoveryResponse:
    """Discover candidate scholarships and university programs matching research intent."""
    return await agent.discover(request)


@router.post(
    "/verify",
    response_model=VerificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify Candidates Against Official Sources",
    description="Evaluate discovered scholarship opportunities against official institutional sources with claim-level evidence and audits.",
)
async def verify_candidates(
    request: VerificationRequest,
    agent: OfficialSourceVerificationAgent = Depends(get_verification_agent),
) -> VerificationResponse:
    """Verify discovered candidate scholarship opportunities against official sources."""
    return await agent.verify(request)


@router.post(
    "/eligibility-audit",
    response_model=EligibilityAuditResponse,
    status_code=status.HTTP_200_OK,
    summary="Deterministic Eligibility Audit",
    description="Perform auditable, evidence-backed criterion evaluation against student profile for admission and scholarship scopes.",
)
async def audit_eligibility(
    request: EligibilityAuditRequest,
    agent: EligibilityAuditAgent = Depends(get_eligibility_agent),
) -> EligibilityAuditResponse:
    """Evaluate student profile against structured, evidence-backed eligibility criteria."""
    return await agent.audit(request)
