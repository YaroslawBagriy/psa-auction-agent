from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.clients.ebay_market import OfficialEbayMarketResearchClient
from app.models.config import MarketResearchConfig
from app.models.listing import Listing
from app.models.pokemon import Pokemon


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
        return FakeResponse({"access_token": f"token-{len(self.posts)}", "expires_in": 7200})

    def get(self, url, **kwargs):
        self.gets.append((url, kwargs))
        if "item_summary/search" in url:
            return FakeResponse(
                {
                    "total": 45,
                    "itemSummaries": [
                        {
                            "itemId": "v1|active-1|0",
                            "legacyItemId": "active-1",
                            "title": "2021 POKEMON CELEBRATIONS CLASSIC COLLECTION #145 GARCHOMP C LV.X-HOLO PSA 10",
                            "price": {"value": "84.99", "currency": "USD"},
                            "seller": {"username": "seller-a"},
                            "itemWebUrl": "https://www.ebay.com/itm/active-1",
                        }
                    ],
                }
            )
        if "marketplace_insights" in url:
            return FakeResponse(
                {
                    "total": 52,
                    "itemSales": [
                        {
                            "itemId": "v1|sold-1|0",
                            "legacyItemId": "sold-1",
                            "title": "2021 POKEMON CELEBRATIONS CLASSIC COLLECTION #145 GARCHOMP C LV.X-HOLO PSA 10",
                            "price": {"value": "60.00", "currency": "USD"},
                            "itemWebUrl": "https://www.ebay.com/itm/sold-1",
                            "itemSoldDate": "2026-04-20T12:00:00.000Z",
                        },
                        {
                            "itemId": "v1|sold-2|0",
                            "legacyItemId": "sold-2",
                            "title": "2021 POKEMON CELEBRATIONS CLASSIC COLLECTION #145 GARCHOMP C LV.X-HOLO PSA 10",
                            "price": {"value": "75.00", "currency": "USD"},
                            "itemWebUrl": "https://www.ebay.com/itm/sold-2",
                            "itemSoldDate": "2026-04-21T12:00:00.000Z",
                        },
                    ],
                }
            )
        return FakeResponse()


class ZeroThenSoldSession(FakeSession):
    def __init__(self) -> None:
        super().__init__()
        self.sold_calls = 0

    def get(self, url, **kwargs):
        if "marketplace_insights" not in url:
            return super().get(url, **kwargs)
        self.gets.append((url, kwargs))
        self.sold_calls += 1
        if self.sold_calls == 1:
            return FakeResponse({"total": 0, "itemSales": []})
        return FakeResponse(
            {
                "total": 2,
                "itemSales": [
                    {
                        "itemId": "v1|sold-fallback|0",
                        "legacyItemId": "sold-fallback",
                        "title": "2021 POKEMON CELEBRATIONS GARCHOMP C LV.X #145 PSA 10",
                        "price": {"value": "70.00", "currency": "USD"},
                        "itemWebUrl": "https://www.ebay.com/itm/sold-fallback",
                    }
                ],
            }
        )


def _listing() -> Listing:
    return Listing(
        listing_id="117155708072",
        title="2021 POKEMON CELEBRATIONS CLASSIC COLLECTION #145 GARCHOMP C LV.X-HOLO PSA 10",
        seller_name="psa",
        url="https://www.ebay.com/itm/117155708072",
        is_auction=True,
        current_price=119.99,
        currency="USD",
        end_time=datetime.now(UTC) + timedelta(hours=1),
        grading_company="PSA",
        grade_value="10",
        detected_pokemon=Pokemon.GARCHOMP,
        set_name="Celebrations Classic Collection",
        card_number="145",
        in_psa_vault=True,
        is_pokemon_related=True,
        normalized_title="2021 pokemon celebrations classic collection 145 garchomp c lvx holo psa 10",
        raw_payload={},
    )


def test_official_market_research_fetches_active_and_sold_comps() -> None:
    session = FakeSession()
    client = OfficialEbayMarketResearchClient(
        client_id="client-id",
        client_secret="client-secret",
        session=session,
    )

    result = client.research_listing(
        _listing(),
        MarketResearchConfig(
            marketplace_insights_enabled=True,
            active_limit=50,
            sold_limit=50,
        ),
    )

    assert result.query == _listing().title
    assert result.active_listing_count == 45
    assert result.sold_listing_count == 52
    assert result.sell_through_rate == 1.156
    assert result.recent_sold_prices == [60.0, 75.0]
    assert result.estimated_market_value == 67.5
    assert len(result.active_comps) == 1
    assert len(result.sold_comps) == 2
    assert "sold price range $60.00-$75.00" in result.evidence_summary

    requested_scopes = [post[1]["data"]["scope"] for post in session.posts]
    assert "https://api.ebay.com/oauth/api_scope" in requested_scopes
    assert "https://api.ebay.com/oauth/api_scope/buy.marketplace.insights" in requested_scopes

    active_params = session.gets[0][1]["params"]
    sold_params = session.gets[1][1]["params"]
    assert active_params["q"] == _listing().title
    assert sold_params["q"] == _listing().title
    assert "buyingOptions:{FIXED_PRICE|AUCTION}" == active_params["filter"]


def test_official_market_research_skips_sold_comps_when_insights_disabled() -> None:
    session = FakeSession()
    client = OfficialEbayMarketResearchClient(
        client_id="client-id",
        client_secret="client-secret",
        session=session,
    )

    result = client.research_listing(
        _listing(),
        MarketResearchConfig(marketplace_insights_enabled=False),
    )

    assert result.active_listing_count == 45
    assert result.sold_listing_count is None
    assert result.estimated_market_value is None
    assert result.warnings == ["marketplace_insights_disabled"]
    assert all("marketplace_insights" not in call[0] for call in session.gets)


def test_official_market_research_tries_query_variants_for_sold_comps() -> None:
    session = ZeroThenSoldSession()
    client = OfficialEbayMarketResearchClient(
        client_id="client-id",
        client_secret="client-secret",
        session=session,
    )

    result = client.research_listing(
        _listing(),
        MarketResearchConfig(marketplace_insights_enabled=True),
        query_strings=[
            _listing().title,
            "2021 Pokemon Celebrations Garchomp C LV.X #145 PSA 10",
        ],
    )

    assert result.sold_listing_count == 2
    assert result.recent_sold_prices == [70.0]
    assert result.estimated_market_value == 70.0
    sold_gets = [call for call in session.gets if "marketplace_insights" in call[0]]
    assert [call[1]["params"]["q"] for call in sold_gets] == [
        _listing().title,
        "2021 Pokemon Celebrations Garchomp C LV.X #145 PSA 10",
    ]
