from __future__ import annotations

from ...core.backtest.intervals import normalize_backtest_interval, normalize_backtest_intervals

_BACKTEST_INTERVAL_ORDER: tuple[str, ...] = ()
_SIDE_LABELS: dict[str, str] = {}
_SYMBOL_FETCH_TOP_N = 200


def configure_backtest_state_runtime(
    *,
    backtest_interval_order,
    side_labels: dict[str, str],
    symbol_fetch_top_n: int,
) -> None:
    global _BACKTEST_INTERVAL_ORDER
    global _SIDE_LABELS
    global _SYMBOL_FETCH_TOP_N

    _BACKTEST_INTERVAL_ORDER = tuple(normalize_backtest_intervals(backtest_interval_order))
    _SIDE_LABELS = dict(side_labels or {})
    _SYMBOL_FETCH_TOP_N = max(1, int(symbol_fetch_top_n))


def get_backtest_interval_order() -> tuple[str, ...]:
    return tuple(_BACKTEST_INTERVAL_ORDER)


def normalize_backtest_interval_value(value) -> str:
    return normalize_backtest_interval(value)


def normalize_backtest_interval_values(values) -> list[str]:
    return normalize_backtest_intervals(values)


def get_side_labels() -> dict[str, str]:
    return dict(_SIDE_LABELS)


def get_symbol_fetch_top_n() -> int:
    return int(_SYMBOL_FETCH_TOP_N)
