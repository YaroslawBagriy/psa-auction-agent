from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.agents.market_research_agent import OpenAIWebMarketResearchEngine
from app.models.config import MarketResearchConfig
from app.models.listing import Listing
from app.models.pokemon import Pokemon


class FakeResponsesClient:
    def __init__(self) -> None:
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        payload = {
            "listing_id": "117155708072",
            "query": "2021 POKEMON CELEBRATIONS CLASSIC COLLECTION #145 GARCHOMP C LV.X-HOLO PSA 10",
            "active_listing_count": 45,
            "sold_listing_count": 52,
            "sell_through_rate": 1.156,
            "recent_sold_prices": [60.0, 65.0, 70.0, 75.0],
            "estimated_market_value": 67.5,
            "evidence_summary": "Exact eBay sold comps cluster between $60 and $75; sell-through is strong.",
            "source_urls": ["https://www.ebay.com/sch/i.html?_nkw=garchomp+psa+10"],
            "warnings": [],
        }
        return SimpleNamespace(
            id="resp_123",
            output_text=json.dumps(payload),
            output=[],
        )


class FakeUnsupportedFiltersResponsesClient(FakeResponsesClient):
    def create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["tools"] and "filters" in kwargs["tools"][0]:
            raise RuntimeError("Parameter 'filters' not supported with model 'gpt-4.1-mini' param='tools'")

        payload = {
            "listing_id": "117155708072",
            "query": "2021 POKEMON CELEBRATIONS CLASSIC COLLECTION #145 GARCHOMP C LV.X-HOLO PSA 10",
            "active_listing_count": 45,
            "sold_listing_count": 52,
            "sell_through_rate": 1.156,
            "recent_sold_prices": [60.0, 65.0, 70.0, 75.0],
            "estimated_market_value": 67.5,
            "evidence_summary": "Exact eBay sold comps cluster between $60 and $75; sell-through is strong.",
            "source_urls": ["https://www.ebay.com/sch/i.html?_nkw=garchomp+psa+10"],
            "warnings": [],
        }
        return SimpleNamespace(
            id="resp_retry",
            output_text=json.dumps(payload),
            output=[],
        )


def _listing() -> Listing:
    return Listing(
        listing_id="117155708072",
        title="2021 POKEMON CELEBRATIONS CLASSIC COLLECTION #145 GARCHOMP C LV.X-HOLO PSA 10",
        seller_name="psa",
        url="https://www.ebay.com/itm/117155708072",
        is_auction=True,
        current_price=119.99,
        currency="USD",
        end_time=datetime.now(UTC) + timedelta(hours=1),
        grading_company="PSA",
        grade_value="10",
        detected_pokemon=Pokemon.GARCHOMP,
        set_name="Celebrations Classic Collection",
        card_number="145",
        in_psa_vault=True,
        is_pokemon_related=True,
        normalized_title="2021 pokemon celebrations classic collection 145 garchomp c lvx holo psa 10",
        raw_payload={},
    )


def test_openai_web_market_research_engine_uses_web_search_and_parses_output() -> None:
    responses_client = FakeResponsesClient()
    engine = OpenAIWebMarketResearchEngine(
        model_name="gpt-4.1-mini",
        responses_client=responses_client,
    )

    result = engine.research(
        listing=_listing(),
        config=MarketResearchConfig(
            web_search_enabled=True,
            web_search_allowed_domains=["ebay.com", "pricecharting.com"],
        ),
        query_strings=[
            "2021 POKEMON CELEBRATIONS CLASSIC COLLECTION #145 GARCHOMP C LV.X-HOLO PSA 10",
            "2021 Pokemon Celebrations Garchomp C LV.X #145 PSA 10",
        ],
    )

    assert result.active_listing_count == 45
    assert result.sold_listing_count == 52
    assert result.sell_through_rate == 1.156
    assert result.estimated_market_value == 67.5
    assert result.recent_sold_prices == [60.0, 65.0, 70.0, 75.0]
    assert result.source_urls == ["https://www.ebay.com/sch/i.html?_nkw=garchomp+psa+10"]

    call = responses_client.calls[0]
    assert call["model"] == "gpt-4.1-mini"
    assert call["tools"][0]["type"] == "web_search"
    assert "filters" not in call["tools"][0]
    assert call["text"]["format"]["type"] == "json_schema"
    schema = call["text"]["format"]["schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    assert "Suggested search queries" in call["input"]


def test_openai_web_market_research_engine_can_opt_into_domain_filters() -> None:
    responses_client = FakeResponsesClient()
    engine = OpenAIWebMarketResearchEngine(
        model_name="gpt-5.5",
        responses_client=responses_client,
    )

    engine.research(
        listing=_listing(),
        config=MarketResearchConfig(
            web_search_enabled=True,
            web_search_domain_filters_enabled=True,
            web_search_allowed_domains=["ebay.com", "pricecharting.com"],
        ),
        query_strings=[
            "2021 POKEMON CELEBRATIONS CLASSIC COLLECTION #145 GARCHOMP C LV.X-HOLO PSA 10",
        ],
    )

    call = responses_client.calls[0]
    assert call["model"] == "gpt-5.5"
    assert call["tools"][0]["filters"]["allowed_domains"] == ["ebay.com", "pricecharting.com"]


def test_openai_web_market_research_engine_retries_without_domain_filters_when_unsupported() -> None:
    responses_client = FakeUnsupportedFiltersResponsesClient()
    engine = OpenAIWebMarketResearchEngine(
        model_name="gpt-4.1-mini",
        responses_client=responses_client,
    )

    result = engine.research(
        listing=_listing(),
        config=MarketResearchConfig(
            web_search_enabled=True,
            web_search_domain_filters_enabled=True,
            web_search_allowed_domains=["ebay.com", "pricecharting.com"],
        ),
        query_strings=[
            "2021 POKEMON CELEBRATIONS CLASSIC COLLECTION #145 GARCHOMP C LV.X-HOLO PSA 10",
        ],
    )

    assert result.estimated_market_value == 67.5
    assert len(responses_client.calls) == 2
    assert responses_client.calls[0]["tools"][0]["filters"]["allowed_domains"] == [
        "ebay.com",
        "pricecharting.com",
    ]
    assert "filters" not in responses_client.calls[1]["tools"][0]
    assert result.raw_payload["domain_filters_applied"] is False
