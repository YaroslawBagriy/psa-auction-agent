from __future__ import annotations

import logging
from collections.abc import Iterator

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
        return list(self.iter_listings(run_id=run_id, search_config=search_config))

    def iter_listings(self, run_id: str, search_config: SearchConfig) -> Iterator[RawListing]:
        self.logger.info("Scanning up to %s PSA auctions...", search_config.scan_limit)
        count = 0
        for listing in self.client.iter_psa_listings(
            limit=search_config.scan_limit,
            max_minutes_remaining=search_config.target_rules.max_minutes_remaining,
            max_current_price=search_config.target_rules.max_current_price,
            currency=search_config.bidding.currency,
        ):
            self.storage.record_fetched_listing(run_id, listing)
            count += 1
            yield listing
        self.logger.info("Finished scanning %s PSA auctions.", count)
