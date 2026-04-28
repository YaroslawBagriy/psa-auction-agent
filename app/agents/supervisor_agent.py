from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.agents.analysis_agent import AnalysisAgent
from app.agents.auction_search_agent import AuctionSearchAgent
from app.agents.base import BaseAgent
from app.models.config import SearchConfig
from app.models.listing import Listing
from app.models.state import ListingWorkflowResult, WorkflowSummary
from app.storage.sqlite import SQLiteStorage
from app.tools.bid_execution_tool import BidExecutionTool
from app.tools.listing_preparation_tool import ListingPreparationTool
from app.tools.scanner_tool import ScannerTool


class SupervisorAgent(BaseAgent):
    name = "supervisor"

    def __init__(
        self,
        scanner_tool: ScannerTool,
        listing_preparation_tool: ListingPreparationTool,
        auction_search_agent: AuctionSearchAgent,
        analysis_agent: AnalysisAgent,
        bid_execution_tool: BidExecutionTool,
        storage: SQLiteStorage,
    ) -> None:
        super().__init__()
        self.scanner_tool = scanner_tool
        self.listing_preparation_tool = listing_preparation_tool
        self.auction_search_agent = auction_search_agent
        self.analysis_agent = analysis_agent
        self.bid_execution_tool = bid_execution_tool
        self.storage = storage
        self.chain = self._build_chain()

    def _build_chain(self):
        from langchain_core.runnables import RunnableLambda

        return (
            RunnableLambda(self._scan_and_validate_stage).with_config(run_name="scanner_and_preparation_tools")
            | RunnableLambda(self._auction_search_stage)
            | RunnableLambda(self._market_analysis_stage)
            | RunnableLambda(self._bidding_stage).with_config(run_name="bid_execution_tool")
        )

    def run(self, search_config: SearchConfig) -> WorkflowSummary:
        run_id = search_config.run_label or f"run-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
        final_state = self.chain.invoke(
            {
                "run_id": run_id,
                "search_config": search_config,
            }
        )
        return self._build_summary(run_id=run_id, results=final_state["results"])

    def _scan_and_validate_stage(self, state: dict[str, Any]) -> dict[str, Any]:
        run_id: str = state["run_id"]
        search_config: SearchConfig = state["search_config"]

        raw_listings = self.scanner_tool.run(run_id=run_id, search_config=search_config)
        results, results_by_listing_id, validated_listings = self.listing_preparation_tool.run(
            run_id=run_id,
            raw_listings=raw_listings,
            search_config=search_config,
        )
        self.logger.info(
            "Scan/preparation stage complete raw=%s validated=%s",
            len(raw_listings),
            len(validated_listings),
        )

        state.update(
            {
                "raw_listings": raw_listings,
                "results": results,
                "results_by_listing_id": results_by_listing_id,
                "validated_listings": validated_listings,
            }
        )
        return state

    def _auction_search_stage(self, state: dict[str, Any]) -> dict[str, Any]:
        run_id: str = state["run_id"]
        search_config: SearchConfig = state["search_config"]
        validated_listings: list[Listing] = state.get("validated_listings", [])
        results_by_listing_id: dict[str, ListingWorkflowResult] = state["results_by_listing_id"]

        search_result = self.auction_search_agent.run(
            run_id=run_id,
            listings=validated_listings,
            search_config=search_config,
        )
        decision_by_listing_id = {
            decision.listing_id: decision
            for decision in search_result.decisions
        }
        selected_listing_ids = set(search_result.selected_listing_ids())
        selected_listings: list[Listing] = []
        for listing in validated_listings:
            workflow_result = results_by_listing_id[listing.listing_id]
            decision = decision_by_listing_id.get(listing.listing_id)
            workflow_result.search_decision = decision
            if listing.listing_id in selected_listing_ids:
                selected_listings.append(listing)

        state.update(
            {
                "selected_listings": selected_listings,
                "search_result": search_result,
            }
        )
        self.logger.info("Auction-search stage complete selected=%s", len(selected_listings))
        return state

    def _market_analysis_stage(self, state: dict[str, Any]) -> dict[str, Any]:
        run_id: str = state["run_id"]
        search_config: SearchConfig = state["search_config"]
        selected_listings: list[Listing] = state.get("selected_listings", [])
        results_by_listing_id: dict[str, ListingWorkflowResult] = state["results_by_listing_id"]

        analysis_batch = self.analysis_agent.run(
            run_id=run_id,
            listings=selected_listings,
            target_rules=search_config.target_rules,
        )
        analyses_by_listing_id = analysis_batch.by_listing_id()
        for listing_id, analysis in analyses_by_listing_id.items():
            results_by_listing_id[listing_id].analysis = analysis

        state["analysis_batch"] = analysis_batch
        self.logger.info("Market-analysis stage complete analyses=%s", len(analysis_batch.analyses))
        return state

    def _bidding_stage(self, state: dict[str, Any]) -> dict[str, Any]:
        run_id: str = state["run_id"]
        search_config: SearchConfig = state["search_config"]
        selected_listings: list[Listing] = state.get("selected_listings", [])
        results_by_listing_id: dict[str, ListingWorkflowResult] = state["results_by_listing_id"]
        analyses_by_listing_id = state.get("analysis_batch").by_listing_id() if state.get("analysis_batch") else {}

        for listing in selected_listings:
            analysis = analyses_by_listing_id.get(listing.listing_id)
            if analysis is None:
                continue
            workflow_result = results_by_listing_id[listing.listing_id]
            try:
                bid_decision, bid_execution = self.bid_execution_tool.run(
                    run_id=run_id,
                    listing=listing,
                    analysis=analysis,
                    search_config=search_config,
                )
                workflow_result.bid_decision = bid_decision
                workflow_result.bid_execution = bid_execution
                self.logger.info(
                    "Bid guardrails listing_id=%s approved=%s reason=%s",
                    listing.listing_id,
                    bid_decision.approved,
                    bid_decision.reason,
                )
            except Exception as exc:  # pragma: no cover - defensive fallback
                self.logger.exception("Bidding failed for listing %s", listing.listing_id)
                self.storage.record_error(run_id, listing.listing_id, "bidding", str(exc))
                workflow_result.errors.append(str(exc))

        self.logger.info("Bidding stage complete selected=%s", len(selected_listings))
        return state

    def _build_summary(self, run_id: str, results: list[ListingWorkflowResult]) -> WorkflowSummary:
        candidate_count = sum(
            1 for result in results if result.validation is not None and result.validation.passed
        )
        selected_link_count = sum(
            1
            for result in results
            if result.search_decision is not None and result.search_decision.should_track
        )
        analyses_completed = sum(1 for result in results if result.analysis is not None)
        bids_approved = sum(
            1 for result in results if result.bid_decision is not None and result.bid_decision.approved
        )
        bid_attempts = sum(
            1 for result in results if result.bid_execution is not None and result.bid_execution.attempted
        )

        return WorkflowSummary(
            run_id=run_id,
            scanned_count=len(results),
            candidate_count=candidate_count,
            selected_link_count=selected_link_count,
            analyses_completed=analyses_completed,
            bids_approved=bids_approved,
            bid_attempts=bid_attempts,
            results=results,
        )
