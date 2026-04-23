from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path

from app.models.listing import RawListing


class EbayClient(ABC):
    @abstractmethod
    def fetch_psa_listings(self, limit: int | None = None) -> list[RawListing]:
        raise NotImplementedError


class MockEbayClient(EbayClient):
    def __init__(self, sample_path: Path) -> None:
        self.sample_path = sample_path

    def fetch_psa_listings(self, limit: int | None = None) -> list[RawListing]:
        with self.sample_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        listings: list[RawListing] = []
        for item in payload:
            raw_payload = dict(item)
            listing = RawListing(**item, raw_payload=raw_payload)
            listings.append(listing)

        if limit is not None:
            return listings[:limit]
        return listings


class OfficialEbayApiClient(EbayClient):
    def __init__(self, app_id: str, official_seller_name: str = "psa-dna") -> None:
        self.app_id = app_id
        self.official_seller_name = official_seller_name

    def fetch_psa_listings(self, limit: int | None = None) -> list[RawListing]:
        # TODO: Wire this client to eBay Browse/Finding APIs with authenticated access,
        # seller filtering, auction-only listing filters, and robust response mapping.
        raise NotImplementedError(
            "Official eBay API integration is not wired yet. "
            "Use MockEbayClient for dry-run MVP execution."
        )

