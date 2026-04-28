from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models.listing import Listing
from app.models.pokemon import Pokemon
from app.tools.bid_execution_tool import RealEbayBidExecutor


class FakeResponse:
    status_code = 200

    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


class FakeSession:
    def __init__(self, response_text: str) -> None:
        self.response_text = response_text
        self.posts = []

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return FakeResponse(self.response_text)


def _listing() -> Listing:
    return Listing(
        listing_id="v1|123456789012|0",
        title="Pokemon Charizard PSA 10",
        seller_name="psa",
        url="https://www.ebay.com/itm/123456789012",
        is_auction=True,
        current_price=120.0,
        end_time=datetime.now(UTC) + timedelta(minutes=5),
        grading_company="PSA",
        grade_value="10",
        detected_pokemon=Pokemon.CHARIZARD,
        in_psa_vault=True,
        vault_evidence=["page_badges[0]: In the PSA Vault"],
        is_pokemon_related=True,
        normalized_title="pokemon charizard psa 10",
        raw_payload={"summary": {"legacyItemId": "123456789012", "currentBidPrice": {"currency": "USD"}}},
    )


def test_real_ebay_bid_executor_posts_place_offer_xml() -> None:
    session = FakeSession(
        """
        <PlaceOfferResponse xmlns="urn:ebay:apis:eBLBaseComponents">
          <Ack>Success</Ack>
        </PlaceOfferResponse>
        """
    )
    executor = RealEbayBidExecutor(user_access_token="user-token", session=session)

    result = executor.place_bid(_listing(), 184.5, dry_run=False)

    assert result.success is True
    assert result.attempted is True
    assert result.bid_amount == 184.5
    url, kwargs = session.posts[0]
    assert url == "https://api.ebay.com/ws/api.dll"
    assert kwargs["headers"]["X-EBAY-API-CALL-NAME"] == "PlaceOffer"
    assert kwargs["headers"]["X-EBAY-API-IAF-TOKEN"] == "user-token"
    assert "<ItemID>123456789012</ItemID>" in kwargs["data"]
    assert '<MaxBid currencyID="USD">184.50</MaxBid>' in kwargs["data"]


def test_real_ebay_bid_executor_requires_user_token() -> None:
    executor = RealEbayBidExecutor(user_access_token=None)

    result = executor.place_bid(_listing(), 184.5, dry_run=False)

    assert result.success is False
    assert "EBAY_USER_ACCESS_TOKEN" in result.message
