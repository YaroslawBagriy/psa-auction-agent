from __future__ import annotations

from app.agents.base import BaseAgent
from app.clients.ebay import EbayClient
from app.models.config import SearchConfig
from app.models.listing import RawListing
from app.storage.sqlite import SQLiteStorage


class ScannerAgent(BaseAgent):
    name = "scanner"

    def __init__(self, client: EbayClient, storage: SQLiteStorage) -> None:
        super().__init__()
        self.client = client
        self.storage = storage

    def scan(self, run_id: str, search_config: SearchConfig) -> list[RawListing]:
        self.logger.info("Scanning for listings with limit=%s", search_config.scan_limit)
        listings = self.client.fetch_psa_listings(limit=search_config.scan_limit)
        for listing in listings:
            self.storage.record_fetched_listing(run_id, listing)
        self.logger.info("Scanner fetched %s listings", len(listings))
        return listings

