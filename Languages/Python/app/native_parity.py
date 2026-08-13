"""
Python-owned native parity contract for C++ and Rust destinations.

This module is intentionally data-oriented.  It defines the Python source
surface that native destinations must track before they can honestly claim
contract parity with the Python application. Standalone product/runtime parity
is stricter and remains false until native runtimes have matching execution
ownership plus external evidence.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any

from .gui.code.code_language_catalog import (
    EXCHANGE_PATHS,
    STARTER_CRYPTO_EXCHANGES,
    _rust_dependency_targets_for_config,
)
from .gui.backtest.backtest_templates import BACKTEST_TEMPLATE_DEFINITIONS
from .gui.runtime.composition.module_state_constants import (
    ACCOUNT_MODE_OPTIONS,
    BACKTEST_INTERVAL_ORDER,
    CHART_MARKET_OPTIONS,
    DASHBOARD_LOOP_CHOICES,
    DEFAULT_CHART_SYMBOLS,
    LEAD_TRADER_OPTIONS,
    MDD_LOGIC_LABELS,
    SIDE_LABELS,
    STOP_LOSS_MODE_LABELS,
    STOP_LOSS_SCOPE_LABELS,
    TRADINGVIEW_INTERVAL_MAP,
    _connector_options,
)
from .gui.runtime.ui.theme_styles import DESIGN_OPTIONS
from .integrations.llm.providers import (
    LLM_MODEL_CATALOG_PATH_ENV,
    LLM_PROVIDER_CATALOG_REVISION,
    _PROVIDER_SPECS,
    llm_provider_choices,
)
from .service.api_contract import (
    SERVICE_API_ROUTE_METHODS,
    SERVICE_API_ROUTE_PATHS,
    SERVICE_API_ROUTE_SUFFIXES,
    SERVICE_BACKTEST_RUN_REQUEST_FIELDS,
    service_api_contract_payload,
)
from .settings.backtest import BacktestSettings, MDD_LOGIC_OPTIONS
from .settings.connectors import DEFAULT_INDICATOR_SOURCE
from .settings.execution import ExecutionSettings
from .settings.exchange_support import (
    BROKER_INTEGRATION_DISPOSITIONS,
    BROKER_MARKET_SCOPES,
    BROKER_ORDER_ROUTING_BACKENDS,
    CCXT_DIAGNOSTIC_EXCHANGES,
    CCXT_EXCHANGE_IDS,
    CCXT_ORDER_ROUTING_EXCHANGES,
    METATRADER5_BROKER_ALIASES,
    ORDER_EXECUTION_EXCHANGES,
    REQUESTED_BROKER_TARGETS,
    SUPPORTED_CONNECTOR_BACKENDS,
    SUPPORTED_EXCHANGES,
    SUPPORTED_BROKERS,
    SUPPORTED_FOREX_BROKERS,
    canonical_broker_name,
)
from .settings.indicators import (
    INDICATOR_CATALOG,
    build_backtest_indicator_defaults,
    build_runtime_indicator_defaults,
)
from .settings.live_safety import (
    LIVE_TRADING_ACK_ENV,
    LIVE_TRADING_ACK_ENV_LEGACY,
    LIVE_TRADING_ENABLED_ENV,
    LIVE_TRADING_MAX_LEVERAGE_ENV,
    LIVE_TRADING_MAX_POSITION_PCT_ENV,
    LIVE_TRADING_MAX_SESSION_ORDERS_ENV,
)
from .settings.risk import RiskManagementSettings, STOP_LOSS_MODE_ORDER, STOP_LOSS_SCOPE_OPTIONS
from .settings.ui import DEFAULT_DESIGN, DEFAULT_SELECTED_EXCHANGE, DEFAULT_THEME
from .settings.validation import (
    _ACCOUNT_MODE_CHOICES,
    _ACCOUNT_TYPE_CHOICES,
    _ASSETS_MODE_CHOICES,
    _BACKTEST_EXECUTION_BACKEND_CHOICES,
    _CHART_VIEW_MODE_CHOICES,
    _LLM_REASONING_EFFORT_CHOICES,
    _LLM_USE_FOR_CHOICES,
    _LOGIC_CHOICES,
    _MARGIN_MODE_CHOICES,
    _OPTIMIZER_METRIC_CHOICES,
    _OPTIMIZER_MODE_CHOICES,
    _ORDER_TYPE_CHOICES,
    _POSITION_MODE_CHOICES,
    _SCAN_SCOPE_CHOICES,
    _SIDE_CHOICES,
    _TIF_CHOICES,
)


NATIVE_PARITY_SCHEMA_VERSION = 1
NATIVE_PARITY_SOURCE = "Languages/Python"
CPP_STANDALONE_RUNTIME_READY = False
RUST_STANDALONE_RUNTIME_READY = False
NATIVE_POSITION_RECONCILIATION_REFERENCE_SCHEMA_VERSION = 1

CONFIG_MODE_OPTIONS = ("Live", "Demo", "Testnet")
THEME_OPTIONS = ("Light", "Dark", "Blue", "Yellow", "Green", "Red")
INDICATOR_SOURCE_OPTIONS = (
    "Binance spot",
    "Binance futures",
)

# Native shells must derive their direct-execution boundary from Python as well
# as their option catalogs. Anything outside this deliberately small surface is
# coordinated by the Python Service API/provider connector until native runtime
# promotion has matching implementation and external evidence.
NATIVE_RUNTIME_OWNERSHIP = {
    "direct_exchanges": ("Binance",),
    "direct_connector_backends": (
        "binance-sdk-derivatives-trading-usds-futures",
        "binance-sdk-derivatives-trading-coin-futures",
        "binance-sdk-spot",
        "binance-connector",
    ),
    "direct_market_families": (
        "usd-m-futures",
        "coin-m-futures",
        "spot",
    ),
    "indicator_source_market_families": (
        ("binance_spot", "spot"),
        ("binance_futures", "usd-m-futures"),
        ("spot", "spot"),
        ("futures", "usd-m-futures"),
    ),
    "delegated_owner": "Python Service API/provider connector",
}
LLM_USE_FOR_OPTIONS = (
    ("Advisory", "advisory"),
    ("Signal confirmation", "signal_confirmation"),
    ("Risk review", "risk_review"),
    ("Backtest explanation", "backtest_explanation"),
)
DASHBOARD_STRATEGY_TEMPLATE_DEFINITIONS = {
    "": {"label": "No Template"},
    "top10": {"label": "Top 10 %2 per trade 1x Isolated"},
    "top50": {"label": "Top 50 %2 per trade 1x"},
    "top100": {"label": "Top 100 %1 per trade 1x"},
}

# Exchange order requests must be structurally safe in every mode. Live mode
# adds credential acknowledgement and session budget gates; it does not own the
# basic request, filter, connector, or audit validation contract.
ORDER_GUARD_BEHAVIOR = {
    "validate_intent_all_modes": True,
    "validate_exchange_filters_all_modes": True,
    "validate_connector_health_all_modes": True,
    "validate_audit_enabled_all_modes": True,
    "validate_audit_writable_all_modes": True,
    "live_only_requirements": (
        "credentials",
        "live_acknowledgement",
        "session_order_cap",
        "session_order_count_increment",
    ),
    "live_safety_environment": {
        "enabled": LIVE_TRADING_ENABLED_ENV,
        "acknowledgement": LIVE_TRADING_ACK_ENV,
        "legacy_acknowledgement": LIVE_TRADING_ACK_ENV_LEGACY,
        "max_leverage": LIVE_TRADING_MAX_LEVERAGE_ENV,
        "max_position_pct": LIVE_TRADING_MAX_POSITION_PCT_ENV,
        "max_session_orders": LIVE_TRADING_MAX_SESSION_ORDERS_ENV,
    },
}

# Canonical runtime-series keys for every user-selectable indicator.  Python's
# chart, backtest, and native destinations consume these names, so emit them
# with the catalog instead of maintaining separate C++ and Rust switch lists.
INDICATOR_RUNTIME_OUTPUT_KEYS: dict[str, tuple[str, ...]] = {
    "ma": ("ma",),
    "donchian": ("donchian_high", "donchian_low", "donchian"),
    "psar": ("psar",),
    "bb": ("bb_upper", "bb_mid", "bb_lower"),
    "bbw": ("bbw",),
    "keltner": ("keltner_upper", "keltner_mid", "keltner_lower"),
    "ichimoku": (
        "ichimoku_tenkan",
        "ichimoku_kijun",
        "ichimoku_span_a",
        "ichimoku_span_b",
        "ichimoku_chikou",
        "ichimoku",
    ),
    "rsi": ("rsi",),
    "volume": ("volume",),
    "obv": ("obv",),
    "rvol": ("rvol",),
    "cmf": ("cmf",),
    "cci": ("cci",),
    "roc": ("roc",),
    "trix": ("trix",),
    "ppo": ("ppo", "ppo_signal", "ppo_hist"),
    "ao": ("ao",),
    "kst": ("kst", "kst_signal", "kst_hist"),
    "aroon": ("aroon_up", "aroon_down", "aroon"),
    "chop": ("chop",),
    "atr": ("atr",),
    "natr": ("natr",),
    "vwap": ("vwap",),
    "mfi": ("mfi",),
    "stoch_rsi": ("stoch_rsi", "stoch_rsi_k", "stoch_rsi_d"),
    "willr": ("willr",),
    "macd": ("macd_line", "macd_signal"),
    "uo": ("uo",),
    "adx": ("adx",),
    "dmi": ("dmi_plus", "dmi_minus", "dmi"),
    "supertrend": ("supertrend",),
    "ema": ("ema",),
    "stochastic": ("stochastic", "stochastic_k", "stochastic_d"),
}


@dataclass(frozen=True, slots=True)
class NativeParityDomain:
    key: str
    title: str
    python_surface: str
    cpp_required_before_full_parity: tuple[str, ...]
    rust_required_before_full_parity: tuple[str, ...]
    cpp_full_parity: bool = False
    rust_full_parity: bool = False


NATIVE_PARITY_DOMAINS: tuple[NativeParityDomain, ...] = (
    NativeParityDomain(
        key="desktop_shell_and_tabs",
        title="Desktop shell and primary tabs",
        python_surface="Dashboard, Chart, Positions, Backtest, Liquidation Heatmap, Code Languages, startup composition, theme, and live tab wiring.",
        cpp_required_before_full_parity=(),
        rust_required_before_full_parity=(),
        cpp_full_parity=True,
        rust_full_parity=True,
    ),
    NativeParityDomain(
        key="service_api_contract",
        title="Service API contract",
        python_surface="Canonical /api/v1 routes, methods, schemas, dashboard stream, auth, control-plane state, and desktop bridge contract.",
        cpp_required_before_full_parity=(),
        rust_required_before_full_parity=(),
        cpp_full_parity=True,
        rust_full_parity=True,
    ),
    NativeParityDomain(
        key="config_persistence",
        title="Config persistence and hydration",
        python_surface="Runtime config, file save/load, dirty state, dashboard hydration, service snapshots, and secret redaction.",
        cpp_required_before_full_parity=(),
        rust_required_before_full_parity=(),
        cpp_full_parity=True,
        rust_full_parity=True,
    ),
    NativeParityDomain(
        key="strategy_runtime",
        title="Strategy runtime and signal generation",
        python_surface="Indicator computation, strategy cycles, signal generation, live candle options, override tables, and worker lifecycle.",
        cpp_required_before_full_parity=(),
        rust_required_before_full_parity=(),
        cpp_full_parity=True,
        rust_full_parity=True,
    ),
    NativeParityDomain(
        key="exchange_connectors",
        title="Exchange connectors and market data",
        python_surface="Binance SDK/connector/CCXT/python-binance selection, connector support metadata, transport diagnostics, rate limits, REST market data, and WebSocket paths.",
        cpp_required_before_full_parity=(),
        rust_required_before_full_parity=(),
        cpp_full_parity=True,
        rust_full_parity=True,
    ),
    NativeParityDomain(
        key="account_portfolio_positions",
        title="Account, portfolio, and positions",
        python_surface="Account snapshots, portfolio summaries, futures position queries, close-all behavior, position history, allocation tracking, and reconciliation.",
        cpp_required_before_full_parity=(),
        rust_required_before_full_parity=(),
        cpp_full_parity=True,
        rust_full_parity=True,
    ),
    NativeParityDomain(
        key="order_execution_and_risk",
        title="Order execution, audit, and risk",
        python_surface="Order sizing, submit guards, audit logs, position gates, close-opposite logic, stop-loss scopes, live safety preflight, circuit breaker, and shutdown guards.",
        cpp_required_before_full_parity=(),
        rust_required_before_full_parity=(),
        cpp_full_parity=True,
        rust_full_parity=True,
    ),
    NativeParityDomain(
        key="backtest_engine",
        title="Backtest engine, optimizer, and scanner",
        python_surface="Backtest engine, optimizer limits/results, live parity request shape, scanner polling, dashboard import, indicator selection, and provenance.",
        cpp_required_before_full_parity=(),
        rust_required_before_full_parity=(),
        cpp_full_parity=True,
        rust_full_parity=True,
    ),
    NativeParityDomain(
        key="charts_and_heatmaps",
        title="Charts and liquidation heatmaps",
        python_surface="TradingView, lightweight chart assets, candlestick fallback, chart state payloads, browser guards, and liquidation provider panels.",
        cpp_required_before_full_parity=(),
        rust_required_before_full_parity=(),
        cpp_full_parity=True,
        rust_full_parity=True,
    ),
    NativeParityDomain(
        key="logs_terminal_diagnostics",
        title="Logs, terminal, and diagnostics",
        python_surface="Service logs, dashboard logs, terminal command execution, exception diagnostics, secret redaction, and test runner/reporting flows.",
        cpp_required_before_full_parity=(),
        rust_required_before_full_parity=(),
        cpp_full_parity=True,
        rust_full_parity=True,
    ),
    NativeParityDomain(
        key="llm_advisory",
        title="LLM advisory and local model lifecycle",
        python_surface="Provider catalogs, privacy flags, advisory prompt execution, config persistence, local Ollama status/start/pull/delete, and redacted output.",
        cpp_required_before_full_parity=(),
        rust_required_before_full_parity=(),
        cpp_full_parity=True,
        rust_full_parity=True,
    ),
    NativeParityDomain(
        key="startup_packaging_platform",
        title="Startup, packaging, and platform integration",
        python_surface="Product entrypoints, startup splash/suppression, Windows taskbar metadata, PyInstaller packaging, service wrappers, and release smoke tests.",
        cpp_required_before_full_parity=(),
        rust_required_before_full_parity=(),
        cpp_full_parity=True,
        rust_full_parity=True,
    ),
)


def _native_position_reference_allocation(
    ledger_id: str,
    interval: str,
    *,
    qty: float = 1.0,
) -> dict[str, object]:
    return {
        "ledger_id": ledger_id,
        "interval": interval,
        "interval_display": interval,
        "trigger_indicators": ["rsi"],
        "trade_id": f"trade-{ledger_id}",
        "client_order_id": f"client-{ledger_id}",
        "order_id": f"order-{ledger_id}",
        "event_uid": f"event-{ledger_id}",
        "slot_id": f"slot-{ledger_id}",
        "context_key": f"context-{ledger_id}",
        "open_time": "2026-01-01T00:00:00Z",
        "close_time": "",
        "qty": qty,
        "margin_usdt": 100.0,
        "notional": 100.0,
        "pnl_value": None,
        "status": "Open",
        "close_price": None,
        "entry_price": 100.0,
        "leverage": 1,
    }


def _native_position_reference_record(
    symbol: str,
    side_key: str,
    interval: str,
    *,
    open_time: str = "",
    stop_loss_enabled: bool = False,
    allocations: list[dict[str, object]] | None = None,
    quantity: float | None = None,
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "side_key": side_key,
        "interval": interval,
        "quantity": quantity,
        "mark_price": 100.0 if quantity is not None else None,
        "size_usdt": 100.0 if quantity is not None else None,
        "margin_usdt": 100.0 if quantity is not None else None,
        "pnl_value": 0.0 if quantity is not None else None,
        "roi_percent": 0.0 if quantity is not None else None,
        "leverage": 1 if quantity is not None else None,
        "liquidation_price": None,
        "status": "Active",
        "stop_loss_enabled": stop_loss_enabled,
        "open_time": open_time,
        "close_time": "",
        "allocations": deepcopy(allocations or []),
    }


def _native_position_reference_state(
    *,
    open_position_records: dict[str, dict[str, object]],
    entry_allocations: dict[str, list[dict[str, object]]] | None = None,
    closed_position_records: list[dict[str, object]] | None = None,
    missing_counts: dict[str, int] | None = None,
    pending_close_times: dict[str, str] | None = None,
) -> dict[str, object]:
    return {
        "entry_allocations": deepcopy(entry_allocations or {}),
        "open_position_records": deepcopy(open_position_records),
        "closed_position_records": deepcopy(closed_position_records or []),
        "missing_counts": deepcopy(missing_counts or {}),
        "pending_close_times": deepcopy(pending_close_times or {}),
    }


def _native_position_reference_epoch(value: object) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except (TypeError, ValueError, OverflowError):
        return None


def _native_position_reference_reconcile_step(
    state: dict[str, object],
    live_position_records: dict[str, dict[str, object]],
    policy: dict[str, object],
    *,
    now_epoch_seconds: float,
    close_time: str,
    max_history: int,
) -> tuple[dict[str, object], dict[str, list[str]]]:
    """Apply the deterministic portion of Python's missing-position policy.

    The GUI still performs the exchange freshness lookup and liquidation lookup
    around this state transition. This pure case runner is the Python oracle for
    the same state transition that native runtimes execute after those lookups.
    """

    next_state = deepcopy(state)
    open_records = next_state["open_position_records"]
    entry_allocations = next_state["entry_allocations"]
    closed_records = next_state["closed_position_records"]
    missing_counts = next_state["missing_counts"]
    pending_close_times = next_state["pending_close_times"]
    assert isinstance(open_records, dict)
    assert isinstance(entry_allocations, dict)
    assert isinstance(closed_records, list)
    assert isinstance(missing_counts, dict)
    assert isinstance(pending_close_times, dict)

    live_keys: list[str] = []
    for key in sorted(live_position_records):
        live_keys.append(key)
        record = deepcopy(live_position_records[key])
        previous = open_records.get(key)
        if not isinstance(previous, dict):
            previous = {}
        if not str(record.get("open_time") or "").strip():
            previous_open = str(previous.get("open_time") or "").strip()
            if previous_open:
                record["open_time"] = previous_open
        if not str(record.get("interval") or "").strip():
            previous_interval = str(previous.get("interval") or "").strip()
            if previous_interval:
                record["interval"] = previous_interval
        if not record.get("allocations"):
            previous_allocations = previous.get("allocations")
            if previous_allocations:
                record["allocations"] = deepcopy(previous_allocations)
        if not bool(record.get("stop_loss_enabled")) and bool(previous.get("stop_loss_enabled")):
            record["stop_loss_enabled"] = True
        if not str(record.get("status") or "").strip():
            record["status"] = "Active"
        missing_counts.pop(key, None)
        pending_close_times.pop(key, None)
        open_records[key] = record

    try:
        threshold = int(policy.get("positions_missing_threshold") or 2)
    except (TypeError, ValueError):
        threshold = 2
    threshold = max(1, threshold)
    try:
        grace_seconds = float(policy.get("positions_missing_grace_seconds") or 30.0)
    except (TypeError, ValueError):
        grace_seconds = 0.0
    if grace_seconds != grace_seconds or grace_seconds < 0.0:
        grace_seconds = 0.0
    allow_autoclose = bool(policy.get("positions_missing_autoclose", True))
    summary = {
        "closed_keys": [],
        "dropped_keys": [],
        "waiting_keys": [],
        "live_keys": live_keys,
    }

    for key in sorted(open_records):
        if key in live_position_records:
            continue
        count = int(missing_counts.get(key, 0) or 0) + 1
        missing_counts[key] = count
        required = 1 if key in pending_close_times else threshold
        if count < required:
            summary["waiting_keys"].append(key)
            continue

        within_grace = False
        if grace_seconds > 0.0 and key not in pending_close_times:
            record = open_records.get(key)
            open_value = record.get("open_time") if isinstance(record, dict) else None
            opened = _native_position_reference_epoch(open_value)
            if opened is not None:
                age_seconds = now_epoch_seconds - opened
                within_grace = 0.0 <= age_seconds < grace_seconds
        if within_grace:
            summary["waiting_keys"].append(key)
            continue

        if allow_autoclose:
            record = deepcopy(open_records.pop(key))
            record["status"] = "Closed"
            record["close_time"] = close_time.strip() or str(record.get("close_time") or "")
            allocations = entry_allocations.get(key)
            if allocations:
                record["allocations"] = deepcopy(allocations)
            closed_records.insert(0, record)
            del closed_records[max(1, int(max_history)) :]
            summary["closed_keys"].append(key)
        else:
            open_records.pop(key, None)
            entry_allocations.pop(key, None)
            summary["dropped_keys"].append(key)
        missing_counts.pop(key, None)
        pending_close_times.pop(key, None)

    for key in summary:
        summary[key].sort()
    return next_state, summary


def native_position_reconciliation_reference_cases() -> list[dict[str, object]]:
    allocation = _native_position_reference_allocation("ledger-btc", "5m")
    cases: list[dict[str, object]] = [
        {
            "name": "live-recovery-preserves-python-metadata",
            "initial_state": _native_position_reference_state(
                open_position_records={
                    "BTCUSDT:L": _native_position_reference_record(
                        "BTCUSDT",
                        "L",
                        "5m",
                        open_time="2026-01-01T00:00:00Z",
                        stop_loss_enabled=True,
                        allocations=[allocation],
                    )
                },
                entry_allocations={"BTCUSDT:L": [allocation]},
                missing_counts={"BTCUSDT:L": 2},
                pending_close_times={"BTCUSDT:L": "2026-01-01T00:00:01Z"},
            ),
            "steps": [
                {
                    "live_position_records": {
                        "BTCUSDT:L": _native_position_reference_record(
                            "BTCUSDT", "L", "", quantity=1.0
                        )
                    },
                    "policy": {
                        "positions_missing_threshold": 2,
                        "positions_missing_grace_seconds": 30.0,
                        "positions_missing_autoclose": True,
                    },
                    "now_epoch_seconds": 1_767_225_602.0,
                    "close_time": "2026-01-01T00:00:02Z",
                    "max_history": 10,
                }
            ],
        },
        {
            "name": "threshold-autoclose-after-two-misses",
            "initial_state": _native_position_reference_state(
                open_position_records={
                    "ETHUSDT:S": _native_position_reference_record("ETHUSDT", "S", "1m")
                }
            ),
            "steps": [
                {
                    "live_position_records": {},
                    "policy": {
                        "positions_missing_threshold": 2,
                        "positions_missing_grace_seconds": 0.0,
                        "positions_missing_autoclose": True,
                    },
                    "now_epoch_seconds": 1_767_225_660.0,
                    "close_time": "2026-01-01T00:01:00Z",
                    "max_history": 10,
                },
                {
                    "live_position_records": {},
                    "policy": {
                        "positions_missing_threshold": 2,
                        "positions_missing_grace_seconds": 0.0,
                        "positions_missing_autoclose": True,
                    },
                    "now_epoch_seconds": 1_767_225_661.0,
                    "close_time": "2026-01-01T00:01:01Z",
                    "max_history": 10,
                },
            ],
        },
        {
            "name": "grace-period-waits-before-close",
            "initial_state": _native_position_reference_state(
                open_position_records={
                    "XRPUSDT:L": _native_position_reference_record(
                        "XRPUSDT", "L", "5m", open_time="2026-01-01T00:00:00Z"
                    )
                }
            ),
            "steps": [
                {
                    "live_position_records": {},
                    "policy": {
                        "positions_missing_threshold": 1,
                        "positions_missing_grace_seconds": 120.0,
                        "positions_missing_autoclose": True,
                    },
                    "now_epoch_seconds": 1_767_225_660.0,
                    "close_time": "2026-01-01T00:01:00Z",
                    "max_history": 10,
                }
            ],
        },
        {
            "name": "autoclose-disabled-drops-record",
            "initial_state": _native_position_reference_state(
                open_position_records={
                    "SOLUSDT:S": _native_position_reference_record("SOLUSDT", "S", "1m")
                }
            ),
            "steps": [
                {
                    "live_position_records": {},
                    "policy": {
                        "positions_missing_threshold": 1,
                        "positions_missing_grace_seconds": 0.0,
                        "positions_missing_autoclose": False,
                    },
                    "now_epoch_seconds": 1_767_225_660.0,
                    "close_time": "2026-01-01T00:01:00Z",
                    "max_history": 10,
                }
            ],
        },
        {
            "name": "pending-close-bypasses-threshold-and-grace",
            "initial_state": _native_position_reference_state(
                open_position_records={
                    "ADAUSDT:L": _native_position_reference_record(
                        "ADAUSDT", "L", "1m", open_time="2026-01-01T00:00:00Z"
                    )
                },
                pending_close_times={"ADAUSDT:L": "2026-01-01T00:00:10Z"},
            ),
            "steps": [
                {
                    "live_position_records": {},
                    "policy": {
                        "positions_missing_threshold": 2,
                        "positions_missing_grace_seconds": 120.0,
                        "positions_missing_autoclose": True,
                    },
                    "now_epoch_seconds": 1_767_225_660.0,
                    "close_time": "2026-01-01T00:01:00Z",
                    "max_history": 10,
                }
            ],
        },
    ]

    for case in cases:
        state = deepcopy(case["initial_state"])
        expected_steps: list[dict[str, object]] = []
        for step in case["steps"]:
            state, summary = _native_position_reference_reconcile_step(
                state,
                step["live_position_records"],
                step["policy"],
                now_epoch_seconds=float(step["now_epoch_seconds"]),
                close_time=str(step["close_time"]),
                max_history=int(step["max_history"]),
            )
            expected_steps.append({"summary": summary, "state": deepcopy(state)})
        case["expected_steps"] = expected_steps
    return cases


def _domain_payload(domain: NativeParityDomain) -> dict[str, Any]:
    return asdict(domain)


def _indicator_payload() -> list[dict[str, object]]:
    runtime_defaults = build_runtime_indicator_defaults()
    backtest_defaults = build_backtest_indicator_defaults()
    catalog_keys = {definition.key for definition in INDICATOR_CATALOG}
    output_keys = set(INDICATOR_RUNTIME_OUTPUT_KEYS)
    if catalog_keys != output_keys:
        missing = ", ".join(sorted(catalog_keys - output_keys))
        unexpected = ", ".join(sorted(output_keys - catalog_keys))
        raise RuntimeError(
            "INDICATOR_RUNTIME_OUTPUT_KEYS must exactly match INDICATOR_CATALOG "
            f"(missing: {missing or '-'}; unexpected: {unexpected or '-'})"
        )
    return [
        {
            "key": definition.key,
            "display_name": definition.display_name,
            "default_enabled": bool(runtime_defaults.get(definition.key, {}).get("enabled")),
            # Native destinations need the canonical runtime parameters as well as the
            # display catalog. Keep this JSON-shaped so new Python-only parameters do
            # not require a parallel destination schema migration.
            "runtime_config": runtime_defaults.get(definition.key, {}),
            # Backtest thresholds and signal/filter modes intentionally differ from
            # live runtime defaults. Native engines must consume these values rather
            # than silently inventing destination-specific behavior.
            "backtest_config": backtest_defaults.get(definition.key, {}),
            "runtime_output_keys": list(INDICATOR_RUNTIME_OUTPUT_KEYS[definition.key]),
        }
        for definition in INDICATOR_CATALOG
    ]


def _llm_provider_payload() -> list[dict[str, object]]:
    return [
        {
            "key": provider.key,
            "label": provider.label,
            "mode": provider.mode,
            "protocol": provider.protocol,
            "default_base_url": provider.default_base_url,
            "default_model": provider.default_model,
            "api_key_env": provider.api_key_env,
            "model_suggestions": list(provider.model_suggestions),
            "reasoning_efforts": list(provider.reasoning_efforts),
            "default_reasoning_effort": provider.default_reasoning_effort,
            "catalog_revision": LLM_PROVIDER_CATALOG_REVISION,
            "custom_models_env": f"BOT_LLM_EXTRA_MODELS_{provider.key.upper().replace('-', '_')}",
            "custom_models_path_env": LLM_MODEL_CATALOG_PATH_ENV,
            "notes": list(provider.notes),
        }
        for provider in _PROVIDER_SPECS
    ]


def _config_choice_maps() -> dict[str, dict[str, str]]:
    return {
        "account_type": dict(_ACCOUNT_TYPE_CHOICES),
        "margin_mode": dict(_MARGIN_MODE_CHOICES),
        "position_mode": dict(_POSITION_MODE_CHOICES),
        "assets_mode": dict(_ASSETS_MODE_CHOICES),
        "account_mode": dict(_ACCOUNT_MODE_CHOICES),
        "side": dict(_SIDE_CHOICES),
        "order_type": dict(_ORDER_TYPE_CHOICES),
        "tif": dict(_TIF_CHOICES),
        "logic": dict(_LOGIC_CHOICES),
        "mdd_logic": {item: item for item in MDD_LOGIC_OPTIONS},
        "stop_loss_mode": {item: item for item in STOP_LOSS_MODE_ORDER},
        "stop_loss_scope": {item: item for item in STOP_LOSS_SCOPE_OPTIONS},
        "scan_scope": dict(_SCAN_SCOPE_CHOICES),
        "optimizer_mode": dict(_OPTIMIZER_MODE_CHOICES),
        "optimizer_metric": dict(_OPTIMIZER_METRIC_CHOICES),
        "backtest_execution_backend": dict(_BACKTEST_EXECUTION_BACKEND_CHOICES),
        "chart_view_mode": dict(_CHART_VIEW_MODE_CHOICES),
        "llm_use_for": dict(_LLM_USE_FOR_CHOICES),
        "llm_reasoning_effort": dict(_LLM_REASONING_EFFORT_CHOICES),
    }


def _label_map_payload(values: dict[str, str]) -> list[dict[str, str]]:
    return [{"key": str(key), "label": str(label)} for key, label in values.items()]


def _choice_payload(values: list[tuple[str, str]] | tuple[tuple[str, str], ...]) -> list[dict[str, str]]:
    return [{"label": str(label), "key": str(key), "value": str(key)} for label, key in values]


def _canonical_choice_payload(values: dict[str, str]) -> list[dict[str, str]]:
    seen = set()
    result = []
    for value in values.values():
        if value in seen:
            continue
        seen.add(value)
        result.append({"key": str(value), "value": str(value), "label": str(value)})
    return result


def _fixed_choice_payload(values: list[tuple[str, str]] | tuple[tuple[str, str], ...]) -> list[dict[str, str]]:
    return [{"key": str(key), "value": str(key), "label": str(label)} for key, label in values]


def _value_option_payload(values: tuple[str, ...] | list[str]) -> list[dict[str, str]]:
    return [{"key": str(value), "value": str(value), "label": str(value)} for value in values]


def _exchange_payload() -> list[dict[str, object]]:
    return [
        {
            "key": str(option["key"]),
            "label": (f"{option['title']} ({option['badge']})" if option.get("badge") else str(option["title"])),
            "title": str(option["title"]),
            "badge": str(option.get("badge") or ""),
            "disabled": bool(option.get("disabled", False)),
        }
        for option in STARTER_CRYPTO_EXCHANGES
        if option["key"] in EXCHANGE_PATHS
    ]


def _rust_environment_dependency_payload() -> list[dict[str, str]]:
    targets = _rust_dependency_targets_for_config({"selected_rust_framework": "Tauri"})
    payload: list[dict[str, str]] = []
    for target in targets:
        kind = str(target.get("custom") or "").strip()
        path = str(target.get("path") or "").strip()
        if kind == "rust_rustc":
            key = "rustc"
        elif kind == "rust_cargo":
            key = "cargo"
        else:
            key = path
        payload.append(
            {
                "key": key,
                "label": str(target.get("label") or key).strip(),
                "kind": kind,
                "path": path,
                "latest": str(target.get("latest") or "").strip(),
                "usage": str(target.get("usage") or "").strip(),
            }
        )
    return payload


def native_python_risk_defaults() -> dict[str, object]:
    """Return the effective Python strategy-risk defaults for native consumers.

    ``RiskManagementSettings`` retains the UI setting default for live candle
    values, while ``StrategyEngine`` deliberately defaults that runtime option
    to ``False`` when it is absent. Native runtimes must consume the effective
    engine default so the generated contract describes execution behavior.
    """

    defaults = RiskManagementSettings().to_config_dict()
    defaults["indicator_use_live_values"] = False
    return defaults


def _broker_identity_key(value: object) -> str:
    return "".join(character for character in str(value or "").strip().lower() if character.isalnum())


def _broker_canonical_name_payload() -> list[dict[str, str]]:
    """Expose Python's broker alias resolution to native consumers."""

    mappings: dict[str, str] = {}
    for value in (
        *SUPPORTED_BROKERS,
        *BROKER_INTEGRATION_DISPOSITIONS,
        *METATRADER5_BROKER_ALIASES,
        *REQUESTED_BROKER_TARGETS,
    ):
        mappings[_broker_identity_key(value)] = canonical_broker_name(value)
    return [{"identity": identity, "canonical": canonical} for identity, canonical in mappings.items()]


def native_python_source_contract_payload() -> dict[str, Any]:
    route_methods = {name: list(methods) for name, methods in SERVICE_API_ROUTE_METHODS.items()}
    connector_options = [{"label": label, "key": key} for label, key in _connector_options()]
    broker_backends = [
        {
            "broker": broker,
            "key": str(broker).strip().lower().replace("_", "-"),
            "backend": BROKER_ORDER_ROUTING_BACKENDS[str(broker).strip().lower().replace("_", "-")],
            "market_scope": BROKER_MARKET_SCOPES[str(broker).strip().lower().replace("_", "-")],
            "forex_order_routing_supported": broker in SUPPORTED_FOREX_BROKERS,
        }
        for broker in SUPPORTED_BROKERS
    ]
    execution_defaults = ExecutionSettings()
    backtest_defaults = BacktestSettings()
    risk_defaults = native_python_risk_defaults()
    ui_defaults = {
        "theme": DEFAULT_THEME,
        "design": DEFAULT_DESIGN,
        "indicator_source": DEFAULT_INDICATOR_SOURCE,
        "selected_exchange": DEFAULT_SELECTED_EXCHANGE,
    }
    cpp_contract_parity = all(domain.cpp_full_parity for domain in NATIVE_PARITY_DOMAINS)
    rust_contract_parity = all(domain.rust_full_parity for domain in NATIVE_PARITY_DOMAINS)
    return {
        "schema_version": NATIVE_PARITY_SCHEMA_VERSION,
        "source": NATIVE_PARITY_SOURCE,
        "contract_parity": {
            "cpp": cpp_contract_parity,
            "rust": rust_contract_parity,
        },
        "standalone_runtime_ready": {
            "cpp": CPP_STANDALONE_RUNTIME_READY,
            "rust": RUST_STANDALONE_RUNTIME_READY,
        },
        "full_parity": {
            "cpp": cpp_contract_parity and CPP_STANDALONE_RUNTIME_READY,
            "rust": rust_contract_parity and RUST_STANDALONE_RUNTIME_READY,
        },
        "order_guard_behavior": {
            **ORDER_GUARD_BEHAVIOR,
            "live_only_requirements": list(ORDER_GUARD_BEHAVIOR["live_only_requirements"]),
        },
        "native_runtime_ownership": {
            "direct_exchanges": list(NATIVE_RUNTIME_OWNERSHIP["direct_exchanges"]),
            "direct_connector_backends": list(NATIVE_RUNTIME_OWNERSHIP["direct_connector_backends"]),
            "direct_market_families": list(NATIVE_RUNTIME_OWNERSHIP["direct_market_families"]),
            "indicator_source_market_families": [
                {"key": key, "value": value}
                for key, value in NATIVE_RUNTIME_OWNERSHIP["indicator_source_market_families"]
            ],
            "delegated_owner": str(NATIVE_RUNTIME_OWNERSHIP["delegated_owner"]),
        },
        "domains": [_domain_payload(domain) for domain in NATIVE_PARITY_DOMAINS],
        "service_api": {
            **service_api_contract_payload(),
            "route_suffixes": dict(SERVICE_API_ROUTE_SUFFIXES),
            "route_methods": route_methods,
            "backtest_run_request_fields": list(SERVICE_BACKTEST_RUN_REQUEST_FIELDS),
        },
        "ui_options": {
            "intervals": list(BACKTEST_INTERVAL_ORDER),
            "tradingview_interval_map": dict(TRADINGVIEW_INTERVAL_MAP),
            "default_chart_symbols": list(DEFAULT_CHART_SYMBOLS),
            "default_execution_symbols": list(execution_defaults.symbols),
            "default_execution_intervals": list(execution_defaults.intervals),
            "default_backtest_symbols": list(backtest_defaults.symbols),
            "default_backtest_intervals": list(backtest_defaults.intervals),
            "chart_market_options": list(CHART_MARKET_OPTIONS),
            "account_mode_options": list(ACCOUNT_MODE_OPTIONS),
            "config_mode_options": _value_option_payload(list(CONFIG_MODE_OPTIONS)),
            "theme_options": _value_option_payload(list(THEME_OPTIONS)),
            "design_options": _value_option_payload(list(DESIGN_OPTIONS)),
            "indicator_source_options": _value_option_payload(list(INDICATOR_SOURCE_OPTIONS)),
            "exchange_options": _exchange_payload(),
            "dashboard_loop_choices": _choice_payload(DASHBOARD_LOOP_CHOICES),
            "lead_trader_options": _choice_payload(LEAD_TRADER_OPTIONS),
            "llm_use_for_options": _choice_payload(LLM_USE_FOR_OPTIONS),
            "dashboard_strategy_templates": [
                {"key": key, "label": str(definition.get("label", key))}
                for key, definition in DASHBOARD_STRATEGY_TEMPLATE_DEFINITIONS.items()
            ],
            "side_options": _label_map_payload(SIDE_LABELS),
            "account_type_options": _canonical_choice_payload(_ACCOUNT_TYPE_CHOICES),
            "margin_mode_options": _canonical_choice_payload(_MARGIN_MODE_CHOICES),
            "position_mode_options": _canonical_choice_payload(_POSITION_MODE_CHOICES),
            "assets_mode_options": [
                {"key": "Single-Asset", "value": "Single-Asset", "label": "Single-Asset Mode"},
                {"key": "Multi-Assets", "value": "Multi-Assets", "label": "Multi-Assets Mode"},
            ],
            "order_type_options": _canonical_choice_payload(_ORDER_TYPE_CHOICES),
            "time_in_force_options": _canonical_choice_payload(_TIF_CHOICES),
            "signal_logic_options": _canonical_choice_payload(_LOGIC_CHOICES),
            "mdd_logic_options": _label_map_payload(MDD_LOGIC_LABELS),
            "stop_loss_modes": _label_map_payload(STOP_LOSS_MODE_LABELS),
            "stop_loss_scopes": _label_map_payload(STOP_LOSS_SCOPE_LABELS),
            "scan_scope_options": _canonical_choice_payload(_SCAN_SCOPE_CHOICES),
            "optimizer_mode_options": _canonical_choice_payload(_OPTIMIZER_MODE_CHOICES),
            "optimizer_metric_options": _canonical_choice_payload(_OPTIMIZER_METRIC_CHOICES),
            "backtest_execution_backend_options": _canonical_choice_payload(_BACKTEST_EXECUTION_BACKEND_CHOICES),
            "chart_view_options": _fixed_choice_payload(
                (
                    ("tradingview", "TradingView"),
                    ("original", "Original"),
                    ("lightweight", "TradingView Lightweight"),
                )
            ),
            "positions_view_options": _fixed_choice_payload(
                (
                    ("cumulative", "Cumulative View"),
                    ("per_trade", "Per Trade View"),
                )
            ),
            "chart_view_keys": list(dict.fromkeys(_CHART_VIEW_MODE_CHOICES.values())),
            "rust_environment_dependencies": _rust_environment_dependency_payload(),
            "connectors": connector_options,
            "backtest_templates": [
                {"key": key, "label": str(definition.get("label", key))}
                for key, definition in BACKTEST_TEMPLATE_DEFINITIONS.items()
            ],
            "indicators": _indicator_payload(),
        },
        "default_execution": execution_defaults.to_config_dict(),
        "default_backtest": backtest_defaults.to_config_dict(),
        "risk_defaults": risk_defaults,
        "ui_defaults": ui_defaults,
        "llm_providers": _llm_provider_payload(),
        "llm_provider_choices": dict(llm_provider_choices()),
        "llm_catalog": {
            "revision": LLM_PROVIDER_CATALOG_REVISION,
            "model_catalog_path_env": LLM_MODEL_CATALOG_PATH_ENV,
        },
        "config_choice_maps": _config_choice_maps(),
        "exchange_support": {
            "supported_exchanges": list(SUPPORTED_EXCHANGES),
            "supported_connector_backends": list(SUPPORTED_CONNECTOR_BACKENDS),
            "ccxt_diagnostic_exchanges": list(CCXT_DIAGNOSTIC_EXCHANGES),
            "ccxt_order_routing_exchanges": list(CCXT_ORDER_ROUTING_EXCHANGES),
            "order_execution_exchanges": list(ORDER_EXECUTION_EXCHANGES),
            "ccxt_exchange_ids": [{"key": key, "value": value} for key, value in CCXT_EXCHANGE_IDS.items()],
            "supported_brokers": list(SUPPORTED_BROKERS),
            "supported_forex_brokers": list(SUPPORTED_FOREX_BROKERS),
            "broker_order_routing_backends": broker_backends,
            "broker_canonical_names": _broker_canonical_name_payload(),
        },
        "position_reconciliation_reference": {
            "schema_version": NATIVE_POSITION_RECONCILIATION_REFERENCE_SCHEMA_VERSION,
            "cases": native_position_reconciliation_reference_cases(),
        },
    }


def native_python_source_contract_json() -> str:
    return json.dumps(
        native_python_source_contract_payload(),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def native_python_source_contract_hash() -> str:
    return sha256(native_python_source_contract_json().encode("utf-8")).hexdigest()


def native_python_source_contract_summary() -> dict[str, object]:
    payload = native_python_source_contract_payload()
    service_routes = [
        {
            "name": name,
            "path": SERVICE_API_ROUTE_PATHS[name],
            "methods": list(SERVICE_API_ROUTE_METHODS[name]),
        }
        for name in SERVICE_API_ROUTE_SUFFIXES
    ]
    route_schemas = payload["service_api"]["route_schemas"]
    service_route_schemas = [
        {
            "name": name,
            "query_fields": list(route_schemas[name]["query_fields"]),
            "request_fields": list(route_schemas[name]["request_fields"]),
            "response_fields": list(route_schemas[name]["response_fields"]),
        }
        for name in SERVICE_API_ROUTE_SUFFIXES
    ]
    return {
        "schema_version": payload["schema_version"],
        "source": payload["source"],
        "contract_hash": native_python_source_contract_hash(),
        "order_guard_behavior": dict(payload["order_guard_behavior"]),
        "native_runtime_ownership": dict(payload["native_runtime_ownership"]),
        "domains": list(payload["domains"]),
        "domain_keys": [domain["key"] for domain in payload["domains"]],
        "route_names": list(SERVICE_API_ROUTE_SUFFIXES),
        "service_routes": service_routes,
        "service_route_schemas": service_route_schemas,
        "backtest_run_request_fields": list(SERVICE_BACKTEST_RUN_REQUEST_FIELDS),
        "indicators": list(payload["ui_options"]["indicators"]),
        "indicator_keys": [definition.key for definition in INDICATOR_CATALOG],
        "connectors": list(payload["ui_options"]["connectors"]),
        "llm_providers": list(payload["llm_providers"]),
        "llm_provider_keys": [provider.key for provider in _PROVIDER_SPECS],
        "llm_catalog_revision": str(payload["llm_catalog"]["revision"]),
        "llm_model_catalog_path_env": str(payload["llm_catalog"]["model_catalog_path_env"]),
        "llm_provider_choices": [
            {"key": key, "value": value}
            for key, value in payload["llm_provider_choices"].items()
        ],
        "config_choice_maps": {
            name: dict(values) for name, values in payload["config_choice_maps"].items()
        },
        "connector_keys": [key for _label, key in _connector_options()],
        "supported_exchanges": list(payload["exchange_support"]["supported_exchanges"]),
        "supported_connector_backends": list(payload["exchange_support"]["supported_connector_backends"]),
        "ccxt_diagnostic_exchanges": list(payload["exchange_support"]["ccxt_diagnostic_exchanges"]),
        "ccxt_order_routing_exchanges": list(payload["exchange_support"]["ccxt_order_routing_exchanges"]),
        "order_execution_exchanges": list(payload["exchange_support"]["order_execution_exchanges"]),
        "ccxt_exchange_ids": list(payload["exchange_support"]["ccxt_exchange_ids"]),
        "supported_brokers": list(payload["exchange_support"]["supported_brokers"]),
        "supported_forex_brokers": list(payload["exchange_support"]["supported_forex_brokers"]),
        "broker_order_routing_backends": list(payload["exchange_support"]["broker_order_routing_backends"]),
        "broker_canonical_names": list(payload["exchange_support"]["broker_canonical_names"]),
        "intervals": list(BACKTEST_INTERVAL_ORDER),
        "tradingview_interval_map": dict(payload["ui_options"]["tradingview_interval_map"]),
        "default_chart_symbols": list(payload["ui_options"]["default_chart_symbols"]),
        "default_execution_symbols": list(payload["ui_options"]["default_execution_symbols"]),
        "default_execution_intervals": list(payload["ui_options"]["default_execution_intervals"]),
        "default_backtest_symbols": list(payload["ui_options"]["default_backtest_symbols"]),
        "default_backtest_intervals": list(payload["ui_options"]["default_backtest_intervals"]),
        "chart_market_options": list(payload["ui_options"]["chart_market_options"]),
        "account_mode_options": list(payload["ui_options"]["account_mode_options"]),
        "config_mode_options": list(payload["ui_options"]["config_mode_options"]),
        "theme_options": list(payload["ui_options"]["theme_options"]),
        "design_options": list(payload["ui_options"]["design_options"]),
        "indicator_source_options": list(payload["ui_options"]["indicator_source_options"]),
        "exchange_options": list(payload["ui_options"]["exchange_options"]),
        "dashboard_loop_choices": list(payload["ui_options"]["dashboard_loop_choices"]),
        "lead_trader_options": list(payload["ui_options"]["lead_trader_options"]),
        "llm_use_for_options": list(payload["ui_options"]["llm_use_for_options"]),
        "dashboard_strategy_templates": list(payload["ui_options"]["dashboard_strategy_templates"]),
        "side_options": list(payload["ui_options"]["side_options"]),
        "account_type_options": list(payload["ui_options"]["account_type_options"]),
        "margin_mode_options": list(payload["ui_options"]["margin_mode_options"]),
        "position_mode_options": list(payload["ui_options"]["position_mode_options"]),
        "assets_mode_options": list(payload["ui_options"]["assets_mode_options"]),
        "order_type_options": list(payload["ui_options"]["order_type_options"]),
        "time_in_force_options": list(payload["ui_options"]["time_in_force_options"]),
        "signal_logic_options": list(payload["ui_options"]["signal_logic_options"]),
        "mdd_logic_options": list(payload["ui_options"]["mdd_logic_options"]),
        "stop_loss_modes": list(payload["ui_options"]["stop_loss_modes"]),
        "stop_loss_scopes": list(payload["ui_options"]["stop_loss_scopes"]),
        "scan_scope_options": list(payload["ui_options"]["scan_scope_options"]),
        "optimizer_mode_options": list(payload["ui_options"]["optimizer_mode_options"]),
        "optimizer_metric_options": list(payload["ui_options"]["optimizer_metric_options"]),
        "backtest_execution_backend_options": list(payload["ui_options"]["backtest_execution_backend_options"]),
        "chart_view_options": list(payload["ui_options"]["chart_view_options"]),
        "positions_view_options": list(payload["ui_options"]["positions_view_options"]),
        "chart_view_keys": list(payload["ui_options"]["chart_view_keys"]),
        "rust_environment_dependencies": list(payload["ui_options"]["rust_environment_dependencies"]),
        "backtest_templates": list(payload["ui_options"]["backtest_templates"]),
        "default_execution": dict(payload["default_execution"]),
        "default_backtest": dict(payload["default_backtest"]),
        "risk_defaults": dict(payload["risk_defaults"]),
        "ui_defaults": dict(payload["ui_defaults"]),
        "cpp_contract_parity": payload["contract_parity"]["cpp"],
        "rust_contract_parity": payload["contract_parity"]["rust"],
        "cpp_standalone_runtime_ready": payload["standalone_runtime_ready"]["cpp"],
        "rust_standalone_runtime_ready": payload["standalone_runtime_ready"]["rust"],
        "cpp_full_parity": payload["full_parity"]["cpp"],
        "rust_full_parity": payload["full_parity"]["rust"],
    }
