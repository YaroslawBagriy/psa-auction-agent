from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.pokemon import Pokemon


class RawListing(BaseModel):
    listing_id: str
    title: str
    seller_name: str
    url: str
    listing_type: str
    current_price: float
    end_time: datetime
    currency: str = "USD"
    subtitle: str | None = None
    description: str | None = None
    condition_description: str | None = None
    page_badges: list[str] = Field(default_factory=list)
    page_highlights: list[str] = Field(default_factory=list)
    item_specifics: dict[str, Any] = Field(default_factory=dict)
    market_context: dict[str, Any] = Field(default_factory=dict)
    set_name: str | None = None
    category_name: str | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_auction(self) -> bool:
        return self.listing_type.strip().upper() == "AUCTION"

    def minutes_remaining(self, reference_time: datetime | None = None) -> float:
        reference = reference_time or datetime.now(UTC)
        target = self.end_time
        if target.tzinfo is None:
            target = target.replace(tzinfo=UTC)
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=UTC)
        delta = target - reference
        return delta.total_seconds() / 60.0


class Listing(BaseModel):
    listing_id: str
    title: str
    seller_name: str
    url: str
    is_auction: bool
    current_price: float
    end_time: datetime
    grading_company: str | None = None
    grade_value: str | None = None
    detected_pokemon: Pokemon | None = None
    set_name: str | None = None
    card_number: str | None = None
    in_psa_vault: bool = False
    vault_evidence: list[str] = Field(default_factory=list)
    market_context: dict[str, Any] = Field(default_factory=dict)
    is_pokemon_related: bool = False
    normalized_title: str
    raw_payload: dict[str, Any] = Field(default_factory=dict)

    def minutes_remaining(self, reference_time: datetime | None = None) -> float:
        reference = reference_time or datetime.now(UTC)
        target = self.end_time
        if target.tzinfo is None:
            target = target.replace(tzinfo=UTC)
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=UTC)
        delta = target - reference
        return delta.total_seconds() / 60.0
