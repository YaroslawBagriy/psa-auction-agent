from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PriceResearchResult(BaseModel):
    listing_id: str
    source: str = "pricecharting"
    search_term: str
    matched_title: str | None = None
    matched_url: str | None = None
    match_confidence: float = 0.0
    prices_by_grade: dict[str, float] = Field(default_factory=dict)
    target_grade_price: float | None = None
    notes: list[str] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)

