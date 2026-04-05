from __future__ import annotations

import copy
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ExecutionSettings:
    mode: str = "Live"
    account_type: str = "Futures"
    margin_mode: str = "Isolated"
    symbols: tuple[str, ...] = ("BTCUSDT",)
    intervals: tuple[str, ...] = ("1m",)
    lookback: int = 200
    leverage: int = 20
    tif: str = "GTC"
    gtd_minutes: int = 30
    position_mode: str = "Hedge"
    assets_mode: str = "Single-Asset"
    account_mode: str = "Classic Trading"
    lead_trader_enabled: bool = False
    lead_trader_profile: str | None = None
    loop_interval_override: str = "1m"
    runtime_symbol_interval_pairs: tuple[object, ...] = field(default_factory=tuple)
    backtest_symbol_interval_pairs: tuple[object, ...] = field(default_factory=tuple)
    side: str = "BOTH"
    position_pct: float = 2.0
    order_type: str = "MARKET"

    def to_config_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "account_type": self.account_type,
            "margin_mode": self.margin_mode,
            "symbols": list(self.symbols),
            "intervals": list(self.intervals),
            "lookback": self.lookback,
            "leverage": self.leverage,
            "tif": self.tif,
            "gtd_minutes": self.gtd_minutes,
            "position_mode": self.position_mode,
            "assets_mode": self.assets_mode,
            "account_mode": self.account_mode,
            "lead_trader_enabled": self.lead_trader_enabled,
            "lead_trader_profile": self.lead_trader_profile,
            "loop_interval_override": self.loop_interval_override,
            "runtime_symbol_interval_pairs": copy.deepcopy(list(self.runtime_symbol_interval_pairs)),
            "backtest_symbol_interval_pairs": copy.deepcopy(list(self.backtest_symbol_interval_pairs)),
            "side": self.side,
            "position_pct": self.position_pct,
            "order_type": self.order_type,
        }
