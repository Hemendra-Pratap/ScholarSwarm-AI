import datetime
from datetime import timezone
import logging
import re
import urllib.parse
from app.schemas.common import UTCDateTime
from app.schemas.discovery import DiscoveredCandidate
from app.schemas.opportunity import FundingType
from app.schemas.research import (
    PageFetchResponse,
    RetrievalStatus,
    SearchRequest,
    SearchStatus,
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
from app.services.page_fetcher import PageFetcher
from app.services.search_provider import SearchProvider, TavilySearchProvider

logger = logging.getLogger(__name__)

# TLDs strongly associated with official educational and governmental institutions
GOVERNMENT_TLDS = {
    ".gov", ".gov.uk", ".gov.au", ".gov.in", ".gouv.fr", ".bund.de",
    ".gc.ca", ".gob.es", ".gob.mx", ".admin.ch",
}

EDUCATION_TLDS = {
    ".edu", ".ac.uk", ".edu.au", ".ac.jp", ".edu.cn", ".ac.in",
    ".edu.sg", ".ac.nz", ".edu.ca",
}

# Major known official scholarship administration bodies and university domains
OFFICIAL_ORGANIZATION_DOMAINS = {
    "daad.de", "campusfrance.org", "fulbrightprogram.org", "chevening.org",
    "erasmus-plus.ec.europa.eu", "sweden.se", "studyinholland.nl",
    "studyinsweden.se", "internationalscholarships.dhet.gov.za",
}

# Known third-party scholarship aggregators and search engines
THIRD_PARTY_DOMAINS = {
    "scholarshipportal.com", "scholars4dev.com", "findamasters.com",
    "masterstudies.com", "topuniversities.com", "timeshighereducation.com",
    "wemakescholars.com", "studyportals.com", "opportunitiesforafricans.com",
    "opportunitydesk.org", "afterschoolafrica.com", "iefa.org",
    "scholarshiproar.com", "scholarshipsads.com", "scholarshipdb.net",
}


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(timezone.utc)


def extract_netloc(url: str) -> str:
    """Extract lowercased network location (domain) without www or port."""
    try:
        parsed = urllib.parse.urlsplit(url.strip())
        netloc = (parsed.hostname or "").lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc
    except Exception:
        return ""


def find_verbatim_excerpt(text: str, match_pattern: str, window: int = 120) -> str | None:
    """Find a concise verbatim excerpt containing the regex pattern from retrieved page text."""
    if not text:
        return None
    match = re.search(match_pattern, text, re.IGNORECASE)
    if not match:
        return None
    start = max(0, match.start() - 30)
    end = min(len(text), match.end() + window)
    raw_excerpt = text[start:end]
    # Clean whitespace while preserving verbatim words
    clean_excerpt = " ".join(raw_excerpt.split())
    if start > 0:
        clean_excerpt = f"...{clean_excerpt}"
    if end < len(text):
        clean_excerpt = f"{clean_excerpt}..."
    return clean_excerpt[:300]


class OfficialSourceVerificationAgent:
    """Agent that verifies candidate opportunities against accessible official sources and extracts claim-level evidence."""

    def __init__(
        self,
        page_fetcher: PageFetcher | None = None,
        search_provider: SearchProvider | None = None,
    ):
        self.page_fetcher = page_fetcher or PageFetcher()
        self.search_provider = search_provider or TavilySearchProvider()

    def classify_source(
        self,
        url: str,
        page_title: str | None = None,
        institution_name: str | None = None,
    ) -> tuple[SourceClassification, str]:
        """Classify a web source as official, third_party, or uncertain based on domain and context."""
        netloc = extract_netloc(url)
        if not netloc:
            return SourceClassification.UNCERTAIN, "Unable to extract valid domain from URL."

        # 1. Known third-party aggregator check
        for tp in THIRD_PARTY_DOMAINS:
            if netloc == tp or netloc.endswith(f".{tp}"):
                return (
                    SourceClassification.THIRD_PARTY,
                    f"Domain '{netloc}' is a known commercial/third-party scholarship aggregator directory.",
                )

        # 2. Known official scholarship agency / government portal
        for off in OFFICIAL_ORGANIZATION_DOMAINS:
            if netloc == off or netloc.endswith(f".{off}"):
                return (
                    SourceClassification.OFFICIAL,
                    f"Domain '{netloc}' is an official government or recognized scholarship awarding organization.",
                )

        # 3. Government TLD match
        for gov_tld in GOVERNMENT_TLDS:
            if netloc.endswith(gov_tld):
                return (
                    SourceClassification.OFFICIAL,
                    f"Domain '{netloc}' is a verified government-controlled top-level domain ({gov_tld}).",
                )

        # 4. Accredited education TLD match
        for edu_tld in EDUCATION_TLDS:
            if netloc.endswith(edu_tld):
                return (
                    SourceClassification.OFFICIAL,
                    f"Domain '{netloc}' belongs to an accredited higher education institution ({edu_tld}).",
                )

        # 5. Check if institution name plausibly matches domain with non-generic tokens
        GENERIC_INST_WORDS = {"city", "global", "international", "college", "university", "institute", "school", "academy", "foundation", "center", "centre"}
        if institution_name and len(institution_name.strip()) >= 4:
            inst_tokens = [w.lower() for w in re.findall(r"[a-zA-Z0-9]+", institution_name) if len(w) >= 3 and w.lower() not in GENERIC_INST_WORDS]
            clean_domain = re.sub(r"[^a-zA-Z0-9]", "", netloc.split(".")[0]).lower()
            # Require at least one distinctive (non-generic) token of >= 4 chars to match or full institution name match
            if inst_tokens:
                distinctive_match = any(t in clean_domain for t in inst_tokens if len(t) >= 4)
                if distinctive_match:
                    return (
                        SourceClassification.OFFICIAL,
                        f"Domain '{netloc}' directly corroborates named institution '{institution_name}'.",
                    )
            elif clean_domain and clean_domain in re.sub(r"[^a-zA-Z0-9]", "", institution_name).lower() and len(clean_domain) >= 6:
                return (
                    SourceClassification.OFFICIAL,
                    f"Domain '{netloc}' directly corroborates named institution '{institution_name}'.",
                )

        return (
            SourceClassification.UNCERTAIN,
            f"Domain '{netloc}' could not be definitively confirmed as an official institutional or government source.",
        )

    async def search_for_official_source(self, candidate: DiscoveredCandidate) -> str | None:
        """Search for an official source using a single bounded query if the candidate source is not official."""
        opp = candidate.opportunity
        name = opp.name.strip() if opp.name else ""
        inst = opp.institution.strip() if opp.institution and opp.institution != "Unknown Organization" else ""

        # Construct concise official query
        query_terms = [name]
        if inst and inst.lower() not in name.lower():
            query_terms.append(inst)
        query_terms.append("official scholarship application")
        query = " ".join(" ".join(query_terms).split())[:200]

        try:
            search_req = SearchRequest(
                query=query,
                max_results=3,
                search_depth="basic",
            )
            resp = await self.search_provider.search(search_req)
            if resp.status != SearchStatus.SUCCESS or not resp.results:
                return None

            # Find the first result that classifies as official
            for item in resp.results:
                classification, _ = self.classify_source(item.url, item.title, inst)
                if classification == SourceClassification.OFFICIAL:
                    return item.url
            return None
        except Exception:
            logger.warning("Official-source search failed for candidate: %s", name, exc_info=True)
            return None

    def assess_claims(
        self,
        candidate: DiscoveredCandidate,
        official_url: str,
        page_text: str,
    ) -> list[ClaimAssessment]:
        """Assess individual candidate claims deterministically against fetched official text."""
        claims: list[ClaimAssessment] = []
        opp = candidate.opportunity

        # Claim 1: Opportunity / Scholarship Name
        claimed_name = opp.name.strip()
        STOP_WORDS = {"international", "scholarship", "scholarships", "program", "programme", "award", "fellowship", "grants", "master", "masters"}
        all_words = [w for w in re.findall(r"\w+", claimed_name) if len(w) > 2]
        distinctive_words = [w for w in all_words if len(w) > 3 and w.lower() not in STOP_WORDS]

        # Use distinctive words if available, otherwise check for a multi-word sequence
        if distinctive_words:
            # Check for any distinctive word
            found_word = None
            found_excerpt = None
            for dw in distinctive_words:
                pattern = r"\b" + re.escape(dw) + r"\b"
                excerpt = find_verbatim_excerpt(page_text, pattern)
                if excerpt:
                    found_word = dw
                    found_excerpt = excerpt
                    break

            if found_excerpt and found_word:
                claims.append(
                    ClaimAssessment(
                        claim_type="opportunity_name",
                        claimed_value=claimed_name,
                        outcome=ClaimOutcome.SUPPORTED,
                        source_url=official_url,
                        excerpt=found_excerpt,
                        explanation=f"Official page mentions key distinctive term '{found_word}' from scholarship name.",
                    )
                )
            else:
                claims.append(
                    ClaimAssessment(
                        claim_type="opportunity_name",
                        claimed_value=claimed_name,
                        outcome=ClaimOutcome.NOT_FOUND,
                        source_url=official_url,
                        excerpt=None,
                        explanation="Distinctive terms of opportunity name were not found on the official page.",
                    )
                )
        elif len(all_words) >= 2:
            # If all words are generic, require at least a two-word phrase match
            phrase = f"{all_words[0]}\\s+{all_words[1]}"
            excerpt = find_verbatim_excerpt(page_text, phrase)
            if excerpt:
                claims.append(
                    ClaimAssessment(
                        claim_type="opportunity_name",
                        claimed_value=claimed_name,
                        outcome=ClaimOutcome.SUPPORTED,
                        source_url=official_url,
                        excerpt=excerpt,
                        explanation=f"Official page mentions name phrase '{all_words[0]} {all_words[1]}'.",
                    )
                )
            else:
                claims.append(
                    ClaimAssessment(
                        claim_type="opportunity_name",
                        claimed_value=claimed_name,
                        outcome=ClaimOutcome.NOT_FOUND,
                        source_url=official_url,
                        excerpt=None,
                        explanation="Opportunity name phrase was not found on the official page.",
                    )
                )
        else:
            claims.append(
                ClaimAssessment(
                    claim_type="opportunity_name",
                    claimed_value=claimed_name,
                    outcome=ClaimOutcome.AMBIGUOUS,
                    source_url=official_url,
                    excerpt=None,
                    explanation="Claimed opportunity name lacks specific identifiable terms.",
                )
            )

        # Claim 2: Institution
        claimed_inst = opp.institution.strip() if opp.institution else None
        if claimed_inst and claimed_inst != "Unknown Organization":
            inst_words = [w for w in re.findall(r"\w+", claimed_inst) if len(w) > 3]
            inst_pattern = r"\b" + re.escape(inst_words[0]) + r"\b" if inst_words else re.escape(claimed_inst)
            excerpt = find_verbatim_excerpt(page_text, inst_pattern)
            if excerpt:
                claims.append(
                    ClaimAssessment(
                        claim_type="institution",
                        claimed_value=claimed_inst,
                        outcome=ClaimOutcome.SUPPORTED,
                        source_url=official_url,
                        excerpt=excerpt,
                        explanation=f"Official source mentions institution '{claimed_inst}'.",
                    )
                )
            else:
                claims.append(
                    ClaimAssessment(
                        claim_type="institution",
                        claimed_value=claimed_inst,
                        outcome=ClaimOutcome.NOT_FOUND,
                        source_url=official_url,
                        excerpt=None,
                        explanation=f"Institution '{claimed_inst}' was not confirmed in official page body.",
                    )
                )
        else:
            claims.append(
                ClaimAssessment(
                    claim_type="institution",
                    claimed_value=None,
                    outcome=ClaimOutcome.NOT_FOUND,
                    source_url=official_url,
                    excerpt=None,
                    explanation="Candidate opportunity did not claim a specific institution.",
                )
            )

        # Claim 3: Destination Country
        claimed_country = opp.destination_country.strip() if opp.destination_country else None
        if claimed_country and claimed_country != "International / Multiple":
            country_pattern = r"\b" + re.escape(claimed_country) + r"\b"
            excerpt = find_verbatim_excerpt(page_text, country_pattern)
            if excerpt:
                claims.append(
                    ClaimAssessment(
                        claim_type="destination_country",
                        claimed_value=claimed_country,
                        outcome=ClaimOutcome.SUPPORTED,
                        source_url=official_url,
                        excerpt=excerpt,
                        explanation=f"Destination country '{claimed_country}' confirmed on official page.",
                    )
                )
            else:
                claims.append(
                    ClaimAssessment(
                        claim_type="destination_country",
                        claimed_value=claimed_country,
                        outcome=ClaimOutcome.NOT_FOUND,
                        source_url=official_url,
                        excerpt=None,
                        explanation=f"Country '{claimed_country}' was not explicitly mentioned in page body.",
                    )
                )

        # Claim 4: Funding Details
        claimed_funding = opp.funding
        if claimed_funding and claimed_funding.funding_type != FundingType.UNKNOWN:
            f_type_str = claimed_funding.funding_type.value
            # Search for full/partial funding proof
            if f_type_str == FundingType.FULL.value:
                funding_pattern = r"\b(fully?\s*funded|full\s*tuition|covers?\s*tuition|full\s*scholarship)\b"
                contra_pattern = r"\b(partial\s*scholarship|tuition\s*only|does\s*not\s*cover\s*living)\b"
            else:
                funding_pattern = r"\b(partially?\s*funded|partial\s*scholarship|tuition\s*waiver)\b"
                contra_pattern = r"\b(fully?\s*funded|full\s*scholarship)\b"

            excerpt = find_verbatim_excerpt(page_text, funding_pattern)
            if excerpt:
                claims.append(
                    ClaimAssessment(
                        claim_type="funding",
                        claimed_value=f"Funding type: {f_type_str}",
                        outcome=ClaimOutcome.SUPPORTED,
                        source_url=official_url,
                        excerpt=excerpt,
                        explanation=f"Official page explicitly supports {f_type_str} funding offer.",
                    )
                )
            else:
                # Check for explicit contradiction
                contra_excerpt = find_verbatim_excerpt(page_text, contra_pattern)
                if contra_excerpt:
                    claims.append(
                        ClaimAssessment(
                            claim_type="funding",
                            claimed_value=f"Funding type: {f_type_str}",
                            outcome=ClaimOutcome.CONTRADICTED,
                            source_url=official_url,
                            excerpt=contra_excerpt,
                            explanation=f"Official text states contrasting funding terms.",
                        )
                    )
                else:
                    claims.append(
                        ClaimAssessment(
                            claim_type="funding",
                            claimed_value=f"Funding type: {f_type_str}",
                            outcome=ClaimOutcome.NOT_FOUND,
                            source_url=official_url,
                            excerpt=None,
                            explanation="Official page does not contain verifiable funding package language.",
                        )
                    )
        else:
            claims.append(
                ClaimAssessment(
                    claim_type="funding",
                    claimed_value="Unknown / Unspecified",
                    outcome=ClaimOutcome.NOT_FOUND,
                    source_url=official_url,
                    excerpt=None,
                    explanation="Candidate had no claimed funding terms to verify.",
                )
            )

        # Claim 5: Deadline Verification
        # Look for explicit deadline keywords in retrieved text
        deadline_pattern = r"\b(?:deadline|closing\s*date|apply\s*by|applications?\s*close)[:\s]+([A-Za-z0-9\s,\.]{4,30})"
        deadline_excerpt = find_verbatim_excerpt(page_text, deadline_pattern)
        if deadline_excerpt:
            claims.append(
                ClaimAssessment(
                    claim_type="deadline",
                    claimed_value=opp.deadline.isoformat() if opp.deadline else "None claimed",
                    outcome=ClaimOutcome.SUPPORTED if opp.deadline else ClaimOutcome.AMBIGUOUS,
                    source_url=official_url,
                    excerpt=deadline_excerpt,
                    explanation="Official application deadline found on page.",
                )
            )
        else:
            claims.append(
                ClaimAssessment(
                    claim_type="deadline",
                    claimed_value=opp.deadline.isoformat() if opp.deadline else None,
                    outcome=ClaimOutcome.NOT_FOUND,
                    source_url=official_url,
                    excerpt=None,
                    explanation="No explicit application deadline statement located in page text.",
                )
            )

        # Claim 6: Eligibility Requirements
        elig_pattern = r"\b(?:eligibility|requirements|eligible\s*candidates|criteria)[:\s]+([A-Za-z0-9\s,\.]{4,40})"
        elig_excerpt = find_verbatim_excerpt(page_text, elig_pattern)
        if elig_excerpt:
            claims.append(
                ClaimAssessment(
                    claim_type="eligibility_requirements",
                    claimed_value="General student eligibility",
                    outcome=ClaimOutcome.SUPPORTED,
                    source_url=official_url,
                    excerpt=elig_excerpt,
                    explanation="Official eligibility criteria section identified on page.",
                )
            )
        else:
            claims.append(
                ClaimAssessment(
                    claim_type="eligibility_requirements",
                    claimed_value="General student eligibility",
                    outcome=ClaimOutcome.NOT_FOUND,
                    source_url=official_url,
                    excerpt=None,
                    explanation="No designated eligibility section located on official page.",
                )
            )

        return claims

    async def verify_candidate(self, candidate: DiscoveredCandidate) -> CandidateVerificationReport:
        """Verify an individual candidate opportunity through safe page fetching and claim evaluation."""
        now = utcnow()
        source_assessments: list[SourceAssessment] = []
        warnings: list[str] = []
        primary_url = candidate.source_url.strip()

        # 1. Fetch initial source page
        fetch_resp = await self.page_fetcher.fetch(primary_url)
        classification, class_reason = self.classify_source(
            primary_url,
            fetch_resp.title,
            candidate.opportunity.institution,
        )

        source_assessments.append(
            SourceAssessment(
                source_url=primary_url,
                title=fetch_resp.title,
                retrieval_status=fetch_resp.status.value,
                classification=classification,
                reason=class_reason,
                retrieved_at=fetch_resp.retrieved_at,
                is_discovered_official_source=False,
                warnings=fetch_resp.warnings,
            )
        )

        official_url: str | None = None
        official_page_text: str | None = None

        if fetch_resp.status == RetrievalStatus.SUCCESS and classification == SourceClassification.OFFICIAL:
            official_url = fetch_resp.final_url or primary_url
            official_page_text = fetch_resp.extracted_text or ""
        else:
            # Source was inaccessible, third-party, or uncertain; attempt single official source discovery search
            warnings.append(f"Initial source '{primary_url}' was {classification.value} (status: {fetch_resp.status.value}).")
            discovered_official_url = await self.search_for_official_source(candidate)

            if discovered_official_url:
                second_fetch = await self.page_fetcher.fetch(discovered_official_url)
                sec_class, sec_reason = self.classify_source(
                    discovered_official_url,
                    second_fetch.title,
                    candidate.opportunity.institution,
                )
                source_assessments.append(
                    SourceAssessment(
                        source_url=discovered_official_url,
                        title=second_fetch.title,
                        retrieval_status=second_fetch.status.value,
                        classification=sec_class,
                        reason=sec_reason,
                        retrieved_at=second_fetch.retrieved_at,
                        is_discovered_official_source=True,
                        warnings=second_fetch.warnings,
                    )
                )

                if second_fetch.status == RetrievalStatus.SUCCESS and sec_class == SourceClassification.OFFICIAL:
                    official_url = second_fetch.final_url or discovered_official_url
                    official_page_text = second_fetch.extracted_text or ""
                else:
                    warnings.append(f"Discovered secondary source '{discovered_official_url}' was not an accessible official page.")
            else:
                warnings.append("No official institutional source could be located via discovery search.")

        # 2. Evaluate Claims or report inaccessibility/unverified
        if official_url and official_page_text:
            claims = self.assess_claims(candidate, official_url, official_page_text)
            
            # Determine overall report status
            supported_count = sum(1 for c in claims if c.outcome == ClaimOutcome.SUPPORTED)
            contradicted_count = sum(1 for c in claims if c.outcome == ClaimOutcome.CONTRADICTED)

            if contradicted_count > 0:
                overall_status = VerificationReportStatus.CONFLICTING
            elif supported_count >= 2:
                overall_status = VerificationReportStatus.VERIFIED
            elif supported_count == 1:
                overall_status = VerificationReportStatus.PARTIALLY_VERIFIED
            else:
                overall_status = VerificationReportStatus.UNVERIFIED

            return CandidateVerificationReport(
                candidate_name=candidate.opportunity.name,
                original_source_url=candidate.source_url,
                overall_status=overall_status,
                source_assessments=source_assessments,
                claim_assessments=claims,
                verified_official_url=official_url,
                warnings=warnings,
                verified_at=now,
            )

        # Inaccessible or unconfirmed official source
        is_inaccessible = any(
            sa.retrieval_status in (RetrievalStatus.BLOCKED_URL.value, RetrievalStatus.HTTP_ERROR.value, RetrievalStatus.TIMEOUT.value)
            for sa in source_assessments
        )
        overall_status = (
            VerificationReportStatus.SOURCE_INACCESSIBLE
            if is_inaccessible
            else VerificationReportStatus.UNVERIFIED
        )

        return CandidateVerificationReport(
            candidate_name=candidate.opportunity.name,
            original_source_url=candidate.source_url,
            overall_status=overall_status,
            source_assessments=source_assessments,
            claim_assessments=[],
            verified_official_url=None,
            warnings=warnings,
            verified_at=now,
        )

    async def verify(self, request: VerificationRequest) -> VerificationResponse:
        """Process verification workflow for a bounded batch of candidates (max 10)."""
        exec_time = utcnow()
        reports: list[CandidateVerificationReport] = []
        overall_warnings: list[str] = []

        for cand in request.candidates:
            try:
                report = await self.verify_candidate(cand)
                reports.append(report)
            except Exception as e:
                logger.exception("Unexpected error verifying candidate '%s'", cand.opportunity.name)
                # Ensure isolated candidate failure does not abort remaining candidates
                reports.append(
                    CandidateVerificationReport(
                        candidate_name=cand.opportunity.name,
                        original_source_url=cand.source_url,
                        overall_status=VerificationReportStatus.UNVERIFIED,
                        source_assessments=[],
                        claim_assessments=[],
                        verified_official_url=None,
                        warnings=[f"Verification failed due to internal error: {str(e)}"],
                        verified_at=exec_time,
                    )
                )
                overall_warnings.append(f"Candidate '{cand.opportunity.name}' verification encountered an unexpected error.")

        return VerificationResponse(
            reports=reports,
            total_candidates_processed=len(reports),
            executed_at=exec_time,
            warnings=overall_warnings,
        )
