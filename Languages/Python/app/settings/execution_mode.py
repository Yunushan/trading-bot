"""Canonical execution environments for exchange-backed trading."""

from __future__ import annotations

from typing import Literal


LIVE_MODE_VALUES = ("live", "live trading", "production")
TESTNET_MODE_VALUES = ("demo", "demo/testnet", "demo trading", "test", "testnet", "sandbox")
INVALID_EXECUTION_MODE_MESSAGE = "unsupported execution mode (choose Live or Demo/Testnet, Paper is not exchange execution)"


class InvalidExecutionModeError(ValueError):
    """An execution environment cannot be selected safely."""


def execution_environment(mode: object) -> Literal["live", "testnet"]:
    text = mode.strip().lower() if isinstance(mode, str) else ""
    if text in TESTNET_MODE_VALUES:
        return "testnet"
    if text in LIVE_MODE_VALUES:
        return "live"
    raise InvalidExecutionModeError(INVALID_EXECUTION_MODE_MESSAGE)


def is_testnet_trading_mode(mode: object) -> bool:
    """Select transport only after validating the entire mode label."""
    return execution_environment(mode) == "testnet"


def is_live_trading_mode(mode: object) -> bool:
    """Unknown modes require live-level guards, which must then reject them."""
    try:
        return execution_environment(mode) == "live"
    except InvalidExecutionModeError:
        return True
