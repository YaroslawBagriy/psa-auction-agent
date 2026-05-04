from __future__ import annotations

from app.models.analysis import AnalysisResult
from app.models.bidding import BidDecision
from app.models.config import SearchConfig
from app.models.listing import Listing
from app.services.market_sanity import (
    LOWER_COMP_RISK_FLAG,
    check_sold_comp_sanity,
    conservative_sold_comp_value,
)
from app.storage.sqlite import SQLiteStorage


class BidGuardrailService:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage

    def decide(
        self,
        listing: Listing,
        analysis: AnalysisResult,
        search_config: SearchConfig,
    ) -> BidDecision:
        reasons: list[str] = []
        approved_max_bid = analysis.recommended_max_bid
        risk_flags = list(analysis.risk_flags)

        if listing.seller_name.strip().lower() not in search_config.official_seller_names:
            reasons.append("Listing seller does not match the configured official seller allow-list.")

        if listing.minutes_remaining() <= 0:
            reasons.append("Listing auction has already ended.")

        if not analysis.should_bid:
            reasons.append("Analysis agent recommended against bidding.")

        if analysis.estimated_market_value is None:
            reasons.append("Analysis did not provide a reliable sold-comp market value.")

        sold_comp_check = check_sold_comp_sanity(
            analysis.recent_sold_prices,
            estimated_market_value=analysis.estimated_market_value,
        )
        if sold_comp_check.unreliable:
            reasons.append(
                f"Recent sold comps are too inconsistent for safe bidding: {sold_comp_check.reason}"
            )
        conservative_value = conservative_sold_comp_value(analysis.recent_sold_prices)

        if analysis.confidence < search_config.bid_guardrails.confidence_threshold:
            reasons.append("Analysis confidence is below the configured threshold.")

        if any("suspicious" in flag.lower() for flag in risk_flags):
            reasons.append("Analysis flagged the listing as suspicious.")

        if analysis.trend_outlook not in search_config.bid_guardrails.allowed_trend_outlooks:
            reasons.append("Trend outlook is not in the allowed trend outlook set.")

        if approved_max_bid is None:
            reasons.append("Analysis did not provide an actionable max bid.")
        else:
            if search_config.bid_guardrails.max_bid_cap is not None:
                approved_max_bid = min(approved_max_bid, search_config.bid_guardrails.max_bid_cap)

            if conservative_value is not None and approved_max_bid > conservative_value.max_bid_cap:
                approved_max_bid = conservative_value.max_bid_cap
                risk_flags = list(dict.fromkeys([*risk_flags, LOWER_COMP_RISK_FLAG]))

            if approved_max_bid <= listing.current_price:
                reasons.append("Approved max bid does not exceed the current auction price.")

        expected_margin = None
        margin_market_value = analysis.estimated_market_value
        if (
            margin_market_value is not None
            and conservative_value is not None
            and conservative_value.value < margin_market_value
        ):
            margin_market_value = conservative_value.value
        if approved_max_bid is not None and margin_market_value is not None:
            expected_margin = round(margin_market_value - approved_max_bid, 2)
            if expected_margin < search_config.bid_guardrails.min_expected_margin:
                reasons.append("Expected margin is below the configured minimum.")

        if (
            search_config.bid_guardrails.prevent_duplicate_bids
            and self.storage.has_bid_attempt(listing.listing_id)
        ):
            reasons.append("A prior bid attempt already exists for this listing.")

        approved = not reasons
        return BidDecision(
            listing_id=listing.listing_id,
            approved=approved,
            reason="Approved by deterministic bid guardrails." if approved else " ".join(reasons),
            approved_max_bid=round(approved_max_bid, 2) if approved else None,
            expected_margin=expected_margin if approved else None,
            risk_flags=risk_flags,
            dry_run=search_config.dry_run,
        )
