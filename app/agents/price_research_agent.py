from __future__ import annotations

from app.agents.base import BaseAgent
from app.clients.pricecharting import PriceChartingClient
from app.models.listing import Listing
from app.models.price_research import PriceResearchResult
from app.storage.sqlite import SQLiteStorage


class PriceResearchAgent(BaseAgent):
    name = "price_research"

    def __init__(self, client: PriceChartingClient, storage: SQLiteStorage) -> None:
        super().__init__()
        self.client = client
        self.storage = storage

    def run(self, run_id: str, listing: Listing) -> PriceResearchResult:
        result = self.client.research(listing)
        self.storage.record_price_research(run_id, result)
        self.logger.debug(
            "Price research for listing %s match=%.3f",
            listing.listing_id,
            result.match_confidence,
        )
        return result

