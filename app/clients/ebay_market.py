from __future__ import annotations

import base64
import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from statistics import median
from time import time
from typing import Any

import requests

from app.clients.ebay import EbayApiError
from app.models.config import MarketResearchConfig
from app.models.listing import Listing
from app.models.market import MarketComp, MarketResearchResult


class EbayMarketResearchClient(ABC):
    @abstractmethod
    def research_listing(
        self,
        listing: Listing,
        config: MarketResearchConfig,
        query_strings: list[str] | None = None,
    ) -> MarketResearchResult:
        raise NotImplementedError


class MockEbayMarketResearchClient(EbayMarketResearchClient):
    def research_listing(
        self,
        listing: Listing,
        config: MarketResearchConfig,
        query_strings: list[str] | None = None,
    ) -> MarketResearchResult:
        market_context = listing.market_context
        recent_sales = [
            float(value)
            for value in market_context.get("recent_sales", [])
            if isinstance(value, (int, float))
        ]
        active_count = market_context.get("active_listing_count")
        sold_count = market_context.get("sold_listing_count")
        active_listing_count = int(active_count) if isinstance(active_count, int) else None
        sold_listing_count = int(sold_count) if isinstance(sold_count, int) else len(recent_sales) or None
        sell_through_rate = None
        if active_listing_count and sold_listing_count is not None:
            sell_through_rate = round(sold_listing_count / active_listing_count, 3)

        estimated_market_value = market_context.get("estimated_market_value")
        estimated_market_value = float(estimated_market_value) if isinstance(estimated_market_value, (int, float)) else None
        if estimated_market_value is None and recent_sales:
            estimated_market_value = round(float(median(recent_sales)), 2)

        sold_comps = [
            MarketComp(
                source="sold",
                title=listing.title,
                url=listing.url,
                price=price,
                currency=listing.currency,
            )
            for price in recent_sales[: config.sold_limit]
        ]
        evidence_summary = (
            f"Mock market context for '{listing.title}' includes "
            f"{len(recent_sales)} recent sold prices."
        )
        return MarketResearchResult(
            listing_id=listing.listing_id,
            query=(query_strings or [listing.title])[0],
            active_listing_count=active_listing_count,
            sold_listing_count=sold_listing_count,
            sell_through_rate=sell_through_rate,
            recent_sold_prices=recent_sales,
            estimated_market_value=estimated_market_value,
            sold_comps=sold_comps,
            evidence_summary=evidence_summary,
            warnings=[] if recent_sales else ["mock_market_context_has_no_recent_sales"],
        )


class OfficialEbayMarketResearchClient(EbayMarketResearchClient):
    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        access_token: str | None = None,
        marketplace_insights_access_token: str | None = None,
        marketplace_id: str = "EBAY_US",
        environment: str = "production",
        session: requests.Session | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.client_id = client_id or ""
        self.client_secret = client_secret or ""
        self.access_token = access_token
        self.marketplace_insights_access_token = marketplace_insights_access_token
        self.marketplace_id = marketplace_id
        self.environment = environment.strip().lower()
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds
        self.logger = logging.getLogger(self.__class__.__name__)
        self._token_cache: dict[str, tuple[str, float]] = {}

    @property
    def api_base_url(self) -> str:
        if self.environment == "sandbox":
            return "https://api.sandbox.ebay.com"
        return "https://api.ebay.com"

    @property
    def oauth_url(self) -> str:
        return f"{self.api_base_url}/identity/v1/oauth2/token"

    def research_listing(
        self,
        listing: Listing,
        config: MarketResearchConfig,
        query_strings: list[str] | None = None,
    ) -> MarketResearchResult:
        queries = self._build_comp_queries(listing, query_strings)
        query = queries[0]
        warnings: list[str] = []
        raw_payload: dict[str, Any] = {"queries": queries}

        active_count: int | None = None
        sold_count: int | None = None
        active_comps: list[MarketComp] = []
        sold_comps: list[MarketComp] = []

        try:
            active_payload = self._search_active_comps(query=query, limit=config.active_limit)
            raw_payload["active"] = active_payload
            active_count = self._optional_int(active_payload.get("total"))
            active_items = active_payload.get("itemSummaries") or []
            active_comps = [
                self._market_comp_from_item(item, source="active")
                for item in active_items
                if isinstance(item, dict)
            ]
        except Exception as exc:
            warning = f"active_comp_search_failed: {exc}"
            self.logger.warning(warning)
            warnings.append(warning)

        if config.marketplace_insights_enabled:
            sold_payloads: list[dict[str, Any]] = []
            for sold_query in queries:
                try:
                    sold_payload = self._search_sold_comps(
                        query=sold_query,
                        limit=config.sold_limit,
                        scope=config.marketplace_insights_scope,
                    )
                    sold_payloads.append({"query": sold_query, "payload": sold_payload})
                    sold_items = sold_payload.get("itemSales") or sold_payload.get("itemSummaries") or []
                    if sold_items:
                        raw_payload["sold"] = sold_payloads
                        raw_payload["selected_sold_query"] = sold_query
                        sold_count = self._optional_int(sold_payload.get("total"))
                        sold_comps = [
                            self._market_comp_from_item(item, source="sold")
                            for item in sold_items
                            if isinstance(item, dict)
                        ]
                        break
                except Exception as exc:
                    warning = f"sold_comp_search_unavailable query='{sold_query}': {exc}"
                    self.logger.warning(warning)
                    warnings.append(warning)
            if "sold" not in raw_payload and sold_payloads:
                raw_payload["sold"] = sold_payloads
        else:
            warnings.append("marketplace_insights_disabled")

        recent_sold_prices = [
            comp.price
            for comp in sold_comps
            if comp.price is not None
        ]
        estimated_market_value = round(float(median(recent_sold_prices)), 2) if recent_sold_prices else None

        if sold_count is None and sold_comps:
            sold_count = len(sold_comps)
        if active_count is None and active_comps:
            active_count = len(active_comps)

        sell_through_rate = None
        if active_count and sold_count is not None:
            sell_through_rate = round(sold_count / active_count, 3)

        evidence_summary = self._build_evidence_summary(
            query=query,
            active_count=active_count,
            sold_count=sold_count,
            sell_through_rate=sell_through_rate,
            recent_sold_prices=recent_sold_prices,
            estimated_market_value=estimated_market_value,
            warnings=warnings,
        )

        return MarketResearchResult(
            listing_id=listing.listing_id,
            query=query,
            active_listing_count=active_count,
            sold_listing_count=sold_count,
            sell_through_rate=sell_through_rate,
            recent_sold_prices=recent_sold_prices,
            estimated_market_value=estimated_market_value,
            active_comps=active_comps,
            sold_comps=sold_comps,
            evidence_summary=evidence_summary,
            warnings=warnings,
            raw_payload=raw_payload,
        )

    def _search_active_comps(self, query: str, limit: int) -> dict[str, Any]:
        token = self._get_application_access_token("https://api.ebay.com/oauth/api_scope")
        response = self.session.get(
            f"{self.api_base_url}/buy/browse/v1/item_summary/search",
            headers=self._headers(token),
            params={
                "q": query,
                "filter": "buyingOptions:{FIXED_PRICE|AUCTION}",
                "fieldgroups": "EXTENDED",
                "limit": str(limit),
            },
            timeout=self.timeout_seconds,
        )
        self._raise_for_status(response)
        return response.json()

    def _search_sold_comps(self, query: str, limit: int, scope: str) -> dict[str, Any]:
        token = self._get_marketplace_insights_token(scope)
        response = self.session.get(
            f"{self.api_base_url}/buy/marketplace_insights/v1_beta/item_sales/search",
            headers=self._headers(token),
            params={
                "q": query,
                "limit": str(limit),
            },
            timeout=self.timeout_seconds,
        )
        self._raise_for_status(response)
        return response.json()

    def _get_marketplace_insights_token(self, scope: str) -> str:
        if self.marketplace_insights_access_token:
            return self.marketplace_insights_access_token
        return self._get_application_access_token(scope)

    def _get_application_access_token(self, scope: str) -> str:
        cached = self._token_cache.get(scope)
        if cached and time() < cached[1]:
            return cached[0]

        if scope == "https://api.ebay.com/oauth/api_scope" and self.access_token and not self.client_secret:
            return self.access_token

        if not self.client_id or not self.client_secret:
            raise EbayApiError(
                "eBay market research requires EBAY_CLIENT_ID and EBAY_CLIENT_SECRET, "
                "or a pre-minted access token for the requested API scope."
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
                "scope": scope,
            },
            timeout=self.timeout_seconds,
        )
        self._raise_for_status(response)
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise EbayApiError("eBay OAuth response did not include access_token.")
        token_value = str(token)
        expires_at = time() + max(int(payload.get("expires_in", 7200)) - 60, 60)
        self._token_cache[scope] = (token_value, expires_at)
        return token_value

    def _headers(self, token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": self.marketplace_id,
            "Accept": "application/json",
        }

    def _build_comp_queries(self, listing: Listing, query_strings: list[str] | None) -> list[str]:
        candidates = query_strings or [listing.title]
        queries: list[str] = []
        for candidate in candidates:
            query = " ".join(candidate.split())
            if query and query not in queries:
                queries.append(query)
        if not queries:
            queries.append(" ".join(listing.title.split()))
        return queries

    def _market_comp_from_item(self, item: dict[str, Any], source: str) -> MarketComp:
        price_payload = (
            item.get("price")
            or item.get("currentBidPrice")
            or item.get("soldPrice")
            or item.get("itemPrice")
            or item.get("convertedPrice")
            or {}
        )
        seller = item.get("seller") or {}
        return MarketComp(
            source=source,  # type: ignore[arg-type]
            item_id=self._optional_str(item.get("legacyItemId") or item.get("itemId")),
            title=str(item.get("title") or ""),
            url=self._optional_str(item.get("itemWebUrl") or item.get("itemHref")),
            price=self._extract_price(price_payload),
            currency=self._extract_currency(price_payload),
            seller_name=self._optional_str(seller.get("username") if isinstance(seller, dict) else None),
            sold_date=self._parse_datetime(
                item.get("itemSoldDate")
                or item.get("soldDate")
                or item.get("lastSoldDate")
                or item.get("transactionDate")
            ),
            end_time=self._parse_datetime(item.get("itemEndDate")),
            raw_payload=item,
        )

    def _build_evidence_summary(
        self,
        query: str,
        active_count: int | None,
        sold_count: int | None,
        sell_through_rate: float | None,
        recent_sold_prices: list[float],
        estimated_market_value: float | None,
        warnings: list[str],
    ) -> str:
        price_summary = "no exact sold prices were returned"
        if recent_sold_prices:
            price_summary = (
                f"sold price range ${min(recent_sold_prices):.2f}-${max(recent_sold_prices):.2f}; "
                f"median ${estimated_market_value:.2f}"
            )
        return (
            f"eBay comp query '{query}' returned active_count={active_count}, "
            f"sold_count={sold_count}, sell_through_rate={sell_through_rate}; "
            f"{price_summary}. warnings={warnings}"
        )

    def _extract_price(self, value: object) -> float | None:
        if isinstance(value, dict):
            raw_value = value.get("value")
        else:
            raw_value = value
        if raw_value is None:
            return None
        try:
            return float(raw_value)
        except (TypeError, ValueError):
            return None

    def _extract_currency(self, value: object) -> str:
        if isinstance(value, dict):
            currency = value.get("currency")
            if isinstance(currency, str) and currency:
                return currency
        return "USD"

    def _optional_int(self, value: object) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _optional_str(self, value: object) -> str | None:
        if value is None:
            return None
        return str(value)

    def _parse_datetime(self, value: object) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    def _raise_for_status(self, response: requests.Response) -> None:
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            body = getattr(response, "text", "")
            raise EbayApiError(f"eBay API request failed: {exc} {body}") from exc
