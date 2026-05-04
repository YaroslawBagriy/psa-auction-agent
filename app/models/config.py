from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator

from app.models.bidding import BiddingMode
from app.models.pokemon import Pokemon


class TargetRules(BaseModel):
    allowed_grades: set[str] = Field(default_factory=set)
    allowed_sets: set[str] = Field(default_factory=set)
    max_current_price: float | None = None
    min_minutes_remaining: int | None = None
    max_minutes_remaining: int | None = None

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


class BiddingConfig(BaseModel):
    mode: BiddingMode = BiddingMode.MANUAL
    enabled: bool = False
    require_human_confirmation: bool = True
    open_listing_in_browser: bool = False
    browser_automation_enabled: bool = False
    buy_offer_api_enabled: bool = False
    buy_offer_scope: str = "https://api.ebay.com/oauth/api_scope/buy.offer.auction"
    marketplace_id: str = "EBAY_US"
    environment: str = "production"
    currency: str = "USD"
    offer_api_timeout_seconds: float = 20.0


class MarketResearchMode(str, Enum):
    LLM_WEB = "llm_web"
    OFFICIAL_EBAY_API = "official_ebay_api"


class MarketResearchConfig(BaseModel):
    enabled: bool = True
    mode: MarketResearchMode = MarketResearchMode.LLM_WEB
    active_limit: int = Field(default=50, ge=1, le=200)
    sold_limit: int = Field(default=50, ge=1, le=200)
    marketplace_insights_enabled: bool = False
    marketplace_insights_scope: str = "https://api.ebay.com/oauth/api_scope/buy.marketplace.insights"
    timeout_seconds: float = 20.0
    web_search_enabled: bool = True
    web_search_domain_filters_enabled: bool = False
    web_search_allowed_domains: list[str] = Field(
        default_factory=lambda: [
            "ebay.com",
            "pricecharting.com",
            "130point.com",
            "psacard.com",
            "tcgplayer.com",
        ]
    )

    @field_validator("web_search_allowed_domains", mode="before")
    @classmethod
    def normalize_web_search_domains(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, str):
            return [domain.strip() for domain in value.split(",") if domain.strip()]
        if isinstance(value, (set, list, tuple)):
            return [str(domain).strip() for domain in value if str(domain).strip()]
        return value


class SearchConfig(BaseModel):
    target_pokemon: list[Pokemon]
    target_rules: TargetRules
    bid_guardrails: BidGuardrails = Field(default_factory=BidGuardrails)
    bidding: BiddingConfig = Field(default_factory=BiddingConfig)
    market_research: MarketResearchConfig = Field(default_factory=MarketResearchConfig)
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
