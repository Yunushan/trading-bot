from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit


def _is_loopback_host(hostname: str | None) -> bool:
    host = str(hostname or "").strip().lower().strip("[]")
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def clean_http_base_url(
    value: object,
    *,
    default: str,
    field_name: str,
    allow_insecure_remote: bool = False,
) -> str:
    text = str(value or "").strip().rstrip("/") or default
    if any(character in text for character in ("\r", "\n", "\x00")):
        raise ValueError(f"{field_name} contains invalid control characters")

    parsed = urlsplit(text)
    scheme = parsed.scheme.lower()
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"{field_name} must contain a valid port") from exc
    if scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"{field_name} must be an absolute HTTP(S) URL")
    if port is not None and port < 1:
        raise ValueError(f"{field_name} must contain a valid port")
    if parsed.username or parsed.password:
        raise ValueError(f"{field_name} must not contain credentials")
    if parsed.query or parsed.fragment:
        raise ValueError(f"{field_name} must not contain a query string or fragment")
    if scheme == "http" and not _is_loopback_host(parsed.hostname) and not allow_insecure_remote:
        raise ValueError(f"remote {field_name} URLs must use HTTPS")
    return text


__all__ = ["clean_http_base_url"]
