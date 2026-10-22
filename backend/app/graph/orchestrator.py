import logging
from typing import Literal
from langgraph.graph import END, START, StateGraph

from app.graph.nodes import MultiAgentWorkflowNodes
from app.graph.state import MultiAgentWorkflowState, WorkflowStage
from app.schemas.discovery import DiscoveryStatus
from app.schemas.research_run import ResearchRunStatus
from app.services.discovery_agent import ScholarshipDiscoveryAgent
from app.services.eligibility_agent import EligibilityAuditAgent
from app.services.ranking_agent import RankingAndStrategyAgent
from app.services.verification_agent import OfficialSourceVerificationAgent

logger = logging.getLogger(__name__)


def route_after_validation(state: MultiAgentWorkflowState) -> Literal["discovery", "__end__"]:
    """Conditional edge after validation: proceeds to discovery only if validation succeeded."""
    if state.terminal_status == ResearchRunStatus.FAILED:
        return END
    return "discovery"


def route_after_discovery(state: MultiAgentWorkflowState) -> Literal["verification", "ranking", "__end__"]:
    """
    Conditional edge after discovery:
    - If discovery failed or errored: terminate immediately to avoid downstream fabrication.
    - If discovery succeeded or returned partial candidates: proceed to verification.
    - If discovery yielded no results / provider unconfigured: skip verification and eligibility, and proceed to ranking node (which cleanly finalizes state without executing ranking).
    """
    if state.terminal_status == ResearchRunStatus.FAILED:
        return END

    if not state.discovered_candidates or state.discovery_status in (
        DiscoveryStatus.NO_RESULTS,
        DiscoveryStatus.PROVIDER_UNAVAILABLE,
    ):
        # Empty discovery result skips downstream verification and eligibility calls
        return "ranking"

    return "verification"


def route_after_verification(state: MultiAgentWorkflowState) -> Literal["eligibility", "ranking", "__end__"]:
    """
    Conditional edge after verification:
    - If state is failed: terminate.
    - If candidates exist: proceed to eligibility audit.
    - Otherwise skip to ranking.
    """
    if state.terminal_status == ResearchRunStatus.FAILED:
        return END

    if not state.discovered_candidates:
        return "ranking"

    return "eligibility"


def route_after_eligibility(state: MultiAgentWorkflowState) -> Literal["ranking", "__end__"]:
    """
    Conditional edge after eligibility:
    - If state is failed: terminate.
    - Otherwise proceed to ranking.
    """
    if state.terminal_status == ResearchRunStatus.FAILED:
        return END
    return "ranking"


def build_orchestrator_graph(
    discovery_agent: ScholarshipDiscoveryAgent,
    verification_agent: OfficialSourceVerificationAgent,
    eligibility_agent: EligibilityAuditAgent,
    ranking_agent: RankingAndStrategyAgent,
):
    """
    Construct and compile the LangGraph StateGraph coordinating M1–M8 capabilities.
    """
    nodes = MultiAgentWorkflowNodes(
        discovery_agent=discovery_agent,
        verification_agent=verification_agent,
        eligibility_agent=eligibility_agent,
        ranking_agent=ranking_agent,
    )

    workflow = StateGraph(MultiAgentWorkflowState)

    # 1. Register nodes
    workflow.add_node("validate_input", nodes.validate_input_node)
    workflow.add_node("discovery", nodes.discovery_node)
    workflow.add_node("verification", nodes.verification_node)
    workflow.add_node("eligibility", nodes.eligibility_node)
    workflow.add_node("ranking", nodes.ranking_node)

    # 2. Add edges and conditional routing
    workflow.add_edge(START, "validate_input")

    workflow.add_conditional_edges(
        "validate_input",
        route_after_validation,
        {
            "discovery": "discovery",
            END: END,
        },
    )

    workflow.add_conditional_edges(
        "discovery",
        route_after_discovery,
        {
            "verification": "verification",
            "ranking": "ranking",
            END: END,
        },
    )

    workflow.add_conditional_edges(
        "verification",
        route_after_verification,
        {
            "eligibility": "eligibility",
            "ranking": "ranking",
            END: END,
        },
    )

    workflow.add_conditional_edges(
        "eligibility",
        route_after_eligibility,
        {
            "ranking": "ranking",
            END: END,
        },
    )

    workflow.add_edge("ranking", END)

    return workflow.compile()
