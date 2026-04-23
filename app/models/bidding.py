from __future__ import annotations

from pydantic import BaseModel, Field


class BidDecision(BaseModel):
    listing_id: str
    approved: bool
    reason: str
    approved_max_bid: float | None = None
    expected_margin: float | None = None
    risk_flags: list[str] = Field(default_factory=list)
    dry_run: bool = True


class BidExecutionResult(BaseModel):
    listing_id: str
    attempted: bool
    success: bool
    dry_run: bool
    bid_amount: float | None = None
    message: str

