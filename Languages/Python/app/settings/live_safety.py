from __future__ import annotations

import os
from collections.abc import Mapping

from .risk import coerce_bool

LIVE_TRADING_ACKNOWLEDGEMENT = "I_UNDERSTAND_LIVE_TRADING_RISK"
LIVE_TRADING_ENABLED_ENV = "BOT_ENABLE_LIVE_TRADING"
LIVE_TRADING_ACK_ENV = "BOT_LIVE_TRADING_ACKNOWLEDGEMENT"
LIVE_TRADING_ACK_ENV_LEGACY = "BOT_LIVE_TRADING_ACK"
LIVE_TRADING_MAX_LEVERAGE_ENV = "BOT_LIVE_MAX_LEVERAGE"
LIVE_TRADING_MAX_POSITION_PCT_ENV = "BOT_LIVE_MAX_POSITION_PCT"
DEFAULT_LIVE_MAX_LEVERAGE = 20
DEFAULT_LIVE_MAX_POSITION_PCT = 10.0
BINANCE_MAX_FUTURES_LEVERAGE = 150

_NON_LIVE_MODE_TOKENS = ("demo", "test", "sandbox", "paper")
_PLACEHOLDER_CREDENTIALS = {
    "api_key",
    "api-secret",
    "api_secret",
    "binance_api_key",
    "binance_api_secret",
    "changeme",
    "demo",
    "example",
    "sandbox",
    "secret",
    "test",
    "testnet",
    "your-api-key",
    "your-api-secret",
    "your_api_key",
    "your_api_secret",
}


class LiveTradingSafetyError(RuntimeError):
    """Raised when a live exchange runtime is requested without safety confirmation."""


def is_live_trading_mode(mode: object) -> bool:
    text = str(mode or "").strip().lower()
    if not text:
        return False
    return not any(token in text for token in _NON_LIVE_MODE_TOKENS)


def _mapping(config: Mapping[str, object] | None) -> Mapping[str, object]:
    return config if isinstance(config, Mapping) else {}


def _env_value(env: Mapping[str, str] | None, key: str) -> str:
    source = env if env is not None else os.environ
    try:
        return str(source.get(key, "") or "").strip()
    except Exception:
        return ""


def _float_value(value: object, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _int_value(value: object, default: int) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _live_confirmation_present(config: Mapping[str, object], env: Mapping[str, str] | None) -> bool:
    config_enabled = coerce_bool(config.get("live_trading_enabled"), False)
    config_ack = str(config.get("live_trading_acknowledgement") or "").strip()
    if config_enabled and config_ack == LIVE_TRADING_ACKNOWLEDGEMENT:
        return True

    env_enabled = coerce_bool(_env_value(env, LIVE_TRADING_ENABLED_ENV), False)
    env_ack = _env_value(env, LIVE_TRADING_ACK_ENV) or _env_value(env, LIVE_TRADING_ACK_ENV_LEGACY)
    return bool(env_enabled and env_ack == LIVE_TRADING_ACKNOWLEDGEMENT)


def _credential_is_real(value: object) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    return text.lower() not in _PLACEHOLDER_CREDENTIALS


def _configured_cap(
    config: Mapping[str, object],
    env: Mapping[str, str] | None,
    *,
    config_key: str,
    env_key: str,
    default: float,
) -> float:
    env_raw = _env_value(env, env_key)
    if env_raw:
        return _float_value(env_raw, default)
    return _float_value(config.get(config_key, default), default)


def validate_live_trading_safety(
    *,
    mode: object,
    api_key: object,
    api_secret: object,
    account_type: object = "Futures",
    leverage: object | None = None,
    margin_mode: object | None = None,
    position_pct: object | None = None,
    config: Mapping[str, object] | None = None,
    env: Mapping[str, str] | None = None,
) -> None:
    """Fail closed before a runtime can talk to live exchange endpoints."""
    if not is_live_trading_mode(mode):
        return

    cfg = _mapping(config)
    errors: list[str] = []

    if not _live_confirmation_present(cfg, env):
        errors.append(
            "set live_trading_enabled=true and "
            f"live_trading_acknowledgement={LIVE_TRADING_ACKNOWLEDGEMENT!r} "
            f"or set {LIVE_TRADING_ENABLED_ENV}=true and {LIVE_TRADING_ACK_ENV}={LIVE_TRADING_ACKNOWLEDGEMENT!r}"
        )

    if not _credential_is_real(api_key) or not _credential_is_real(api_secret):
        errors.append("provide non-placeholder Binance API credentials")

    max_leverage = _int_value(
        _configured_cap(
            cfg,
            env,
            config_key="live_trading_max_leverage",
            env_key=LIVE_TRADING_MAX_LEVERAGE_ENV,
            default=DEFAULT_LIVE_MAX_LEVERAGE,
        ),
        DEFAULT_LIVE_MAX_LEVERAGE,
    )
    if max_leverage < 1 or max_leverage > BINANCE_MAX_FUTURES_LEVERAGE:
        errors.append(f"live_trading_max_leverage must be between 1 and {BINANCE_MAX_FUTURES_LEVERAGE}")

    max_position_pct = _configured_cap(
        cfg,
        env,
        config_key="live_trading_max_position_pct",
        env_key=LIVE_TRADING_MAX_POSITION_PCT_ENV,
        default=DEFAULT_LIVE_MAX_POSITION_PCT,
    )
    if max_position_pct <= 0.0 or max_position_pct > 100.0:
        errors.append("live_trading_max_position_pct must be > 0 and <= 100")

    pct_value = position_pct
    if pct_value is None:
        pct_value = cfg.get("position_pct", 2.0)
    pct = _float_value(pct_value, 0.0)
    if pct <= 0.0 or pct > 100.0:
        errors.append("position_pct must be > 0 and <= 100 for live trading")
    elif pct > max_position_pct:
        errors.append(f"position_pct {pct:g}% exceeds live cap {max_position_pct:g}%")

    account = str(account_type or "").strip().upper()
    if account.startswith("FUT"):
        lev_value = leverage
        if lev_value is None:
            lev_value = cfg.get("leverage", 1)
        requested_leverage = _int_value(lev_value, 0)
        if requested_leverage < 1:
            errors.append("leverage must be >= 1 for live futures trading")
        elif requested_leverage > max_leverage:
            errors.append(f"leverage {requested_leverage} exceeds live cap {max_leverage}")

        margin = str(margin_mode if margin_mode is not None else cfg.get("margin_mode", "")).strip().upper()
        if margin and margin not in {"ISOLATED", "CROSS"}:
            errors.append("margin_mode must be Isolated or Cross for live futures trading")

    if errors:
        joined = "; ".join(errors)
        raise LiveTradingSafetyError(f"Live trading safety check failed for mode {mode!r}: {joined}.")
