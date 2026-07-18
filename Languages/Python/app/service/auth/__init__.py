"""
Authentication helpers for the service API.
"""

from .token import (
    MIN_NON_LOOPBACK_SERVICE_API_TOKEN_LENGTH,
    SERVICE_API_ALLOW_UNAUTHENTICATED_WRITES_ENV,
    SERVICE_API_TOKEN_FILE_ENV,
    SERVICE_API_TLS_CERTFILE_ENV,
    SERVICE_API_TLS_KEYFILE_ENV,
    SERVICE_API_TRUST_LOOPBACK_PROXY_ENV,
    SERVICE_API_TRUST_PROXY_TLS_ENV,
    auth_required,
    host_requires_service_api_token,
    resolve_service_api_token,
    service_api_url_scheme,
    service_api_tls_settings,
    validate_bearer_token,
    validate_service_api_exposure,
)

__all__ = [
    "MIN_NON_LOOPBACK_SERVICE_API_TOKEN_LENGTH",
    "SERVICE_API_ALLOW_UNAUTHENTICATED_WRITES_ENV",
    "SERVICE_API_TOKEN_FILE_ENV",
    "SERVICE_API_TLS_CERTFILE_ENV",
    "SERVICE_API_TLS_KEYFILE_ENV",
    "SERVICE_API_TRUST_LOOPBACK_PROXY_ENV",
    "SERVICE_API_TRUST_PROXY_TLS_ENV",
    "auth_required",
    "host_requires_service_api_token",
    "resolve_service_api_token",
    "service_api_url_scheme",
    "service_api_tls_settings",
    "validate_bearer_token",
    "validate_service_api_exposure",
]
