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
    warnings: list[str] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)
