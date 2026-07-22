"""
Bearer-token auth helpers for the service API.
"""

from __future__ import annotations

import hmac
import ipaddress
import os
import stat
from pathlib import Path


MIN_NON_LOOPBACK_SERVICE_API_TOKEN_LENGTH = 32
SERVICE_API_ALLOW_UNAUTHENTICATED_WRITES_ENV = "BOT_SERVICE_API_ALLOW_UNAUTHENTICATED_WRITES"
SERVICE_API_TOKEN_FILE_ENV = "BOT_SERVICE_API_TOKEN_FILE"
SERVICE_API_TLS_CERTFILE_ENV = "BOT_SERVICE_API_TLS_CERTFILE"
SERVICE_API_TLS_KEYFILE_ENV = "BOT_SERVICE_API_TLS_KEYFILE"
SERVICE_API_TRUST_PROXY_TLS_ENV = "BOT_SERVICE_API_TRUST_PROXY_TLS"
SERVICE_API_TRUST_LOOPBACK_PROXY_ENV = "BOT_SERVICE_API_TRUST_LOOPBACK_PROXY"
MAX_SERVICE_API_TOKEN_FILE_BYTES = 4096


def _service_api_token_from_file() -> str:
    configured_path = str(os.environ.get(SERVICE_API_TOKEN_FILE_ENV) or "").strip()
    if not configured_path:
        return ""
    path = Path(configured_path).expanduser()
    try:
        with path.open("r", encoding="utf-8") as handle:
            file_stat = os.fstat(handle.fileno())
            if not stat.S_ISREG(file_stat.st_mode):
                raise RuntimeError(f"{SERVICE_API_TOKEN_FILE_ENV} does not point to a readable regular file.")
            if file_stat.st_size > MAX_SERVICE_API_TOKEN_FILE_BYTES:
                raise RuntimeError(
                    f"{SERVICE_API_TOKEN_FILE_ENV} exceeds the {MAX_SERVICE_API_TOKEN_FILE_BYTES}-byte safety limit."
                )
            if os.name != "nt" and file_stat.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
                raise RuntimeError(
                    f"{SERVICE_API_TOKEN_FILE_ENV} must not grant group or other permissions on POSIX hosts."
                )
            return handle.read().strip()
    except FileNotFoundError as exc:
        raise RuntimeError(f"{SERVICE_API_TOKEN_FILE_ENV} does not point to a readable file.") from exc
    except OSError as exc:
        raise RuntimeError(f"Unable to read {SERVICE_API_TOKEN_FILE_ENV}.") from exc


def resolve_service_api_token(explicit_token: str | None = None) -> str:
    token = explicit_token
    if token in (None, ""):
        token = os.environ.get("BOT_SERVICE_API_TOKEN", "")
    if token in (None, ""):
        token = _service_api_token_from_file()
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


def service_api_tls_settings() -> tuple[str, str, bool, bool]:
    """Return certificate paths and explicit trusted-proxy deployment modes."""
    certfile = str(os.environ.get(SERVICE_API_TLS_CERTFILE_ENV) or "").strip()
    keyfile = str(os.environ.get(SERVICE_API_TLS_KEYFILE_ENV) or "").strip()
    trusted_proxy_tls = str(os.environ.get(SERVICE_API_TRUST_PROXY_TLS_ENV) or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    trusted_loopback_proxy = str(os.environ.get(SERVICE_API_TRUST_LOOPBACK_PROXY_ENV) or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    return certfile, keyfile, trusted_proxy_tls, trusted_loopback_proxy


def service_api_url_scheme() -> str:
    """Return the scheme exposed by a directly TLS-enabled Service API listener."""
    certfile, keyfile, _, _ = service_api_tls_settings()
    return "https" if certfile and keyfile else "http"


def _validate_service_api_tls_files() -> tuple[str, str, bool, bool]:
    certfile, keyfile, trusted_proxy_tls, trusted_loopback_proxy = service_api_tls_settings()
    if not certfile and not keyfile:
        return certfile, keyfile, trusted_proxy_tls, trusted_loopback_proxy
    if not certfile or not keyfile:
        raise RuntimeError(
            f"Configure both {SERVICE_API_TLS_CERTFILE_ENV} and {SERVICE_API_TLS_KEYFILE_ENV}, "
            "or remove both settings."
        )
    if not Path(certfile).is_file():
        raise RuntimeError("The configured non-loopback service API TLS certificate or key file does not exist.")
    try:
        with Path(keyfile).open("rb") as handle:
            file_stat = os.fstat(handle.fileno())
    except FileNotFoundError as exc:
        raise RuntimeError("The configured non-loopback service API TLS certificate or key file does not exist.") from exc
    except OSError as exc:
        raise RuntimeError("Unable to read the configured service API TLS private-key file.") from exc
    if not stat.S_ISREG(file_stat.st_mode):
        raise RuntimeError("The configured service API TLS private-key path is not a regular file.")
    if os.name != "nt" and file_stat.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise RuntimeError("The configured service API TLS private-key file must not grant group or other permissions.")
    return certfile, keyfile, trusted_proxy_tls, trusted_loopback_proxy


def validate_service_api_exposure(host: str | None, token: str | None = None) -> None:
    certfile, keyfile, trusted_proxy_tls, trusted_loopback_proxy = _validate_service_api_tls_files()
    if not host_requires_service_api_token(host):
        return
    resolved_token = resolve_service_api_token(token)
    if not resolved_token:
        raise RuntimeError(
            "BOT_SERVICE_API_TOKEN or --api-token is required when the service API "
            "binds to a non-loopback host."
        )
    if len(resolved_token) < MIN_NON_LOOPBACK_SERVICE_API_TOKEN_LENGTH:
        raise RuntimeError(
            "BOT_SERVICE_API_TOKEN or --api-token must contain at least "
            f"{MIN_NON_LOOPBACK_SERVICE_API_TOKEN_LENGTH} characters when the service API "
            "binds to a non-loopback host."
        )
    unsafe_writes = str(os.environ.get(SERVICE_API_ALLOW_UNAUTHENTICATED_WRITES_ENV) or "").strip().lower()
    if unsafe_writes in {"1", "true", "yes", "on"}:
        raise RuntimeError(
            f"{SERVICE_API_ALLOW_UNAUTHENTICATED_WRITES_ENV} is only allowed when the service API "
            "binds to a loopback host."
        )
    if certfile and keyfile:
        return
    if trusted_proxy_tls or trusted_loopback_proxy:
        return
    raise RuntimeError(
        "A non-loopback service API requires TLS. Configure both "
        f"{SERVICE_API_TLS_CERTFILE_ENV} and {SERVICE_API_TLS_KEYFILE_ENV}, or set "
        f"{SERVICE_API_TRUST_PROXY_TLS_ENV}=1 only behind a trusted TLS-terminating reverse proxy. "
        f"{SERVICE_API_TRUST_LOOPBACK_PROXY_ENV}=1 is reserved for a container port that is "
        "published only on host loopback."
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
