from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.models.config import TargetRules
from app.models.listing import Listing


class MarketAnalysisInput(BaseModel):
    listings: list[Listing]
    target_rules: TargetRules


class AnalysisResult(BaseModel):
    listing_id: str
    url: str
    should_bid: bool
    confidence: float
    estimated_market_value: float | None = None
    recommended_max_bid: float | None = None
    trend_outlook: Literal["upward", "steady", "downward", "uncertain"]
    reasoning: str
    risk_flags: list[str] = Field(default_factory=list)
    active_listing_count: int | None = None
    sold_listing_count: int | None = None
    sell_through_rate: float | None = None
    recent_sold_prices: list[float] = Field(default_factory=list)
    market_evidence: str | None = None


class MarketAnalysisBatchResult(BaseModel):
    analyses: list[AnalysisResult] = Field(default_factory=list)

    def by_listing_id(self) -> dict[str, AnalysisResult]:
        return {analysis.listing_id: analysis for analysis in self.analyses}
