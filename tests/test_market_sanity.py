from __future__ import annotations

from app.models.analysis import AnalysisResult
from app.models.market import MarketResearchResult
from app.services.market_sanity import (
    LOWER_COMP_RISK_FLAG,
    OUTLIER_RISK_FLAG,
    check_sold_comp_sanity,
    conservative_sold_comp_value,
    sanitize_analysis_result,
    sanitize_market_research_result,
)


def test_sold_comp_sanity_detects_incompatible_price_clusters() -> None:
    check = check_sold_comp_sanity([1000.19, 850.0, 520.0, 29.99, 26.99])

    assert check.unreliable is True
    assert check.reason is not None
    assert "clusters" in check.reason
    assert check.low_cluster == (26.99, 29.99)
    assert check.high_cluster == (520.0, 850.0, 1000.19)


def test_sanitize_analysis_result_removes_bad_outlier_based_max_bid() -> None:
    analysis = AnalysisResult(
        listing_id="298245897717",
        url="https://www.ebay.com/itm/298245897717",
        should_bid=True,
        confidence=0.9,
        estimated_market_value=850.0,
        recommended_max_bid=765.0,
        trend_outlook="steady",
        reasoning="High-value comps justify an $850 value.",
        risk_flags=[],
        active_listing_count=1,
        sold_listing_count=5,
        sell_through_rate=5.0,
        recent_sold_prices=[1000.19, 850.0, 520.0, 29.99, 26.99],
        market_evidence="Sold prices range from $26.99 to $1000.19.",
    )

    sanitized = sanitize_analysis_result(analysis)

    assert sanitized.should_bid is False
    assert sanitized.estimated_market_value is None
    assert sanitized.recommended_max_bid is None
    assert sanitized.trend_outlook == "uncertain"
    assert sanitized.confidence <= 0.55
    assert OUTLIER_RISK_FLAG in sanitized.risk_flags


def test_sanitize_market_research_result_clears_unreliable_estimate() -> None:
    research = MarketResearchResult(
        listing_id="298245897717",
        query="2025 POKEMON PFL EN-PHANTASMAL FLAMES #013 MEGA CHARIZARD X EX PSA 9",
        active_listing_count=1,
        sold_listing_count=5,
        sell_through_rate=5.0,
        recent_sold_prices=[1000.19, 850.0, 520.0, 29.99, 26.99],
        estimated_market_value=850.0,
        evidence_summary="Recent sold prices range from $26.99 to $1000.19.",
    )

    sanitized = sanitize_market_research_result(research)

    assert sanitized.estimated_market_value is None
    assert OUTLIER_RISK_FLAG in sanitized.warnings
    assert "Safety check" in sanitized.evidence_summary


def test_conservative_sold_comp_value_uses_lower_half_and_wide_spread_discount() -> None:
    conservative = conservative_sold_comp_value([925.0, 375.0, 206.55, 330.69, 199.99])

    assert conservative is not None
    assert conservative.value == 206.55
    assert conservative.bid_fraction == 0.70
    assert conservative.max_bid_cap == 144.59


def test_sanitize_analysis_result_caps_rayquaza_deoxys_value_to_lower_solds() -> None:
    analysis = AnalysisResult(
        listing_id="117162542756",
        url="https://www.ebay.com/itm/117162542756",
        should_bid=True,
        confidence=0.9,
        estimated_market_value=375.0,
        recommended_max_bid=330.0,
        trend_outlook="steady",
        reasoning="Median sold comp supports $375.",
        risk_flags=[],
        active_listing_count=1,
        sold_listing_count=5,
        sell_through_rate=1.0,
        recent_sold_prices=[925.0, 375.0, 206.55, 330.69, 199.99],
        market_evidence="Sold prices range $199.99-$925 with median $375.",
    )

    sanitized = sanitize_analysis_result(analysis)

    assert sanitized.estimated_market_value == 206.55
    assert sanitized.recommended_max_bid == 144.59
    assert LOWER_COMP_RISK_FLAG in sanitized.risk_flags


def test_sanitize_analysis_result_caps_celebrations_rayquaza_to_lower_solds() -> None:
    analysis = AnalysisResult(
        listing_id="306893319759",
        url="https://www.ebay.com/itm/306893319759",
        should_bid=True,
        confidence=0.82,
        estimated_market_value=270.0,
        recommended_max_bid=230.0,
        trend_outlook="steady",
        reasoning="Median cluster supports $270.",
        risk_flags=[],
        active_listing_count=1,
        sold_listing_count=7,
        sell_through_rate=1.0,
        recent_sold_prices=[270.0, 170.0, 500.91, 180.5, 45.0, 70.0, 225.0],
        market_evidence="Sold prices range $45-$500.91.",
    )

    sanitized = sanitize_analysis_result(analysis)

    assert sanitized.estimated_market_value == 120.0
    assert sanitized.recommended_max_bid == 84.0
    assert LOWER_COMP_RISK_FLAG in sanitized.risk_flags
