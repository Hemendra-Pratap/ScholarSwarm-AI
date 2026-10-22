from datetime import datetime, timezone
import logging
from typing import Any
import uuid

from sqlalchemy.orm import Session

from app.graph.orchestrator import build_orchestrator_graph
from app.graph.state import (
    MultiAgentWorkflowState,
    WorkflowEvent,
    WorkflowEventType,
    WorkflowStage,
)
from app.models.entities import ResearchRunModel, StudentProfileModel
from app.schemas.discovery import DiscoveredCandidate, DiscoveryRequest, DiscoveryStatus
from app.schemas.eligibility import EligibilityAuditResponse, EvaluatedCriterion
from app.schemas.ranking import RankingResponse
from app.schemas.research_run import ResearchRunRead, ResearchRunStatus
from app.schemas.student_profile import StudentProfileBase
from app.schemas.verification import CandidateVerificationReport
from app.services.discovery_agent import ScholarshipDiscoveryAgent
from app.services.eligibility_agent import EligibilityAuditAgent
from app.services.ranking_agent import RankingAndStrategyAgent
from app.services.verification_agent import OfficialSourceVerificationAgent

logger = logging.getLogger(__name__)


class OrchestrationRunRequest(MultiAgentWorkflowState.__annotations__["discovery_request"].__base__ if False else object):
    pass


class OrchestrationService:
    """
    Independent orchestration service coordinating multi-agent research runs.
    Callable with or without FastAPI dependencies.
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
        self.graph = build_orchestrator_graph(
            discovery_agent=discovery_agent,
            verification_agent=verification_agent,
            eligibility_agent=eligibility_agent,
            ranking_agent=ranking_agent,
        )

    async def execute_run(
        self,
        student_profile: StudentProfileBase,
        discovery_request: DiscoveryRequest,
        profile_id: str | None = None,
        max_shortlist_size: int = 5,
        reference_date: datetime | None = None,
        custom_criteria: list[EvaluatedCriterion] | None = None,
        db: Session | None = None,
    ) -> MultiAgentWorkflowState:
        """
        Execute an end-to-end multi-agent orchestration run synchronously.
        Updates persistent ResearchRunModel if db session is provided.
        """
        run_uuid = uuid.uuid4()
        run_id_str = str(run_uuid)
        start_time = datetime.now(timezone.utc)

        # 1. Initialize persistent record if db session is available
        db_run: ResearchRunModel | None = None
        if db is not None:
            try:
                # Validate profile_id if given
                valid_profile_uuid = None
                if profile_id:
                    try:
                        valid_profile_uuid = uuid.UUID(profile_id)
                        # Confirm profile exists
                        db_p = db.query(StudentProfileModel).filter(StudentProfileModel.id == valid_profile_uuid).first()
                        if not db_p:
                            valid_profile_uuid = None
                    except ValueError:
                        valid_profile_uuid = None

                db_run = ResearchRunModel(
                    id=run_uuid,
                    profile_id=valid_profile_uuid,
                    status=ResearchRunStatus.RUNNING,
                    started_at=start_time,
                )
                db.add(db_run)
                db.commit()
                db.refresh(db_run)
            except Exception:
                logger.exception("Failed to initialize database research run record")
                db.rollback()
                db_run = None

        # 2. Build initial typed workflow state
        initial_state = MultiAgentWorkflowState(
            run_id=run_id_str,
            profile_id=profile_id,
            student_profile=student_profile,
            discovery_request=discovery_request,
            current_stage=WorkflowStage.INITIALIZATION,
            terminal_status=ResearchRunStatus.RUNNING,
            is_partial=False,
            max_shortlist_size=max_shortlist_size,
            reference_date=reference_date,
            custom_criteria=custom_criteria,
        )

        # 3. Execute LangGraph workflow
        final_state_dict = await self.graph.ainvoke(initial_state)

        # Ensure we have a MultiAgentWorkflowState instance
        if isinstance(final_state_dict, MultiAgentWorkflowState):
            final_state = final_state_dict
        elif isinstance(final_state_dict, dict):
            final_state = MultiAgentWorkflowState.model_validate(final_state_dict)
        else:
            final_state = initial_state

        end_time = datetime.now(timezone.utc)

        # 4. Synchronize persistent record if db was provided
        if db is not None and db_run is not None:
            try:
                db_run.status = final_state.terminal_status
                db_run.ended_at = end_time
                if final_state.sanitized_failure_info:
                    db_run.failure_summary = final_state.sanitized_failure_info
                elif final_state.warnings and final_state.terminal_status == ResearchRunStatus.PARTIAL:
                    db_run.failure_summary = "; ".join(final_state.warnings[:3])
                db.commit()
            except Exception:
                logger.exception("Failed to update database research run record on completion")
                db.rollback()

        return final_state
