"""Identify the exchange account to which cached observations belong."""

from collections.abc import Mapping


def observation_scope(config: Mapping[str, object]) -> tuple[object, ...]:
    # Kept in memory only: never serialize or log credential-bearing identities.
    return tuple(config.get(key) for key in (
        "mode", "account_type", "selected_exchange", "selected_forex_broker",
        "connector_backend", "api_key", "api_secret", "api_key_env", "api_secret_env",
    ))
