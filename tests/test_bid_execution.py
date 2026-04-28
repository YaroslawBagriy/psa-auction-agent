from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import requests

from app.clients.ebay_offer import OfficialEbayOfferApiClient
from app.models.analysis import AnalysisResult
from app.models.bidding import BidDecision, BiddingMode
from app.models.config import BidGuardrails, BiddingConfig, SearchConfig, TargetRules
from app.models.listing import Listing
from app.models.pokemon import Pokemon
from app.services.bid_guardrails import BidGuardrailService
from app.storage.sqlite import SQLiteStorage
from app.tools.bid_execution_tool import (
    BidExecutionTool,
    BrowserAutomationBiddingService,
    ManualBiddingService,
    OfficialApiBiddingCredentials,
    OfficialEbayBiddingService,
    select_bidding_service,
)


class FakeOfferResponse:
    def __init__(
        self,
        payload: dict | None = None,
        text: str = "",
        status_code: int = 200,
    ) -> None:
        self.payload = payload or {}
        self.text = text
        self.status_code = status_code
        self.content = text.encode("utf-8") if text else b"{}"

    def json(self):
        return self.payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(self.text)


class FakeOfferSession:
    def __init__(self, response: FakeOfferResponse | None = None) -> None:
        self.posts = []
        self.response = response or FakeOfferResponse({"proxyBidId": "proxy-bid-123"})

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return self.response


class SequenceOfferSession:
    def __init__(self, responses: list[FakeOfferResponse]) -> None:
        self.posts = []
        self.responses = list(responses)

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return self.responses.pop(0)


def _listing(**overrides) -> Listing:
    payload = {
        "listing_id": "v1|123456789012|0",
        "ebay_restful_item_id": "v1|123456789012|0",
        "title": "Pokemon Charizard PSA 10",
        "seller_name": "psa",
        "url": "https://www.ebay.com/itm/123456789012",
        "is_auction": True,
        "current_price": 120.0,
        "end_time": datetime.now(UTC) + timedelta(minutes=5),
        "grading_company": "PSA",
        "grade_value": "10",
        "detected_pokemon": Pokemon.CHARIZARD,
        "in_psa_vault": True,
        "vault_evidence": ["page_badges[0]: In the PSA Vault"],
        "is_pokemon_related": True,
        "normalized_title": "pokemon charizard psa 10",
        "raw_payload": {"summary": {"legacyItemId": "123456789012"}},
    }
    payload.update(overrides)
    return Listing(**payload)


def _analysis(**overrides) -> AnalysisResult:
    payload = {
        "listing_id": "v1|123456789012|0",
        "url": "https://www.ebay.com/itm/123456789012",
        "should_bid": True,
        "confidence": 0.8,
        "estimated_market_value": 205.0,
        "recommended_max_bid": 184.5,
        "trend_outlook": "upward",
        "reasoning": "Strong market context.",
        "risk_flags": [],
    }
    payload.update(overrides)
    return AnalysisResult(**payload)


def _decision(**overrides) -> BidDecision:
    payload = {
        "listing_id": "v1|123456789012|0",
        "approved": True,
        "reason": "Approved by deterministic bid guardrails.",
        "approved_max_bid": 184.5,
        "expected_margin": 20.5,
        "risk_flags": [],
        "dry_run": True,
    }
    payload.update(overrides)
    return BidDecision(**payload)


def _search_config(**overrides) -> SearchConfig:
    payload = {
        "target_pokemon": [Pokemon.CHARIZARD],
        "target_rules": TargetRules(allowed_grades={"10"}),
    }
    payload.update(overrides)
    return SearchConfig(**payload)


def _run_tool(
    tmp_path: Path,
    listing: Listing | None = None,
    analysis: AnalysisResult | None = None,
    search_config: SearchConfig | None = None,
):
    storage = SQLiteStorage(tmp_path / "bidding.db")
    try:
        tool = BidExecutionTool(
            storage=storage,
            guardrail_service=BidGuardrailService(storage=storage),
            bidding_service=ManualBiddingService(),
        )
        return tool.run(
            run_id="test-run",
            listing=listing or _listing(),
            analysis=analysis or _analysis(),
            search_config=search_config or _search_config(),
        )
    finally:
        storage.close()


def test_manual_mode_returns_requires_user_action() -> None:
    service = ManualBiddingService()

    result = service.prepare_bid(_listing(), _analysis(), _decision(), _search_config())

    assert result.mode == BiddingMode.MANUAL
    assert result.status == "requires_user_action"
    assert result.attempted is False
    assert result.recommended_bid == 184.5
    assert result.listing_url == "https://www.ebay.com/itm/123456789012"
    assert "Manual bidding required" in result.message


def test_official_mode_with_missing_credentials_falls_back_to_manual() -> None:
    service = select_bidding_service(
        BiddingConfig(mode=BiddingMode.OFFICIAL_API, enabled=True, buy_offer_api_enabled=True),
        OfficialApiBiddingCredentials(client_id="client-id"),
    )

    result = service.prepare_bid(_listing(), _analysis(), _decision(), _search_config())

    assert result.mode == BiddingMode.MANUAL
    assert result.status == "fallback_manual_required"
    assert "Official API bidding is not configured" in result.message


def test_official_mode_disabled_falls_back_to_manual() -> None:
    service = select_bidding_service(
        BiddingConfig(mode=BiddingMode.OFFICIAL_API, enabled=False, buy_offer_api_enabled=True),
        OfficialApiBiddingCredentials(
            client_id="client-id",
            client_secret="client-secret",
            user_access_token="access-token",
            user_refresh_token="refresh-token",
        ),
    )

    result = service.prepare_bid(_listing(), _analysis(), _decision(), _search_config())

    assert result.mode == BiddingMode.MANUAL
    assert result.status == "fallback_manual_required"


def test_official_mode_with_human_confirmation_falls_back_to_manual() -> None:
    service = select_bidding_service(
        BiddingConfig(
            mode=BiddingMode.OFFICIAL_API,
            enabled=True,
            buy_offer_api_enabled=True,
            require_human_confirmation=True,
        ),
        OfficialApiBiddingCredentials(
            client_id="client-id",
            client_secret="client-secret",
            user_access_token="access-token",
            user_refresh_token="refresh-token",
        ),
    )

    result = service.prepare_bid(_listing(), _analysis(), _decision(), _search_config())

    assert result.mode == BiddingMode.MANUAL
    assert result.status == "fallback_manual_required"


def test_official_mode_complete_config_dry_run_does_not_submit_bid() -> None:
    session = FakeOfferSession()
    offer_client = OfficialEbayOfferApiClient(
        user_access_token="access-token",
        session=session,
    )
    service = OfficialEbayBiddingService(
        OfficialApiBiddingCredentials(
            client_id="client-id",
            client_secret="client-secret",
            user_access_token="access-token",
            user_refresh_token="refresh-token",
        ),
        offer_api_client=offer_client,
    )
    config = _search_config(
        bidding=BiddingConfig(
            mode=BiddingMode.OFFICIAL_API,
            enabled=True,
            buy_offer_api_enabled=True,
            require_human_confirmation=False,
        )
    )

    result = service.prepare_bid(_listing(), _analysis(), _decision(), config)

    assert result.mode == BiddingMode.OFFICIAL_API
    assert result.status == "dry_run_official_api"
    assert result.attempted is False
    assert session.posts == []


def test_official_mode_complete_config_submits_proxy_bid_through_offer_api() -> None:
    session = FakeOfferSession()
    offer_client = OfficialEbayOfferApiClient(
        user_access_token="access-token",
        marketplace_id="EBAY_US",
        environment="sandbox",
        session=session,
    )
    service = OfficialEbayBiddingService(
        OfficialApiBiddingCredentials(
            client_id="client-id",
            client_secret="client-secret",
            user_access_token="access-token",
            user_refresh_token="refresh-token",
        ),
        offer_api_client=offer_client,
    )
    config = _search_config(
        dry_run=False,
        bidding=BiddingConfig(
            mode=BiddingMode.OFFICIAL_API,
            enabled=True,
            buy_offer_api_enabled=True,
            require_human_confirmation=False,
            marketplace_id="EBAY_US",
            environment="sandbox",
        ),
    )

    result = service.prepare_bid(_listing(), _analysis(), _decision(), config)

    assert result.mode == BiddingMode.OFFICIAL_API
    assert result.status == "submitted"
    assert result.attempted is True
    assert result.success is True
    assert result.bid_amount == 184.5
    assert result.external_bid_id == "proxy-bid-123"
    assert len(session.posts) == 1
    url, kwargs = session.posts[0]
    assert url.endswith("/buy/offer/v1_beta/bidding/v1%7C123456789012%7C0/place_proxy_bid")
    assert kwargs["headers"]["Authorization"] == "Bearer access-token"
    assert kwargs["headers"]["X-EBAY-C-MARKETPLACE-ID"] == "EBAY_US"
    assert kwargs["json"] == {
        "maxAmount": {
            "currency": "USD",
            "value": "184.50",
        }
    }


def test_offer_api_client_refreshes_user_access_token_before_proxy_bid() -> None:
    session = SequenceOfferSession(
        [
            FakeOfferResponse({"access_token": "fresh-user-token", "expires_in": 7200}),
            FakeOfferResponse({"proxyBidId": "proxy-bid-123"}),
        ]
    )
    client = OfficialEbayOfferApiClient(
        client_id="client-id",
        client_secret="client-secret",
        refresh_token="refresh-token",
        scope="https://api.ebay.com/oauth/api_scope/buy.offer.auction",
        session=session,
    )

    response = client.place_proxy_bid(
        item_id="v1|123456789012|0",
        max_bid_amount=184.5,
        currency="USD",
    )

    assert response.proxy_bid_id == "proxy-bid-123"
    assert len(session.posts) == 2
    oauth_url, oauth_kwargs = session.posts[0]
    bid_url, bid_kwargs = session.posts[1]
    assert oauth_url.endswith("/identity/v1/oauth2/token")
    assert oauth_kwargs["data"]["grant_type"] == "refresh_token"
    assert oauth_kwargs["data"]["refresh_token"] == "refresh-token"
    assert oauth_kwargs["data"]["scope"] == "https://api.ebay.com/oauth/api_scope/buy.offer.auction"
    assert oauth_kwargs["headers"]["Authorization"].startswith("Basic ")
    assert bid_url.endswith("/buy/offer/v1_beta/bidding/v1%7C123456789012%7C0/place_proxy_bid")
    assert bid_kwargs["headers"]["Authorization"] == "Bearer fresh-user-token"


def test_official_mode_api_error_returns_failed_attempt() -> None:
    session = FakeOfferSession(FakeOfferResponse(text="approval missing", status_code=403))
    offer_client = OfficialEbayOfferApiClient(
        user_access_token="access-token",
        session=session,
    )
    service = OfficialEbayBiddingService(
        OfficialApiBiddingCredentials(
            client_id="client-id",
            client_secret="client-secret",
            user_access_token="access-token",
            user_refresh_token="refresh-token",
        ),
        offer_api_client=offer_client,
    )
    config = _search_config(
        dry_run=False,
        bidding=BiddingConfig(
            mode=BiddingMode.OFFICIAL_API,
            enabled=True,
            buy_offer_api_enabled=True,
            require_human_confirmation=False,
        ),
    )

    result = service.prepare_bid(_listing(), _analysis(), _decision(), config)

    assert result.mode == BiddingMode.OFFICIAL_API
    assert result.status == "api_error"
    assert result.attempted is True
    assert result.success is False
    assert result.provider_response["status_code"] == 403


def test_browser_automation_mode_returns_unsupported() -> None:
    service = BrowserAutomationBiddingService()

    result = service.prepare_bid(_listing(), _analysis(), _decision(), _search_config())

    assert result.mode == BiddingMode.BROWSER_AUTOMATION
    assert result.status == "unsupported"
    assert result.attempted is False
    assert "intentionally unsupported" in result.message


def test_browser_automation_mode_does_not_import_browser_automation_libraries() -> None:
    BrowserAutomationBiddingService().prepare_bid(_listing(), _analysis(), _decision(), _search_config())

    assert "selenium" not in sys.modules
    assert "playwright" not in sys.modules
    assert "puppeteer" not in sys.modules


def test_recommended_bid_never_exceeds_configured_max_bid_cap(tmp_path: Path) -> None:
    decision, action = _run_tool(
        tmp_path,
        search_config=_search_config(bid_guardrails=BidGuardrails(max_bid_cap=150.0)),
    )

    assert decision.approved is True
    assert decision.approved_max_bid == 150.0
    assert action is not None
    assert action.recommended_bid == 150.0


def test_low_confidence_blocks_bid_recommendation(tmp_path: Path) -> None:
    decision, action = _run_tool(tmp_path, analysis=_analysis(confidence=0.2))

    assert decision.approved is False
    assert "confidence" in decision.reason.lower()
    assert action is None


def test_low_margin_opportunities_are_skipped(tmp_path: Path) -> None:
    decision, action = _run_tool(
        tmp_path,
        analysis=_analysis(estimated_market_value=190.0, recommended_max_bid=184.5),
    )

    assert decision.approved is False
    assert "margin" in decision.reason.lower()
    assert action is None


def test_seller_mismatch_blocks_recommendation(tmp_path: Path) -> None:
    decision, action = _run_tool(tmp_path, listing=_listing(seller_name="not-psa"))

    assert decision.approved is False
    assert "seller" in decision.reason.lower()
    assert action is None
