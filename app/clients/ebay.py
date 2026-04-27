from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.models.listing import RawListing

RELATIVE_END_TIME_PATTERN = re.compile(r"__NOW_PLUS_(\d+)_MIN__$")


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
            resolved_item = self._resolve_dynamic_fields(dict(item))
            raw_payload = dict(resolved_item)
            listing = RawListing(**resolved_item, raw_payload=raw_payload)
            listings.append(listing)

        if limit is not None:
            return listings[:limit]
        return listings

    def _resolve_dynamic_fields(self, item: dict[str, object]) -> dict[str, object]:
        end_time = item.get("end_time")
        if isinstance(end_time, str):
            match = RELATIVE_END_TIME_PATTERN.match(end_time)
            if match:
                minutes = int(match.group(1))
                item["end_time"] = datetime.now(UTC) + timedelta(minutes=minutes)
        return item


class OfficialEbayApiClient(EbayClient):
    def __init__(self, app_id: str, official_seller_name: str = "psa-dna") -> None:
        self.app_id = app_id
        self.official_seller_name = official_seller_name

    def fetch_psa_listings(self, limit: int | None = None) -> list[RawListing]:
        # TODO: Wire this client to eBay Browse/Finding APIs with authenticated access,
        # seller filtering, auction-only listing filters, robust response mapping, and
        # listing-detail enrichment so page-level PSA Vault badges/text are captured even
        # when the title does not mention vault status.
        raise NotImplementedError(
            "Official eBay API integration is not wired yet. "
            "Use MockEbayClient for dry-run MVP execution."
        )
