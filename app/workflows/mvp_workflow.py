from __future__ import annotations

from typing import TypedDict

try:
    from langgraph.graph import END, START, StateGraph
except ImportError:  # pragma: no cover - depends on local environment
    END = "__end__"
    START = "__start__"
    StateGraph = None

from app.agents.analysis_agent import AnalysisAgent
from app.agents.bidding_agent import BiddingAgent
from app.agents.parsing_agent import ParsingAgent
from app.agents.price_research_agent import PriceResearchAgent
from app.agents.validation_agent import ValidationAgent
from app.models.analysis import AnalysisResult
from app.models.bidding import BidDecision, BidExecutionResult
from app.models.config import SearchConfig
from app.models.listing import Listing, RawListing
from app.models.price_research import PriceResearchResult
from app.models.validation import ValidationResult


class CandidateWorkflowState(TypedDict, total=False):
    run_id: str
    search_config: SearchConfig
    raw_listing: RawListing
    pre_validation: ValidationResult
    listing: Listing
    validation: ValidationResult
    price_research: PriceResearchResult
    analysis: AnalysisResult
    bid_decision: BidDecision
    bid_execution: BidExecutionResult


def build_candidate_workflow(
    parsing_agent: ParsingAgent,
    validation_agent: ValidationAgent,
    price_research_agent: PriceResearchAgent,
    analysis_agent: AnalysisAgent,
    bidding_agent: BiddingAgent,
):
    if StateGraph is None:
        return _SequentialCandidateWorkflow(
            parsing_agent=parsing_agent,
            validation_agent=validation_agent,
            price_research_agent=price_research_agent,
            analysis_agent=analysis_agent,
            bidding_agent=bidding_agent,
        )

    graph = StateGraph(CandidateWorkflowState)

    def pre_validate_node(state: CandidateWorkflowState) -> dict[str, ValidationResult]:
        result = validation_agent.pre_validate(state["raw_listing"], state["search_config"])
        return {"pre_validation": result}

    def parse_node(state: CandidateWorkflowState) -> dict[str, Listing]:
        listing = parsing_agent.run(state["raw_listing"])
        return {"listing": listing}

    def validate_node(state: CandidateWorkflowState) -> dict[str, ValidationResult]:
        result = validation_agent.validate(
            run_id=state["run_id"],
            listing=state["listing"],
            search_config=state["search_config"],
        )
        return {"validation": result}

    def price_research_node(state: CandidateWorkflowState) -> dict[str, PriceResearchResult]:
        result = price_research_agent.run(
            run_id=state["run_id"],
            listing=state["listing"],
        )
        return {"price_research": result}

    def analysis_node(state: CandidateWorkflowState) -> dict[str, AnalysisResult]:
        result = analysis_agent.run(
            run_id=state["run_id"],
            listing=state["listing"],
            price_research=state["price_research"],
            target_rules=state["search_config"].target_rules,
        )
        return {"analysis": result}

    def bidding_node(state: CandidateWorkflowState) -> dict[str, BidDecision | BidExecutionResult]:
        decision, execution = bidding_agent.run(
            run_id=state["run_id"],
            listing=state["listing"],
            analysis=state["analysis"],
            search_config=state["search_config"],
        )
        payload: dict[str, BidDecision | BidExecutionResult] = {"bid_decision": decision}
        if execution is not None:
            payload["bid_execution"] = execution
        return payload

    def route_after_pre_validation(state: CandidateWorkflowState) -> str:
        if state["pre_validation"].passed:
            return "parse"
        return END

    def route_after_validation(state: CandidateWorkflowState) -> str:
        if state["validation"].passed:
            return "price_research"
        return END

    graph.add_node("pre_validate", pre_validate_node)
    graph.add_node("parse", parse_node)
    graph.add_node("validate", validate_node)
    graph.add_node("price_research", price_research_node)
    graph.add_node("analyze", analysis_node)
    graph.add_node("bid", bidding_node)

    graph.add_edge(START, "pre_validate")
    graph.add_conditional_edges("pre_validate", route_after_pre_validation, {"parse": "parse", END: END})
    graph.add_edge("parse", "validate")
    graph.add_conditional_edges("validate", route_after_validation, {"price_research": "price_research", END: END})
    graph.add_edge("price_research", "analyze")
    graph.add_edge("analyze", "bid")
    graph.add_edge("bid", END)

    return graph.compile()


class _SequentialCandidateWorkflow:
    def __init__(
        self,
        parsing_agent: ParsingAgent,
        validation_agent: ValidationAgent,
        price_research_agent: PriceResearchAgent,
        analysis_agent: AnalysisAgent,
        bidding_agent: BiddingAgent,
    ) -> None:
        self.parsing_agent = parsing_agent
        self.validation_agent = validation_agent
        self.price_research_agent = price_research_agent
        self.analysis_agent = analysis_agent
        self.bidding_agent = bidding_agent

    def invoke(self, state: CandidateWorkflowState) -> CandidateWorkflowState:
        final_state: CandidateWorkflowState = dict(state)
        pre_validation = self.validation_agent.pre_validate(
            final_state["raw_listing"],
            final_state["search_config"],
        )
        final_state["pre_validation"] = pre_validation
        if not pre_validation.passed:
            return final_state

        listing = self.parsing_agent.run(final_state["raw_listing"])
        final_state["listing"] = listing

        validation = self.validation_agent.validate(
            run_id=final_state["run_id"],
            listing=listing,
            search_config=final_state["search_config"],
        )
        final_state["validation"] = validation
        if not validation.passed:
            return final_state

        price_research = self.price_research_agent.run(
            run_id=final_state["run_id"],
            listing=listing,
        )
        final_state["price_research"] = price_research

        analysis = self.analysis_agent.run(
            run_id=final_state["run_id"],
            listing=listing,
            price_research=price_research,
            target_rules=final_state["search_config"].target_rules,
        )
        final_state["analysis"] = analysis

        bid_decision, bid_execution = self.bidding_agent.run(
            run_id=final_state["run_id"],
            listing=listing,
            analysis=analysis,
            search_config=final_state["search_config"],
        )
        final_state["bid_decision"] = bid_decision
        if bid_execution is not None:
            final_state["bid_execution"] = bid_execution
        return final_state
