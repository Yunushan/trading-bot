from __future__ import annotations

import copy
import hashlib
import os
import sys
import json
import math
import platform
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
from PyQt6 import QtCore, QtWidgets
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
from app.gui.shared.param_dialog import ParamDialog
from app.gui.backtest.backtest_templates import BACKTEST_TEMPLATE_DEFINITIONS
from app.gui.backtest import (
    main_window_backtest_bridge_runtime,
    main_window_backtest_execution_runtime,
    main_window_backtest_results_runtime,
    main_window_backtest_runtime,
    main_window_backtest_state_runtime,
    main_window_backtest_tab,
    main_window_backtest_template_runtime,
)
from app.gui.chart import (
    chart_embed,
    main_window_chart_display_runtime,
    main_window_chart_host_runtime,
    main_window_chart_selection_runtime,
    main_window_chart_tab,
    main_window_chart_view_runtime,
)
from app.gui.chart.chart_widgets import InteractiveChartView, SimpleCandlestickWidget
from app.gui.code import (
    code_language_build,
    code_language_launch,
    code_language_launcher,
    code_language_runtime,
    code_language_status,
    code_language_ui,
    dependency_versions_runtime,
    dependency_versions_ui,
    main_window_code,
    main_window_code_runtime,
)
from app.gui.dashboard import (
    main_window_dashboard_actions_runtime,
    main_window_dashboard_chart_runtime,
    main_window_dashboard_header_runtime,
    main_window_dashboard_indicator_runtime,
    main_window_dashboard_log_runtime,
    main_window_dashboard_markets_runtime,
    main_window_dashboard_state_runtime,
    main_window_dashboard_strategy_runtime,
)
from app.gui.runtime import (
    main_window_account_runtime,
    main_window_balance_runtime,
    main_window_bootstrap_runtime,
    main_window_control_runtime,
    main_window_indicator_runtime,
    main_window_init_finalize_runtime,
    main_window_margin_runtime,
    main_window_override_runtime,
    main_window_runtime,
    main_window_secondary_tabs_runtime,
    main_window_session_runtime,
    main_window_status_runtime,
    main_window_stop_loss_runtime,
    main_window_strategy_context_runtime,
    main_window_strategy_controls_runtime,
    main_window_strategy_ui_runtime,
    main_window_tab_runtime,
    main_window_theme_runtime,
    main_window_ui_misc_runtime,
    window_runtime,
)
from app.gui.shared import (
    allocation_persistence,
    main_window_config,
    main_window_helper_runtime,
    main_window_ui_support,
    main_window_web_embed,
)
from app.gui.trade import main_window_trade_runtime
from app.gui.positions import (
    main_window_positions,
    main_window_positions_tab,
    main_window_positions_worker,
)
from app.gui.shared.main_window_config import _load_app_state_file, _save_app_state_file
from app.gui.chart.chart_embed import (
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
from app.gui.code.code_language_catalog import (
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
        self._initialize_main_window_state()

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
                delay_raw = os.environ.get("BOT_WINDOW_ICON_RETRY_MS")
                delay_ms = int(delay_raw) if delay_raw is not None else 0
            except Exception:
                delay_ms = 0
            if delay_ms > 0:
                QtCore.QTimer.singleShot(delay_ms, lambda w=self: _apply_window_icon(w))
        root_layout = QtWidgets.QVBoxLayout(self)
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.tabs.tabBarClicked.connect(self._on_tab_bar_clicked)
        try:
            self._store_previous_main_window_event_filter()
            self.tabs.tabBar().installEventFilter(self)
        except Exception:
            pass
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
main_window_bootstrap_runtime.bind_main_window_bootstrap_runtime(
    MainWindow,
    app_state_path=APP_STATE_PATH,
    load_app_state_file=_load_app_state_file,
    normalize_connector_backend=_normalize_connector_backend,
    default_connector_backend=DEFAULT_CONNECTOR_BACKEND,
    chart_market_options=CHART_MARKET_OPTIONS,
    disable_tradingview=_DISABLE_TRADINGVIEW,
    disable_charts=_DISABLE_CHARTS,
    enable_chart_tab=ENABLE_CHART_TAB,
    tradingview_supported=_tradingview_supported,
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
main_window_session_runtime.bind_main_window_session_runtime(
    MainWindow,
    default_connector_backend=DEFAULT_CONNECTOR_BACKEND,
    normalize_connector_backend=_normalize_connector_backend,
    save_app_state_file=_save_app_state_file,
)
main_window_strategy_ui_runtime.bind_main_window_strategy_ui_runtime(
    MainWindow,
    account_mode_options=ACCOUNT_MODE_OPTIONS,
    stop_loss_scope_options=STOP_LOSS_SCOPE_OPTIONS,
)
main_window_ui_misc_runtime.bind_main_window_ui_misc_runtime(MainWindow)
main_window_override_runtime.bind_main_window_override_runtime(
    MainWindow,
    format_indicator_list=_format_indicator_list,
    normalize_connector_backend=_normalize_connector_backend,
    normalize_indicator_values=_normalize_indicator_values,
    normalize_stop_loss_dict=normalize_stop_loss_dict,
)
main_window_status_runtime.bind_main_window_status_runtime(MainWindow)
main_window_stop_loss_runtime.bind_main_window_stop_loss_runtime(
    MainWindow,
    normalize_stop_loss_dict=normalize_stop_loss_dict,
    stop_loss_mode_order=STOP_LOSS_MODE_ORDER,
    stop_loss_scope_options=STOP_LOSS_SCOPE_OPTIONS,
)
main_window_strategy_controls_runtime.bind_main_window_strategy_controls_runtime(
    MainWindow,
    side_labels=SIDE_LABELS,
    normalize_stop_loss_dict=normalize_stop_loss_dict,
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







