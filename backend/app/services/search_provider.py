from abc import ABC, abstractmethod
import datetime
from datetime import timezone
import logging
import httpx
from app.core.config import settings
from app.schemas.research import (
    SearchRequest,
    SearchResponse,
    SearchResultItem,
    SearchStatus,
)

logger = logging.getLogger(__name__)


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(timezone.utc)


class SearchProvider(ABC):
    """Abstract interface for external search providers."""

    @abstractmethod
    async def search(self, request: SearchRequest) -> SearchResponse:
        """Execute a search query and return normalized results."""
        pass


class TavilySearchProvider(SearchProvider):
    """Concrete adapter for Tavily Search API using httpx."""

    def __init__(
        self,
        api_key: str | None = None,
        api_url: str | None = None,
        timeout: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.api_key = api_key if api_key is not None else settings.TAVILY_API_KEY
        # Check for placeholder default
        if self.api_key in ("your_tavily_api_key_here", ""):
            self.api_key = None

        self.api_url = api_url or settings.TAVILY_API_URL
        self.timeout = timeout or settings.TAVILY_TIMEOUT_SECONDS
        self.transport = transport

    async def search(self, request: SearchRequest) -> SearchResponse:
        """Execute search via Tavily API with safe error handling and normalization."""
        retrieved_time = utcnow()

        # 1. Check if provider API key is configured
        if not self.api_key:
            return SearchResponse(
                status=SearchStatus.PROVIDER_NOT_CONFIGURED,
                query=request.query,
                results=[],
                total_results=0,
                retrieved_at=retrieved_time,
                warnings=["Tavily search provider is not configured: TAVILY_API_KEY is missing or invalid."],
                error_message="Search provider is not configured. Real search requires a valid API key.",
            )

        # 2. Build request payload with bounded parameters
        payload = {
            "api_key": self.api_key,
            "query": request.query.strip(),
            "max_results": max(1, min(20, request.max_results)),
            "search_depth": request.search_depth,
        }

        if request.include_domains:
            payload["include_domains"] = request.include_domains
        if request.exclude_domains:
            payload["exclude_domains"] = request.exclude_domains

        timeout_config = httpx.Timeout(
            connect=5.0,
            read=self.timeout,
            write=self.timeout,
            pool=5.0,
        )

        # 3. Execute HTTP request
        try:
            async with httpx.AsyncClient(
                transport=self.transport,
                timeout=timeout_config,
                verify=True,
            ) as client:
                response = await client.post(
                    self.api_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )

                status_code = response.status_code

                if status_code in (401, 403):
                    return SearchResponse(
                        status=SearchStatus.AUTHENTICATION_ERROR,
                        query=request.query,
                        results=[],
                        total_results=0,
                        retrieved_at=retrieved_time,
                        error_message="Search provider authentication failed. Check configured API key.",
                    )

                if status_code == 429:
                    return SearchResponse(
                        status=SearchStatus.RATE_LIMITED,
                        query=request.query,
                        results=[],
                        total_results=0,
                        retrieved_at=retrieved_time,
                        error_message="Search provider rate limit reached. Please try again later.",
                    )

                if status_code >= 500:
                    return SearchResponse(
                        status=SearchStatus.PROVIDER_ERROR,
                        query=request.query,
                        results=[],
                        total_results=0,
                        retrieved_at=retrieved_time,
                        error_message="Search provider service encountered an internal error.",
                    )

                if status_code != 200:
                    return SearchResponse(
                        status=SearchStatus.PROVIDER_ERROR,
                        query=request.query,
                        results=[],
                        total_results=0,
                        retrieved_at=retrieved_time,
                        error_message=f"Search provider returned unexpected HTTP status {status_code}.",
                    )

                # Parse JSON response
                try:
                    data = response.json()
                except Exception:
                    return SearchResponse(
                        status=SearchStatus.MALFORMED_RESPONSE,
                        query=request.query,
                        results=[],
                        total_results=0,
                        retrieved_at=retrieved_time,
                        error_message="Search provider returned malformed non-JSON data.",
                    )

                raw_results = data.get("results")
                if not isinstance(raw_results, list):
                    return SearchResponse(
                        status=SearchStatus.MALFORMED_RESPONSE,
                        query=request.query,
                        results=[],
                        total_results=0,
                        retrieved_at=retrieved_time,
                        error_message="Search provider response missing valid results list.",
                    )

                # Normalize items
                normalized_items: list[SearchResultItem] = []
                for item in raw_results:
                    if isinstance(item, dict) and item.get("url"):
                        raw_url = str(item.get("url")).strip()
                        raw_title = item.get("title")
                        raw_snippet = item.get("content") or item.get("snippet")
                        raw_score = item.get("score")
                        raw_date = item.get("published_date")

                        score_val: float | None = None
                        if raw_score is not None:
                            try:
                                score_val = float(raw_score)
                            except (ValueError, TypeError):
                                pass

                        normalized_items.append(
                            SearchResultItem(
                                url=raw_url,
                                title=str(raw_title).strip() if raw_title else None,
                                snippet=str(raw_snippet).strip() if raw_snippet else None,
                                score=score_val,
                                published_date=str(raw_date).strip() if raw_date else None,
                            )
                        )

                return SearchResponse(
                    status=SearchStatus.SUCCESS,
                    query=request.query,
                    results=normalized_items,
                    total_results=len(normalized_items),
                    retrieved_at=retrieved_time,
                )

        except httpx.TimeoutException:
            return SearchResponse(
                status=SearchStatus.TIMEOUT,
                query=request.query,
                results=[],
                total_results=0,
                retrieved_at=retrieved_time,
                error_message="Search provider request timed out.",
            )
        except httpx.RequestError:
            return SearchResponse(
                status=SearchStatus.CONNECTION_ERROR,
                query=request.query,
                results=[],
                total_results=0,
                retrieved_at=retrieved_time,
                error_message="Network connection to search provider failed.",
            )
        except Exception:
            logger.exception("Unexpected error occurred while querying search provider")
            return SearchResponse(
                status=SearchStatus.PROVIDER_ERROR,
                query=request.query,
                results=[],
                total_results=0,
                retrieved_at=retrieved_time,
                error_message="An unexpected error occurred while processing the search request.",
            )
