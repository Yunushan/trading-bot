from __future__ import annotations

import copy
import os
import sys
import time
from pathlib import Path

from PyQt6 import QtCore, QtWidgets

from app.config import (
    BACKTEST_TEMPLATE_DEFAULT,
    DEFAULT_CONFIG,
    MDD_LOGIC_DEFAULT,
    MDD_LOGIC_OPTIONS,
    coerce_bool,
    normalize_stop_loss_dict,
)
from app.core.positions import IntervalPositionGuard
from app.gui.backtest.backtest_templates import BACKTEST_TEMPLATE_DEFINITIONS
from app.gui.code.code_language_catalog import EXCHANGE_PATHS, FOREX_BROKER_PATHS, LANGUAGE_PATHS

_APP_STATE_PATH = Path.home() / ".trading_bot_state.json"
_LEGACY_APP_STATE_PATH = Path.home() / ".binance_trading_bot_state.json"
_LOAD_APP_STATE_FILE = lambda path: {}
_NORMALIZE_CONNECTOR_BACKEND = lambda value: value
_DEFAULT_CONNECTOR_BACKEND = ""
_CHART_MARKET_OPTIONS = ["Futures", "Spot"]
_DISABLE_TRADINGVIEW = False
_DISABLE_CHARTS = False
_ENABLE_CHART_TAB = True
_TRADINGVIEW_SUPPORTED = lambda: False


def configure_main_window_state_init_runtime(
    *,
    app_state_path,
    legacy_app_state_path=None,
    load_app_state_file,
    normalize_connector_backend,
    default_connector_backend,
    chart_market_options,
    disable_tradingview,
    disable_charts,
    enable_chart_tab,
    tradingview_supported,
) -> None:
    global _APP_STATE_PATH
    global _LEGACY_APP_STATE_PATH
    global _LOAD_APP_STATE_FILE
    global _NORMALIZE_CONNECTOR_BACKEND
    global _DEFAULT_CONNECTOR_BACKEND
    global _CHART_MARKET_OPTIONS
    global _DISABLE_TRADINGVIEW
    global _DISABLE_CHARTS
    global _ENABLE_CHART_TAB
    global _TRADINGVIEW_SUPPORTED

    _APP_STATE_PATH = app_state_path
    _LEGACY_APP_STATE_PATH = legacy_app_state_path or _LEGACY_APP_STATE_PATH
    _LOAD_APP_STATE_FILE = load_app_state_file
    _NORMALIZE_CONNECTOR_BACKEND = normalize_connector_backend
    _DEFAULT_CONNECTOR_BACKEND = default_connector_backend
    _CHART_MARKET_OPTIONS = list(chart_market_options or ["Futures", "Spot"])
    _DISABLE_TRADINGVIEW = bool(disable_tradingview)
    _DISABLE_CHARTS = bool(disable_charts)
    _ENABLE_CHART_TAB = bool(enable_chart_tab)
    _TRADINGVIEW_SUPPORTED = tradingview_supported


def _initialize_main_window_state(self) -> None:
    self._state_path = _APP_STATE_PATH
    load_path = _resolve_app_state_load_path(self._state_path)
    self._app_state = _LOAD_APP_STATE_FILE(load_path)
    self._previous_session_unclosed = bool(self._app_state.get("session_active", False))
    self._session_marker_active = False
    self._auto_close_on_restart_triggered = False
    self._ui_initialized = False
    self.guard = IntervalPositionGuard(stale_ttl_sec=90, strict_symbol_side=False)

    _initialize_config_state(self)
    _initialize_chart_state(self)
    _initialize_backtest_state(self)
    _initialize_runtime_state(self)
    try:
        self._initialize_desktop_service_bridge()
    except Exception:
        pass

    self._ensure_runtime_connector_for_account(self.config.get("account_type") or "Futures", force_default=False)
    self._override_debug_verbose = bool(self.config.get("debug_override_verbose", False))
    self.init_ui()
    try:
        self._maybe_start_desktop_service_api_host()
    except Exception:
        pass
    try:
        self._refresh_desktop_service_api_ui()
    except Exception:
        pass

    if self._open_code_tab_on_start:
        try:
            tabs = getattr(self, "tabs", None)
            code_tab = getattr(self, "code_tab", None)
            if tabs is not None and code_tab is not None:
                idx = tabs.indexOf(code_tab)
                if idx >= 0:
                    tabs.setCurrentIndex(idx)
        except Exception:
            pass

    try:
        tabs = getattr(self, "tabs", None)
        if tabs is not None and tabs.count() > 0:
            tabs.setCurrentIndex(0)
    except Exception:
        pass

    self.log_signal.connect(self._buffer_log)
    self.trade_signal.connect(self._on_trade_signal)
    try:
        self._schedule_webengine_runtime_prewarm()
    except Exception:
        pass
    QtCore.QTimer.singleShot(250, self._handle_post_init_state)
    QtCore.QTimer.singleShot(50, self._update_connector_labels)


def _resolve_app_state_load_path(preferred_path: Path) -> Path:
    if preferred_path.is_file():
        return preferred_path
    legacy_path = _LEGACY_APP_STATE_PATH
    if legacy_path and legacy_path != preferred_path and legacy_path.is_file():
        return legacy_path
    return preferred_path


def _initialize_config_state(self) -> None:
    self.config = copy.deepcopy(DEFAULT_CONFIG)
    self.config["stop_loss"] = normalize_stop_loss_dict(self.config.get("stop_loss"))
    self.config.setdefault("theme", "Dark")
    self.config["close_on_exit"] = False
    self.config.setdefault("close_on_exit", False)
    self.config["allow_opposite_positions"] = coerce_bool(
        self.config.get("allow_opposite_positions", True),
        True,
    )
    self.config.setdefault("account_mode", "Classic Trading")
    self.config.setdefault("auto_bump_percent_multiplier", DEFAULT_CONFIG.get("auto_bump_percent_multiplier", 10.0))
    self.config["connector_backend"] = _NORMALIZE_CONNECTOR_BACKEND(self.config.get("connector_backend"))
    self.config.setdefault("positions_auto_resize_rows", True)
    self.config.setdefault("positions_auto_resize_columns", True)
    self.config.setdefault("code_language", next(iter(LANGUAGE_PATHS)))
    self.config.setdefault("selected_rust_framework", "")
    self.config.setdefault("selected_exchange", next(iter(EXCHANGE_PATHS)))
    if FOREX_BROKER_PATHS:
        self.config.setdefault("selected_forex_broker", next(iter(FOREX_BROKER_PATHS)))
    else:
        self.config.setdefault("selected_forex_broker", None)
    self.config.setdefault("code_market", "crypto")

    exchange_override = os.environ.get("BOT_SELECTED_EXCHANGE") or os.environ.get("BOT_DEFAULT_EXCHANGE")
    if exchange_override:
        exchange_override = str(exchange_override).strip()
        for key in EXCHANGE_PATHS:
            if key.lower() == exchange_override.lower():
                self.config["selected_exchange"] = key
                self.config["code_market"] = "crypto"
                self.config["selected_forex_broker"] = None
                break


def _initialize_chart_state(self) -> None:
    self.strategy_threads = {}
    self.shared_binance = None
    self.stop_worker = None
    self.indicator_widgets = {}
    self.traded_symbols = set()
    self._chart_pending_initial_load = True
    self._chart_needs_render = True
    self.config.setdefault("chart", {})
    if not isinstance(self.config.get("chart"), dict):
        self.config["chart"] = {}
    self.chart_config = self.config["chart"]
    try:
        self.chart_config.pop("follow_dashboard", None)
    except Exception:
        pass
    self.chart_config.setdefault("auto_follow", True)
    self.chart_auto_follow = bool(self.chart_config.get("auto_follow", True))
    self._chart_manual_override = False
    self._chart_updating = False
    self._pending_tradingview_mode = False
    self._pending_tradingview_switch = False
    self._pending_webengine_mode = None
    self._tradingview_ready_connected = False
    self._chart_switch_overlay = None
    self._chart_switch_overlay_active = False
    self._chart_view_stack_event_filter_installed = False
    self._tradingview_first_switch_done = False
    self._tradingview_prewarm_scheduled = False
    self._tradingview_prewarmed = False
    self._tv_window_suppress_active = False
    self._tv_window_suppress_timer = None
    self._tv_visibility_guard_active = False
    self._tv_visibility_guard_timer = None
    self._tv_close_guard_until = 0.0
    self._tv_close_guard_active = False
    self._webengine_close_guard_until = 0.0
    self._webengine_close_guard_active = False
    self._webengine_visibility_watchdog_active = False
    self._webengine_visibility_watchdog_timer = None
    self._webengine_runtime_prewarmed = False
    self._webengine_runtime_prewarm_view = None
    self._last_user_close_command_ts = 0.0
    self._spontaneous_close_block_until = 0.0
    self._tv_visibility_watchdog_active = False
    self._tv_visibility_watchdog_timer = None
    self._tradingview_external_last_open_ts = 0.0
    self._chart_debug_log_path = Path(os.getenv("TEMP") or ".").resolve() / "binance_chart_debug.log"
    self.chart_enabled = _ENABLE_CHART_TAB and not _DISABLE_CHARTS
    self._chart_worker = None
    self._chart_theme_signal_installed = False

    default_symbols = self.config.get("symbols") or ["BTCUSDT"]
    default_intervals = self.config.get("intervals") or ["1h"]
    self.chart_symbol_cache = {opt: [] for opt in _CHART_MARKET_OPTIONS}
    self._chart_symbol_alias_map = {}
    self._chart_symbol_loading = set()
    default_market = self.config.get("account_type", "Futures")
    if not default_market or default_market not in _CHART_MARKET_OPTIONS:
        default_market = "Futures"
    self.chart_config.setdefault("market", default_market)

    initial_symbols_norm = [str(sym).strip().upper() for sym in (default_symbols or []) if str(sym).strip()]
    dedup: list[str] = []
    if initial_symbols_norm:
        seen = set()
        for sym in initial_symbols_norm:
            if sym not in seen:
                seen.add(sym)
                dedup.append(sym)
    self.chart_symbol_cache["Futures"] = dedup

    default_symbol = default_symbols[0] if default_symbols else "BTCUSDT"
    if default_market == "Futures":
        default_symbol = self._futures_display_symbol(default_symbol)
    self.chart_config.setdefault("symbol", default_symbol)
    self.chart_config.setdefault("interval", (default_intervals[0] if default_intervals else "1h"))

    default_view_mode = "original"
    if sys.platform != "win32" and _TRADINGVIEW_SUPPORTED() and not _DISABLE_TRADINGVIEW and not _DISABLE_CHARTS:
        default_view_mode = "tradingview"
    self.chart_config.setdefault("view_mode", default_view_mode)
    try:
        if self._normalize_chart_market(self.chart_config.get("market")) == "Futures":
            current_cfg_symbol = str(self.chart_config.get("symbol") or "").strip()
            if current_cfg_symbol and not current_cfg_symbol.endswith(".P"):
                self.chart_config["symbol"] = self._futures_display_symbol(current_cfg_symbol)
    except Exception:
        pass


def _initialize_backtest_state(self) -> None:
    self._indicator_runtime_controls = []
    self._runtime_lock_widgets = []
    self._runtime_active_exemptions = set()
    self._dep_version_refresh_inflight = False
    self._dep_version_refresh_pending = False
    self._dep_version_auto_refresh_done = False
    self._dep_usage_last_state: dict[str, str] = {}
    self._dep_usage_change_counts: dict[str, int] = {}
    self.backtest_indicator_widgets = {}
    self.backtest_results = []
    self.backtest_worker = None
    self.backtest_scan_worker = None
    self._backtest_symbol_worker = None
    self.backtest_symbols_all = []
    self._backtest_wrappers = {}
    self._backtest_pending_symbol_selection: dict | None = None
    self.backtest_config = copy.deepcopy(self.config.get("backtest", {}))
    if not self.backtest_config:
        self.backtest_config = copy.deepcopy(DEFAULT_CONFIG.get("backtest", {}))
    else:
        self.backtest_config = copy.deepcopy(self.backtest_config)
    if not self.backtest_config.get("indicators"):
        self.backtest_config["indicators"] = copy.deepcopy(DEFAULT_CONFIG["backtest"]["indicators"])

    default_backtest = DEFAULT_CONFIG.get("backtest", {}) or {}
    self.backtest_config.setdefault("symbol_source", default_backtest.get("symbol_source", "Futures"))
    self.backtest_config.setdefault("capital", float(default_backtest.get("capital", 1000.0)))
    self.backtest_config.setdefault("logic", default_backtest.get("logic", "AND"))
    self.backtest_config.setdefault("start_date", default_backtest.get("start_date"))
    self.backtest_config.setdefault("end_date", default_backtest.get("end_date"))
    self.backtest_config.setdefault("symbols", list(default_backtest.get("symbols", [])))
    self.backtest_config.setdefault("intervals", list(default_backtest.get("intervals", [])))
    self.backtest_config.setdefault("position_pct", float(default_backtest.get("position_pct", 2.0)))
    self.backtest_config.setdefault("side", default_backtest.get("side", "BOTH"))
    self.backtest_config.setdefault("margin_mode", default_backtest.get("margin_mode", "Isolated"))
    self.backtest_config.setdefault("position_mode", default_backtest.get("position_mode", "Hedge"))
    self.backtest_config.setdefault("assets_mode", default_backtest.get("assets_mode", "Single-Asset"))
    self.backtest_config.setdefault("account_mode", default_backtest.get("account_mode", "Classic Trading"))
    self.backtest_config.setdefault(
        "connector_backend",
        DEFAULT_CONFIG.get("backtest", {}).get("connector_backend", _DEFAULT_CONNECTOR_BACKEND),
    )
    self.backtest_config["connector_backend"] = _NORMALIZE_CONNECTOR_BACKEND(
        self.backtest_config.get("connector_backend")
    )
    self.config.setdefault("backtest", {})["connector_backend"] = self.backtest_config["connector_backend"]
    self.backtest_config.setdefault("leverage", int(default_backtest.get("leverage", 5)))

    mdd_logic_cfg = str(
        self.backtest_config.get("mdd_logic") or default_backtest.get("mdd_logic") or MDD_LOGIC_DEFAULT
    ).lower()
    if mdd_logic_cfg not in MDD_LOGIC_OPTIONS:
        mdd_logic_cfg = MDD_LOGIC_DEFAULT
    self.backtest_config["mdd_logic"] = mdd_logic_cfg
    self.config.setdefault("backtest", {})["mdd_logic"] = mdd_logic_cfg

    template_cfg_bt = self.backtest_config.get("template")
    if not isinstance(template_cfg_bt, dict):
        template_cfg_bt = copy.deepcopy(BACKTEST_TEMPLATE_DEFAULT)
    template_enabled = bool(template_cfg_bt.get("enabled", False))
    template_name = template_cfg_bt.get("name")
    if template_name not in BACKTEST_TEMPLATE_DEFINITIONS:
        template_name = next(iter(BACKTEST_TEMPLATE_DEFINITIONS)) if BACKTEST_TEMPLATE_DEFINITIONS else None
    self.backtest_config["template"] = {
        "enabled": template_enabled,
        "name": template_name,
    }
    self.config.setdefault("backtest", {})["template"] = copy.deepcopy(self.backtest_config["template"])
    self.backtest_config.setdefault(
        "backtest_symbol_interval_pairs",
        list(self.config.get("backtest_symbol_interval_pairs", [])),
    )
    default_stop_loss = normalize_stop_loss_dict(default_backtest.get("stop_loss"))
    self.backtest_config["stop_loss"] = normalize_stop_loss_dict(
        self.backtest_config.get("stop_loss", default_stop_loss)
    )
    self.config.setdefault("backtest", {})["stop_loss"] = copy.deepcopy(self.backtest_config["stop_loss"])
    self._backtest_futures_widgets = []


def _initialize_runtime_state(self) -> None:
    self.config.setdefault("runtime_symbol_interval_pairs", [])
    self.config.setdefault("backtest_symbol_interval_pairs", [])
    self.config.setdefault("debug_override_verbose", False)
    self._override_refresh_depth = 0
    self.symbol_interval_table = None
    self.pair_add_btn = None
    self.pair_remove_btn = None
    self.pair_clear_btn = None
    self.backtest_run_btn = None
    self.backtest_stop_btn = None
    self.override_contexts = {}
    self.bot_status_label_tab1 = None
    self.bot_status_label_tab2 = None
    self.bot_status_label_tab3 = None
    self.bot_status_label_chart = None
    self.bot_status_label_code_tab = None
    self.pnl_active_label_tab1 = None
    self.pnl_closed_label_tab1 = None
    self.pnl_active_label_tab2 = None
    self.pnl_closed_label_tab2 = None
    self.pnl_active_label_tab3 = None
    self.pnl_closed_label_tab3 = None
    self.pnl_active_label_chart = None
    self.pnl_closed_label_chart = None
    self.pnl_active_label_code_tab = None
    self.pnl_closed_label_code_tab = None
    self.bot_time_label_tab1 = None
    self.bot_time_label_tab2 = None
    self.bot_time_label_tab3 = None
    self.bot_time_label_chart = None
    self.bot_time_label_code_tab = None
    self.code_tab = None
    self.liquidation_tab = None
    self.liquidation_tabs = None
    self._bot_active = False
    self._bot_active_since = None
    self._bot_time_timer = None
    self._pnl_label_sets: list[tuple[QtWidgets.QLabel | None, QtWidgets.QLabel | None]] = []
    self._last_pnl_snapshot = {
        "active": {"pnl": None},
        "closed": {"pnl": None},
    }
    self._processed_close_events: set[str] = set()
    self._closed_trade_registry: dict[str, dict[str, float | None]] = {}
    self.language_combo = None
    self.exchange_combo = None
    self.forex_combo = None
    self.exchange_list = None
    self._exchange_list_items = {}
    self._starter_language_cards = {}
    self._starter_rust_framework_cards = {}
    self._starter_market_cards = {}
    self._starter_crypto_cards = {}
    self._starter_forex_cards = {}
    self._webengine_runtime_prewarm_scheduled = False
    self._rust_code_tab_process = None
    self._rust_process_watchdog_timer = None
    self._rust_auto_install_inflight = False
    self._rust_auto_install_last_attempt_at = 0.0
    self._rust_auto_install_last_completed_at = 0.0
    self._code_tab_selected_market = self.config.get("code_market") or "crypto"
    self._open_code_tab_on_start = str(os.environ.get("BOT_OPEN_CODE_TAB", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    self._desktop_service_api_enabled_pref = False
    self._desktop_service_api_host_pref = "127.0.0.1"
    self._desktop_service_api_port_pref = 8000
    self._desktop_service_api_token_pref = str(os.environ.get("BOT_SERVICE_API_TOKEN") or "").strip()
    self._desktop_service_api_host_status = None
    try:
        self._initialize_desktop_service_api_preferences()
    except Exception:
        pass
