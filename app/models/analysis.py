from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.config import TargetRules
from app.models.listing import Listing
from app.models.price_research import PriceResearchResult


class AnalyzerInput(BaseModel):
    listing: Listing
    price_research: PriceResearchResult
    target_rules: TargetRules


class AnalysisResult(BaseModel):
    should_bid: bool
    confidence: float
    estimated_market_value: float
    recommended_max_bid: float
    reasoning: str
    risk_flags: list[str] = Field(default_factory=list)

