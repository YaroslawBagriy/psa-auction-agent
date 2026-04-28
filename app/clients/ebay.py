from __future__ import annotations

import base64
import json
import logging
import re
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import time
from typing import Any
from urllib.parse import quote

import requests

from app.models.listing import RawListing

RELATIVE_END_TIME_PATTERN = re.compile(r"__NOW_PLUS_(\d+)_MIN__$")
PSA_VAULT_PATTERN = re.compile(r"\bin\s+the\s+psa\s+vault\b", re.IGNORECASE)


class EbayApiError(RuntimeError):
    pass


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
    def __init__(
        self,
        app_id: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        access_token: str | None = None,
        official_seller_name: str = "psa",
        marketplace_id: str = "EBAY_US",
        environment: str = "production",
        enrich_listing_page: bool = True,
        session: requests.Session | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.client_id = client_id or app_id or ""
        self.client_secret = client_secret or ""
        self.access_token = access_token
        self.official_seller_name = official_seller_name
        self.marketplace_id = marketplace_id
        self.environment = environment.strip().lower()
        self.enrich_listing_page = enrich_listing_page
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds
        self.logger = logging.getLogger(self.__class__.__name__)
        self._token_expires_at = 0.0

    @property
    def api_base_url(self) -> str:
        if self.environment == "sandbox":
            return "https://api.sandbox.ebay.com"
        return "https://api.ebay.com"

    @property
    def oauth_url(self) -> str:
        return f"{self.api_base_url}/identity/v1/oauth2/token"

    def fetch_psa_listings(self, limit: int | None = None) -> list[RawListing]:
        target_limit = limit or 100
        token = self._get_application_access_token()
        summaries = self._search_item_summaries(token=token, limit=target_limit)
        listings: list[RawListing] = []

        for summary in summaries:
            try:
                detail = self._get_item_detail(token=token, item_id=str(summary["itemId"]))
                page_vault_text = self._fetch_listing_page_vault_text(summary.get("itemWebUrl"))
                listing = self._map_listing(summary=summary, detail=detail, page_vault_text=page_vault_text)
            except Exception as exc:
                self.logger.warning("Skipping eBay listing after mapping error: %s", exc)
                continue
            listings.append(listing)

        return listings[:target_limit]

    def _get_application_access_token(self) -> str:
        if self.access_token and time() < self._token_expires_at:
            return self.access_token

        if self.access_token and not self.client_secret:
            return self.access_token

        if not self.client_id or not self.client_secret:
            raise EbayApiError(
                "Live eBay listing fetch requires EBAY_CLIENT_ID and EBAY_CLIENT_SECRET, "
                "or a pre-minted EBAY_ACCESS_TOKEN."
            )

        credentials = f"{self.client_id}:{self.client_secret}".encode("utf-8")
        basic_auth = base64.b64encode(credentials).decode("ascii")
        response = self.session.post(
            self.oauth_url,
            headers={
                "Authorization": f"Basic {basic_auth}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "client_credentials",
                "scope": "https://api.ebay.com/oauth/api_scope",
            },
            timeout=self.timeout_seconds,
        )
        self._raise_for_status(response)
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise EbayApiError("eBay OAuth response did not include access_token.")
        self.access_token = str(token)
        self._token_expires_at = time() + max(int(payload.get("expires_in", 7200)) - 60, 60)
        return self.access_token

    def _search_item_summaries(self, token: str, limit: int) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        offset = 0
        page_limit = min(max(limit, 1), 200)
        while len(items) < limit:
            response = self.session.get(
                f"{self.api_base_url}/buy/browse/v1/item_summary/search",
                headers=self._browse_headers(token),
                params={
                    "q": "Pokemon PSA",
                    "filter": f"sellers:{{{self.official_seller_name}}},buyingOptions:{{AUCTION}}",
                    "fieldgroups": "EXTENDED",
                    "sort": "endTime",
                    "limit": str(min(page_limit, limit - len(items))),
                    "offset": str(offset),
                },
                timeout=self.timeout_seconds,
            )
            self._raise_for_status(response)
            payload = response.json()
            page_items = payload.get("itemSummaries") or []
            items.extend(page_items)
            if len(page_items) == 0 or not payload.get("next"):
                break
            offset += len(page_items)
        return items

    def _get_item_detail(self, token: str, item_id: str) -> dict[str, Any]:
        response = self.session.get(
            f"{self.api_base_url}/buy/browse/v1/item/{quote(item_id, safe='')}",
            headers=self._browse_headers(token),
            params={"fieldgroups": "PRODUCT,ADDITIONAL_SELLER_DETAILS"},
            timeout=self.timeout_seconds,
        )
        self._raise_for_status(response)
        return response.json()

    def _fetch_listing_page_vault_text(self, item_web_url: object) -> str | None:
        if not self.enrich_listing_page or not isinstance(item_web_url, str) or not item_web_url:
            return None

        try:
            response = self.session.get(
                item_web_url,
                headers={"User-Agent": "psa-pokemon-bidder/0.1"},
                timeout=self.timeout_seconds,
            )
            if getattr(response, "status_code", 200) >= 400:
                return None
            text = response.text
        except requests.RequestException:
            return None

        match = PSA_VAULT_PATTERN.search(text)
        return match.group(0) if match else None

    def _map_listing(
        self,
        summary: dict[str, Any],
        detail: dict[str, Any],
        page_vault_text: str | None,
    ) -> RawListing:
        price = summary.get("currentBidPrice") or summary.get("price") or {}
        seller = summary.get("seller") or detail.get("seller") or {}
        item_specifics = self._localized_aspects_to_dict(
            detail.get("localizedAspects") or summary.get("localizedAspects") or []
        )
        end_time = self._parse_datetime(summary.get("itemEndDate") or detail.get("itemEndDate"))
        if end_time is None:
            raise EbayApiError("Auction listing is missing itemEndDate.")

        raw_payload = {
            "summary": summary,
            "detail": detail,
        }
        page_badges = []
        if page_vault_text:
            page_badges.append(page_vault_text)
            raw_payload["listing_page_evidence"] = page_vault_text

        categories = summary.get("categories") or detail.get("categories") or []
        category_name = None
        if categories and isinstance(categories[-1], dict):
            category_name = categories[-1].get("categoryName")

        return RawListing(
            listing_id=str(summary.get("legacyItemId") or detail.get("legacyItemId") or summary.get("itemId")),
            ebay_restful_item_id=self._optional_str(summary.get("itemId") or detail.get("itemId")),
            title=str(summary.get("title") or detail.get("title") or ""),
            seller_name=str(seller.get("username") or self.official_seller_name),
            url=str(summary.get("itemWebUrl") or detail.get("itemWebUrl") or ""),
            listing_type="AUCTION" if "AUCTION" in (summary.get("buyingOptions") or []) else "UNKNOWN",
            current_price=float(price.get("value") or 0.0),
            end_time=end_time,
            currency=str(price.get("currency") or "USD"),
            subtitle=self._optional_str(summary.get("subtitle")),
            description=self._optional_str(detail.get("shortDescription") or summary.get("shortDescription")),
            condition_description=self._optional_str(detail.get("condition") or summary.get("condition")),
            page_badges=page_badges,
            page_highlights=[
                str(value)
                for value in [detail.get("itemWebUrl"), detail.get("title")]
                if isinstance(value, str) and value
            ],
            item_specifics=item_specifics,
            set_name=self._optional_str(item_specifics.get("Set")),
            category_name=self._optional_str(category_name),
            raw_payload=raw_payload,
        )

    def _browse_headers(self, token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": self.marketplace_id,
            "Accept": "application/json",
        }

    def _localized_aspects_to_dict(self, aspects: list[Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for aspect in aspects:
            if not isinstance(aspect, dict):
                continue
            name = aspect.get("name")
            value = aspect.get("value")
            if isinstance(name, str) and value is not None:
                result[name] = value
        return result

    def _optional_str(self, value: object) -> str | None:
        if value is None:
            return None
        return str(value)

    def _parse_datetime(self, value: object) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    def _raise_for_status(self, response: requests.Response) -> None:
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            body = getattr(response, "text", "")
            raise EbayApiError(f"eBay API request failed: {exc} {body}") from exc
