"""
Optional bearer-token auth for the service API.
"""

from __future__ import annotations

import hmac
import os


def resolve_service_api_token(explicit_token: str | None = None) -> str:
    token = explicit_token
    if token in (None, ""):
        token = os.environ.get("BOT_SERVICE_API_TOKEN", "")
    return str(token or "").strip()


def auth_required(token: str | None = None) -> bool:
    return bool(resolve_service_api_token(token))


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
