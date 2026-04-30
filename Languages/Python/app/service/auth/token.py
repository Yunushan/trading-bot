"""
Bearer-token auth helpers for the service API.
"""

from __future__ import annotations

import hmac
import ipaddress
import os


def resolve_service_api_token(explicit_token: str | None = None) -> str:
    token = explicit_token
    if token in (None, ""):
        token = os.environ.get("BOT_SERVICE_API_TOKEN", "")
    return str(token or "").strip()


def auth_required(token: str | None = None) -> bool:
    return bool(resolve_service_api_token(token))


def host_requires_service_api_token(host: str | None) -> bool:
    text = str(host or "").strip().lower()
    if not text:
        return False
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    if text in {"localhost", "127.0.0.1", "::1"}:
        return False
    try:
        return not ipaddress.ip_address(text).is_loopback
    except ValueError:
        return True


def validate_service_api_exposure(host: str | None, token: str | None = None) -> None:
    if host_requires_service_api_token(host) and not auth_required(token):
        raise RuntimeError(
            "BOT_SERVICE_API_TOKEN or --api-token is required when the service API "
            "binds to a non-loopback host."
        )


def validate_bearer_token(authorization: str | None, expected_token: str | None = None) -> bool:
    token = resolve_service_api_token(expected_token)
    if not token:
        return True
    header = str(authorization or "").strip()
    if not header:
        return False
    scheme, _, supplied = header.partition(" ")
    if scheme.lower() != "bearer":
        return False
    supplied = supplied.strip()
    if not supplied:
        return False
    return hmac.compare_digest(supplied, token)
