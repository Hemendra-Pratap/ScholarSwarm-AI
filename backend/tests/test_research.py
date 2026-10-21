import json
from unittest.mock import patch
import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.research import (
    PageFetchRequest,
    PageFetchResponse,
    RetrievalStatus,
    SearchRequest,
    SearchResponse,
    SearchStatus,
)
from app.services.page_fetcher import HTMLTextExtractor, PageFetcher
from app.services.search_provider import TavilySearchProvider
from app.services.url_validator import URLValidationError, URLValidator

client = TestClient(app)


# ==============================================================================
# 1. URLValidator and SSRF Protection Tests
# ==============================================================================

def test_url_validator_accepts_public_urls():
    """Verify standard public HTTP and HTTPS URLs are accepted."""
    valid_urls = [
        "https://www.daad.de/en/",
        "http://example.com/scholarships",
        "https://sub.domain.org/path?query=val#frag",
    ]
    # Mock DNS resolution to public IP 93.184.216.34
    mock_resolver = lambda host, port: ["93.184.216.34"]
    for url in valid_urls:
        norm_url, ips = URLValidator.validate_url(url, dns_resolver=mock_resolver)
        assert norm_url.startswith("http")
        assert "93.184.216.34" in ips


def test_url_validator_rejects_unsupported_schemes():
    """Verify schemes other than http/https are strictly rejected."""
    unsupported = [
        "ftp://example.com/file",
        "file:///etc/passwd",
        "gopher://example.com",
        "javascript:alert(1)",
        "data:text/html,<h1>Hello</h1>",
    ]
    for url in unsupported:
        with pytest.raises(URLValidationError, match="Unsupported URL scheme"):
            URLValidator.validate_url(url)


def test_url_validator_rejects_credentials():
    """Verify embedded credentials in URLs are rejected."""
    credential_urls = [
        "http://user:pass@example.com/",
        "https://admin@example.com/path",
        "http://user:@example.com/",
    ]
    for url in credential_urls:
        with pytest.raises(URLValidationError, match="Embedded credentials"):
            URLValidator.validate_url(url)


def test_url_validator_rejects_unsupported_ports():
    """Verify only standard ports 80 and 443 are allowed."""
    bad_ports = [
        "http://example.com:8080/",
        "http://example.com:22/",
        "https://example.com:8443/",
        "http://example.com:6379/",
    ]
    for url in bad_ports:
        with pytest.raises(URLValidationError, match="Only ports 80 and 443 are supported"):
            URLValidator.validate_url(url)


def test_url_validator_blocks_forbidden_destinations():
    """Verify localhost, private, loopback, link-local, and metadata IPs are blocked."""
    forbidden_urls = [
        "http://localhost/",
        "http://localhost.localdomain/",
        "http://sub.localhost/",
        "http://app.internal/",
        "http://metadata.google.internal/",
        "http://127.0.0.1/",
        "http://127.0.0.2/",
        "http://10.0.0.1/",
        "http://172.16.0.1/",
        "http://172.31.255.255/",
        "http://192.168.1.1/",
        "http://[::1]/",
        "http://[fe80::1]/",
        "http://[fc00::1]/",
        "http://169.254.169.254/latest/meta-data/",
        # Alternative IP notations
        "http://2130706433/",            # Integer for 127.0.0.1
        "http://0x7f000001/",            # Hex for 127.0.0.1
        "http://0177.0.0.1/",            # Octal 127.0.0.1
        "http://[::ffff:127.0.0.1]/",    # IPv4-mapped IPv6
        "http://[::ffff:169.254.169.254]/",
        "http://0.0.0.0/",
    ]
    for url in forbidden_urls:
        with pytest.raises(URLValidationError):
            URLValidator.validate_url(url)


def test_url_validator_blocks_hostname_resolving_to_forbidden_ip():
    """Verify hostname that resolves to a private or loopback IP is blocked."""
    mock_resolver_loopback = lambda host, port: ["127.0.0.1"]
    with pytest.raises(URLValidationError, match="resolves to forbidden IP"):
        URLValidator.validate_url("http://spoofed.example.com/", dns_resolver=mock_resolver_loopback)

    # Dual stack with one forbidden IP
    mock_resolver_mixed = lambda host, port: ["93.184.216.34", "10.0.0.1"]
    with pytest.raises(URLValidationError, match="resolves to forbidden IP"):
        URLValidator.validate_url("http://mixed.example.com/", dns_resolver=mock_resolver_mixed)


def test_url_validator_blocks_unresolvable_hostname():
    """Verify DNS resolution failure raises a clean error."""
    def failing_resolver(host, port):
        raise ValueError("NXDOMAIN")

    with pytest.raises(URLValidationError, match="DNS resolution failed"):
        URLValidator.validate_url("http://nonexistent.invalid/", dns_resolver=failing_resolver)


# ==============================================================================
# 2. HTMLTextExtractor Tests
# ==============================================================================

def test_html_text_extractor_normalizes_content_and_removes_boilerplate():
    """Verify extractor extracts title, main text, and strips boilerplate tags."""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>   International Scholarships 2026   </title>
        <style>body { font-size: 14px; }</style>
        <script>console.log("tracking code");</script>
    </head>
    <body>
        <header><nav><a href="/">Home</a> <a href="/about">About</a></nav></header>
        <main>
            <h1>Full Master's Scholarships</h1>
            <p>We offer <strong>merit-based</strong> scholarships for international students.</p>
            <p>Eligibility requires a bachelor's degree in engineering.</p>
        </main>
        <aside>Related articles</aside>
        <footer>Copyright 2026 University. All rights reserved.</footer>
    </body>
    </html>
    """
    title, text, warnings = HTMLTextExtractor.extract(html, max_length=1000)
    assert title == "International Scholarships 2026"
    assert "Full Master's Scholarships" in text
    assert "merit-based" in text
    # Verify boilerplate elements are removed
    assert "tracking code" not in text
    assert "font-size" not in text
    assert "Home" not in text
    assert "Copyright" not in text
    assert len(warnings) == 0


def test_html_text_extractor_handles_empty_and_malformed_html():
    """Verify extractor safely handles empty and malformed HTML."""
    # Empty string
    title, text, warnings = HTMLTextExtractor.extract("")
    assert title is None
    assert text == ""
    assert "empty" in warnings[0].lower()

    # Pure whitespace
    title, text, warnings = HTMLTextExtractor.extract("    \n\t   ")
    assert title is None
    assert text == ""

    # Malformed HTML fragment
    title, text, warnings = HTMLTextExtractor.extract("<div><p>Unclosed paragraph")
    assert "Unclosed paragraph" in text


def test_html_text_extractor_enforces_length_limit():
    """Verify text exceeding max_length is cleanly truncated with a warning."""
    long_html = "<html><body><p>" + ("A" * 500) + "</p></body></html>"
    title, text, warnings = HTMLTextExtractor.extract(long_html, max_length=100)
    assert len(text) == 100
    assert any("truncated" in w for w in warnings)


# ==============================================================================
# 3. PageFetcher Retrieval & SSRF Defense Tests
# ==============================================================================

@pytest.mark.anyio
async def test_page_fetcher_retrieves_public_html_successfully():
    """Verify successful retrieval and text extraction from a public page."""
    html_response = "<html><head><title>DAAD Study</title></head><body><h1>Scholarships in Germany</h1><p>Information on master's funding.</p></body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            headers={"Content-Type": "text/html; charset=utf-8"},
            content=html_response.encode("utf-8"),
        )

    mock_transport = httpx.MockTransport(handler)
    mock_dns = lambda host, port: ["93.184.216.34"]

    fetcher = PageFetcher(dns_resolver=mock_dns, transport=mock_transport)
    result = await fetcher.fetch("https://www.daad.de/en/")

    assert result.status == RetrievalStatus.SUCCESS
    assert result.http_status == 200
    assert result.title == "DAAD Study"
    assert "Scholarships in Germany" in (result.extracted_text or "")
    assert "Information on master's funding" in (result.extracted_text or "")
    assert result.error_message is None


@pytest.mark.anyio
async def test_page_fetcher_blocks_ssrf_initial_url():
    """Verify SSRF attempt on initial URL is rejected immediately with BLOCKED_URL."""
    fetcher = PageFetcher()
    result = await fetcher.fetch("http://169.254.169.254/latest/meta-data/")
    assert result.status == RetrievalStatus.BLOCKED_URL
    assert "blocked" in (result.error_message or "").lower()
    assert result.extracted_text is None


@pytest.mark.anyio
async def test_page_fetcher_blocks_redirect_to_forbidden_destination():
    """Verify redirect to private/internal destination is blocked."""
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://public.example.com/redirect":
            return httpx.Response(
                status_code=302,
                headers={"Location": "http://127.0.0.1:80/admin-console"},
            )
        return httpx.Response(status_code=200, text="Internal secret!")

    mock_transport = httpx.MockTransport(handler)
    mock_dns = lambda host, port: ["93.184.216.34"]

    fetcher = PageFetcher(dns_resolver=mock_dns, transport=mock_transport)
    result = await fetcher.fetch("https://public.example.com/redirect")

    assert result.status == RetrievalStatus.BLOCKED_URL
    assert "redirect" in (result.error_message or "").lower()
    assert result.extracted_text is None


@pytest.mark.anyio
async def test_page_fetcher_enforces_redirect_limit():
    """Verify redirect loop exceeding max_redirects is halted."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=302, headers={"Location": "/loop"})

    mock_transport = httpx.MockTransport(handler)
    mock_dns = lambda host, port: ["93.184.216.34"]

    fetcher = PageFetcher(dns_resolver=mock_dns, transport=mock_transport, max_redirects=2)
    result = await fetcher.fetch("https://public.example.com/loop")

    assert result.status == RetrievalStatus.BLOCKED_URL
    assert "redirect limit" in (result.error_message or "").lower()


@pytest.mark.anyio
async def test_page_fetcher_rejects_unsupported_content_type():
    """Verify non-HTML content types like PDF are rejected without downloading."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            headers={"Content-Type": "application/pdf"},
            content=b"%PDF-1.4 dummy binary",
        )

    mock_transport = httpx.MockTransport(handler)
    mock_dns = lambda host, port: ["93.184.216.34"]

    fetcher = PageFetcher(dns_resolver=mock_dns, transport=mock_transport)
    result = await fetcher.fetch("https://public.example.com/document.pdf")

    assert result.status == RetrievalStatus.UNSUPPORTED_CONTENT
    assert result.content_type == "application/pdf"
    assert "Only HTML is supported" in (result.error_message or "")


@pytest.mark.anyio
async def test_page_fetcher_enforces_response_size_limit():
    """Verify oversized response is truncated and marked PARTIAL_CONTENT."""
    # 200 KiB response with 50 KiB limit
    oversized_content = "<html><body><p>" + ("X" * (100 * 1024)) + "</p></body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            headers={"Content-Type": "text/html"},
            content=oversized_content.encode("utf-8"),
        )

    mock_transport = httpx.MockTransport(handler)
    mock_dns = lambda host, port: ["93.184.216.34"]

    fetcher = PageFetcher(dns_resolver=mock_dns, transport=mock_transport, max_bytes=32 * 1024)
    result = await fetcher.fetch("https://public.example.com/large-page")

    assert result.status == RetrievalStatus.PARTIAL_CONTENT
    assert any("truncated" in w for w in result.warnings)


@pytest.mark.anyio
async def test_page_fetcher_handles_http_error_and_timeout():
    """Verify non-200 HTTP statuses and timeouts return expected status codes."""
    # 404 Not Found
    def not_found_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=404, headers={"Content-Type": "text/html"}, text="Not Found")

    fetcher_404 = PageFetcher(dns_resolver=lambda h, p: ["93.184.216.34"], transport=httpx.MockTransport(not_found_handler))
    res_404 = await fetcher_404.fetch("https://public.example.com/notfound")
    assert res_404.status == RetrievalStatus.HTTP_ERROR
    assert res_404.http_status == 404

    # Timeout
    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Socket timed out")

    fetcher_timeout = PageFetcher(dns_resolver=lambda h, p: ["93.184.216.34"], transport=httpx.MockTransport(timeout_handler))
    res_timeout = await fetcher_timeout.fetch("https://public.example.com/timeout")
    assert res_timeout.status == RetrievalStatus.TIMEOUT
    assert "timed out" in (res_timeout.error_message or "").lower()


# ==============================================================================
# 4. TavilySearchProvider Tests
# ==============================================================================

@pytest.mark.anyio
async def test_tavily_search_unconfigured_without_api_key():
    """Verify provider returns PROVIDER_NOT_CONFIGURED when API key is missing."""
    provider = TavilySearchProvider(api_key=None)
    req = SearchRequest(query="Erasmus Mundus Computer Science scholarships")
    res = await provider.search(req)

    assert res.status == SearchStatus.PROVIDER_NOT_CONFIGURED
    assert res.results == []
    assert res.total_results == 0
    assert any("not configured" in w.lower() for w in res.warnings)


@pytest.mark.anyio
async def test_tavily_search_normalizes_valid_results():
    """Verify provider correctly normalizes successful search results."""
    mock_tavily_payload = {
        "results": [
            {
                "url": "https://www.daad.de/helmut-schmidt",
                "title": "DAAD Helmut-Schmidt-Programme",
                "content": "Fully funded master scholarships in Germany for public policy.",
                "score": 0.98,
                "published_date": "2026-01-15",
            },
            {
                "url": "https://study-in-germany.de/scholarships",
                "title": "German Master Funding",
                "content": "Overview of funding opportunities.",
                "score": 0.85,
            },
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        body = json.loads(request.read())
        assert body["query"] == "Germany scholarships"
        assert body["api_key"] == "test-valid-key"
        return httpx.Response(status_code=200, json=mock_tavily_payload)

    provider = TavilySearchProvider(api_key="test-valid-key", transport=httpx.MockTransport(handler))
    res = await provider.search(SearchRequest(query="Germany scholarships", max_results=5))

    assert res.status == SearchStatus.SUCCESS
    assert res.total_results == 2
    assert len(res.results) == 2

    first = res.results[0]
    assert first.url == "https://www.daad.de/helmut-schmidt"
    assert first.title == "DAAD Helmut-Schmidt-Programme"
    assert "Fully funded" in (first.snippet or "")
    assert first.score == 0.98
    assert first.published_date == "2026-01-15"


@pytest.mark.anyio
async def test_tavily_search_handles_auth_error_and_rate_limit():
    """Verify HTTP 401 auth failure and 429 rate limit are mapped to distinct typed statuses."""
    # 401 Auth error
    def auth_err_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=401, json={"detail": "Unauthorized"})

    provider_401 = TavilySearchProvider(api_key="bad-key", transport=httpx.MockTransport(auth_err_handler))
    res_401 = await provider_401.search(SearchRequest(query="test"))
    assert res_401.status == SearchStatus.AUTHENTICATION_ERROR
    assert "authentication failed" in (res_401.error_message or "").lower()

    # 429 Rate limit
    def rate_limit_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=429, json={"detail": "Rate limit exceeded"})

    provider_429 = TavilySearchProvider(api_key="key", transport=httpx.MockTransport(rate_limit_handler))
    res_429 = await provider_429.search(SearchRequest(query="test"))
    assert res_429.status == SearchStatus.RATE_LIMITED
    assert "rate limit" in (res_429.error_message or "").lower()


@pytest.mark.anyio
async def test_tavily_search_handles_malformed_response_and_errors():
    """Verify malformed JSON, server errors, and network failures fail safely."""
    # Malformed non-JSON
    def malformed_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, text="Not valid json {")

    provider_malformed = TavilySearchProvider(api_key="key", transport=httpx.MockTransport(malformed_handler))
    res_malformed = await provider_malformed.search(SearchRequest(query="test"))
    assert res_malformed.status == SearchStatus.MALFORMED_RESPONSE

    # Server error 500
    def server_err_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=500, text="Internal Server Error")

    provider_500 = TavilySearchProvider(api_key="key", transport=httpx.MockTransport(server_err_handler))
    res_500 = await provider_500.search(SearchRequest(query="test"))
    assert res_500.status == SearchStatus.PROVIDER_ERROR

    # Timeout
    def timeout_handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Timeout")

    provider_timeout = TavilySearchProvider(api_key="key", transport=httpx.MockTransport(timeout_handler))
    res_timeout = await provider_timeout.search(SearchRequest(query="test"))
    assert res_timeout.status == SearchStatus.TIMEOUT


# ==============================================================================
# 5. FastAPI Route Integration Tests
# ==============================================================================

def test_api_route_search_endpoint():
    """Verify POST /api/v1/research/search route executes and returns SearchResponse schema."""
    response = client.post(
        "/api/v1/research/search",
        json={"query": "International master scholarships", "max_results": 3},
    )
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["query"] == "International master scholarships"
    # In test environment without real key, returns provider_not_configured
    assert data["status"] in ["provider_not_configured", "success"]


def test_api_route_search_endpoint_rejects_invalid_payload():
    """Verify invalid search payload (empty query or out-of-range results) is rejected."""
    # Empty query
    res_empty = client.post("/api/v1/research/search", json={"query": "", "max_results": 5})
    assert res_empty.status_code == 422

    # max_results > 20
    res_too_many = client.post("/api/v1/research/search", json={"query": "valid", "max_results": 50})
    assert res_too_many.status_code == 422


def test_api_route_fetch_page_blocks_ssrf():
    """Verify POST /api/v1/research/fetch-page rejects SSRF attempt via API route."""
    response = client.post(
        "/api/v1/research/fetch-page",
        json={"url": "http://127.0.0.1/internal"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "blocked_url"
    assert "blocked" in (data["error_message"] or "").lower()
