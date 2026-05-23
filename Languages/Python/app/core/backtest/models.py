from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from ...config import MDD_LOGIC_DEFAULT


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
    pair_overrides: Optional[List[PairOverride]] = None


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
    strategy_controls: Dict[str, object] | None = None
    optimizer_rank: int | None = None
    optimizer_metric: str | None = None
    optimizer_primary_score: float | None = None
    optimizer_eligible: bool | None = None
    optimizer_rejection_reason: str | None = None
