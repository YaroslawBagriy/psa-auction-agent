from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class MarketComp(BaseModel):
    source: Literal["active", "sold"]
    item_id: str | None = None
    title: str
    url: str | None = None
    price: float | None = None
    currency: str = "USD"
    seller_name: str | None = None
    sold_date: datetime | None = None
    end_time: datetime | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class MarketResearchResult(BaseModel):
    listing_id: str
    query: str
    active_listing_count: int | None = None
    sold_listing_count: int | None = None
    sell_through_rate: float | None = None
    recent_sold_prices: list[float] = Field(default_factory=list)
    estimated_market_value: float | None = None
    active_comps: list[MarketComp] = Field(default_factory=list)
    sold_comps: list[MarketComp] = Field(default_factory=list)
    evidence_summary: str
    source_urls: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class MarketResearchQuery(BaseModel):
    query: str
    purpose: Literal["exact_title", "normalized_title", "identity_variant"]
    rationale: str


class MarketResearchQueryPlan(BaseModel):
    listing_id: str
    queries: list[MarketResearchQuery] = Field(default_factory=list)

    def query_strings(self) -> list[str]:
        unique_queries: list[str] = []
        for item in self.queries:
            normalized = " ".join(item.query.split())
            if normalized and normalized not in unique_queries:
                unique_queries.append(normalized)
        return unique_queries


class MarketResearchQueryPlanBatch(BaseModel):
    plans: list[MarketResearchQueryPlan] = Field(default_factory=list)

    def by_listing_id(self) -> dict[str, MarketResearchQueryPlan]:
        return {plan.listing_id: plan for plan in self.plans}


class LLMMarketResearchOutput(BaseModel):
    listing_id: str
    query: str
    active_listing_count: int | None = None
    sold_listing_count: int | None = None
    sell_through_rate: float | None = None
    recent_sold_prices: list[float] = Field(default_factory=list)
    estimated_market_value: float | None = None
    evidence_summary: str
    source_urls: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
