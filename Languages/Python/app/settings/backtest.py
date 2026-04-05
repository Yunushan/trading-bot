from __future__ import annotations

import copy
from dataclasses import dataclass, field

from .connectors import DEFAULT_CONNECTOR_BACKEND
from .indicators import build_backtest_indicator_defaults
from .risk import StopLossSettings


MDD_LOGIC_OPTIONS = ["per_trade", "cumulative", "entire_account"]
MDD_LOGIC_DEFAULT = MDD_LOGIC_OPTIONS[0]


@dataclass(frozen=True, slots=True)
class BacktestTemplateSettings:
    enabled: bool = False
    name: str | None = None

    def to_config_dict(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "name": self.name,
        }


BACKTEST_TEMPLATE_DEFAULT = BacktestTemplateSettings().to_config_dict()


@dataclass(frozen=True, slots=True)
class BacktestSettings:
    symbols: tuple[str, ...] = ("BTCUSDT",)
    intervals: tuple[str, ...] = ("1h",)
    capital: float = 1000.0
    logic: str = "AND"
    symbol_source: str = "Futures"
    start_date: str | None = None
    end_date: str | None = None
    position_pct: float = 2.0
    side: str = "BOTH"
    margin_mode: str = "Isolated"
    position_mode: str = "Hedge"
    assets_mode: str = "Single-Asset"
    account_mode: str = "Classic Trading"
    connector_backend: str = DEFAULT_CONNECTOR_BACKEND
    leverage: int = 20
    mdd_logic: str = MDD_LOGIC_DEFAULT
    scan_top_n: int = 200
    scan_mdd_limit: float = 10.0
    scan_auto_apply: bool = False
    template: BacktestTemplateSettings = field(default_factory=BacktestTemplateSettings)
    indicators: dict[str, dict[str, object]] = field(default_factory=build_backtest_indicator_defaults)
    stop_loss: StopLossSettings = field(default_factory=StopLossSettings)

    def to_config_dict(self) -> dict[str, object]:
        return {
            "symbols": list(self.symbols),
            "intervals": list(self.intervals),
            "capital": self.capital,
            "logic": self.logic,
            "symbol_source": self.symbol_source,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "position_pct": self.position_pct,
            "side": self.side,
            "margin_mode": self.margin_mode,
            "position_mode": self.position_mode,
            "assets_mode": self.assets_mode,
            "account_mode": self.account_mode,
            "connector_backend": self.connector_backend,
            "leverage": self.leverage,
            "mdd_logic": self.mdd_logic,
            "scan_top_n": self.scan_top_n,
            "scan_mdd_limit": self.scan_mdd_limit,
            "scan_auto_apply": self.scan_auto_apply,
            "template": self.template.to_config_dict(),
            "indicators": copy.deepcopy(self.indicators),
            "stop_loss": self.stop_loss.to_config_dict(),
        }
