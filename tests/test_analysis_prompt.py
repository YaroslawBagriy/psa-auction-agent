from app.models.analysis import AnalysisResult
from app.prompts.analysis_prompt import ANALYSIS_SYSTEM_PROMPT


def test_analysis_prompt_requires_exact_ebay_comp_method() -> None:
    prompt = ANALYSIS_SYSTEM_PROMPT.lower()

    assert "exact card identity" in prompt
    assert "matching ebay active listings" in prompt
    assert "matching ebay sold" in prompt
    assert "sell_through_rate" in prompt
    assert "recent ebay sold prices" in prompt
    assert "insufficient_exact_ebay_comps" in prompt
    assert "set estimated_market_value=null" in prompt
    assert "do not estimate fair market value from active listing asking prices" in prompt
    assert "non_ebay_fallback_value" in prompt
    assert "do not use 0 as a do-not-bid sentinel" in prompt
    assert "unreliable_outlier_sold_comps" in prompt
    assert "do not anchor to the high cluster" in prompt
    assert "role/persona" in prompt
    assert "private reasoning process" in prompt
    assert "one-shot example" in prompt
    assert "do not reveal hidden chain-of-thought" in prompt
    assert "listing.card_language" in prompt
    assert "japanese and english" in prompt
    assert "lower recent sold range" in prompt
    assert "70% to 80%" in prompt


def test_analysis_result_captures_market_comp_evidence() -> None:
    result = AnalysisResult(
        listing_id="117155708072",
        url="https://www.ebay.com/itm/117155708072",
        should_bid=False,
        confidence=0.8,
        estimated_market_value=70.0,
        recommended_max_bid=59.5,
        trend_outlook="steady",
        reasoning="Exact eBay sold comps cluster between $60 and $75.",
        active_listing_count=45,
        sold_listing_count=52,
        sell_through_rate=1.16,
        recent_sold_prices=[60.0, 65.0, 70.0, 75.0],
        market_evidence="52 sold / 45 active exact comps; median sold price near $70.",
    )

    assert result.active_listing_count == 45
    assert result.sold_listing_count == 52
    assert result.sell_through_rate == 1.16
    assert result.recent_sold_prices == [60.0, 65.0, 70.0, 75.0]
