from __future__ import annotations

import logging

from app.agents.base import BaseAgent
from app.agents.market_query_agent import MarketQueryPlannerAgent
from app.agents.market_research_agent import MarketResearchAgent
from app.clients.ebay_market import EbayMarketResearchClient
from app.models.config import SearchConfig
from app.models.listing import Listing
from app.models.market import MarketResearchResult
from app.services.market_sanity import sanitize_market_research_result
from app.storage.sqlite import SQLiteStorage


class MarketResearchTool(BaseAgent):
    name = "market_research_tool"

    def __init__(
        self,
        storage: SQLiteStorage,
        client: EbayMarketResearchClient | None = None,
        query_planner_agent: MarketQueryPlannerAgent | None = None,
        market_research_agent: MarketResearchAgent | None = None,
    ) -> None:
        super().__init__()
        self.client = client
        self.storage = storage
        self.query_planner_agent = query_planner_agent
        self.market_research_agent = market_research_agent

    def run(
        self,
        run_id: str,
        listings: list[Listing],
        search_config: SearchConfig,
    ) -> tuple[list[Listing], dict[str, MarketResearchResult]]:
        if not listings or not search_config.market_research.enabled:
            return listings, {}

        query_plans = self.query_planner_agent.run(listings) if self.query_planner_agent else {}
        enriched_listings: list[Listing] = []
        results_by_listing_id: dict[str, MarketResearchResult] = {}
        for listing in listings:
            try:
                query_plan = query_plans.get(listing.listing_id)
                query_strings = query_plan.query_strings() if query_plan else [listing.title]
                if self.market_research_agent is not None:
                    result = self.market_research_agent.run(
                        listing=listing,
                        config=search_config.market_research,
                        query_strings=query_strings,
                    )
                elif self.client is not None:
                    result = self.client.research_listing(
                        listing,
                        search_config.market_research,
                        query_strings=query_strings,
                    )
                else:
                    raise ValueError("MarketResearchTool requires either a client or market_research_agent.")
                result = sanitize_market_research_result(result)
                self.storage.record_market_research(run_id, result)
                results_by_listing_id[listing.listing_id] = result
                enriched_listings.append(self._attach_market_research(listing, result))
                self.logger.debug(
                    "Market research listing_id=%s active=%s sold=%s sell_through=%s warnings=%s",
                    listing.listing_id,
                    result.active_listing_count,
                    result.sold_listing_count,
                    result.sell_through_rate,
                    result.warnings,
                )
            except Exception as exc:
                if self.logger.isEnabledFor(logging.DEBUG):
                    self.logger.exception("Market research failed for listing %s", listing.listing_id)
                else:
                    self.logger.warning(
                        "Step 3 result: market research could not be completed for this auction. "
                        "Continuing safely without comp evidence."
                    )
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
