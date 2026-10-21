import datetime
from datetime import timezone
import io
import re
import urllib.parse
from collections.abc import Callable
import httpx
import lxml.html
from app.core.config import settings
from app.schemas.research import PageFetchResponse, RetrievalStatus
from app.services.url_validator import URLValidationError, URLValidator


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(timezone.utc)


class HTMLTextExtractor:
    """Safe, non-executing HTML text and title extractor with boilerplate removal."""

    BOILERPLATE_TAGS = {
        "script",
        "style",
        "nav",
        "footer",
        "header",
        "aside",
        "noscript",
        "svg",
        "iframe",
        "form",
        "menu",
        "select",
    }

    @classmethod
    def extract(cls, html_content: str, max_length: int = 50000) -> tuple[str | None, str, list[str]]:
        """Extract title and cleaned body text from HTML string.
        
        Returns:
            tuple[str | None, str, list[str]]: Title, cleaned text, and warnings.
        """
        warnings: list[str] = []
        if not html_content or not html_content.strip():
            return None, "", ["Page HTML content is empty."]

        try:
            # lxml.html.fromstring parses full documents and fragments safely
            doc = lxml.html.fromstring(html_content)
        except Exception:
            return None, "", ["Malformed HTML could not be parsed into a document structure."]

        # 1. Extract title if present
        title: str | None = None
        try:
            title_elem = doc.find(".//title")
            if title_elem is not None and title_elem.text:
                title = re.sub(r"\s+", " ", title_elem.text).strip() or None
        except Exception:
            pass

        # 2. Drop boilerplate tags and their trees
        for tag in cls.BOILERPLATE_TAGS:
            try:
                for elem in doc.xpath(f"//{tag}"):
                    elem.drop_tree()
            except Exception:
                pass

        # 3. Extract text content
        try:
            raw_text = doc.text_content()
        except Exception:
            raw_text = ""

        # 4. Clean whitespace and collapse empty lines
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in raw_text.splitlines()]
        cleaned_lines: list[str] = []
        prev_blank = False
        for line in lines:
            if line:
                cleaned_lines.append(line)
                prev_blank = False
            elif not prev_blank:
                cleaned_lines.append("")
                prev_blank = True

        cleaned_text = "\n".join(cleaned_lines).strip()

        # 5. Enforce text length limit
        if len(cleaned_text) > max_length:
            cleaned_text = cleaned_text[:max_length]
            warnings.append(f"Extracted text exceeded maximum length and was truncated to {max_length} characters.")

        return title, cleaned_text, warnings


class PageFetcher:
    """Secure public web page retriever with strict SSRF defense, streaming limits, and redirect validation.
    
    Residual DNS-Rebinding Limitation Notice:
    Standard HTTP client connection pools (including httpx) execute an independent DNS lookup
    when opening the socket following pre-validation. An adversary with control over a sub-second
    TTL authoritative DNS server could theoretically return a valid public IP during pre-validation
    and a private IP upon socket creation. Full mitigation requires low-level socket pinning or
    custom resolver transport layers.
    """

    SUPPORTED_CONTENT_TYPES = (
        "text/html",
        "application/xhtml+xml",
    )

    def __init__(
        self,
        dns_resolver: Callable[[str, int], list[str]] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float | None = None,
        max_bytes: int | None = None,
        max_redirects: int | None = None,
        max_text_length: int | None = None,
    ):
        self.dns_resolver = dns_resolver
        self.transport = transport
        self.timeout = timeout or settings.RESEARCH_PAGE_FETCH_TIMEOUT_SECONDS
        self.max_bytes = max_bytes or settings.RESEARCH_PAGE_MAX_BYTES
        self.max_redirects = max_redirects or settings.RESEARCH_PAGE_MAX_REDIRECTS
        self.max_text_length = max_text_length or settings.RESEARCH_TEXT_MAX_LENGTH

    async def fetch(self, url: str, max_length: int | None = None) -> PageFetchResponse:
        """Fetch and extract text from a public web page securely."""
        text_limit = max_length or self.max_text_length
        warnings: list[str] = []
        current_url = url.strip()

        # 1. Validate initial URL
        try:
            current_url, _ = URLValidator.validate_url(current_url, dns_resolver=self.dns_resolver)
        except URLValidationError as e:
            return PageFetchResponse(
                status=RetrievalStatus.BLOCKED_URL,
                url=url,
                retrieved_at=utcnow(),
                error_message=f"URL validation failed: {str(e)}",
            )
        except Exception:
            return PageFetchResponse(
                status=RetrievalStatus.BLOCKED_URL,
                url=url,
                retrieved_at=utcnow(),
                error_message="Target URL is not permitted.",
            )

        redirect_count = 0
        final_url = current_url

        headers = {
            "User-Agent": f"{settings.APP_NAME}-ResearchBot/{settings.APP_VERSION} (Academic Research; Security-Compliant)",
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
            "Accept-Language": "en-US,en;q=0.9",
        }

        timeout_config = httpx.Timeout(
            connect=min(5.0, self.timeout),
            read=self.timeout,
            write=self.timeout,
            pool=5.0,
        )

        async with httpx.AsyncClient(
            transport=self.transport,
            timeout=timeout_config,
            follow_redirects=False,
            verify=True,
        ) as client:
            while True:
                try:
                    # Stream response to inspect headers and enforce bounded byte accumulation
                    async with client.stream("GET", current_url, headers=headers) as response:
                        status_code = response.status_code
                        raw_content_type = response.headers.get("content-type", "")
                        clean_content_type = raw_content_type.split(";")[0].strip().lower()

                        # Check for redirect status
                        if status_code in (301, 302, 303, 307, 308):
                            location = response.headers.get("location")
                            if not location:
                                return PageFetchResponse(
                                    status=RetrievalStatus.HTTP_ERROR,
                                    url=url,
                                    final_url=current_url,
                                    http_status=status_code,
                                    retrieved_at=utcnow(),
                                    error_message="Redirect response missing Location header.",
                                )

                            redirect_count += 1
                            if redirect_count > self.max_redirects:
                                return PageFetchResponse(
                                    status=RetrievalStatus.BLOCKED_URL,
                                    url=url,
                                    final_url=current_url,
                                    http_status=status_code,
                                    retrieved_at=utcnow(),
                                    error_message=f"Maximum redirect limit ({self.max_redirects}) exceeded.",
                                )

                            # Resolve relative redirect URLs safely
                            next_url = urllib.parse.urljoin(current_url, location)

                            # RE-VALIDATE REDIRECT DESTINATION FOR SSRF!
                            try:
                                next_url, _ = URLValidator.validate_url(next_url, dns_resolver=self.dns_resolver)
                            except URLValidationError as err:
                                return PageFetchResponse(
                                    status=RetrievalStatus.BLOCKED_URL,
                                    url=url,
                                    final_url=next_url,
                                    http_status=status_code,
                                    retrieved_at=utcnow(),
                                    error_message=f"Redirect blocked: {str(err)}",
                                )
                            except Exception:
                                return PageFetchResponse(
                                    status=RetrievalStatus.BLOCKED_URL,
                                    url=url,
                                    final_url=next_url,
                                    http_status=status_code,
                                    retrieved_at=utcnow(),
                                    error_message="Redirect to forbidden destination blocked.",
                                )

                            current_url = next_url
                            final_url = current_url
                            continue

                        # Validate content type: only HTML allowed in M4
                        if not any(supported in clean_content_type for supported in self.SUPPORTED_CONTENT_TYPES):
                            return PageFetchResponse(
                                status=RetrievalStatus.UNSUPPORTED_CONTENT,
                                url=url,
                                final_url=current_url,
                                content_type=raw_content_type or None,
                                http_status=status_code,
                                retrieved_at=utcnow(),
                                error_message=f"Unsupported content type '{clean_content_type}'. Only HTML is supported.",
                            )

                        # Check HTTP status
                        if status_code != 200:
                            return PageFetchResponse(
                                status=RetrievalStatus.HTTP_ERROR,
                                url=url,
                                final_url=current_url,
                                content_type=raw_content_type or None,
                                http_status=status_code,
                                retrieved_at=utcnow(),
                                error_message=f"HTTP request failed with status {status_code}.",
                            )

                        # Stream response bytes with hard ceiling
                        accumulated = bytearray()
                        is_truncated = False
                        async for chunk in response.aiter_bytes(chunk_size=16384):
                            accumulated.extend(chunk)
                            if len(accumulated) > self.max_bytes:
                                is_truncated = True
                                accumulated = accumulated[:self.max_bytes]
                                warnings.append(
                                    f"Response exceeded maximum allowable size ({self.max_bytes // 1024} KiB) and was truncated."
                                )
                                break

                        # Decode text
                        encoding = response.encoding or "utf-8"
                        try:
                            html_text = accumulated.decode(encoding)
                        except (UnicodeDecodeError, LookupError):
                            try:
                                html_text = accumulated.decode("utf-8", errors="replace")
                            except Exception:
                                html_text = accumulated.decode("latin-1", errors="replace")

                        # Extract title and text
                        title, extracted_text, ext_warnings = HTMLTextExtractor.extract(html_text, max_length=text_limit)
                        warnings.extend(ext_warnings)

                        retrieval_status = RetrievalStatus.PARTIAL_CONTENT if is_truncated else RetrievalStatus.SUCCESS

                        return PageFetchResponse(
                            status=retrieval_status,
                            url=url,
                            final_url=current_url,
                            title=title,
                            content_type=raw_content_type or None,
                            http_status=status_code,
                            extracted_text=extracted_text,
                            retrieved_at=utcnow(),
                            warnings=warnings,
                        )

                except httpx.TimeoutException:
                    return PageFetchResponse(
                        status=RetrievalStatus.TIMEOUT,
                        url=url,
                        final_url=current_url,
                        retrieved_at=utcnow(),
                        error_message="Page retrieval timed out.",
                    )
                except httpx.RequestError as e:
                    return PageFetchResponse(
                        status=RetrievalStatus.CONNECTION_ERROR,
                        url=url,
                        final_url=current_url,
                        retrieved_at=utcnow(),
                        error_message="Network connection failed during page retrieval.",
                    )
                except Exception:
                    return PageFetchResponse(
                        status=RetrievalStatus.MALFORMED_CONTENT,
                        url=url,
                        final_url=current_url,
                        retrieved_at=utcnow(),
                        error_message="An error occurred while reading page content.",
                    )
