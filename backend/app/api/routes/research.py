from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.entities import StudentProfileModel
from app.schemas.orchestration import (
    ResearchRunExecutionRequest,
    ResearchRunExecutionResponse,
)
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
from app.schemas.ranking import (
    RankingRequest,
    RankingResponse,
)
from app.schemas.student_profile import StudentProfileBase
from app.services.page_fetcher import PageFetcher
from app.services.search_provider import SearchProvider, TavilySearchProvider
from app.services.discovery_agent import ScholarshipDiscoveryAgent
from app.services.verification_agent import OfficialSourceVerificationAgent
from app.services.eligibility_agent import EligibilityAuditAgent
from app.services.ranking_agent import RankingAndStrategyAgent
from app.services.orchestration_service import OrchestrationService

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


def get_ranking_agent() -> RankingAndStrategyAgent:
    """Dependency provider yielding the ranking and application strategy agent."""
    return RankingAndStrategyAgent()


def get_orchestration_service(
    discovery_agent: ScholarshipDiscoveryAgent = Depends(get_discovery_agent),
    verification_agent: OfficialSourceVerificationAgent = Depends(get_verification_agent),
    eligibility_agent: EligibilityAuditAgent = Depends(get_eligibility_agent),
    ranking_agent: RankingAndStrategyAgent = Depends(get_ranking_agent),
) -> OrchestrationService:
    """Dependency provider yielding the multi-agent orchestration service."""
    return OrchestrationService(
        discovery_agent=discovery_agent,
        verification_agent=verification_agent,
        eligibility_agent=eligibility_agent,
        ranking_agent=ranking_agent,
    )


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


@router.post(
    "/rank",
    response_model=RankingResponse,
    status_code=status.HTTP_200_OK,
    summary="Deterministic Opportunity Ranking & Application Strategy",
    description="Rank candidate opportunities deterministically using eligibility as a gate, computing transparent profile-fit scores, and generating actionable next steps.",
)
async def rank_opportunities(
    request: RankingRequest,
    agent: RankingAndStrategyAgent = Depends(get_ranking_agent),
) -> RankingResponse:
    """Rank candidate opportunities and generate prioritized application action plan."""
    return await agent.rank(request)


@router.post(
    "/runs",
    response_model=ResearchRunExecutionResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute Multi-Agent Scholarship Research Run",
    description="Synchronously coordinate scholarship discovery, official-source verification, eligibility audit, and ranking through a central LangGraph orchestrator.",
)
async def create_research_run(
    request: ResearchRunExecutionRequest,
    orchestrator: OrchestrationService = Depends(get_orchestration_service),
    db: Session = Depends(get_db),
) -> ResearchRunExecutionResponse:
    """Execute end-to-end multi-agent orchestration run with typed output and execution trace."""
    # 1. Resolve student profile: either from direct payload or confirmed database profile
    profile: StudentProfileBase | None = None
    profile_id_str: str | None = None

    if request.student_profile is not None:
        profile = request.student_profile
        if request.profile_id is not None:
            profile_id_str = str(request.profile_id)
    elif request.profile_id is not None:
        profile_id_str = str(request.profile_id)
        db_profile = db.query(StudentProfileModel).filter(StudentProfileModel.id == request.profile_id).first()
        if not db_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Confirmed student profile with ID '{request.profile_id}' not found.",
            )
        profile = StudentProfileBase.model_validate(db_profile)
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Either a student_profile object or a valid profile_id referencing a confirmed profile must be provided.",
        )

    # 2. Execute orchestration workflow
    state = await orchestrator.execute_run(
        student_profile=profile,
        discovery_request=request.discovery,
        profile_id=profile_id_str,
        max_shortlist_size=request.max_shortlist_size,
        reference_date=request.reference_date,
        db=db,
    )

    # 3. Assemble typed response contract
    from datetime import datetime, timezone
    return ResearchRunExecutionResponse(
        run_id=state.run_id,
        profile_id=state.profile_id,
        status=state.terminal_status,
        is_partial=state.is_partial,
        discovery_status=state.discovery_status,
        candidates=state.discovered_candidates,
        verification_reports=state.verification_reports,
        eligibility_assessments=state.eligibility_assessments,
        ranking=state.ranking_response,
        events=state.events,
        warnings=state.warnings,
        failure_summary=state.sanitized_failure_info,
        executed_at=datetime.now(timezone.utc),
    )
