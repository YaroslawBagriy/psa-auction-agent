from __future__ import annotations

from app.clients.ebay import OfficialEbayApiClient


class FakeResponse:
    def __init__(self, payload=None, text: str = "", status_code: int = 200) -> None:
        self.payload = payload or {}
        self.text = text
        self.status_code = status_code

    def json(self):
        return self.payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(self.text)


class FakeSession:
    def __init__(self) -> None:
        self.posts = []
        self.gets = []

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return FakeResponse({"access_token": "app-token", "expires_in": 7200})

    def get(self, url, **kwargs):
        self.gets.append((url, kwargs))
        if "item_summary/search" in url:
            return FakeResponse(
                {
                    "itemSummaries": [
                        {
                            "itemId": "v1|123456789012|0",
                            "legacyItemId": "123456789012",
                            "title": "2025 Pokemon Mega Charizard X EX PSA 10",
                            "seller": {"username": "psa"},
                            "buyingOptions": ["AUCTION"],
                            "currentBidPrice": {"value": "120.00", "currency": "USD"},
                            "itemEndDate": "2030-01-01T18:00:00.000Z",
                            "itemWebUrl": "https://www.ebay.com/itm/123456789012",
                            "shortDescription": "Official PSA auction",
                            "categories": [{"categoryName": "Pokemon TCG"}],
                        }
                    ]
                }
            )
        if "/buy/browse/v1/item/" in url:
            return FakeResponse(
                {
                    "title": "2025 Pokemon Mega Charizard X EX PSA 10",
                    "shortDescription": "Official PSA detail",
                    "condition": "Graded",
                    "localizedAspects": [
                        {"name": "Set", "value": "Phantasmal Flames"},
                        {"name": "Card Number", "value": "109"},
                    ],
                }
            )
        return FakeResponse(text="<html><body>In the PSA Vault</body></html>")


def test_official_ebay_client_fetches_and_maps_auction_listings() -> None:
    session = FakeSession()
    client = OfficialEbayApiClient(
        client_id="client-id",
        client_secret="client-secret",
        session=session,
    )

    listings = client.fetch_psa_listings(
        limit=1,
        max_current_price=1500.0,
        currency="USD",
    )

    assert len(listings) == 1
    listing = listings[0]
    assert listing.listing_id == "123456789012"
    assert listing.ebay_restful_item_id == "v1|123456789012|0"
    assert listing.seller_name == "psa"
    assert listing.listing_type == "AUCTION"
    assert listing.current_price == 120.0
    assert listing.page_badges == ["In the PSA Vault"]
    assert listing.item_specifics["Set"] == "Phantasmal Flames"
    assert session.posts[0][0].endswith("/identity/v1/oauth2/token")
    search_params = session.gets[0][1]["params"]
    assert "sellers:{psa}" in search_params["filter"]
    assert "buyingOptions:{AUCTION}" in search_params["filter"]
    assert "itemEndDate:[" not in search_params["filter"]
    assert "price:[..1500.00]" in search_params["filter"]
    assert "priceCurrency:USD" in search_params["filter"]
    assert search_params["sort"] == "endingSoonest"


def test_official_ebay_client_adds_end_date_filter_only_when_configured() -> None:
    session = FakeSession()
    client = OfficialEbayApiClient(
        client_id="client-id",
        client_secret="client-secret",
        session=session,
    )

    client.fetch_psa_listings(
        limit=1,
        max_minutes_remaining=10,
        max_current_price=1500.0,
        currency="USD",
    )

    search_params = session.gets[0][1]["params"]
    assert "itemEndDate:[" in search_params["filter"]


def test_official_ebay_client_defaults_to_psa_store_seller() -> None:
    client = OfficialEbayApiClient(access_token="app-token", enrich_listing_page=False)

    assert client.official_seller_name == "psa"
