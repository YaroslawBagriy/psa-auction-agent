from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.analysis import AnalysisResult
from app.models.bidding import BidDecision, BidExecutionResult
from app.models.listing import Listing, RawListing
from app.models.market import MarketResearchResult
from app.models.review import AuctionSearchDecision
from app.models.validation import ValidationResult


class ListingWorkflowResult(BaseModel):
    raw_listing: RawListing
    pre_validation: ValidationResult | None = None
    listing: Listing | None = None
    validation: ValidationResult | None = None
    search_decision: AuctionSearchDecision | None = None
    market_research: MarketResearchResult | None = None
    analysis: AnalysisResult | None = None
    bid_decision: BidDecision | None = None
    bid_execution: BidExecutionResult | None = None
    errors: list[str] = Field(default_factory=list)


class WorkflowSummary(BaseModel):
    run_id: str
    scanned_count: int
    candidate_count: int
    selected_link_count: int
    analyses_completed: int
    bids_approved: int
    bid_attempts: int
    results: list[ListingWorkflowResult] = Field(default_factory=list)
