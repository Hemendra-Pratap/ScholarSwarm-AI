import datetime
from datetime import timezone
import logging
import re
import urllib.parse
from pydantic import HttpUrl
from app.schemas.common import UTCDateTime
from app.schemas.discovery import (
    DiscoveredCandidate,
    DiscoveryRequest,
    DiscoveryResponse,
    DiscoveryStatus,
)
from app.schemas.opportunity import (
    FundingDetail,
    FundingType,
    OpportunityBase,
    VerificationStatus,
)
from app.schemas.research import (
    SearchRequest,
    SearchResultItem,
    SearchStatus,
)
from app.services.search_provider import SearchProvider, TavilySearchProvider

logger = logging.getLogger(__name__)

# Known country mappings for deterministic destination matching
KNOWN_COUNTRIES = [
    "Germany", "United States", "USA", "United Kingdom", "UK", "Canada",
    "Australia", "France", "Netherlands", "Sweden", "Switzerland", "Japan",
    "South Korea", "Singapore", "New Zealand", "Italy", "Spain", "Ireland",
    "Norway", "Denmark", "Finland", "Austria", "Belgium",
]

KNOWN_INSTITUTION_KEYWORDS = [
    "University", "College", "Institute", "Academy", "School", "DAAD",
    "Erasmus", "Fulbright", "Chevening", "Commonwealth", "Consortium", "Foundation",
]


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(timezone.utc)


def normalize_source_url(raw_url: str) -> str:
    """Normalize a URL deterministically for deduplication (strip scheme/www, lowercase netloc, strip trailing slash/fragment)."""
    if not raw_url:
        return ""
    clean = raw_url.strip()
    try:
        parsed = urllib.parse.urlsplit(clean)
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        # Remove trailing slashes from path, default to empty or /
        path = parsed.path.rstrip("/")
        # We omit scheme (treat http and https as equivalent destinations) for deduplication
        query_part = f"?{parsed.query}" if parsed.query else ""
        return f"{netloc}{path}{query_part}"
    except Exception:
        return clean.lower()


class ScholarshipDiscoveryAgent:
    """Agent that queries the search provider with targeted queries and extracts candidate opportunities."""

    def __init__(self, search_provider: SearchProvider | None = None):
        self.search_provider = search_provider or TavilySearchProvider()

    def generate_search_queries(self, request: DiscoveryRequest, max_queries: int = 3) -> list[str]:
        """Generate a small, bounded set of targeted search queries from research intent."""
        base_intent = request.query.strip()
        study_term = f"{request.study_level.strip()} " if request.study_level else ""
        destinations = [d.strip() for d in request.destinations if d.strip()]

        queries: list[str] = []

        # Query 1: Direct user intent with study level if present
        if study_term and study_term.lower() not in base_intent.lower():
            primary_query = f"{base_intent} {study_term}scholarships"
        else:
            primary_query = base_intent
        queries.append(primary_query)

        # Query 2: Focused destination-based university/official funding query
        if destinations:
            dest_str = " ".join(destinations[:2])
            queries.append(f"official {study_term}scholarships international students {dest_str}")
        else:
            queries.append(f"official university {study_term}scholarships international students")

        # Query 3: Government or major funding scheme query
        if destinations:
            queries.append(f"government funding scholarship {study_term}{destinations[0]}")
        else:
            queries.append(f"government funded international master scholarship programs")

        # Deduplicate queries while preserving order, enforce bound
        seen = set()
        deduped_queries = []
        for q in queries:
            clean_q = " ".join(q.split())
            if clean_q not in seen:
                seen.add(clean_q)
                deduped_queries.append(clean_q)

        return deduped_queries[:max_queries]

    def extract_candidate_from_result(
        self,
        item: SearchResultItem,
        search_query: str,
        retrieved_at: UTCDateTime,
    ) -> DiscoveredCandidate | None:
        """Extract candidate opportunity facts honestly from title and snippet without fabrication."""
        url_str = item.url.strip() if item.url else ""
        if not url_str or not (url_str.startswith("http://") or url_str.startswith("https://")):
            return None

        # Clean title
        raw_title = (item.title or "").strip()
        raw_snippet = (item.snippet or "").strip()

        # Combine title and snippet for analysis
        combined_text = f"{raw_title} {raw_snippet}"

        extracted_fields: list[str] = ["official_url"]
        missing_fields: list[str] = []

        # 1. Opportunity Name: Prefer page title if descriptive, or extract from heading pattern
        name = raw_title if len(raw_title) >= 3 else "Scholarship Opportunity"
        extracted_fields.append("name")

        # 2. Institution / Administering Organization
        institution: str | None = None
        # Try extracting known institution keywords or domain name
        for word in KNOWN_INSTITUTION_KEYWORDS:
            match = re.search(rf"\b([A-Z][A-Za-z0-9\s&,\.\-]{{2,40}}\s+{word}\b)", combined_text)
            if match:
                institution = match.group(1).strip(" ,.-")
                break

        if not institution:
            # Fall back to host/domain as organization indicator
            try:
                parsed_host = urllib.parse.urlsplit(url_str).netloc
                parts = parsed_host.split(".")
                if len(parts) >= 2:
                    institution = parts[-2].capitalize()
                else:
                    institution = parsed_host
            except Exception:
                institution = "Unknown Organization"
            missing_fields.append("institution")
        else:
            extracted_fields.append("institution")

        # 3. Destination Country
        destination_country: str | None = None
        for country in KNOWN_COUNTRIES:
            if re.search(rf"\b{re.escape(country)}\b", combined_text, re.IGNORECASE):
                destination_country = country
                break

        if destination_country:
            extracted_fields.append("destination_country")
        else:
            destination_country = "International / Multiple"
            missing_fields.append("destination_country")

        # 4. Funding: Check for explicit full/partial mentions, never fabricate amounts
        funding: FundingDetail | None = None
        if re.search(r"\b(fully?\s*funded|full\s*tuition|full\s*scholarship)\b", combined_text, re.IGNORECASE):
            funding = FundingDetail(
                funding_type=FundingType.FULL,
                amount=None,
                currency=None,
                period=None,
            )
            extracted_fields.append("funding")
        elif re.search(r"\b(partially?\s*funded|partial\s*scholarship|tuition\s*waiver)\b", combined_text, re.IGNORECASE):
            funding = FundingDetail(
                funding_type=FundingType.PARTIAL,
                amount=None,
                currency=None,
                period=None,
            )
            extracted_fields.append("funding")
        else:
            missing_fields.append("funding")

        # 5. Deadline: NEVER infer from snippet unless an explicit structured date is present
        # In general search snippets, deadlines are ambiguous or past; leave None unless verified.
        deadline = None
        missing_fields.append("deadline")

        # Validate URL for schema HttpUrl
        try:
            pydantic_url = HttpUrl(url_str)
        except Exception:
            return None

        # Opportunity Base Record
        opportunity = OpportunityBase(
            name=name[:500],
            institution=institution[:500],
            destination_country=destination_country[:100],
            official_url=pydantic_url,
            funding=funding,
            deadline=deadline,
            verification_status=VerificationStatus.UNVERIFIED,
        )

        return DiscoveredCandidate(
            opportunity=opportunity,
            source_url=url_str,
            source_title=raw_title if raw_title else None,
            snippet=raw_snippet if raw_snippet else None,
            search_query=search_query,
            discovered_at=retrieved_at,
            extracted_fields=extracted_fields,
            missing_fields=missing_fields,
            alternate_urls=[],
            confidence_notes="Extracted from search provider snippet; candidate unverified by official source.",
        )

    def deduplicate_candidates(self, candidates: list[DiscoveredCandidate]) -> list[DiscoveredCandidate]:
        """Deduplicate candidates deterministically by normalized URL and preserve alternate sources."""
        deduped: dict[str, DiscoveredCandidate] = {}

        for cand in candidates:
            norm_key = normalize_source_url(cand.source_url)
            if norm_key in deduped:
                existing = deduped[norm_key]
                # If the new candidate has a different raw source URL, store it as an alternate
                if cand.source_url != existing.source_url and cand.source_url not in existing.alternate_urls:
                    existing.alternate_urls.append(cand.source_url)
                # Keep the richer candidate or preserve earlier
                if not existing.snippet and cand.snippet:
                    existing.snippet = cand.snippet
                if not existing.source_title and cand.source_title:
                    existing.source_title = cand.source_title
            else:
                deduped[norm_key] = cand

        return list(deduped.values())

    async def discover(self, request: DiscoveryRequest) -> DiscoveryResponse:
        """Execute discovery workflow over bounded queries, returning honest candidate opportunities."""
        exec_time = utcnow()
        queries = self.generate_search_queries(request)
        executed_queries: list[str] = []
        raw_candidates: list[DiscoveredCandidate] = []
        warnings: list[str] = []
        provider_unconfigured = False
        all_failed = True

        for query in queries:
            executed_queries.append(query)
            search_req = SearchRequest(
                query=query,
                max_results=min(10, request.max_candidates),
                search_depth="basic",
            )

            search_resp = await self.search_provider.search(search_req)

            if search_resp.status == SearchStatus.PROVIDER_NOT_CONFIGURED:
                provider_unconfigured = True
                warnings.append(f"Query '{query}': Search provider not configured.")
                break  # No need to retry remaining queries if key is missing

            if search_resp.status == SearchStatus.SUCCESS:
                all_failed = False
                for item in search_resp.results:
                    cand = self.extract_candidate_from_result(item, query, search_resp.retrieved_at)
                    if cand:
                        raw_candidates.append(cand)
            else:
                warning_msg = f"Query '{query}' failed with status {search_resp.status.value}"
                if search_resp.error_message:
                    warning_msg += f": {search_resp.error_message}"
                warnings.append(warning_msg)

        # Handle complete failure states
        if provider_unconfigured:
            return DiscoveryResponse(
                status=DiscoveryStatus.PROVIDER_UNAVAILABLE,
                candidates=[],
                total_candidates=0,
                queries_executed=executed_queries,
                executed_at=exec_time,
                warnings=warnings,
                error_message="Search provider is not configured. Real scholarship discovery requires a valid API key.",
            )

        if all_failed:
            return DiscoveryResponse(
                status=DiscoveryStatus.FAILED,
                candidates=[],
                total_candidates=0,
                queries_executed=executed_queries,
                executed_at=exec_time,
                warnings=warnings,
                error_message="All discovery search queries failed to execute.",
            )

        # Deduplicate and sort deterministically
        deduped = self.deduplicate_candidates(raw_candidates)
        # Sort deterministically by opportunity name, then source URL
        deduped.sort(key=lambda c: (c.opportunity.name.lower(), c.source_url.lower()))

        # Enforce max_candidates bound
        bounded_candidates = deduped[:request.max_candidates]

        # Determine overall status
        if not bounded_candidates:
            status = DiscoveryStatus.NO_RESULTS
        elif warnings:
            status = DiscoveryStatus.PARTIAL
        else:
            status = DiscoveryStatus.SUCCESS

        return DiscoveryResponse(
            status=status,
            candidates=bounded_candidates,
            total_candidates=len(bounded_candidates),
            queries_executed=executed_queries,
            executed_at=exec_time,
            warnings=warnings,
        )
