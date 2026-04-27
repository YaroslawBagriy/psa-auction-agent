from __future__ import annotations

from pydantic import BaseModel, Field


class AuctionSearchDecision(BaseModel):
    listing_id: str
    url: str
    should_track: bool
    confidence: float
    rationale: str


class AuctionSearchResult(BaseModel):
    decisions: list[AuctionSearchDecision] = Field(default_factory=list)

    def selected_listing_ids(self) -> list[str]:
        return [decision.listing_id for decision in self.decisions if decision.should_track]

    def selected_urls(self) -> list[str]:
        return [decision.url for decision in self.decisions if decision.should_track]
