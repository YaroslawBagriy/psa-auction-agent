from __future__ import annotations

from abc import ABC, abstractmethod

from app.agents.base import BaseAgent
from app.models.analysis import AnalysisResult
from app.models.bidding import BidDecision, BidExecutionResult
from app.models.config import SearchConfig
from app.models.listing import Listing
from app.services.bid_guardrails import BidGuardrailService
from app.storage.sqlite import SQLiteStorage


class BidExecutor(ABC):
    @abstractmethod
    def place_bid(self, listing: Listing, bid_amount: float, dry_run: bool) -> BidExecutionResult:
        raise NotImplementedError


class DryRunBidExecutor(BidExecutor):
    def place_bid(self, listing: Listing, bid_amount: float, dry_run: bool) -> BidExecutionResult:
        return BidExecutionResult(
            listing_id=listing.listing_id,
            attempted=True,
            success=True,
            dry_run=dry_run,
            bid_amount=round(bid_amount, 2),
            message=f"Dry-run only. Would place bid of ${bid_amount:.2f} on {listing.title}.",
        )


class RealEbayBidExecutor(BidExecutor):
    def place_bid(self, listing: Listing, bid_amount: float, dry_run: bool) -> BidExecutionResult:
        # TODO: Implement authenticated eBay bid placement, session handling,
        # bid confirmation parsing, and idempotency protections before live usage.
        raise NotImplementedError("Live bidding is not implemented yet.")


class BiddingAgent(BaseAgent):
    name = "bidding"

    def __init__(
        self,
        storage: SQLiteStorage,
        guardrail_service: BidGuardrailService,
        executor: BidExecutor,
    ) -> None:
        super().__init__()
        self.storage = storage
        self.guardrail_service = guardrail_service
        self.executor = executor

    def run(
        self,
        run_id: str,
        listing: Listing,
        analysis: AnalysisResult,
        search_config: SearchConfig,
    ) -> tuple[BidDecision, BidExecutionResult | None]:
        decision = self.guardrail_service.decide(listing, analysis, search_config)
        self.storage.record_bid_decision(run_id, decision)
        self.logger.debug(
            "Bid decision for listing %s approved=%s",
            listing.listing_id,
            decision.approved,
        )

        if not decision.approved or decision.approved_max_bid is None:
            return decision, None

        execution = self.executor.place_bid(
            listing=listing,
            bid_amount=decision.approved_max_bid,
            dry_run=search_config.dry_run,
        )
        self.storage.record_bid_attempt(run_id, execution)
        return decision, execution

