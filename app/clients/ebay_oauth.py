from __future__ import annotations

import base64
import secrets
from dataclasses import dataclass
from time import time
from typing import Any
from urllib.parse import parse_qs, unquote, urlencode, urlparse

import requests


DEFAULT_PUBLIC_SCOPE = "https://api.ebay.com/oauth/api_scope"
BUY_OFFER_AUCTION_SCOPE = "https://api.ebay.com/oauth/api_scope/buy.offer.auction"


class EbayOAuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class EbayOAuthConfig:
    client_id: str
    client_secret: str
    redirect_uri: str | None = None
    environment: str = "production"
    scopes: tuple[str, ...] = (DEFAULT_PUBLIC_SCOPE,)

    @property
    def api_base_url(self) -> str:
        if self.environment.strip().lower() == "sandbox":
            return "https://api.sandbox.ebay.com"
        return "https://api.ebay.com"

    @property
    def auth_base_url(self) -> str:
        if self.environment.strip().lower() == "sandbox":
            return "https://auth.sandbox.ebay.com"
        return "https://auth.ebay.com"

    @property
    def oauth_url(self) -> str:
        return f"{self.api_base_url}/identity/v1/oauth2/token"


class EbayOAuthClient:
    def __init__(
        self,
        config: EbayOAuthConfig,
        session: requests.Session | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.config = config
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds

    def build_authorization_url(
        self,
        state: str | None = None,
        prompt_login: bool = True,
    ) -> tuple[str, str]:
        if not self.config.redirect_uri:
            raise EbayOAuthError("EBAY_RU_NAME is required to build an eBay user consent URL.")

        resolved_state = state or secrets.token_urlsafe(24)
        params = {
            "client_id": self.config.client_id,
            "redirect_uri": self.config.redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.config.scopes),
            "state": resolved_state,
        }
        if prompt_login:
            params["prompt"] = "login"
        return f"{self.config.auth_base_url}/oauth2/authorize?{urlencode(params)}", resolved_state

    def mint_application_token(self) -> dict[str, Any]:
        response = self.session.post(
            self.config.oauth_url,
            headers=self._token_headers(),
            data={
                "grant_type": "client_credentials",
                "scope": " ".join(self.config.scopes),
            },
            timeout=self.timeout_seconds,
        )
        self._raise_for_status(response)
        return self._token_payload(response)

    def exchange_authorization_code(self, code: str) -> dict[str, Any]:
        if not self.config.redirect_uri:
            raise EbayOAuthError("EBAY_RU_NAME is required to exchange an authorization code.")

        response = self.session.post(
            self.config.oauth_url,
            headers=self._token_headers(),
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.config.redirect_uri,
            },
            timeout=self.timeout_seconds,
        )
        self._raise_for_status(response)
        return self._token_payload(response)

    def refresh_user_access_token(self, refresh_token: str) -> dict[str, Any]:
        response = self.session.post(
            self.config.oauth_url,
            headers=self._token_headers(),
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "scope": " ".join(self.config.scopes),
            },
            timeout=self.timeout_seconds,
        )
        self._raise_for_status(response)
        return self._token_payload(response)

    def _token_headers(self) -> dict[str, str]:
        credentials = f"{self.config.client_id}:{self.config.client_secret}".encode("utf-8")
        encoded_credentials = base64.b64encode(credentials).decode("ascii")
        return {
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

    def _token_payload(self, response: requests.Response) -> dict[str, Any]:
        payload = response.json()
        expires_in = payload.get("expires_in")
        if isinstance(expires_in, int):
            payload["expires_at"] = int(time()) + max(expires_in - 60, 60)
        return payload

    def _raise_for_status(self, response: requests.Response) -> None:
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            body = getattr(response, "text", "")
            raise EbayOAuthError(f"eBay OAuth request failed: {exc} {body}") from exc


def parse_scope_list(raw_scopes: str | None) -> tuple[str, ...]:
    if not raw_scopes:
        return (DEFAULT_PUBLIC_SCOPE,)
    scopes = tuple(scope.strip() for scope in raw_scopes.replace(",", " ").split() if scope.strip())
    return scopes or (DEFAULT_PUBLIC_SCOPE,)


def extract_authorization_code(redirect_url: str) -> dict[str, str]:
    parsed = urlparse(redirect_url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    code_values = query.get("code")
    if not code_values or not code_values[0]:
        raise EbayOAuthError("Redirect URL does not contain a code query parameter.")

    result = {"code": unquote(code_values[0])}
    for key in ("state", "expires_in"):
        values = query.get(key)
        if values and values[0]:
            result[key] = values[0]
    return result


def redact_secret(value: object) -> str:
    if not isinstance(value, str) or not value:
        return ""
    if len(value) <= 10:
        return "***"
    return f"{value[:6]}...{value[-4:]}"
