from __future__ import annotations

import copy
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ExecutionSettings:
    mode: str = "Demo/Testnet"
    account_type: str = "Futures"
    margin_mode: str = "Isolated"
    symbols: tuple[str, ...] = ("BTCUSDT",)
    intervals: tuple[str, ...] = ("1m",)
    lookback: int = 200
    leverage: int = 1
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
    live_trading_enabled: bool = False
    live_trading_acknowledgement: str = ""
    live_trading_max_leverage: int = 20
    live_trading_max_position_pct: float = 10.0
    live_allow_auto_bump_to_min_order: bool = False
    order_audit_enabled: bool = True
    order_audit_log_path: str = ""
    order_audit_max_bytes: int = 10 * 1024 * 1024
    order_audit_backup_count: int = 1
    connector_order_circuit_incident_log_path: str = ""
    connector_order_circuit_incident_log_max_bytes: int = 2 * 1024 * 1024
    connector_order_circuit_incident_log_backup_count: int = 1
    operational_connector_snapshot_stale_seconds: float = 120.0
    operational_execution_heartbeat_stale_seconds: float = 10.0
    operational_account_snapshot_stale_seconds: float = 300.0
    operational_portfolio_snapshot_stale_seconds: float = 300.0
    operational_live_start_gate_enabled: bool = True
    operational_live_order_gate_enabled: bool = True
    connector_order_block_circuit_breaker_enabled: bool = True
    connector_order_block_pause_threshold: int = 2
    connector_order_block_window_seconds: float = 60.0

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
            "live_trading_enabled": self.live_trading_enabled,
            "live_trading_acknowledgement": self.live_trading_acknowledgement,
            "live_trading_max_leverage": self.live_trading_max_leverage,
            "live_trading_max_position_pct": self.live_trading_max_position_pct,
            "live_allow_auto_bump_to_min_order": self.live_allow_auto_bump_to_min_order,
            "order_audit_enabled": self.order_audit_enabled,
            "order_audit_log_path": self.order_audit_log_path,
            "order_audit_max_bytes": self.order_audit_max_bytes,
            "order_audit_backup_count": self.order_audit_backup_count,
            "connector_order_circuit_incident_log_path": self.connector_order_circuit_incident_log_path,
            "connector_order_circuit_incident_log_max_bytes": self.connector_order_circuit_incident_log_max_bytes,
            "connector_order_circuit_incident_log_backup_count": (
                self.connector_order_circuit_incident_log_backup_count
            ),
            "operational_connector_snapshot_stale_seconds": self.operational_connector_snapshot_stale_seconds,
            "operational_execution_heartbeat_stale_seconds": self.operational_execution_heartbeat_stale_seconds,
            "operational_account_snapshot_stale_seconds": self.operational_account_snapshot_stale_seconds,
            "operational_portfolio_snapshot_stale_seconds": self.operational_portfolio_snapshot_stale_seconds,
            "operational_live_start_gate_enabled": self.operational_live_start_gate_enabled,
            "operational_live_order_gate_enabled": self.operational_live_order_gate_enabled,
            "connector_order_block_circuit_breaker_enabled": self.connector_order_block_circuit_breaker_enabled,
            "connector_order_block_pause_threshold": self.connector_order_block_pause_threshold,
            "connector_order_block_window_seconds": self.connector_order_block_window_seconds,
        }
