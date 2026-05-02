from __future__ import annotations

from app.agents.base import BaseAgent
from app.clients.ebay_market import EbayMarketResearchClient
from app.models.config import SearchConfig
from app.models.listing import Listing
from app.models.market import MarketResearchResult
from app.storage.sqlite import SQLiteStorage


class MarketResearchTool(BaseAgent):
    name = "market_research_tool"

    def __init__(self, client: EbayMarketResearchClient, storage: SQLiteStorage) -> None:
        super().__init__()
        self.client = client
        self.storage = storage

    def run(
        self,
        run_id: str,
        listings: list[Listing],
        search_config: SearchConfig,
    ) -> tuple[list[Listing], dict[str, MarketResearchResult]]:
        if not listings or not search_config.market_research.enabled:
            return listings, {}

        enriched_listings: list[Listing] = []
        results_by_listing_id: dict[str, MarketResearchResult] = {}
        for listing in listings:
            try:
                result = self.client.research_listing(listing, search_config.market_research)
                self.storage.record_market_research(run_id, result)
                results_by_listing_id[listing.listing_id] = result
                enriched_listings.append(self._attach_market_research(listing, result))
                self.logger.info(
                    "Market research listing_id=%s active=%s sold=%s sell_through=%s warnings=%s",
                    listing.listing_id,
                    result.active_listing_count,
                    result.sold_listing_count,
                    result.sell_through_rate,
                    result.warnings,
                )
            except Exception as exc:
                self.logger.exception("Market research failed for listing %s", listing.listing_id)
                self.storage.record_error(run_id, listing.listing_id, "market_research", str(exc))
                enriched_listings.append(listing)

        return enriched_listings, results_by_listing_id

    def _attach_market_research(self, listing: Listing, result: MarketResearchResult) -> Listing:
        market_context = dict(listing.market_context)
        market_context["ebay_market_research"] = result.model_dump(mode="json")
        if result.estimated_market_value is not None:
            market_context["estimated_market_value_from_ebay_sold_comps"] = result.estimated_market_value
        if result.sell_through_rate is not None:
            market_context["sell_through_rate"] = result.sell_through_rate
        return listing.model_copy(update={"market_context": market_context})
