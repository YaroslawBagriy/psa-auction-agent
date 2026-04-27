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
    estimated_market_value: float
    recommended_max_bid: float
    trend_outlook: Literal["upward", "steady", "downward", "uncertain"]
    reasoning: str
    risk_flags: list[str] = Field(default_factory=list)


class MarketAnalysisBatchResult(BaseModel):
    analyses: list[AnalysisResult] = Field(default_factory=list)

    def by_listing_id(self) -> dict[str, AnalysisResult]:
        return {analysis.listing_id: analysis for analysis in self.analyses}
