from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Dict, List, Optional

from ...config import MDD_LOGIC_DEFAULT


EXECUTION_MODEL_SAME_CLOSE_LEGACY = "same_close_legacy"
EXECUTION_MODEL_NEXT_BAR_OPEN = "next_bar_open"
BACKTEST_EXECUTION_MODELS = (
    EXECUTION_MODEL_SAME_CLOSE_LEGACY,
    EXECUTION_MODEL_NEXT_BAR_OPEN,
)


def validate_execution_model(value: object) -> str:
    model = str(value).strip()
    if model not in BACKTEST_EXECUTION_MODELS:
        raise ValueError(
            f"Invalid backtest execution_model {model!r}; expected one of "
            + ", ".join(BACKTEST_EXECUTION_MODELS)
        )
    return model


def validate_execution_cost_bps(value: object, *, field: str) -> float:
    try:
        bps = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"Invalid backtest {field}: expected finite nonnegative basis points") from exc
    if not isfinite(bps) or bps < 0.0:
        raise ValueError(f"Invalid backtest {field}: expected finite nonnegative basis points")
    if field == "slippage_bps" and bps >= 10_000.0:
        # At 100% adverse slippage, one side of a fill has a zero/negative price.
        raise ValueError("Invalid backtest slippage_bps: must be below 10000 basis points")
    return bps


@dataclass
class IndicatorDefinition:
    key: str
    params: Dict[str, object]


@dataclass
class PairOverride:
    symbol: str
    interval: str
    indicators: Optional[List[str]] = None
    leverage: Optional[int] = None
    strategy_controls: Optional[Dict[str, object]] = None
    logic: Optional[str] = None
    capital: Optional[float] = None
    side: Optional[str] = None
    position_pct: Optional[float] = None
    position_pct_units: Optional[str] = None
    margin_mode: Optional[str] = None
    position_mode: Optional[str] = None
    assets_mode: Optional[str] = None
    account_mode: Optional[str] = None
    mdd_logic: Optional[str] = None
    stop_loss_enabled: Optional[bool] = None
    stop_loss_mode: Optional[str] = None
    stop_loss_usdt: Optional[float] = None
    stop_loss_percent: Optional[float] = None
    stop_loss_scope: Optional[str] = None


@dataclass
class BacktestRequest:
    symbols: List[str]
    intervals: List[str]
    indicators: List[IndicatorDefinition]
    logic: str
    symbol_source: str
    start: datetime
    end: datetime
    capital: float
    side: str = "BOTH"
    position_pct: float = 1.0
    position_pct_units: str = ""
    leverage: float = 1.0
    margin_mode: str = "Isolated"
    position_mode: str = "Hedge"
    assets_mode: str = "Single-Asset"
    account_mode: str = "Classic Trading"
    mdd_logic: str = MDD_LOGIC_DEFAULT
    stop_loss_enabled: bool = False
    stop_loss_mode: str = "usdt"
    stop_loss_usdt: float = 0.0
    stop_loss_percent: float = 0.0
    stop_loss_scope: str = "per_trade"
    fee_bps: float = 5.0
    slippage_bps: float = 2.0
    execution_model: str = EXECUTION_MODEL_SAME_CLOSE_LEGACY
    pair_overrides: Optional[Iterable[PairOverride]] = None
    optimizer_max_duration_seconds: int = 0


@dataclass
class BacktestRunResult:
    symbol: str
    interval: str
    indicator_keys: List[str]
    trades: int
    roi_value: float
    roi_percent: float
    final_equity: float
    max_drawdown_value: float
    max_drawdown_percent: float
    logic: str
    leverage: float
    max_drawdown_during_value: float = 0.0
    max_drawdown_during_percent: float = 0.0
    max_drawdown_result_value: float = 0.0
    max_drawdown_result_percent: float = 0.0
    mdd_logic: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    side: str | None = None
    capital: float | None = None
    position_pct: float | None = None
    position_pct_units: str | None = None
    stop_loss_enabled: bool | None = None
    stop_loss_mode: str | None = None
    stop_loss_usdt: float | None = None
    stop_loss_percent: float | None = None
    stop_loss_scope: str | None = None
    margin_mode: str | None = None
    position_mode: str | None = None
    assets_mode: str | None = None
    account_mode: str | None = None
    fee_bps: float | None = None
    slippage_bps: float | None = None
    fees_paid: float | None = None
    execution_model: str = EXECUTION_MODEL_SAME_CLOSE_LEGACY
    terminal_valuation: str = ""
    terminal_position_open: bool = False
    terminal_unrealized_pnl: float = 0.0
    strategy_controls: Dict[str, object] | None = None
    optimizer_rank: int | None = None
    optimizer_metric: str | None = None
    optimizer_primary_score: float | None = None
    optimizer_eligible: bool | None = None
    optimizer_mode: str | None = None
    optimizer_scope: str | None = None
    optimizer_mdd_limit: float | None = None
    optimizer_min_trades: int | None = None
    optimizer_candidate_count: int | None = None
    optimizer_eligible_count: int | None = None
    optimizer_filtered_count: int | None = None
    optimizer_run_count: int | None = None
    optimizer_rejection_reason: str | None = None
