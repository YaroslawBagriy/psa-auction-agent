from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.agents.analysis_agent import AnalysisAgent
from app.agents.auction_search_agent import AuctionSearchAgent
from app.agents.base import BaseAgent
from app.models.config import SearchConfig
from app.models.listing import RawListing
from app.models.state import ListingWorkflowResult, WorkflowSummary
from app.storage.sqlite import SQLiteStorage
from app.tools.bid_execution_tool import BidExecutionTool
from app.tools.listing_preparation_tool import ListingPreparationTool
from app.tools.market_research_tool import MarketResearchTool
from app.tools.scanner_tool import ScannerTool


class SupervisorAgent(BaseAgent):
    name = "supervisor"

    def __init__(
        self,
        scanner_tool: ScannerTool,
        listing_preparation_tool: ListingPreparationTool,
        auction_search_agent: AuctionSearchAgent,
        market_research_tool: MarketResearchTool,
        analysis_agent: AnalysisAgent,
        bid_execution_tool: BidExecutionTool,
        storage: SQLiteStorage,
    ) -> None:
        super().__init__()
        self.scanner_tool = scanner_tool
        self.listing_preparation_tool = listing_preparation_tool
        self.auction_search_agent = auction_search_agent
        self.market_research_tool = market_research_tool
        self.analysis_agent = analysis_agent
        self.bid_execution_tool = bid_execution_tool
        self.storage = storage
        self.chain = self._build_chain()

    def _build_chain(self):
        from langchain_core.runnables import RunnableLambda

        return RunnableLambda(self._process_listings_stage).with_config(run_name="per_listing_agent_workflow")

    def run(self, search_config: SearchConfig) -> WorkflowSummary:
        run_id = search_config.run_label or f"run-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
        final_state = self.chain.invoke(
            {
                "run_id": run_id,
                "search_config": search_config,
            }
        )
        return self._build_summary(run_id=run_id, results=final_state["results"])

    def _process_listings_stage(self, state: dict[str, Any]) -> dict[str, Any]:
        run_id: str = state["run_id"]
        search_config: SearchConfig = state["search_config"]

        results: list[ListingWorkflowResult] = []
        results_by_listing_id: dict[str, ListingWorkflowResult] = {}
        self.logger.info("Reviewing up to %s auctions one at a time.", search_config.scan_limit)
        for index, raw_listing in enumerate(
            self.scanner_tool.iter_listings(run_id=run_id, search_config=search_config),
            start=1,
        ):
            workflow_result = self._process_single_listing(
                run_id=run_id,
                raw_listing=raw_listing,
                search_config=search_config,
                index=index,
                total=search_config.scan_limit,
            )
            results.append(workflow_result)
            results_by_listing_id[raw_listing.listing_id] = workflow_result

        state.update(
            {
                "results": results,
                "results_by_listing_id": results_by_listing_id,
            }
        )
        self.logger.info("Auction review finished. Reviewed %s auctions.", len(results))
        return state

    def _process_single_listing(
        self,
        run_id: str,
        raw_listing: RawListing,
        search_config: SearchConfig,
        index: int,
        total: int,
    ) -> ListingWorkflowResult:
        self._log_auction_start(index=index, total=total, raw_listing=raw_listing)
        workflow_result = ListingWorkflowResult(raw_listing=raw_listing)
        try:
            self._log_step(1, "Checking listing requirements")
            preparation_results, _, validated_listings = self.listing_preparation_tool.run(
                run_id=run_id,
                raw_listings=[raw_listing],
                search_config=search_config,
            )
            workflow_result = preparation_results[0] if preparation_results else workflow_result

            if workflow_result.pre_validation and not workflow_result.pre_validation.passed:
                self._finish_listing(
                    index=index,
                    total=total,
                    workflow_result=workflow_result,
                    verdict="DENIED",
                    stage="pre_validation",
                    reason=self._join_reasons(workflow_result.pre_validation.reasons),
                )
                return workflow_result

            if workflow_result.validation and not workflow_result.validation.passed:
                self._finish_listing(
                    index=index,
                    total=total,
                    workflow_result=workflow_result,
                    verdict="DENIED",
                    stage="listing_validation",
                    reason=self._join_reasons(workflow_result.validation.reasons),
                )
                return workflow_result

            listing = workflow_result.listing or (validated_listings[0] if validated_listings else None)
            if listing is None:
                self._finish_listing(
                    index=index,
                    total=total,
                    workflow_result=workflow_result,
                    verdict="DENIED",
                    stage="listing_preparation",
                    reason="Listing preparation did not produce a normalized listing.",
                )
                return workflow_result

            self._log_preparation_passed(workflow_result)
            self._log_step(2, "Asking the listing-review agent if this auction is worth researching")
            search_result = self.auction_search_agent.run(
                run_id=run_id,
                listings=[listing],
                search_config=search_config,
            )
            search_decision = next(
                (
                    decision
                    for decision in search_result.decisions
                    if decision.listing_id == listing.listing_id
                ),
                None,
            )
            workflow_result.search_decision = search_decision
            if search_decision is None:
                reason = "AuctionSearchAgent did not return a decision for this listing."
                self.storage.record_error(run_id, listing.listing_id, "auction_search", reason)
                self._finish_listing(
                    index=index,
                    total=total,
                    workflow_result=workflow_result,
                    verdict="DENIED",
                    stage="auction_search",
                    reason=reason,
                )
                return workflow_result

            if not search_decision.should_track:
                self._finish_listing(
                    index=index,
                    total=total,
                    workflow_result=workflow_result,
                    verdict="DENIED",
                    stage="auction_search",
                    reason=search_decision.rationale,
                )
                return workflow_result

            self.logger.info("Step 2 result: selected for market research.")
            self._log_step(3, "Researching market value, sold comps, and sell-through")
            enriched_listings, market_research_by_listing_id = self.market_research_tool.run(
                run_id=run_id,
                listings=[listing],
                search_config=search_config,
            )
            if enriched_listings:
                listing = enriched_listings[0]
                workflow_result.listing = listing
            workflow_result.market_research = market_research_by_listing_id.get(listing.listing_id)
            if workflow_result.market_research is None:
                self.logger.info("Step 3 result: no reliable market evidence found yet.")
            else:
                self._log_market_research(workflow_result)

            self._log_step(4, "Asking the analysis agent for fair value and max bid")
            analysis_batch = self.analysis_agent.run(
                run_id=run_id,
                listings=[listing],
                target_rules=search_config.target_rules,
            )
            analysis = analysis_batch.by_listing_id().get(listing.listing_id)
            if analysis is None:
                reason = "AnalysisAgent did not return an analysis for this listing."
                self.storage.record_error(run_id, listing.listing_id, "analysis", reason)
                self._finish_listing(
                    index=index,
                    total=total,
                    workflow_result=workflow_result,
                    verdict="DENIED",
                    stage="analysis",
                    reason=reason,
                )
                return workflow_result

            workflow_result.analysis = analysis
            self._log_analysis(workflow_result)
            self._log_step(5, "Applying bid safety rules")
            bid_decision, bid_execution = self.bid_execution_tool.run(
                run_id=run_id,
                listing=listing,
                analysis=analysis,
                search_config=search_config,
            )
            workflow_result.bid_decision = bid_decision
            workflow_result.bid_execution = bid_execution
            self._finish_listing(
                index=index,
                total=total,
                workflow_result=workflow_result,
                verdict="ACCEPTED" if bid_decision.approved else "DENIED",
                stage="bid_guardrails",
                reason=bid_decision.reason,
            )
            return workflow_result
        except Exception as exc:  # pragma: no cover - defensive workflow boundary
            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.exception("Per-listing workflow failed for %s", raw_listing.listing_id)
            else:
                self.logger.warning(
                    "This auction could not be fully reviewed because one step failed. It will be denied safely."
                )
            self.storage.record_error(run_id, raw_listing.listing_id, "per_listing_workflow", str(exc))
            workflow_result.errors.append(str(exc))
            self._finish_listing(
                index=index,
                total=total,
                workflow_result=workflow_result,
                verdict="DENIED",
                stage="error",
                reason=str(exc),
            )
            return workflow_result

    def _join_reasons(self, reasons: list[str]) -> str:
        return "; ".join(reason for reason in reasons if reason) or "No reason provided."

    def _log_auction_start(self, index: int, total: int, raw_listing: RawListing) -> None:
        self.logger.info(
            "------ Start auction %s/%s ------",
            index,
            total,
        )
        self.logger.info("Item ID: %s | Current price: $%.2f", raw_listing.listing_id, raw_listing.current_price)
        self.logger.info("Auction title: %s", raw_listing.title[:180])

    def _log_step(self, step_number: int, message: str) -> None:
        self.logger.info("Step %s: %s...", step_number, message)

    def _log_preparation_passed(self, workflow_result: ListingWorkflowResult) -> None:
        listing = workflow_result.listing
        if listing is None:
            self.logger.info("Step 1 result: passed basic requirements.")
            return

        pokemon = listing.detected_pokemon.display_name if listing.detected_pokemon else "unknown Pokemon"
        grade = f"PSA {listing.grade_value}" if listing.grade_value else "unknown grade"
        language = listing.card_language.display_name if listing.card_language else "unknown language"
        self.logger.info(
            "Step 1 result: passed. Card appears to be %s, %s, %s, current price $%.2f.",
            pokemon,
            grade,
            language,
            listing.current_price,
        )

    def _log_market_research(self, workflow_result: ListingWorkflowResult) -> None:
        research = workflow_result.market_research
        if research is None:
            return

        value = self._money(research.estimated_market_value)
        sell_through = (
            f"{research.sell_through_rate:.2f}"
            if research.sell_through_rate is not None
            else "unknown"
        )
        self.logger.info(
            "Step 3 result: market value=%s, sold comps=%s, active listings=%s, sell-through=%s.",
            value,
            research.sold_listing_count if research.sold_listing_count is not None else "unknown",
            research.active_listing_count if research.active_listing_count is not None else "unknown",
            sell_through,
        )
        if research.evidence_summary:
            self.logger.info("Market evidence: %s", research.evidence_summary)

    def _log_analysis(self, workflow_result: ListingWorkflowResult) -> None:
        analysis = workflow_result.analysis
        if analysis is None:
            return

        self.logger.info(
            "Step 4 result: %s. Estimated value=%s, recommended max bid=%s, confidence=%.2f.",
            "bid candidate" if analysis.should_bid else "do not bid",
            self._money(analysis.estimated_market_value),
            self._money(analysis.recommended_max_bid),
            analysis.confidence,
        )
        if analysis.reasoning:
            self.logger.info("Analysis: %s", analysis.reasoning)
        if analysis.risk_flags:
            self.logger.info("Risks: %s", "; ".join(analysis.risk_flags))

    def _finish_listing(
        self,
        index: int,
        total: int,
        workflow_result: ListingWorkflowResult,
        verdict: str,
        stage: str,
        reason: str,
    ) -> None:
        self._log_verdict(
            workflow_result=workflow_result,
            verdict=verdict,
            stage=stage,
            reason=reason,
        )
        self.logger.info(
            "------ End auction %s/%s: %s ------",
            index,
            total,
            "accepted" if verdict == "ACCEPTED" else "denied",
        )

    def _log_verdict(
        self,
        workflow_result: ListingWorkflowResult,
        verdict: str,
        stage: str,
        reason: str,
    ) -> None:
        if verdict == "ACCEPTED":
            decision = workflow_result.bid_decision
            self.logger.info(
                "Final decision: ACCEPTED. Recommended max bid: %s. Reason: %s",
                self._money(decision.approved_max_bid if decision else None),
                reason,
            )
            return

        self.logger.info("Final decision: DENIED. Reason: %s", reason)

    def _money(self, value: float | None) -> str:
        if value is None:
            return "unknown"
        return f"${value:.2f}"

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
