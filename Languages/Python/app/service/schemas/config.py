"""
Config summary schemas for the service facade.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from ...core.backtest.intervals import normalize_backtest_intervals
from ...config import coerce_bool
from ...integrations.llm.providers import build_llm_config_payload


@dataclass(frozen=True, slots=True)
class ServiceEditableConfig:
    mode: str
    account_type: str
    margin_mode: str
    position_mode: str
    side: str
    leverage: float
    position_pct: float
    connector_backend: str
    selected_exchange: str
    code_language: str
    theme: str
    order_audit_max_bytes: int
    order_audit_backup_count: int
    connector_order_circuit_incident_log_max_bytes: int
    connector_order_circuit_incident_log_backup_count: int
    operational_connector_snapshot_stale_seconds: float
    operational_execution_heartbeat_stale_seconds: float
    operational_account_snapshot_stale_seconds: float
    operational_portfolio_snapshot_stale_seconds: float
    operational_live_start_gate_enabled: bool
    operational_live_order_gate_enabled: bool
    symbols: tuple[str, ...]
    intervals: tuple[str, ...]
    api_credentials_present: bool
    llm: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["symbols"] = list(self.symbols)
        payload["intervals"] = list(self.intervals)
        return payload


@dataclass(frozen=True, slots=True)
class ServiceConfigSummary:
    mode: str
    account_type: str
    connector_backend: str
    selected_exchange: str
    code_language: str
    theme: str
    api_credentials_present: bool
    symbol_count: int
    interval_count: int
    enabled_indicator_count: int
    runtime_pair_count: int
    backtest_pair_count: int
    llm_enabled: bool
    llm_provider: str
    llm_mode: str
    llm_api_key_present: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _string_list(value) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    items: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            items.append(text)
    return tuple(items)


def _interval_tuple(value) -> tuple[str, ...]:
    return tuple(normalize_backtest_intervals(value))


def _number(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _integer(value, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def build_editable_config(config: dict | None) -> ServiceEditableConfig:
    cfg = config if isinstance(config, dict) else {}
    api_key = str(cfg.get("api_key") or "").strip()
    api_secret = str(cfg.get("api_secret") or "").strip()

    return ServiceEditableConfig(
        mode=str(cfg.get("mode") or "Demo/Testnet"),
        account_type=str(cfg.get("account_type") or "Futures"),
        margin_mode=str(cfg.get("margin_mode") or "Isolated"),
        position_mode=str(cfg.get("position_mode") or "Hedge"),
        side=str(cfg.get("side") or "BOTH"),
        leverage=_number(cfg.get("leverage"), 0.0),
        position_pct=_number(cfg.get("position_pct"), 0.0),
        connector_backend=str(cfg.get("connector_backend") or ""),
        selected_exchange=str(cfg.get("selected_exchange") or ""),
        code_language=str(cfg.get("code_language") or ""),
        theme=str(cfg.get("theme") or ""),
        order_audit_max_bytes=_integer(cfg.get("order_audit_max_bytes"), 10 * 1024 * 1024),
        order_audit_backup_count=_integer(cfg.get("order_audit_backup_count"), 1),
        connector_order_circuit_incident_log_max_bytes=_integer(
            cfg.get("connector_order_circuit_incident_log_max_bytes"),
            2 * 1024 * 1024,
        ),
        connector_order_circuit_incident_log_backup_count=_integer(
            cfg.get("connector_order_circuit_incident_log_backup_count"),
            1,
        ),
        operational_connector_snapshot_stale_seconds=_number(
            cfg.get("operational_connector_snapshot_stale_seconds"),
            120.0,
        ),
        operational_execution_heartbeat_stale_seconds=_number(
            cfg.get("operational_execution_heartbeat_stale_seconds"),
            10.0,
        ),
        operational_account_snapshot_stale_seconds=_number(
            cfg.get("operational_account_snapshot_stale_seconds"),
            300.0,
        ),
        operational_portfolio_snapshot_stale_seconds=_number(
            cfg.get("operational_portfolio_snapshot_stale_seconds"),
            300.0,
        ),
        operational_live_start_gate_enabled=coerce_bool(cfg.get("operational_live_start_gate_enabled"), True),
        operational_live_order_gate_enabled=coerce_bool(cfg.get("operational_live_order_gate_enabled"), True),
        symbols=_string_list(cfg.get("symbols")),
        intervals=_interval_tuple(cfg.get("intervals")),
        api_credentials_present=bool(api_key and api_secret),
        llm=build_llm_config_payload(cfg),
    )


def build_config_summary(config: dict | None) -> ServiceConfigSummary:
    cfg = config if isinstance(config, dict) else {}
    indicators: dict[str, dict[str, object]] = {}
    raw_indicators = cfg.get("indicators")
    if isinstance(raw_indicators, dict):
        indicators = {
            str(key): value
            for key, value in raw_indicators.items()
            if isinstance(value, dict)
        }
    enabled_indicator_count = 0
    try:
        enabled_indicator_count = sum(
            True
            for params in indicators.values()
            if coerce_bool(params.get("enabled"), False)
        )
    except Exception:
        enabled_indicator_count = 0

    symbols: list[object] = []
    raw_symbols = cfg.get("symbols")
    if isinstance(raw_symbols, list):
        symbols = raw_symbols
    intervals = normalize_backtest_intervals(cfg.get("intervals"))
    runtime_pairs: list[object] = []
    raw_runtime_pairs = cfg.get("runtime_symbol_interval_pairs")
    if isinstance(raw_runtime_pairs, list):
        runtime_pairs = raw_runtime_pairs
    backtest_pairs: list[object] = []
    raw_backtest_pairs = cfg.get("backtest_symbol_interval_pairs")
    if isinstance(raw_backtest_pairs, list):
        backtest_pairs = raw_backtest_pairs

    api_key = str(cfg.get("api_key") or "").strip()
    api_secret = str(cfg.get("api_secret") or "").strip()
    llm = build_llm_config_payload(cfg)

    return ServiceConfigSummary(
        mode=str(cfg.get("mode") or "Unknown"),
        account_type=str(cfg.get("account_type") or "Unknown"),
        connector_backend=str(cfg.get("connector_backend") or "Unknown"),
        selected_exchange=str(cfg.get("selected_exchange") or "Unknown"),
        code_language=str(cfg.get("code_language") or "Unknown"),
        theme=str(cfg.get("theme") or "Unknown"),
        api_credentials_present=bool(api_key and api_secret),
        symbol_count=len(symbols),
        interval_count=len(intervals),
        enabled_indicator_count=int(enabled_indicator_count),
        runtime_pair_count=len(runtime_pairs),
        backtest_pair_count=len(backtest_pairs),
        llm_enabled=bool(llm["enabled"]),
        llm_provider=str(llm["provider"]),
        llm_mode=str(llm["mode"]),
        llm_api_key_present=bool(llm["api_key_present"]),
    )
