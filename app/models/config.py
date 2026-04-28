from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.models.pokemon import Pokemon


class TargetRules(BaseModel):
    allowed_grades: set[str] = Field(default_factory=set)
    allowed_sets: set[str] = Field(default_factory=set)
    max_current_price: float | None = None
    min_minutes_remaining: int | None = None
    max_minutes_remaining: int | None = 10

    @field_validator("allowed_grades", mode="before")
    @classmethod
    def normalize_grades(cls, value: object) -> object:
        if value is None:
            return set()
        if isinstance(value, (set, list, tuple)):
            return {str(item).strip() for item in value}
        return value


class BidGuardrails(BaseModel):
    confidence_threshold: float = 0.65
    min_expected_margin: float = 20.0
    max_bid_cap: float | None = None
    allowed_trend_outlooks: set[str] = Field(default_factory=lambda: {"steady", "upward"})
    prevent_duplicate_bids: bool = True

    @field_validator("allowed_trend_outlooks", mode="before")
    @classmethod
    def normalize_trend_outlooks(cls, value: object) -> object:
        if value is None:
            return {"steady", "upward"}
        if isinstance(value, (set, list, tuple)):
            return {str(item).strip().lower() for item in value}
        return value


class SearchConfig(BaseModel):
    target_pokemon: list[Pokemon]
    target_rules: TargetRules
    bid_guardrails: BidGuardrails = Field(default_factory=BidGuardrails)
    dry_run: bool = True
    official_seller_names: set[str] = Field(default_factory=lambda: {"psa"})
    scan_limit: int = Field(default=100, ge=1)
    poll_interval_minutes: int = Field(default=15, ge=1)
    run_label: str | None = None

    @field_validator("target_pokemon")
    @classmethod
    def ensure_targets(cls, value: list[Pokemon]) -> list[Pokemon]:
        if not value:
            raise ValueError("target_pokemon must contain at least one Pokemon enum")
        unique_items = list(dict.fromkeys(value))
        return unique_items

    @field_validator("official_seller_names", mode="before")
    @classmethod
    def normalize_seller_names(cls, value: object) -> object:
        if value is None:
            return {"psa"}
        if isinstance(value, (set, list, tuple)):
            return {str(item).strip().lower() for item in value}
        return value
