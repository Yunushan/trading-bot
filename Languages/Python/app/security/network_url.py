from __future__ import annotations

import ipaddress
import math
import urllib.request
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit


def is_loopback_host(hostname: str | None) -> bool:
    host = str(hostname or "").strip().lower().strip("[]")
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


# Kept as a private alias for integrations that imported the helper before it
# became part of the shared URL policy.
_is_loopback_host = is_loopback_host


def url_uses_public_network(value: object) -> bool:
    """Return whether a validated URL targets a public network destination.

    Loopback, RFC1918/private, link-local and ``.local`` names are treated as
    local destinations. Callers should run :func:`validate_http_url` first so
    malformed authorities cannot be classified as safe by accident.
    """

    try:
        hostname = urlsplit(str(value or "").strip()).hostname
    except ValueError:
        return True
    host = str(hostname or "").strip().lower()
    if not host or is_loopback_host(host) or host.endswith(".local"):
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return True
    return not (address.is_loopback or address.is_private or address.is_link_local)


def validate_http_url(
    value: object,
    *,
    field_name: str = "URL",
    allow_loopback_http: bool = False,
    allow_query: bool = True,
) -> str:
    raw_text = str(value or "")
    if any(ord(character) < 32 for character in raw_text):
        raise ValueError(f"{field_name} contains invalid characters")
    text = raw_text.strip()
    if not text:
        raise ValueError(f"{field_name} is required")
    if "\\" in text or any(character.isspace() for character in text):
        raise ValueError(f"{field_name} contains invalid characters")

    parsed = urlsplit(text)
    try:
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"{field_name} must contain a valid host and port") from exc

    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not hostname:
        raise ValueError(f"{field_name} must be an absolute HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{field_name} must not contain credentials")
    if parsed.netloc.endswith(":"):
        raise ValueError(f"{field_name} must contain a valid host and port")
    if port is not None and port < 1:
        raise ValueError(f"{field_name} must contain a valid port")
    if parsed.fragment:
        raise ValueError(f"{field_name} must not contain a fragment")
    if parsed.query and not allow_query:
        raise ValueError(f"{field_name} must not contain a query string")
    if scheme == "http" and not (allow_loopback_http and is_loopback_host(hostname)):
        raise ValueError(f"{field_name} must use HTTPS unless it targets loopback")
    return text


class _ValidatedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, *, allow_loopback_http: bool, allow_redirects: bool) -> None:
        super().__init__()
        self._allow_loopback_http = allow_loopback_http
        self._allow_redirects = allow_redirects

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        if not self._allow_redirects:
            return None
        target = validate_http_url(
            newurl,
            field_name="redirect URL",
            allow_loopback_http=self._allow_loopback_http,
        )
        return super().redirect_request(req, fp, code, msg, headers, target)


def open_validated_url(
    url: object,
    *,
    timeout: float,
    headers: Mapping[str, str] | None = None,
    data: bytes | None = None,
    method: str | None = None,
    allow_loopback_http: bool = False,
    allow_redirects: bool = True,
) -> Any:
    safe_url = validate_http_url(url, allow_loopback_http=allow_loopback_http)
    timeout_value = float(timeout)
    if not math.isfinite(timeout_value) or timeout_value <= 0:
        raise ValueError("URL timeout must be a positive finite number")

    request = urllib.request.Request(  # noqa: S310 - URL and every redirect are validated above.
        safe_url,
        data=data,
        headers=dict(headers or {}),
        method=method,
    )
    redirect_handler = _ValidatedRedirectHandler(
        allow_loopback_http=allow_loopback_http,
        allow_redirects=allow_redirects,
    )
    opener = urllib.request.build_opener(redirect_handler)
    return opener.open(request, timeout=timeout_value)


__all__ = ["is_loopback_host", "open_validated_url", "url_uses_public_network", "validate_http_url"]
