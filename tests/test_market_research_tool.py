from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.clients.ebay_market import MockEbayMarketResearchClient
from app.models.config import SearchConfig, TargetRules
from app.models.listing import Listing
from app.models.pokemon import Pokemon
from app.storage.sqlite import SQLiteStorage
from app.tools.market_research_tool import MarketResearchTool


def _listing() -> Listing:
    return Listing(
        listing_id="1001",
        title="2025 Pokemon PFL EN-Phantasmal Flames Ultra Rare #109 Mega Charizard X EX PSA 10",
        seller_name="psa",
        url="https://www.ebay.com/itm/1001",
        is_auction=True,
        current_price=120.0,
        currency="USD",
        end_time=datetime.now(UTC) + timedelta(hours=1),
        grading_company="PSA",
        grade_value="10",
        detected_pokemon=Pokemon.CHARIZARD,
        set_name="Phantasmal Flames",
        card_number="109",
        in_psa_vault=True,
        is_pokemon_related=True,
        normalized_title="2025 pokemon phantasmal flames mega charizard x ex 109 psa 10",
        market_context={
            "estimated_market_value": 205.0,
            "recent_sales": [194.0, 201.0, 211.0, 214.0],
            "active_listing_count": 18,
            "sold_listing_count": 27,
        },
        raw_payload={},
    )


def test_market_research_tool_attaches_evidence_to_listing_context(tmp_path) -> None:
    storage = SQLiteStorage(tmp_path / "market-research.db")
    try:
        tool = MarketResearchTool(
            client=MockEbayMarketResearchClient(),
            storage=storage,
        )
        config = SearchConfig(
            target_pokemon=[Pokemon.CHARIZARD],
            target_rules=TargetRules(allowed_grades={"10"}),
        )

        enriched_listings, results = tool.run(
            run_id="test-run",
            listings=[_listing()],
            search_config=config,
        )
    finally:
        storage.close()

    assert len(enriched_listings) == 1
    enriched_context = enriched_listings[0].market_context
    assert "ebay_market_research" in enriched_context
    assert enriched_context["estimated_market_value_from_ebay_sold_comps"] == 205.0
    assert enriched_context["sell_through_rate"] == 1.5
    assert results["1001"].active_listing_count == 18
    assert results["1001"].sold_listing_count == 27
