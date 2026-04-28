from __future__ import annotations

import base64
from dataclasses import dataclass
from time import time
from typing import Any
from urllib.parse import quote

import requests


class EbayOfferApiError(RuntimeError):
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_body: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


@dataclass(frozen=True)
class PlaceProxyBidResponse:
    proxy_bid_id: str | None
    raw_payload: dict[str, Any]


class OfficialEbayOfferApiClient:
    """Official eBay Buy Offer API client for approved proxy bidding access."""

    def __init__(
        self,
        user_access_token: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        refresh_token: str | None = None,
        scope: str = "https://api.ebay.com/oauth/api_scope/buy.offer.auction",
        marketplace_id: str = "EBAY_US",
        environment: str = "production",
        session: requests.Session | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.user_access_token = user_access_token
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.scope = scope
        self.marketplace_id = marketplace_id
        self.environment = environment.strip().lower()
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds
        self._token_expires_at = 0.0

    @property
    def api_base_url(self) -> str:
        if self.environment == "sandbox":
            return "https://api.sandbox.ebay.com"
        return "https://api.ebay.com"

    @property
    def oauth_url(self) -> str:
        return f"{self.api_base_url}/identity/v1/oauth2/token"

    def place_proxy_bid(
        self,
        item_id: str,
        max_bid_amount: float,
        currency: str = "USD",
    ) -> PlaceProxyBidResponse:
        token = self._get_user_access_token()
        response = self._post_proxy_bid(
            token=token,
            item_id=item_id,
            max_bid_amount=max_bid_amount,
            currency=currency,
        )
        if getattr(response, "status_code", None) == 401 and self.refresh_token:
            token = self._refresh_user_access_token()
            response = self._post_proxy_bid(
                token=token,
                item_id=item_id,
                max_bid_amount=max_bid_amount,
                currency=currency,
            )

        self._raise_for_status(response)
        payload = response.json() if getattr(response, "content", b"") else {}
        return PlaceProxyBidResponse(
            proxy_bid_id=payload.get("proxyBidId"),
            raw_payload=payload,
        )

    def _post_proxy_bid(
        self,
        token: str,
        item_id: str,
        max_bid_amount: float,
        currency: str,
    ) -> requests.Response:
        return self.session.post(
            f"{self.api_base_url}/buy/offer/v1_beta/bidding/{quote(item_id, safe='')}/place_proxy_bid",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-EBAY-C-MARKETPLACE-ID": self.marketplace_id,
            },
            json={
                "maxAmount": {
                    "currency": currency,
                    "value": f"{max_bid_amount:.2f}",
                }
            },
            timeout=self.timeout_seconds,
        )

    def _get_user_access_token(self) -> str:
        if self.user_access_token and time() < self._token_expires_at:
            return self.user_access_token

        if self.user_access_token:
            return self.user_access_token

        return self._refresh_user_access_token()

    def _refresh_user_access_token(self) -> str:
        if not self.client_id or not self.client_secret or not self.refresh_token:
            raise EbayOfferApiError(
                "Missing eBay OAuth client credentials or user refresh token for proxy bidding."
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
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
                "scope": self.scope,
            },
            timeout=self.timeout_seconds,
        )
        self._raise_for_status(response)
        payload = response.json() if getattr(response, "content", b"") else {}
        token = payload.get("access_token")
        if not token:
            raise EbayOfferApiError("eBay OAuth refresh response did not include access_token.")
        self.user_access_token = str(token)
        self._token_expires_at = time() + max(int(payload.get("expires_in", 7200)) - 60, 60)
        return self.user_access_token

    def _raise_for_status(self, response: requests.Response) -> None:
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            body = getattr(response, "text", "")
            raise EbayOfferApiError(
                f"eBay Offer API request failed: {exc}",
                status_code=getattr(response, "status_code", None),
                response_body=body,
            ) from exc
