from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - depends on local environment
    def load_dotenv() -> bool:
        return False


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.clients.ebay_oauth import (
    EbayOAuthClient,
    EbayOAuthConfig,
    extract_authorization_code,
    parse_scope_list,
    redact_secret,
)


ENV_PATH = ROOT / ".env"


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


def _build_client(scope_override: str | None = None) -> EbayOAuthClient:
    client_id = _env("EBAY_CLIENT_ID") or _env("EBAY_APP_ID")
    client_secret = _env("EBAY_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise SystemExit("EBAY_CLIENT_ID and EBAY_CLIENT_SECRET are required.")

    scopes = parse_scope_list(scope_override or _env("EBAY_OAUTH_SCOPES"))
    config = EbayOAuthConfig(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=_env("EBAY_RU_NAME"),
        environment=_env("EBAY_ENVIRONMENT", "production") or "production",
        scopes=scopes,
    )
    return EbayOAuthClient(config)


def _merge_env_values(updates: dict[str, str]) -> None:
    existing_lines: list[str] = []
    if ENV_PATH.exists():
        existing_lines = ENV_PATH.read_text(encoding="utf-8").splitlines()

    pending = dict(updates)
    output_lines: list[str] = []
    for line in existing_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            output_lines.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in pending:
            output_lines.append(f"{key}={pending.pop(key)}")
        else:
            output_lines.append(line)

    if pending and output_lines and output_lines[-1].strip():
        output_lines.append("")
    for key, value in pending.items():
        output_lines.append(f"{key}={value}")

    ENV_PATH.write_text("\n".join(output_lines) + "\n", encoding="utf-8")


def _token_env_updates(payload: dict[str, Any], token_prefix: str) -> dict[str, str]:
    updates: dict[str, str] = {}
    access_token = payload.get("access_token")
    refresh_token = payload.get("refresh_token")
    expires_at = payload.get("expires_at")

    if isinstance(access_token, str):
        updates[f"{token_prefix}_ACCESS_TOKEN"] = access_token
    if isinstance(refresh_token, str):
        updates[f"{token_prefix}_REFRESH_TOKEN"] = refresh_token
    if isinstance(expires_at, int):
        updates[f"{token_prefix}_ACCESS_TOKEN_EXPIRES_AT"] = str(expires_at)
    return updates


def _redacted_payload(payload: dict[str, Any]) -> dict[str, Any]:
    redacted = dict(payload)
    for key in ("access_token", "refresh_token"):
        if key in redacted:
            redacted[key] = redact_secret(redacted[key])
    return redacted


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="eBay OAuth helper for psa-pokemon-bidder.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    auth_url = subparsers.add_parser("auth-url", help="Print a user-consent URL.")
    auth_url.add_argument("--scopes", help="Space- or comma-separated OAuth scopes.")
    auth_url.add_argument("--state", help="Optional CSRF state value.")

    app_token = subparsers.add_parser("app-token", help="Mint an application access token.")
    app_token.add_argument("--scopes", help="Space- or comma-separated OAuth scopes.")
    app_token.add_argument("--write-env", action="store_true", help="Write EBAY_ACCESS_TOKEN to .env.")

    exchange = subparsers.add_parser("exchange-code", help="Exchange an authorization code for user tokens.")
    exchange.add_argument("--code", required=True, help="Authorization code from eBay redirect.")
    exchange.add_argument("--write-env", action="store_true", help="Write EBAY_USER_* tokens to .env.")

    extract = subparsers.add_parser("extract-code", help="Extract code/state from a full eBay redirect URL.")
    extract.add_argument("--redirect-url", required=True, help="Full URL eBay redirected to after consent.")

    exchange_redirect = subparsers.add_parser(
        "exchange-redirect",
        help="Extract an authorization code from a redirect URL and exchange it for user tokens.",
    )
    exchange_redirect.add_argument(
        "--redirect-url",
        required=True,
        help="Full URL eBay redirected to after consent.",
    )
    exchange_redirect.add_argument("--write-env", action="store_true", help="Write EBAY_USER_* tokens to .env.")

    refresh = subparsers.add_parser("refresh-user-token", help="Refresh the user access token.")
    refresh.add_argument("--refresh-token", help="Override EBAY_USER_REFRESH_TOKEN.")
    refresh.add_argument("--write-env", action="store_true", help="Write EBAY_USER_ACCESS_TOKEN to .env.")

    args = parser.parse_args()

    if args.command == "auth-url":
        client = _build_client(args.scopes)
        url, state = client.build_authorization_url(state=args.state)
        print(json.dumps({"authorization_url": url, "state": state}, indent=2))
        return

    if args.command == "app-token":
        client = _build_client(args.scopes)
        payload = client.mint_application_token()
        if args.write_env:
            updates = _token_env_updates(payload, "EBAY")
            _merge_env_values({key: value for key, value in updates.items() if key == "EBAY_ACCESS_TOKEN"})
        print(json.dumps(_redacted_payload(payload), indent=2, sort_keys=True))
        return

    if args.command == "exchange-code":
        client = _build_client(None)
        payload = client.exchange_authorization_code(args.code)
        if args.write_env:
            _merge_env_values(_token_env_updates(payload, "EBAY_USER"))
        print(json.dumps(_redacted_payload(payload), indent=2, sort_keys=True))
        return

    if args.command == "extract-code":
        print(json.dumps(extract_authorization_code(args.redirect_url), indent=2, sort_keys=True))
        return

    if args.command == "exchange-redirect":
        code_payload = extract_authorization_code(args.redirect_url)
        client = _build_client(None)
        payload = client.exchange_authorization_code(code_payload["code"])
        if args.write_env:
            _merge_env_values(_token_env_updates(payload, "EBAY_USER"))
        print(
            json.dumps(
                {
                    "oauth_redirect": code_payload,
                    "token_response": _redacted_payload(payload),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    if args.command == "refresh-user-token":
        refresh_token = args.refresh_token or _env("EBAY_USER_REFRESH_TOKEN")
        if not refresh_token:
            raise SystemExit("EBAY_USER_REFRESH_TOKEN is required.")
        client = _build_client(None)
        payload = client.refresh_user_access_token(refresh_token)
        if args.write_env:
            updates = _token_env_updates(payload, "EBAY_USER")
            _merge_env_values(
                {key: value for key, value in updates.items() if key != "EBAY_USER_REFRESH_TOKEN"}
            )
        print(json.dumps(_redacted_payload(payload), indent=2, sort_keys=True))
        return


if __name__ == "__main__":
    main()
