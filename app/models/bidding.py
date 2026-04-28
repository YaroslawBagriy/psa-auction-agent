from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class BiddingMode(str, Enum):
    MANUAL = "manual"
    OFFICIAL_API = "official_api"
    BROWSER_AUTOMATION = "browser_automation"


class BidDecision(BaseModel):
    listing_id: str
    approved: bool
    reason: str
    approved_max_bid: float | None = None
    expected_margin: float | None = None
    risk_flags: list[str] = Field(default_factory=list)
    dry_run: bool = True


class BidActionResult(BaseModel):
    listing_id: str
    mode: BiddingMode
    status: str
    attempted: bool = False
    success: bool
    dry_run: bool
    recommended_bid: float | None = None
    bid_amount: float | None = None
    listing_url: str | None = None
    item_id: str | None = None
    ebay_restful_item_id: str | None = None
    external_bid_id: str | None = None
    title: str | None = None
    current_price: float | None = None
    end_time: datetime | None = None
    estimated_market_value: float | None = None
    expected_margin: float | None = None
    reasoning: str | None = None
    provider_response: dict[str, Any] = Field(default_factory=dict)
    message: str


BidExecutionResult = BidActionResult
