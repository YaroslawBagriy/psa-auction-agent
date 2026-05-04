from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.clients.ebay_market import MockEbayMarketResearchClient
from app.agents.market_query_agent import MarketQueryPlannerAgent, MarketQueryPlannerEngine
from app.models.config import SearchConfig, TargetRules
from app.models.listing import Listing
from app.models.market import (
    MarketResearchQuery,
    MarketResearchQueryPlan,
    MarketResearchQueryPlanBatch,
    MarketResearchResult,
)
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
    assert enriched_context["estimated_market_value_from_ebay_sold_comps"] == 197.5
    assert enriched_context["sell_through_rate"] == 1.5
    assert results["1001"].active_listing_count == 18
    assert results["1001"].sold_listing_count == 27
    assert results["1001"].estimated_market_value == 197.5


class FakeMarketQueryPlannerEngine(MarketQueryPlannerEngine):
    def plan(self, listings: list[Listing]) -> MarketResearchQueryPlanBatch:
        return MarketResearchQueryPlanBatch(
            plans=[
                MarketResearchQueryPlan(
                    listing_id=listings[0].listing_id,
                    queries=[
                        MarketResearchQuery(
                            query=listings[0].title,
                            purpose="exact_title",
                            rationale="Exact title first.",
                        ),
                        MarketResearchQuery(
                            query="2025 Pokemon Mega Charizard X EX 109 PSA 10",
                            purpose="identity_variant",
                            rationale="Normalized identity fallback.",
                        ),
                    ],
                )
            ]
        )


class CapturingMarketResearchClient(MockEbayMarketResearchClient):
    def __init__(self) -> None:
        self.query_strings: list[str] | None = None

    def research_listing(self, listing, config, query_strings=None) -> MarketResearchResult:
        self.query_strings = query_strings
        return super().research_listing(listing, config, query_strings=query_strings)


def test_market_research_tool_passes_query_planner_variants_to_client(tmp_path) -> None:
    storage = SQLiteStorage(tmp_path / "market-query-plan.db")
    client = CapturingMarketResearchClient()
    try:
        tool = MarketResearchTool(
            client=client,
            storage=storage,
            query_planner_agent=MarketQueryPlannerAgent(FakeMarketQueryPlannerEngine()),
        )
        config = SearchConfig(
            target_pokemon=[Pokemon.CHARIZARD],
            target_rules=TargetRules(allowed_grades={"10"}),
        )

        tool.run(
            run_id="test-run",
            listings=[_listing()],
            search_config=config,
        )
    finally:
        storage.close()

    assert client.query_strings == [
        "2025 Pokemon PFL EN-Phantasmal Flames Ultra Rare #109 Mega Charizard X EX PSA 10",
        "2025 Pokemon Mega Charizard X EX 109 PSA 10",
    ]
