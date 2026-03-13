from __future__ import annotations

import copy
import hashlib
import os
import sys
import json
import math
import platform
import re
import shutil
import subprocess
import threading
import time
import tempfile
import traceback
import types
import concurrent.futures
import importlib
import importlib.metadata as importlib_metadata
import urllib.request
import zipfile
import pandas as pd
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from PyQt6 import QtCore, QtGui, QtWidgets
try:
    from PyQt6.QtCharts import (
        QChart,
        QChartView,
        QCandlestickSeries,
        QCandlestickSet,
        QDateTimeAxis,
        QValueAxis,
    )
    QT_CHARTS_AVAILABLE = True
except Exception:
    QT_CHARTS_AVAILABLE = False
    QChart = QChartView = QCandlestickSeries = QCandlestickSet = QDateTimeAxis = QValueAxis = None
from PyQt6.QtCore import pyqtSignal

ENABLE_CHART_TAB = True

_THIS_FILE = Path(__file__).resolve()

if __package__ in (None, ""):
    import sys
    sys.path.append(str(_THIS_FILE.parents[2]))

from app.config import (
    DEFAULT_CONFIG,
    INDICATOR_DISPLAY_NAMES,
    MDD_LOGIC_DEFAULT,
    MDD_LOGIC_OPTIONS,
    STOP_LOSS_MODE_ORDER,
    STOP_LOSS_SCOPE_OPTIONS,
    BACKTEST_TEMPLATE_DEFAULT,
    normalize_stop_loss_dict,
    coerce_bool,
)
from app.binance_wrapper import BinanceWrapper, normalize_margin_ratio
from app.backtester import BacktestEngine, BacktestRequest, IndicatorDefinition
from app.strategy import StrategyEngine
from app.workers import StopWorker, StartWorker, CallWorker
from app.position_guard import IntervalPositionGuard
from app.gui.param_dialog import ParamDialog
from app.gui import allocation_persistence
from app.gui.backtest_templates import BACKTEST_TEMPLATE_DEFINITIONS
from app.gui.chart_widgets import InteractiveChartView, SimpleCandlestickWidget
from app.gui import (
    chart_embed,
    code_language_build,
    main_window_account_runtime,
    main_window_backtest_runtime,
    main_window_backtest_execution_runtime,
    main_window_backtest_results_runtime,
    main_window_backtest_state_runtime,
    main_window_backtest_template_runtime,
    main_window_backtest_tab,
    main_window_backtest_bridge_runtime,
    main_window_dashboard_actions_runtime,
    main_window_dashboard_chart_runtime,
    main_window_dashboard_header_runtime,
    main_window_dashboard_indicator_runtime,
    main_window_dashboard_log_runtime,
    main_window_dashboard_markets_runtime,
    main_window_dashboard_state_runtime,
    main_window_dashboard_strategy_runtime,
    main_window_init_finalize_runtime,
    main_window_secondary_tabs_runtime,
    main_window_chart_display_runtime,
    main_window_chart_host_runtime,
    main_window_chart_tab,
    main_window_chart_selection_runtime,
    main_window_chart_view_runtime,
    main_window_positions_tab,
    main_window_tab_runtime,
    main_window_control_runtime,
    main_window_code,
    main_window_balance_runtime,
    main_window_code_runtime,
    main_window_helper_runtime,
    main_window_indicator_runtime,
    main_window_margin_runtime,
    main_window_theme_runtime,
    main_window_trade_runtime,
    main_window_ui_support,
    main_window_strategy_context_runtime,
    main_window_web_embed,
    dependency_versions_runtime,
    code_language_launch,
    code_language_launcher,
    code_language_runtime,
    code_language_status,
    code_language_ui,
    dependency_versions_ui,
    main_window_config,
    main_window_positions,
    main_window_positions_worker,
    main_window_runtime,
    window_runtime,
)
from app.gui.main_window_config import _load_app_state_file, _save_app_state_file
from app.gui.chart_embed import (
    _DEFAULT_WEB_UA,
    _binance_unavailable_reason,
    _chart_safe_mode_enabled,
    _configure_tradingview_webengine_env,
    _lightweight_unavailable_reason,
    _load_tradingview_widget,
    _native_chart_host_prewarm_enabled,
    _tradingview_external_preferred,
    _tradingview_supported,
    _tradingview_unavailable_reason,
    _webengine_charts_allowed,
    _webengine_embed_unavailable_reason,
)
from app.gui.code_language_catalog import (
    BASE_PROJECT_PATH as _BASE_PROJECT_PATH,
    CPP_BUILD_ROOT,
    CPP_CACHE_META_FILE,
    CPP_CODE_LANGUAGE_KEY,
    CPP_DEPENDENCY_VERSION_TARGETS as _CPP_DEPENDENCY_VERSION_TARGETS,
    CPP_EXECUTABLE_BASENAME,
    CPP_EXECUTABLE_LEGACY_BASENAME,
    CPP_PACKAGED_EXECUTABLE_BASENAME,
    CPP_PROJECT_PATH,
    CPP_RELEASE_CPP_ASSET,
    CPP_RELEASE_OWNER,
    CPP_RELEASE_REPO,
    CPP_SUPPORTED_EXCHANGE_KEY,
    DEFAULT_DEPENDENCY_VERSION_TARGETS as _DEFAULT_DEPENDENCY_VERSION_TARGETS,
    EXCHANGE_PATHS,
    FOREX_BROKER_PATHS,
    LANGUAGE_PATHS,
    PYTHON_CODE_LANGUAGE_KEY,
    RELEASE_INFO_JSON_NAME,
    RELEASE_TAG_TEXT_NAME,
    REQUIREMENTS_PATHS as _REQUIREMENTS_PATHS,
    RUST_CODE_LANGUAGE_KEY,
    RUST_FRAMEWORK_PACKAGES,
    RUST_PROJECT_PATH,
    STARTER_CRYPTO_EXCHANGES,
    STARTER_FOREX_BROKERS,
    STARTER_MARKET_OPTIONS,
    _rust_dependency_targets_for_config,
    _rust_framework_key,
    _rust_framework_option,
    _rust_framework_path,
    _rust_framework_title,
)
from app.indicators import (
    rsi as rsi_indicator,
    stoch_rsi as stoch_rsi_indicator,
    williams_r as williams_r_indicator,
    sma as sma_indicator,
    ema as ema_indicator,
    donchian_high as donchian_high_indicator,
    donchian_low as donchian_low_indicator,
    bollinger_bands as bollinger_bands_indicator,
    parabolic_sar as psar_indicator,
    macd as macd_indicator,
    ultimate_oscillator as uo_indicator,
    adx as adx_indicator,
    dmi as dmi_indicator,
    supertrend as supertrend_indicator,
    stochastic as stochastic_indicator,
)

_allow_guard_bypass = main_window_runtime._allow_guard_bypass
_restore_window_after_guard = main_window_runtime._restore_window_after_guard
_mw_interval_sort_key = main_window_runtime._mw_interval_sort_key
_is_trigger_log_line = main_window_runtime._is_trigger_log_line
_mw_positions_records_cumulative = main_window_positions._mw_positions_records_cumulative
_apply_window_icon = main_window_ui_support._apply_window_icon
_NumericItem = main_window_ui_support._NumericItem
_StarterCard = main_window_ui_support._StarterCard
_BacktestWorker = main_window_backtest_runtime._BacktestWorker
_LazyWebEmbed = main_window_web_embed._LazyWebEmbed
_PositionsWorker = main_window_positions_worker._PositionsWorker

BINANCE_SUPPORTED_INTERVALS = {
    "1m", "3m", "5m", "15m", "30m",
    "1h", "2h", "4h", "6h", "8h", "12h",
    "1d", "3d", "1w", "1M",
}
BINANCE_INTERVAL_LOWER = {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w"}

BACKTEST_INTERVAL_ORDER = [
    "1m", "3m", "5m", "10m", "15m", "20m", "30m",
    "1h", "2h", "3h", "4h", "5h", "6h", "7h", "8h", "9h", "10h", "11h", "12h",
    "1d", "2d", "3d", "4d", "5d", "6d",
    "1w", "2w", "3w",
    "1month", "2months", "3months", "6months",
    "1mo", "2mo", "3mo", "6mo",
    "1y", "2y"
]

MAX_CLOSED_HISTORY = 200

APP_STATE_PATH = Path.home() / ".binance_trading_bot_state.json"

TRADINGVIEW_SYMBOL_PREFIX = "BINANCE:"
TRADINGVIEW_INTERVAL_MAP = {
    "1m": "1",
    "3m": "3",
    "5m": "5",
    "10m": "10",
    "15m": "15",
    "20m": "20",
    "30m": "30",
    "45m": "45",
    "1h": "60",
    "2h": "120",
    "3h": "180",
    "4h": "240",
    "5h": "300",
    "6h": "360",
    "7h": "420",
    "8h": "480",
    "9h": "540",
    "10h": "600",
    "11h": "660",
    "12h": "720",
    "1d": "1D",
    "2d": "2D",
    "3d": "3D",
    "4d": "4D",
    "5d": "5D",
    "6d": "6D",
    "1w": "1W",
    "2w": "2W",
    "3w": "3W",
    "1mo": "1M",
    "2mo": "2M",
    "3mo": "3M",
    "6mo": "6M",
    "1month": "1M",
    "2months": "2M",
    "3months": "3M",
    "6months": "6M",
    "1y": "12M",
    "2y": "24M",
}

STOP_LOSS_MODE_LABELS = {
    "usdt": "USDT Based Stop Loss",
    "percent": "Percentage Based Stop Loss",
    "both": "Both Stop Loss (USDT & Percentage)",
}

STOP_LOSS_SCOPE_LABELS = {
    "per_trade": "Per Trade Stop Loss",
    "cumulative": "Cumulative Stop Loss",
    "entire_account": "Entire Account Stop Loss",
}

DASHBOARD_LOOP_CHOICES = [
    ("30 seconds", "30s"),
    ("45 seconds", "45s"),
    ("1 minute", "1m"),
    ("2 minutes", "2m"),
    ("3 minutes", "3m"),
    ("5 minutes", "5m"),
    ("10 minutes", "10m"),
    ("30 minutes", "30m"),
    ("1 hour", "1h"),
    ("2 hours", "2h"),
]

LEAD_TRADER_OPTIONS = [
    ("Futures Public Lead Trader", "futures_public"),
    ("Futures Private Lead Trader", "futures_private"),
    ("Spot Public Lead Trader", "spot_public"),
    ("Spot Private Lead Trader", "spot_private"),
]

MDD_LOGIC_LABELS = {
    "per_trade": "Per Trade MDD",
    "cumulative": "Cumulative MDD",
    "entire_account": "Entire Account MDD",
}

CONNECTOR_OPTIONS = [
    ("Binance SDK Derivatives Trading USDⓈ Futures (Official Recommended)", "binance-sdk-derivatives-trading-usds-futures"),
    ("Binance SDK Derivatives Trading COIN-M Futures", "binance-sdk-derivatives-trading-coin-futures"),
    ("Binance SDK Spot (Official Recommended)", "binance-sdk-spot"),
    ("Binance Connector Python", "binance-connector"),
    ("CCXT (Unified)", "ccxt"),
    ("python-binance (Community)", "python-binance"),
]
DEFAULT_CONNECTOR_BACKEND = CONNECTOR_OPTIONS[0][1]

FUTURES_CONNECTOR_KEYS = {
    "binance-sdk-derivatives-trading-usds-futures",
    "binance-sdk-derivatives-trading-coin-futures",
    "binance-connector",
    "ccxt",
    "python-binance",
}

SPOT_CONNECTOR_KEYS = {
    "binance-sdk-spot",
    "binance-connector",
    "ccxt",
    "python-binance",
}
main_window_helper_runtime.bind_main_window_helper_runtime(
    default_connector_backend=DEFAULT_CONNECTOR_BACKEND,
)
_normalize_connector_backend = main_window_helper_runtime._normalize_connector_backend
_recommended_connector_for_key = main_window_helper_runtime._recommended_connector_for_key
_format_indicator_list = main_window_helper_runtime._format_indicator_list
_safe_float = main_window_helper_runtime._safe_float
_safe_int = main_window_helper_runtime._safe_int
_normalize_indicator_token = main_window_helper_runtime._normalize_indicator_token
_canonicalize_indicator_key = main_window_helper_runtime._canonicalize_indicator_key
_normalize_indicator_values = main_window_helper_runtime._normalize_indicator_values
_infer_indicators_from_desc = main_window_helper_runtime._infer_indicators_from_desc
_resolve_trigger_indicators = main_window_helper_runtime._resolve_trigger_indicators
_normalize_datetime_pair = main_window_helper_runtime._normalize_datetime_pair
_make_engine_key = main_window_helper_runtime._make_engine_key

# Startup knobs to avoid slow/flashy QtWebEngine init on Windows
_DISABLE_CHARTS = str(os.environ.get("BOT_DISABLE_CHARTS", "")).strip().lower() in {"1", "true", "yes", "on"}
_DISABLE_TRADINGVIEW = str(os.environ.get("BOT_DISABLE_TRADINGVIEW", "")).strip().lower() in {"1", "true", "yes", "on"}
try:
    _SYMBOL_FETCH_TOP_N = int(os.environ.get("BOT_SYMBOL_FETCH_TOP_N") or 200)
except Exception:
    _SYMBOL_FETCH_TOP_N = 200
_SYMBOL_FETCH_TOP_N = max(50, min(_SYMBOL_FETCH_TOP_N, 5000))

_DEPENDENCY_USAGE_POLL_INTERVAL_MS = dependency_versions_runtime._DEPENDENCY_USAGE_POLL_INTERVAL_MS
_normalize_dependency_key = dependency_versions_runtime._normalize_dependency_key
_normalize_dependency_usage_text = dependency_versions_runtime._normalize_dependency_usage_text
_set_dependency_usage_widget = dependency_versions_runtime._set_dependency_usage_widget
_set_dependency_usage_counter_widget = dependency_versions_runtime._set_dependency_usage_counter_widget
_make_dependency_cell_copyable = dependency_versions_runtime._make_dependency_cell_copyable
_apply_dependency_usage_entry = dependency_versions_runtime._apply_dependency_usage_entry
_rust_manifest_path = dependency_versions_runtime._rust_manifest_path
_rust_package_metadata = dependency_versions_runtime._rust_package_metadata
_rust_project_version = dependency_versions_runtime._rust_project_version
_rust_tool_path = dependency_versions_runtime._rust_tool_path
_rust_toolchain_env = dependency_versions_runtime._rust_toolchain_env
_reset_rust_dependency_caches = dependency_versions_runtime._reset_rust_dependency_caches
_rust_tool_version = dependency_versions_runtime._rust_tool_version
_rust_auto_install_enabled = dependency_versions_runtime._rust_auto_install_enabled
_rust_auto_install_cooldown_seconds = dependency_versions_runtime._rust_auto_install_cooldown_seconds
_rust_missing_tool_labels = dependency_versions_runtime._rust_missing_tool_labels
_install_rust_toolchain = dependency_versions_runtime._install_rust_toolchain
_cpp_qt_webengine_available = dependency_versions_runtime._cpp_qt_webengine_available
_cpp_qt_websockets_available = dependency_versions_runtime._cpp_qt_websockets_available
_cpp_auto_setup_enabled = dependency_versions_runtime._cpp_auto_setup_enabled
_cpp_auto_setup_cooldown_seconds = dependency_versions_runtime._cpp_auto_setup_cooldown_seconds
_tail_text = dependency_versions_runtime._tail_text
_cpp_auto_prepare_environment_result = dependency_versions_runtime._cpp_auto_prepare_environment_result
_apply_cpp_auto_prepare_result = dependency_versions_runtime._apply_cpp_auto_prepare_result
_maybe_auto_prepare_cpp_environment = dependency_versions_runtime._maybe_auto_prepare_cpp_environment
_dependency_usage_state = dependency_versions_runtime._dependency_usage_state
_refresh_dependency_usage_labels = dependency_versions_runtime._refresh_dependency_usage_labels
_resolve_dependency_targets_for_config = dependency_versions_runtime._resolve_dependency_targets_for_config
_collect_dependency_versions = dependency_versions_runtime._collect_dependency_versions
DEPENDENCY_VERSION_TARGETS = dependency_versions_runtime.DEPENDENCY_VERSION_TARGETS

CHART_INTERVAL_OPTIONS = BACKTEST_INTERVAL_ORDER[:]

CHART_MARKET_OPTIONS = ["Futures", "Spot"]

ACCOUNT_MODE_OPTIONS = ["Classic Trading", "Portfolio Margin"]
POS_TRIGGERED_VALUE_COLUMN = 10
POS_CURRENT_VALUE_COLUMN = 11
POS_STOP_LOSS_COLUMN = 15
POS_STATUS_COLUMN = 16
POS_CLOSE_COLUMN = 17
WAITING_POSITION_LATE_THRESHOLD = 45.0

DEFAULT_CHART_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "TRXUSDT",
]

SIDE_LABELS = {
    "BUY": "Buy (Long)",
    "SELL": "Sell (Short)",
    "BOTH": "Both (Long/Short)",
}
SIDE_LABEL_LOOKUP = {label.lower(): code for code, label in SIDE_LABELS.items()}


# ============== Persistence for Position Allocations ==============
def _save_position_allocations(
    entry_allocations: dict,
    open_position_records: dict,
    mode: str | None = None,
) -> bool:
    return allocation_persistence.save_position_allocations(
        entry_allocations,
        open_position_records,
        this_file=_THIS_FILE,
        mode=mode,
    )


def _load_position_allocations(mode: str | None = None) -> tuple[dict, dict]:
    return allocation_persistence.load_position_allocations(
        this_file=_THIS_FILE,
        mode=mode,
    )
def _collect_dependency_versions(
    targets: list[dict[str, str]] | None = None,
    *,
    include_latest: bool = True,
    config: dict | None = None,
) -> list[tuple[str, str, str, str]]:
    return dependency_versions_runtime._collect_dependency_versions(
        targets,
        include_latest=include_latest,
        config=config,
    )

_DBG_BACKTEST_DASHBOARD = True
_DBG_BACKTEST_RUN = True



class MainWindow(QtWidgets.QWidget):
    log_signal = pyqtSignal(str)
    trade_signal = pyqtSignal(dict)

    # thread-safe control signals for positions worker
    req_pos_start = QtCore.pyqtSignal(int)
    req_pos_stop = QtCore.pyqtSignal()
    req_pos_set_interval = QtCore.pyqtSignal(int)

    def _on_trade_signal(self, order_info: dict):
        return main_window_trade_runtime._mw_on_trade_signal(self, order_info)

    LIGHT_THEME = """
    QWidget { background-color: #FFFFFF; color: #000000; font-family: Arial; }
    QGroupBox { border: 1px solid #C0C0C0; margin-top: 6px; }
    QPushButton { background-color: #F0F0F0; border: 1px solid #B0B0B0; padding: 6px; }
    QPushButton:disabled { background-color: #D5D5D5; border: 1px solid #B8B8B8; color: #7A7A7A; }
    QTextEdit { background-color: #FFFFFF; color: #000000; }
    QLineEdit { background-color: #FFFFFF; color: #000000; }
    QLineEdit:disabled,
    QComboBox:disabled,
    QListWidget:disabled,
    QSpinBox:disabled,
    QDoubleSpinBox:disabled,
    QTextEdit:disabled,
    QPlainTextEdit:disabled { background-color: #E6E6E6; color: #7A7A7A; }
    QCheckBox:disabled,
    QRadioButton:disabled { color: #7A7A7A; }
    QCheckBox::indicator {
        width: 16px;
        height: 16px;
        border: 1px solid #7A7A7A;
        border-radius: 3px;
        background-color: #FFFFFF;
    }
    QCheckBox::indicator:unchecked {
        image: none;
    }
    QCheckBox::indicator:checked {
        background-color: #0A84FF;
        border-color: #0A84FF;
        image: url(:/qt-project.org/styles/commonstyle/images/checkboxchecked.png);
    }
    QCheckBox::indicator:hover {
        border-color: #0A84FF;
    }
    QComboBox { background-color: #FFFFFF; color: #000000; }
    QListWidget { background-color: #FFFFFF; color: #000000; }
    QLabel { color: #000000; }
    QLabel:disabled { color: #7A7A7A; }
    """

    DARK_THEME = """
    QWidget { background-color: #121212; color: #E0E0E0; font-family: Arial; }
    QGroupBox { border: 1px solid #333; margin-top: 6px; }
    QPushButton { background-color: #1E1E1E; border: 1px solid #333; padding: 6px; }
    QPushButton:disabled { background-color: #2A2A2A; border: 1px solid #444; color: #808080; }
    QTextEdit { background-color: #0E0E0E; color: #E0E0E0; }
    QLineEdit { background-color: #1E1E1E; color: #E0E0E0; }
    QLineEdit:disabled,
    QComboBox:disabled,
    QListWidget:disabled,
    QSpinBox:disabled,
    QDoubleSpinBox:disabled,
    QTextEdit:disabled,
    QPlainTextEdit:disabled { background-color: #1A1A1A; color: #7E7E7E; }
    QCheckBox:disabled,
    QRadioButton:disabled { color: #7E7E7E; }
    QCheckBox::indicator {
        width: 16px;
        height: 16px;
        border: 1px solid #5A5A5A;
        border-radius: 3px;
        background-color: #1A1A1A;
    }
    QCheckBox::indicator:unchecked {
        image: none;
    }
    QCheckBox::indicator:checked {
        background-color: #3FB950;
        border-color: #3FB950;
        image: url(:/qt-project.org/styles/commonstyle/images/checkboxchecked.png);
    }
    QCheckBox::indicator:hover {
        border-color: #3FB950;
    }
    QComboBox { background-color: #1E1E1E; color: #E0E0E0; }
    QListWidget { background-color: #0E0E0E; color: #E0E0E0; }
    QLabel { color: #E0E0E0; }
    QLabel:disabled { color: #6F6F6F; }
    """

    def __init__(self):
        super().__init__()
        try:
            # Avoid repeated native window re-creation (can cause Windows flicker during startup).
            current_flags = self.windowFlags()
            desired_flags = (
                current_flags
                | QtCore.Qt.WindowType.Window
                | QtCore.Qt.WindowType.WindowMinimizeButtonHint
                | QtCore.Qt.WindowType.WindowMaximizeButtonHint
                | QtCore.Qt.WindowType.WindowTitleHint
                | QtCore.Qt.WindowType.WindowSystemMenuHint
                | QtCore.Qt.WindowType.WindowCloseButtonHint
            )
            desired_flags &= ~QtCore.Qt.WindowType.FramelessWindowHint
            desired_flags &= ~QtCore.Qt.WindowType.Tool
            if desired_flags != current_flags:
                self.setWindowFlags(desired_flags)
        except Exception:
            pass
        self._state_path = APP_STATE_PATH
        self._app_state = _load_app_state_file(self._state_path)
        self._previous_session_unclosed = bool(self._app_state.get("session_active", False))
        self._session_marker_active = False
        self._auto_close_on_restart_triggered = False
        self._ui_initialized = False
        # Keep pending-attempt TTL finite to avoid stale queue entries delaying orders (esp. on testnet).
        self.guard = IntervalPositionGuard(stale_ttl_sec=90, strict_symbol_side=False)
        self.config = copy.deepcopy(DEFAULT_CONFIG)
        self.config["stop_loss"] = normalize_stop_loss_dict(self.config.get("stop_loss"))
        self.config.setdefault('theme', 'Dark')
        self.config['close_on_exit'] = False
        self.config.setdefault('close_on_exit', False)
        self.config["allow_opposite_positions"] = coerce_bool(
            self.config.get("allow_opposite_positions", True), True
        )
        self.config.setdefault('account_mode', 'Classic Trading')
        self.config.setdefault('auto_bump_percent_multiplier', DEFAULT_CONFIG.get('auto_bump_percent_multiplier', 10.0))
        self.config["connector_backend"] = _normalize_connector_backend(self.config.get("connector_backend"))
        self.config.setdefault("positions_auto_resize_rows", True)
        self.config.setdefault("positions_auto_resize_columns", True)
        self.config.setdefault("code_language", next(iter(LANGUAGE_PATHS)))
        self.config.setdefault("selected_rust_framework", "")
        self.config.setdefault("selected_exchange", next(iter(EXCHANGE_PATHS)))
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
        self._pending_tradingview_mode = False  # Defer TradingView init to avoid startup window flashes
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
        self._tv_visibility_watchdog_active = False
        self._tv_visibility_watchdog_timer = None
        self._tradingview_external_last_open_ts = 0.0
        self._chart_debug_log_path = Path(os.getenv("TEMP") or ".").resolve() / "binance_chart_debug.log"
        self.chart_enabled = ENABLE_CHART_TAB and not _DISABLE_CHARTS
        self._chart_worker = None
        self._chart_theme_signal_installed = False
        default_symbols = self.config.get("symbols") or ["BTCUSDT"]
        default_intervals = self.config.get("intervals") or ["1h"]
        self.chart_symbol_cache = {opt: [] for opt in CHART_MARKET_OPTIONS}
        self._chart_symbol_alias_map = {}
        self._chart_symbol_loading = set()
        default_market = self.config.get("account_type", "Futures")
        if not default_market or default_market not in CHART_MARKET_OPTIONS:
            default_market = "Futures"
        self.chart_config.setdefault("market", default_market)
        initial_symbols_norm = [str(sym).strip().upper() for sym in (default_symbols or []) if str(sym).strip()]
        if initial_symbols_norm:
            dedup = []
            seen = set()
            for sym in initial_symbols_norm:
                if sym not in seen:
                    seen.add(sym)
                    dedup.append(sym)
        self.chart_symbol_cache["Futures"] = dedup
        default_symbol = (default_symbols[0] if default_symbols else "BTCUSDT")
        if default_market == "Futures":
            default_symbol = self._futures_display_symbol(default_symbol)
        self.chart_config.setdefault("symbol", default_symbol)
        self.chart_config.setdefault("interval", (default_intervals[0] if default_intervals else "1h"))
        # Default to TradingView when available so the chart tab opens directly in TradingView mode.
        # On Windows, avoid auto-opening TradingView during startup; keep the Original selection by default.
        default_view_mode = "original"
        if sys.platform != "win32" and _tradingview_supported() and not _DISABLE_TRADINGVIEW and not _DISABLE_CHARTS:
            default_view_mode = "tradingview"
        self.chart_config.setdefault("view_mode", default_view_mode)
        try:
            if self._normalize_chart_market(self.chart_config.get("market")) == "Futures":
                current_cfg_symbol = str(self.chart_config.get("symbol") or "").strip()
                if current_cfg_symbol and not current_cfg_symbol.endswith(".P"):
                    self.chart_config["symbol"] = self._futures_display_symbol(current_cfg_symbol)
        except Exception:
            pass
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
        self.backtest_config.setdefault("connector_backend", DEFAULT_CONFIG.get("backtest", {}).get("connector_backend", DEFAULT_CONNECTOR_BACKEND))
        self.backtest_config["connector_backend"] = _normalize_connector_backend(self.backtest_config.get("connector_backend"))
        self.config.setdefault("backtest", {})["connector_backend"] = self.backtest_config["connector_backend"]
        self.backtest_config.setdefault("leverage", int(default_backtest.get("leverage", 5)))
        mdd_logic_cfg = str(
            self.backtest_config.get("mdd_logic")
            or default_backtest.get("mdd_logic")
            or MDD_LOGIC_DEFAULT
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
            template_name = (
                next(iter(BACKTEST_TEMPLATE_DEFINITIONS))
                if BACKTEST_TEMPLATE_DEFINITIONS
                else None
            )
        self.backtest_config["template"] = {
            "enabled": template_enabled,
            "name": template_name,
        }
        self.config.setdefault("backtest", {})["template"] = copy.deepcopy(self.backtest_config["template"])
        self.backtest_config.setdefault("backtest_symbol_interval_pairs", list(self.config.get("backtest_symbol_interval_pairs", [])))
        default_stop_loss = normalize_stop_loss_dict(default_backtest.get("stop_loss"))
        self.backtest_config["stop_loss"] = normalize_stop_loss_dict(self.backtest_config.get("stop_loss", default_stop_loss))
        self.config.setdefault("backtest", {})["stop_loss"] = copy.deepcopy(self.backtest_config["stop_loss"])
        self._backtest_futures_widgets = []
        self.config.setdefault("runtime_symbol_interval_pairs", [])
        self.config.setdefault("backtest_symbol_interval_pairs", [])
        # Verbose override debugging can generate a lot of log traffic and make the UI feel frozen on startup.
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
        self._ensure_runtime_connector_for_account(self.config.get("account_type") or "Futures", force_default=False)
        self._override_debug_verbose = bool(self.config.get("debug_override_verbose", False))
        self.init_ui()
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
        # Always start on Dashboard for consistent startup UX across runtimes.
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

    def _update_positions_balance_labels(
        self,
        total_balance: float | None,
        available_balance: float | None,
    ) -> None:
        try:
            snapshot = getattr(self, "_positions_balance_snapshot", None)
        except Exception:
            snapshot = None
        if total_balance is None and available_balance is None and isinstance(snapshot, dict):
            total_balance = snapshot.get("total")
            available_balance = snapshot.get("available")
        else:
            try:
                self._positions_balance_snapshot = {"total": total_balance, "available": available_balance}
            except Exception:
                pass

        def _set_label(label: QtWidgets.QLabel | None, prefix: str, value: float | None) -> None:
            if label is None:
                return
            if value is None:
                label.setText(f"{prefix}: --")
            else:
                try:
                    label.setText(f"{prefix}: {float(value):.3f} USDT")
                except Exception:
                    label.setText(f"{prefix}: --")

        _set_label(getattr(self, "positions_total_balance_label", None), "Total Balance", total_balance)
        _set_label(getattr(self, "positions_available_balance_label", None), "Available Balance", available_balance)

    def _compute_global_pnl_totals(
        self,
    ) -> tuple[float | None, float | None, float | None, float | None]:
        def _safe_float(value) -> float | None:
            try:
                if value is None:
                    return None
                return float(value)
            except Exception:
                return None

        open_records = getattr(self, "_open_position_records", {}) or {}
        active_total_pnl = 0.0
        active_total_margin = 0.0
        active_pnl_found = False
        active_margin_found = False
        for rec in open_records.values():
            if not isinstance(rec, dict):
                continue
            data = rec.get("data") if isinstance(rec, dict) else {}
            pnl_val = _safe_float((data or {}).get("pnl_value"))
            if pnl_val is None:
                pnl_val = _safe_float(rec.get("pnl_value"))
            if pnl_val is not None:
                active_total_pnl += pnl_val
                active_pnl_found = True
            margin_val = _safe_float((data or {}).get("margin_usdt"))
            if margin_val is None or margin_val <= 0.0:
                margin_val = _safe_float((data or {}).get("margin_balance"))
            if margin_val is None or margin_val <= 0.0:
                allocs = (data or {}).get("allocations") or rec.get("allocations")
                if isinstance(allocs, list):
                    alloc_margin = 0.0
                    for alloc in allocs:
                        alloc_margin += _safe_float((alloc or {}).get("margin_usdt")) or 0.0
                    if alloc_margin > 0.0:
                        margin_val = alloc_margin
            if margin_val is not None and margin_val > 0.0:
                active_total_margin += margin_val
                active_margin_found = True

        closed_registry = getattr(self, "_closed_trade_registry", {}) or {}
        closed_total_pnl = 0.0
        closed_total_margin = 0.0
        closed_pnl_found = False
        closed_margin_found = False
        for entry in closed_registry.values():
            if not isinstance(entry, dict):
                continue
            pnl_val = _safe_float(entry.get("pnl_value"))
            if pnl_val is not None:
                closed_total_pnl += pnl_val
                closed_pnl_found = True
            margin_val = _safe_float(entry.get("margin_usdt"))
            if margin_val is not None and margin_val > 0.0:
                closed_total_margin += margin_val
                closed_margin_found = True

        active_pnl = active_total_pnl if active_pnl_found else None
        active_margin = active_total_margin if active_margin_found and active_total_margin > 0.0 else None
        closed_pnl = closed_total_pnl if closed_pnl_found else None
        closed_margin = closed_total_margin if closed_margin_found and closed_total_margin > 0.0 else None
        return active_pnl, active_margin, closed_pnl, closed_margin

    def _on_close_on_exit_changed(self, state):
        enabled = bool(state)
        self.config['close_on_exit'] = enabled
        try:
            data = dict(getattr(self, "_app_state", {}) or {})
        except Exception:
            data = {}
        data['close_on_exit'] = enabled
        if getattr(self, "_session_marker_active", False):
            data['session_active'] = True
        else:
            data['session_active'] = bool(data.get('session_active', False))
        data['updated_at'] = datetime.utcnow().isoformat()
        try:
            _save_app_state_file(self._state_path, data)
            self._app_state = data
        except Exception:
            pass
        try:
            engines = getattr(self, "strategy_engines", {}) or {}
            for eng in engines.values():
                try:
                    if hasattr(eng, "config"):
                        eng.config['close_on_exit'] = enabled
                except Exception:
                    pass
        except Exception:
            pass

    def _mark_session_active(self):
        if getattr(self, "_session_marker_active", False):
            return
        self._session_marker_active = True
        try:
            data = dict(getattr(self, "_app_state", {}) or {})
        except Exception:
            data = {}
        data['session_active'] = True
        data['close_on_exit'] = bool(self.config.get('close_on_exit', False))
        data['activated_at'] = datetime.utcnow().isoformat()
        try:
            _save_app_state_file(self._state_path, data)
            self._app_state = data
        except Exception:
            pass

    def _mark_session_inactive(self):
        if not getattr(self, "_session_marker_active", False):
            return
        self._session_marker_active = False
        try:
            data = dict(getattr(self, "_app_state", {}) or {})
        except Exception:
            data = {}
        data['session_active'] = False
        data['close_on_exit'] = bool(self.config.get('close_on_exit', False))
        data['deactivated_at'] = datetime.utcnow().isoformat()
        try:
            _save_app_state_file(self._state_path, data)
            self._app_state = data
        except Exception:
            pass

    def _handle_post_init_state(self):
        try:
            self._mark_session_active()
            if self.config.get('close_on_exit') and getattr(self, "_previous_session_unclosed", False):
                if not getattr(self, "_auto_close_on_restart_triggered", False):
                    self._auto_close_on_restart_triggered = True
                    self._previous_session_unclosed = False
                    self.log(
                        "Previous session ended unexpectedly with close-on-exit enabled; scheduling emergency close of all positions."
                    )

                    api_key = ""
                    api_secret = ""
                    mode = ""
                    account = ""
                    margin_mode = "Isolated"
                    leverage = 1
                    connector_backend = DEFAULT_CONNECTOR_BACKEND

                    try:
                        api_key = self.api_key_edit.text().strip() if getattr(self, "api_key_edit", None) else ""
                        api_secret = self.api_secret_edit.text().strip() if getattr(self, "api_secret_edit", None) else ""
                    except Exception:
                        api_key = ""
                        api_secret = ""

                    try:
                        mode = str(self.mode_combo.currentText() or "") if getattr(self, "mode_combo", None) else ""
                    except Exception:
                        mode = ""
                    try:
                        account = str(self.account_combo.currentText() or "") if getattr(self, "account_combo", None) else ""
                    except Exception:
                        account = ""
                    try:
                        margin_mode = str(self.margin_mode_combo.currentText() or "Isolated") if getattr(self, "margin_mode_combo", None) else "Isolated"
                    except Exception:
                        margin_mode = "Isolated"
                    try:
                        leverage = int(self.leverage_spin.value() or 1) if getattr(self, "leverage_spin", None) else 1
                    except Exception:
                        leverage = 1
                    try:
                        connector_backend = _normalize_connector_backend(self.config.get("connector_backend") or DEFAULT_CONNECTOR_BACKEND)
                    except Exception:
                        connector_backend = DEFAULT_CONNECTOR_BACKEND

                    if api_key and api_secret:
                        try:
                            self.stop_strategy_async(close_positions=False, blocking=False)
                        except Exception:
                            pass

                        def _run_emergency_close(
                            api_key_val: str,
                            api_secret_val: str,
                            mode_val: str,
                            account_val: str,
                            connector_backend_val: str,
                            leverage_val: int,
                            margin_mode_val: str,
                        ) -> None:
                            try:
                                wrapper = self._create_binance_wrapper(
                                    api_key=api_key_val,
                                    api_secret=api_secret_val,
                                    mode=mode_val,
                                    account_type=account_val,
                                    connector_backend=connector_backend_val,
                                    default_leverage=max(1, int(leverage_val or 1)),
                                    default_margin_mode=str(margin_mode_val or "Isolated"),
                                )
                                wrapper.trigger_emergency_close_all(reason="restart_recovery", source="startup")
                                try:
                                    self.log("Emergency close request submitted.")
                                except Exception:
                                    pass
                            except Exception as exc_inner:
                                try:
                                    self.log(f"Emergency close scheduling error: {exc_inner}")
                                except Exception:
                                    pass

                        threading.Thread(
                            target=_run_emergency_close,
                            args=(api_key, api_secret, mode, account, connector_backend, leverage, margin_mode),
                            daemon=True,
                        ).start()
                    else:
                        self.log("Emergency close skipped: API credentials are missing.")
                    try:
                        data = dict(getattr(self, "_app_state", {}) or {})
                        data['session_active'] = True
                        data['close_on_exit'] = bool(self.config.get('close_on_exit', False))
                        data['last_recovery_at'] = datetime.utcnow().isoformat()
                        data['last_recovery_reason'] = 'restart_recovery'
                        _save_app_state_file(self._state_path, data)
                        self._app_state = data
                    except Exception:
                        pass
        except Exception as exc:
            try:
                self.log(f"Post-init state handler error: {exc}")
            except Exception:
                pass

    def _set_runtime_controls_enabled(self, enabled: bool):
        try:
            widgets = getattr(self, "_runtime_lock_widgets", [])
            exemptions = getattr(self, "_runtime_active_exemptions", set())
            for widget in widgets:
                if widget is None:
                    continue
                if enabled:
                    widget.setEnabled(True)
                    continue
                if widget in exemptions:
                    try:
                        widget.setEnabled(True)
                    except Exception:
                        pass
                else:
                    widget.setEnabled(False)
        except Exception:
            pass
        if enabled:
            try:
                tif_combo = getattr(self, "tif_combo", None)
                gtd_spin = getattr(self, "gtd_minutes_spin", None)
                if tif_combo is not None and gtd_spin is not None:
                    is_gtd = (tif_combo.currentText() == "GTD")
                    gtd_spin.setEnabled(is_gtd)
                    gtd_spin.setReadOnly(not is_gtd)
                    try:
                        gtd_spin.setButtonSymbols(
                            QtWidgets.QAbstractSpinBox.ButtonSymbols.UpDownArrows
                            if is_gtd
                            else QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons
                        )
                    except Exception:
                        pass
                self._apply_lead_trader_state(bool(self.config.get("lead_trader_enabled", False)))
            except Exception:
                pass

    def _override_ctx(self, kind: str) -> dict:
        return getattr(self, "override_contexts", {}).get(kind, {})

    def _register_runtime_active_exemption(self, widget):
        if widget is None:
            return
        try:
            exemptions = getattr(self, "_runtime_active_exemptions", None)
            if isinstance(exemptions, set):
                exemptions.add(widget)
        except Exception:
            pass

    def _override_config_list(self, kind: str) -> list:
        ctx = self._override_ctx(kind)
        cfg_key = ctx.get("config_key")
        if not cfg_key:
            return []
        lst = self.config.setdefault(cfg_key, [])
        if not isinstance(lst, list):
            if isinstance(lst, (tuple, set)):
                lst = list(lst)
            elif isinstance(lst, dict):
                lst = [dict(lst)]
            else:
                lst = []
            self.config[cfg_key] = lst
        if kind == "backtest":
            try:
                self.backtest_config[cfg_key] = list(lst)
            except Exception:
                pass
        return lst

    @staticmethod
    def _normalize_loop_override(value) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        cleaned = re.sub(r"\s+", "", text.lower())
        if re.match(r"^\d+(s|m|h|d|w)?$", cleaned):
            return cleaned
        return None

    def _loop_choice_value(self, combo: QtWidgets.QComboBox | None) -> str:
        if combo is None:
            return ""
        try:
            data = combo.currentData()
        except Exception:
            data = ""
        if data is None:
            data = ""
        normalized = self._normalize_loop_override(data)
        if normalized:
            return normalized
        return ""

    def _set_loop_combo_value(self, combo: QtWidgets.QComboBox | None, value: str | None) -> None:
        if combo is None:
            return
        target = self._normalize_loop_override(value)
        if not target:
            target = ""
        idx = combo.findData(target)
        if idx < 0 and target:
            combo.addItem(target, target)
            idx = combo.count() - 1
        try:
            blocker = QtCore.QSignalBlocker(combo)
        except Exception:
            blocker = None
        if idx < 0:
            idx = 0
        combo.setCurrentIndex(idx)
        if blocker is not None:
            del blocker

    def _collect_strategy_controls(self, kind: str) -> dict:
        try:
            if kind == "runtime":
                stop_cfg = normalize_stop_loss_dict(copy.deepcopy(self.config.get("stop_loss")))
                controls = {
                    "side": self._resolve_dashboard_side(),
                    "position_pct": float(self.pospct_spin.value()) if hasattr(self, "pospct_spin") else None,
                    "position_pct_units": "percent" if hasattr(self, "pospct_spin") else None,
                    "loop_interval_override": self._loop_choice_value(getattr(self, "loop_combo", None)),
                    "add_only": bool(self.cb_add_only.isChecked()) if hasattr(self, "cb_add_only") else None,
                    "stop_loss": stop_cfg,
                    "connector_backend": self._runtime_connector_backend(suppress_refresh=True),
                }
                leverage_val = None
                if hasattr(self, "leverage_spin"):
                    try:
                        leverage_val = int(self.leverage_spin.value())
                    except Exception:
                        leverage_val = None
                acct_text = str(self.config.get("account_type") or "")
                if not acct_text.strip().upper().startswith("FUT"):
                    leverage_val = 1
                if leverage_val is not None:
                    controls["leverage"] = leverage_val
                account_mode_val = None
                try:
                    account_mode_val = self.account_mode_combo.currentData()
                except Exception:
                    account_mode_val = None
                if not account_mode_val and hasattr(self, "account_mode_combo"):
                    try:
                        account_mode_val = self.account_mode_combo.currentText()
                    except Exception:
                        account_mode_val = None
                if account_mode_val:
                    controls["account_mode"] = self._normalize_account_mode(account_mode_val)
                return self._normalize_strategy_controls("runtime", controls)
            if kind == "backtest":
                stop_cfg = normalize_stop_loss_dict(copy.deepcopy(self.backtest_config.get("stop_loss")))
                assets_mode_val = None
                try:
                    assets_mode_val = self.backtest_assets_mode_combo.currentData()
                except Exception:
                    assets_mode_val = None
                if not assets_mode_val and hasattr(self, "backtest_assets_mode_combo"):
                    try:
                        assets_mode_val = self.backtest_assets_mode_combo.currentText()
                    except Exception:
                        assets_mode_val = None
                account_mode_val = None
                try:
                    account_mode_val = self.backtest_account_mode_combo.currentData()
                except Exception:
                    account_mode_val = None
                if not account_mode_val and hasattr(self, "backtest_account_mode_combo"):
                    try:
                        account_mode_val = self.backtest_account_mode_combo.currentText()
                    except Exception:
                        account_mode_val = None
                controls = {
                    "logic": self.backtest_logic_combo.currentText() if hasattr(self, "backtest_logic_combo") else None,
                    "capital": float(self.backtest_capital_spin.value()) if hasattr(self, "backtest_capital_spin") else None,
                    "position_pct": float(self.backtest_pospct_spin.value()) if hasattr(self, "backtest_pospct_spin") else None,
                    "position_pct_units": "percent" if hasattr(self, "backtest_pospct_spin") else None,
                    "side": self.backtest_side_combo.currentText() if hasattr(self, "backtest_side_combo") else None,
                    "margin_mode": self.backtest_margin_mode_combo.currentText() if hasattr(self, "backtest_margin_mode_combo") else None,
                    "position_mode": self.backtest_position_mode_combo.currentText() if hasattr(self, "backtest_position_mode_combo") else None,
                    "assets_mode": assets_mode_val,
                    "loop_interval_override": self._loop_choice_value(getattr(self, "backtest_loop_combo", None)),
                    "leverage": int(self.backtest_leverage_spin.value()) if hasattr(self, "backtest_leverage_spin") else None,
                    "stop_loss": stop_cfg,
                    "connector_backend": self._backtest_connector_backend(),
                }
                if account_mode_val:
                    controls["account_mode"] = self._normalize_account_mode(account_mode_val)
                return self._normalize_strategy_controls("backtest", controls)
        except Exception:
            pass
        return {}

    def _prepare_controls_snapshot(self, kind: str, snapshot) -> dict:
        prepared: dict[str, object] = {}
        if isinstance(snapshot, dict):
            try:
                prepared = copy.deepcopy(snapshot)
            except Exception:
                prepared = dict(snapshot)
        else:
            prepared = {}

        def _runtime_default(name: str, getter, fallback=None):
            if name in prepared and prepared.get(name) not in (None, ""):
                return prepared[name]
            try:
                value = getter()
                if value not in (None, ""):
                    prepared[name] = value
                    return value
            except Exception:
                pass
            if fallback not in (None, ""):
                prepared[name] = fallback
                return fallback
            return prepared.get(name)

        if kind == "runtime":
            _runtime_default(
                "side",
                lambda: self._resolve_dashboard_side() if hasattr(self, "_resolve_dashboard_side") else self.config.get("side"),
                fallback=str(self.config.get("side") or "BOTH").upper(),
            )
            _runtime_default(
                "position_pct",
                lambda: float(self.pospct_spin.value()) if hasattr(self, "pospct_spin") else float(self.config.get("position_pct", 0.0)),
                fallback=float(self.config.get("position_pct", 0.0)),
            )
            units_val = prepared.get("position_pct_units") or self.config.get("position_pct_units") or "percent"
            try:
                prepared["position_pct_units"] = self._normalize_position_pct_units(units_val)
            except Exception:
                prepared["position_pct_units"] = "percent"
            loop_val = prepared.get("loop_interval_override")
            if not loop_val and hasattr(self, "loop_combo"):
                loop_val = self._loop_choice_value(getattr(self, "loop_combo", None))
            loop_val = self._normalize_loop_override(loop_val)
            if loop_val:
                prepared["loop_interval_override"] = loop_val
            _runtime_default(
                "add_only",
                lambda: bool(self.cb_add_only.isChecked()) if hasattr(self, "cb_add_only") else self.config.get("add_only", False),
                fallback=bool(self.config.get("add_only", False)),
            )
            _runtime_default(
                "leverage",
                lambda: int(self.leverage_spin.value()) if hasattr(self, "leverage_spin") else int(self.config.get("leverage", 1)),
                fallback=int(self.config.get("leverage", 1)),
            )
            account_mode_val = prepared.get("account_mode")
            if not account_mode_val and hasattr(self, "account_mode_combo"):
                try:
                    account_mode_val = self.account_mode_combo.currentData() or self.account_mode_combo.currentText()
                except Exception:
                    account_mode_val = None
            if not account_mode_val:
                account_mode_val = self.config.get("account_mode")
            if account_mode_val:
                try:
                    prepared["account_mode"] = self._normalize_account_mode(account_mode_val)
                except Exception:
                    prepared["account_mode"] = self.config.get("account_mode")
            stop_cfg = prepared.get("stop_loss")
            if not isinstance(stop_cfg, dict):
                prepared["stop_loss"] = normalize_stop_loss_dict(self.config.get("stop_loss"))
            connector_val = prepared.get("connector_backend")
            if not connector_val:
                try:
                    connector_val = self._runtime_connector_backend(suppress_refresh=True)
                except Exception:
                    connector_val = self.config.get("connector_backend")
            prepared["connector_backend"] = _normalize_connector_backend(connector_val)
        elif kind == "backtest":
            back_cfg = self.backtest_config if isinstance(getattr(self, "backtest_config", None), dict) else {}
            _runtime_default(
                "logic",
                lambda: self.backtest_logic_combo.currentText() if hasattr(self, "backtest_logic_combo") else back_cfg.get("logic"),
                fallback=back_cfg.get("logic"),
            )
            _runtime_default(
                "capital",
                lambda: float(self.backtest_capital_spin.value()) if hasattr(self, "backtest_capital_spin") else float(back_cfg.get("capital", 0.0)),
                fallback=float(back_cfg.get("capital", 0.0)),
            )
            _runtime_default(
                "position_pct",
                lambda: float(self.backtest_pospct_spin.value()) if hasattr(self, "backtest_pospct_spin") else float(back_cfg.get("position_pct", 0.0)),
                fallback=float(back_cfg.get("position_pct", 0.0)),
            )
            units_val = prepared.get("position_pct_units") or back_cfg.get("position_pct_units") or "percent"
            try:
                prepared["position_pct_units"] = self._normalize_position_pct_units(units_val)
            except Exception:
                prepared["position_pct_units"] = "percent"
            _runtime_default(
                "side",
                lambda: self.backtest_side_combo.currentText() if hasattr(self, "backtest_side_combo") else back_cfg.get("side"),
                fallback=back_cfg.get("side"),
            )
            _runtime_default(
                "margin_mode",
                lambda: self.backtest_margin_mode_combo.currentText() if hasattr(self, "backtest_margin_mode_combo") else back_cfg.get("margin_mode"),
                fallback=back_cfg.get("margin_mode"),
            )
            _runtime_default(
                "position_mode",
                lambda: self.backtest_position_mode_combo.currentText() if hasattr(self, "backtest_position_mode_combo") else back_cfg.get("position_mode"),
                fallback=back_cfg.get("position_mode"),
            )
            _runtime_default(
                "assets_mode",
                lambda: self.backtest_assets_mode_combo.currentData() if hasattr(self, "backtest_assets_mode_combo") else back_cfg.get("assets_mode"),
                fallback=back_cfg.get("assets_mode"),
            )
            account_mode_val = prepared.get("account_mode")
            if not account_mode_val and hasattr(self, "backtest_account_mode_combo"):
                try:
                    account_mode_val = self.backtest_account_mode_combo.currentData() or self.backtest_account_mode_combo.currentText()
                except Exception:
                    account_mode_val = None
            if not account_mode_val:
                account_mode_val = back_cfg.get("account_mode")
            if account_mode_val:
                try:
                    prepared["account_mode"] = self._normalize_account_mode(account_mode_val)
                except Exception:
                    prepared["account_mode"] = account_mode_val
            loop_val = prepared.get("loop_interval_override")
            if not loop_val and hasattr(self, "backtest_loop_combo"):
                loop_val = self._loop_choice_value(getattr(self, "backtest_loop_combo", None))
            loop_val = self._normalize_loop_override(loop_val)
            if loop_val:
                prepared["loop_interval_override"] = loop_val
            _runtime_default(
                "leverage",
                lambda: int(self.backtest_leverage_spin.value()) if hasattr(self, "backtest_leverage_spin") else int(back_cfg.get("leverage", 1)),
                fallback=int(back_cfg.get("leverage", 1)),
            )
            stop_cfg = prepared.get("stop_loss")
            if not isinstance(stop_cfg, dict):
                prepared["stop_loss"] = normalize_stop_loss_dict(back_cfg.get("stop_loss"))
            connector_val = prepared.get("connector_backend")
            if not connector_val:
                try:
                    connector_val = self._backtest_connector_backend()
                except Exception:
                    connector_val = back_cfg.get("connector_backend")
            prepared["connector_backend"] = _normalize_connector_backend(connector_val)
        return prepared

    def _override_debug_enabled(self) -> bool:
        return bool(getattr(self, "_override_debug_verbose", False) or self.config.get("debug_override_verbose", False))

    def _log_override_debug(self, kind: str, message: str, *, payload: dict | None = None) -> None:
        if not self._override_debug_enabled():
            return
        try:
            suffix = ""
            if payload:
                try:
                    import json

                    suffix = f" :: {json.dumps(payload, default=str, ensure_ascii=False)}"
                except Exception:
                    suffix = f" :: {payload}"
            self.log(f"[Override-{kind}] {message}{suffix}")
        except Exception:
            pass

    @staticmethod
    def _normalize_position_pct_units(value) -> str:
        text = str(value or "").strip().lower()
        if text in {"percent", "%", "perc", "percentage"}:
            return "percent"
        if text in {"fraction", "decimal", "ratio"}:
            return "fraction"
        return ""

    def _normalize_strategy_controls(self, kind: str, controls) -> dict:
        if not isinstance(controls, dict):
            return {}
        normalized: dict[str, object] = {}
        if kind == "runtime":
            side_raw = str(controls.get("side") or "").upper()
            if side_raw in SIDE_LABELS:
                normalized["side"] = side_raw
            pos_pct = controls.get("position_pct")
            if pos_pct is not None:
                try:
                    normalized["position_pct"] = float(pos_pct)
                except Exception:
                    pass
            units_val = controls.get("position_pct_units") or controls.get("_position_pct_units")
            units_norm = self._normalize_position_pct_units(units_val)
            if units_norm:
                normalized["position_pct_units"] = units_norm
            leverage = controls.get("leverage")
            if leverage is not None:
                try:
                    lev_val = int(leverage)
                    if lev_val >= 1:
                        normalized["leverage"] = lev_val
                except Exception:
                    pass
            loop_override = self._normalize_loop_override(controls.get("loop_interval_override"))
            if loop_override:
                normalized["loop_interval_override"] = loop_override
            add_only = controls.get("add_only")
            if add_only is not None:
                normalized["add_only"] = bool(add_only)
            account_mode = controls.get("account_mode")
            if account_mode:
                normalized["account_mode"] = self._normalize_account_mode(account_mode)
            stop_loss_raw = controls.get("stop_loss")
            if isinstance(stop_loss_raw, dict):
                normalized["stop_loss"] = normalize_stop_loss_dict(stop_loss_raw)
            backend_val = controls.get("connector_backend")
            if backend_val:
                normalized["connector_backend"] = _normalize_connector_backend(backend_val)
        elif kind == "backtest":
            logic_raw = str(controls.get("logic") or "").upper()
            if logic_raw in {"AND", "OR", "SEPARATE"}:
                normalized["logic"] = logic_raw
            capital = controls.get("capital")
            if capital is not None:
                try:
                    normalized["capital"] = float(capital)
                except Exception:
                    pass
            pos_pct = controls.get("position_pct")
            if pos_pct is not None:
                try:
                    normalized["position_pct"] = float(pos_pct)
                except Exception:
                    pass
            units_val = controls.get("position_pct_units") or controls.get("_position_pct_units")
            units_norm = self._normalize_position_pct_units(units_val)
            if units_norm:
                normalized["position_pct_units"] = units_norm
            side_val = controls.get("side")
            if side_val:
                side_code = str(side_val).upper()
                if side_code not in SIDE_LABELS:
                    side_code = self._canonical_side_from_text(str(side_val))
                if side_code in SIDE_LABELS:
                    normalized["side"] = side_code
            margin_mode = controls.get("margin_mode")
            if margin_mode:
                normalized["margin_mode"] = str(margin_mode)
            position_mode = controls.get("position_mode")
            if position_mode:
                normalized["position_mode"] = str(position_mode)
            assets_mode = controls.get("assets_mode")
            if assets_mode:
                normalized["assets_mode"] = self._normalize_assets_mode(assets_mode)
            account_mode = controls.get("account_mode")
            if account_mode:
                normalized["account_mode"] = self._normalize_account_mode(account_mode)
            loop_override = self._normalize_loop_override(controls.get("loop_interval_override"))
            if loop_override:
                normalized["loop_interval_override"] = loop_override
            leverage = controls.get("leverage")
            if leverage is not None:
                try:
                    normalized["leverage"] = int(leverage)
                except Exception:
                    pass
            stop_loss_raw = controls.get("stop_loss")
            if isinstance(stop_loss_raw, dict):
                normalized["stop_loss"] = normalize_stop_loss_dict(stop_loss_raw)
            backend_val = controls.get("connector_backend")
            if backend_val:
                normalized["connector_backend"] = _normalize_connector_backend(backend_val)
        return normalized

    def _format_strategy_controls_summary(self, kind: str, controls: dict) -> str:
        if not controls:
            return "-"
        parts: list[str] = []
        if kind == "runtime":
            side = controls.get("side")
            if side:
                parts.append(f"Side={side}")
            pos_pct = controls.get("position_pct")
            if pos_pct is not None:
                try:
                    pct_value = float(pos_pct)
                    units_norm = self._normalize_position_pct_units(controls.get("position_pct_units"))
                    if units_norm == "fraction":
                        pct_value *= 100.0
                    parts.append(f"Pos={pct_value:.2f}%")
                except Exception:
                    pass
            leverage = controls.get("leverage")
            if leverage is not None:
                try:
                    parts.append(f"Lev={int(leverage)}x")
                except Exception:
                    pass
            loop = controls.get("loop_interval_override") or "auto"
            parts.append(f"Loop={loop}")
            add_only = controls.get("add_only")
            if add_only is not None:
                parts.append(f"AddOnly={'Y' if add_only else 'N'}")
            account_mode = controls.get("account_mode")
            if account_mode:
                parts.append(f"AcctMode={account_mode}")
            stop_loss = controls.get("stop_loss")
            if isinstance(stop_loss, dict):
                if stop_loss.get("enabled"):
                    mode = str(stop_loss.get("mode") or "usdt")
                    summary_bits = []
                    scope_val = str(stop_loss.get("scope") or "per_trade")
                    summary_bits.append(f"scope={scope_val}")
                    summary_bits.append(f"mode={mode}")
                    if mode == "usdt" and stop_loss.get("usdt"):
                        summary_bits.append(f"U={float(stop_loss.get('usdt', 0.0)):.0f}")
                    elif mode == "percent" and stop_loss.get("percent"):
                        summary_bits.append(f"P={float(stop_loss.get('percent', 0.0)):.2f}%")
                    elif mode == "both":
                        if stop_loss.get("usdt") is not None:
                            summary_bits.append(f"U={float(stop_loss.get('usdt', 0.0)):.0f}")
                        if stop_loss.get("percent") is not None:
                            summary_bits.append(f"P={float(stop_loss.get('percent', 0.0)):.2f}%")
                    parts.append(f"SL=On({'; '.join(summary_bits)})")
                else:
                    parts.append("SL=Off")
        elif kind == "backtest":
            logic = controls.get("logic")
            if logic:
                parts.append(f"Logic={logic}")
            pos_pct = controls.get("position_pct")
            if pos_pct is not None:
                try:
                    pct_value = float(pos_pct)
                    units_norm = self._normalize_position_pct_units(controls.get("position_pct_units"))
                    if units_norm == "fraction":
                        pct_value *= 100.0
                    parts.append(f"Pos={pct_value:.2f}%")
                except Exception:
                    pass
            capital = controls.get("capital")
            if capital is not None:
                try:
                    parts.append(f"Cap={float(capital):.0f}")
                except Exception:
                    pass
            leverage = controls.get("leverage")
            if leverage is not None:
                try:
                    parts.append(f"Lev={int(leverage)}")
                except Exception:
                    pass
            side = controls.get("side")
            if side:
                parts.append(f"Side={side}")
            margin_mode = controls.get("margin_mode")
            if margin_mode:
                parts.append(f"Margin={margin_mode}")
            assets_mode = controls.get("assets_mode")
            if assets_mode:
                parts.append(f"Assets={assets_mode}")
            account_mode = controls.get("account_mode")
            if account_mode:
                parts.append(f"AcctMode={account_mode}")
            stop_loss = controls.get("stop_loss")
            if isinstance(stop_loss, dict):
                if stop_loss.get("enabled"):
                    mode = str(stop_loss.get("mode") or "usdt")
                    scope_val = str(stop_loss.get("scope") or "per_trade")
                    details = []
                    details.append(f"mode={mode}")
                    details.append(f"scope={scope_val}")
                    if stop_loss.get("usdt") not in (None, ""):
                        details.append(f"U={float(stop_loss.get('usdt', 0.0)):.0f}")
                    if stop_loss.get("percent") not in (None, ""):
                        details.append(f"P={float(stop_loss.get('percent', 0.0)):.2f}%")
                    parts.append(f"SL=On({'; '.join(details)})")
                else:
                    parts.append("SL=Off")
        return ", ".join(parts) if parts else "-"

    def _runtime_stop_loss_update(self, **updates):
        current = normalize_stop_loss_dict(self.config.get("stop_loss"))
        current.update(updates)
        current = normalize_stop_loss_dict(current)
        self.config["stop_loss"] = current
        return current

    def _update_runtime_stop_loss_widgets(self):
        cfg = normalize_stop_loss_dict(self.config.get("stop_loss"))
        self.config["stop_loss"] = cfg
        enabled = bool(cfg.get("enabled"))
        mode = str(cfg.get("mode") or "usdt").lower()
        scope = str(cfg.get("scope") or "per_trade").lower()
        bot_active = bool(getattr(self, "_bot_active", False))
        checkbox = getattr(self, "stop_loss_enable_cb", None)
        combo = getattr(self, "stop_loss_mode_combo", None)
        usdt_spin = getattr(self, "stop_loss_usdt_spin", None)
        pct_spin = getattr(self, "stop_loss_percent_spin", None)
        scope_combo = getattr(self, "stop_loss_scope_combo", None)
        if checkbox is not None:
            checkbox.blockSignals(True)
            checkbox.setChecked(enabled)
            checkbox.blockSignals(False)
        if combo is not None:
            combo.blockSignals(True)
            idx = combo.findData(mode)
            if idx < 0:
                idx = combo.findData(STOP_LOSS_MODE_ORDER[0])
                if idx < 0:
                    idx = 0
            combo.setCurrentIndex(idx)
            combo.setEnabled(enabled and not bot_active)
            combo.blockSignals(False)
        if usdt_spin is not None:
            usdt_spin.blockSignals(True)
            usdt_spin.setValue(float(cfg.get("usdt", 0.0)))
            usdt_spin.blockSignals(False)
            usdt_spin.setEnabled(enabled and not bot_active and mode in ("usdt", "both"))
        if pct_spin is not None:
            pct_spin.blockSignals(True)
            pct_spin.setValue(float(cfg.get("percent", 0.0)))
            pct_spin.blockSignals(False)
            pct_spin.setEnabled(enabled and not bot_active and mode in ("percent", "both"))
        if scope_combo is not None:
            scope_combo.blockSignals(True)
            idx_scope = scope_combo.findData(scope)
            if idx_scope < 0:
                idx_scope = scope_combo.findData(STOP_LOSS_SCOPE_OPTIONS[0])
                if idx_scope < 0:
                    idx_scope = 0
            scope_combo.setCurrentIndex(idx_scope)
            scope_combo.setEnabled(enabled and not bot_active)
            scope_combo.blockSignals(False)

    def _on_dashboard_template_changed(self):
        if not hasattr(self, "template_combo"):
            return
        key = self.template_combo.currentData()
        if key is None:
            return
        key = str(key or "")
        self.config["dashboard_template"] = key
        if not key:
            return
        template = self._dashboard_templates.get(key)
        if not template:
            return

        pct_value = float(template.get("position_pct", self.config.get("position_pct", 2.0)))
        self.config["position_pct"] = pct_value
        self.config["position_pct_units"] = "percent"
        display_pct = pct_value if pct_value > 1.0 else pct_value * 100.0
        if hasattr(self, "pospct_spin"):
            self.pospct_spin.blockSignals(True)
            self.pospct_spin.setValue(display_pct)
            self.pospct_spin.blockSignals(False)

        leverage_value = int(template.get("leverage", self.config.get("leverage", 5)))
        self.config["leverage"] = leverage_value
        if hasattr(self, "leverage_spin"):
            self.leverage_spin.setValue(leverage_value)

        margin_mode = template.get("margin_mode")
        if margin_mode:
            self.config["margin_mode"] = margin_mode
            if hasattr(self, "margin_mode_combo"):
                combo = self.margin_mode_combo
                combo.blockSignals(True)
                if hasattr(QtCore.Qt, "MatchFlag"):
                    idx = combo.findText(margin_mode, QtCore.Qt.MatchFlag.MatchFixedString)
                else:
                    idx = combo.findText(margin_mode)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                combo.blockSignals(False)

        if key == "top10":
            updated_sl = self._runtime_stop_loss_update(
                enabled=True,
                mode="percent",
                percent=20.0,
                scope="per_trade",
            )
            checkbox = getattr(self, "stop_loss_enable_cb", None)
            if checkbox is not None:
                with QtCore.QSignalBlocker(checkbox):
                    checkbox.setChecked(True)
            mode_combo = getattr(self, "stop_loss_mode_combo", None)
            if mode_combo is not None:
                with QtCore.QSignalBlocker(mode_combo):
                    idx_mode = mode_combo.findData("percent")
                    if idx_mode < 0:
                        idx_mode = 0
                    mode_combo.setCurrentIndex(idx_mode)
            percent_spin = getattr(self, "stop_loss_percent_spin", None)
            if percent_spin is not None:
                with QtCore.QSignalBlocker(percent_spin):
                    percent_spin.setValue(20.0)
            scope_combo = getattr(self, "stop_loss_scope_combo", None)
            if scope_combo is not None:
                with QtCore.QSignalBlocker(scope_combo):
                    idx_scope = scope_combo.findData("per_trade")
                    if idx_scope < 0:
                        idx_scope = scope_combo.findData(STOP_LOSS_SCOPE_OPTIONS[0])
                    if idx_scope is not None and idx_scope >= 0:
                        scope_combo.setCurrentIndex(idx_scope)
            self.config["stop_loss"] = updated_sl
            self._update_runtime_stop_loss_widgets()

        indicators = template.get("indicators", {})
        for ind_key, params in indicators.items():
            cfg = self.config["indicators"].setdefault(ind_key, {})
            cfg.update(params)
            cfg["enabled"] = True
            widgets = self.indicator_widgets.get(ind_key) if hasattr(self, "indicator_widgets") else None
            if widgets:
                cb, _btn = widgets
                if not cb.isChecked():
                    cb.setChecked(True)
                else:
                    self.config["indicators"][ind_key] = cfg

    def _on_runtime_loop_changed(self, *_args):
        value = self._loop_choice_value(getattr(self, "loop_combo", None))
        self.config["loop_interval_override"] = value

    def _on_allow_opposite_changed(self, state: int) -> None:
        allow = state == QtCore.Qt.CheckState.Checked
        self.config["allow_opposite_positions"] = allow
        guard_obj = getattr(self, "guard", None)
        if guard_obj and hasattr(guard_obj, "allow_opposite"):
            dual_enabled = False
            try:
                if self.shared_binance is not None and hasattr(self.shared_binance, "get_futures_dual_side"):
                    dual_enabled = bool(self.shared_binance.get_futures_dual_side())
            except Exception:
                dual_enabled = False
            try:
                guard_obj.allow_opposite = allow and dual_enabled
            except Exception:
                pass

    def _on_backtest_loop_changed(self, *_args):
        value = self._loop_choice_value(getattr(self, "backtest_loop_combo", None))
        self._update_backtest_config("loop_interval_override", value)

    def _on_runtime_account_mode_changed(self, index: int) -> None:
        combo = getattr(self, "account_mode_combo", None)
        if combo is None:
            return
        if index is None or index < 0:
            index = combo.currentIndex()
        try:
            data = combo.itemData(index)
        except Exception:
            data = None
        if data is None:
            data = combo.itemText(index)
        normalized = self._normalize_account_mode(data)
        self.config["account_mode"] = normalized
        self._apply_runtime_account_mode_constraints(normalized)

    def _on_backtest_account_mode_changed(self, index: int) -> None:
        combo = getattr(self, "backtest_account_mode_combo", None)
        if combo is None:
            return
        if index is None or index < 0:
            index = combo.currentIndex()
        try:
            data = combo.itemData(index)
        except Exception:
            data = None
        if data is None:
            data = combo.itemText(index)
        normalized = self._normalize_account_mode(data)
        self._update_backtest_config("account_mode", normalized)
        self._apply_backtest_account_mode_constraints(normalized)

    def _apply_runtime_account_mode_constraints(self, normalized_mode: str) -> None:
        self._enforce_portfolio_margin_constraints(
            normalized_mode,
            getattr(self, "margin_mode_combo", None),
            runtime=True,
        )

    def _apply_backtest_account_mode_constraints(self, normalized_mode: str) -> None:
        self._enforce_portfolio_margin_constraints(
            normalized_mode,
            getattr(self, "backtest_margin_mode_combo", None),
            runtime=False,
        )

    def _enforce_portfolio_margin_constraints(
        self,
        normalized_mode: str,
        combo: QtWidgets.QComboBox | None,
        *,
        runtime: bool,
    ) -> None:
        if combo is None:
            return
        is_portfolio = (normalized_mode == "Portfolio Margin")
        blocker = None
        try:
            blocker = QtCore.QSignalBlocker(combo)
        except Exception:
            blocker = None
        if is_portfolio:
            idx_cross = -1
            try:
                idx_cross = combo.findText("Cross", QtCore.Qt.MatchFlag.MatchFixedString)
            except Exception:
                try:
                    idx_cross = combo.findText("Cross")
                except Exception:
                    idx_cross = -1
            if idx_cross < 0:
                for pos in range(combo.count()):
                    text = str(combo.itemText(pos)).strip().lower()
                    if text == "cross":
                        idx_cross = pos
                        break
            if idx_cross >= 0:
                combo.setCurrentIndex(idx_cross)
        if blocker is not None:
            del blocker
        combo.setEnabled(not is_portfolio)
        if is_portfolio:
            if runtime:
                self.config["margin_mode"] = "Cross"
            else:
                self.backtest_config["margin_mode"] = "Cross"
                self.config.setdefault("backtest", {})["margin_mode"] = "Cross"

    def _on_lead_trader_toggled(self, checked: bool) -> None:
        enabled = bool(checked)
        self.config["lead_trader_enabled"] = enabled
        self._apply_lead_trader_state(enabled)

    def _on_lead_trader_option_changed(self, index: int) -> None:
        combo = getattr(self, "lead_trader_combo", None)
        if combo is None:
            return
        if index is None or index < 0:
            index = combo.currentIndex()
        try:
            value = combo.itemData(index)
        except Exception:
            value = None
        if value is None:
            value = combo.itemText(index)
        self.config["lead_trader_profile"] = str(value)

    def _apply_lead_trader_state(self, enabled: bool) -> None:
        combo = getattr(self, "lead_trader_combo", None)
        if combo is not None:
            combo.setEnabled(bool(enabled))
        self._apply_runtime_account_mode_constraints(self.config.get("account_mode", ACCOUNT_MODE_OPTIONS[0]))

    def _apply_initial_geometry(self):
        """Ensure the window fits on the active screen on Linux desktops."""
        if not sys.platform.startswith("linux"):
            return
        try:
            screen = QtGui.QGuiApplication.primaryScreen()
            if screen is None:
                return
            avail = screen.availableGeometry()
            if not avail or not avail.isValid():
                return
            min_w, min_h = 1024, 640
            target_w = min(max(min_w, int(avail.width() * 0.9)), avail.width())
            target_h = min(max(min_h, int(avail.height() * 0.9)), avail.height())
            self.setMinimumSize(min(min_w, avail.width()), min(min_h, avail.height()))
            self.resize(target_w, target_h)
            frame_geo = self.frameGeometry()
            frame_geo.moveCenter(avail.center())
            self.move(frame_geo.topLeft())
        except Exception:
            pass

    def _on_runtime_stop_loss_enabled(self, checked: bool):
        self._runtime_stop_loss_update(enabled=bool(checked))
        self._update_runtime_stop_loss_widgets()

    def _on_runtime_stop_loss_mode_changed(self):
        combo = getattr(self, "stop_loss_mode_combo", None)
        mode = combo.currentData() if combo is not None else None
        if mode not in STOP_LOSS_MODE_ORDER:
            mode = STOP_LOSS_MODE_ORDER[0]
        self._runtime_stop_loss_update(mode=mode)
        self._update_runtime_stop_loss_widgets()

    def _on_runtime_stop_loss_scope_changed(self):
        combo = getattr(self, "stop_loss_scope_combo", None)
        scope = combo.currentData() if combo is not None else None
        if scope not in STOP_LOSS_SCOPE_OPTIONS:
            scope = STOP_LOSS_SCOPE_OPTIONS[0]
        self._runtime_stop_loss_update(scope=scope)
        self._update_runtime_stop_loss_widgets()

    def _on_runtime_stop_loss_value_changed(self, kind: str, value: float):
        if kind == "usdt":
            self._runtime_stop_loss_update(usdt=max(0.0, float(value)))
        elif kind == "percent":
            self._runtime_stop_loss_update(percent=max(0.0, float(value)))
        self._update_runtime_stop_loss_widgets()

    def _backtest_stop_loss_update(self, **updates):
        current = normalize_stop_loss_dict(self.backtest_config.get("stop_loss"))
        current.update(updates)
        current = normalize_stop_loss_dict(current)
        self.backtest_config["stop_loss"] = current
        backtest_cfg = self.config.setdefault("backtest", {})
        backtest_cfg["stop_loss"] = copy.deepcopy(current)
        return current

    def _update_backtest_stop_loss_widgets(self):
        cfg = normalize_stop_loss_dict(self.backtest_config.get("stop_loss"))
        self.backtest_config["stop_loss"] = cfg
        self.config.setdefault("backtest", {})["stop_loss"] = copy.deepcopy(cfg)
        enabled = bool(cfg.get("enabled"))
        mode = str(cfg.get("mode") or "usdt").lower()
        scope = str(cfg.get("scope") or "per_trade").lower()
        checkbox = getattr(self, "backtest_stop_loss_enable_cb", None)
        combo = getattr(self, "backtest_stop_loss_mode_combo", None)
        usdt_spin = getattr(self, "backtest_stop_loss_usdt_spin", None)
        pct_spin = getattr(self, "backtest_stop_loss_percent_spin", None)
        scope_combo = getattr(self, "backtest_stop_loss_scope_combo", None)
        if checkbox is not None:
            checkbox.blockSignals(True)
            checkbox.setChecked(enabled)
            checkbox.blockSignals(False)
        if combo is not None:
            combo.blockSignals(True)
            idx = combo.findData(mode)
            if idx < 0:
                idx = combo.findData(STOP_LOSS_MODE_ORDER[0])
                if idx < 0:
                    idx = 0
            combo.setCurrentIndex(idx)
            combo.setEnabled(enabled)
            combo.blockSignals(False)
        if usdt_spin is not None:
            usdt_spin.blockSignals(True)
            usdt_spin.setValue(float(cfg.get("usdt", 0.0)))
            usdt_spin.blockSignals(False)
            usdt_spin.setEnabled(enabled and mode in ("usdt", "both"))
        if pct_spin is not None:
            pct_spin.blockSignals(True)
            pct_spin.setValue(float(cfg.get("percent", 0.0)))
            pct_spin.blockSignals(False)
            pct_spin.setEnabled(enabled and mode in ("percent", "both"))
        if scope_combo is not None:
            scope_combo.blockSignals(True)
            idx_scope = scope_combo.findData(scope)
            if idx_scope < 0:
                idx_scope = scope_combo.findData(STOP_LOSS_SCOPE_OPTIONS[0])
                if idx_scope < 0:
                    idx_scope = 0
            scope_combo.setCurrentIndex(idx_scope)
            scope_combo.setEnabled(enabled)
            scope_combo.blockSignals(False)

    def _on_backtest_stop_loss_enabled(self, checked: bool):
        self._backtest_stop_loss_update(enabled=bool(checked))
        self._update_backtest_stop_loss_widgets()

    def _on_backtest_stop_loss_mode_changed(self):
        combo = getattr(self, "backtest_stop_loss_mode_combo", None)
        mode = combo.currentData() if combo is not None else None
        if mode not in STOP_LOSS_MODE_ORDER:
            mode = STOP_LOSS_MODE_ORDER[0]
        self._backtest_stop_loss_update(mode=mode)
        self._update_backtest_stop_loss_widgets()

    def _on_backtest_stop_loss_scope_changed(self):
        combo = getattr(self, "backtest_stop_loss_scope_combo", None)
        scope = combo.currentData() if combo is not None else None
        if scope not in STOP_LOSS_SCOPE_OPTIONS:
            scope = STOP_LOSS_SCOPE_OPTIONS[0]
        self._backtest_stop_loss_update(scope=scope)
        self._update_backtest_stop_loss_widgets()

    def _on_backtest_stop_loss_value_changed(self, kind: str, value: float):
        if kind == "usdt":
            self._backtest_stop_loss_update(usdt=max(0.0, float(value)))
        elif kind == "percent":
            self._backtest_stop_loss_update(percent=max(0.0, float(value)))
        self._update_backtest_stop_loss_widgets()

    def _get_selected_indicator_keys(self, kind: str) -> list[str]:
        try:
            if kind == "runtime":
                widgets = getattr(self, "indicator_widgets", {}) or {}
            else:
                widgets = getattr(self, "backtest_indicator_widgets", {}) or {}
            keys: list[str] = []
            for key, control in widgets.items():
                cb = control[0] if isinstance(control, (tuple, list)) and control else None
                if cb and cb.isChecked():
                    keys.append(str(key))
            if keys:
                return keys
        except Exception:
            pass
        try:
            cfg = self.config if kind == "runtime" else self.backtest_config
            indicators_cfg = (cfg or {}).get("indicators", {}) or {}
            return [key for key, params in indicators_cfg.items() if params.get("enabled")]
        except Exception:
            return []

    def _refresh_symbol_interval_pairs(self, kind: str = "runtime", _depth: int = 0):
        current_depth = getattr(self, "_override_refresh_depth", 0)
        setattr(self, "_override_refresh_depth", current_depth + 1)
        try:
            ctx = self._override_ctx(kind)
            table = ctx.get("table")
            if table is None:
                return
            self._log_override_debug(kind, "Refreshing symbol/interval table start.")
            column_map = ctx.get("column_map") or {}
            symbol_col = column_map.get("Symbol", 0)
            interval_col = column_map.get("Interval", 1)
            indicator_col = column_map.get("Indicators")
            loop_col = column_map.get("Loop")
            leverage_col = column_map.get("Leverage")
            strategy_col = column_map.get("Strategy Controls")
            connector_col = column_map.get("Connector")
            stoploss_col = column_map.get("Stop-Loss")
            header = table.horizontalHeader()
            try:
                sort_column = header.sortIndicatorSection()
                sort_order = header.sortIndicatorOrder()
                if sort_column is None or sort_column < 0:
                    sort_column = 0
                    sort_order = QtCore.Qt.SortOrder.AscendingOrder
            except Exception:
                sort_column = 0
                sort_order = QtCore.Qt.SortOrder.AscendingOrder
            table.setSortingEnabled(False)
            pairs_cfg = self._override_config_list(kind) or []
            self._log_override_debug(kind, "Refresh loaded config list.", payload={"count": len(pairs_cfg)})
            snapshot_pairs = []
            try:
                snapshot_pairs = [copy.deepcopy(entry) for entry in pairs_cfg if isinstance(entry, dict)]
            except Exception:
                snapshot_pairs = [dict(entry) for entry in pairs_cfg if isinstance(entry, dict)]
            table.setRowCount(0)
            seen = set()
            cleaned = []
            for entry in pairs_cfg:
                self._log_override_debug(kind, "Processing existing override entry.", payload={"entry": entry})
                sym = str((entry or {}).get('symbol') or '').strip().upper()
                iv = str((entry or {}).get('interval') or '').strip()
                if not sym or not iv:
                    self._log_override_debug(kind, "Skipping entry: missing symbol or interval.", payload={"entry": entry})
                    continue
                indicators_raw = entry.get('indicators')
                indicator_values = _normalize_indicator_values(indicators_raw)
                leverage_val = None
                if isinstance(entry.get('strategy_controls'), dict):
                    lev_ctrl = entry['strategy_controls'].get('leverage')
                    if lev_ctrl is not None:
                        try:
                            leverage_val = max(1, int(lev_ctrl))
                        except Exception:
                            leverage_val = None
                if leverage_val is None:
                    lev_entry_raw = entry.get("leverage")
                    if lev_entry_raw is not None:
                        try:
                            leverage_val = max(1, int(lev_entry_raw))
                        except Exception:
                            leverage_val = None
                key = (sym, iv, tuple(indicator_values), leverage_val)
                if key in seen:
                    self._log_override_debug(kind, "Skipping duplicate entry.", payload={"key": key})
                    continue
                seen.add(key)
                controls = self._normalize_strategy_controls(kind, entry.get("strategy_controls"))
                self._log_override_debug(kind, "Normalized controls for entry.", payload={"symbol": sym, "interval": iv, "controls": controls})
                entry_clean = {'symbol': sym, 'interval': iv}
                if indicator_values:
                    entry_clean['indicators'] = list(indicator_values)
                loop_val = entry.get("loop_interval_override")
                if not loop_val and isinstance(controls, dict):
                    loop_val = controls.get("loop_interval_override")
                loop_val = self._normalize_loop_override(loop_val)
                if loop_val:
                    entry_clean["loop_interval_override"] = loop_val
                if controls:
                    entry_clean['strategy_controls'] = controls
                    stop_cfg = controls.get("stop_loss")
                    if isinstance(stop_cfg, dict):
                        entry_clean["stop_loss"] = normalize_stop_loss_dict(stop_cfg)
                    backend_ctrl = controls.get("connector_backend")
                    if backend_ctrl:
                        entry_clean["connector_backend"] = backend_ctrl
                if leverage_val is not None:
                    entry_clean["leverage"] = leverage_val
                    if isinstance(controls, dict):
                        controls["leverage"] = leverage_val
                if "stop_loss" not in entry_clean and entry.get("stop_loss"):
                    entry_clean["stop_loss"] = normalize_stop_loss_dict(entry.get("stop_loss"))
                cleaned.append(entry_clean)
                row = table.rowCount()
                table.insertRow(row)
                table.setItem(row, symbol_col, QtWidgets.QTableWidgetItem(sym))
                table.setItem(row, interval_col, QtWidgets.QTableWidgetItem(iv))
                if indicator_col is not None:
                    table.setItem(row, indicator_col, QtWidgets.QTableWidgetItem(_format_indicator_list(indicator_values)))
                if loop_col is not None:
                    loop_display = entry_clean.get("loop_interval_override") or "-"
                    table.setItem(row, loop_col, QtWidgets.QTableWidgetItem(loop_display))
                if leverage_col is not None:
                    leverage_display = f"{leverage_val}x" if leverage_val is not None else "-"
                    table.setItem(row, leverage_col, QtWidgets.QTableWidgetItem(leverage_display))
                if strategy_col is not None:
                    summary = self._format_strategy_controls_summary(kind, controls)
                    table.setItem(row, strategy_col, QtWidgets.QTableWidgetItem(summary))
                if connector_col is not None:
                    backend_val = None
                    if isinstance(controls, dict):
                        backend_val = controls.get("connector_backend")
                    if not backend_val:
                        if kind == "runtime":
                            backend_val = self._runtime_connector_backend(suppress_refresh=True)
                        else:
                            if current_depth > 0:
                                backend_val = _normalize_connector_backend(
                                    (self.backtest_config or {}).get("connector_backend")
                                    or self.config.get("backtest", {}).get("connector_backend")
                                )
                            else:
                                backend_val = self._backtest_connector_backend()
                    connector_display = self._connector_label_text(backend_val) if backend_val else "-"
                    table.setItem(row, connector_col, QtWidgets.QTableWidgetItem(connector_display))
                if stoploss_col is not None:
                    stop_label = "No"
                    stop_cfg_display = None
                    if isinstance(controls, dict):
                        stop_cfg_display = controls.get("stop_loss")
                    if stop_cfg_display is None:
                        stop_cfg_display = entry_clean.get("stop_loss")
                    if isinstance(stop_cfg_display, dict) and stop_cfg_display.get("enabled"):
                        scope_txt = str(stop_cfg_display.get("scope") or "").replace("_", "-")
                        stop_label = f"Yes ({scope_txt or 'per-trade'})"
                    table.setItem(row, stoploss_col, QtWidgets.QTableWidgetItem(stop_label))
                try:
                    table.item(row, symbol_col).setData(QtCore.Qt.ItemDataRole.UserRole, entry_clean)
                except Exception:
                    pass
                self._log_override_debug(kind, "Row populated.", payload={"row": row, "entry_clean": entry_clean})
            cfg_key = ctx.get("config_key")
            if cfg_key and not cleaned and snapshot_pairs and _depth == 0:
                self._log_override_debug(
                    kind,
                    "Refresh produced no rows; retrying with snapshot fallback.",
                    payload={"snapshot_len": len(snapshot_pairs)},
                )
                try:
                    self.config[cfg_key] = snapshot_pairs
                except Exception:
                    self.config[cfg_key] = list(snapshot_pairs)
                return self._refresh_symbol_interval_pairs(kind, _depth=_depth + 1)
            if cfg_key:
                self.config[cfg_key] = cleaned
                if kind == "backtest":
                    try:
                        self.backtest_config[cfg_key] = list(cleaned)
                    except Exception:
                        pass
            self._log_override_debug(kind, "Refresh completed.", payload={"cleaned_count": len(cleaned)})
            table.setSortingEnabled(True)
            try:
                if sort_column is not None and sort_column >= 0:
                    table.sortItems(sort_column, sort_order)
            except Exception:
                pass
        finally:
            setattr(self, "_override_refresh_depth", current_depth)

    def _add_selected_symbol_interval_pairs(self, kind: str = "runtime"):
        if kind == "runtime" and getattr(self, "_bot_active", False):
            try:
                self.log("Stop the bot before modifying runtime overrides.")
            except Exception:
                pass
            return
        ctx = self._override_ctx(kind)
        symbol_list = ctx.get("symbol_list")
        interval_list = ctx.get("interval_list")
        if symbol_list is None or interval_list is None:
            self._log_override_debug(kind, "Add-selected aborted: missing list widgets.", payload={"ctx_keys": list(ctx.keys())})
            return
        try:
            self._log_override_debug(kind, "Add-selected triggered.")
            symbol_items = []
            try:
                symbol_items = [item for item in symbol_list.selectedItems() if item]
                self._log_override_debug(kind, "Collected selected symbol items via selectedItems().", payload={"count": len(symbol_items)})
            except Exception:
                symbol_items = []
            if not symbol_items:
                for i in range(symbol_list.count()):
                    item = symbol_list.item(i)
                    if item and item.isSelected():
                        symbol_items.append(item)
                self._log_override_debug(kind, "Fallback symbol scan after selectedItems() empty.", payload={"count": len(symbol_items)})
            symbols = []
            for item in symbol_items:
                try:
                    text = item.text()
                except Exception:
                    text = ""
                text_norm = str(text or "").strip().upper()
                if text_norm:
                    symbols.append(text_norm)
            self._log_override_debug(kind, "Normalized symbols.", payload={"symbols": symbols})

            interval_items = []
            try:
                interval_items = [item for item in interval_list.selectedItems() if item]
                self._log_override_debug(kind, "Collected selected interval items via selectedItems().", payload={"count": len(interval_items)})
            except Exception:
                interval_items = []
            if not interval_items:
                for i in range(interval_list.count()):
                    item = interval_list.item(i)
                    if item and item.isSelected():
                        interval_items.append(item)
                self._log_override_debug(kind, "Fallback interval scan after selectedItems() empty.", payload={"count": len(interval_items)})
            intervals = []
            for item in interval_items:
                try:
                    text = item.text()
                except Exception:
                    text = ""
                text_norm = str(text or "").strip()
                if text_norm:
                    intervals.append(text_norm)
            self._log_override_debug(kind, "Normalized intervals.", payload={"intervals": intervals})

            if symbols:
                symbols = list(dict.fromkeys(symbols))
            if intervals:
                intervals = list(dict.fromkeys(intervals))
            if not symbols or not intervals:
                self._log_override_debug(kind, "Add-selected aborted: missing symbols or intervals.", payload={"symbols": symbols, "intervals": intervals})
                try:
                    self.log("Select at least one symbol and interval before adding overrides.")
                except Exception:
                    pass
                return
            pairs_cfg = self._override_config_list(kind)
            existing_keys = {}
            for entry in pairs_cfg:
                sym_existing = str(entry.get('symbol') or '').strip().upper()
                iv_existing = str(entry.get('interval') or '').strip()
                if not (sym_existing and iv_existing):
                    self._log_override_debug(kind, "Skipping existing entry missing symbol/interval.", payload={"entry": entry})
                    continue
                indicators_existing = entry.get('indicators')
                if isinstance(indicators_existing, (list, tuple)):
                    indicators_existing = sorted({str(k).strip() for k in indicators_existing if str(k).strip()})
                else:
                    indicators_existing = []
                key = (sym_existing, iv_existing, tuple(indicators_existing))
                existing_keys[key] = entry
            self._log_override_debug(kind, "Prepared existing key map.", payload={"existing_count": len(existing_keys)})
            controls_snapshot_raw = self._collect_strategy_controls(kind)
            self._log_override_debug(kind, "Raw strategy controls collected.", payload={"raw": controls_snapshot_raw})
            controls_snapshot = self._prepare_controls_snapshot(kind, controls_snapshot_raw)
            self._log_override_debug(kind, "Prepared strategy controls snapshot.", payload={"prepared": controls_snapshot})
            changed = False
            sel_indicators = self._get_selected_indicator_keys(kind)
            indicators_value = sorted({str(k).strip() for k in sel_indicators if str(k).strip()}) if sel_indicators else []
            indicators_tuple = tuple(indicators_value)
            for sym in symbols:
                if not sym:
                    self._log_override_debug(kind, "Skipping empty symbol after normalization.")
                    continue
                for iv in intervals:
                    if not iv:
                        self._log_override_debug(kind, "Skipping empty interval after normalization.", payload={"symbol": sym})
                        continue
                    key = (sym, iv, indicators_tuple)
                    if key in existing_keys:
                        entry = existing_keys[key]
                        if indicators_value:
                            entry['indicators'] = list(indicators_value)
                        else:
                            entry.pop('indicators', None)
                        if controls_snapshot:
                            entry['strategy_controls'] = copy.deepcopy(controls_snapshot)
                        else:
                            entry.pop('strategy_controls', None)
                        changed = True
                        self._log_override_debug(kind, "Updated existing override entry.", payload={"symbol": sym, "interval": iv, "indicators": indicators_value})
                        continue
                    new_entry = {'symbol': sym, 'interval': iv}
                    if indicators_value:
                        new_entry['indicators'] = list(indicators_value)
                    if controls_snapshot:
                        new_entry['strategy_controls'] = copy.deepcopy(controls_snapshot)
                    pairs_cfg.append(new_entry)
                    existing_keys[key] = new_entry
                    changed = True
                    self._log_override_debug(kind, "Appended new override entry.", payload={"symbol": sym, "interval": iv, "indicators": indicators_value})
            if changed:
                self._log_override_debug(kind, "Changes detected, refreshing table.", payload={"total_entries": len(pairs_cfg)})
                self._refresh_symbol_interval_pairs(kind)
            for widget in (symbol_list, interval_list):
                try:
                    for i in range(widget.count()):
                        item = widget.item(i)
                        if item:
                            item.setSelected(False)
                except Exception:
                    pass
            self._log_override_debug(kind, "Add-selected completed.", payload={"final_entries": len(self.config.get(ctx.get("config_key"), []))})
        except Exception:
            try:
                tb_text = traceback.format_exc()
                self._log_override_debug(kind, "Exception while adding overrides.", payload={"traceback": tb_text})
                self.log(f"Failed to add symbol/interval override: {tb_text}")
            except Exception:
                pass

    def _remove_selected_symbol_interval_pairs(self, kind: str = "runtime"):
        if kind == "runtime" and getattr(self, "_bot_active", False):
            try:
                self.log("Stop the bot before modifying runtime overrides.")
            except Exception:
                pass
            return
        ctx = self._override_ctx(kind)
        table = ctx.get("table")
        if table is None:
            return
        column_map = ctx.get("column_map") or {}
        symbol_col = column_map.get("Symbol", 0)
        interval_col = column_map.get("Interval", 1)
        try:
            rows = sorted({idx.row() for idx in table.selectionModel().selectedRows()}, reverse=True)
            if not rows:
                return
            pairs_cfg = self._override_config_list(kind)
            updated = []
            remove_set = set()
            for row in rows:
                sym_item = table.item(row, symbol_col)
                iv_item = table.item(row, interval_col)
                sym = sym_item.text().strip().upper() if sym_item else ''
                iv = iv_item.text().strip() if iv_item else ''
                if not (sym and iv):
                    continue
                indicators_raw = None
                exact_match = True
                try:
                    entry_data = sym_item.data(QtCore.Qt.ItemDataRole.UserRole)
                except Exception:
                    entry_data = None
                if isinstance(entry_data, dict):
                    indicators_raw = entry_data.get('indicators')
                else:
                    exact_match = False
                indicators_norm = _normalize_indicator_values(indicators_raw)
                if exact_match:
                    remove_set.add((sym, iv, tuple(indicators_norm)))
                else:
                    remove_set.add((sym, iv, None))
            for entry in pairs_cfg:
                if not isinstance(entry, dict):
                    continue
                sym = str(entry.get('symbol') or '').strip().upper()
                iv = str(entry.get('interval') or '').strip()
                indicators_raw = entry.get('indicators')
                indicators_norm = _normalize_indicator_values(indicators_raw)
                key = (sym, iv, tuple(indicators_norm))
                if key in remove_set or (sym, iv, None) in remove_set:
                    continue
                new_entry = {'symbol': sym, 'interval': iv}
                if indicators_norm:
                    new_entry['indicators'] = list(indicators_norm)
                updated.append(new_entry)
            cfg_key = ctx.get("config_key")
            if cfg_key:
                self.config[cfg_key] = updated
                if kind == "backtest":
                    try:
                        self.backtest_config[cfg_key] = list(updated)
                    except Exception:
                        pass
            self._refresh_symbol_interval_pairs(kind)
        except Exception:
            pass

    def _clear_symbol_interval_pairs(self, kind: str = "runtime"):
        if kind == "runtime" and getattr(self, "_bot_active", False):
            try:
                self.log("Stop the bot before modifying runtime overrides.")
            except Exception:
                pass
            return
        ctx = self._override_ctx(kind)
        cfg_key = ctx.get("config_key")
        if not cfg_key:
            return
        try:
            self.config[cfg_key] = []
            if kind == "backtest":
                try:
                    self.backtest_config[cfg_key] = []
                except Exception:
                    pass
            self._refresh_symbol_interval_pairs(kind)
        except Exception:
            pass

    def _create_override_group(self, kind: str, symbol_list, interval_list) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox("Symbol / Interval Overrides")
        layout = QtWidgets.QVBoxLayout(group)
        columns = ["Symbol", "Interval"]
        show_indicators = kind in ("runtime", "backtest")
        if show_indicators:
            columns.append("Indicators")
        include_loop = kind in ("runtime", "backtest")
        include_leverage = kind in ("runtime", "backtest")
        if include_loop:
            columns.append("Loop")
        if include_leverage:
            columns.append("Leverage")
        columns.append("Connector")
        columns.append("Strategy Controls")
        columns.append("Stop-Loss")
        table = QtWidgets.QTableWidget(0, len(columns))
        table.setHorizontalHeaderLabels(columns)
        column_map = {name: idx for idx, name in enumerate(columns)}
        header = table.horizontalHeader()
        header.setStretchLastSection(False)
        try:
            header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        except Exception:
            pass
        try:
            header.setSectionsMovable(True)
        except Exception:
            pass
        table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table.setSizeAdjustPolicy(QtWidgets.QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored)
        table.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel)
        table.setMinimumHeight(180)
        try:
            table.verticalHeader().setDefaultSectionSize(28)
        except Exception:
            pass
        try:
            table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        except Exception:
            table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QtWidgets.QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        table.setSortingEnabled(True)
        layout.addWidget(table)

        btn_layout = QtWidgets.QHBoxLayout()
        add_btn = QtWidgets.QPushButton("Add Selected")
        add_btn.clicked.connect(lambda _, k=kind: self._add_selected_symbol_interval_pairs(k))
        btn_layout.addWidget(add_btn)
        remove_btn = QtWidgets.QPushButton("Remove Selected")
        remove_btn.clicked.connect(lambda _, k=kind: self._remove_selected_symbol_interval_pairs(k))
        btn_layout.addWidget(remove_btn)
        clear_btn = QtWidgets.QPushButton("Clear All")
        clear_btn.clicked.connect(lambda _, k=kind: self._clear_symbol_interval_pairs(k))
        btn_layout.addWidget(clear_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        config_key = "runtime_symbol_interval_pairs" if kind == "runtime" else "backtest_symbol_interval_pairs"
        self.override_contexts[kind] = {
            "table": table,
            "symbol_list": symbol_list,
            "interval_list": interval_list,
            "config_key": config_key,
            "add_btn": add_btn,
            "remove_btn": remove_btn,
            "clear_btn": clear_btn,
            "column_map": column_map,
        }
        if kind == "runtime":
            self.pair_add_btn = add_btn
            self.pair_remove_btn = remove_btn
            self.pair_clear_btn = clear_btn
        lock_widgets = getattr(self, '_runtime_lock_widgets', None)
        if isinstance(lock_widgets, list):
            for widget in (table, add_btn, remove_btn, clear_btn):
                if widget and widget not in lock_widgets:
                    lock_widgets.append(widget)
        self._refresh_symbol_interval_pairs(kind)
        return group

    def _on_indicator_toggled(self, key: str, checked: bool):
        try:
            indicators = self.config.setdefault('indicators', {})
            params = indicators.setdefault(key, {})
            params['enabled'] = bool(checked)
        except Exception:
            pass

    def _update_bot_status(self, active=None):
        try:
            if active is not None:
                self._bot_active = bool(active)
            current_active = bool(getattr(self, "_bot_active", False))
            if current_active and not self._bot_active_since:
                self._bot_active_since = time.time()
                self._ensure_bot_time_timer()
                if self._bot_time_timer:
                    self._bot_time_timer.start()
            elif not current_active:
                self._bot_active_since = None
                if self._bot_time_timer:
                    self._bot_time_timer.stop()
            text = "Bot Status: ON" if current_active else "Bot Status: OFF"
            color = "#3FB950" if current_active else "#F97068"
            for label in (
                getattr(self, 'bot_status_label_tab1', None),
                getattr(self, 'bot_status_label_tab2', None),
                getattr(self, 'bot_status_label_tab3', None),
                getattr(self, 'bot_status_label_chart', None),
                getattr(self, 'bot_status_label_code_tab', None),
            ):
                if label is None:
                    continue
                label.setText(text)
                label.setStyleSheet(f"font-weight: bold; color: {color};")
            self._update_bot_time_labels()
        except Exception:
            pass

    def _ensure_bot_time_timer(self):
        if getattr(self, "_bot_time_timer", None) is None:
            try:
                timer = QtCore.QTimer(self)
                timer.setInterval(1000)
                timer.timeout.connect(self._update_bot_time_labels)
                self._bot_time_timer = timer
            except Exception:
                self._bot_time_timer = None

    @staticmethod
    def _format_bot_duration(seconds: float) -> str:
        remaining = int(max(seconds, 0))
        units = []
        spans = [
            ("mo", 30 * 24 * 3600),
            ("d", 24 * 3600),
            ("h", 3600),
            ("m", 60),
            ("s", 1),
        ]
        for suffix, size in spans:
            if remaining >= size:
                value, remaining = divmod(remaining, size)
                units.append(f"{value}{suffix}")
            if len(units) >= 3:
                break
        if not units:
            return "0s"
        return " ".join(units)

    def _update_bot_time_labels(self):
        try:
            labels = [
                getattr(self, 'bot_time_label_tab1', None),
                getattr(self, 'bot_time_label_tab2', None),
                getattr(self, 'bot_time_label_tab3', None),
                getattr(self, 'bot_time_label_chart', None),
                getattr(self, 'bot_time_label_code_tab', None),
            ]
            if not labels:
                return
            if self._bot_active and self._bot_active_since:
                elapsed = max(0.0, time.time() - float(self._bot_active_since))
                text = f"Bot Active Time: {self._format_bot_duration(elapsed)}"
            else:
                text = "Bot Active Time: --"
            for label in labels:
                if label is not None:
                    label.setText(text)
        except Exception:
            pass

    @staticmethod
    def _format_total_pnl_text(prefix: str, pnl_value: float | None, total_balance: float | None) -> str:
        if pnl_value is None:
            return f"{prefix}: --"
        text = f"{prefix}: {pnl_value:+.2f} USDT"
        if total_balance is not None:
            try:
                if total_balance != 0:
                    roi_value = (float(pnl_value) / float(total_balance)) * 100.0
                else:
                    roi_value = None
            except Exception:
                roi_value = None
            if roi_value is not None:
                text += f" ({roi_value:+.2f}%)"
        return text

    def _apply_pnl_snapshot_to_labels(
        self,
        active_label: QtWidgets.QLabel | None,
        closed_label: QtWidgets.QLabel | None,
    ) -> None:
        snapshot = getattr(self, "_last_pnl_snapshot", None) or {}
        balance_snapshot = getattr(self, "_positions_balance_snapshot", None) or {}
        total_balance_ref = balance_snapshot.get("total")
        active_snapshot = snapshot.get("active", {})
        closed_snapshot = snapshot.get("closed", {})
        if active_label is not None:
            active_label.setText(
                self._format_total_pnl_text(
                    "Total PNL Active Positions",
                    active_snapshot.get("pnl"),
                    total_balance_ref,
                )
            )
        if closed_label is not None:
            closed_label.setText(
                self._format_total_pnl_text(
                    "Total PNL Closed Positions",
                    closed_snapshot.get("pnl"),
                    total_balance_ref,
                )
            )

    def _register_pnl_summary_labels(
        self,
        active_label: QtWidgets.QLabel | None,
        closed_label: QtWidgets.QLabel | None,
    ) -> None:
        if not hasattr(self, "_pnl_label_sets") or self._pnl_label_sets is None:
            self._pnl_label_sets = []
        self._pnl_label_sets.append((active_label, closed_label))
        self._apply_pnl_snapshot_to_labels(active_label, closed_label)

    def _update_global_pnl_display(
        self,
        active_pnl: float | None,
        active_margin: float | None,
        closed_pnl: float | None,
        closed_margin: float | None,
    ) -> None:
        try:
            snapshot = getattr(self, "_last_pnl_snapshot", None)
            if snapshot is None:
                snapshot = {"active": {"pnl": None}, "closed": {"pnl": None}}
                self._last_pnl_snapshot = snapshot

            snapshot["active"] = {
                "pnl": active_pnl if active_pnl is not None else None,
            }
            snapshot["closed"] = {
                "pnl": closed_pnl if closed_pnl is not None else None,
            }
            for label_pair in getattr(self, "_pnl_label_sets", []) or []:
                if not isinstance(label_pair, (list, tuple)):
                    continue
                if len(label_pair) != 2:
                    continue
                active_label, closed_label = label_pair
                self._apply_pnl_snapshot_to_labels(active_label, closed_label)
        except Exception:
            pass

    def _has_active_engines(self):
        try:
            engines = getattr(self, 'strategy_engines', {}) or {}
        except Exception:
            return False
        for eng in engines.values():
            try:
                if hasattr(eng, 'is_alive'):
                    if eng.is_alive():
                        return True
                else:
                    thread = getattr(eng, '_thread', None)
                    if thread and getattr(thread, 'is_alive', lambda: False)():
                        return True
            except Exception:
                continue
        return False

    def _sync_runtime_state(self):
        active = self._has_active_engines()
        if active:
            self._set_runtime_controls_enabled(False)
        else:
            self._set_runtime_controls_enabled(True)
        try:
            btn = getattr(self, 'refresh_balance_btn', None)
            if btn is not None:
                btn.setEnabled(True)
        except Exception:
            pass
        try:
            start_btn = getattr(self, 'start_btn', None)
            stop_btn = getattr(self, 'stop_btn', None)
            if start_btn is not None:
                start_btn.setEnabled(not active)
            if stop_btn is not None:
                stop_btn.setEnabled(active)
        except Exception:
            pass
        try:
            for btn in (
                getattr(self, "pair_add_btn", None),
                getattr(self, "pair_remove_btn", None),
                getattr(self, "pair_clear_btn", None),
            ):
                if btn is not None:
                    btn.setEnabled(not active)
        except Exception:
            pass
        self._update_bot_status(active)
        try:
            self._update_runtime_stop_loss_widgets()
        except Exception:
            pass
        return active

    def _on_positions_view_changed(self, index: int):
        try:
            text = self.positions_view_combo.itemText(index)
        except Exception:
            text = ""
        mode = "cumulative"
        if isinstance(text, str) and text.lower().startswith("per"):
            mode = "per_trade"
        self._positions_view_mode = mode
        try:
            self._render_positions_table()
        except Exception:
            pass

    def _on_positions_auto_resize_changed(self, state: int):
        enabled = bool(state)
        self.config["positions_auto_resize_rows"] = enabled
        try:
            if enabled:
                self.pos_table.resizeRowsToContents()
            else:
                default_height = 44
                try:
                    default_height = int(
                        self.pos_table.verticalHeader().defaultSectionSize() or default_height
                    )
                except Exception:
                    default_height = 44
                self.pos_table.verticalHeader().setDefaultSectionSize(default_height)
                for row in range(self.pos_table.rowCount()):
                    try:
                        self.pos_table.setRowHeight(row, default_height)
                    except Exception:
                        pass
        except Exception:
            pass

    def _on_positions_auto_resize_columns_changed(self, state: int):
        enabled = bool(state)
        self.config["positions_auto_resize_columns"] = enabled
        try:
            if enabled:
                self.pos_table.resizeColumnsToContents()
            else:
                header = self.pos_table.horizontalHeader()
                try:
                    header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Interactive)
                except Exception:
                    try:
                        header.setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
                    except Exception:
                        pass
        except Exception:
            pass

    def init_ui(self):
        self.setWindowTitle("Trading Bot")
        # Allow smaller manual resize on compact screens.
        self.setMinimumSize(640, 420)
        try:
            _apply_window_icon(self)
        except Exception:
            pass
        if sys.platform == "win32":
            try:
                delay_ms = int(os.environ.get("BOT_WINDOW_ICON_RETRY_MS") or 1200)
            except Exception:
                delay_ms = 1200
            if delay_ms > 0:
                QtCore.QTimer.singleShot(delay_ms, lambda w=self: _apply_window_icon(w))
        root_layout = QtWidgets.QVBoxLayout(self)
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.currentChanged.connect(self._on_tab_changed)
        root_layout.addWidget(self.tabs)

        # ---------------- Dashboard tab ----------------
        tab1 = QtWidgets.QWidget()
        tab1_layout = QtWidgets.QVBoxLayout(tab1)
        tab1_layout.setContentsMargins(0, 0, 0, 0)
        tab1_layout.setSpacing(0)

        self.dashboard_scroll = QtWidgets.QScrollArea()
        self.dashboard_scroll.setWidgetResizable(True)
        self.dashboard_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.dashboard_scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        tab1_layout.addWidget(self.dashboard_scroll)

        scroll_contents = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_contents)
        scroll_layout.setContentsMargins(10, 10, 10, 10)
        scroll_layout.setSpacing(10)
        self.dashboard_scroll.setWidget(scroll_contents)
        # Top grid
        self._create_dashboard_header_section(scroll_layout)

        runtime_override_group = self._create_dashboard_markets_section(scroll_layout)
        # Strategy Controls
        self._create_dashboard_strategy_controls_section(scroll_layout)
        # Indicators
        self._create_dashboard_indicator_section(scroll_layout)

        scroll_layout.addWidget(runtime_override_group)
        # Buttons
        self._create_dashboard_action_section(scroll_layout)
        # Log
        self._create_dashboard_log_section(scroll_layout)

        self.tabs.addTab(tab1, "Dashboard")
        self._initialize_dashboard_chart_section()
        global MAX_CLOSED_HISTORY
        MAX_CLOSED_HISTORY = self._initialize_dashboard_runtime_state(
            current_max_closed_history=MAX_CLOSED_HISTORY,
            gui_max_closed_history=MAX_CLOSED_HISTORY,
        )


        # ---------------- Positions tab ----------------
        self._initialize_secondary_tabs()
        self._finalize_init_ui()


main_window_runtime.bind_main_window_runtime(
    MainWindow,
    strategy_engine_cls=StrategyEngine,
    numeric_item_cls=_NumericItem,
    waiting_position_late_threshold=WAITING_POSITION_LATE_THRESHOLD,
)
main_window_account_runtime.bind_main_window_account_runtime(
    MainWindow,
    connector_options=CONNECTOR_OPTIONS,
    default_connector_backend=DEFAULT_CONNECTOR_BACKEND,
    futures_connector_keys=FUTURES_CONNECTOR_KEYS,
    spot_connector_keys=SPOT_CONNECTOR_KEYS,
    side_labels=SIDE_LABELS,
    normalize_connector_backend=_normalize_connector_backend,
    recommended_connector_for_key=_recommended_connector_for_key,
    refresh_dependency_usage_labels=_refresh_dependency_usage_labels,
)
main_window_chart_view_runtime.bind_main_window_chart_view_runtime(
    MainWindow,
    chart_interval_options=CHART_INTERVAL_OPTIONS,
    chart_market_options=CHART_MARKET_OPTIONS,
)
main_window_chart_host_runtime.bind_main_window_chart_host_runtime(MainWindow)
main_window_chart_tab.bind_main_window_chart_tab(
    MainWindow,
    chart_market_options=CHART_MARKET_OPTIONS,
    chart_interval_options=CHART_INTERVAL_OPTIONS,
    disable_tradingview=_DISABLE_TRADINGVIEW,
    disable_charts=_DISABLE_CHARTS,
    qt_charts_available=QT_CHARTS_AVAILABLE,
)
main_window_tab_runtime.bind_main_window_tab_runtime(
    MainWindow,
    cpp_code_language_key=CPP_CODE_LANGUAGE_KEY,
)
main_window_dashboard_log_runtime.bind_main_window_dashboard_log_runtime(MainWindow)
main_window_dashboard_markets_runtime.bind_main_window_dashboard_markets_runtime(
    MainWindow,
    starter_crypto_exchanges=STARTER_CRYPTO_EXCHANGES,
    exchange_paths=EXCHANGE_PATHS,
    chart_interval_options=CHART_INTERVAL_OPTIONS,
    binance_supported_intervals=BINANCE_SUPPORTED_INTERVALS,
)
main_window_dashboard_state_runtime.bind_main_window_dashboard_state_runtime(
    MainWindow,
    load_position_allocations=_load_position_allocations,
)
main_window_dashboard_strategy_runtime.bind_main_window_dashboard_strategy_runtime(
    MainWindow,
    side_labels=SIDE_LABELS,
    dashboard_loop_choices=DASHBOARD_LOOP_CHOICES,
    lead_trader_options=LEAD_TRADER_OPTIONS,
    stop_loss_mode_order=STOP_LOSS_MODE_ORDER,
    stop_loss_mode_labels=STOP_LOSS_MODE_LABELS,
    stop_loss_scope_options=STOP_LOSS_SCOPE_OPTIONS,
    stop_loss_scope_labels=STOP_LOSS_SCOPE_LABELS,
    coerce_bool=coerce_bool,
    normalize_stop_loss_dict=normalize_stop_loss_dict,
)
main_window_dashboard_indicator_runtime.bind_main_window_dashboard_indicator_runtime(
    MainWindow,
    indicator_display_names=INDICATOR_DISPLAY_NAMES,
    param_dialog_cls=ParamDialog,
)
main_window_dashboard_actions_runtime.bind_main_window_dashboard_actions_runtime(
    MainWindow,
)
main_window_dashboard_chart_runtime.bind_main_window_dashboard_chart_runtime(
    MainWindow,
    qt_charts_available=QT_CHARTS_AVAILABLE,
)
main_window_dashboard_header_runtime.bind_main_window_dashboard_header_runtime(
    MainWindow,
    account_mode_options=ACCOUNT_MODE_OPTIONS,
    connector_options=CONNECTOR_OPTIONS,
    futures_connector_keys=FUTURES_CONNECTOR_KEYS,
    spot_connector_keys=SPOT_CONNECTOR_KEYS,
)
main_window_init_finalize_runtime.bind_main_window_init_finalize_runtime(
    MainWindow,
)
main_window_secondary_tabs_runtime.bind_main_window_secondary_tabs_runtime(
    MainWindow,
)
main_window_positions_tab.bind_main_window_positions_tab(
    MainWindow,
    coerce_bool=coerce_bool,
    pos_close_column=POS_CLOSE_COLUMN,
    positions_worker_cls=_PositionsWorker,
)
main_window_backtest_tab.bind_main_window_backtest_tab(
    MainWindow,
    mdd_logic_options=MDD_LOGIC_OPTIONS,
    mdd_logic_labels=MDD_LOGIC_LABELS,
    mdd_logic_default=MDD_LOGIC_DEFAULT,
    dashboard_loop_choices=DASHBOARD_LOOP_CHOICES,
    stop_loss_mode_order=STOP_LOSS_MODE_ORDER,
    stop_loss_scope_options=STOP_LOSS_SCOPE_OPTIONS,
    stop_loss_mode_labels=STOP_LOSS_MODE_LABELS,
    stop_loss_scope_labels=STOP_LOSS_SCOPE_LABELS,
    side_labels=SIDE_LABELS,
    account_mode_options=ACCOUNT_MODE_OPTIONS,
    backtest_template_definitions=BACKTEST_TEMPLATE_DEFINITIONS,
    backtest_template_default=BACKTEST_TEMPLATE_DEFAULT,
    indicator_display_names=INDICATOR_DISPLAY_NAMES,
    symbol_fetch_top_n=_SYMBOL_FETCH_TOP_N,
    normalize_stop_loss_dict=normalize_stop_loss_dict,
)
main_window_backtest_state_runtime.bind_main_window_backtest_state_runtime(
    MainWindow,
    backtest_interval_order=BACKTEST_INTERVAL_ORDER,
    side_labels=SIDE_LABELS,
    symbol_fetch_top_n=_SYMBOL_FETCH_TOP_N,
)
main_window_backtest_template_runtime.bind_main_window_backtest_template_runtime(
    MainWindow,
    mdd_logic_options=MDD_LOGIC_OPTIONS,
    mdd_logic_default=MDD_LOGIC_DEFAULT,
    backtest_template_definitions=BACKTEST_TEMPLATE_DEFINITIONS,
    backtest_template_default=BACKTEST_TEMPLATE_DEFAULT,
    indicator_display_names=INDICATOR_DISPLAY_NAMES,
    side_labels=SIDE_LABELS,
    normalize_connector_backend=_normalize_connector_backend,
    param_dialog_cls=ParamDialog,
)
main_window_backtest_execution_runtime.bind_main_window_backtest_execution_runtime(
    MainWindow,
    dbg_backtest_run=_DBG_BACKTEST_RUN,
    symbol_fetch_top_n=_SYMBOL_FETCH_TOP_N,
    normalize_stop_loss_dict=normalize_stop_loss_dict,
    backtest_worker_cls=_BacktestWorker,
)
main_window_chart_selection_runtime.bind_main_window_chart_selection_runtime(
    MainWindow,
    default_chart_symbols=DEFAULT_CHART_SYMBOLS,
    symbol_fetch_top_n=_SYMBOL_FETCH_TOP_N,
    tradingview_symbol_prefix=TRADINGVIEW_SYMBOL_PREFIX,
    tradingview_interval_map=TRADINGVIEW_INTERVAL_MAP,
)
main_window_chart_display_runtime.bind_main_window_chart_display_runtime(MainWindow)
main_window_control_runtime.bind_main_window_control_runtime(
    MainWindow,
    strategy_engine_cls=StrategyEngine,
    make_engine_key=_make_engine_key,
    coerce_bool=coerce_bool,
    normalize_stop_loss_dict=normalize_stop_loss_dict,
    format_indicator_list=_format_indicator_list,
    symbol_fetch_top_n=_SYMBOL_FETCH_TOP_N,
)
main_window_balance_runtime.bind_main_window_balance_runtime(
    MainWindow,
    normalize_connector_backend=_normalize_connector_backend,
)
main_window_indicator_runtime.bind_main_window_indicator_runtime(
    canonicalize_indicator_key=_canonicalize_indicator_key,
    normalize_connector_backend=_normalize_connector_backend,
    normalize_indicator_token=_normalize_indicator_token,
    normalize_indicator_values=_normalize_indicator_values,
    resolve_trigger_indicators=_resolve_trigger_indicators,
)
main_window_strategy_context_runtime.bind_main_window_strategy_context_runtime(
    MainWindow,
    side_label_lookup=SIDE_LABEL_LOOKUP,
    binance_interval_lower=BINANCE_INTERVAL_LOWER,
)
main_window_trade_runtime.bind_main_window_trade_runtime(
    MainWindow,
    resolve_trigger_indicators=_resolve_trigger_indicators,
    save_position_allocations=_save_position_allocations,
    normalize_trigger_actions_map=main_window_indicator_runtime._normalize_trigger_actions_map,
    max_closed_history=MAX_CLOSED_HISTORY,
)
main_window_positions.bind_main_window_positions(
    MainWindow,
    resolve_trigger_indicators=_resolve_trigger_indicators,
    max_closed_history=MAX_CLOSED_HISTORY,
    stop_strategy_sync=main_window_control_runtime._stop_strategy_sync,
    pos_status_column=POS_STATUS_COLUMN,
    save_position_allocations=_save_position_allocations,
    normalize_indicator_values=_normalize_indicator_values,
    derive_margin_snapshot=main_window_margin_runtime._derive_margin_snapshot,
    coerce_bool=coerce_bool,
    format_indicator_list=_format_indicator_list,
    collect_record_indicator_keys=main_window_indicator_runtime._collect_record_indicator_keys,
    collect_indicator_value_strings=main_window_indicator_runtime._collect_indicator_value_strings,
    collect_current_indicator_live_strings=main_window_indicator_runtime._collect_current_indicator_live_strings,
    dedupe_indicator_entries_normalized=main_window_indicator_runtime._dedupe_indicator_entries_normalized,
    numeric_item_cls=_NumericItem,
    pos_triggered_value_column=POS_TRIGGERED_VALUE_COLUMN,
    pos_current_value_column=POS_CURRENT_VALUE_COLUMN,
    pos_stop_loss_column=POS_STOP_LOSS_COLUMN,
    pos_close_column=POS_CLOSE_COLUMN,
)
main_window_backtest_results_runtime.bind_main_window_backtest_results_runtime(
    MainWindow,
    mdd_logic_labels=MDD_LOGIC_LABELS,
    normalize_loop_override=MainWindow._normalize_loop_override,
)
main_window_backtest_bridge_runtime.bind_main_window_backtest_bridge_runtime(
    MainWindow,
    dbg_backtest_dashboard=_DBG_BACKTEST_DASHBOARD,
    normalize_indicator_values=_normalize_indicator_values,
    normalize_stop_loss_dict=normalize_stop_loss_dict,
)
main_window_config.bind_main_window_config(
    MainWindow,
    normalize_stop_loss_dict=normalize_stop_loss_dict,
    qt_charts_available=QT_CHARTS_AVAILABLE,
    tradingview_supported=_tradingview_supported,
    language_paths=LANGUAGE_PATHS,
    exchange_paths=EXCHANGE_PATHS,
    forex_broker_paths=FOREX_BROKER_PATHS,
    lead_trader_options=LEAD_TRADER_OPTIONS,
)
main_window_code_runtime.bind_main_window_code_runtime(MainWindow)




main_window_code.bind_main_window_code(
    MainWindow,
    lazy_web_embed_cls=_LazyWebEmbed,
    starter_card_cls=_StarterCard,
    resolve_dependency_targets_for_config=_resolve_dependency_targets_for_config,
    launch_cpp_from_code_tab=main_window_code_runtime._launch_cpp_from_code_tab,
    launch_rust_from_code_tab=main_window_code_runtime._launch_rust_from_code_tab,
    refresh_code_language_card_release_labels=main_window_code_runtime._refresh_code_language_card_release_labels,
    refresh_dependency_usage_labels=_refresh_dependency_usage_labels,
    base_project_path=_BASE_PROJECT_PATH,
)
main_window_theme_runtime.bind_main_window_theme_runtime(MainWindow)







