from __future__ import annotations

import logging
import webbrowser
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from app.clients.ebay_offer import EbayOfferApiError, OfficialEbayOfferApiClient
from app.models.analysis import AnalysisResult
from app.models.bidding import BidActionResult, BidDecision, BiddingMode
from app.models.config import BiddingConfig, SearchConfig
from app.models.listing import Listing
from app.services.bid_guardrails import BidGuardrailService
from app.storage.sqlite import SQLiteStorage


@dataclass(frozen=True)
class OfficialApiBiddingCredentials:
    client_id: str | None = None
    client_secret: str | None = None
    user_access_token: str | None = None
    user_refresh_token: str | None = None

    def is_complete(self) -> bool:
        return all(
            [
                self.client_id,
                self.client_secret,
                self.user_refresh_token,
            ]
        )


class BiddingService(ABC):
    mode: BiddingMode

    @abstractmethod
    def prepare_bid(
        self,
        listing: Listing,
        analysis: AnalysisResult,
        decision: BidDecision,
        search_config: SearchConfig,
    ) -> BidActionResult:
        raise NotImplementedError

    def _result(
        self,
        listing: Listing,
        analysis: AnalysisResult,
        decision: BidDecision,
        search_config: SearchConfig,
        status: str,
        message: str,
        success: bool = False,
        attempted: bool = False,
        mode: BiddingMode | None = None,
        external_bid_id: str | None = None,
        provider_response: dict[str, Any] | None = None,
    ) -> BidActionResult:
        recommended_bid = decision.approved_max_bid
        return BidActionResult(
            listing_id=listing.listing_id,
            mode=mode or self.mode,
            status=status,
            attempted=attempted,
            success=success,
            dry_run=search_config.dry_run,
            recommended_bid=recommended_bid,
            bid_amount=recommended_bid if attempted else None,
            listing_url=listing.url,
            item_id=listing.listing_id,
            ebay_restful_item_id=listing.ebay_restful_item_id,
            external_bid_id=external_bid_id,
            title=listing.title,
            current_price=listing.current_price,
            end_time=listing.end_time,
            estimated_market_value=analysis.estimated_market_value,
            expected_margin=decision.expected_margin,
            reasoning=analysis.reasoning,
            provider_response=provider_response or {},
            message=message,
        )


class ManualBiddingService(BiddingService):
    mode = BiddingMode.MANUAL

    def __init__(self, fallback_reason: str | None = None) -> None:
        self.fallback_reason = fallback_reason
        self.logger = logging.getLogger(self.__class__.__name__)

    def prepare_bid(
        self,
        listing: Listing,
        analysis: AnalysisResult,
        decision: BidDecision,
        search_config: SearchConfig,
    ) -> BidActionResult:
        if search_config.bidding.open_listing_in_browser and listing.url:
            webbrowser.open(listing.url)

        prefix = f"{self.fallback_reason} " if self.fallback_reason else ""
        message = (
            f"{prefix}Manual bidding required. Review {listing.title} on eBay and place any bid "
            f"yourself; the app recommends a max bid of ${decision.approved_max_bid:.2f}."
        )
        return self._result(
            listing=listing,
            analysis=analysis,
            decision=decision,
            search_config=search_config,
            status="requires_user_action" if not self.fallback_reason else "fallback_manual_required",
            message=message,
            success=False,
            attempted=False,
            mode=BiddingMode.MANUAL,
        )


class OfficialEbayBiddingService(BiddingService):
    mode = BiddingMode.OFFICIAL_API

    def __init__(
        self,
        credentials: OfficialApiBiddingCredentials,
        offer_api_client: OfficialEbayOfferApiClient | None = None,
    ) -> None:
        self.credentials = credentials
        self.offer_api_client = offer_api_client
        self.logger = logging.getLogger(self.__class__.__name__)

    def prepare_bid(
        self,
        listing: Listing,
        analysis: AnalysisResult,
        decision: BidDecision,
        search_config: SearchConfig,
    ) -> BidActionResult:
        fallback_reason = self._fallback_reason(search_config.bidding)
        if fallback_reason:
            fallback = ManualBiddingService(
                fallback_reason=fallback_reason,
            )
            return fallback.prepare_bid(listing, analysis, decision, search_config)

        if search_config.dry_run:
            return self._result(
                listing=listing,
                analysis=analysis,
                decision=decision,
                search_config=search_config,
                status="dry_run_official_api",
                message=(
                    "Dry run only. Official eBay Offer API bidding is configured, but no bid "
                    f"was submitted. The app would place a proxy bid up to "
                    f"${decision.approved_max_bid:.2f} after dry_run is disabled."
                ),
                success=False,
                attempted=False,
            )

        offer_item_id = self._resolve_offer_item_id(listing)
        if offer_item_id is None:
            fallback = ManualBiddingService(
                fallback_reason=(
                    "Official API bidding requires the RESTful eBay item ID returned by the "
                    "Browse API, but this listing only has a legacy item ID."
                )
            )
            return fallback.prepare_bid(listing, analysis, decision, search_config)

        client = self.offer_api_client or OfficialEbayOfferApiClient(
            user_access_token=self.credentials.user_access_token,
            client_id=self.credentials.client_id,
            client_secret=self.credentials.client_secret,
            refresh_token=self.credentials.user_refresh_token,
            scope=search_config.bidding.buy_offer_scope,
            marketplace_id=search_config.bidding.marketplace_id,
            environment=search_config.bidding.environment,
            timeout_seconds=search_config.bidding.offer_api_timeout_seconds,
        )
        currency = listing.currency or search_config.bidding.currency

        try:
            response = client.place_proxy_bid(
                item_id=offer_item_id,
                max_bid_amount=decision.approved_max_bid or 0.0,
                currency=currency,
            )
        except EbayOfferApiError as exc:
            self.logger.warning(
                "Official eBay proxy bid failed for listing %s with status %s",
                listing.listing_id,
                exc.status_code,
            )
            return self._result(
                listing=listing,
                analysis=analysis,
                decision=decision,
                search_config=search_config,
                status="api_error",
                message=(
                    "Official eBay Offer API bidding was attempted but eBay rejected or failed "
                    f"the request. Status={exc.status_code}; {exc}"
                ),
                success=False,
                attempted=True,
                provider_response={
                    "status_code": exc.status_code,
                    "error": str(exc),
                    "response_body": exc.response_body,
                },
            )

        return self._result(
            listing=listing,
            analysis=analysis,
            decision=decision,
            search_config=search_config,
            status="submitted",
            message=(
                "Official eBay Offer API proxy bid submitted successfully "
                f"for max bid ${decision.approved_max_bid:.2f}."
            ),
            success=True,
            attempted=True,
            external_bid_id=response.proxy_bid_id,
            provider_response=response.raw_payload,
        )

    def _is_enabled(self, bidding_config: BiddingConfig) -> bool:
        return (
            bidding_config.mode == BiddingMode.OFFICIAL_API
            and bidding_config.enabled
            and bidding_config.buy_offer_api_enabled
            and not bidding_config.require_human_confirmation
        )

    def _fallback_reason(self, bidding_config: BiddingConfig) -> str | None:
        if bidding_config.mode != BiddingMode.OFFICIAL_API:
            return "Official API bidding mode is not selected."
        if not bidding_config.enabled:
            return "Official API bidding is disabled."
        if not bidding_config.buy_offer_api_enabled:
            return "eBay Buy Offer API bidding is disabled."
        if bidding_config.require_human_confirmation:
            return "Human confirmation is required, so automatic official API bidding is disabled."
        if not self.credentials.is_complete():
            return "Official API bidding is not fully configured."
        return None

    def _resolve_offer_item_id(self, listing: Listing) -> str | None:
        candidates: list[object] = [
            listing.ebay_restful_item_id,
            listing.listing_id,
            listing.raw_payload.get("ebay_restful_item_id"),
            listing.raw_payload.get("itemId"),
        ]
        for key in ("summary", "detail"):
            value = listing.raw_payload.get(key)
            if isinstance(value, dict):
                candidates.append(value.get("itemId"))

        for candidate in candidates:
            if isinstance(candidate, str) and candidate.startswith("v1|"):
                return candidate
        return None


class BrowserAutomationBiddingService(BiddingService):
    mode = BiddingMode.BROWSER_AUTOMATION

    def prepare_bid(
        self,
        listing: Listing,
        analysis: AnalysisResult,
        decision: BidDecision,
        search_config: SearchConfig,
    ) -> BidActionResult:
        return self._result(
            listing=listing,
            analysis=analysis,
            decision=decision,
            search_config=search_config,
            status="unsupported",
            message=(
                "Browser automation bidding is intentionally unsupported. The app will not use "
                "Selenium, Playwright, Puppeteer, copied browser requests, cookie replay, browser "
                "session reuse, DOM clicking, or form submission to place eBay bids because that "
                "approach is fragile, risky, and may violate platform rules. Use the listing URL "
                "for manual bidding instead."
            ),
            success=False,
            attempted=False,
        )


def select_bidding_service(
    bidding_config: BiddingConfig,
    credentials: OfficialApiBiddingCredentials | None = None,
) -> BiddingService:
    if bidding_config.mode == BiddingMode.MANUAL:
        return ManualBiddingService()

    if bidding_config.mode == BiddingMode.OFFICIAL_API:
        resolved_credentials = credentials or OfficialApiBiddingCredentials()
        if (
            bidding_config.enabled
            and bidding_config.buy_offer_api_enabled
            and not bidding_config.require_human_confirmation
            and resolved_credentials.is_complete()
        ):
            return OfficialEbayBiddingService(resolved_credentials)
        return ManualBiddingService(
            fallback_reason="Official API bidding is not configured."
        )

    if bidding_config.mode == BiddingMode.BROWSER_AUTOMATION:
        return BrowserAutomationBiddingService()

    raise ValueError("Unsupported bidding mode")


class BidExecutionTool:
    """Deterministic LangChain workflow tool for bid guardrails and safe bid action prep."""

    name = "bid_execution_tool"

    def __init__(
        self,
        storage: SQLiteStorage,
        guardrail_service: BidGuardrailService,
        bidding_service: BiddingService,
    ) -> None:
        self.storage = storage
        self.guardrail_service = guardrail_service
        self.bidding_service = bidding_service
        self.logger = logging.getLogger(self.__class__.__name__)

    def run(
        self,
        run_id: str,
        listing: Listing,
        analysis: AnalysisResult,
        search_config: SearchConfig,
    ) -> tuple[BidDecision, BidActionResult | None]:
        decision = self.guardrail_service.decide(listing, analysis, search_config)
        self.storage.record_bid_decision(run_id, decision)
        self.logger.debug(
            "Bid decision for listing %s approved=%s",
            listing.listing_id,
            decision.approved,
        )

        if not decision.approved or decision.approved_max_bid is None:
            return decision, None

        action = self.bidding_service.prepare_bid(
            listing=listing,
            analysis=analysis,
            decision=decision,
            search_config=search_config,
        )
        self.storage.record_bid_attempt(run_id, action)
        return decision, action
