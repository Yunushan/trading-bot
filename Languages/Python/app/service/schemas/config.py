"""
Config summary schemas for the service facade.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


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
    symbols: tuple[str, ...]
    intervals: tuple[str, ...]
    api_credentials_present: bool

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


def _number(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def build_editable_config(config: dict | None) -> ServiceEditableConfig:
    cfg = config if isinstance(config, dict) else {}
    api_key = str(cfg.get("api_key") or "").strip()
    api_secret = str(cfg.get("api_secret") or "").strip()

    return ServiceEditableConfig(
        mode=str(cfg.get("mode") or "Live"),
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
        symbols=_string_list(cfg.get("symbols")),
        intervals=_string_list(cfg.get("intervals")),
        api_credentials_present=bool(api_key and api_secret),
    )


def build_config_summary(config: dict | None) -> ServiceConfigSummary:
    cfg = config if isinstance(config, dict) else {}
    indicators = cfg.get("indicators") if isinstance(cfg.get("indicators"), dict) else {}
    enabled_indicator_count = 0
    try:
        enabled_indicator_count = sum(
            1 for params in indicators.values() if isinstance(params, dict) and bool(params.get("enabled"))
        )
    except Exception:
        enabled_indicator_count = 0

    symbols = cfg.get("symbols") if isinstance(cfg.get("symbols"), list) else []
    intervals = cfg.get("intervals") if isinstance(cfg.get("intervals"), list) else []
    runtime_pairs = (
        cfg.get("runtime_symbol_interval_pairs")
        if isinstance(cfg.get("runtime_symbol_interval_pairs"), list)
        else []
    )
    backtest_pairs = (
        cfg.get("backtest_symbol_interval_pairs")
        if isinstance(cfg.get("backtest_symbol_interval_pairs"), list)
        else []
    )

    api_key = str(cfg.get("api_key") or "").strip()
    api_secret = str(cfg.get("api_secret") or "").strip()

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
    )
