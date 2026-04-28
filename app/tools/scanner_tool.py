from __future__ import annotations

import logging

from app.clients.ebay import EbayClient
from app.models.config import SearchConfig
from app.models.listing import RawListing
from app.storage.sqlite import SQLiteStorage


class ScannerTool:
    """Deterministic LangChain workflow tool for eBay listing ingestion."""

    name = "scanner_tool"

    def __init__(self, client: EbayClient, storage: SQLiteStorage) -> None:
        self.client = client
        self.storage = storage
        self.logger = logging.getLogger(self.__class__.__name__)

    def run(self, run_id: str, search_config: SearchConfig) -> list[RawListing]:
        self.logger.info("Scanning for listings with limit=%s", search_config.scan_limit)
        listings = self.client.fetch_psa_listings(
            limit=search_config.scan_limit,
            max_minutes_remaining=search_config.target_rules.max_minutes_remaining,
            max_current_price=search_config.target_rules.max_current_price,
            currency=search_config.bidding.currency,
        )
        for listing in listings:
            self.storage.record_fetched_listing(run_id, listing)
        self.logger.info("Scanner fetched %s listings", len(listings))
        return listings
