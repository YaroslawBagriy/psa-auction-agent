from __future__ import annotations

from app.clients.ebay_oauth import (
    BUY_OFFER_AUCTION_SCOPE,
    DEFAULT_PUBLIC_SCOPE,
    EbayOAuthClient,
    EbayOAuthConfig,
    extract_authorization_code,
    parse_scope_list,
    redact_secret,
)


class FakeOAuthResponse:
    def __init__(self, payload=None, status_code: int = 200, text: str = "") -> None:
        self.payload = payload or {}
        self.status_code = status_code
        self.text = text

    def json(self):
        return self.payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(self.text)


class FakeOAuthSession:
    def __init__(self) -> None:
        self.posts = []

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return FakeOAuthResponse(
            {
                "access_token": "access-token",
                "refresh_token": "refresh-token",
                "expires_in": 7200,
            }
        )


def test_parse_scope_list_accepts_spaces_and_commas() -> None:
    scopes = parse_scope_list(f"{DEFAULT_PUBLIC_SCOPE}, {BUY_OFFER_AUCTION_SCOPE}")

    assert scopes == (DEFAULT_PUBLIC_SCOPE, BUY_OFFER_AUCTION_SCOPE)


def test_build_authorization_url_uses_runame_and_scopes() -> None:
    client = EbayOAuthClient(
        EbayOAuthConfig(
            client_id="client-id",
            client_secret="client-secret",
            redirect_uri="Example_RuName",
            scopes=(DEFAULT_PUBLIC_SCOPE, BUY_OFFER_AUCTION_SCOPE),
        )
    )

    url, state = client.build_authorization_url(state="csrf-state")

    assert state == "csrf-state"
    assert url.startswith("https://auth.ebay.com/oauth2/authorize?")
    assert "client_id=client-id" in url
    assert "redirect_uri=Example_RuName" in url
    assert "response_type=code" in url
    assert "state=csrf-state" in url
    assert "buy.offer.auction" in url


def test_exchange_authorization_code_posts_expected_payload() -> None:
    session = FakeOAuthSession()
    client = EbayOAuthClient(
        EbayOAuthConfig(
            client_id="client-id",
            client_secret="client-secret",
            redirect_uri="Example_RuName",
            scopes=(DEFAULT_PUBLIC_SCOPE,),
        ),
        session=session,
    )

    payload = client.exchange_authorization_code("auth-code")

    assert payload["access_token"] == "access-token"
    assert payload["refresh_token"] == "refresh-token"
    assert "expires_at" in payload
    url, kwargs = session.posts[0]
    assert url == "https://api.ebay.com/identity/v1/oauth2/token"
    assert kwargs["data"] == {
        "grant_type": "authorization_code",
        "code": "auth-code",
        "redirect_uri": "Example_RuName",
    }
    assert kwargs["headers"]["Authorization"].startswith("Basic ")


def test_redact_secret_keeps_token_safe_for_terminal_output() -> None:
    assert redact_secret("abcdef1234567890") == "abcdef...7890"


def test_extract_authorization_code_from_redirect_url() -> None:
    payload = extract_authorization_code(
        "https://example.com/accepted?state=csrf-state&code=v%255E1.1%2523token&expires_in=299"
    )

    assert payload == {
        "code": "v^1.1#token",
        "state": "csrf-state",
        "expires_in": "299",
    }
