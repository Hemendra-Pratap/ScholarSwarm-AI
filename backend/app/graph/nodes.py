from datetime import datetime, timezone
import logging
from typing import Any, Callable, Coroutine
import httpx
from pydantic import ValidationError

from app.graph.adapters import (
    adapt_candidate_and_audit_to_ranking_input,
    adapt_candidate_to_eligibility_criteria,
    build_candidate_key,
)
from app.graph.state import (
    MultiAgentWorkflowState,
    WorkflowEvent,
    WorkflowEventType,
    WorkflowStage,
)
from app.schemas.discovery import DiscoveryRequest, DiscoveryResponse, DiscoveryStatus
from app.schemas.eligibility import (
    EligibilityAuditRequest,
    EligibilityAuditResponse,
    OverallEligibilityClassification,
)
from app.schemas.ranking import (
    CandidateOpportunityInput,
    RankingRequest,
    RankingResponse,
)
from app.schemas.research_run import ResearchRunStatus
from app.schemas.verification import (
    CandidateVerificationReport,
    VerificationReportStatus,
    VerificationRequest,
    VerificationResponse,
)
from app.services.discovery_agent import ScholarshipDiscoveryAgent
from app.services.eligibility_agent import EligibilityAuditAgent
from app.services.ranking_agent import RankingAndStrategyAgent
from app.services.verification_agent import OfficialSourceVerificationAgent

logger = logging.getLogger(__name__)

# Configured bounded retry policy: small finite limit, only transient network / 429 / 5xx
MAX_TRANSIENT_RETRIES = 2


def is_transient_error(exc: Exception) -> bool:
    """Determine whether an exception is plausibly transient and safe to retry."""
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, httpx.ConnectError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code if exc.response is not None else 0
        if code in (429, 502, 503, 504):
            return True
    return False


def sanitize_error(exc: Exception) -> str:
    """Sanitize error to avoid leaking credentials, full tracebacks, internal file paths, or sensitive payload data."""
    if isinstance(exc, ValidationError):
        return "Validation failed on agent contract or input payload."
    if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
        return "External network request timed out."
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code if exc.response is not None else 0
        return f"External HTTP error {status} encountered."
    if isinstance(exc, (httpx.NetworkError, httpx.ConnectError)):
        return "External network connection error encountered."
    # Conservative safe fallback: do not expose arbitrary raw exception text or filesystem paths
    return "Service error: An unexpected internal service error occurred."


def emit_event(
    state: MultiAgentWorkflowState,
    event_type: WorkflowEventType,
    stage: WorkflowStage,
    message: str,
    retry_attempt: int | None = None,
    error_code: str | None = None,
) -> None:
    """Helper to emit and append a structured event to state."""
    seq = len(state.events) + 1
    event = WorkflowEvent(
        sequence_number=seq,
        run_id=state.run_id,
        stage=stage,
        event_type=event_type,
        timestamp=datetime.now(timezone.utc),
        message=message,
        retry_attempt=retry_attempt,
        error_code=error_code,
    )
    state.events.append(event)


class MultiAgentWorkflowNodes:
    """
    LangGraph node implementations coordinating M3, M4, M6, M7, and M8 agent services.
    Enforces candidate-level isolation, bounded retries, and honest partial results.
    """

    def __init__(
        self,
        discovery_agent: ScholarshipDiscoveryAgent,
        verification_agent: OfficialSourceVerificationAgent,
        eligibility_agent: EligibilityAuditAgent,
        ranking_agent: RankingAndStrategyAgent,
    ) -> None:
        self.discovery_agent = discovery_agent
        self.verification_agent = verification_agent
        self.eligibility_agent = eligibility_agent
        self.ranking_agent = ranking_agent

    async def _execute_with_retry(
        self,
        state: MultiAgentWorkflowState,
        stage_name: str,
        stage_enum: WorkflowStage,
        coro_factory: Callable[[], Coroutine[Any, Any, Any]],
    ) -> Any:
        """Execute a coroutine with bounded retries for transient errors only."""
        attempt = 0
        while True:
            try:
                return await coro_factory()
            except Exception as e:
                if is_transient_error(e) and attempt < MAX_TRANSIENT_RETRIES:
                    attempt += 1
                    state.retry_counts[stage_name] = attempt
                    emit_event(
                        state=state,
                        event_type=WorkflowEventType.STAGE_RETRYING,
                        stage=stage_enum,
                        message=f"Transient failure in {stage_name}: {sanitize_error(e)}. Retrying (attempt {attempt}/{MAX_TRANSIENT_RETRIES}).",
                        retry_attempt=attempt,
                        error_code="TRANSIENT_RETRY",
                    )
                    continue
                # Permanent error or retries exhausted
                raise

    async def validate_input_node(self, state: MultiAgentWorkflowState) -> MultiAgentWorkflowState:
        """Node 1: Validate input student profile and discovery request."""
        state.current_stage = WorkflowStage.VALIDATION
        emit_event(
            state=state,
            event_type=WorkflowEventType.STAGE_STARTED,
            stage=WorkflowStage.VALIDATION,
            message="Validating incoming student profile and discovery request context.",
        )

        try:
            # Pydantic validation: confirm student profile and discovery request
            if not state.discovery_request.query or len(state.discovery_request.query.strip()) < 2:
                raise ValueError("Discovery query is empty or too short.")
            
            emit_event(
                state=state,
                event_type=WorkflowEventType.STAGE_COMPLETED,
                stage=WorkflowStage.VALIDATION,
                message="Profile context and discovery request validated successfully.",
            )
        except Exception as e:
            sanitized = sanitize_error(e)
            state.terminal_status = ResearchRunStatus.FAILED
            state.current_stage = WorkflowStage.FAILED
            state.sanitized_failure_info = sanitized
            emit_event(
                state=state,
                event_type=WorkflowEventType.STAGE_FAILED,
                stage=WorkflowStage.VALIDATION,
                message=f"Validation failed: {sanitized}",
                error_code="VALIDATION_ERROR",
            )
        return state

    async def discovery_node(self, state: MultiAgentWorkflowState) -> MultiAgentWorkflowState:
        """Node 2: Discover scholarship opportunities using M4 discovery agent."""
        if state.terminal_status == ResearchRunStatus.FAILED:
            return state

        state.current_stage = WorkflowStage.DISCOVERY
        emit_event(
            state=state,
            event_type=WorkflowEventType.STAGE_STARTED,
            stage=WorkflowStage.DISCOVERY,
            message=f"Executing discovery with query: '{state.discovery_request.query}'.",
        )

        try:
            response: DiscoveryResponse = await self._execute_with_retry(
                state=state,
                stage_name="discovery",
                stage_enum=WorkflowStage.DISCOVERY,
                coro_factory=lambda: self.discovery_agent.discover(state.discovery_request),
            )
            state.discovery_status = response.status
            state.discovered_candidates = response.candidates
            if response.warnings:
                state.warnings.extend(response.warnings)

            if response.status == DiscoveryStatus.SUCCESS:
                emit_event(
                    state=state,
                    event_type=WorkflowEventType.STAGE_COMPLETED,
                    stage=WorkflowStage.DISCOVERY,
                    message=f"Discovered {len(response.candidates)} candidate opportunities.",
                )
            elif response.status == DiscoveryStatus.PARTIAL:
                state.is_partial = True
                emit_event(
                    state=state,
                    event_type=WorkflowEventType.STAGE_PARTIAL,
                    stage=WorkflowStage.DISCOVERY,
                    message=f"Discovery completed with partial results: {len(response.candidates)} candidates found.",
                )
            elif response.status in (DiscoveryStatus.NO_RESULTS, DiscoveryStatus.PROVIDER_UNAVAILABLE):
                # Honest terminal state without fabrication
                emit_event(
                    state=state,
                    event_type=WorkflowEventType.STAGE_COMPLETED,
                    stage=WorkflowStage.DISCOVERY,
                    message=f"Discovery returned no candidates (status: {response.status.value}).",
                )
                # Truthfully record explicit skip events for all downstream stages bypassed by empty discovery
                emit_event(
                    state=state,
                    event_type=WorkflowEventType.STAGE_SKIPPED,
                    stage=WorkflowStage.VERIFICATION,
                    message="Skipping verification: no candidate opportunities available.",
                )
                emit_event(
                    state=state,
                    event_type=WorkflowEventType.STAGE_SKIPPED,
                    stage=WorkflowStage.ELIGIBILITY,
                    message="Skipping eligibility audit: no candidate opportunities available.",
                )
                emit_event(
                    state=state,
                    event_type=WorkflowEventType.STAGE_SKIPPED,
                    stage=WorkflowStage.RANKING,
                    message="Skipping ranking: no candidate opportunities available.",
                )
            else:
                state.terminal_status = ResearchRunStatus.FAILED
                state.current_stage = WorkflowStage.FAILED
                state.sanitized_failure_info = response.error_message or "Discovery failed to yield results."
                emit_event(
                    state=state,
                    event_type=WorkflowEventType.STAGE_FAILED,
                    stage=WorkflowStage.DISCOVERY,
                    message=f"Discovery failed: {state.sanitized_failure_info}",
                    error_code="DISCOVERY_FAILED",
                )
        except Exception as e:
            sanitized = sanitize_error(e)
            state.terminal_status = ResearchRunStatus.FAILED
            state.current_stage = WorkflowStage.FAILED
            state.sanitized_failure_info = sanitized
            emit_event(
                state=state,
                event_type=WorkflowEventType.STAGE_FAILED,
                stage=WorkflowStage.DISCOVERY,
                message=f"Discovery error: {sanitized}",
                error_code="DISCOVERY_ERROR",
            )
        return state

    async def verification_node(self, state: MultiAgentWorkflowState) -> MultiAgentWorkflowState:
        """Node 3: Assess candidate claims against official sources using M6 verification agent."""
        if state.terminal_status == ResearchRunStatus.FAILED:
            return state

        # If no candidates discovered, skip verification honestly
        if not state.discovered_candidates:
            # Check if skip event was already emitted to prevent duplicate events
            if not any(e.stage == WorkflowStage.VERIFICATION and e.event_type == WorkflowEventType.STAGE_SKIPPED for e in state.events):
                emit_event(
                    state=state,
                    event_type=WorkflowEventType.STAGE_SKIPPED,
                    stage=WorkflowStage.VERIFICATION,
                    message="Skipping verification: no candidate opportunities available.",
                )
            return state

        state.current_stage = WorkflowStage.VERIFICATION
        # Enforce M6 candidate bounds: at most 10 candidates
        candidates_to_verify = state.discovered_candidates[:10]
        if len(state.discovered_candidates) > 10:
            state.warnings.append(
                f"Discovery returned {len(state.discovered_candidates)} candidates; bounded verification evaluated the first 10."
            )

        emit_event(
            state=state,
            event_type=WorkflowEventType.STAGE_STARTED,
            stage=WorkflowStage.VERIFICATION,
            message=f"Verifying {len(candidates_to_verify)} candidate opportunities against official sources.",
        )

        try:
            req = VerificationRequest(candidates=candidates_to_verify)
            response: VerificationResponse = await self._execute_with_retry(
                state=state,
                stage_name="verification",
                stage_enum=WorkflowStage.VERIFICATION,
                coro_factory=lambda: self.verification_agent.verify(req),
            )
            state.verification_reports = response.reports
            for rep in response.reports:
                state.candidate_verification_map[rep.candidate_name] = rep.overall_status

            if response.warnings:
                state.warnings.extend(response.warnings)

            emit_event(
                state=state,
                event_type=WorkflowEventType.STAGE_COMPLETED,
                stage=WorkflowStage.VERIFICATION,
                message=f"Verification completed for {response.total_candidates_processed} candidates.",
            )
        except Exception as e:
            # Verification failure does not erase discovery results!
            sanitized = sanitize_error(e)
            state.is_partial = True
            state.warnings.append(f"Official-source verification failed: {sanitized}")
            emit_event(
                state=state,
                event_type=WorkflowEventType.STAGE_PARTIAL,
                stage=WorkflowStage.VERIFICATION,
                message=f"Verification error: {sanitized}. Proceeding with unverified discovery data.",
                error_code="VERIFICATION_ERROR",
            )
        return state

    async def eligibility_node(self, state: MultiAgentWorkflowState) -> MultiAgentWorkflowState:
        """Node 4: Perform deterministic criterion evaluation using M7 eligibility audit agent."""
        if state.terminal_status == ResearchRunStatus.FAILED:
            return state

        # Skip if no candidates discovered
        if not state.discovered_candidates:
            if not any(e.stage == WorkflowStage.ELIGIBILITY and e.event_type == WorkflowEventType.STAGE_SKIPPED for e in state.events):
                emit_event(
                    state=state,
                    event_type=WorkflowEventType.STAGE_SKIPPED,
                    stage=WorkflowStage.ELIGIBILITY,
                    message="Skipping eligibility audit: no candidate opportunities available.",
                )
            return state

        state.current_stage = WorkflowStage.ELIGIBILITY
        candidates_to_assess = state.discovered_candidates[:10]

        emit_event(
            state=state,
            event_type=WorkflowEventType.STAGE_STARTED,
            stage=WorkflowStage.ELIGIBILITY,
            message=f"Auditing eligibility for {len(candidates_to_assess)} candidate opportunities.",
        )

        # Build verification report map keyed by collision-safe candidate key
        rep_map: dict[str, CandidateVerificationReport] = {}
        for rep in state.verification_reports:
            # Lookup candidate matching this report to extract institution
            cand_match = next((c for c in candidates_to_assess if c.opportunity.name.strip().lower() == rep.candidate_name.strip().lower()), None)
            inst = cand_match.opportunity.institution if cand_match else None
            key = build_candidate_key(rep.candidate_name, inst)
            rep_map[key] = rep

        assessments: list[EligibilityAuditResponse] = []
        had_individual_failures = False

        for cand in candidates_to_assess:
            opp_name = cand.opportunity.name
            key = build_candidate_key(opp_name, cand.opportunity.institution)
            v_report = rep_map.get(key)
            if v_report is None:
                # Fallback to name-only match if report lacked institution
                v_report = next((r for r in state.verification_reports if r.candidate_name.strip().lower() == opp_name.strip().lower()), None)
            
            # Use custom criteria if provided in state (for explicit tests), otherwise adapt candidate
            criteria = (
                state.custom_criteria
                if state.custom_criteria is not None
                else adapt_candidate_to_eligibility_criteria(cand, v_report)
            )

            try:
                audit_req = EligibilityAuditRequest(
                    opportunity_name=opp_name,
                    institution=cand.opportunity.institution,
                    student_profile=state.student_profile,
                    criteria=criteria,
                    verification_report=v_report,
                )
                audit_res: EligibilityAuditResponse = await self._execute_with_retry(
                    state=state,
                    stage_name=f"eligibility_{opp_name[:20]}",
                    stage_enum=WorkflowStage.ELIGIBILITY,
                    coro_factory=lambda req=audit_req: self.eligibility_agent.audit(req),
                )
                assessments.append(audit_res)
            except Exception as e:
                # Candidate-level isolation: failure for one candidate must not erase others!
                had_individual_failures = True
                sanitized = sanitize_error(e)
                state.warnings.append(f"Eligibility audit failed for '{opp_name}': {sanitized}")
                # Create an honest fallback unassessable response preserving candidate association
                fallback_res = EligibilityAuditResponse(
                    opportunity_name=opp_name,
                    institution=cand.opportunity.institution,
                    overall_classification=OverallEligibilityClassification.NOT_ASSESSABLE,
                    evaluated_criteria=[],
                    disqualifying_criteria=[],
                    unknown_criteria=["Eligibility evaluation failed during execution."],
                    evidence_caveats=[sanitized],
                    is_incomplete=True,
                    evaluated_at=datetime.now(timezone.utc),
                )
                assessments.append(fallback_res)

        state.eligibility_assessments = assessments

        if had_individual_failures:
            state.is_partial = True
            emit_event(
                state=state,
                event_type=WorkflowEventType.STAGE_PARTIAL,
                stage=WorkflowStage.ELIGIBILITY,
                message=f"Eligibility audit completed with partial failures across candidates ({len(assessments)} total assessed).",
            )
        else:
            emit_event(
                state=state,
                event_type=WorkflowEventType.STAGE_COMPLETED,
                stage=WorkflowStage.ELIGIBILITY,
                message=f"Eligibility audit completed for {len(assessments)} candidates.",
            )

        return state

    async def ranking_node(self, state: MultiAgentWorkflowState) -> MultiAgentWorkflowState:
        """Node 5: Rank opportunities and generate application strategy using M8 ranking agent."""
        if state.terminal_status == ResearchRunStatus.FAILED:
            return state

        # Skip ranking if no candidates discovered
        if not state.discovered_candidates:
            if not any(e.stage == WorkflowStage.RANKING and e.event_type == WorkflowEventType.STAGE_SKIPPED for e in state.events):
                emit_event(
                    state=state,
                    event_type=WorkflowEventType.STAGE_SKIPPED,
                    stage=WorkflowStage.RANKING,
                    message="Skipping ranking: no candidate opportunities available.",
                )
            # Finalize clean terminal status
            state.terminal_status = ResearchRunStatus.COMPLETED
            state.current_stage = WorkflowStage.COMPLETED
            return state

        state.current_stage = WorkflowStage.RANKING
        candidates_to_rank = state.discovered_candidates[:10]

        emit_event(
            state=state,
            event_type=WorkflowEventType.STAGE_STARTED,
            stage=WorkflowStage.RANKING,
            message=f"Ranking {len(candidates_to_rank)} candidates with profile-fit and eligibility gates.",
        )

        rep_map: dict[str, CandidateVerificationReport] = {}
        for rep in state.verification_reports:
            cand_match = next((c for c in candidates_to_rank if c.opportunity.name.strip().lower() == rep.candidate_name.strip().lower()), None)
            inst = cand_match.opportunity.institution if cand_match else None
            key = build_candidate_key(rep.candidate_name, inst)
            rep_map[key] = rep

        audit_map: dict[str, EligibilityAuditResponse] = {
            build_candidate_key(aud.opportunity_name, aud.institution): aud for aud in state.eligibility_assessments
        }

        # Build CandidateOpportunityInput items
        ranking_inputs: list[CandidateOpportunityInput] = []
        for cand in candidates_to_rank:
            opp_name = cand.opportunity.name
            key = build_candidate_key(opp_name, cand.opportunity.institution)
            v_rep = rep_map.get(key)
            if v_rep is None:
                v_rep = next((r for r in state.verification_reports if r.candidate_name.strip().lower() == opp_name.strip().lower()), None)
            aud_res = audit_map.get(key)
            if aud_res is None:
                aud_res = next((a for a in state.eligibility_assessments if a.opportunity_name.strip().lower() == opp_name.strip().lower()), None)
            cand_input = adapt_candidate_and_audit_to_ranking_input(cand, v_rep, aud_res)
            ranking_inputs.append(cand_input)

        try:
            ranking_req = RankingRequest(
                student_profile=state.student_profile,
                candidates=ranking_inputs,
                max_shortlist_size=state.max_shortlist_size,
                reference_date=state.reference_date,
            )
            ranking_res: RankingResponse = await self._execute_with_retry(
                state=state,
                stage_name="ranking",
                stage_enum=WorkflowStage.RANKING,
                coro_factory=lambda: self.ranking_agent.rank(ranking_req),
            )
            state.ranking_response = ranking_res
            if ranking_res.warnings:
                state.warnings.extend(ranking_res.warnings)

            emit_event(
                state=state,
                event_type=WorkflowEventType.STAGE_COMPLETED,
                stage=WorkflowStage.RANKING,
                message=f"Ranking generated {len(ranking_res.recommended_shortlist)} recommended and {len(ranking_res.needs_review_shortlist)} review opportunities.",
            )
            state.current_stage = WorkflowStage.COMPLETED
            state.terminal_status = ResearchRunStatus.PARTIAL if state.is_partial else ResearchRunStatus.COMPLETED
        except Exception as e:
            # If ranking fails, preserve earlier stage results (discovery, verification, eligibility)
            sanitized = sanitize_error(e)
            state.is_partial = True
            state.warnings.append(f"Ranking and application strategy could not run: {sanitized}")
            emit_event(
                state=state,
                event_type=WorkflowEventType.STAGE_PARTIAL,
                stage=WorkflowStage.RANKING,
                message=f"Ranking failed: {sanitized}. Previous research and audit results preserved.",
                error_code="RANKING_FAILED",
            )
            state.current_stage = WorkflowStage.COMPLETED
            state.terminal_status = ResearchRunStatus.PARTIAL

        return state
