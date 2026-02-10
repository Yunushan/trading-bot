from __future__ import annotations

import copy
import os
import sys
import json
import math
import re
import threading
import time
import traceback
import concurrent.futures
import importlib.metadata as importlib_metadata
import urllib.request
import urllib.parse
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
from app.gui.app_icon import load_app_icon
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

# Lazy import TradingView to avoid spawning QtWebEngine helper windows during startup.
TradingViewWidget = None  # type: ignore[assignment]
TRADINGVIEW_EMBED_AVAILABLE = False
_TRADINGVIEW_IMPORT_ERROR = None
_TRADINGVIEW_ENV_CONFIGURED = False
_TRADINGVIEW_EXTERNAL_PREFERRED = None
BinanceWebWidget = None  # type: ignore[assignment]
BINANCE_WEB_AVAILABLE = False
_BINANCE_IMPORT_ERROR = None
LightweightChartWidget = None  # type: ignore[assignment]
LIGHTWEIGHT_CHART_AVAILABLE = False
_LIGHTWEIGHT_IMPORT_ERROR = None
_WEBENGINE_DISABLED_REASON = (
    "WebEngine charts are disabled on Windows. "
    "Unset BOT_DISABLE_WEBENGINE_CHARTS or set it to 0 to enable."
)
_DEFAULT_WEB_UA = os.environ.get(
    "BOT_WEBENGINE_UA",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
)


def _native_chart_host_prewarm_enabled() -> bool:
    """Whether to pre-create native window handles for chart hosts."""
    if sys.platform != "win32":
        return True
    flag = str(os.environ.get("BOT_PRIME_NATIVE_CHART_HOST", "0")).strip().lower()
    return flag in {"1", "true", "yes", "on"}


def _apply_window_icon(window) -> None:
    try:
        icon = load_app_icon()
    except Exception:
        icon = QtGui.QIcon()
    if icon.isNull():
        return
    try:
        window.setWindowIcon(icon)
    except Exception:
        pass
    try:
        QtGui.QGuiApplication.setWindowIcon(icon)
    except Exception:
        pass
    try:
        handle = window.windowHandle()
    except Exception:
        handle = None
    if handle is not None:
        try:
            handle.setIcon(icon)
        except Exception:
            pass


def _configure_tradingview_webengine_env() -> None:
    """Best-effort tweaks to stabilize QtWebEngine on Windows before importing it."""
    global _TRADINGVIEW_ENV_CONFIGURED
    if _TRADINGVIEW_ENV_CONFIGURED:
        return
    _TRADINGVIEW_ENV_CONFIGURED = True
    if sys.platform != "win32":
        return
    flag = str(os.environ.get("BOT_TRADINGVIEW_DISABLE_GPU", "")).strip().lower()
    if flag:
        disable_gpu = flag in {"1", "true", "yes", "on"}
    else:
        force_gpu = str(os.environ.get("BOT_TRADINGVIEW_FORCE_GPU", "")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if force_gpu:
            disable_gpu = False
        else:
            disable_gpu = False
    flags = str(os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "") or "").strip()
    parts = [part for part in flags.split() if part]
    # Always strip known unstable/global flags that can interfere with the app window.
    base_cleaned = []
    for part in parts:
        lower = part.lower()
        if part in {"--single-process", "--in-process-gpu"}:
            continue
        if lower.startswith("--window-position="):
            continue
        base_cleaned.append(part)
    if base_cleaned != parts:
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(base_cleaned).strip()
    parts = list(base_cleaned)
    if not disable_gpu:
        return
    drop_flags = {
        "--ignore-gpu-blocklist",
        "--enable-zero-copy",
        "--disable-software-rasterizer",
        "--in-process-gpu",
        "--single-process",
    }
    cleaned = []
    for part in parts:
        lower = part.lower()
        if part in drop_flags:
            continue
        if lower.startswith("--use-gl=") or lower.startswith("--use-angle="):
            continue
        if lower.startswith("--enable-gpu"):
            continue
        if lower.startswith("--enable-features=") and ("vulkan" in lower or "useskiarenderer" in lower):
            continue
        cleaned.append(part)
    required = [
        "--disable-gpu",
        "--disable-gpu-compositing",
        "--disable-features=Vulkan,UseSkiaRenderer",
    ]
    use_swiftshader = str(os.environ.get("BOT_TRADINGVIEW_USE_SWIFTSHADER", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if use_swiftshader:
        required.append("--use-gl=swiftshader")
    for part in required:
        if part not in cleaned:
            cleaned.append(part)
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(cleaned).strip()
    os.environ["QTWEBENGINE_DISABLE_GPU"] = "1"
    os.environ.setdefault("QT_OPENGL", "software")
    os.environ.setdefault("QSG_RHI_BACKEND", "software")
    os.environ.setdefault("QT_QUICK_BACKEND", "software")


def _webengine_charts_allowed() -> bool:
    if sys.platform != "win32":
        return True
    flag = str(os.environ.get("BOT_DISABLE_WEBENGINE_CHARTS", "")).strip().lower()
    if flag:
        return flag not in {"1", "true", "yes", "on"}
    return True


def _chart_safe_mode_enabled() -> bool:
    flag = str(os.environ.get("BOT_SAFE_CHART_TAB", "")).strip().lower()
    if flag:
        return flag in {"1", "true", "yes", "on"}
    if sys.platform == "win32":
        return False
    try:
        return bool(os.name == "posix" and hasattr(os, "geteuid") and os.geteuid() == 0)
    except Exception:
        return False

def _resolve_dist_version(*names: str) -> str | None:
    for name in names:
        try:
            return importlib_metadata.version(name)
        except Exception:
            continue
    return None

def _tradingview_embed_health() -> tuple[bool, str]:
    if sys.platform != "win32":
        return True, ""
    pyqt_ver = _resolve_dist_version("PyQt6", "pyqt6")
    web_ver = _resolve_dist_version("PyQt6-WebEngine", "pyqt6-webengine", "PyQt6_WebEngine")
    if pyqt_ver and web_ver:
        pyqt_norm = pyqt_ver.split("+", 1)[0]
        web_norm = web_ver.split("+", 1)[0]
        if pyqt_norm != web_norm:
            return False, f"TradingView embed disabled: PyQt6 {pyqt_ver} and PyQt6-WebEngine {web_ver} must match."
    exec_dir = ""
    try:
        exec_dir = QtCore.QLibraryInfo.path(QtCore.QLibraryInfo.LibraryPath.LibraryExecutablesPath)
    except Exception:
        try:
            exec_dir = QtCore.QLibraryInfo.location(QtCore.QLibraryInfo.LibraryLocation.LibraryExecutablesPath)
        except Exception:
            exec_dir = ""
    if exec_dir:
        exe_name = "QtWebEngineProcess.exe" if sys.platform == "win32" else "QtWebEngineProcess"
        exe_path = Path(exec_dir) / exe_name
        if not exe_path.is_file():
            return False, f"TradingView embed disabled: {exe_name} not found in {exec_dir}."
    return True, ""

def _webengine_embed_health() -> tuple[bool, str]:
    ok, reason = _tradingview_embed_health()
    if ok:
        return True, ""
    if reason:
        reason = reason.replace("TradingView", "WebEngine")
    return False, reason

def _webengine_embed_unavailable_reason() -> str | None:
    if _DISABLE_CHARTS:
        return "Charts disabled. Set BOT_DISABLE_CHARTS=0 to enable web embeds."
    if _chart_safe_mode_enabled():
        return "Web embeds disabled for stability. Set BOT_SAFE_CHART_TAB=0 to enable."
    if sys.platform == "win32" and not _webengine_charts_allowed():
        return _WEBENGINE_DISABLED_REASON
    ok, reason = _webengine_embed_health()
    if not ok:
        return reason or "WebEngine embed unavailable."
    return None

def _tradingview_unavailable_reason() -> str:
    if sys.platform == "win32" and not _webengine_charts_allowed():
        return _WEBENGINE_DISABLED_REASON
    err = _TRADINGVIEW_IMPORT_ERROR
    if err is not None:
        return str(err)
    return "TradingView embed unavailable."

def _binance_unavailable_reason() -> str:
    if sys.platform == "win32" and not _webengine_charts_allowed():
        return _WEBENGINE_DISABLED_REASON
    err = _BINANCE_IMPORT_ERROR
    if err is not None:
        return str(err)
    return "Binance web embed unavailable."

def _lightweight_unavailable_reason() -> str:
    if sys.platform == "win32" and not _webengine_charts_allowed():
        return _WEBENGINE_DISABLED_REASON
    err = _LIGHTWEIGHT_IMPORT_ERROR
    if err is not None:
        return str(err)
    return "Lightweight chart embed unavailable."

def _load_tradingview_widget():
    """Import TradingViewWidget only when the chart tab is needed."""
    global TradingViewWidget, TRADINGVIEW_EMBED_AVAILABLE, _TRADINGVIEW_IMPORT_ERROR
    if _DISABLE_TRADINGVIEW or _DISABLE_CHARTS:
        return None, False
    if sys.platform == "win32" and not _webengine_charts_allowed():
        if _TRADINGVIEW_IMPORT_ERROR is None:
            _TRADINGVIEW_IMPORT_ERROR = RuntimeError(_WEBENGINE_DISABLED_REASON)
        return None, False
    _configure_tradingview_webengine_env()
    if TradingViewWidget is not None or _TRADINGVIEW_IMPORT_ERROR is not None:
        return TradingViewWidget, TRADINGVIEW_EMBED_AVAILABLE
    ok, reason = _tradingview_embed_health()
    if not ok:
        _TRADINGVIEW_IMPORT_ERROR = RuntimeError(reason)
        TradingViewWidget = None  # type: ignore[assignment]
        TRADINGVIEW_EMBED_AVAILABLE = False
        return TradingViewWidget, TRADINGVIEW_EMBED_AVAILABLE
    try:
        from app.gui.tradingview_widget import TradingViewWidget as _TVW, TRADINGVIEW_EMBED_AVAILABLE as _EMBED  # type: ignore
    except Exception as exc:
        _TRADINGVIEW_IMPORT_ERROR = exc
        TradingViewWidget = None  # type: ignore[assignment]
        TRADINGVIEW_EMBED_AVAILABLE = False
        return TradingViewWidget, TRADINGVIEW_EMBED_AVAILABLE
    TradingViewWidget = _TVW  # type: ignore[assignment]
    TRADINGVIEW_EMBED_AVAILABLE = bool(_EMBED and _TVW is not None)
    return TradingViewWidget, TRADINGVIEW_EMBED_AVAILABLE

def _load_binance_widget():
    """Import BinanceWebWidget only when the chart tab is needed."""
    global BinanceWebWidget, BINANCE_WEB_AVAILABLE, _BINANCE_IMPORT_ERROR
    if _DISABLE_CHARTS:
        return None, False
    if sys.platform == "win32" and not _webengine_charts_allowed():
        if _BINANCE_IMPORT_ERROR is None:
            _BINANCE_IMPORT_ERROR = RuntimeError(_WEBENGINE_DISABLED_REASON)
        return None, False
    _configure_tradingview_webengine_env()
    if BinanceWebWidget is not None or _BINANCE_IMPORT_ERROR is not None:
        return BinanceWebWidget, BINANCE_WEB_AVAILABLE
    ok, reason = _tradingview_embed_health()
    if not ok:
        _BINANCE_IMPORT_ERROR = RuntimeError(reason)
        BinanceWebWidget = None  # type: ignore[assignment]
        BINANCE_WEB_AVAILABLE = False
        return BinanceWebWidget, BINANCE_WEB_AVAILABLE
    try:
        from app.gui.binance_web_widget import BinanceWebWidget as _BW  # type: ignore
    except Exception as exc:
        _BINANCE_IMPORT_ERROR = exc
        BinanceWebWidget = None  # type: ignore[assignment]
        BINANCE_WEB_AVAILABLE = False
        return BinanceWebWidget, BINANCE_WEB_AVAILABLE
    BinanceWebWidget = _BW  # type: ignore[assignment]
    BINANCE_WEB_AVAILABLE = bool(_BW is not None)
    return BinanceWebWidget, BINANCE_WEB_AVAILABLE

def _load_lightweight_widget():
    """Import LightweightChartWidget only when the chart tab is needed."""
    global LightweightChartWidget, LIGHTWEIGHT_CHART_AVAILABLE, _LIGHTWEIGHT_IMPORT_ERROR
    if _DISABLE_CHARTS:
        return None, False
    if sys.platform == "win32" and not _webengine_charts_allowed():
        if _LIGHTWEIGHT_IMPORT_ERROR is None:
            _LIGHTWEIGHT_IMPORT_ERROR = RuntimeError(_WEBENGINE_DISABLED_REASON)
        return None, False
    _configure_tradingview_webengine_env()
    if LightweightChartWidget is not None or _LIGHTWEIGHT_IMPORT_ERROR is not None:
        return LightweightChartWidget, LIGHTWEIGHT_CHART_AVAILABLE
    ok, reason = _tradingview_embed_health()
    if not ok:
        _LIGHTWEIGHT_IMPORT_ERROR = RuntimeError(reason)
        LightweightChartWidget = None  # type: ignore[assignment]
        LIGHTWEIGHT_CHART_AVAILABLE = False
        return LightweightChartWidget, LIGHTWEIGHT_CHART_AVAILABLE
    try:
        from app.gui.lightweight_widget import LightweightChartWidget as _LW  # type: ignore
    except Exception as exc:
        _LIGHTWEIGHT_IMPORT_ERROR = exc
        LightweightChartWidget = None  # type: ignore[assignment]
        LIGHTWEIGHT_CHART_AVAILABLE = False
        return LightweightChartWidget, LIGHTWEIGHT_CHART_AVAILABLE
    LightweightChartWidget = _LW  # type: ignore[assignment]
    LIGHTWEIGHT_CHART_AVAILABLE = bool(_LW is not None)
    return LightweightChartWidget, LIGHTWEIGHT_CHART_AVAILABLE

def _tradingview_supported(*, probe: bool = False) -> bool:
    if _DISABLE_TRADINGVIEW or _DISABLE_CHARTS:
        return False
    if TradingViewWidget is not None and TRADINGVIEW_EMBED_AVAILABLE:
        return True
    if _TRADINGVIEW_IMPORT_ERROR is not None:
        return False
    if not probe:
        return False
    tvw, available = _load_tradingview_widget()
    return bool(available and tvw is not None)

def _binance_supported(*, probe: bool = False) -> bool:
    if _DISABLE_CHARTS:
        return False
    if BinanceWebWidget is not None and BINANCE_WEB_AVAILABLE:
        return True
    if _BINANCE_IMPORT_ERROR is not None:
        return False
    if not probe:
        return False
    bw, available = _load_binance_widget()
    return bool(available and bw is not None)

def _lightweight_supported(*, probe: bool = False) -> bool:
    if _DISABLE_CHARTS:
        return False
    if LightweightChartWidget is not None and LIGHTWEIGHT_CHART_AVAILABLE:
        return True
    if _LIGHTWEIGHT_IMPORT_ERROR is not None:
        return False
    if not probe:
        return False
    lw, available = _load_lightweight_widget()
    return bool(available and lw is not None)

def _tradingview_external_preferred() -> bool:
    global _TRADINGVIEW_EXTERNAL_PREFERRED
    if _TRADINGVIEW_EXTERNAL_PREFERRED is not None:
        return bool(_TRADINGVIEW_EXTERNAL_PREFERRED)
    flag = str(os.environ.get("BOT_TRADINGVIEW_EXTERNAL", "")).strip().lower()
    if flag:
        _TRADINGVIEW_EXTERNAL_PREFERRED = flag in {"1", "true", "yes", "on"}
        return bool(_TRADINGVIEW_EXTERNAL_PREFERRED)
    _TRADINGVIEW_EXTERNAL_PREFERRED = False
    return False

def _build_tradingview_url(symbol: str, interval: str) -> str:
    params = urllib.parse.urlencode({"symbol": symbol, "interval": interval}, safe=":")
    return f"https://www.tradingview.com/chart/?{params}"

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

def _load_app_state_file(path: Path) -> dict:
    try:
        if path.is_file():
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}

def _save_app_state_file(path: Path, data: dict) -> None:
    try:
        if not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    except Exception:
        pass

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

RECOMMENDED_CONNECTOR_BY_ACCOUNT = {
    "FUTURES": "binance-sdk-derivatives-trading-usds-futures",
    "SPOT": "binance-sdk-spot",
}

def _normalize_connector_backend(value) -> str:
    text_raw = str(value or "").strip()
    if not text_raw:
        return DEFAULT_CONNECTOR_BACKEND
    text = text_raw.lower()
    if text in {
        "binance-sdk-derivatives-trading-usds-futures",
        "binance_sdk_derivatives_trading_usds_futures",
    } or ("sdk" in text and "future" in text and ("usd" in text or "usds" in text)):
        return "binance-sdk-derivatives-trading-usds-futures"
    if text in {
        "binance-sdk-derivatives-trading-coin-futures",
        "binance_sdk_derivatives_trading_coin_futures",
    } or ("sdk" in text and "coin" in text and "future" in text):
        return "binance-sdk-derivatives-trading-coin-futures"
    if text in {"binance-sdk-spot", "binance_sdk_spot"} or ("sdk" in text and "spot" in text):
        return "binance-sdk-spot"
    if text == "ccxt" or "ccxt" in text:
        return "ccxt"
    if "connector" in text or "official" in text or text == "binance-connector":
        return "binance-connector"
    if "python" in text and "binance" in text:
        return "python-binance"
    return DEFAULT_CONNECTOR_BACKEND

def _recommended_connector_for_key(account_key: str) -> str:
    key = (account_key or "").strip().upper()
    return RECOMMENDED_CONNECTOR_BY_ACCOUNT.get(key, DEFAULT_CONNECTOR_BACKEND)

for _parent in _THIS_FILE.parents:
    if (_parent / "Languages").exists():
        _BASE_PROJECT_PATH = _parent
        break
else:
    _BASE_PROJECT_PATH = _THIS_FILE.parents[2]

# Startup knobs to avoid slow/flashy QtWebEngine init on Windows
_DISABLE_CHARTS = str(os.environ.get("BOT_DISABLE_CHARTS", "")).strip().lower() in {"1", "true", "yes", "on"}
_DISABLE_TRADINGVIEW = str(os.environ.get("BOT_DISABLE_TRADINGVIEW", "")).strip().lower() in {"1", "true", "yes", "on"}
try:
    _SYMBOL_FETCH_TOP_N = int(os.environ.get("BOT_SYMBOL_FETCH_TOP_N") or 200)
except Exception:
    _SYMBOL_FETCH_TOP_N = 200
_SYMBOL_FETCH_TOP_N = max(50, min(_SYMBOL_FETCH_TOP_N, 5000))

LANGUAGE_PATHS = {
    "Python (PyQt)": "Languages/Python",
    "C++ (Qt/C++23)": "Languages/C++",
    "C": "Languages/C",
    "Rust": "Languages/Rust",
}

EXCHANGE_PATHS = {
    "Binance": None,
    "Bybit": None,
    "OKX": None,
    "Bitget": None,
    "Gate": None,
    "MEXC": None,
    "KuCoin": None,
    "HTX": None,
    "Crypto.com Exchange": None,
    "Kraken": None,
    "Bitfinex": None,
}

FOREX_BROKER_PATHS: dict[str, str | None] = {}
MUTED_TEXT = "#94a3b8"

STARTER_LANGUAGE_OPTIONS = [
    {
        "config_key": "Python (PyQt)",
        "title": "Python",
        "subtitle": "Fast to build - Huge ecosystem",
        "accent": "#3b82f6",
        "badge": "Recommended",
    },
    {
        "config_key": "C++ (Qt/C++23)",
        "title": "C++",
        "subtitle": "Qt native desktop (preview)",
        "accent": "#38bdf8",
        "badge": "Preview",
    },
    {
        "config_key": "Rust",
        "title": "Rust",
        "subtitle": "Memory safe - coming soon",
        "accent": "#fb923c",
        "badge": "Coming Soon",
        "disabled": True,
    },
    {
        "config_key": "C",
        "title": "C",
        "subtitle": "Low-level power - coming soon",
        "accent": "#f87171",
        "badge": "Coming Soon",
        "disabled": True,
    },
]

STARTER_MARKET_OPTIONS = [
    {"key": "crypto", "title": "Crypto Exchange", "subtitle": "Binance, Bybit, KuCoin", "accent": "#34d399"},
    {
        "key": "forex",
        "title": "Forex Exchange",
        "subtitle": "OANDA, FXCM, MetaTrader - coming soon",
        "accent": "#93c5fd",
        "badge": "Coming Soon",
        "disabled": True,
    },
]

STARTER_CRYPTO_EXCHANGES = [
    {"key": "Binance", "title": "Binance", "subtitle": "Advanced desktop bot ready to launch", "accent": "#fbbf24"},
    {
        "key": "Bybit",
        "title": "Bybit",
        "subtitle": "Advanced desktop bot ready to launch",
        "accent": "#fb7185",
        "badge": "coming soon",
        "disabled": True,
    },
    {
        "key": "OKX",
        "title": "OKX",
        "subtitle": "Advanced desktop bot ready to launch",
        "accent": "#a78bfa",
        "badge": "coming soon",
        "disabled": True,
    },
    {
        "key": "Gate",
        "title": "Gate",
        "subtitle": "Advanced desktop bot ready to launch",
        "accent": "#22c55e",
        "badge": "coming soon",
        "disabled": True,
    },
    {
        "key": "Bitget",
        "title": "Bitget",
        "subtitle": "Advanced desktop bot ready to launch",
        "accent": "#0ea5e9",
        "badge": "coming soon",
        "disabled": True,
    },
    {
        "key": "MEXC",
        "title": "MEXC",
        "subtitle": "Advanced desktop bot ready to launch",
        "accent": "#10b981",
        "badge": "coming soon",
        "disabled": True,
    },
    {
        "key": "KuCoin",
        "title": "KuCoin",
        "subtitle": "Advanced desktop bot ready to launch",
        "accent": "#eab308",
        "badge": "coming soon",
        "disabled": True,
    },
]

STARTER_FOREX_BROKERS = [
    {
        "key": "OANDA",
        "title": "OANDA",
        "subtitle": "Popular REST API - coming soon",
        "accent": "#60a5fa",
        "badge": "Coming Soon",
        "disabled": True,
    },
    {
        "key": "FXCM",
        "title": "FXCM",
        "subtitle": "Streaming quotes - coming soon",
        "accent": "#c084fc",
        "badge": "Coming Soon",
        "disabled": True,
    },
    {
        "key": "IG",
        "title": "IG",
        "subtitle": "Global CFD trading - coming soon",
        "accent": "#f472b6",
        "badge": "Coming Soon",
        "disabled": True,
    },
]

_REQUIREMENTS_PATHS = [
    _THIS_FILE.parents[2] / "requirements.txt",
    _THIS_FILE.parents[3] / "requirements.txt",
]

_DEFAULT_DEPENDENCY_VERSION_TARGETS = [
    {"label": "python-binance", "package": "python-binance"},
    {"label": "binance-connector", "package": "binance-connector"},
    {"label": "ccxt", "package": "ccxt"},
    {"label": "PyQt6", "package": "PyQt6"},
    {"label": "PyQt6-Qt6", "package": "PyQt6-Qt6"},
    {"label": "PyQt6-WebEngine", "package": "PyQt6-WebEngine"},
    {"label": "numba", "package": "numba"},
    {"label": "llvmlite", "package": "llvmlite"},
    {"label": "numpy", "package": "numpy"},
    {"label": "pandas", "package": "pandas"},
    {"label": "pandas-ta", "package": "pandas-ta"},
    {"label": "requests", "package": "requests"},
    {"label": "binance-sdk-derivatives-trading-usds-futures", "package": "binance-sdk-derivatives-trading-usds-futures"},
    {"label": "binance-sdk-derivatives-trading-coin-futures", "package": "binance-sdk-derivatives-trading-coin-futures"},
    {"label": "binance-sdk-spot", "package": "binance-sdk-spot"},
]


def _extract_requirement_name(line: str) -> str | None:
    stripped = (line or "").strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith(("-", "--")):
        return None
    if "#" in stripped:
        stripped = stripped.split("#", 1)[0].strip()
    if not stripped:
        return None
    separators = ("==", ">=", "<=", "~=", "!=", "===", "<", ">", "@")
    name_part = stripped
    for sep in separators:
        if sep in stripped:
            name_part = stripped.split(sep, 1)[0].strip()
            break
    if "[" in name_part:
        name_part = name_part.split("[", 1)[0].strip()
    return name_part or None


def _iter_candidate_requirement_paths(config: dict | None = None) -> list[Path]:
    candidates: list[Path] = []
    seen: set[Path] = set()

    def _add(path: Path | None):
        if path is None:
            return
        try:
            resolved = Path(path).resolve()
        except Exception:
            return
        if resolved in seen:
            return
        seen.add(resolved)
        candidates.append(resolved)

    base_path = _BASE_PROJECT_PATH
    _add(base_path / "requirements.txt")
    lang_rel = None
    exch_rel = None
    forex_rel = None
    try:
        if config:
            lang_rel = LANGUAGE_PATHS.get(config.get("code_language"))
            exch_rel = EXCHANGE_PATHS.get(config.get("selected_exchange"))
            forex_rel = FOREX_BROKER_PATHS.get(config.get("selected_forex_broker"))
    except Exception:
        lang_rel = exch_rel = forex_rel = None

    if lang_rel:
        _add(base_path / lang_rel / "requirements.txt")
        if exch_rel:
            _add(base_path / lang_rel / exch_rel / "requirements.txt")
        if forex_rel:
            _add(base_path / lang_rel / forex_rel / "requirements.txt")
    if exch_rel:
        _add(base_path / exch_rel / "requirements.txt")

    for legacy in _REQUIREMENTS_PATHS:
        _add(legacy)

    return candidates


def _dependency_targets_from_requirements(paths: list[Path] | None = None) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    seen: set[str] = set()
    paths_to_check = paths or _REQUIREMENTS_PATHS
    for path in paths_to_check:
        if not path.is_file():
            continue
        try:
            with path.open("r", encoding="utf-8") as fh:
                for raw_line in fh:
                    pkg_name = _extract_requirement_name(raw_line)
                    if not pkg_name or pkg_name in seen:
                        continue
                    entries.append({"label": pkg_name, "package": pkg_name})
                    seen.add(pkg_name)
        except Exception:
            continue
    if not entries:
        return copy.deepcopy(_DEFAULT_DEPENDENCY_VERSION_TARGETS)
    return entries


DEPENDENCY_VERSION_TARGETS = _dependency_targets_from_requirements()

def _latest_version_from_pypi(package: str, timeout: float = 8.0) -> str | None:
    if not package:
        return None
    cache_entry = _LATEST_VERSION_CACHE.get(package)
    now = time.time()
    if cache_entry and now - cache_entry[1] < 1800:
        return cache_entry[0]
    url = f"https://pypi.org/pypi/{package}/json"
    timeout_val = max(2.0, float(timeout or 8.0))
    latest = None

    # Preferred: requests with verification (respects proxies)
    try:
        import requests  # type: ignore

        resp = requests.get(url, timeout=timeout_val, headers={"User-Agent": "trading-bot-starter/1.0"})
        if resp.status_code == 200:
            payload = resp.json()
            latest = payload.get("info", {}).get("version")
    except Exception:
        pass

    # Fallback: requests with verify=False (for environments with intercepting proxies)
    if latest is None:
        try:
            import requests  # type: ignore

            resp = requests.get(
                url,
                timeout=timeout_val,
                headers={"User-Agent": "trading-bot-starter/1.0"},
                verify=False,  # noqa: S501
            )
            if resp.status_code == 200:
                payload = resp.json()
                latest = payload.get("info", {}).get("version")
        except Exception:
            pass

    # Final fallback: urllib without verification
    if latest is None:
        try:
            import ssl

            req = urllib.request.Request(url, headers={"User-Agent": "trading-bot-starter/1.0"})
            ctx = ssl.create_default_context()
            try:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            except Exception:
                pass
            with urllib.request.urlopen(req, timeout=timeout_val, context=ctx) as resp:
                payload = json.load(resp)
                latest = payload.get("info", {}).get("version")
        except Exception:
            latest = None

    if latest:
        _LATEST_VERSION_CACHE[package] = (latest, now)
        return latest
    return None

BACKTEST_TEMPLATE_DEFINITIONS = {
    "volume_top50": {
        "label": "First 50 Highest Volume",
        "intervals": [
            "1m",
            "3m",
            "5m",
            "10m",
            "15m",
            "20m",
            "30m",
            "1h",
            "2h",
            "3h",
            "4h",
            "5h",
            "6h",
            "7h",
            "8h",
            "9h",
            "10h",
            "11h",
            "12h",
            "1d",
            "3d",
            "2d",
            "4d",
            "5d",
            "6d",
            "1w",
        ],
        "logic": "SEPARATE",
        "position_pct": 2.0,
        "side": "BOTH",
        "stop_loss": {
            "enabled": True,
            "mode": "percent",
            "percent": 30.0,
            "usdt": 0.0,
            "scope": "per_trade",
        },
        "date_range": {"months": 1},
        "indicators": {
            "rsi": {"enabled": True, "buy_value": 30, "sell_value": 70},
            "stoch_rsi": {"enabled": True, "buy_value": 20, "sell_value": 80},
            "willr": {"enabled": True, "buy_value": -80, "sell_value": -20},
        },
        "margin_mode": "Isolated",
        "position_mode": "Hedge",
        "assets_mode": "Single-Asset",
        "account_mode": "Classic Trading",
        "leverage": 20,
        "mdd_logic": "per_trade",
        "loop_interval_override": "30s",
        "symbol_selection": {
            "type": "top_volume",
            "count": 50,
            "source": "Futures",
        },
    },
    "volume_last_week": {
        "label": "Last 1 week · 2% per trade · 50 highest volume",
        "intervals": [
            "1m",
            "3m",
            "5m",
            "10m",
            "15m",
            "20m",
            "30m",
            "1h",
            "2h",
            "3h",
            "4h",
            "6h",
            "8h",
            "12h",
            "1d",
        ],
        "logic": "SEPARATE",
        "position_pct": 2.0,
        "side": "BOTH",
        "loop_interval_override": "30s",
        "stop_loss": {
            "enabled": True,
            "mode": "percent",
            "percent": 20.0,
            "scope": "per_trade",
        },
        "date_range": {"days": 7},
        "indicators": {
            "rsi": {"enabled": True, "buy_value": 30, "sell_value": 70},
            "stoch_rsi": {"enabled": True, "buy_value": 20, "sell_value": 80},
            "willr": {"enabled": True, "buy_value": -80, "sell_value": -20},
        },
        "margin_mode": "Isolated",
        "position_mode": "Hedge",
        "assets_mode": "Single-Asset",
        "account_mode": "Classic Trading",
        "leverage": 20,
        "mdd_logic": "entire_account",
        "connector_backend": "binance-connector",
        "symbol_selection": {
            "type": "top_volume",
            "count": 50,
            "source": "Futures",
        },
    },
    "top100_isolated_1pct_sl": {
        "label": "Top 100, %2 per trade, isolated, %20 (%1 Actual Move) per trade SL",
        "intervals": [
            "1m",
            "3m",
            "5m",
            "10m",
            "15m",
            "20m",
            "30m",
            "1h",
            "2h",
            "3h",
            "4h",
            "5h",
            "6h",
            "7h",
            "8h",
            "9h",
            "10h",
            "11h",
            "12h",
            "1d",
            "2d",
            "3d",
            "4d",
            "5d",
            "6d",
            "1w",
        ],
        "logic": "SEPARATE",
        "position_pct": 2.0,
        "side": "BOTH",
        "loop_interval_override": "30s",
        "stop_loss": {
            "enabled": True,
            "mode": "percent",
            "percent": 20.0,
            "scope": "per_trade",
        },
        "margin_mode": "Isolated",
        "position_mode": "Hedge",
        "assets_mode": "Single-Asset",
        "account_mode": "Classic Trading",
        "connector_backend": "binance-sdk-derivatives-trading-usds-futures",
        "leverage": 20,
        "mdd_logic": "entire_account",
        "indicators": {
            "rsi": {"enabled": True, "buy_value": 30, "sell_value": 70},
            "stoch_rsi": {"enabled": True, "buy_value": 20, "sell_value": 80},
            "willr": {"enabled": True, "buy_value": -80, "sell_value": -20},
        },
        "symbol_selection": {
            "type": "top_volume",
            "count": 100,
            "source": "Futures",
        },
    },
}

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

class SimpleCandlestickWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._candles: list[dict] = []
        self._message: str | None = "Charts unavailable."
        self._message_color: str = "#f75467"
        self.setMinimumHeight(320)
        self.setMouseTracking(True)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self._view_start = 0
        self._view_end = 0
        self._min_visible = 10
        self._manual_view = False
        self._pan_active = False
        self._pan_last_pos: QtCore.QPointF | None = None
        self._fib_start: float | None = None
        self._fib_end: float | None = None
        self._fib_dragging = False
        self._show_hint = True

    def set_message(self, message: str, color: str = "#d1d4dc") -> None:
        self._candles = []
        self._message = message
        self._message_color = color
        self._fib_start = None
        self._fib_end = None
        self._reset_view()
        self.update()

    def set_candles(self, candles: list[dict]) -> None:
        self._candles = candles or []
        if not self._candles:
            self._message = "No data available."
            self._message_color = "#f75467"
            self._fib_start = None
            self._fib_end = None
            self._reset_view()
        else:
            self._message = None
            if self._manual_view:
                self._clamp_view()
            else:
                self._reset_view()
        self.update()

    def _reset_view(self) -> None:
        self._view_start = 0
        self._view_end = len(self._candles)
        self._manual_view = False

    def _clamp_view(self) -> None:
        total = len(self._candles)
        if total <= 0:
            self._view_start = 0
            self._view_end = 0
            return
        start = int(self._view_start)
        end = int(self._view_end) if self._view_end else total
        start = max(0, min(start, total - 1))
        end = max(start + 1, min(end, total))
        self._view_start = start
        self._view_end = end

    def _get_visible_range(self) -> tuple[int, int]:
        if not self._candles:
            return 0, 0
        self._clamp_view()
        return self._view_start, self._view_end

    def _chart_rect(self) -> QtCore.QRect:
        rect = self.rect()
        margin_x = max(int(rect.width() * 0.05), 40)
        margin_y = max(int(rect.height() * 0.1), 30)
        return rect.adjusted(margin_x, margin_y, -margin_x, -margin_y)

    def _visible_min_max(self, candles: list[dict]) -> tuple[float, float] | None:
        highs = [float(c.get("high", 0.0)) for c in candles]
        lows = [float(c.get("low", 0.0)) for c in candles]
        if not highs or not lows:
            return None
        max_high = max(highs)
        min_low = min(lows)
        if max_high <= min_low:
            max_high = min_low + 1.0
        return min_low, max_high

    def _pos_to_price(self, pos: QtCore.QPointF) -> float | None:
        if not self._candles:
            return None
        start, end = self._get_visible_range()
        visible = self._candles[start:end]
        if not visible:
            return None
        chart_rect = self._chart_rect()
        if chart_rect.width() <= 0 or chart_rect.height() <= 0:
            return None
        min_max = self._visible_min_max(visible)
        if min_max is None:
            return None
        min_low, max_high = min_max
        y = min(max(pos.y(), chart_rect.top()), chart_rect.bottom())
        ratio = (chart_rect.bottom() - y) / chart_rect.height()
        return min_low + ratio * (max_high - min_low)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        rect = self.rect()
        painter.fillRect(rect, QtGui.QColor("#0b0e11"))

        if not self._candles:
            if self._message:
                painter.setPen(QtGui.QColor(self._message_color))
                painter.drawText(
                    rect,
                    QtCore.Qt.AlignmentFlag.AlignCenter,
                    self._message,
                )
            return

        start, end = self._get_visible_range()
        visible = self._candles[start:end]
        if not visible:
            return
        min_max = self._visible_min_max(visible)
        if min_max is None:
            return
        min_low, max_high = min_max

        chart_rect = self._chart_rect()
        if chart_rect.width() <= 0 or chart_rect.height() <= 0:
            return

        painter.setPen(QtGui.QColor("#1f2326"))
        painter.drawRect(chart_rect)

        count = len(visible)
        spacing = chart_rect.width() / max(count, 1)
        body_width = max(4.0, spacing * 0.6)

        def price_to_y(price: float) -> float:
            ratio = (price - min_low) / (max_high - min_low)
            return chart_rect.bottom() - ratio * chart_rect.height()

        for idx, candle in enumerate(visible):
            try:
                open_ = float(candle.get("open", 0.0))
                close = float(candle.get("close", 0.0))
                high = float(candle.get("high", 0.0))
                low = float(candle.get("low", 0.0))
            except Exception:
                continue

            x_center = chart_rect.left() + (idx + 0.5) * spacing
            color = QtGui.QColor("#0ebb7a" if close >= open_ else "#f75467")
            painter.setPen(QtGui.QPen(color, 1.0))

            y_high = price_to_y(high)
            y_low = price_to_y(low)
            painter.drawLine(QtCore.QPointF(x_center, y_high), QtCore.QPointF(x_center, y_low))

            body_top = price_to_y(max(open_, close))
            body_bottom = price_to_y(min(open_, close))
            rect_body = QtCore.QRectF(
                x_center - body_width / 2.0,
                body_top,
                body_width,
                max(1.0, body_bottom - body_top),
            )
            painter.fillRect(rect_body, QtGui.QBrush(color))

        painter.setPen(QtGui.QColor("#3b434a"))
        painter.drawText(
            chart_rect.adjusted(4, 2, -4, -4),
            QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignLeft,
            f"High: {max_high:.4f}",
        )
        painter.drawText(
            chart_rect.adjusted(4, 2, -4, -4),
            QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignRight,
            f"Low: {min_low:.4f}",
        )
        if self._fib_start is not None and self._fib_end is not None:
            self._draw_fib_levels(painter, chart_rect, price_to_y)
        if self._show_hint:
            painter.setPen(QtGui.QColor("#3b434a"))
            hint = "Wheel: zoom | Drag: pan | Shift+Drag: fib | Double-click: reset"
            painter.drawText(
                chart_rect.adjusted(4, 4, -4, -4),
                QtCore.Qt.AlignmentFlag.AlignBottom | QtCore.Qt.AlignmentFlag.AlignLeft,
                hint,
            )

    def _draw_fib_levels(
        self,
        painter: QtGui.QPainter,
        chart_rect: QtCore.QRect,
        price_to_y,
    ) -> None:
        start_price = self._fib_start
        end_price = self._fib_end
        if start_price is None or end_price is None:
            return
        if abs(end_price - start_price) <= 0:
            return
        levels = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
        line_pen = QtGui.QPen(QtGui.QColor("#3b82f6"))
        line_pen.setStyle(QtCore.Qt.PenStyle.DashLine)
        line_pen.setWidthF(1.0)
        text_pen = QtGui.QPen(QtGui.QColor("#7dd3fc"))
        span = end_price - start_price
        for level in levels:
            price = start_price + span * level
            y = price_to_y(price)
            if y < chart_rect.top() - 1 or y > chart_rect.bottom() + 1:
                continue
            painter.setPen(line_pen)
            painter.drawLine(
                QtCore.QPointF(chart_rect.left(), y),
                QtCore.QPointF(chart_rect.right(), y),
            )
            label = f"{level:.3f}  {price:.4f}"
            painter.setPen(text_pen)
            painter.drawText(
                QtCore.QRectF(chart_rect.left() + 4, y - 9, chart_rect.width() - 8, 18),
                QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter,
                label,
            )

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:  # noqa: N802
        if not self._candles:
            return super().wheelEvent(event)
        angle = event.angleDelta().y()
        if angle == 0:
            return super().wheelEvent(event)
        steps = angle / 120.0
        start, end = self._get_visible_range()
        total = len(self._candles)
        current_count = max(1, end - start)
        min_visible = min(self._min_visible, total) if total > 0 else 1
        scale = 1.2 ** steps
        new_count = int(round(current_count / scale))
        new_count = max(min_visible, min(total, new_count))
        if new_count == current_count:
            return super().wheelEvent(event)
        chart_rect = self._chart_rect()
        if chart_rect.width() <= 0:
            return super().wheelEvent(event)
        pos = event.position()
        ratio = (pos.x() - chart_rect.left()) / chart_rect.width()
        ratio = max(0.0, min(1.0, ratio))
        center = start + ratio * current_count
        new_start = int(round(center - ratio * new_count))
        new_start = max(0, min(new_start, total - new_count))
        self._view_start = new_start
        self._view_end = new_start + new_count
        self._manual_view = True
        self._show_hint = False
        self.update()
        event.accept()

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            try:
                self.setFocus(QtCore.Qt.FocusReason.MouseFocusReason)
            except Exception:
                pass
            chart_rect = self._chart_rect()
            if chart_rect.contains(event.position().toPoint()):
                if event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier:
                    price = self._pos_to_price(event.position())
                    if price is not None:
                        self._fib_start = price
                        self._fib_end = price
                        self._fib_dragging = True
                        self._show_hint = False
                        self.update()
                    event.accept()
                    return
                self._pan_active = True
                self._pan_last_pos = event.position()
                try:
                    self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
                except Exception:
                    pass
                self._show_hint = False
                event.accept()
                return
        if event.button() == QtCore.Qt.MouseButton.RightButton:
            if self._fib_start is not None or self._fib_end is not None:
                self._fib_start = None
                self._fib_end = None
                self._fib_dragging = False
                self._show_hint = False
                self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if self._pan_active and self._pan_last_pos is not None:
            start, end = self._get_visible_range()
            count = max(1, end - start)
            chart_rect = self._chart_rect()
            spacing = chart_rect.width() / max(count, 1)
            if spacing > 0:
                delta_x = event.position().x() - self._pan_last_pos.x()
                delta_candles = int(round(delta_x / spacing))
                if delta_candles != 0:
                    total = len(self._candles)
                    new_start = start - delta_candles
                    new_start = max(0, min(new_start, total - count))
                    self._view_start = new_start
                    self._view_end = new_start + count
                    self._manual_view = True
                    self.update()
            self._pan_last_pos = event.position()
            event.accept()
            return
        if self._fib_dragging:
            price = self._pos_to_price(event.position())
            if price is not None:
                self._fib_end = price
                self._show_hint = False
                self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            if self._pan_active:
                self._pan_active = False
                self._pan_last_pos = None
                try:
                    self.unsetCursor()
                except Exception:
                    pass
                event.accept()
                return
            if self._fib_dragging:
                self._fib_dragging = False
                event.accept()
                return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._reset_view()
            self._show_hint = False
            self.update()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:  # noqa: N802
        key = event.key()
        if key in (
            QtCore.Qt.Key.Key_Escape,
            QtCore.Qt.Key.Key_Delete,
            QtCore.Qt.Key.Key_Backspace,
        ):
            if self._fib_start is not None or self._fib_end is not None:
                self._fib_start = None
                self._fib_end = None
                self._fib_dragging = False
                self._show_hint = False
                self.update()
            event.accept()
            return
        if key == QtCore.Qt.Key.Key_R:
            self._reset_view()
            self._show_hint = False
            self.update()
            event.accept()
            return
        super().keyPressEvent(event)


if QT_CHARTS_AVAILABLE and QChartView is not None:
    class InteractiveChartView(QChartView):
        """QChartView with scroll/zoom conveniences for the 'Original' chart view."""

        def __init__(self, parent=None):
            super().__init__(parent)
            try:
                self.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            except Exception:
                pass
            try:
                self.setRubberBand(QChartView.RubberBand.RectangleRubberBand)
            except Exception:
                pass
            try:
                self.setDragMode(QtWidgets.QGraphicsView.DragMode.NoDrag)
            except Exception:
                pass
            self.setMouseTracking(True)
            self._panning = False
            self._pan_start: QtCore.QPoint | None = None

        def wheelEvent(self, event: QtGui.QWheelEvent) -> None:  # noqa: N802
            chart = self.chart()
            if chart is None:
                return super().wheelEvent(event)
            angle = event.angleDelta().y()
            if angle == 0:
                return super().wheelEvent(event)
            factor = 1.15 if angle > 0 else 1 / 1.15
            try:
                chart.zoom(factor)
            except Exception:
                pass
            event.accept()

        def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
            if event.button() == QtCore.Qt.MouseButton.MiddleButton:
                self._panning = True
                self._pan_start = event.position().toPoint()
                try:
                    self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
                except Exception:
                    pass
                event.accept()
                return
            super().mousePressEvent(event)

        def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
            if self._panning and self._pan_start is not None:
                delta = event.position().toPoint() - self._pan_start
                self._pan_start = event.position().toPoint()
                chart = self.chart()
                if chart is not None:
                    try:
                        chart.scroll(-delta.x(), delta.y())
                    except Exception:
                        pass
                event.accept()
                return
            super().mouseMoveEvent(event)

        def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
            if event.button() == QtCore.Qt.MouseButton.MiddleButton:
                self._panning = False
                self._pan_start = None
                try:
                    self.unsetCursor()
                except Exception:
                    pass
                event.accept()
                return
            super().mouseReleaseEvent(event)

        def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
            chart = self.chart()
            if chart is not None:
                try:
                    chart.zoomReset()
                except Exception:
                    pass
            super().mouseDoubleClickEvent(event)
else:  # QT_CHARTS_AVAILABLE is False
    class InteractiveChartView(QtWidgets.QWidget):
        """Fallback placeholder when PyQt6-Charts is unavailable."""

        def __init__(self, *args, **kwargs):
            raise RuntimeError("PyQt6-Charts is not installed; Original chart view is unavailable.")

def _format_indicator_list(keys):
    if not keys:
        return "-"
    rendered = []
    for key in keys:
        rendered.append(INDICATOR_DISPLAY_NAMES.get(key, key))
    return ", ".join(rendered) if rendered else "-"


_FLOAT_RE = re.compile(r"-?\d+(?:\.\d+)?")
_ACTION_RE = re.compile(r"->\s*(BUY|SELL)", re.IGNORECASE)
_ENTRY_ACTION_SUFFIX_RE = re.compile(r"\s-\s*(BUY|SELL)\s*$", re.IGNORECASE)
_INDICATOR_SHORT_LABEL_OVERRIDES = {
    "stoch_rsi": "SRSI",
    "rsi": "RSI",
    "willr": "W%R",
}


# ============== Persistence for Position Allocations ==============
# These functions persist the _entry_allocations and _open_position_records
# across bot restarts so interval/indicator data is not lost.

_ALLOCATIONS_FILE_NAME = ".trading_bot_allocations.json"


def _get_allocations_file_path() -> Path:
    """Get the path to the allocations persistence file."""
    return _THIS_FILE.parents[2] / _ALLOCATIONS_FILE_NAME


def _serialize_allocation_key(key: tuple) -> str:
    """Convert a (symbol, side_key) tuple to a string for JSON serialization."""
    return f"{key[0]}:{key[1]}"


def _deserialize_allocation_key(key_str: str) -> tuple:
    """Convert a serialized key back to a (symbol, side_key) tuple."""
    parts = key_str.split(":", 1)
    return (parts[0], parts[1]) if len(parts) == 2 else (key_str, "")


def _save_position_allocations(
    entry_allocations: dict,
    open_position_records: dict,
    mode: str | None = None,
) -> bool:
    """
    Save the entry allocations and position records to a JSON file.
    Returns True on success, False on failure.
    """
    try:
        file_path = _get_allocations_file_path()
        
        # Convert tuple keys to string keys for JSON serialization
        serialized_allocations = {}
        for key, entries in (entry_allocations or {}).items():
            str_key = _serialize_allocation_key(key)
            # Deep copy and ensure all values are JSON-serializable
            if isinstance(entries, list):
                serialized_allocations[str_key] = [
                    {k: v for k, v in e.items() if _is_json_serializable(v)}
                    for e in entries if isinstance(e, dict)
                ]
            elif isinstance(entries, dict):
                entries_list = list(entries.values())
                serialized_allocations[str_key] = [
                    {k: v for k, v in e.items() if _is_json_serializable(v)}
                    for e in entries_list if isinstance(e, dict)
                ]
        
        serialized_records = {}
        for key, record in (open_position_records or {}).items():
            if not isinstance(record, dict):
                continue
            str_key = _serialize_allocation_key(key)
            # Only save active records
            if str(record.get("status", "")).lower() != "active":
                continue
            serialized_records[str_key] = _make_json_serializable(record)
        
        data = {
            "version": 1,
            "mode": mode or "unknown",
            "timestamp": time.time(),
            "entry_allocations": serialized_allocations,
            "open_position_records": serialized_records,
        }
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        return True
    except Exception:
        return False


def _is_json_serializable(value) -> bool:
    """Check if a value can be JSON serialized."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, (list, tuple)):
        return all(_is_json_serializable(v) for v in value)
    if isinstance(value, dict):
        return all(
            isinstance(k, str) and _is_json_serializable(v)
            for k, v in value.items()
        )
    return False


def _make_json_serializable(obj: dict) -> dict:
    """Convert a dict to be JSON serializable, converting unsupported types to strings."""
    result = {}
    for k, v in obj.items():
        if not isinstance(k, str):
            continue
        if v is None or isinstance(v, (str, int, float, bool)):
            result[k] = v
        elif isinstance(v, (list, tuple)):
            result[k] = [
                _make_json_serializable(item) if isinstance(item, dict) else item
                for item in v
                if _is_json_serializable(item) or isinstance(item, dict)
            ]
        elif isinstance(v, dict):
            result[k] = _make_json_serializable(v)
        else:
            result[k] = str(v)
    return result


def _load_position_allocations(mode: str | None = None) -> tuple[dict, dict]:
    """
    Load entry allocations and position records from the JSON file.
    Returns (entry_allocations, open_position_records) dicts.
    If file doesn't exist or is invalid, returns empty dicts.
    """
    entry_allocations = {}
    open_position_records = {}
    
    try:
        file_path = _get_allocations_file_path()
        if not file_path.exists():
            return entry_allocations, open_position_records
        
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        if not isinstance(data, dict):
            return entry_allocations, open_position_records
        
        # Check mode compatibility - only load if mode matches or mode is not specified
        saved_mode = data.get("mode")
        if mode and saved_mode and saved_mode != mode:
            # Mode mismatch - don't load incompatible data (e.g., live vs testnet)
            return entry_allocations, open_position_records
        
        # Check data age - only load if less than 24 hours old
        saved_ts = data.get("timestamp", 0)
        if time.time() - saved_ts > 86400:  # 24 hours
            return entry_allocations, open_position_records
        
        # Deserialize entry_allocations
        for str_key, entries in data.get("entry_allocations", {}).items():
            if not isinstance(entries, list):
                continue
            key = _deserialize_allocation_key(str_key)
            # Ensure each entry has a valid 'data' field
            validated_entries = []
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                # Ensure 'data' field exists and is a dict
                if not isinstance(entry.get("data"), dict):
                    entry["data"] = {}
                validated_entries.append(entry)
            entry_allocations[key] = validated_entries
        
        # Deserialize open_position_records
        for str_key, record in data.get("open_position_records", {}).items():
            if not isinstance(record, dict):
                continue
            key = _deserialize_allocation_key(str_key)
            # Ensure 'data' field exists and is a dict
            if not isinstance(record.get("data"), dict):
                record["data"] = {}
            # Ensure allocations field is a list
            if not isinstance(record.get("allocations"), list):
                record["allocations"] = []
            open_position_records[key] = record
        
    except Exception:
        pass
    
    return entry_allocations, open_position_records




def _indicator_short_label(indicator_key: str) -> str:
    key_norm = str(indicator_key or "").strip().lower()
    if not key_norm:
        return "-"
    if key_norm in _INDICATOR_SHORT_LABEL_OVERRIDES:
        return _INDICATOR_SHORT_LABEL_OVERRIDES[key_norm]
    display = INDICATOR_DISPLAY_NAMES.get(key_norm)
    if display:
        if "(" in display and ")" in display:
            candidate = display.rsplit("(", 1)[-1].rstrip(")")
            if candidate.strip():
                return candidate.strip()
        first_word = display.strip().split()[0]
        if first_word:
            return first_word.upper()
    return key_norm.upper()


def _split_trigger_desc(desc: str | None) -> list[str]:
    if not desc:
        return []
    return [segment.strip() for segment in str(desc).split("|") if segment.strip()]


def _indicator_segment_match(indicator_key: str, segment: str) -> bool:
    key_norm = _canonicalize_indicator_key(indicator_key) or str(indicator_key or "").strip().lower()
    seg_low = segment.lower()
    if not key_norm or not seg_low:
        return False
    if key_norm == "stoch_rsi":
        return "stochrsi" in seg_low
    if key_norm == "rsi":
        return "rsi" in seg_low and "stochrsi" not in seg_low
    if key_norm == "willr":
        return "williams" in seg_low
    token = key_norm.replace("_", "")
    return token in seg_low if token else False


def _extract_indicator_metrics(indicator_key: str, segments: list[str]) -> tuple[str | None, str | None]:
    if not segments:
        return None, None
    value_str: str | None = None
    action_str: str | None = None
    for seg in segments:
        if not _indicator_segment_match(indicator_key, seg):
            continue
        if "=" in seg and "->" not in seg:
            match = _FLOAT_RE.search(seg.split("=", 1)[1])
            if match:
                value_str = match.group(0)
                break
    if value_str is None:
        for seg in segments:
            if not _indicator_segment_match(indicator_key, seg):
                continue
            if "->" in seg:
                continue
            match = _FLOAT_RE.search(seg)
            if match:
                value_str = match.group(0)
                break
    if value_str is None:
        for seg in segments:
            if not _indicator_segment_match(indicator_key, seg):
                continue
            match = _FLOAT_RE.search(seg)
            if match:
                value_str = match.group(0)
                break
    for seg in segments:
        if not _indicator_segment_match(indicator_key, seg):
            continue
        match = _ACTION_RE.search(seg)
        if match:
            action_str = match.group(1).title()
            break
    return value_str, action_str


def _normalize_trigger_actions_map(raw_actions) -> dict[str, str]:
    if not isinstance(raw_actions, dict):
        return {}
    normalized: dict[str, str] = {}
    for raw_key, raw_action in raw_actions.items():
        key_norm = _canonicalize_indicator_key(raw_key)
        action_norm = str(raw_action or "").strip().lower()
        if not key_norm or action_norm not in {"buy", "sell"}:
            continue
        normalized[key_norm] = action_norm.title()
    return normalized


def _fallback_trigger_entries_from_desc(
    desc: str | None,
    interval_hint: str | None,
    allowed_indicators: set[str] | None = None,
) -> list[str]:
    if not desc:
        return []
    interval_label = str(interval_hint or "").strip().upper()
    interval_part = f"@{interval_label}" if interval_label else ""
    results: list[str] = []

    def _infer_indicator_key(segment: str) -> str | None:
        seg_low = segment.lower()
        if "stochrsi" in seg_low:
            return "stoch_rsi"
        if "williams" in seg_low or "%r" in seg_low:
            return "willr"
        if "rsi" in seg_low:
            return "rsi"
        return None

    for segment in _split_trigger_desc(desc):
        seg_clean = segment.strip()
        if not seg_clean:
            continue
        indicator_key = _infer_indicator_key(seg_clean)
        if not indicator_key:
            continue
        if allowed_indicators and indicator_key not in allowed_indicators:
            continue
        value_str, action_str = _extract_indicator_metrics(indicator_key, [seg_clean])
        if value_str is None:
            match = _FLOAT_RE.search(seg_clean)
            if match:
                value_str = match.group(0)
        if value_str is not None:
            try:
                value_display = f"{float(value_str):.2f}"
            except Exception:
                value_display = str(value_str)
        else:
            value_display = "--"
        label = _indicator_short_label(indicator_key)
        action_part = f" -{action_str}" if action_str else ""
        entry_text = f"{label}{interval_part} {value_display}{action_part}".strip()
        if entry_text:
            results.append(entry_text)
    return results


def _indicator_entry_signature(text: str) -> tuple[str, str]:
    parts = text.split("@", 1)
    label_part = parts[0].strip().lower()
    interval_part = ""
    if len(parts) == 2:
        remainder = parts[1]
        interval_part = remainder.split(None, 1)[0].strip().lower()
    return label_part, interval_part


def _dedupe_indicator_entries(entries: list[str] | None) -> list[str]:
    if not entries:
        return []
    seen: set[tuple[str, str]] = set()
    deduped: list[str] = []
    for entry in entries:
        sig = _indicator_entry_signature(entry)
        if sig in seen:
            continue
        seen.add(sig)
        deduped.append(entry)
    return deduped


def _dedupe_indicator_entries_normalized(entries: list[str] | None) -> list[str]:
    if not entries:
        return []
    seen_idx: dict[tuple[str, str], int] = {}
    deduped: list[str] = []
    for entry in entries:
        label_part, interval_part = _indicator_entry_signature(entry)
        label_key = _normalize_indicator_token(label_part) or label_part
        interval_key = _normalize_indicator_token(interval_part) or interval_part
        sig = (label_key, interval_key)
        prior = seen_idx.get(sig)
        if prior is None:
            seen_idx[sig] = len(deduped)
            deduped.append(entry)
        else:
            deduped[prior] = entry
    return deduped


def _indicator_entry_components(text: str) -> tuple[tuple[str, str], str | None, str | None]:
    sig = _indicator_entry_signature(text)
    value_str: str | None = None
    action_str: str | None = None
    try:
        parts = str(text or "").strip().split(None, 1)
    except Exception:
        parts = []
    payload = parts[1].strip() if len(parts) >= 2 else ""
    if payload:
        action_match = _ENTRY_ACTION_SUFFIX_RE.search(payload)
        if action_match:
            action_str = action_match.group(1).title()
            payload = payload[:action_match.start()].strip()
        if payload and payload != "--":
            float_match = _FLOAT_RE.search(payload)
            if float_match:
                value_str = float_match.group(0)
    return sig, value_str, action_str


def _backfill_trigger_entries_with_live_values(
    trigger_entries: list[str] | None,
    live_entries: list[str] | None,
) -> list[str]:
    if not trigger_entries:
        return []
    if not live_entries:
        return list(trigger_entries)
    live_map: dict[tuple[str, str], tuple[str | None, str | None]] = {}
    for live_entry in live_entries:
        sig, value_str, action_str = _indicator_entry_components(live_entry)
        if not sig[0]:
            continue
        if value_str is None and action_str is None:
            continue
        live_map[sig] = (value_str, action_str)
    if not live_map:
        return list(trigger_entries)
    merged: list[str] = []
    for trigger_entry in trigger_entries:
        sig, value_str, action_str = _indicator_entry_components(trigger_entry)
        if value_str is not None:
            merged.append(trigger_entry)
            continue
        fallback = live_map.get(sig)
        if not fallback:
            merged.append(trigger_entry)
            continue
        fallback_value, fallback_action = fallback
        if fallback_value is None:
            merged.append(trigger_entry)
            continue
        head = str(trigger_entry or "").strip().split(None, 1)[0].strip()
        action_final = action_str or fallback_action
        rebuilt = f"{head} {fallback_value}".strip()
        if action_final:
            rebuilt = f"{rebuilt} -{action_final}"
        merged.append(rebuilt)
    return _dedupe_indicator_entries_normalized(merged)


def _filter_indicator_entries_for_interval(
    entries: list[str],
    interval_hint: str | None,
    *,
    include_non_matching: bool = True,
) -> list[str]:
    """Return entries matching the given interval (case-insensitive)."""
    if not entries:
        return []
    interval_targets: list[str] = []
    if interval_hint:
        for part in str(interval_hint).split(","):
            token = _normalize_interval_token(part)
            if token and token not in interval_targets:
                interval_targets.append(token)
    seen: set[tuple[str, str]] = set()
    filtered: list[str] = []

    def _interval_token(text: str) -> str | None:
        if "@" not in text:
            return None
        return text.split("@", 1)[1].split(None, 1)[0].strip().lower()

    def _label_token(text: str) -> str:
        return text.split("@", 1)[0].strip().lower()

    matched: list[str] = []
    if interval_targets:
        for target in interval_targets:
            for text in entries:
                token = _interval_token(text)
                if token != target:
                    continue
                label = _label_token(text)
                sig = (label, token)
                if sig in seen:
                    continue
                seen.add(sig)
                matched.append(text)
    if matched:
        return _dedupe_indicator_entries(matched)
    any_interval_token = any(_interval_token(text) is not None for text in entries)
    if not any_interval_token:
        # Keep entries when no explicit interval tags exist.
        return _dedupe_indicator_entries(entries)
    if not include_non_matching:
        return []
    for text in entries:
        token = _interval_token(text)
        if token is None:
            continue
        label = _label_token(text)
        sig = (label, token)
        if sig in seen:
            continue
        seen.add(sig)
        filtered.append(text)
    return _dedupe_indicator_entries(filtered or entries)


_CLOSED_RECORD_STATES = {
    "closed",
    "liquidated",
    "liquidation",
    "error",
    "stopped",
}

_CLOSED_ALLOCATION_STATES = {
    "closed",
    "error",
    "cancelled",
    "canceled",
    "liquidated",
    "liquidation",
    "stopped",
    "completed",
    "filled",
}


def _normalize_interval_token(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(value).strip().lower() or None
    except Exception:
        return None


def _collect_record_indicator_keys(
    rec: dict,
    *,
    include_inactive_allocs: bool = False,
    include_allocation_scope: bool = True,
) -> list[str]:
    if not isinstance(rec, dict):
        return []
    collected: list[str] = []
    seen: set[str] = set()

    def _add_keys(raw, desc_text: str | None = None) -> None:
        resolved = _resolve_trigger_indicators(raw, desc_text)
        for key in _normalize_indicator_values(resolved):
            key_norm = _canonicalize_indicator_key(key)
            if not key_norm or key_norm in seen:
                continue
            seen.add(key_norm)
            collected.append(key_norm)

    def _iter_allocations(payload) -> list[dict]:
        if isinstance(payload, dict):
            payload = list(payload.values())
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict)]

    data = rec.get("data") or {}
    base_desc = data.get("trigger_desc") or rec.get("trigger_desc")
    _add_keys(rec.get("indicators"))
    _add_keys(data.get("trigger_indicators"))
    if isinstance(data.get("trigger_actions"), dict):
        _add_keys(list((data.get("trigger_actions") or {}).keys()))
    if not collected:
        _add_keys(None, base_desc)

    if include_allocation_scope:
        for alloc in _iter_allocations(rec.get("allocations")):
            status_flag = str(alloc.get("status") or "").strip().lower()
            if status_flag in _CLOSED_ALLOCATION_STATES and not include_inactive_allocs:
                continue
            _add_keys(alloc.get("trigger_indicators"), alloc.get("trigger_desc"))
            if isinstance(alloc.get("trigger_actions"), dict):
                _add_keys(list((alloc.get("trigger_actions") or {}).keys()))

    aggregated_entries = rec.get("_aggregated_entries")
    if isinstance(aggregated_entries, list):
        for agg in aggregated_entries:
            if not isinstance(agg, dict):
                continue
            agg_data = agg.get("data") or {}
            agg_status = str(agg.get("status") or agg_data.get("status") or "").strip().lower()
            if agg_status in _CLOSED_RECORD_STATES and not include_inactive_allocs:
                continue
            agg_desc = agg_data.get("trigger_desc") or agg.get("trigger_desc")
            _add_keys(agg.get("indicators"))
            _add_keys(agg_data.get("trigger_indicators"))
            if isinstance(agg_data.get("trigger_actions"), dict):
                _add_keys(list((agg_data.get("trigger_actions") or {}).keys()))
            if not collected:
                _add_keys(None, agg_desc)
            if include_allocation_scope:
                for alloc in _iter_allocations(agg.get("allocations")):
                    status_flag = str(alloc.get("status") or "").strip().lower()
                    if status_flag in _CLOSED_ALLOCATION_STATES and not include_inactive_allocs:
                        continue
                    _add_keys(alloc.get("trigger_indicators"), alloc.get("trigger_desc"))
                    if isinstance(alloc.get("trigger_actions"), dict):
                        _add_keys(list((alloc.get("trigger_actions") or {}).keys()))
    return collected


def _collect_indicator_value_strings(rec: dict, interval_hint: str | None = None) -> tuple[list[str], dict[str, list[str]]]:
    data = rec.get("data") or {}
    record_status = str(rec.get("status") or data.get("status") or "").strip().lower()
    include_inactive_allocs = record_status in _CLOSED_RECORD_STATES
    primary_interval = ""
    if interval_hint:
        primary_interval = str(interval_hint).split(",")[0].strip()
    elif isinstance(data.get("interval_display"), str):
        primary_interval = str(data.get("interval_display")).split(",")[0].strip()

    indicator_keys = _collect_record_indicator_keys(
        rec,
        include_inactive_allocs=include_inactive_allocs,
    )
    if not indicator_keys:
        return [], {}
    indicator_key_set = set(indicator_keys)
    action_overrides_by_interval: dict[tuple[str, str | None], str] = {}

    sources: list[dict] = []

    def _append_source(interval_value, desc_text):
        if not desc_text:
            return
        segments = _split_trigger_desc(desc_text)
        if not segments:
            return
        interval_tokens: list[tuple[str | None, str | None]] = []
        if interval_value:
            parts = [part.strip() for part in str(interval_value).split(",") if part.strip()]
            for part in parts:
                interval_tokens.append((part, _normalize_interval_token(part)))
        if not interval_tokens:
            interval_tokens.append(((interval_value or "").strip() or None, _normalize_interval_token(interval_value)))
        for display_token, norm_token in interval_tokens:
            sources.append(
                {
                    "interval": display_token or interval_value,
                    "norm_interval": norm_token,
                    "segments": segments,
                }
            )

    def _register_action_overrides(interval_value, raw_actions) -> None:
        normalized_actions = _normalize_trigger_actions_map(raw_actions)
        if not normalized_actions:
            return
        interval_norm_tokens: list[str | None] = []
        if interval_value:
            for part in [p.strip() for p in str(interval_value).split(",") if p.strip()]:
                interval_norm_tokens.append(_normalize_interval_token(part))
        if not interval_norm_tokens:
            interval_norm_tokens.append(_normalize_interval_token(interval_value))
        if None not in interval_norm_tokens:
            interval_norm_tokens.append(None)
        for indicator_key, action_val in normalized_actions.items():
            key_norm = _canonicalize_indicator_key(indicator_key) or indicator_key
            if not key_norm:
                continue
            for interval_norm_token in interval_norm_tokens:
                action_overrides_by_interval[(key_norm, interval_norm_token)] = action_val

    aggregated_entries = rec.get("_aggregated_entries")
    data_desc = data.get("trigger_desc")
    data_interval = data.get("interval_display") or data.get("interval") or primary_interval
    _register_action_overrides(data_interval, data.get("trigger_actions") or rec.get("trigger_actions"))
    if data_desc and not aggregated_entries:
        interval_display = data_interval
        _append_source(interval_display, data_desc)

    allocations = rec.get("allocations") or []
    if isinstance(allocations, dict):
        allocations = list(allocations.values())
    if isinstance(allocations, list):
        for alloc in allocations:
            if not isinstance(alloc, dict):
                continue
            status_flag = str(alloc.get("status") or "").strip().lower()
            if status_flag in _CLOSED_ALLOCATION_STATES and not include_inactive_allocs:
                continue
            desc = alloc.get("trigger_desc")
            if not desc:
                continue
            iv = alloc.get("interval_display") or alloc.get("interval")
            _register_action_overrides(iv, alloc.get("trigger_actions"))
            _append_source(iv, desc)

    if isinstance(aggregated_entries, list):
        for agg in aggregated_entries:
            if not isinstance(agg, dict):
                continue
            agg_data = agg.get("data") or {}
            agg_status = str(agg.get("status") or agg_data.get("status") or "").strip().lower()
            if agg_status in _CLOSED_RECORD_STATES and not include_inactive_allocs:
                continue
            agg_desc = agg_data.get("trigger_desc") or agg.get("trigger_desc")
            if agg_desc:
                agg_interval = (
                    agg_data.get("interval_display")
                    or agg_data.get("interval")
                    or agg.get("entry_tf")
                    or primary_interval
                )
                _register_action_overrides(
                    agg_interval,
                    agg_data.get("trigger_actions") or agg.get("trigger_actions"),
                )
                _append_source(agg_interval, agg_desc)
            agg_allocs = agg.get("allocations") or []
            if isinstance(agg_allocs, dict):
                agg_allocs = list(agg_allocs.values())
            if isinstance(agg_allocs, list):
                for alloc in agg_allocs:
                    if not isinstance(alloc, dict):
                        continue
                    status_flag = str(alloc.get("status") or "").strip().lower()
                    if status_flag in _CLOSED_ALLOCATION_STATES and not include_inactive_allocs:
                        continue
                    desc = alloc.get("trigger_desc")
                    if not desc:
                        continue
                    iv = alloc.get("interval_display") or alloc.get("interval")
                    _register_action_overrides(iv, alloc.get("trigger_actions"))
                    _append_source(iv, desc)

    side_key = str(rec.get("side_key") or (rec.get("data") or {}).get("side_key") or "").upper()

    primary_norm = _normalize_interval_token(primary_interval)
    restrict_to_primary = bool(rec.get("_aggregate_is_primary"))
    sources_to_use = sources
    if restrict_to_primary and primary_norm:
        preferred_sources = [src for src in sources if src.get("norm_interval") == primary_norm]
        if preferred_sources:
            sources_to_use = preferred_sources
        else:
            fallback_sources = [src for src in sources if src.get("norm_interval") in (None, "")]
            if fallback_sources:
                sources_to_use = fallback_sources
    interval_map: dict[str, list[str]] = {}
    results: list[str] = []
    allow_value_without_action = len(indicator_keys) == 1
    for key in indicator_keys:
        key_norm = _canonicalize_indicator_key(key) or key.lower()
        interval_entry_order: list[str | None] = []
        interval_entry_map: dict[str | None, str] = {}

        for source in sources_to_use:
            segments = source.get("segments") or []
            value, action = _extract_indicator_metrics(key, segments)
            source_interval_norm = source.get("norm_interval")
            if action is None:
                action = action_overrides_by_interval.get((key_norm, source_interval_norm))
            if action is None:
                action = action_overrides_by_interval.get((key_norm, None))
            if action is None and (value is None or not allow_value_without_action):
                continue
            interval_label = source.get("interval") or primary_interval
            interval_display = (interval_label or "").strip()
            if not interval_display and primary_interval:
                interval_display = primary_interval
            label = _indicator_short_label(key)
            interval_part = f"@{interval_display.upper()}" if interval_display else ""
            if value is not None:
                try:
                    value_display = f"{float(value):.2f}"
                except Exception:
                    value_display = str(value)
            else:
                value_display = "--"
            action_part = f" -{action}" if action else ""
            entry = f"{label}{interval_part} {value_display}{action_part}".strip()
            interval_reg_key = (interval_display or "").strip().lower() or None
            if interval_reg_key in interval_entry_map:
                interval_entry_map[interval_reg_key] = entry
            else:
                interval_entry_map[interval_reg_key] = entry
                interval_entry_order.append(interval_reg_key)
            if interval_display:
                interval_clean = interval_display.strip().upper()
                slots = interval_map.setdefault(key.lower(), [])
                if interval_clean not in slots:
                    slots.append(interval_clean)
        if interval_entry_map:
            results.extend(interval_entry_map[idx] for idx in interval_entry_order)

    deduped_results = _dedupe_indicator_entries(results)

    if not deduped_results and action_overrides_by_interval:
        interval_order: list[str | None] = []
        if primary_norm is not None:
            interval_order.append(primary_norm)
        if None not in interval_order:
            interval_order.append(None)
        for key in indicator_keys:
            key_norm = _canonicalize_indicator_key(key) or key.lower()
            action_val = None
            for interval_norm in interval_order:
                action_val = action_overrides_by_interval.get((key_norm, interval_norm))
                if action_val:
                    break
            if not action_val:
                continue
            interval_display = (primary_interval or "").strip()
            label = _indicator_short_label(key)
            interval_part = f"@{interval_display.upper()}" if interval_display else ""
            entry = f"{label}{interval_part} -- -{action_val}".strip()
            deduped_results.append(entry)
            if interval_display:
                interval_clean = interval_display.strip().upper()
                slots = interval_map.setdefault(key.lower(), [])
                if interval_clean not in slots:
                    slots.append(interval_clean)

    seen_interval_pairs = {_indicator_entry_signature(entry) for entry in deduped_results}
    if not deduped_results:
        fallback_entries: list[str] = []
        data_desc_primary = (rec.get("data") or {}).get("trigger_desc") or rec.get("trigger_desc")
        fallback_entries.extend(
            _fallback_trigger_entries_from_desc(
                data_desc_primary,
                interval_hint,
                allowed_indicators=indicator_key_set,
            )
        )
        allocations = rec.get("allocations") or []
        if isinstance(allocations, dict):
            allocations = list(allocations.values())
        for alloc in allocations or []:
            if not isinstance(alloc, dict):
                continue
            status_flag = str(alloc.get("status") or "").strip().lower()
            if status_flag in _CLOSED_ALLOCATION_STATES and not include_inactive_allocs:
                continue
            fallback_entries.extend(
                _fallback_trigger_entries_from_desc(
                    alloc.get("trigger_desc"),
                    alloc.get("interval_display") or alloc.get("interval") or interval_hint,
                    allowed_indicators=indicator_key_set,
                )
            )
        aggregated_entries = rec.get("_aggregated_entries") or []
        if isinstance(aggregated_entries, list):
            for agg in aggregated_entries:
                if not isinstance(agg, dict):
                    continue
                agg_data = agg.get("data") or {}
                agg_status = str(agg.get("status") or agg_data.get("status") or "").strip().lower()
                if agg_status in _CLOSED_RECORD_STATES and not include_inactive_allocs:
                    continue
                agg_desc = agg_data.get("trigger_desc") or agg.get("trigger_desc")
                fallback_entries.extend(
                    _fallback_trigger_entries_from_desc(
                        agg_desc,
                        agg.get("entry_tf") or agg_data.get("interval_display") or interval_hint,
                        allowed_indicators=indicator_key_set,
                    )
                )
        if fallback_entries:
            filtered: list[str] = []
            for entry in fallback_entries:
                interval_key = _indicator_entry_signature(entry)
                if interval_key in seen_interval_pairs:
                    continue
                seen_interval_pairs.add(interval_key)
                filtered.append(entry)
            if filtered:
                deduped_results = list(dict.fromkeys(filtered))
    else:
        fallback_entries: list[str] = []
        data_desc_primary = (rec.get("data") or {}).get("trigger_desc") or rec.get("trigger_desc")
        fallback_entries.extend(
            _fallback_trigger_entries_from_desc(
                data_desc_primary,
                interval_hint,
                allowed_indicators=indicator_key_set,
            )
        )
        allocations = rec.get("allocations") or []
        if isinstance(allocations, dict):
            allocations = list(allocations.values())
        for alloc in allocations or []:
            if not isinstance(alloc, dict):
                continue
            status_flag = str(alloc.get("status") or "").strip().lower()
            if status_flag in _CLOSED_ALLOCATION_STATES and not include_inactive_allocs:
                continue
            fallback_entries.extend(
                _fallback_trigger_entries_from_desc(
                    alloc.get("trigger_desc"),
                    alloc.get("interval_display") or alloc.get("interval") or interval_hint,
                    allowed_indicators=indicator_key_set,
                )
            )
        aggregated_entries = rec.get("_aggregated_entries") or []
        if isinstance(aggregated_entries, list):
            for agg in aggregated_entries:
                if not isinstance(agg, dict):
                    continue
                agg_data = agg.get("data") or {}
                agg_status = str(agg.get("status") or agg_data.get("status") or "").strip().lower()
                if agg_status in _CLOSED_RECORD_STATES and not include_inactive_allocs:
                    continue
                agg_desc = agg_data.get("trigger_desc") or agg.get("trigger_desc")
                fallback_entries.extend(
                    _fallback_trigger_entries_from_desc(
                        agg_desc,
                        agg.get("entry_tf") or agg_data.get("interval_display") or interval_hint,
                        allowed_indicators=indicator_key_set,
                    )
                )
        if fallback_entries:
            for entry in fallback_entries:
                interval_key = _indicator_entry_signature(entry)
                if interval_key in seen_interval_pairs:
                    continue
                seen_interval_pairs.add(interval_key)
                if entry not in deduped_results:
                    deduped_results.append(entry)
    if deduped_results:
        label_map = {
            _indicator_short_label(key).strip().lower(): key
            for key in indicator_keys
        }
        for entry in deduped_results:
            label_part, interval_part = _indicator_entry_signature(entry)
            if not interval_part:
                continue
            key = label_map.get(label_part)
            if not key:
                continue
            interval_slots = interval_map.setdefault(key.lower(), [])
            interval_clean = interval_part.strip().upper()
            if interval_clean and interval_clean not in interval_slots:
                interval_slots.append(interval_clean)
    return deduped_results, interval_map


def _collect_dependency_versions(
    targets: list[dict[str, str]] | None = None,
    *,
    include_latest: bool = True,
) -> list[tuple[str, str, str]]:
    versions: list[tuple[str, str, str]] = []
    target_list = targets or DEPENDENCY_VERSION_TARGETS

    installed_map: dict[str, str] = {}
    for target in target_list:
        label = target["label"]
        installed_version = None
        if target.get("custom") == "qt":
            installed_version = getattr(QtCore, "QT_VERSION_STR", None)
        else:
            package = target.get("package")
            if package:
                try:
                    installed_version = importlib_metadata.version(package)
                except Exception:
                    installed_version = None
        installed_map[label] = installed_version or "Not installed"

    latest_map: dict[str, str] = {}
    if include_latest:
        # Fetch latest versions concurrently to avoid long waits on slow networks/PyPI.
        max_workers = min(6, max(1, len(target_list)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_map: dict[str, concurrent.futures.Future] = {}
            for target in target_list:
                if target.get("custom") == "qt":
                    continue
                pypi_name = target.get("pypi") or target.get("package")
                if not pypi_name:
                    continue
                future_map[target["label"]] = pool.submit(_latest_version_from_pypi, pypi_name)
            for label, fut in future_map.items():
                try:
                    latest_val = fut.result(timeout=10.0)
                except Exception:
                    latest_val = None
                latest_map[label] = latest_val or "Unknown"

    for target in target_list:
        label = target["label"]
        installed_display = installed_map.get(label, "Not installed")
        latest_display = latest_map.get(label, "Not checked" if not include_latest else "Unknown")
        versions.append((label, installed_display, latest_display))
    return versions


def _sanitize_interval_hint(interval_hint: str | None) -> str:
    if not interval_hint:
        return ""
    try:
        primary = str(interval_hint).split(",")[0].strip()
    except Exception:
        primary = str(interval_hint or "").strip()
    return primary


def _calc_indicator_value_from_df(df, indicator_key: str, indicator_cfg: dict, *, use_live_values: bool = True) -> float | None:
    if df is None or df.empty:
        return None
    key = str(indicator_key or "").strip().lower()
    if not key:
        return None
    try:
        close = pd.to_numeric(df["close"], errors="coerce")
    except Exception:
        return None
    close = close.dropna()
    if close.empty:
        return None
    cfg = indicator_cfg or {}
    def _pick(series) -> float | None:
        try:
            s = series.dropna()
        except Exception:
            s = series
        if s is None or len(s) == 0:
            return None
        if use_live_values:
            return float(s.iloc[-1])
        return float(s.iloc[-2]) if len(s) >= 2 else float(s.iloc[-1])
    try:
        if key == "rsi":
            length = int(cfg.get("length") or cfg.get("period") or 14)
            series = rsi_indicator(close, length=length).dropna()
            return _pick(series)
        elif key == "stoch_rsi":
            length = int(cfg.get("length") or cfg.get("rsi_length") or 14)
            smooth_k = int(cfg.get("smooth_k") or 3)
            smooth_d = int(cfg.get("smooth_d") or 3)
            k_series, _ = stoch_rsi_indicator(close, length=length, smooth_k=smooth_k, smooth_d=smooth_d)
            return _pick(k_series)
        elif key == "willr":
            length = int(cfg.get("length") or 14)
            high = pd.to_numeric(df["high"], errors="coerce")
            low = pd.to_numeric(df["low"], errors="coerce")
            price_frame = pd.DataFrame({"high": high, "low": low, "close": close})
            wr_series = williams_r_indicator(price_frame, length=length).dropna()
            return _pick(wr_series)
        elif key == "ma":
            length = int(cfg.get("length") or 20)
            kind = str(cfg.get("type") or "SMA").upper()
            if kind == "EMA":
                series = ema_indicator(close, length).dropna()
            else:
                series = sma_indicator(close, length).dropna()
            return _pick(series)
        elif key == "ema":
            length = int(cfg.get("length") or 20)
            series = ema_indicator(close, length).dropna()
            return _pick(series)
    except Exception:
        return None
    return None


def _ensure_shared_wrapper(window) -> BinanceWrapper | None:
    bw = getattr(window, "shared_binance", None)
    if not hasattr(window, "_create_binance_wrapper"):
        return None
    try:
        api_key = window.api_key_edit.text().strip()
        api_secret = window.api_secret_edit.text().strip()
        mode = window.mode_combo.currentText()
        account = window.account_combo.currentText()
        backend_raw = None
        try:
            combo = getattr(window, "connector_combo", None)
            if combo is not None:
                backend_raw = combo.currentData()
                if backend_raw is None:
                    backend_raw = combo.currentText()
        except Exception:
            backend_raw = None
        backend = _normalize_connector_backend(backend_raw)
        if bw is not None:
            try:
                bw_key = str(getattr(bw, "api_key", "") or "")
                bw_secret = str(getattr(bw, "api_secret", "") or "")
                bw_mode = str(getattr(bw, "mode", "") or "")
                bw_acct = str(getattr(bw, "account_type", "") or "")
                bw_backend = str(getattr(bw, "_connector_backend", "") or "")
                if (
                    bw_key == api_key
                    and bw_secret == api_secret
                    and bw_mode == mode
                    and bw_acct.upper() == str(account or "").strip().upper()
                    and bw_backend == backend
                ):
                    return bw
            except Exception:
                pass
        bw = window._create_binance_wrapper(
            api_key=api_key,
            api_secret=api_secret,
            mode=mode,
            account_type=account,
            connector_backend=backend,
        )
        window.shared_binance = bw
        return bw
    except Exception:
        return None


def _snapshot_live_indicator_context(window) -> dict:
    try:
        auth = _snapshot_auth_state(window)
    except Exception:
        auth = {}
    try:
        backend = window._runtime_connector_backend(suppress_refresh=True)
    except Exception:
        backend = None
    try:
        indicator_source = str(window.ind_source_combo.currentText() or "").strip()
    except Exception:
        indicator_source = ""
    return {
        "auth": auth,
        "connector_backend": backend,
        "indicator_source": indicator_source,
    }


def _get_live_indicator_wrapper(window, context: dict) -> BinanceWrapper | None:
    try:
        auth = context.get("auth") or {}
    except Exception:
        auth = {}
    try:
        backend = _normalize_connector_backend(context.get("connector_backend"))
    except Exception:
        backend = None
    api_key = str(auth.get("api_key") or "")
    api_secret = str(auth.get("api_secret") or "")
    mode = str(auth.get("mode") or "Live")
    account_type = str(auth.get("account_type") or "Futures")
    signature = (api_key, api_secret, mode, account_type, str(backend or ""))
    wrapper = getattr(window, "_live_indicator_wrapper", None)
    if wrapper is None or signature != getattr(window, "_live_indicator_wrapper_signature", None):
        try:
            wrapper = BinanceWrapper(
                api_key,
                api_secret,
                mode=mode,
                account_type=account_type,
                connector_backend=backend,
                default_leverage=int(auth.get("default_leverage", 1) or 1),
                default_margin_mode=str(auth.get("default_margin_mode") or "Isolated"),
            )
        except Exception:
            wrapper = None
        window._live_indicator_wrapper = wrapper
        window._live_indicator_wrapper_signature = signature
    indicator_source = context.get("indicator_source") or ""
    if wrapper is not None and indicator_source:
        try:
            wrapper.indicator_source = indicator_source
        except Exception:
            pass
    return wrapper


def _start_live_indicator_refresh_worker(window, entry: dict) -> None:
    cache_key = entry.get("cache_key")
    symbol = entry.get("symbol")
    interval = entry.get("interval")
    indicator_keys = sorted({str(k).strip().lower() for k in (entry.get("indicator_keys") or []) if str(k).strip()})
    if not cache_key or not symbol or not interval or not indicator_keys:
        return
    indicators_cfg = entry.get("indicators_cfg") or {}
    use_live_values = bool(entry.get("use_live_values", True))
    context = entry.get("context") or {}
    indicator_source = context.get("indicator_source") or ""

    cache = getattr(window, "_live_indicator_cache", None)
    if not isinstance(cache, dict):
        cache = {}
        window._live_indicator_cache = cache
    cache_entry = cache.get(cache_key)
    if cache_entry is None:
        cache_entry = {"df": None, "values": {}, "error": False, "df_ts": 0.0, "error_ts": 0.0}
        cache[cache_key] = cache_entry
    cache_entry["refreshing"] = True

    wrapper = _get_live_indicator_wrapper(window, context)
    auth = context.get("auth") or {}
    backend = _normalize_connector_backend(context.get("connector_backend"))

    def _do():
        bw = wrapper
        if bw is None:
            bw = BinanceWrapper(
                str(auth.get("api_key") or ""),
                str(auth.get("api_secret") or ""),
                mode=str(auth.get("mode") or "Live"),
                account_type=str(auth.get("account_type") or "Futures"),
                connector_backend=backend,
                default_leverage=int(auth.get("default_leverage", 1) or 1),
                default_margin_mode=str(auth.get("default_margin_mode") or "Isolated"),
            )
        if indicator_source:
            try:
                bw.indicator_source = indicator_source
            except Exception:
                pass
        frame = bw.get_klines(symbol, interval, limit=200)
        if frame is None or getattr(frame, "empty", True):
            raise RuntimeError("no_kline_data")
        values = {}
        for key in indicator_keys:
            values[key] = _calc_indicator_value_from_df(
                frame,
                key,
                indicators_cfg.get(key, {}),
                use_live_values=use_live_values,
            )
        return {"df": frame, "values": values}

    worker = CallWorker(_do, parent=window)

    def _done(res, err, key=cache_key):
        try:
            cache_local = getattr(window, "_live_indicator_cache", None)
        except Exception:
            cache_local = None
        if not isinstance(cache_local, dict):
            cache_local = {}
            try:
                window._live_indicator_cache = cache_local
            except Exception:
                pass
        cache_entry_local = cache_local.get(key) or {}
        cache_entry_local["refreshing"] = False
        now_ts = time.monotonic()
        if err or not isinstance(res, dict):
            cache_entry_local["error"] = True
            cache_entry_local["error_ts"] = now_ts
        else:
            cache_entry_local["error"] = False
            cache_entry_local["error_ts"] = 0.0
            cache_entry_local["df"] = res.get("df")
            cache_entry_local["df_ts"] = now_ts
            values_cache = cache_entry_local.setdefault("values", {})
            values_cache.update(res.get("values") or {})
            cache_entry_local["use_live_values"] = use_live_values
            if indicator_source:
                cache_entry_local["indicator_source"] = indicator_source
            cache_entry_local.pop("pending_keys", None)
        cache_local[key] = cache_entry_local
        try:
            inflight = getattr(window, "_live_indicator_refresh_inflight", None)
            if isinstance(inflight, set):
                inflight.discard(key)
        except Exception:
            pass
        try:
            active = int(getattr(window, "_live_indicator_refresh_active", 0) or 0)
            if active > 0:
                active -= 1
            window._live_indicator_refresh_active = active
        except Exception:
            pass
        try:
            QtCore.QTimer.singleShot(0, lambda w=window: _process_live_indicator_refresh_queue(w))
        except Exception:
            pass

    worker.done.connect(_done)
    workers = getattr(window, "_live_indicator_refresh_workers", None)
    if not isinstance(workers, list):
        workers = []
        window._live_indicator_refresh_workers = workers
    workers.append(worker)
    worker.finished.connect(lambda: workers.remove(worker) if worker in workers else None)
    worker.start()


def _process_live_indicator_refresh_queue(window) -> None:
    try:
        window._live_indicator_refresh_scheduled = False
    except Exception:
        pass
    queue = getattr(window, "_live_indicator_refresh_queue", None)
    if not queue:
        return
    inflight = getattr(window, "_live_indicator_refresh_inflight", None)
    if not isinstance(inflight, set):
        inflight = set()
        window._live_indicator_refresh_inflight = inflight
    active = int(getattr(window, "_live_indicator_refresh_active", 0) or 0)
    limit = int(getattr(window, "_live_indicator_refresh_limit", 2) or 2)
    while queue and active < limit:
        entry = queue.popleft()
        cache_key = entry.get("cache_key")
        if not cache_key or cache_key in inflight:
            continue
        inflight.add(cache_key)
        active += 1
        window._live_indicator_refresh_active = active
        _start_live_indicator_refresh_worker(window, entry)


def _queue_live_indicator_refresh(
    window,
    cache: dict,
    cache_key: tuple,
    symbol: str,
    interval: str,
    indicator_keys: set[str],
    indicators_cfg: dict,
    use_live_values: bool,
    indicator_source: str,
) -> None:
    if not cache_key or not symbol or not interval or not indicator_keys:
        return
    inflight = getattr(window, "_live_indicator_refresh_inflight", None)
    if not isinstance(inflight, set):
        inflight = set()
        window._live_indicator_refresh_inflight = inflight
    queue = getattr(window, "_live_indicator_refresh_queue", None)
    if queue is None:
        from collections import deque
        queue = deque()
        window._live_indicator_refresh_queue = queue
    cache_entry = cache.get(cache_key)
    if cache_entry is None:
        cache_entry = {"df": None, "values": {}, "error": False, "df_ts": 0.0, "error_ts": 0.0}
        cache[cache_key] = cache_entry
    pending = cache_entry.setdefault("pending_keys", set())
    pending.update(indicator_keys)
    if cache_key in inflight:
        return
    for existing in queue:
        if existing.get("cache_key") == cache_key:
            existing.setdefault("indicator_keys", set()).update(indicator_keys)
            return
    context = _snapshot_live_indicator_context(window)
    if indicator_source and not context.get("indicator_source"):
        context["indicator_source"] = indicator_source
    entry = {
        "cache_key": cache_key,
        "symbol": symbol,
        "interval": interval,
        "indicator_keys": set(indicator_keys),
        "indicators_cfg": indicators_cfg,
        "use_live_values": use_live_values,
        "context": context,
    }
    queue.append(entry)
    if not getattr(window, "_live_indicator_refresh_scheduled", False):
        window._live_indicator_refresh_scheduled = True
        QtCore.QTimer.singleShot(0, lambda w=window: _process_live_indicator_refresh_queue(w))


def _collect_current_indicator_live_strings(
    window,
    symbol,
    indicator_keys,
    cache,
    interval_map: dict[str, list[str]] | None = None,
    default_interval_hint: str | None = None,
):
    raw_keys = [str(k).strip() for k in (indicator_keys or []) if str(k).strip()]
    keys: list[str] = []
    seen_keys: set[str] = set()
    for key in raw_keys:
        key_norm = _canonicalize_indicator_key(key) or key.lower()
        if not key_norm or key_norm in seen_keys:
            continue
        seen_keys.add(key_norm)
        keys.append(key_norm)
    if not symbol or not keys:
        return []
    default_interval = _sanitize_interval_hint(default_interval_hint) or "1m"
    symbol_norm = str(symbol).strip().upper()

    try:
        indicators_cfg = (window.config or {}).get("indicators", {}) or {}
    except Exception:
        indicators_cfg = {}
    try:
        use_live_values = bool((window.config or {}).get("indicator_use_live_values", False))
    except Exception:
        use_live_values = True
    try:
        indicator_source = str(window.ind_source_combo.currentText() or "").strip()
    except Exception:
        indicator_source = ""
    buy_thresholds = {
        "stoch_rsi": float((indicators_cfg.get("stoch_rsi", {}).get("buy_value") or 20.0)),
        "willr": float((indicators_cfg.get("willr", {}).get("buy_value") or -80.0)),
        "rsi": float((indicators_cfg.get("rsi", {}).get("buy_value") or 30.0)),
    }
    sell_thresholds = {
        "stoch_rsi": float((indicators_cfg.get("stoch_rsi", {}).get("sell_value") or 80.0)),
        "willr": float((indicators_cfg.get("willr", {}).get("sell_value") or -20.0)),
        "rsi": float((indicators_cfg.get("rsi", {}).get("sell_value") or 70.0)),
    }
    ttl = float(getattr(window, "_live_indicator_cache_ttl", 8.0) or 8.0)
    now_ts = time.monotonic()

    entries: list[str] = []
    refresh_requests: dict[tuple, dict] = {}
    for key in keys:
        intervals: list[str] = []
        if isinstance(interval_map, dict):
            intervals = interval_map.get(key) or interval_map.get(key.lower()) or []
        if not intervals:
            intervals = [default_interval]
        normalized_intervals: list[str] = []
        seen_intervals: set[str] = set()
        for interval_label in intervals:
            interval_clean = (str(interval_label or "").strip() or default_interval).lower()
            interval_key = _normalize_indicator_token(interval_clean) or interval_clean
            if interval_key in seen_intervals:
                continue
            seen_intervals.add(interval_key)
            normalized_intervals.append(interval_clean)
        if not normalized_intervals:
            normalized_intervals = [default_interval]
        for interval_clean in normalized_intervals:
            cache_key = (symbol_norm, interval_clean)
            cache_entry = cache.get(cache_key)
            if cache_entry is None:
                cache_entry = {
                    "df": None,
                    "values": {},
                    "error": False,
                    "df_ts": 0.0,
                    "error_ts": 0.0,
                }
                cache[cache_key] = cache_entry
            frame = cache_entry.get("df")
            try:
                frame_ts = float(cache_entry.get("df_ts") or 0.0)
            except Exception:
                frame_ts = 0.0
            needs_refresh = frame is None or (now_ts - frame_ts) >= ttl
            cached_mode = cache_entry.get("use_live_values")
            if cached_mode is None or cached_mode != use_live_values:
                needs_refresh = True
            cached_source = str(cache_entry.get("indicator_source") or "")
            if indicator_source and cached_source != indicator_source:
                needs_refresh = True
            try:
                error_ts = float(cache_entry.get("error_ts") or 0.0)
            except Exception:
                error_ts = 0.0
            recently_failed = bool(cache_entry.get("error")) and (now_ts - error_ts) < ttl
            if needs_refresh and not recently_failed and not cache_entry.get("refreshing"):
                req = refresh_requests.setdefault(
                    cache_key,
                    {"symbol": symbol_norm, "interval": interval_clean, "keys": set()},
                )
                req["keys"].add(key)
            values_cache = cache_entry.setdefault("values", {})
            value = values_cache.get(key)
            if value is None:
                values_cache[key] = None
                value = None

            label = _indicator_short_label(key)
            interval_tag = f"@{interval_clean.upper()}" if interval_clean else ""
            if value is None or not isinstance(value, (int, float)) or not math.isfinite(value):
                value_text = "--"
                action = ""
            else:
                value_text = f"{value:.2f}"
                action = ""
                buy = buy_thresholds.get(key)
                sell = sell_thresholds.get(key)
                if key == "stoch_rsi":
                    if buy is not None and value <= buy:
                        action = "-Buy"
                    elif sell is not None and value >= sell:
                        action = "-Sell"
                elif key == "willr":
                    if buy is not None and value <= buy:
                        action = "-Buy"
                    elif sell is not None and value >= sell:
                        action = "-Sell"
                elif key == "rsi":
                    if buy is not None and value <= buy:
                        action = "-Buy"
                    elif sell is not None and value >= sell:
                        action = "-Sell"
            entry = f"{label}{interval_tag} {value_text}{action}".strip()
            entries.append(entry)
    if entries:
        entries = _dedupe_indicator_entries_normalized(entries)
    if refresh_requests:
        for cache_key, req in refresh_requests.items():
            _queue_live_indicator_refresh(
                window,
                cache,
                cache_key,
                req.get("symbol") or symbol_norm,
                req.get("interval") or default_interval,
                req.get("keys") or set(),
                indicators_cfg,
                use_live_values,
                indicator_source,
            )
    return entries


class _NumericItem(QtWidgets.QTableWidgetItem):
    def __init__(self, text: str, value: float = 0.0):
        super().__init__(text)
        try:
            self._numeric = float(value)
        except Exception:
            self._numeric = 0.0
        self.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)

    def __lt__(self, other):
        if isinstance(other, _NumericItem):
            return self._numeric < other._numeric
        try:
            return self._numeric < float(other.text().replace('%', '').strip() or 0.0)
        except Exception:
            try:
                return float(self.text().replace('%', '').strip() or 0.0) < float(other.text().replace('%', '').strip() or 0.0)
            except Exception:
                return super().__lt__(other)


def _safe_float(value, default=0.0):
    try:
        if isinstance(value, str):
            value = value.replace('%', '').strip()
            if value == "":
                return float(default)
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value, default=0):
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _normalize_indicator_token(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())

_INDICATOR_TOKEN_TO_KEY: dict[str, str] = {}
for _ind_key, _display_name in INDICATOR_DISPLAY_NAMES.items():
    _key_norm = str(_ind_key or "").strip().lower()
    _key_token = _normalize_indicator_token(_key_norm)
    if _key_token:
        _INDICATOR_TOKEN_TO_KEY.setdefault(_key_token, _key_norm)
    if isinstance(_display_name, str) and _display_name.strip():
        _display_token = _normalize_indicator_token(_display_name)
        if _display_token:
            _INDICATOR_TOKEN_TO_KEY.setdefault(_display_token, _key_norm)

_INDICATOR_TOKEN_ALIASES = {
    "stochrsi": "stoch_rsi",
    "stochasticrsi": "stoch_rsi",
    "srsi": "stoch_rsi",
    "williamsr": "willr",
    "williamspercentr": "willr",
    "wr": "willr",
    "wpr": "willr",
    "relativestrengthindex": "rsi",
}


def _canonicalize_indicator_key(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        text = str(value).strip()
    except Exception:
        return None
    if not text:
        return None
    # Drop interval/action fragments if they leak into indicator fields.
    base = text.split("@", 1)[0].strip()
    low = base.lower()
    if not low:
        return None
    if low in INDICATOR_DISPLAY_NAMES:
        return low
    token = _normalize_indicator_token(low)
    if not token:
        return low
    alias = _INDICATOR_TOKEN_ALIASES.get(token)
    if alias:
        return alias
    mapped = _INDICATOR_TOKEN_TO_KEY.get(token)
    if mapped:
        return mapped
    return low


def _normalize_indicator_values(raw) -> list[str]:
    """
    Ensure indicator collections are returned as canonical, sorted keys.
    Handles legacy booleans/strings and display-name inputs gracefully.
    """
    items: list[str] = []
    if isinstance(raw, (list, tuple, set)):
        iterable = raw
    elif raw in (None, "", False, True):
        iterable = []
    else:
        iterable = [raw]
    for item in iterable:
        canonical = _canonicalize_indicator_key(item)
        if canonical:
            items.append(canonical)
    if not items:
        return []
    # Deduplicate while maintaining deterministic order.
    return sorted(dict.fromkeys(items))

_INDICATOR_DESC_TOKENS = {
    key: _normalize_indicator_token(name)
    for key, name in INDICATOR_DISPLAY_NAMES.items()
    if isinstance(name, str) and name
}

_INDICATOR_DESC_HINTS = {
    "stoch_rsi": {"stochrsi", "stochasticrsi", "srsi"},
    "willr": {"williamsr", "williamspercentr", "wr", "wpr"},
    "rsi": {"rsi", "relativestrengthindex"},
}

def _infer_indicators_from_desc(desc: str | None) -> list[str]:
    if not desc:
        return []
    inferred: set[str] = set()
    segments = [seg.strip() for seg in str(desc).split("|") if "->" in seg]
    for segment in segments:
        norm_segment = _normalize_indicator_token(segment)
        if not norm_segment:
            continue
        for key, token in _INDICATOR_DESC_TOKENS.items():
            if token and token in norm_segment:
                inferred.add(key)
        for key, hints in _INDICATOR_DESC_HINTS.items():
            if any(hint in norm_segment for hint in hints):
                if key == "rsi" and (
                    "stochrsi" in norm_segment or "stochasticrsi" in norm_segment
                ):
                    continue
                inferred.add(key)
    return sorted(inferred)

def _resolve_trigger_indicators(raw, desc: str | None = None) -> list[str]:
    indicators = _normalize_indicator_values(raw)
    if not indicators and desc:
        indicators = _infer_indicators_from_desc(desc)
    if not indicators:
        return []
    return sorted(dict.fromkeys(indicators))


class _StarterCard(QtWidgets.QFrame):
    clicked = QtCore.pyqtSignal(str)

    def __init__(
        self,
        option_key: str,
        title: str,
        subtitle: str,
        accent_color: str,
        badge_text: str | None = None,
        *,
        disabled: bool = False,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.option_key = option_key
        self._accent = accent_color
        self._selected = False
        self._disabled = bool(disabled)
        cursor_shape = (
            QtCore.Qt.CursorShape.ForbiddenCursor if self._disabled else QtCore.Qt.CursorShape.PointingHandCursor
        )
        self.setCursor(cursor_shape)
        self.setObjectName(f"starter_card_{option_key.replace(' ', '_')}")

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.accent_bar = QtWidgets.QFrame()
        self.accent_bar.setFixedHeight(4)
        root.addWidget(self.accent_bar)

        body = QtWidgets.QWidget()
        body_layout = QtWidgets.QVBoxLayout(body)
        body_layout.setContentsMargins(16, 16, 16, 16)
        body_layout.setSpacing(8)
        root.addWidget(body)

        self.badge_label = QtWidgets.QLabel(badge_text or "")
        self.badge_label.setStyleSheet(
            "padding: 2px 8px; border-radius: 7px; font-size: 10px; font-weight: 600;"
            "background-color: rgba(59, 130, 246, 0.15); color: #93c5fd;"
        )
        self.badge_label.setVisible(bool(badge_text))
        body_layout.addWidget(self.badge_label, alignment=QtCore.Qt.AlignmentFlag.AlignLeft)

        self.title_label = QtWidgets.QLabel(title)
        body_layout.addWidget(self.title_label)

        self.subtitle_label = QtWidgets.QLabel(subtitle)
        self.subtitle_label.setWordWrap(True)
        body_layout.addWidget(self.subtitle_label)
        body_layout.addStretch()

        self._refresh_style()

    def setSelected(self, selected: bool) -> None:
        if self._disabled:
            selected = False
        self._selected = bool(selected)
        self._refresh_style()

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if self._disabled:
            event.ignore()
            return
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.clicked.emit(self.option_key)
        super().mouseReleaseEvent(event)

    def is_disabled(self) -> bool:
        return self._disabled

    def _refresh_style(self) -> None:
        effective_selected = self._selected and not self._disabled
        if self._disabled:
            bg = "#10131d"
            border = "#1f2433"
        else:
            bg = "#1b2231" if effective_selected else "#151926"
            border = self._accent if effective_selected else "#242b3d"
        self.setStyleSheet(
            f"""
            QFrame#{self.objectName()} {{
                background-color: {bg};
                border: 2px solid {border};
                border-radius: 16px;
            }}
            """
        )
        if self._disabled:
            bar_color = "#1f2433"
        else:
            bar_color = self._accent if effective_selected else "#1f2433"
        self.accent_bar.setStyleSheet(
            f"background-color: {bar_color}; border-top-left-radius: 16px; border-top-right-radius: 16px;"
        )
        title_color = "#6b7280" if self._disabled else "#f8fafc"
        subtitle_color = "#4b5565" if self._disabled else MUTED_TEXT
        self.title_label.setStyleSheet(f"font-size: 20px; font-weight: 600; color: {title_color};")
        self.subtitle_label.setStyleSheet(f"color: {subtitle_color}; font-size: 12px;")


def _normalize_datetime_pair(value) -> tuple[str, str]:
    """
    Convert various datetime representations into (iso_string, display_string).
    """
    dt_obj = None
    text_value = ""
    if isinstance(value, datetime):
        dt_obj = value
    elif isinstance(value, (int, float)):
        try:
            dt_obj = datetime.fromtimestamp(float(value))
        except Exception:
            dt_obj = None
    elif isinstance(value, str):
        text_value = value.strip()
        if text_value:
            try:
                dt_obj = datetime.fromisoformat(text_value)
            except Exception:
                try:
                    dt_obj = datetime.strptime(text_value, "%Y-%m-%d %H:%M")
                except Exception:
                    dt_obj = None
    if dt_obj is not None:
        iso = dt_obj.isoformat()
        display = dt_obj.strftime("%Y-%m-%d %H:%M")
        return iso, display
    return text_value, text_value or ""

_DBG_BACKTEST_DASHBOARD = True
_DBG_BACKTEST_RUN = True



def _make_engine_key(symbol: str, interval: str, indicators: list[str] | None) -> str:
    base = f"{symbol}@{interval}"
    if indicators:
        base += "#" + ",".join(indicators)
    return base



class _PositionsWorker(QtCore.QObject):
    positions_ready = QtCore.pyqtSignal(list, str)  # rows, account_type
    error = QtCore.pyqtSignal(str)

    def __init__(self, api_key:str, api_secret:str, mode:str, account_type:str, connector_backend: str | None = None, parent=None):
        super().__init__(parent)
        self._api_key = api_key
        self._api_secret = api_secret
        self._mode = mode
        self._acct = account_type
        self._symbols = None  # optional filter set
        self._busy = False
        self._timer = None
        self._wrapper = None
        self._last_err_ts = 0
        self._enabled = True
        self._interval_ms = 5000
        self._spot_filter_cache: dict[str, dict] = {}
        self._connector_backend = _normalize_connector_backend(connector_backend)

    @QtCore.pyqtSlot(int)
    def start_with_interval(self, interval_ms: int):
        try:
            self._enabled = True
            self._interval_ms = int(max(200, int(interval_ms)))
            if self._timer is not None:
                try:
                    self._timer.stop()
                    self._timer.deleteLater()
                except Exception:
                    pass
            self._timer = QtCore.QTimer(self)
            self._timer.setInterval(self._interval_ms)
            self._timer.timeout.connect(self._tick)
            self._timer.start()
            # immediate tick
            try:
                self._tick()
            except Exception:
                pass
        except Exception:
            pass

    @QtCore.pyqtSlot()
    def stop_timer(self):
        try:
            self._enabled = False
            if self._timer is not None:
                try:
                    self._timer.stop()
                    self._timer.deleteLater()
                except Exception:
                    pass
            self._timer = None
        except Exception:
            pass

    @QtCore.pyqtSlot(int)
    def set_interval(self, interval_ms: int):
        try:
            self._interval_ms = int(max(200, int(interval_ms)))
            if self._timer is not None:
                self._timer.setInterval(self._interval_ms)
        except Exception:
            pass

    def configure(self, api_key=None, api_secret=None, mode=None, account_type=None, symbols=None, connector_backend=None):
        if api_key is not None: self._api_key = api_key
        if api_secret is not None: self._api_secret = api_secret
        if mode is not None: self._mode = mode
        if account_type is not None: self._acct = account_type
        if connector_backend is not None:
            self._connector_backend = _normalize_connector_backend(connector_backend)
        self._symbols = set(symbols) if symbols else None
        # force wrapper rebuild on next tick
        self._wrapper = None
        self._spot_filter_cache = {}

    def _ensure_wrapper(self):
        if self._wrapper is None:
            try:
                self._wrapper = BinanceWrapper(
                    self._api_key or "",
                    self._api_secret or "",
                    mode=self._mode or "Live",
                    account_type=self._acct or "Futures",
                    connector_backend=self._connector_backend,
                )
            except Exception:
                self._wrapper = None

    def _compute_futures_metrics(self, p: dict) -> dict:
        try:
            sym = str(p.get('symbol') or '').strip().upper()
            amt = float(p.get('positionAmt') or 0.0)
            try:
                mark = float(p.get('markPrice') or 0.0)
            except Exception:
                mark = 0.0
            raw_mark = mark
            lev = int(float(p.get('leverage') or 0.0)) or 0
            pnl = float(p.get('unRealizedProfit') or 0.0)
            notional = float(p.get('notional') or 0.0)
            entry_price = float(p.get('entryPrice') or 0.0)
            qty_abs = abs(amt)
            if notional <= 0.0 and mark > 0.0 and qty_abs > 0.0:
                notional = qty_abs * mark
            if entry_price <= 0.0 and qty_abs > 0.0 and notional > 0.0:
                entry_price = notional / qty_abs

            # Repair missing/zero mark prices by falling back to alternate sources.
            if mark <= 0.0 or not math.isfinite(mark):
                for key in ("indexPrice", "lastPrice", "estimatedSettlePrice", "oraclePrice", "avgPrice"):
                    try:
                        alt = float(p.get(key) or 0.0)
                    except Exception:
                        alt = 0.0
                    if alt > 0.0:
                        mark = alt
                        break
            if (mark <= 0.0 or not math.isfinite(mark)) and notional > 0.0 and qty_abs > 0.0:
                implied = notional / qty_abs
                if implied > 0.0:
                    mark = implied
            if (mark <= 0.0 or not math.isfinite(mark)) and entry_price > 0.0:
                mark = entry_price
            if (mark <= 0.0 or not math.isfinite(mark)) and sym and self._wrapper is not None:
                try:
                    alt = float(self._wrapper.get_last_price(sym, max_age=2.5) or 0.0)
                    if alt > 0.0:
                        mark = alt
                except Exception:
                    pass

            size_usdt = abs(notional)
            if (size_usdt <= 0.0 or not math.isfinite(size_usdt)) and mark > 0.0 and qty_abs > 0.0:
                size_usdt = qty_abs * mark
                notional = size_usdt

            if ((not math.isfinite(pnl)) or abs(pnl) <= 1e-9 or raw_mark <= 0.0) and mark > 0.0 and entry_price > 0.0 and qty_abs > 0.0:
                pnl = (mark - entry_price) * amt
            elif not math.isfinite(pnl):
                pnl = 0.0

            margin, margin_balance, maint_margin, unrealized_loss = _derive_margin_snapshot(
                p, qty_hint=qty_abs, entry_price_hint=entry_price
            )
            if margin <= 0.0 and size_usdt > 0.0 and lev > 0:
                margin = size_usdt / max(lev, 1)
            margin = max(margin, 0.0)
            margin_balance = max(margin_balance, 0.0)
            roi = (pnl / margin * 100.0) if margin > 0 else 0.0
            pnl_roi_str = f"{pnl:+.2f} USDT ({roi:+.2f}%)"

            # Prefer Binance-provided marginRatio when available, otherwise approximate.
            ratio = normalize_margin_ratio(p.get('marginRatio'))
            if ratio <= 0.0 and margin_balance > 0.0 and maint_margin > 0.0:
                ratio = ((maint_margin + unrealized_loss) / margin_balance) * 100.0
            try:
                update_time = int(float(p.get('updateTime') or p.get('update_time') or 0))
            except Exception:
                update_time = None
            try:
                liq_price = float(p.get('liquidationPrice') or p.get('liqPrice') or 0.0)
            except Exception:
                liq_price = 0.0
            contract_type = str(
                p.get('contractType') or p.get('contract_type') or ""
            ).strip()
            return {
                'size_usdt': size_usdt,
                'margin_usdt': margin,
                'margin_balance': margin_balance,
                'maint_margin': max(maint_margin, 0.0),
                'pnl_roi': pnl_roi_str,
                'margin_ratio': ratio,
                'pnl_value': pnl,
                'roi_percent': roi,
                'update_time': update_time,
                'leverage': lev or None,
                'entry_price': entry_price or None,
                'mark': mark if mark > 0.0 else 0.0,
                'liquidation_price': liq_price if liq_price > 0.0 else 0.0,
                'contract_type': contract_type or None,
            }
        except Exception:
            return {
                'size_usdt': 0.0,
                'margin_usdt': 0.0,
                'margin_balance': 0.0,
                'maint_margin': 0.0,
                'pnl_roi': "-",
                'margin_ratio': 0.0,
                'pnl_value': 0.0,
                'roi_percent': 0.0,
                'update_time': None,
                'leverage': None,
                'mark': 0.0,
            }


    def _tick(self):
        if not self._enabled:
            return
        if self._busy:
            return
        self._busy = True
        try:
            acct = str(self._acct or "FUTURES").upper()
            self._ensure_wrapper()
            if self._wrapper is None:
                return
            rows = []
            if acct == "FUTURES":
                try:
                    positions = self._wrapper.list_open_futures_positions(max_age=0.0, force_refresh=True) or []
                except Exception as e:
                    import time
                    if time.time() - self._last_err_ts > 5:
                        self._last_err_ts = time.time()
                        self.error.emit(f"Positions error: {e}")
                    return
                for p in positions:
                    try:
                        sym = str(p.get('symbol'))
                        if self._symbols and sym not in self._symbols:
                            continue
                        amt = float(p.get('positionAmt') or 0.0)
                        if abs(amt) <= 0.0:
                            continue
                        metrics = self._compute_futures_metrics(p)
                        mark = metrics.get('mark')
                        if mark is None:
                            mark = float(p.get('markPrice') or 0.0)
                        value = metrics.get('size_usdt')
                        if not value:
                            value = abs(amt) * mark if mark else 0.0
                        side_key = 'L' if amt > 0 else 'S'
                        data_row = {
                            'symbol': sym,
                            'qty': abs(amt),
                            'mark': mark or 0.0,
                            'value': value,
                            'side_key': side_key,
                            'raw_position': dict(p),
                        }
                        data_row.update(metrics)
                        data_row['stop_loss_enabled'] = False
                        rows.append(data_row)
                    except Exception:
                        pass
            else:
                # SPOT
                try:
                    balances = self._wrapper.get_balances() or []
                except Exception as e:
                    self.error.emit(f"Spot balances error: {e}")
                    return
                base = "USDT"
                for b in balances:
                    try:
                        asset = b.get("asset")
                        free = float(b.get("free") or 0.0)
                        locked = float(b.get("locked") or 0.0)
                        total = free + locked
                        if asset in (base, None) or total <= 0:
                            continue
                        sym = f"{asset}{base}"
                        if self._symbols and sym not in self._symbols:
                            continue
                        last = float(self._wrapper.get_last_price(sym, max_age=8.0) or 0.0)
                        if last <= 0.0:
                            # If price is missing, don't skip the position. Use 0.0 but keep it to prevent UI auto-close.
                            pass
                        value = total * last
                        cost_snap = None
                        try:
                            cost_snap = self._wrapper.get_spot_position_cost(sym)
                        except Exception:
                            cost_snap = None
                        if cost_snap and cost_snap.get("qty", 0.0) > 0.0:
                            snap_qty = float(cost_snap.get("qty") or 0.0)
                            snap_cost = float(cost_snap.get("cost") or 0.0)
                            if snap_qty > 0.0 and snap_cost > 0.0:
                                cost_per_unit = snap_cost / snap_qty
                                margin_usdt = cost_per_unit * total
                            else:
                                margin_usdt = value
                        else:
                            margin_usdt = value
                        if margin_usdt <= 0.0:
                            margin_usdt = value
                        pnl_value = value - margin_usdt
                        roi = (pnl_value / margin_usdt * 100.0) if margin_usdt > 0 else 0.0
                        pnl_roi = f"{pnl_value:+.2f} USDT ({roi:+.2f}%)"
                        filters = self._spot_filter_cache.get(sym)
                        if filters is None:
                            try:
                                filters = self._wrapper.get_spot_symbol_filters(sym) or {}
                            except Exception:
                                filters = {}
                            self._spot_filter_cache[sym] = filters
                        min_notional = 0.0
                        try:
                            min_notional = float(filters.get('minNotional', 0.0) or 0.0)
                        except Exception:
                            min_notional = 0.0
                        # Don't skip if value < min_notional, just log or allow it. 
                        # Skipping causes the UI to think the position is closed.
                        # if min_notional > 0.0 and value < min_notional:
                        #    continue
                        rows.append({
                            'symbol': sym,
                            'qty': total,
                            'mark': last,
                            'value': value,
                            'size_usdt': value,
                            'margin_usdt': margin_usdt,
                            'pnl_roi': pnl_roi,
                            'pnl_value': pnl_value,
                            'side_key': 'L',  # treat spot as long for aggregation/indicators
                            'raw_position': {
                                'cost_usdt': margin_usdt,
                                'qty_total': total,
                            },
                            'stop_loss_enabled': False,
                        })
                    except Exception:
                        pass
            self.positions_ready.emit(rows, acct)
        finally:
            self._busy = False


class _BacktestWorker(QtCore.QThread):
    progress = QtCore.pyqtSignal(str)
    finished = QtCore.pyqtSignal(dict, object)

    def __init__(self, engine: BacktestEngine, request: BacktestRequest, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.request = request
        self._stop_requested = False

    def request_stop(self):
        self._stop_requested = True

    def run(self):
        try:
            result = self.engine.run(self.request, progress=self.progress.emit,
                                     should_stop=lambda: bool(self._stop_requested))
            self.finished.emit(result, None)
        except Exception as exc:
            self.finished.emit({}, exc)
from ..position_guard import IntervalPositionGuard
from .param_dialog import ParamDialog

class _LazyWebEmbed(QtWidgets.QWidget):
    def __init__(self, url: str, parent=None) -> None:
        super().__init__(parent)
        self._url = str(url or "").strip()
        self._view = None
        self._loaded_once = False
        self._native_primed = False
        self._cursor_filter_installed = False

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._stack = QtWidgets.QStackedWidget()
        layout.addWidget(self._stack)

        self._fallback_label = QtWidgets.QLabel("Loading web view...")
        self._fallback_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._fallback_label.setWordWrap(True)
        self._stack.addWidget(self._fallback_label)

    def prime_native_host(self) -> None:
        if self._native_primed:
            return
        if not _native_chart_host_prewarm_enabled():
            return
        self._native_primed = True
        # Pre-create native handles to avoid top-level flicker when WebEngine initializes.
        for widget in (self, self._stack):
            try:
                widget.setAttribute(QtCore.Qt.WidgetAttribute.WA_NativeWindow, True)
            except Exception:
                pass
            try:
                widget.winId()
            except Exception:
                pass

    def showEvent(self, event: QtGui.QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        self.prime_native_host()
        if self._loaded_once:
            return
        self._loaded_once = True
        self._ensure_view()

    def set_url(self, url: str) -> None:
        url = str(url or "").strip()
        if not url:
            return
        self._url = url
        if self._view is not None:
            try:
                self._view.load(QtCore.QUrl(self._url))
            except Exception:
                pass

    def reload(self) -> None:
        if self._view is None:
            return
        try:
            self._view.reload()
        except Exception:
            pass

    def _set_fallback_text(self, text: str) -> None:
        self._fallback_label.setText(text)
        try:
            self._stack.setCurrentWidget(self._fallback_label)
        except Exception:
            pass

    def _ensure_view(self) -> None:
        reason = _webengine_embed_unavailable_reason()
        if reason:
            self._set_fallback_text(f"{reason}\n\nUse 'Open in Browser' to view the heatmap.")
            return
        self.prime_native_host()
        try:
            host_window = self.window()
            start_guard = getattr(host_window, "_start_webengine_close_guard", None)
            if callable(start_guard):
                start_guard()
        except Exception:
            pass
        try:
            _configure_tradingview_webengine_env()
        except Exception:
            pass
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
        except Exception as exc:
            self._set_fallback_text(f"QtWebEngine unavailable: {exc}")
            return

        view = QWebEngineView(self)
        self._configure_view(view)
        self._view = view
        self._stack.insertWidget(0, view)
        self._stack.setCurrentWidget(view)
        try:
            view.installEventFilter(self)
            self._cursor_filter_installed = True
        except Exception:
            self._cursor_filter_installed = False
        if self._url:
            try:
                view.load(QtCore.QUrl(self._url))
            except Exception:
                pass

    def _configure_view(self, view) -> None:
        try:
            view.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.NoContextMenu)
        except Exception:
            pass
        try:
            settings = view.settings()
            settings.setAttribute(settings.WebAttribute.LocalStorageEnabled, True)
            settings.setAttribute(settings.WebAttribute.JavascriptCanOpenWindows, False)
            settings.setAttribute(settings.WebAttribute.JavascriptCanCloseWindows, False)
            settings.setAttribute(settings.WebAttribute.HyperlinkAuditingEnabled, False)
            if hasattr(settings.WebAttribute, "Accelerated2dCanvasEnabled"):
                settings.setAttribute(settings.WebAttribute.Accelerated2dCanvasEnabled, True)
            if hasattr(settings.WebAttribute, "WebGLEnabled"):
                settings.setAttribute(settings.WebAttribute.WebGLEnabled, True)
        except Exception:
            pass
        try:
            profile = view.page().profile()
            profile.setHttpUserAgent(_DEFAULT_WEB_UA)
        except Exception:
            pass

    def eventFilter(self, obj, event):  # noqa: N802
        if obj is getattr(self, "_view", None):
            try:
                if event.type() == QtCore.QEvent.Type.CursorChange:
                    shape = self._view.cursor().shape()
                    if shape in {
                        QtCore.Qt.CursorShape.PointingHandCursor,
                        QtCore.Qt.CursorShape.OpenHandCursor,
                        QtCore.Qt.CursorShape.ClosedHandCursor,
                    }:
                        self._view.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
            except Exception:
                pass
        return super().eventFilter(obj, event)

class MainWindow(QtWidgets.QWidget):
    log_signal = pyqtSignal(str)
    trade_signal = pyqtSignal(dict)

    # thread-safe control signals for positions worker
    req_pos_start = QtCore.pyqtSignal(int)
    req_pos_stop = QtCore.pyqtSignal()
    req_pos_set_interval = QtCore.pyqtSignal(int)

    def _on_trade_signal(self, order_info: dict):
        return _mw_on_trade_signal(self, order_info)

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
        self.config.setdefault("selected_exchange", next(iter(EXCHANGE_PATHS)))
        self.config.setdefault("code_language", next(iter(LANGUAGE_PATHS)))
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
        self._starter_market_cards = {}
        self._starter_crypto_cards = {}
        self._starter_forex_cards = {}
        self._code_tab_selected_market = self.config.get("code_market") or "crypto"
        self._ensure_runtime_connector_for_account(self.config.get("account_type") or "Futures", force_default=False)
        self._override_debug_verbose = bool(self.config.get("debug_override_verbose", False))
        self.init_ui()
        self.log_signal.connect(self._buffer_log)
        self.trade_signal.connect(self._on_trade_signal)
        try:
            self._prewarm_webengine_runtime()
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

    def _backtest_add_selected_to_dashboard(self, rows: list[int] | None = None):
        try:
            def _dbg(msg: str) -> None:
                if not _DBG_BACKTEST_DASHBOARD:
                    return
                try:
                    self.log(f"[Backtest->Dashboard] {msg}")
                except Exception:
                    pass

            if isinstance(rows, bool):
                _dbg(f"Received rows bool={rows}; normalizing to None")
                rows = None
            table = getattr(self, "backtest_results_table", None)
            raw_results = getattr(self, "backtest_results", [])
            _dbg(f"Raw results type={type(raw_results).__name__}")
            if isinstance(raw_results, list):
                results = list(raw_results)
            elif isinstance(raw_results, tuple):
                results = list(raw_results)
            elif isinstance(raw_results, dict):
                results = [dict(raw_results)]
            elif raw_results in (None, False, True):
                results = []
            else:
                results = [raw_results]
            normalized_results = []
            for entry in results:
                try:
                    normalized_results.append(self._normalize_backtest_run(entry))
                except Exception:
                    try:
                        dict_candidate = dict(entry)
                        normalized_results.append(self._normalize_backtest_run(dict_candidate))
                    except Exception:
                        _dbg(f"Dropping non-normalizable entry type={type(entry).__name__}")
                        continue
            results = normalized_results
            _dbg(f"Normalized results count={len(results)}")
            try:
                self.backtest_results = list(results)
            except Exception:
                pass
            if table is None or not results:
                try:
                    self.backtest_status_label.setText("No backtest results available to import.")
                except Exception:
                    pass
                _dbg("No results or table; aborting.")
                return
            if rows is None:
                selection = table.selectionModel()
                if selection is None:
                    _dbg("Selection model missing; aborting.")
                    return
                target_rows = sorted({index.row() for index in selection.selectedRows()})
                if not target_rows:
                    try:
                        self.backtest_status_label.setText("Select one or more backtest rows to add.")
                    except Exception:
                        pass
                    _dbg("No rows selected via UI.")
                    return
            else:
                target_rows = sorted({int(r) for r in rows if isinstance(r, int)})
                if not target_rows:
                    try:
                        self.backtest_status_label.setText("No backtest rows available to add.")
                    except Exception:
                        pass
                    _dbg("Row indices arg empty after filtering.")
                    return
            _dbg(f"Target row count={len(target_rows)}")
            runtime_pairs = self._override_config_list("runtime")
            if not isinstance(runtime_pairs, list):
                try:
                    runtime_pairs = list(runtime_pairs)
                except TypeError:
                    runtime_pairs = []
                try:
                    ctx_runtime = self._override_ctx("runtime")
                    cfg_key_runtime = ctx_runtime.get("config_key")
                    if cfg_key_runtime:
                        self.config[cfg_key_runtime] = runtime_pairs
                except Exception:
                    pass
            _dbg(f"Existing runtime pairs before cleanup: type={type(runtime_pairs).__name__}, len={len(runtime_pairs or [])}")
            existing = {}
            clean_runtime_pairs: list[dict] = []
            for entry in runtime_pairs or []:
                if not isinstance(entry, dict):
                    _dbg(f"Skipping non-dict runtime entry type={type(entry).__name__}")
                    continue
                sym = str((entry or {}).get("symbol") or "").strip().upper()
                iv = str((entry or {}).get("interval") or "").strip()
                indicators = _normalize_indicator_values((entry or {}).get("indicators"))
                lev_existing = None
                controls_existing = entry.get("strategy_controls")
                if isinstance(controls_existing, dict):
                    lev_existing = controls_existing.get("leverage")
                if lev_existing is None:
                    lev_existing = entry.get("leverage")
                try:
                    if lev_existing is not None:
                        lev_existing = max(1, int(float(lev_existing)))
                except Exception:
                    lev_existing = None
                key = (sym, iv, tuple(indicators), lev_existing)
                existing[key] = entry
                clean_runtime_pairs.append(entry)
            if runtime_pairs is not None:
                try:
                    runtime_pairs.clear()
                    runtime_pairs.extend(clean_runtime_pairs)
                except Exception:
                    pass
            row_count = table.rowCount()

            def _row_payload(row_idx: int) -> dict:
                payload = None
                try:
                    item = table.item(row_idx, 0)
                except Exception:
                    item = None
                if item is not None:
                    try:
                        payload = item.data(QtCore.Qt.ItemDataRole.UserRole)
                    except Exception:
                        payload = None
                if isinstance(payload, dict):
                    return dict(payload)
                if 0 <= row_idx < len(results):
                    return dict(results[row_idx])
                return {}

            added_count = 0
            for row_idx in target_rows:
                if row_idx < 0 or row_idx >= row_count:
                    _dbg(f"Row {row_idx} out of bounds (table rows={row_count})")
                    continue
                data = self._normalize_backtest_run(_row_payload(row_idx))
                _dbg(f"Row {row_idx} normalized data: {data}")
                sym = str(data.get("symbol") or "").strip().upper()
                iv = str(data.get("interval") or "").strip()
                if not sym or not iv:
                    _dbg(f"Row {row_idx} missing sym/interval")
                    continue
                indicators_clean = _normalize_indicator_values(data.get("indicator_keys"))

                # Determine strategy controls / leverage to use for deduping and persistence
                controls_snapshot = self._collect_strategy_controls("backtest")
                controls_to_apply = None
                stop_cfg = None
                loop_override_value = None
                leverage_for_key = None

                if controls_snapshot:
                    _dbg(f"Row {row_idx} using live controls snapshot")
                    controls_to_apply = copy.deepcopy(controls_snapshot)
                    stop_cfg = controls_to_apply.get("stop_loss")
                    loop_override_value = self._normalize_loop_override(controls_to_apply.get("loop_interval_override"))
                    leverage_for_key = controls_to_apply.get("leverage")
                else:
                    stored_controls = data.get("strategy_controls")
                    if isinstance(stored_controls, dict):
                        _dbg(f"Row {row_idx} using stored controls from result")
                        controls_to_apply = copy.deepcopy(stored_controls)
                        stop_cfg = controls_to_apply.get("stop_loss")
                        loop_override_value = self._normalize_loop_override(controls_to_apply.get("loop_interval_override"))
                        leverage_for_key = controls_to_apply.get("leverage")

                if leverage_for_key is None:
                    leverage_for_key = data.get("leverage")
                try:
                    if leverage_for_key is not None:
                        leverage_for_key = max(1, int(float(leverage_for_key)))
                except Exception:
                    leverage_for_key = None

                key = (sym, iv, tuple(indicators_clean), leverage_for_key)
                if key in existing:
                    _dbg(f"Row {row_idx} already exists; skipping")
                    continue

                entry = {"symbol": sym, "interval": iv}
                if indicators_clean:
                    entry["indicators"] = list(indicators_clean)
                base_loop_value = self._normalize_loop_override(data.get("loop_interval_override"))
                if base_loop_value:
                    entry["loop_interval_override"] = base_loop_value
                if loop_override_value:
                    entry["loop_interval_override"] = loop_override_value
                if controls_to_apply:
                    entry["strategy_controls"] = controls_to_apply
                if isinstance(stop_cfg, dict):
                    stop_cfg = normalize_stop_loss_dict(stop_cfg)
                    entry["stop_loss"] = stop_cfg
                    if isinstance(controls_to_apply, dict):
                        controls_to_apply["stop_loss"] = stop_cfg
                else:
                    data_stop_cfg = data.get("stop_loss")
                    if isinstance(data_stop_cfg, dict):
                        stop_cfg_norm = normalize_stop_loss_dict(data_stop_cfg)
                        entry["stop_loss"] = stop_cfg_norm
                        if isinstance(controls_to_apply, dict):
                            controls_to_apply.setdefault("stop_loss", stop_cfg_norm)
                if leverage_for_key is not None:
                    entry["leverage"] = leverage_for_key

                runtime_pairs.append(entry)
                existing[key] = entry
                added_count += 1
                _dbg(f"Row {row_idx} appended: indicators={indicators_clean}, leverage={leverage_for_key}, has_controls={'strategy_controls' in entry}")
            if added_count:
                self._refresh_symbol_interval_pairs("runtime")
                try:
                    self.backtest_status_label.setText(f"Added {added_count} row(s) to dashboard overrides.")
                except Exception:
                    pass
                _dbg(f"Completed: appended {added_count} entries.")
            else:
                try:
                    self.backtest_status_label.setText("Selected results already exist in dashboard overrides.")
                except Exception:
                    pass
                _dbg("No new entries were added (duplicates?).")
        except Exception as exc:
            try:
                self.backtest_status_label.setText(f"Add to dashboard failed: {exc}")
            except Exception:
                pass
            try:
                if _DBG_BACKTEST_DASHBOARD:
                    tb = traceback.format_exc()
                    self.log(f"[Backtest->Dashboard] error: {exc}\n{tb}")
                else:
                    self.log(f"Add backtest results to dashboard error: {exc}")
            except Exception:
                pass

    def _backtest_add_all_to_dashboard(self):
        try:
            table = getattr(self, "backtest_results_table", None)
            if table is None:
                try:
                    self.backtest_status_label.setText("No backtest results table available.")
                except Exception:
                    pass
                return
            all_rows = list(range(table.rowCount()))
            if not all_rows:
                try:
                    self.backtest_status_label.setText("No backtest rows available to add.")
                except Exception:
                    pass
                return
            self._backtest_add_selected_to_dashboard(rows=all_rows)
        except Exception as exc:
            try:
                self.backtest_status_label.setText(f"Add all failed: {exc}")
            except Exception:
                pass
            try:
                self.log(f"Add all backtest results to dashboard error: {exc}")
            except Exception:
                pass

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

    @staticmethod
    def _coerce_qdate(value):
        if isinstance(value, QtCore.QDate):
            return value
        if isinstance(value, datetime):
            return QtCore.QDate(value.year, value.month, value.day)
        if isinstance(value, str):
            # Try common formats
            for fmt in ("yyyy-MM-dd", "yyyy/MM/dd", "dd.MM.yyyy"):
                qd = QtCore.QDate.fromString(value, fmt)
                if qd.isValid():
                    return qd
            try:
                dt = datetime.fromisoformat(value)
                return QtCore.QDate(dt.year, dt.month, dt.day)
            except Exception:
                pass
        return QtCore.QDate.currentDate()

    @staticmethod
    def _coerce_qdatetime(value):
        if isinstance(value, QtCore.QDateTime):
            return value
        if isinstance(value, datetime):
            return QtCore.QDateTime(value)
        if isinstance(value, str):
            from datetime import datetime as _dt
            for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
                try:
                    dt = _dt.strptime(value, fmt)
                    return QtCore.QDateTime(QtCore.QDate(dt.year, dt.month, dt.day), QtCore.QTime(dt.hour, dt.minute))
                except Exception:
                    continue
            try:
                dt = _dt.fromisoformat(value)
                return QtCore.QDateTime(QtCore.QDate(dt.year, dt.month, dt.day), QtCore.QTime(dt.hour, dt.minute))
            except Exception:
                pass
        current = QtCore.QDateTime.currentDateTime()
        return current

    def _initialize_backtest_ui_defaults(self):
        fetch_triggered = False
        try:
            source = self.backtest_config.get("symbol_source") or "Futures"
            idx = self.backtest_symbol_source_combo.findText(source)
            if idx is not None and idx >= 0 and self.backtest_symbol_source_combo.currentIndex() != idx:
                self.backtest_symbol_source_combo.setCurrentIndex(idx)
                fetch_triggered = True
        except Exception:
            pass
        try:
            self._populate_backtest_lists()
        except Exception:
            pass
        try:
            if self.backtest_stop_btn is not None:
                self.backtest_stop_btn.setEnabled(False)
        except Exception:
            pass
        try:
            logic = (self.backtest_config.get("logic") or "AND").upper()
            def _set_combo(combo: QtWidgets.QComboBox, value: str):
                if combo is None:
                    return
                try:
                    target = (value or "").strip().lower()
                    for i in range(combo.count()):
                        if combo.itemText(i).strip().lower() == target:
                            combo.setCurrentIndex(i)
                            return
                except Exception:
                    pass
            _set_combo(self.backtest_logic_combo, logic)
            capital = float(self.backtest_config.get("capital", 1000.0))
            self.backtest_capital_spin.setValue(capital)
            pct_cfg = float(self.backtest_config.get("position_pct", 2.0) or 0.0)
            if pct_cfg <= 1.0:
                pct_disp = pct_cfg * 100.0
                self.backtest_pospct_spin.setValue(pct_disp)
                self._update_backtest_config("position_pct", pct_disp)
            else:
                self.backtest_pospct_spin.setValue(pct_cfg)
            side_cfg = (self.backtest_config.get("side") or "BOTH").upper()
            side_label = SIDE_LABELS.get(side_cfg, SIDE_LABELS["BOTH"])
            try:
                idx_side = self.backtest_side_combo.findText(side_label, QtCore.Qt.MatchFlag.MatchFixedString)
            except Exception:
                idx_side = self.backtest_side_combo.findText(side_label)
            if idx_side is not None and idx_side >= 0:
                self.backtest_side_combo.setCurrentIndex(idx_side)
            margin_mode_cfg = (self.backtest_config.get("margin_mode") or "Isolated")
            _set_combo(self.backtest_margin_mode_combo, margin_mode_cfg)
            position_mode_cfg = (self.backtest_config.get("position_mode") or "Hedge")
            _set_combo(self.backtest_position_mode_combo, position_mode_cfg)
            assets_mode_cfg = self._normalize_assets_mode(self.backtest_config.get("assets_mode"))
            idx_assets = self.backtest_assets_mode_combo.findData(assets_mode_cfg)
            if idx_assets is not None and idx_assets >= 0:
                with QtCore.QSignalBlocker(self.backtest_assets_mode_combo):
                    self.backtest_assets_mode_combo.setCurrentIndex(idx_assets)
            account_mode_cfg = self._normalize_account_mode(self.backtest_config.get("account_mode"))
            idx_account_mode = self.backtest_account_mode_combo.findData(account_mode_cfg)
            if idx_account_mode is not None and idx_account_mode >= 0:
                with QtCore.QSignalBlocker(self.backtest_account_mode_combo):
                    self.backtest_account_mode_combo.setCurrentIndex(idx_account_mode)
            leverage_cfg = int(self.backtest_config.get("leverage", 5) or 1)
            self.backtest_leverage_spin.setValue(leverage_cfg)
            loop_cfg = self._normalize_loop_override(self.backtest_config.get("loop_interval_override")) or ""
            if hasattr(self, "backtest_loop_combo"):
                self._set_loop_combo_value(self.backtest_loop_combo, loop_cfg)
            self.backtest_config["loop_interval_override"] = loop_cfg
            now_dt = QtCore.QDateTime.currentDateTime()
            start_cfg = self.backtest_config.get("start_date")
            end_cfg = self.backtest_config.get("end_date")
            end_qdt = self._coerce_qdatetime(end_cfg) if end_cfg else now_dt
            if not end_qdt.isValid():
                end_qdt = now_dt
            start_qdt = self._coerce_qdatetime(start_cfg) if start_cfg else end_qdt.addMonths(-3)
            if not start_qdt.isValid() or start_qdt > end_qdt:
                start_qdt = end_qdt.addMonths(-3)
            self.backtest_start_edit.setDateTime(start_qdt)
            self.backtest_end_edit.setDateTime(end_qdt)
        except Exception:
            pass
        try:
            self._update_backtest_stop_loss_widgets()
        except Exception:
            pass
        self._update_backtest_futures_controls()
        if not fetch_triggered:
            self._refresh_backtest_symbols()

    def _populate_backtest_lists(self):
        try:
            if not self.backtest_symbols_all:
                fallback_ordered: list[str] = []

                def _extend_unique(seq):
                    for sym in seq or []:
                        sym_up = str(sym).strip().upper()
                        if not sym_up:
                            continue
                        if sym_up not in fallback_ordered:
                            fallback_ordered.append(sym_up)

                _extend_unique(self.backtest_config.get("symbols"))
                _extend_unique(self.config.get("symbols"))
                try:
                    if hasattr(self, "symbol_list"):
                        for i in range(self.symbol_list.count()):
                            item = self.symbol_list.item(i)
                            if item:
                                _extend_unique([item.text()])
                except Exception:
                    pass
                if not fallback_ordered:
                    fallback_ordered.append("BTCUSDT")
                self.backtest_symbols_all = list(fallback_ordered)
            self._update_backtest_symbol_list(self.backtest_symbols_all)
        except Exception:
            pass

        interval_candidates: list[str] = []

        def _extend_interval(seq):
            for iv in seq or []:
                iv_norm = str(iv).strip()
                if not iv_norm:
                    continue
                if iv_norm not in interval_candidates:
                    interval_candidates.append(iv_norm)

        _extend_interval(self.backtest_config.get("intervals"))
        try:
            if hasattr(self, "interval_list"):
                for i in range(self.interval_list.count()):
                    item = self.interval_list.item(i)
                    if item:
                        _extend_interval([item.text()])
        except Exception:
            pass
        _extend_interval(BACKTEST_INTERVAL_ORDER)
        if not interval_candidates:
            interval_candidates.append("1h")

        ordered_intervals = [iv for iv in BACKTEST_INTERVAL_ORDER if iv in interval_candidates]
        extras = [iv for iv in interval_candidates if iv not in BACKTEST_INTERVAL_ORDER]
        full_order = ordered_intervals + extras

        selected_intervals = [iv for iv in (self.backtest_config.get("intervals") or []) if iv in full_order]
        if not selected_intervals and full_order:
            selected_intervals = [full_order[0]]
        with QtCore.QSignalBlocker(self.backtest_interval_list):
            self.backtest_interval_list.clear()
            for iv in full_order:
                item = QtWidgets.QListWidgetItem(iv)
                item.setSelected(iv in selected_intervals)
                self.backtest_interval_list.addItem(item)
        self.backtest_config["intervals"] = list(selected_intervals)
        cfg = self.config.setdefault("backtest", {})
        cfg["intervals"] = list(selected_intervals)
        self._backtest_store_intervals()

    def _set_backtest_symbol_selection(self, symbols):
        symbols_upper = {str(s).upper() for s in (symbols or []) if s}
        with QtCore.QSignalBlocker(self.backtest_symbol_list):
            for i in range(self.backtest_symbol_list.count()):
                item = self.backtest_symbol_list.item(i)
                if not item:
                    continue
                item.setSelected(item.text().upper() in symbols_upper)
        self._backtest_store_symbols()

    def _apply_backtest_symbol_selection_rule(self, rule: dict | None) -> bool:
        if not rule:
            return True
        rule_type = str(rule.get("type") or "").lower()
        if rule_type == "top_volume":
            try:
                count = int(rule.get("count", 0) or 0)
            except Exception:
                count = 0
            if count <= 0:
                return True
            symbols_pool = list(self.backtest_symbols_all or [])
            if len(symbols_pool) < count:
                return False
            selection = [sym.upper() for sym in symbols_pool[:count]]
            self._set_backtest_symbol_selection(selection)
            try:
                self.backtest_symbol_list.scrollToTop()
            except Exception:
                pass
            try:
                self.backtest_status_label.setText(f"Template applied: selected top {count} volume symbols.")
            except Exception:
                pass
            return True
        return False

    def _set_backtest_interval_selection(self, intervals):
        intervals_norm = {str(iv) for iv in (intervals or []) if iv}
        with QtCore.QSignalBlocker(self.backtest_interval_list):
            for i in range(self.backtest_interval_list.count()):
                item = self.backtest_interval_list.item(i)
                if not item:
                    continue
                item.setSelected(item.text() in intervals_norm)
        self._backtest_store_intervals()

    def _update_backtest_symbol_list(self, candidates):
        try:
            candidates = [str(sym).upper() for sym in (candidates or []) if sym]
            unique_candidates: list[str] = []
            seen = set()
            for sym in candidates:
                if sym and sym not in seen:
                    seen.add(sym)
                    unique_candidates.append(sym)
            selected_cfg = [str(s).upper() for s in (self.backtest_config.get("symbols") or []) if s]
            selected = [s for s in selected_cfg if s in unique_candidates]
            if not unique_candidates and selected_cfg:
                unique_candidates = []
                seen.clear()
                for sym in selected_cfg:
                    if sym and sym not in seen:
                        seen.add(sym)
                        unique_candidates.append(sym)
                selected = list(unique_candidates)
            if not selected and unique_candidates:
                selected = [unique_candidates[0]]
            selected_set = {str(sym).upper() for sym in (selected or []) if sym}
            try:
                self.backtest_symbol_list.setUpdatesEnabled(False)
            except Exception:
                pass
            try:
                with QtCore.QSignalBlocker(self.backtest_symbol_list):
                    self.backtest_symbol_list.clear()
                    if unique_candidates:
                        self.backtest_symbol_list.addItems(unique_candidates)
                        if selected_set:
                            for i in range(self.backtest_symbol_list.count()):
                                item = self.backtest_symbol_list.item(i)
                                if item and item.text().upper() in selected_set:
                                    item.setSelected(True)
            finally:
                try:
                    self.backtest_symbol_list.setUpdatesEnabled(True)
                except Exception:
                    pass
            self.backtest_symbols_all = list(unique_candidates)
            self.backtest_config["symbols"] = list(selected)
            cfg = self.config.setdefault("backtest", {})
            cfg["symbols"] = list(selected)
            if unique_candidates and not selected and self.backtest_symbol_list.count():
                self.backtest_symbol_list.item(0).setSelected(True)
            self._backtest_store_symbols()
        except Exception:
            pass

    def _backtest_store_symbols(self):
        try:
            symbols = []
            for i in range(self.backtest_symbol_list.count()):
                item = self.backtest_symbol_list.item(i)
                if item and item.isSelected():
                    symbols.append(item.text().upper())
            self.backtest_config["symbols"] = symbols
            cfg = self.config.setdefault("backtest", {})
            cfg["symbols"] = list(symbols)
        except Exception:
            pass

    def _backtest_store_intervals(self):
        try:
            intervals = []
            for i in range(self.backtest_interval_list.count()):
                item = self.backtest_interval_list.item(i)
                if item and item.isSelected():
                    intervals.append(item.text())
            self.backtest_config["intervals"] = intervals
            cfg = self.config.setdefault("backtest", {})
            cfg["intervals"] = list(intervals)
        except Exception:
            pass

    def _apply_backtest_intervals_to_dashboard(self):
        try:
            intervals = [
                str(iv).strip()
                for iv in (self.backtest_config.get("intervals") or [])
                if str(iv).strip()
            ]
        except Exception:
            intervals = []
        if not intervals:
            intervals = list(BACKTEST_INTERVAL_ORDER)
        existing = {self.interval_list.item(i).text() for i in range(self.interval_list.count())}
        for iv in intervals:
            if iv not in existing:
                self.interval_list.addItem(QtWidgets.QListWidgetItem(iv))
        with QtCore.QSignalBlocker(self.interval_list):
            for i in range(self.interval_list.count()):
                item = self.interval_list.item(i)
                if item is None:
                    continue
                item.setSelected(item.text() in intervals)
        try:
            self.config["intervals"] = list(intervals)
        except Exception:
            pass
        try:
            self._reconfigure_positions_worker()
        except Exception:
            pass

    def _update_backtest_futures_controls(self):
        try:
            source = (self.backtest_symbol_source_combo.currentText() or "Futures").strip().lower()
            is_futures = source.startswith("fut")
        except Exception:
            is_futures = True
        for widget in getattr(self, "_backtest_futures_widgets", []):
            if widget is None:
                continue
            try:
                widget.setVisible(is_futures)
                widget.setEnabled(is_futures)
            except Exception:
                pass

    def _backtest_symbol_source_changed(self, text: str):
        self._update_backtest_config("symbol_source", text)
        self._update_backtest_futures_controls()
        self._refresh_backtest_connector_options(text, force_default=True)
        self._refresh_backtest_symbols()

    def _refresh_backtest_symbols(self):
        try:
            worker = getattr(self, "_backtest_symbol_worker", None)
            if worker is not None and worker.isRunning():
                return
        except Exception:
            pass
        if not hasattr(self, "backtest_refresh_symbols_btn"):
            return
        self.backtest_refresh_symbols_btn.setEnabled(False)
        self.backtest_refresh_symbols_btn.setText("Refreshing...")
        source_text = (self.backtest_symbol_source_combo.currentText() or "Futures").strip()
        source_lower = source_text.lower()
        acct = "Spot" if source_lower.startswith("spot") else "Futures"
        api_key = self.api_key_edit.text().strip()
        api_secret = self.api_secret_edit.text().strip()
        mode = self.mode_combo.currentText()

        def _do():
            wrapper = self._create_binance_wrapper(
                api_key=api_key,
                api_secret=api_secret,
                mode=mode,
                account_type=acct,
                connector_backend=self._backtest_connector_backend(),
            )
            return wrapper.fetch_symbols(sort_by_volume=True, top_n=_SYMBOL_FETCH_TOP_N)

        worker = CallWorker(_do, parent=self)
        try:
            worker.progress.connect(self.log)
        except Exception:
            pass
        worker.done.connect(lambda res, err, src=acct: self._on_backtest_symbols_ready(res, err, src))
        self._backtest_symbol_worker = worker
        try:
            self.backtest_status_label.setText(f"Refreshing {acct.upper()} symbols...")
        except Exception:
            pass
        worker.start()

    def _on_backtest_symbols_ready(self, result, error, source_label):
        try:
            self.backtest_refresh_symbols_btn.setEnabled(True)
            self.backtest_refresh_symbols_btn.setText("Refresh")
        except Exception:
            pass
        self._backtest_symbol_worker = None
        if error or not result:
            msg = f"Backtest symbol refresh failed: {error or 'no symbols returned'}"
            self.log(msg)
            try:
                self.backtest_status_label.setText(msg)
            except Exception:
                pass
            return
        symbols = [str(sym).upper() for sym in (result or []) if sym]
        self.backtest_symbols_all = symbols
        self._update_backtest_symbol_list(symbols)
        if self._backtest_pending_symbol_selection:
            if self._apply_backtest_symbol_selection_rule(self._backtest_pending_symbol_selection):
                self._backtest_pending_symbol_selection = None
        msg = f"Loaded {len(symbols)} {source_label.upper()} symbols for backtest."
        self.log(msg)
        try:
            self.backtest_status_label.setText(msg)
        except Exception:
            pass

    def _backtest_dates_changed(self):
        try:
            start_dt = self.backtest_start_edit.dateTime().toString("dd.MM.yyyy HH:mm:ss")
            end_dt = self.backtest_end_edit.dateTime().toString("dd.MM.yyyy HH:mm:ss")
            self.backtest_config["start_date"] = start_dt
            self.backtest_config["end_date"] = end_dt
            cfg = self.config.setdefault("backtest", {})
            cfg["start_date"] = start_dt
            cfg["end_date"] = end_dt
        except Exception:
            pass

    def _get_selected_mdd_logic(self) -> str:
        try:
            combo = getattr(self, "backtest_mdd_combo", None)
            if combo is not None and combo.count():
                value = combo.currentData(QtCore.Qt.ItemDataRole.UserRole)
                if value in MDD_LOGIC_OPTIONS:
                    return str(value)
        except Exception:
            pass
        value = str(self.backtest_config.get("mdd_logic", MDD_LOGIC_DEFAULT) or "").lower()
        return value if value in MDD_LOGIC_OPTIONS else MDD_LOGIC_DEFAULT

    def _set_backtest_mdd_selection(self, logic: str | None, *, update_config: bool = False) -> str:
        logic_norm = str(logic or MDD_LOGIC_DEFAULT).lower()
        if logic_norm not in MDD_LOGIC_OPTIONS:
            logic_norm = MDD_LOGIC_DEFAULT
        try:
            combo = getattr(self, "backtest_mdd_combo", None)
            if combo is not None and combo.count():
                with QtCore.QSignalBlocker(combo):
                    idx = combo.findData(logic_norm)
                    if idx < 0:
                        idx = 0
                    combo.setCurrentIndex(idx)
                    data = combo.itemData(combo.currentIndex(), QtCore.Qt.ItemDataRole.UserRole)
                    if data in MDD_LOGIC_OPTIONS:
                        logic_norm = str(data)
        except Exception:
            pass
        if update_config:
            self._update_backtest_config("mdd_logic", logic_norm)
        return logic_norm

    def _on_backtest_mdd_logic_changed(self, _index: int = -1):
        try:
            logic = self._get_selected_mdd_logic()
            self._update_backtest_config("mdd_logic", logic)
        except Exception:
            pass

    def _get_selected_template_key(self) -> str | None:
        try:
            combo = getattr(self, "backtest_template_combo", None)
            if combo is not None and combo.count():
                value = combo.currentData(QtCore.Qt.ItemDataRole.UserRole)
                if value in BACKTEST_TEMPLATE_DEFINITIONS:
                    return value
        except Exception:
            pass
        template_cfg = self.backtest_config.get("template", {})
        name = template_cfg.get("name")
        return name if name in BACKTEST_TEMPLATE_DEFINITIONS else None

    def _select_backtest_template(self, key: str | None, *, update_config: bool = False) -> str | None:
        try:
            combo = getattr(self, "backtest_template_combo", None)
            if combo is None or combo.count() == 0:
                return None
            target = key if key in BACKTEST_TEMPLATE_DEFINITIONS else None
            if target is None and BACKTEST_TEMPLATE_DEFINITIONS:
                target = next(iter(BACKTEST_TEMPLATE_DEFINITIONS))
            selected = target
            with QtCore.QSignalBlocker(combo):
                idx = combo.findData(target)
                if idx < 0:
                    idx = 0 if combo.count() else -1
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                    selected = combo.itemData(idx)
        except Exception:
            selected = target
        if update_config and selected:
            template_cfg = self.backtest_config.setdefault("template", copy.deepcopy(BACKTEST_TEMPLATE_DEFAULT))
            template_cfg["name"] = selected
            self.config.setdefault("backtest", {})["template"] = copy.deepcopy(template_cfg)
        return selected

    def _on_backtest_template_enabled(self, checked: bool):
        try:
            template_cfg = self.backtest_config.setdefault("template", copy.deepcopy(BACKTEST_TEMPLATE_DEFAULT))
            template_cfg["enabled"] = bool(checked)
            selected = self._get_selected_template_key()
            if checked:
                selected = self._select_backtest_template(template_cfg.get("name") or selected, update_config=False)
                if selected:
                    template_cfg["name"] = selected
            self.config.setdefault("backtest", {})["template"] = copy.deepcopy(template_cfg)
            combo = getattr(self, "backtest_template_combo", None)
            if combo is not None:
                combo.setEnabled(bool(checked) and combo.count() > 0)
            if checked:
                self._apply_backtest_template(template_cfg.get("name"))
            else:
                self._backtest_pending_symbol_selection = None
        except Exception:
            pass

    def _on_backtest_template_selected(self, _index: int = -1):
        try:
            key = self._get_selected_template_key()
            if not key:
                return
            template_cfg = self.backtest_config.setdefault("template", copy.deepcopy(BACKTEST_TEMPLATE_DEFAULT))
            template_cfg["name"] = key
            self.config.setdefault("backtest", {})["template"] = copy.deepcopy(template_cfg)
            if template_cfg.get("enabled"):
                self._apply_backtest_template(key)
        except Exception:
            pass

    def _apply_backtest_template(self, template_key: str | None) -> None:
        if not template_key or template_key not in BACKTEST_TEMPLATE_DEFINITIONS:
            return
        template = BACKTEST_TEMPLATE_DEFINITIONS.get(template_key)
        if not isinstance(template, dict):
            return
        try:
            template_cfg = self.backtest_config.setdefault("template", copy.deepcopy(BACKTEST_TEMPLATE_DEFAULT))
            template_cfg["name"] = template_key
            self.config.setdefault("backtest", {})["template"] = copy.deepcopy(template_cfg)
            symbol_selection_rule = template.get("symbol_selection")
            if isinstance(symbol_selection_rule, dict):
                source_changed = False
                desired_source = symbol_selection_rule.get("source")
                if desired_source:
                    idx_source = self.backtest_symbol_source_combo.findText(
                        desired_source,
                        QtCore.Qt.MatchFlag.MatchFixedString,
                    )
                    if idx_source < 0:
                        idx_source = self.backtest_symbol_source_combo.findText(desired_source)
                    if idx_source >= 0 and self.backtest_symbol_source_combo.currentIndex() != idx_source:
                        self.backtest_symbol_source_combo.setCurrentIndex(idx_source)
                        source_changed = True
                self._backtest_pending_symbol_selection = dict(symbol_selection_rule)
                applied = False
                if not source_changed:
                    applied = self._apply_backtest_symbol_selection_rule(symbol_selection_rule)
                if applied:
                    self._backtest_pending_symbol_selection = None
                else:
                    worker = getattr(self, "_backtest_symbol_worker", None)
                    needs_refresh = not source_changed
                    try:
                        if worker is not None and worker.isRunning():
                            needs_refresh = False
                    except Exception:
                        pass
                    if needs_refresh:
                        try:
                            self._refresh_backtest_symbols()
                        except Exception:
                            pass
            else:
                self._backtest_pending_symbol_selection = None
            intervals = template.get("intervals")
            if intervals:
                existing = {self.backtest_interval_list.item(i).text() for i in range(self.backtest_interval_list.count())}
                missing = [iv for iv in intervals if iv not in existing]
                if missing:
                    with QtCore.QSignalBlocker(self.backtest_interval_list):
                        for iv in missing:
                            self.backtest_interval_list.addItem(QtWidgets.QListWidgetItem(iv))
                self._set_backtest_interval_selection(intervals)
            logic_value = str(template.get("logic") or "").upper()
            if logic_value:
                with QtCore.QSignalBlocker(self.backtest_logic_combo):
                    idx_logic = self.backtest_logic_combo.findText(logic_value, QtCore.Qt.MatchFlag.MatchFixedString)
                    if idx_logic < 0:
                        idx_logic = self.backtest_logic_combo.findText(logic_value)
                    if idx_logic >= 0:
                        self.backtest_logic_combo.setCurrentIndex(idx_logic)
                self._update_backtest_config("logic", logic_value)
            pct_value = float(template.get("position_pct", self.backtest_config.get("position_pct", 2.0)))
            with QtCore.QSignalBlocker(self.backtest_pospct_spin):
                self.backtest_pospct_spin.setValue(pct_value)
            self._update_backtest_config("position_pct", float(pct_value))
            side_value = str(template.get("side") or "BOTH").upper()
            side_label = SIDE_LABELS.get(side_value, side_value.title())
            with QtCore.QSignalBlocker(self.backtest_side_combo):
                idx_side = self.backtest_side_combo.findText(side_label, QtCore.Qt.MatchFlag.MatchFixedString)
                if idx_side < 0:
                    idx_side = self.backtest_side_combo.findText(side_label)
                if idx_side >= 0:
                    self.backtest_side_combo.setCurrentIndex(idx_side)
            self._update_backtest_config("side", side_label)
            stop_loss_template = template.get("stop_loss")
            if isinstance(stop_loss_template, dict):
                updates = {
                    "enabled": bool(stop_loss_template.get("enabled", True)),
                    "mode": stop_loss_template.get("mode", "percent"),
                    "percent": float(stop_loss_template.get("percent", 0.0) or 0.0),
                    "usdt": float(stop_loss_template.get("usdt", 0.0) or 0.0),
                    "scope": stop_loss_template.get("scope", "per_trade"),
                }
                self._backtest_stop_loss_update(**updates)
                self._update_backtest_stop_loss_widgets()
            date_range = template.get("date_range")
            if isinstance(date_range, dict):
                now_dt = QtCore.QDateTime.currentDateTime()
                start_dt = QtCore.QDateTime(now_dt)
                months = int(date_range.get("months", 0) or 0)
                days = int(date_range.get("days", 0) or 0)
                if months:
                    start_dt = start_dt.addMonths(-months)
                if days:
                    start_dt = start_dt.addDays(-days)
                with QtCore.QSignalBlocker(self.backtest_end_edit):
                    self.backtest_end_edit.setDateTime(now_dt)
                with QtCore.QSignalBlocker(self.backtest_start_edit):
                    self.backtest_start_edit.setDateTime(start_dt)
                self._backtest_dates_changed()
            indicators_template = template.get("indicators", {})
            if isinstance(indicators_template, dict):
                indicators_cfg = self.backtest_config.setdefault("indicators", {})
                cfg_parent = self.config.setdefault("backtest", {}).setdefault("indicators", {})
                for key, (cb, _btn) in self.backtest_indicator_widgets.items():
                    params = indicators_cfg.setdefault(key, {})
                    target_params = indicators_template.get(key)
                    enabled = bool(target_params)
                    params["enabled"] = enabled
                    if enabled and isinstance(target_params, dict):
                        params.update({k: v for k, v in target_params.items() if k != "enabled"})
                    cb.blockSignals(True)
                    cb.setChecked(enabled)
                    cb.blockSignals(False)
                    cfg_parent[key] = copy.deepcopy(params)
                for key, target_params in indicators_template.items():
                    if key in self.backtest_indicator_widgets:
                        continue
                    if not isinstance(target_params, dict):
                        continue
                    params = indicators_cfg.setdefault(key, {})
                    params.update({k: v for k, v in target_params.items() if k != "enabled"})
                    params["enabled"] = bool(target_params.get("enabled", True))
                    cfg_parent[key] = copy.deepcopy(params)
            margin_mode = str(template.get("margin_mode") or "")
            if margin_mode:
                with QtCore.QSignalBlocker(self.backtest_margin_mode_combo):
                    idx_margin = self.backtest_margin_mode_combo.findText(margin_mode, QtCore.Qt.MatchFlag.MatchFixedString)
                    if idx_margin < 0:
                        idx_margin = self.backtest_margin_mode_combo.findText(margin_mode)
                    if idx_margin >= 0:
                        self.backtest_margin_mode_combo.setCurrentIndex(idx_margin)
                self._update_backtest_config("margin_mode", margin_mode)
            position_mode = str(template.get("position_mode") or "")
            if position_mode:
                with QtCore.QSignalBlocker(self.backtest_position_mode_combo):
                    idx_position = self.backtest_position_mode_combo.findText(position_mode, QtCore.Qt.MatchFlag.MatchFixedString)
                    if idx_position < 0:
                        idx_position = self.backtest_position_mode_combo.findText(position_mode)
                    if idx_position >= 0:
                        self.backtest_position_mode_combo.setCurrentIndex(idx_position)
                self._update_backtest_config("position_mode", position_mode)
            assets_mode = str(template.get("assets_mode") or "")
            if assets_mode:
                normalized_assets = self._normalize_assets_mode(assets_mode)
                with QtCore.QSignalBlocker(self.backtest_assets_mode_combo):
                    idx_assets = self.backtest_assets_mode_combo.findData(normalized_assets)
                    if idx_assets < 0:
                        idx_assets = 0
                    self.backtest_assets_mode_combo.setCurrentIndex(idx_assets)
                self._update_backtest_config("assets_mode", normalized_assets)
            account_mode = str(template.get("account_mode") or "")
            if account_mode:
                normalized_account = self._normalize_account_mode(account_mode)
                with QtCore.QSignalBlocker(self.backtest_account_mode_combo):
                    idx_account = self.backtest_account_mode_combo.findData(normalized_account)
                    if idx_account < 0:
                        idx_account = 0
                    self.backtest_account_mode_combo.setCurrentIndex(idx_account)
                self._update_backtest_config("account_mode", normalized_account)
            leverage_value = int(template.get("leverage", self.backtest_config.get("leverage", 5) or 1))
            with QtCore.QSignalBlocker(self.backtest_leverage_spin):
                self.backtest_leverage_spin.setValue(leverage_value)
            self._update_backtest_config("leverage", leverage_value)
            connector_backend = template.get("connector_backend")
            if connector_backend:
                normalized_connector = _normalize_connector_backend(connector_backend)
                combo = getattr(self, "backtest_connector_combo", None)
                if combo is not None:
                    idx_conn = combo.findData(normalized_connector)
                    if idx_conn < 0:
                        idx_conn = combo.findText(normalized_connector, QtCore.Qt.MatchFlag.MatchFixedString)
                    if idx_conn < 0:
                        idx_conn = combo.findText(normalized_connector)
                    if idx_conn >= 0:
                        with QtCore.QSignalBlocker(combo):
                            combo.setCurrentIndex(idx_conn)
                self.backtest_config["connector_backend"] = normalized_connector
                self.config.setdefault("backtest", {})["connector_backend"] = normalized_connector
            template_mdd = template.get("mdd_logic")
            if template_mdd:
                self._set_backtest_mdd_selection(template_mdd, update_config=True)
            loop_override_value = template.get("loop_interval_override")
            if loop_override_value is not None:
                normalized_loop = self._normalize_loop_override(loop_override_value)
                if hasattr(self, "backtest_loop_combo"):
                    self._set_loop_combo_value(self.backtest_loop_combo, normalized_loop)
                self._update_backtest_config("loop_interval_override", normalized_loop or "")
        except Exception:
            pass

    def _update_backtest_config(self, key, value):
        try:
            if key == "side":
                value = self._canonical_side_from_text(value)
            if key == "assets_mode":
                value = self._normalize_assets_mode(value)
            if key == "account_mode":
                value = self._normalize_account_mode(value)
            self.backtest_config[key] = value
            cfg = self.config.setdefault("backtest", {})
            cfg[key] = value
        except Exception:
            pass

    def _backtest_toggle_indicator(self, key: str, checked: bool):
        try:
            indicators = self.backtest_config.setdefault("indicators", {})
            params = indicators.setdefault(key, {})
            params["enabled"] = bool(checked)
            cfg = self.config.setdefault("backtest", {}).setdefault("indicators", {})
            cfg[key] = copy.deepcopy(params)
        except Exception:
            pass

    def _open_backtest_params(self, key: str):
        try:
            params = self.backtest_config.setdefault("indicators", {}).setdefault(key, {})
            dlg = ParamDialog(key, params, self, display_name=INDICATOR_DISPLAY_NAMES.get(key, key))
            if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
                updates = dlg.get_params()
                params.update(updates)
                cfg = self.config.setdefault("backtest", {}).setdefault("indicators", {})
                cfg[key] = copy.deepcopy(params)
        except Exception:
            pass

    def _run_backtest(self):
        def dbg(msg: str) -> None:
            if not _DBG_BACKTEST_RUN:
                return
            try:
                self.log(f"[Backtest] {msg}")
            except Exception:
                print(f"[Backtest] {msg}", flush=True)

        try:
            scan_worker = getattr(self, "backtest_scan_worker", None)
            if scan_worker is not None and scan_worker.isRunning():
                self.backtest_status_label.setText("Scan in progress; stop it before starting a backtest.")
                dbg("Scan worker running; aborting backtest request.")
                return
            if self.backtest_worker and self.backtest_worker.isRunning():
                self.backtest_status_label.setText("Backtest already running...")
                dbg("Existing worker already running; aborting request.")
                return

            dbg("Preparing parameter overrides.")
            self._backtest_expected_runs = []

            ctx_backtest = self._override_ctx("backtest")
            pair_table = ctx_backtest.get("table") if ctx_backtest else None
            pair_overrides_from_ui: list[dict] = []
            if pair_table is not None:
                try:
                    rows = sorted({idx.row() for idx in pair_table.selectionModel().selectedRows()})
                except Exception:
                    rows = []
                if rows:
                    dbg(f"Processing {len(rows)} selected override rows.")
                    for row in rows:
                        try:
                            sym_item = pair_table.item(row, 0)
                            entry_data = sym_item.data(QtCore.Qt.ItemDataRole.UserRole)
                            if isinstance(entry_data, dict):
                                pair_overrides_from_ui.append(entry_data)
                        except Exception:
                            continue
                else:
                    dbg("No rows selected in override table; using all entries from config.")
                    all_pairs_from_config = self.config.get("backtest_symbol_interval_pairs", []) or []
                    for entry in all_pairs_from_config:
                        if isinstance(entry, dict):
                            pair_overrides_from_ui.append(entry)
            else:
                dbg("No override table found.")

            pairs_override_for_request: list[dict] | None = None
            if pair_overrides_from_ui:
                pairs_override_for_request = []
                seen_keys = set()
                for entry in pair_overrides_from_ui:
                    sym = str(entry.get("symbol") or "").strip().upper()
                    iv = str(entry.get("interval") or "").strip()
                    if not (sym and iv):
                        continue
                    # Use a simple key for now; engine will handle indicator permutations
                    key = (sym, iv)
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    pairs_override_for_request.append(entry)
                dbg(f"Prepared {len(pairs_override_for_request)} unique overrides for the backtest request.")

            symbols = [s for s in (self.backtest_config.get("symbols") or []) if s]
            intervals = [iv for iv in (self.backtest_config.get("intervals") or []) if iv]
            if pairs_override_for_request:
                symbol_order: list[str] = []
                interval_order: list[str] = []
                for entry in pairs_override_for_request:
                    sym = str(entry.get("symbol") or "")
                    iv = str(entry.get("interval") or "")
                    if sym not in symbol_order:
                        symbol_order.append(sym)
                    if iv not in interval_order:
                        interval_order.append(iv)
                if not symbol_order or not interval_order:
                    self.backtest_status_label.setText("Symbol/Interval overrides list is empty.")
                    dbg("Overrides empty after filtering.")
                    return
                symbols = symbol_order
                intervals = interval_order
            if not symbols:
                self.backtest_status_label.setText("Select at least one symbol.")
                dbg("Missing symbols.")
                return
            if not intervals:
                self.backtest_status_label.setText("Select at least one interval.")
                dbg("Missing intervals.")
                return

            dbg(f"Symbols={symbols}, intervals={intervals}")

            self.backtest_config["symbols"] = list(symbols)
            self.backtest_config["intervals"] = list(intervals)
            cfg_bt = self.config.setdefault("backtest", {})
            cfg_bt["symbols"] = list(symbols)
            cfg_bt["intervals"] = list(intervals)

            indicators_cfg = self.backtest_config.get("indicators", {}) or {}
            indicators: list[IndicatorDefinition] = []
            for key, params in indicators_cfg.items():
                if not params or not params.get("enabled"):
                    continue
                clean_params = copy.deepcopy(params)
                clean_params.pop("enabled", None)
                indicators.append(IndicatorDefinition(key=key, params=clean_params))
            if not indicators:
                self.backtest_status_label.setText("Enable at least one indicator to backtest.")
                dbg("No indicators enabled.")
                return

            start_qdt = self.backtest_start_edit.dateTime()
            end_qdt = self.backtest_end_edit.dateTime()
            if start_qdt > end_qdt:
                self.backtest_status_label.setText("Start date/time must be before end date/time.")
                dbg("Invalid date range (start > end).")
                return

            start_dt = start_qdt.toPyDateTime()
            end_dt = end_qdt.toPyDateTime()
            if start_dt >= end_dt:
                self.backtest_status_label.setText("Backtest range must span a positive duration.")
                dbg("Invalid date range (duration <= 0).")
                return

            capital = float(self.backtest_capital_spin.value())
            if capital <= 0.0:
                self.backtest_status_label.setText("Margin capital must be positive.")
                dbg("Capital <= 0.")
                return

            position_pct = float(self.backtest_pospct_spin.value())
            position_pct_units = "percent"
            side_value = self._canonical_side_from_text(self.backtest_side_combo.currentText())
            margin_mode = (self.backtest_margin_mode_combo.currentText() or "Isolated").strip()
            position_mode = (self.backtest_position_mode_combo.currentText() or "Hedge").strip()
            assets_mode = self._normalize_assets_mode(
                self.backtest_assets_mode_combo.currentData() or self.backtest_assets_mode_combo.currentText()
            )
            account_mode = self._normalize_account_mode(
                self.backtest_account_mode_combo.currentData() or self.backtest_account_mode_combo.currentText()
            )
            leverage_value = int(self.backtest_leverage_spin.value() or 1)

            logic = (self.backtest_logic_combo.currentText() or "AND").upper()
            self._update_backtest_config("logic", logic)
            self._update_backtest_config("capital", capital)
            self._update_backtest_config("position_pct", position_pct)
            self._update_backtest_config("position_pct_units", position_pct_units)
            self._update_backtest_config("side", side_value)
            self._update_backtest_config("margin_mode", margin_mode)
            self._update_backtest_config("position_mode", position_mode)
            self._update_backtest_config("assets_mode", assets_mode)
            self._update_backtest_config("account_mode", account_mode)
            self._update_backtest_config("leverage", leverage_value)
            dbg(f"Logic={logic}, capital={capital}, pos%={position_pct}, side={side_value}, loop={self.backtest_config.get('loop_interval_override')}")

            indicator_keys_order = [ind.key for ind in indicators]
            combos_sequence = [(entry['symbol'], entry['interval']) for entry in pairs_override_for_request] if pairs_override_for_request else [(sym, iv) for sym in symbols for iv in intervals]
            expected_runs = []
            if logic == "SEPARATE":
                for sym, iv in combos_sequence:
                    for ind in indicators:
                        expected_runs.append((sym, iv, [ind.key]))
            else:
                expected_indicator_list = list(indicator_keys_order)
                for sym, iv in combos_sequence:
                    expected_runs.append((sym, iv, list(expected_indicator_list)))
            self._backtest_expected_runs = expected_runs
            self._backtest_dates_changed()
            dbg(f"Prepared {len(expected_runs)} expected run entries.")

            symbol_source = (self.backtest_symbol_source_combo.currentText() or "Futures").strip()
            self._update_backtest_config("symbol_source", symbol_source)
            account_type = "Spot" if symbol_source.lower().startswith("spot") else "Futures"

            api_key = self.api_key_edit.text().strip()
            api_secret = self.api_secret_edit.text().strip()
            mode = self.mode_combo.currentText()

            stop_cfg = normalize_stop_loss_dict(self.backtest_config.get("stop_loss"))
            self.backtest_config["stop_loss"] = stop_cfg
            self.config.setdefault("backtest", {})["stop_loss"] = copy.deepcopy(stop_cfg)

            mdd_logic_value = self._get_selected_mdd_logic()

            request = BacktestRequest(
                symbols=symbols,
                intervals=intervals,
                indicators=indicators,
                logic=logic,
                symbol_source=symbol_source,
                start=start_dt,
                end=end_dt,
                capital=capital,
                side=side_value,
                position_pct=position_pct,
                position_pct_units=position_pct_units,
                leverage=leverage_value,
                margin_mode=margin_mode,
                position_mode=position_mode,
                assets_mode=assets_mode,
                account_mode=account_mode,
                mdd_logic=mdd_logic_value,
                stop_loss_enabled=bool(stop_cfg.get("enabled")),
                stop_loss_mode=str(stop_cfg.get("mode") or "usdt"),
                stop_loss_usdt=float(stop_cfg.get("usdt", 0.0) or 0.0),
                stop_loss_percent=float(stop_cfg.get("percent", 0.0) or 0.0),
                stop_loss_scope=str(stop_cfg.get("scope") or "per_trade"),
                pair_overrides=pairs_override_for_request,
            )
            dbg(f"BacktestRequest prepared: symbols={len(symbols)}, intervals={len(intervals)}, indicators={len(indicators)}")

            signature = (mode, api_key, api_secret)
            wrapper_entry = self._backtest_wrappers.get(account_type)
            wrapper = None
            if isinstance(wrapper_entry, dict) and wrapper_entry.get("signature") == signature:
                wrapper = wrapper_entry.get("wrapper")
                dbg("Reusing cached Binance wrapper.")
            if wrapper is None:
                try:
                    wrapper = self._create_binance_wrapper(
                        api_key=api_key,
                        api_secret=api_secret,
                        mode=mode,
                        account_type=account_type,
                        connector_backend=self._backtest_connector_backend(),
                    )
                    self._backtest_wrappers[account_type] = {"signature": signature, "wrapper": wrapper}
                    dbg("Created new Binance wrapper instance.")
                except Exception as exc:
                    msg = f"Unable to initialize Binance wrapper: {exc}"
                    self.backtest_status_label.setText(msg)
                    self.log(msg)
                    return
            else:
                try:
                    wrapper.account_type = account_type
                except Exception:
                    pass

            try:
                wrapper.indicator_source = self.ind_source_combo.currentText()
            except Exception:
                pass

            engine = BacktestEngine(wrapper)
            self.backtest_worker = _BacktestWorker(engine, request, self)
            self.backtest_worker.progress.connect(self._on_backtest_progress)
            self.backtest_worker.finished.connect(self._on_backtest_finished)
            self.backtest_results_table.setRowCount(0)
            self.backtest_status_label.setText("Running backtest...")
            self.backtest_run_btn.setEnabled(False)
            try:
                self.backtest_stop_btn.setEnabled(True)
            except Exception:
                pass
            try:
                self.backtest_stop_btn.setEnabled(True)
            except Exception:
                pass
            dbg("Dispatching worker thread.")
            self.backtest_worker.start()
        except Exception as exc:
            tb = traceback.format_exc()
            try:
                self.backtest_status_label.setText(f"Backtest failed: {exc}")
                self.log(f"[Backtest] error: {exc}\n{tb}")
            except Exception:
                print(tb, flush=True)

    def _run_backtest_scan(self):
        try:
            if self.backtest_worker and self.backtest_worker.isRunning():
                self.backtest_status_label.setText("Backtest running; stop it before scanning.")
                return
            scan_worker = getattr(self, "backtest_scan_worker", None)
            if scan_worker is not None and scan_worker.isRunning():
                self.backtest_status_label.setText("Scan already running...")
                return

            symbols_all = list(self.backtest_symbols_all or [])
            if not symbols_all:
                self.backtest_status_label.setText("No symbols loaded. Click Refresh Symbols first.")
                return
            try:
                top_n = int(self.backtest_scan_top_spin.value())
            except Exception:
                top_n = int(self.backtest_config.get("scan_top_n", _SYMBOL_FETCH_TOP_N) or _SYMBOL_FETCH_TOP_N)
            if top_n <= 0:
                self.backtest_status_label.setText("Scan Top N must be at least 1.")
                return
            if len(symbols_all) < top_n:
                self.backtest_status_label.setText(
                    f"Only {len(symbols_all)} symbols loaded; lower Scan Top N or refresh."
                )
                return
            symbols = symbols_all[:top_n]

            intervals = [iv for iv in (self.backtest_config.get("intervals") or []) if iv]
            if not intervals:
                self.backtest_status_label.setText("Select at least one interval to scan.")
                return

            indicators_cfg = self.backtest_config.get("indicators", {}) or {}
            indicators: list[IndicatorDefinition] = []
            for key, params in indicators_cfg.items():
                if not params or not params.get("enabled"):
                    continue
                clean_params = copy.deepcopy(params)
                clean_params.pop("enabled", None)
                indicators.append(IndicatorDefinition(key=key, params=clean_params))
            if not indicators:
                self.backtest_status_label.setText("Enable at least one indicator to scan.")
                return

            start_qdt = self.backtest_start_edit.dateTime()
            end_qdt = self.backtest_end_edit.dateTime()
            if start_qdt > end_qdt:
                self.backtest_status_label.setText("Start date/time must be before end date/time.")
                return
            start_dt = start_qdt.toPyDateTime()
            end_dt = end_qdt.toPyDateTime()
            if start_dt >= end_dt:
                self.backtest_status_label.setText("Backtest range must span a positive duration.")
                return

            capital = float(self.backtest_capital_spin.value())
            if capital <= 0.0:
                self.backtest_status_label.setText("Margin capital must be positive.")
                return

            position_pct = float(self.backtest_pospct_spin.value())
            position_pct_units = "percent"
            side_value = self._canonical_side_from_text(self.backtest_side_combo.currentText())
            margin_mode = (self.backtest_margin_mode_combo.currentText() or "Isolated").strip()
            position_mode = (self.backtest_position_mode_combo.currentText() or "Hedge").strip()
            assets_mode = self._normalize_assets_mode(
                self.backtest_assets_mode_combo.currentData() or self.backtest_assets_mode_combo.currentText()
            )
            account_mode = self._normalize_account_mode(
                self.backtest_account_mode_combo.currentData() or self.backtest_account_mode_combo.currentText()
            )
            leverage_value = int(self.backtest_leverage_spin.value() or 1)

            logic = (self.backtest_logic_combo.currentText() or "AND").upper()
            self._update_backtest_config("logic", logic)
            self._update_backtest_config("capital", capital)
            self._update_backtest_config("position_pct", position_pct)
            self._update_backtest_config("position_pct_units", position_pct_units)
            self._update_backtest_config("side", side_value)
            self._update_backtest_config("margin_mode", margin_mode)
            self._update_backtest_config("position_mode", position_mode)
            self._update_backtest_config("assets_mode", assets_mode)
            self._update_backtest_config("account_mode", account_mode)
            self._update_backtest_config("leverage", leverage_value)

            indicator_keys_order = [ind.key for ind in indicators]
            expected_runs = []
            if logic == "SEPARATE":
                for sym in symbols:
                    for iv in intervals:
                        for ind in indicators:
                            expected_runs.append((sym, iv, [ind.key]))
            else:
                for sym in symbols:
                    for iv in intervals:
                        expected_runs.append((sym, iv, list(indicator_keys_order)))
            self._backtest_expected_runs = expected_runs
            self._backtest_dates_changed()

            symbol_source = (self.backtest_symbol_source_combo.currentText() or "Futures").strip()
            self._update_backtest_config("symbol_source", symbol_source)
            account_type = "Spot" if symbol_source.lower().startswith("spot") else "Futures"

            api_key = self.api_key_edit.text().strip()
            api_secret = self.api_secret_edit.text().strip()
            mode = self.mode_combo.currentText()

            stop_cfg = normalize_stop_loss_dict(self.backtest_config.get("stop_loss"))
            self.backtest_config["stop_loss"] = stop_cfg
            self.config.setdefault("backtest", {})["stop_loss"] = copy.deepcopy(stop_cfg)

            mdd_logic_value = self._get_selected_mdd_logic()
            request = BacktestRequest(
                symbols=symbols,
                intervals=intervals,
                indicators=indicators,
                logic=logic,
                symbol_source=symbol_source,
                start=start_dt,
                end=end_dt,
                capital=capital,
                side=side_value,
                position_pct=position_pct,
                position_pct_units=position_pct_units,
                leverage=leverage_value,
                margin_mode=margin_mode,
                position_mode=position_mode,
                assets_mode=assets_mode,
                account_mode=account_mode,
                mdd_logic=mdd_logic_value,
                stop_loss_enabled=bool(stop_cfg.get("enabled")),
                stop_loss_mode=str(stop_cfg.get("mode") or "usdt"),
                stop_loss_usdt=float(stop_cfg.get("usdt", 0.0) or 0.0),
                stop_loss_percent=float(stop_cfg.get("percent", 0.0) or 0.0),
                stop_loss_scope=str(stop_cfg.get("scope") or "per_trade"),
            )

            signature = (mode, api_key, api_secret)
            wrapper_entry = self._backtest_wrappers.get(account_type)
            wrapper = None
            if isinstance(wrapper_entry, dict) and wrapper_entry.get("signature") == signature:
                wrapper = wrapper_entry.get("wrapper")
            if wrapper is None:
                wrapper = self._create_binance_wrapper(
                    api_key=api_key,
                    api_secret=api_secret,
                    mode=mode,
                    account_type=account_type,
                    connector_backend=self._backtest_connector_backend(),
                )
                self._backtest_wrappers[account_type] = {"signature": signature, "wrapper": wrapper}
            else:
                try:
                    wrapper.account_type = account_type
                except Exception:
                    pass

            try:
                wrapper.indicator_source = self.ind_source_combo.currentText()
            except Exception:
                pass

            engine = BacktestEngine(wrapper)
            self.backtest_scan_worker = _BacktestWorker(engine, request, self)
            self.backtest_scan_worker.progress.connect(self._on_backtest_progress)
            self.backtest_scan_worker.finished.connect(self._on_backtest_scan_finished)
            self.backtest_results_table.setRowCount(0)
            self.backtest_status_label.setText(f"Scanning top {len(symbols)} symbols...")
            self.backtest_run_btn.setEnabled(False)
            try:
                self.backtest_scan_btn.setEnabled(False)
            except Exception:
                pass
            try:
                self.backtest_stop_btn.setEnabled(True)
            except Exception:
                pass
            try:
                self._backtest_scan_mdd_limit = float(self.backtest_scan_mdd_spin.value())
            except Exception:
                self._backtest_scan_mdd_limit = float(self.backtest_config.get("scan_mdd_limit", 10.0) or 10.0)
            self.backtest_scan_worker.start()
        except Exception as exc:
            tb = traceback.format_exc()
            try:
                self.backtest_status_label.setText(f"Scan failed: {exc}")
                self.log(f"[Backtest Scan] error: {exc}\n{tb}")
            except Exception:
                print(tb, flush=True)

    def _select_backtest_scan_best(self, runs, mdd_limit: float):
        best = None
        best_score = None
        for run in runs or []:
            if is_dataclass(run):
                data = asdict(run)
            elif isinstance(run, dict):
                data = dict(run)
            else:
                data = {
                    "symbol": getattr(run, "symbol", ""),
                    "interval": getattr(run, "interval", ""),
                    "indicator_keys": getattr(run, "indicator_keys", []),
                    "trades": getattr(run, "trades", 0),
                    "roi_percent": getattr(run, "roi_percent", 0.0),
                    "roi_value": getattr(run, "roi_value", 0.0),
                    "max_drawdown_percent": getattr(run, "max_drawdown_percent", 0.0),
                    "mdd_logic": getattr(run, "mdd_logic", None),
                }
            try:
                trades = int(data.get("trades", 0) or 0)
            except Exception:
                trades = 0
            if trades <= 0:
                continue
            try:
                mdd = float(data.get("max_drawdown_percent", 0.0) or 0.0)
            except Exception:
                mdd = 0.0
            if mdd > mdd_limit:
                continue
            try:
                roi_pct = float(data.get("roi_percent", 0.0) or 0.0)
            except Exception:
                roi_pct = 0.0
            try:
                roi_val = float(data.get("roi_value", 0.0) or 0.0)
            except Exception:
                roi_val = 0.0
            symbol = str(data.get("symbol") or "").strip().upper()
            interval = str(data.get("interval") or "").strip()
            if not symbol or not interval:
                continue
            score = (roi_pct, roi_val, -mdd)
            if best_score is None or score > best_score:
                best_score = score
                best = {
                    "symbol": symbol,
                    "interval": interval,
                    "roi_percent": roi_pct,
                    "roi_value": roi_val,
                    "max_drawdown_percent": mdd,
                    "trades": trades,
                    "indicator_keys": list(data.get("indicator_keys") or []),
                    "mdd_logic": data.get("mdd_logic"),
                }
        return best

    def _select_backtest_scan_row(self, symbol: str, interval: str, indicator_keys: list | None = None) -> None:
        try:
            symbol = str(symbol or "").upper()
            interval = str(interval or "")
            if not symbol or not interval:
                return
            for row in range(self.backtest_results_table.rowCount()):
                item = self.backtest_results_table.item(row, 0)
                if item is None:
                    continue
                data = item.data(QtCore.Qt.ItemDataRole.UserRole) or {}
                sym_val = str(data.get("symbol") or "").upper()
                iv_val = str(data.get("interval") or "")
                if sym_val != symbol or iv_val != interval:
                    continue
                if indicator_keys:
                    row_keys = data.get("indicator_keys") or []
                    if set(row_keys) != set(indicator_keys):
                        continue
                self.backtest_results_table.selectRow(row)
                try:
                    self.backtest_results_table.scrollToItem(item)
                except Exception:
                    pass
                break
        except Exception:
            pass

    def _apply_backtest_scan_best(self, best: dict) -> None:
        symbol = str(best.get("symbol") or "").upper()
        interval = str(best.get("interval") or "")
        if symbol:
            self._set_backtest_symbol_selection([symbol])
        if interval:
            self._set_backtest_interval_selection([interval])
        self._select_backtest_scan_row(symbol, interval, best.get("indicator_keys"))

    def _on_backtest_scan_finished(self, result: dict, error: object):
        self.backtest_scan_worker = None
        self._on_backtest_finished(result, error)
        try:
            self.backtest_scan_btn.setEnabled(True)
        except Exception:
            pass
        if error:
            return
        if not isinstance(result, dict):
            return
        runs_raw = result.get("runs", []) or []
        try:
            mdd_limit = float(getattr(self, "_backtest_scan_mdd_limit", 0.0) or 0.0)
        except Exception:
            mdd_limit = 0.0
        best = self._select_backtest_scan_best(runs_raw, mdd_limit)
        if not best:
            self.backtest_status_label.setText(
                f"Scan complete, but no runs met MDD <= {mdd_limit:.2f}% with trades."
            )
            return
        auto_apply = False
        if auto_apply:
            self._apply_backtest_scan_best(best)
        summary = (
            f"Scan best: {best['symbol']}@{best['interval']} "
            f"ROI {best['roi_percent']:+.2f}% | MDD {best['max_drawdown_percent']:.2f}% "
            f"| trades {best['trades']}"
        )
        self.backtest_status_label.setText(summary)

    def _stop_backtest(self):
        try:
            worker = getattr(self, 'backtest_worker', None)
            if worker and worker.isRunning():
                if hasattr(worker, 'request_stop'):
                    worker.request_stop()
                self.backtest_status_label.setText('Stopping backtest...')
                try:
                    self.backtest_stop_btn.setEnabled(False)
                except Exception:
                    pass
                return
            scan_worker = getattr(self, 'backtest_scan_worker', None)
            if scan_worker and scan_worker.isRunning():
                if hasattr(scan_worker, 'request_stop'):
                    scan_worker.request_stop()
                self.backtest_status_label.setText('Stopping scan...')
                try:
                    self.backtest_stop_btn.setEnabled(False)
                except Exception:
                    pass
                return
            self.backtest_status_label.setText('No backtest running.')
        except Exception:
            pass

    def _on_backtest_progress(self, msg: str):
        self.backtest_status_label.setText(str(msg))

    @staticmethod
    def _normalize_backtest_run(run):
        if is_dataclass(run):
            data = asdict(run)
        elif isinstance(run, dict):
            data = dict(run)
        else:
            indicator_keys = getattr(run, "indicator_keys", [])
            if indicator_keys is None:
                indicator_keys = []
            elif not isinstance(indicator_keys, (list, tuple)):
                indicator_keys = [indicator_keys]
            data = {
                "symbol": getattr(run, "symbol", ""),
                "interval": getattr(run, "interval", ""),
                "logic": getattr(run, "logic", ""),
                "indicator_keys": list(indicator_keys),
                "trades": getattr(run, "trades", 0),
                "roi_value": getattr(run, "roi_value", 0.0),
                "roi_percent": getattr(run, "roi_percent", 0.0),
                "max_drawdown_value": getattr(run, "max_drawdown_value", 0.0),
                "max_drawdown_percent": getattr(run, "max_drawdown_percent", 0.0),
                "max_drawdown_during_value": getattr(run, "max_drawdown_during_value", getattr(run, "max_drawdown_value", 0.0)),
                "max_drawdown_during_percent": getattr(run, "max_drawdown_during_percent", getattr(run, "max_drawdown_percent", 0.0)),
                "max_drawdown_result_value": getattr(run, "max_drawdown_result_value", 0.0),
                "max_drawdown_result_percent": getattr(run, "max_drawdown_result_percent", 0.0),
                "mdd_logic": getattr(run, "mdd_logic", None),
            }
        data.setdefault("indicator_keys", [])
        keys = data.get("indicator_keys") or []
        if not isinstance(keys, (list, tuple)):
            keys = [keys]
        data["indicator_keys"] = [str(k) for k in keys if k is not None]
        try:
            data["trades"] = int(data.get("trades", 0) or 0)
        except Exception:
            data["trades"] = 0
        for key in (
            "roi_value",
            "roi_percent",
            "max_drawdown_value",
            "max_drawdown_percent",
            "max_drawdown_during_value",
            "max_drawdown_during_percent",
            "max_drawdown_result_value",
            "max_drawdown_result_percent",
        ):
            try:
                data[key] = float(data.get(key, 0.0) or 0.0)
            except Exception:
                data[key] = 0.0
        for pct_key in ("position_pct",):
            try:
                data[pct_key] = float(data.get(pct_key, 0.0) or 0.0)
            except Exception:
                data[pct_key] = 0.0
        for lev_key in ("leverage",):
            try:
                data[lev_key] = float(data.get(lev_key, 0.0) or 0.0)
            except Exception:
                data[lev_key] = 0.0
        for bool_key in ("stop_loss_enabled",):
            data[bool_key] = bool(data.get(bool_key, False))
        for str_key in ("symbol", "interval", "logic", "stop_loss_mode", "stop_loss_scope", "margin_mode", "position_mode", "assets_mode", "account_mode"):
            val = data.get(str_key)
            data[str_key] = str(val or "").strip()
        mdd_logic_val = str(data.get("mdd_logic", "") or "").lower()
        if mdd_logic_val not in MDD_LOGIC_OPTIONS:
            mdd_logic_val = MDD_LOGIC_DEFAULT
        data["mdd_logic"] = mdd_logic_val
        data["mdd_logic_display"] = MDD_LOGIC_LABELS.get(
            mdd_logic_val,
            mdd_logic_val.replace("_", " ").title(),
        )
        loop_raw = data.get("loop_interval_override")
        if loop_raw is None:
            if isinstance(run, dict):
                loop_raw = run.get("loop_interval_override")
            else:
                loop_raw = getattr(run, "loop_interval_override", None)
        if loop_raw is None:
            strategy_controls = data.get("strategy_controls")
            if isinstance(strategy_controls, dict):
                loop_raw = strategy_controls.get("loop_interval_override")
        loop_normalized = MainWindow._normalize_loop_override(loop_raw)
        data["loop_interval_override"] = loop_normalized or ""
        start_iso, start_display = _normalize_datetime_pair(data.get("start"))
        if not start_iso and hasattr(run, "start"):
            start_iso, start_display = _normalize_datetime_pair(getattr(run, "start"))
        data["start"] = start_iso
        data["start_display"] = start_display or "-"
        end_iso, end_display = _normalize_datetime_pair(data.get("end"))
        if not end_iso and hasattr(run, "end"):
            end_iso, end_display = _normalize_datetime_pair(getattr(run, "end"))
        data["end"] = end_iso
        data["end_display"] = end_display or "-"
        pos_pct_fraction = data.get("position_pct", 0.0)
        try:
            pos_pct_fraction = float(pos_pct_fraction or 0.0)
        except Exception:
            pos_pct_fraction = 0.0
        data["position_pct"] = pos_pct_fraction
        data["position_pct_display"] = f"{max(pos_pct_fraction, 0.0) * 100.0:.2f}%"
        stop_enabled = data.get("stop_loss_enabled", False)
        stop_mode = data.get("stop_loss_mode", "")
        stop_usdt = data.get("stop_loss_usdt", 0.0)
        stop_percent = data.get("stop_loss_percent", 0.0)
        stop_scope = data.get("stop_loss_scope", "")
        try:
            stop_usdt = float(stop_usdt or 0.0)
        except Exception:
            stop_usdt = 0.0
        try:
            stop_percent = float(stop_percent or 0.0)
        except Exception:
            stop_percent = 0.0
        data["stop_loss_usdt"] = stop_usdt
        data["stop_loss_percent"] = stop_percent
        if stop_enabled:
            parts = []
            if stop_mode:
                parts.append(stop_mode)
            if stop_scope:
                parts.append(stop_scope)
            if stop_usdt > 0.0:
                parts.append(f"{stop_usdt:.2f} USDT")
            if stop_percent > 0.0:
                parts.append(f"{stop_percent:.2f}%")
            data["stop_loss_display"] = "Enabled" + (f" ({', '.join(parts)})" if parts else "")
        else:
            data["stop_loss_display"] = "Disabled"
        if not data.get("margin_mode"):
            data["margin_mode"] = ""
        if not data.get("position_mode"):
            data["position_mode"] = ""
        if not data.get("assets_mode"):
            data["assets_mode"] = ""
        if not data.get("account_mode"):
            data["account_mode"] = ""
        data["leverage_display"] = f"{data.get('leverage', 0.0):.2f}x"
        max_dd_during_pct = data.get("max_drawdown_during_percent", data.get("max_drawdown_percent", 0.0))
        try:
            max_dd_during_pct = float(max_dd_during_pct or 0.0)
        except Exception:
            max_dd_during_pct = 0.0
        max_dd_during_val = data.get("max_drawdown_during_value", data.get("max_drawdown_value", 0.0))
        try:
            max_dd_during_val = float(max_dd_during_val or 0.0)
        except Exception:
            max_dd_during_val = 0.0
        max_dd_result_pct = data.get("max_drawdown_result_percent", 0.0)
        try:
            max_dd_result_pct = float(max_dd_result_pct or 0.0)
        except Exception:
            max_dd_result_pct = 0.0
        max_dd_result_val = data.get("max_drawdown_result_value", 0.0)
        try:
            max_dd_result_val = float(max_dd_result_val or 0.0)
        except Exception:
            max_dd_result_val = 0.0
        data["max_drawdown_percent"] = max_dd_during_pct
        data["max_drawdown_value"] = max_dd_during_val
        data["max_drawdown_during_percent"] = max_dd_during_pct
        data["max_drawdown_during_value"] = max_dd_during_val
        data["max_drawdown_result_percent"] = max_dd_result_pct
        data["max_drawdown_result_value"] = max_dd_result_val
        if max_dd_during_pct > 0.0:
            data["max_drawdown_during_display"] = f"{-abs(max_dd_during_pct):.2f}%"
        else:
            data["max_drawdown_during_display"] = "0.00%"
        if max_dd_during_val > 0.0:
            data["max_drawdown_during_value_display"] = f"{-abs(max_dd_during_val):.2f} USDT"
        else:
            data["max_drawdown_during_value_display"] = "0.00 USDT"
        if max_dd_result_pct > 0.0:
            data["max_drawdown_result_display"] = f"{-abs(max_dd_result_pct):.2f}%"
        else:
            data["max_drawdown_result_display"] = "0.00%"
        if max_dd_result_val > 0.0:
            data["max_drawdown_result_value_display"] = f"{-abs(max_dd_result_val):.2f} USDT"
        else:
            data["max_drawdown_result_value_display"] = "0.00 USDT"
        data["symbol"] = str(data.get("symbol") or "")
        data["interval"] = str(data.get("interval") or "")
        data["logic"] = str(data.get("logic") or "")
        return data

    def _on_backtest_finished(self, result: dict, error: object):
        self.backtest_run_btn.setEnabled(True)
        try:
            self.backtest_stop_btn.setEnabled(False)
        except Exception:
            pass
        worker = getattr(self, "backtest_worker", None)
        if worker and worker.isRunning():
            worker.wait(100)
        self.backtest_worker = None
        if error:
            err_text = str(error) if error is not None else ''
            if isinstance(error, RuntimeError) and 'backtest_cancelled' in err_text.lower():
                self.backtest_status_label.setText('Backtest cancelled.')
                return
            msg = f"Backtest failed: {error}"
            self.backtest_status_label.setText(msg)
            self.log(msg)
            return
        runs_raw = result.get("runs", []) if isinstance(result, dict) else []
        errors = result.get("errors", []) if isinstance(result, dict) else []
        run_dicts = [self._normalize_backtest_run(r) for r in (runs_raw or [])]
        default_loop_override = MainWindow._normalize_loop_override(self.backtest_config.get("loop_interval_override"))
        for rd in run_dicts:
            if not rd.get("loop_interval_override"):
                rd["loop_interval_override"] = default_loop_override or ""
        self.backtest_results = run_dicts
        expected_runs = getattr(self, "_backtest_expected_runs", []) or []
        for idx, rd in enumerate(run_dicts):
            if idx < len(expected_runs):
                sym, iv, inds = expected_runs[idx]
                if not rd.get("symbol") and sym:
                    rd["symbol"] = sym
                if not rd.get("interval") and iv:
                    rd["interval"] = iv
                if (not rd.get("indicator_keys")) and inds:
                    rd["indicator_keys"] = list(inds)
        try:
            self.log(f"Backtest returned {len(run_dicts)} run(s).")
            for idx, rd in enumerate(run_dicts):
                self.log(f"Backtest run[{idx}]: {rd}")
        except Exception:
            pass
        self._populate_backtest_results_table(run_dicts)
        summary_parts = []
        if run_dicts:
            summary_parts.append(f"{len(run_dicts)} run(s) completed")
            total_roi = sum(r.get("roi_value", 0.0) for r in run_dicts)
            summary_parts.append(f"Total ROI: {total_roi:+.2f} USDT")
            avg_roi_pct = sum(r.get("roi_percent", 0.0) for r in run_dicts) / max(len(run_dicts), 1)
            summary_parts.append(f"Avg ROI %: {avg_roi_pct:+.2f}%")
        if errors:
            summary_parts.append(f"{len(errors)} error(s)")
            for err in errors:
                sym = err.get("symbol")
                interval = err.get("interval")
                self.log(f"Backtest error for {sym}@{interval}: {err.get('error')}")
        if not summary_parts:
            summary_parts.append("No results generated.")
        self.backtest_status_label.setText(" | ".join(summary_parts))

    def _populate_backtest_results_table(self, runs):
        try:
            rows_data = list(runs or [])
            try:
                self.backtest_results_table.setSortingEnabled(False)
            except Exception:
                pass
            try:
                self.backtest_results_table.clearContents()
            except Exception:
                pass
            self.backtest_results_table.setRowCount(len(rows_data))
            for row, run in enumerate(rows_data):
                try:
                    data = self._normalize_backtest_run(run)
                    symbol = data.get("symbol") or "-"
                    interval = data.get("interval") or "-"
                    logic = data.get("logic") or "-"
                    indicator_keys = data.get("indicator_keys") or []
                    trades = _safe_float(data.get("trades", 0.0), 0.0)
                    roi_value = _safe_float(data.get("roi_value", 0.0), 0.0)
                    roi_percent = _safe_float(data.get("roi_percent", 0.0), 0.0)
                    start_display = data.get("start_display") or "-"
                    end_display = data.get("end_display") or "-"
                    pos_pct_display = data.get("position_pct_display") or "0.00%"
                    stop_loss_display = data.get("stop_loss_display") or "Disabled"
                    margin_mode = data.get("margin_mode") or "-"
                    position_mode = data.get("position_mode") or "-"
                    assets_mode = data.get("assets_mode") or "-"
                    account_mode = data.get("account_mode") or "-"
                    leverage_display = data.get("leverage_display") or f"{data.get('leverage', 0.0):.2f}x"
                    max_drawdown_during_percent = _safe_float(data.get("max_drawdown_during_percent", data.get("max_drawdown_percent", 0.0)), 0.0)
                    max_drawdown_during_value = _safe_float(data.get("max_drawdown_during_value", data.get("max_drawdown_value", 0.0)), 0.0)
                    max_drawdown_result_percent = _safe_float(data.get("max_drawdown_result_percent", 0.0), 0.0)
                    max_drawdown_result_value = _safe_float(data.get("max_drawdown_result_value", 0.0), 0.0)

                    indicators_display = ", ".join(INDICATOR_DISPLAY_NAMES.get(k, k) for k in indicator_keys) or "-"
                    item_symbol = QtWidgets.QTableWidgetItem(symbol or "-")
                    try:
                        item_symbol.setData(QtCore.Qt.ItemDataRole.UserRole, dict(data))
                    except Exception:
                        pass
                    self.backtest_results_table.setItem(row, 0, item_symbol)
                    self.backtest_results_table.setItem(row, 1, QtWidgets.QTableWidgetItem(interval or "-"))
                    self.backtest_results_table.setItem(row, 2, QtWidgets.QTableWidgetItem(logic or "-"))
                    self.backtest_results_table.setItem(row, 3, QtWidgets.QTableWidgetItem(indicators_display))
                    trades_display = _safe_int(trades, 0)
                    trades_item = _NumericItem(str(trades_display), trades_display)
                    self.backtest_results_table.setItem(row, 4, trades_item)
                    loop_display = data.get("loop_interval_override") or "-"
                    self.backtest_results_table.setItem(row, 5, QtWidgets.QTableWidgetItem(loop_display))
                    self.backtest_results_table.setItem(row, 6, QtWidgets.QTableWidgetItem(start_display or "-"))
                    self.backtest_results_table.setItem(row, 7, QtWidgets.QTableWidgetItem(end_display or "-"))
                    self.backtest_results_table.setItem(row, 8, QtWidgets.QTableWidgetItem(pos_pct_display))
                    self.backtest_results_table.setItem(row, 9, QtWidgets.QTableWidgetItem(stop_loss_display))
                    self.backtest_results_table.setItem(row, 10, QtWidgets.QTableWidgetItem(margin_mode or "-"))
                    self.backtest_results_table.setItem(row, 11, QtWidgets.QTableWidgetItem(position_mode or "-"))
                    self.backtest_results_table.setItem(row, 12, QtWidgets.QTableWidgetItem(assets_mode or "-"))
                    self.backtest_results_table.setItem(row, 13, QtWidgets.QTableWidgetItem(account_mode or "-"))
                    self.backtest_results_table.setItem(row, 14, QtWidgets.QTableWidgetItem(leverage_display))
                    roi_value_item = _NumericItem(f"{roi_value:+.2f}", roi_value)
                    self.backtest_results_table.setItem(row, 15, roi_value_item)
                    roi_percent_item = _NumericItem(f"{roi_percent:+.2f}%", roi_percent)
                    self.backtest_results_table.setItem(row, 16, roi_percent_item)
                    if max_drawdown_during_value > 0.0:
                        dd_during_value_for_sort = -abs(max_drawdown_during_value)
                        dd_during_value_text = f"{dd_during_value_for_sort:.2f} USDT"
                    else:
                        dd_during_value_for_sort = 0.0
                        dd_during_value_text = "0.00 USDT"
                    dd_during_value_item = _NumericItem(dd_during_value_text, dd_during_value_for_sort)
                    if max_drawdown_during_percent > 0.0:
                        dd_during_value_item.setToolTip(f"Peak-to-trough drop while open: {max_drawdown_during_percent:.2f}%")
                    self.backtest_results_table.setItem(row, 17, dd_during_value_item)
                    if max_drawdown_during_percent > 0.0:
                        dd_during_for_sort = -abs(max_drawdown_during_percent)
                        dd_during_text = f"{dd_during_for_sort:.2f}%"
                    else:
                        dd_during_for_sort = 0.0
                        dd_during_text = "0.00%"
                    dd_during_item = _NumericItem(dd_during_text, dd_during_for_sort)
                    if max_drawdown_during_value > 0.0:
                        dd_during_item.setToolTip(f"Peak-to-trough drop while open: {max_drawdown_during_value:.2f} USDT")
                    self.backtest_results_table.setItem(row, 18, dd_during_item)
                    if max_drawdown_result_value > 0.0:
                        dd_result_value_for_sort = -abs(max_drawdown_result_value)
                        dd_result_value_text = f"{dd_result_value_for_sort:.2f} USDT"
                    else:
                        dd_result_value_for_sort = 0.0
                        dd_result_value_text = "0.00 USDT"
                    dd_result_value_item = _NumericItem(dd_result_value_text, dd_result_value_for_sort)
                    if max_drawdown_result_percent > 0.0:
                        dd_result_value_item.setToolTip(f"Max loss on closed position: {max_drawdown_result_percent:.2f}%")
                    self.backtest_results_table.setItem(row, 19, dd_result_value_item)
                    if max_drawdown_result_percent > 0.0:
                        dd_result_for_sort = -abs(max_drawdown_result_percent)
                        dd_result_text = f"{dd_result_for_sort:.2f}%"
                    else:
                        dd_result_for_sort = 0.0
                        dd_result_text = "0.00%"
                    dd_result_item = _NumericItem(dd_result_text, dd_result_for_sort)
                    if max_drawdown_result_value > 0.0:
                        dd_result_item.setToolTip(f"Max loss on closed position: {max_drawdown_result_value:.2f} USDT")
                    self.backtest_results_table.setItem(row, 20, dd_result_item)
                except Exception as row_exc:
                    self.log(f"Backtest table row {row} error: {row_exc}")
                    err_item = QtWidgets.QTableWidgetItem(f"Error: {row_exc}")
                    err_item.setForeground(QtGui.QBrush(QtGui.QColor("red")))
                    self.backtest_results_table.setItem(row, 0, err_item)
                    for col in range(1, self.backtest_results_table.columnCount()):
                        self.backtest_results_table.setItem(row, col, QtWidgets.QTableWidgetItem("-"))
                    continue
            self.backtest_results_table.resizeRowsToContents()
        except Exception as exc:
            self.log(f"Backtest results table error: {exc}")
        finally:
            try:
                self.backtest_results_table.setSortingEnabled(True)
            except Exception:
                pass

    def _create_chart_tab(self):
        tab = QtWidgets.QWidget()
        self.chart_tab = tab
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        controls_layout = QtWidgets.QHBoxLayout()
        layout.addLayout(controls_layout)

        controls_layout.addWidget(QtWidgets.QLabel("Market:"))
        self.chart_market_combo = QtWidgets.QComboBox()
        for opt in CHART_MARKET_OPTIONS:
            self.chart_market_combo.addItem(opt)
        controls_layout.addWidget(self.chart_market_combo)

        controls_layout.addWidget(QtWidgets.QLabel("Symbol:"))
        self.chart_symbol_combo = QtWidgets.QComboBox()
        self.chart_symbol_combo.setEditable(False)
        self.chart_symbol_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        controls_layout.addWidget(self.chart_symbol_combo)

        controls_layout.addWidget(QtWidgets.QLabel("Interval:"))
        self.chart_interval_combo = QtWidgets.QComboBox()
        self.chart_interval_combo.setEditable(False)
        self.chart_interval_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        for iv in CHART_INTERVAL_OPTIONS:
            self.chart_interval_combo.addItem(iv)
        controls_layout.addWidget(self.chart_interval_combo)

        controls_layout.addWidget(QtWidgets.QLabel("View:"))
        self.chart_view_mode_combo = QtWidgets.QComboBox()
        self.chart_view_mode_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        controls_layout.addWidget(self.chart_view_mode_combo)

        controls_layout.addStretch()
        chart_status_widget = QtWidgets.QWidget()
        chart_status_layout = QtWidgets.QHBoxLayout(chart_status_widget)
        chart_status_layout.setContentsMargins(0, 0, 0, 0)
        chart_status_layout.setSpacing(8)
        self.pnl_active_label_chart = QtWidgets.QLabel()
        self.pnl_closed_label_chart = QtWidgets.QLabel()
        self.bot_status_label_chart = QtWidgets.QLabel()
        self.bot_time_label_chart = QtWidgets.QLabel("Bot Active Time: --")
        for lbl in (self.pnl_active_label_chart, self.pnl_closed_label_chart):
            lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
            chart_status_layout.addWidget(lbl)
        chart_status_layout.addStretch()
        for lbl in (self.bot_status_label_chart, self.bot_time_label_chart):
            lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
            chart_status_layout.addWidget(lbl)
        self._register_pnl_summary_labels(self.pnl_active_label_chart, self.pnl_closed_label_chart)
        controls_layout.addWidget(chart_status_widget)

        self._chart_view_widgets = {}
        self.chart_view_stack = QtWidgets.QStackedWidget()
        layout.addWidget(self.chart_view_stack, stretch=1)
        if _native_chart_host_prewarm_enabled():
            try:
                self.chart_view_stack.setAttribute(QtCore.Qt.WidgetAttribute.WA_NativeWindow, True)
                self.chart_view_stack.winId()
            except Exception:
                pass
        try:
            self._chart_switch_overlay = QtWidgets.QLabel(self.chart_view_stack)
            self._chart_switch_overlay.setVisible(False)
            self._chart_switch_overlay.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self._chart_switch_overlay.setScaledContents(True)
            self._chart_switch_overlay.setStyleSheet(
                "background-color: #0b0e11; color: #94a3b8; font-size: 15px;"
            )
            self._chart_switch_overlay.setAttribute(
                QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
            )
            self._update_chart_overlay_geometry()
            if not self._chart_view_stack_event_filter_installed:
                self.chart_view_stack.installEventFilter(self)
                self._chart_view_stack_event_filter_installed = True
        except Exception:
            self._chart_switch_overlay = None

        self.chart_tradingview = None
        self._chart_view_tradingview_available = (
            (_TRADINGVIEW_IMPORT_ERROR is None)
            and (not _DISABLE_TRADINGVIEW)
            and (not _DISABLE_CHARTS)
            and _webengine_charts_allowed()
        )
        self.chart_binance = None
        self.chart_lightweight = None
        self._chart_view_binance_available = (
            (_BINANCE_IMPORT_ERROR is None)
            and (not _DISABLE_CHARTS)
            and _webengine_charts_allowed()
        )
        self._chart_view_lightweight_available = (
            (_LIGHTWEIGHT_IMPORT_ERROR is None)
            and (not _DISABLE_CHARTS)
            and _webengine_charts_allowed()
        )

        self.chart_original_view = None
        if QT_CHARTS_AVAILABLE and QChartView is not None:
            view = InteractiveChartView()
            try:
                view.setMinimumHeight(300)
            except Exception:
                pass
            self.chart_original_view = view
        else:
            self.chart_original_view = SimpleCandlestickWidget()
        if self.chart_original_view is not None:
            self._chart_view_widgets["legacy"] = self.chart_original_view
            self.chart_view_stack.addWidget(self.chart_original_view)

        self.chart_view_mode_combo.clear()
        tv_label = "TradingView"
        if self._chart_view_tradingview_available:
            self.chart_view_mode_combo.addItem(tv_label, "tradingview")
        else:
            self.chart_view_mode_combo.addItem(tv_label, "tradingview")
            try:
                idx = self.chart_view_mode_combo.findData("tradingview")
                if idx >= 0:
                    model = self.chart_view_mode_combo.model()
                    model.setData(model.index(idx, 0), QtCore.Qt.ItemDataRole.EnabledRole, False)
                    model.setData(
                        model.index(idx, 0),
                        _tradingview_unavailable_reason(),
                        QtCore.Qt.ItemDataRole.ToolTipRole,
                    )
            except Exception:
                pass
        self.chart_view_mode_combo.addItem("Original", "original")
        if not self._chart_view_binance_available:
            try:
                idx = self.chart_view_mode_combo.findData("original")
                if idx >= 0:
                    model = self.chart_view_mode_combo.model()
                    model.setData(model.index(idx, 0), QtCore.Qt.ItemDataRole.EnabledRole, False)
                    model.setData(
                        model.index(idx, 0),
                        _binance_unavailable_reason(),
                        QtCore.Qt.ItemDataRole.ToolTipRole,
                    )
            except Exception:
                pass
        self.chart_view_mode_combo.addItem("TradingView Lightweight", "lightweight")
        if not self._chart_view_lightweight_available:
            try:
                idx = self.chart_view_mode_combo.findData("lightweight")
                if idx >= 0:
                    model = self.chart_view_mode_combo.model()
                    model.setData(model.index(idx, 0), QtCore.Qt.ItemDataRole.EnabledRole, False)
                    model.setData(
                        model.index(idx, 0),
                        _lightweight_unavailable_reason(),
                        QtCore.Qt.ItemDataRole.ToolTipRole,
                    )
            except Exception:
                pass

        requested_mode = str(self.chart_config.get("view_mode") or "").strip().lower()
        if requested_mode not in {"tradingview", "original", "lightweight"}:
            requested_mode = "tradingview" if self._chart_view_tradingview_available else "original"
        if requested_mode == "tradingview" and not self._chart_view_tradingview_available:
            requested_mode = "original"
        if requested_mode == "lightweight" and not self._chart_view_lightweight_available:
            requested_mode = "original"
        self.chart_config["view_mode"] = requested_mode

        self._pending_tradingview_mode = False
        if self._chart_view_tradingview_available and sys.platform != "win32":
            # Preload TradingView widget so switching to the chart tab feels instant.
            # On Windows this can spawn helper windows that briefly flash during startup,
            # so we defer creation until the chart tab is shown.
            try:
                self._ensure_tradingview_widget()
            except Exception:
                pass
        # Pre-select the combo box to TradingView so the UI reflects the active view.
        try:
            idx = self.chart_view_mode_combo.findData(requested_mode)
            if idx >= 0:
                blocker = QtCore.QSignalBlocker(self.chart_view_mode_combo)
                self.chart_view_mode_combo.setCurrentIndex(idx)
                del blocker
        except Exception:
            pass

        allow_tradingview_init = sys.platform != "win32"
        self._apply_chart_view_mode(requested_mode, initial=True, allow_tradingview_init=allow_tradingview_init)
        self.chart_view_mode_combo.currentIndexChanged.connect(self._on_chart_view_mode_changed)

        self.chart_symbol_combo.currentTextChanged.connect(self._on_chart_controls_changed)
        self.chart_interval_combo.currentTextChanged.connect(self._on_chart_controls_changed)
        self.chart_market_combo.currentTextChanged.connect(self._on_chart_market_changed)

        self._restore_chart_controls_from_config()
        self._on_chart_market_changed(self.chart_market_combo.currentText())
        self._update_bot_status()
        # Preload symbol universes for both markets so selections react quickly.
        self._load_chart_symbols_async("Futures")
        self._load_chart_symbols_async("Spot")

        if not getattr(self, "_chart_theme_signal_installed", False):
            try:
                self.theme_combo.currentTextChanged.connect(self._on_chart_theme_changed)
                self._chart_theme_signal_installed = True
            except Exception:
                pass

        self._schedule_tradingview_prewarm()

        return tab

    def _ensure_tradingview_widget(self):
        """Lazily create the TradingView widget so QtWebEngine processes spawn only when needed."""
        if _chart_safe_mode_enabled():
            return None
        if self.chart_tradingview is not None:
            self._bind_tradingview_ready(self.chart_tradingview)
            return self.chart_tradingview
        if not self._chart_view_tradingview_available:
            return None
        tv_class, _ = _load_tradingview_widget()
        if tv_class is None:
            self._chart_view_tradingview_available = False
            return None
        self._start_webengine_close_guard()
        try:
            parent = getattr(self, "chart_view_stack", None) or self
            widget = tv_class(parent)
        except Exception:
            self.chart_tradingview = None
            self._chart_view_tradingview_available = False
            return None
        self.chart_tradingview = widget
        self._chart_view_widgets["tradingview"] = widget
        self.chart_view_stack.addWidget(widget)
        self._bind_tradingview_ready(widget)
        return widget

    def _bind_tradingview_ready(self, widget):
        if widget is None:
            return
        if getattr(self, "_tradingview_ready_connected", False):
            return
        try:
            if hasattr(widget, "ready"):
                widget.ready.connect(self._on_tradingview_ready)
                self._tradingview_ready_connected = True
        except Exception:
            pass

    def _ensure_binance_widget(self):
        """Lazily create the Binance web widget so QtWebEngine spawns only when needed."""
        if _chart_safe_mode_enabled():
            return None
        if self.chart_binance is not None:
            return self.chart_binance
        if not self._chart_view_binance_available:
            return None
        bw_class, available = _load_binance_widget()
        if bw_class is None or not available:
            self._chart_view_binance_available = False
            return None
        self._start_webengine_close_guard()
        try:
            parent = getattr(self, "chart_view_stack", None) or self
            widget = bw_class(parent)
        except Exception:
            self._chart_view_binance_available = False
            return None
        self.chart_binance = widget
        self._chart_view_widgets["original"] = widget
        try:
            self.chart_view_stack.addWidget(widget)
        except Exception:
            pass
        return widget

    def _ensure_lightweight_widget(self):
        """Lazily create the lightweight chart widget so QtWebEngine spawns only when needed."""
        if _chart_safe_mode_enabled():
            return None
        if self.chart_lightweight is not None:
            return self.chart_lightweight
        if not self._chart_view_lightweight_available:
            return None
        lw_class, available = _load_lightweight_widget()
        if lw_class is None or not available:
            self._chart_view_lightweight_available = False
            return None
        self._start_webengine_close_guard()
        try:
            parent = getattr(self, "chart_view_stack", None) or self
            widget = lw_class(parent)
        except Exception:
            self._chart_view_lightweight_available = False
            return None
        self.chart_lightweight = widget
        self._chart_view_widgets["lightweight"] = widget
        try:
            self.chart_view_stack.addWidget(widget)
        except Exception:
            pass
        return widget

    def _update_chart_overlay_geometry(self):
        overlay = getattr(self, "_chart_switch_overlay", None)
        stack = getattr(self, "chart_view_stack", None)
        if overlay is None or stack is None:
            return
        try:
            overlay.setGeometry(stack.rect())
        except Exception:
            pass

    def _show_chart_switch_overlay(self):
        if getattr(self, "_chart_switch_overlay_active", False):
            return
        overlay = getattr(self, "_chart_switch_overlay", None)
        stack = getattr(self, "chart_view_stack", None)
        if overlay is None or stack is None:
            return
        self._update_chart_overlay_geometry()
        pixmap = None
        try:
            source = stack.currentWidget()
            if source is not None:
                pixmap = source.grab()
        except Exception:
            pixmap = None
        try:
            if pixmap is not None and not pixmap.isNull():
                overlay.setPixmap(pixmap)
                overlay.setText("")
            else:
                overlay.setPixmap(QtGui.QPixmap())
                overlay.setText("Loading TradingView...")
            overlay.setVisible(True)
            overlay.raise_()
            self._chart_switch_overlay_active = True
        except Exception:
            pass

    def _hide_chart_switch_overlay(self, delay_ms: int = 0):
        overlay = getattr(self, "_chart_switch_overlay", None)
        if overlay is None or not getattr(self, "_chart_switch_overlay_active", False):
            return

        def _do_hide():
            try:
                overlay.setVisible(False)
                overlay.setPixmap(QtGui.QPixmap())
                overlay.setText("")
            except Exception:
                pass
            self._chart_switch_overlay_active = False

        if delay_ms and delay_ms > 0:
            QtCore.QTimer.singleShot(int(delay_ms), _do_hide)
        else:
            _do_hide()

    def _schedule_tradingview_prewarm(self):
        if getattr(self, "_tradingview_prewarm_scheduled", False) or getattr(self, "_tradingview_prewarmed", False):
            return
        if not getattr(self, "_chart_view_tradingview_available", False):
            return
        if sys.platform != "win32":
            return
        flag = str(os.environ.get("BOT_PREWARM_TRADINGVIEW", "0")).strip().lower()
        if flag in {"0", "false", "no", "off"}:
            return
        try:
            delay_ms = int(os.environ.get("BOT_PREWARM_TRADINGVIEW_DELAY_MS") or 1200)
        except Exception:
            delay_ms = 1200
        delay_ms = max(100, min(delay_ms, 10000))
        self._tradingview_prewarm_scheduled = True
        QtCore.QTimer.singleShot(delay_ms, self._prewarm_tradingview)

    def _prewarm_webengine_runtime(self):
        """Initialize QtWebEngine once while the app is booting to avoid first-tab flicker."""
        if getattr(self, "_webengine_runtime_prewarmed", False):
            return
        if sys.platform != "win32":
            return
        if not _webengine_charts_allowed():
            return
        flag = str(os.environ.get("BOT_PREWARM_WEBENGINE", "1")).strip().lower()
        if flag in {"0", "false", "no", "off"}:
            return
        if _webengine_embed_unavailable_reason():
            return
        try:
            _configure_tradingview_webengine_env()
        except Exception:
            pass
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
        except Exception:
            return
        try:
            view = QWebEngineView(self)
            view.setObjectName("botWebEnginePrewarm")
            try:
                view.setAttribute(QtCore.Qt.WidgetAttribute.WA_DontShowOnScreen, True)
            except Exception:
                pass
            try:
                view.resize(1, 1)
                view.move(-32000, -32000)
                view.hide()
            except Exception:
                pass
            try:
                view.load(QtCore.QUrl("about:blank"))
            except Exception:
                pass
            self._webengine_runtime_prewarm_view = view
            self._webengine_runtime_prewarmed = True
            try:
                self._chart_debug_log("webengine_prewarm init=1")
            except Exception:
                pass
        except Exception:
            return

        try:
            hold_ms = int(os.environ.get("BOT_PREWARM_WEBENGINE_HOLD_MS") or 2200)
        except Exception:
            hold_ms = 2200
        hold_ms = max(500, min(hold_ms, 10000))

        def _cleanup():
            view_obj = getattr(self, "_webengine_runtime_prewarm_view", None)
            self._webengine_runtime_prewarm_view = None
            if view_obj is not None:
                try:
                    view_obj.deleteLater()
                except Exception:
                    pass

        QtCore.QTimer.singleShot(hold_ms, _cleanup)

    def _prewarm_tradingview(self):
        self._tradingview_prewarm_scheduled = False
        if getattr(self, "_tradingview_prewarmed", False):
            return
        if not getattr(self, "_chart_view_tradingview_available", False):
            return
        widget = self._ensure_tradingview_widget()
        if widget is None:
            return
        self._tradingview_prewarmed = True
        self._prime_tradingview_chart(widget)

    def _start_tradingview_visibility_guard(self):
        if sys.platform != "win32":
            return
        if getattr(self, "_tv_visibility_guard_active", False):
            return
        try:
            duration_ms = int(os.environ.get("BOT_TRADINGVIEW_VISIBILITY_GUARD_MS") or 2500)
        except Exception:
            duration_ms = 2500
        duration_ms = max(500, min(duration_ms, 8000))
        try:
            interval_ms = int(os.environ.get("BOT_TRADINGVIEW_VISIBILITY_GUARD_INTERVAL_MS") or 50)
        except Exception:
            interval_ms = 50
        interval_ms = max(20, min(interval_ms, 200))

        timer = QtCore.QTimer(self)
        timer.setInterval(interval_ms)
        start_ts = time.monotonic()
        self._tv_visibility_guard_active = True
        self._tv_visibility_guard_timer = timer

        def _tick():
            if (time.monotonic() - start_ts) * 1000.0 >= duration_ms:
                self._stop_tradingview_visibility_guard()
                return
            try:
                if not self.isVisible():
                    self.showNormal()
                    self.raise_()
                    self.activateWindow()
                elif self.windowState() & QtCore.Qt.WindowState.WindowMinimized:
                    self.showNormal()
                    self.raise_()
                    self.activateWindow()
            except Exception:
                pass

        timer.timeout.connect(_tick)
        timer.start()
        _tick()

    def _start_tradingview_visibility_watchdog(self):
        if sys.platform != "win32":
            return
        if getattr(self, "_tv_visibility_watchdog_active", False):
            return
        flag = str(os.environ.get("BOT_TRADINGVIEW_VISIBILITY_WATCHDOG", "1")).strip().lower()
        if flag in {"0", "false", "no", "off"}:
            return
        try:
            interval_ms = int(os.environ.get("BOT_TRADINGVIEW_VISIBILITY_WATCHDOG_INTERVAL_MS") or 200)
        except Exception:
            interval_ms = 200
        interval_ms = max(50, min(interval_ms, 1000))
        timer = QtCore.QTimer(self)
        timer.setInterval(interval_ms)
        self._tv_visibility_watchdog_active = True
        self._tv_visibility_watchdog_timer = timer

        def _tick():
            try:
                if not self.isVisible() or self.windowState() & QtCore.Qt.WindowState.WindowMinimized:
                    self.showNormal()
                    self.raise_()
                    self.activateWindow()
            except Exception:
                pass

        timer.timeout.connect(_tick)
        timer.start()
        _tick()

    def _start_tradingview_close_guard(self):
        if sys.platform != "win32":
            return
        try:
            duration_ms = int(os.environ.get("BOT_TRADINGVIEW_CLOSE_GUARD_MS") or 2500)
        except Exception:
            duration_ms = 2500
        duration_ms = max(500, min(duration_ms, 8000))
        try:
            self._tv_close_guard_until = time.monotonic() + (duration_ms / 1000.0)
        except Exception:
            self._tv_close_guard_until = 0.0
        self._tv_close_guard_active = True

    def _start_webengine_close_guard(self):
        if sys.platform != "win32":
            return
        if not _webengine_charts_allowed():
            return
        try:
            duration_ms = int(os.environ.get("BOT_WEBENGINE_CLOSE_GUARD_MS") or 3500)
        except Exception:
            duration_ms = 3500
        duration_ms = max(800, min(duration_ms, 15000))
        try:
            until = time.monotonic() + (duration_ms / 1000.0)
        except Exception:
            until = 0.0
        try:
            prev_until = float(getattr(self, "_webengine_close_guard_until", 0.0) or 0.0)
        except Exception:
            prev_until = 0.0
        self._webengine_close_guard_until = max(prev_until, until)
        self._webengine_close_guard_active = True
        self._start_webengine_visibility_watchdog()
        try:
            self._chart_debug_log(
                f"webengine_close_guard start duration_ms={duration_ms} until={self._webengine_close_guard_until:.3f}"
            )
        except Exception:
            pass

    def _start_webengine_visibility_watchdog(self):
        if sys.platform != "win32":
            return
        if getattr(self, "_webengine_visibility_watchdog_active", False):
            return
        try:
            interval_ms = int(os.environ.get("BOT_WEBENGINE_CLOSE_GUARD_WATCHDOG_INTERVAL_MS") or 120)
        except Exception:
            interval_ms = 120
        interval_ms = max(30, min(interval_ms, 1000))
        timer = QtCore.QTimer(self)
        timer.setInterval(interval_ms)
        self._webengine_visibility_watchdog_active = True
        self._webengine_visibility_watchdog_timer = timer

        def _tick():
            if _allow_guard_bypass(self):
                self._stop_webengine_visibility_watchdog()
                return
            try:
                now = time.monotonic()
            except Exception:
                now = 0.0
            try:
                until = float(getattr(self, "_webengine_close_guard_until", 0.0) or 0.0)
            except Exception:
                until = 0.0
            if not until or now >= until:
                try:
                    self._webengine_close_guard_active = False
                except Exception:
                    pass
                self._stop_webengine_visibility_watchdog()
                return
            if not getattr(self, "_webengine_close_guard_active", False):
                self._stop_webengine_visibility_watchdog()
                return
            try:
                if not self.isVisible() or self.windowState() & QtCore.Qt.WindowState.WindowMinimized:
                    _restore_window_after_guard(self)
            except Exception:
                pass

        timer.timeout.connect(_tick)
        timer.start()
        _tick()

    def _stop_webengine_visibility_watchdog(self):
        timer = getattr(self, "_webengine_visibility_watchdog_timer", None)
        if timer is not None:
            try:
                timer.stop()
            except Exception:
                pass
            try:
                timer.deleteLater()
            except Exception:
                pass
        self._webengine_visibility_watchdog_timer = None
        self._webengine_visibility_watchdog_active = False

    def _stop_tradingview_visibility_guard(self):
        timer = getattr(self, "_tv_visibility_guard_timer", None)
        if timer is not None:
            try:
                timer.stop()
            except Exception:
                pass
            try:
                timer.deleteLater()
            except Exception:
                pass
        self._tv_visibility_guard_timer = None
        self._tv_visibility_guard_active = False

    def _stop_tradingview_visibility_watchdog(self):
        timer = getattr(self, "_tv_visibility_watchdog_timer", None)
        if timer is not None:
            try:
                timer.stop()
            except Exception:
                pass
            try:
                timer.deleteLater()
            except Exception:
                pass
        self._tv_visibility_watchdog_timer = None
        self._tv_visibility_watchdog_active = False

    def _start_tradingview_window_suppression(self):
        if sys.platform != "win32":
            return
        flag = str(os.environ.get("BOT_TRADINGVIEW_WINDOW_SUPPRESS", "")).strip().lower()
        if flag not in {"1", "true", "yes", "on"}:
            return
        if getattr(self, "_tv_window_suppress_active", False):
            return
        try:
            import ctypes
            import ctypes.wintypes as wintypes
        except Exception:
            return
        self._tv_window_suppress_active = True

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        try:
            pid = int(kernel32.GetCurrentProcessId())
        except Exception:
            pid = 0

        TH32CS_SNAPPROCESS = 0x00000002
        SW_HIDE = 0
        debug_windows = str(os.environ.get("BOT_DEBUG_TRADINGVIEW_WINDOWS", "")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        debug_log_path = Path(os.getenv("TEMP") or ".").resolve() / "binance_tv_windows.log"

        def _get_hwnd_pid(hwnd_obj):  # noqa: ANN001
            try:
                out_pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd_obj, ctypes.byref(out_pid))
                return int(out_pid.value)
            except Exception:
                return 0

        def _class_name(hwnd_obj):  # noqa: ANN001
            try:
                buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd_obj, buf, 256)
                return str(buf.value or "").strip()
            except Exception:
                return ""

        def _is_transient(hwnd_obj, class_name: str | None = None):  # noqa: ANN001
            try:
                rect = wintypes.RECT()
                if not user32.GetWindowRect(hwnd_obj, ctypes.byref(rect)):
                    return False
                width = int(rect.right - rect.left)
                height = int(rect.bottom - rect.top)
                if width <= 0 or height <= 0:
                    return False
                class_name = class_name or _class_name(hwnd_obj)
                try:
                    GWL_STYLE = -16
                    WS_CHILD = 0x40000000
                    get_style = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
                    style = int(get_style(hwnd_obj, GWL_STYLE))
                    if style & WS_CHILD:
                        return False
                except Exception:
                    pass
                if class_name.startswith("Qt") and class_name.endswith(
                    (
                        "PowerDummyWindow",
                        "ClipboardView",
                        "ScreenChangeObserverWindow",
                        "ThemeChangeObserverWindow",
                    )
                ):
                    return True
                if class_name.startswith("_q_"):
                    return height <= 260 and width <= 4000
                if class_name == "Intermediate D3D Window":
                    return height <= 500 and width <= 4000
                if class_name.startswith("Chrome_WidgetWin_"):
                    return height <= 500 and width <= 4000
                if width >= 500 and height >= 300:
                    return False
                return height <= 120 and width <= 4000
            except Exception:
                return False

        def _hide(hwnd_obj):  # noqa: ANN001
            try:
                SWP_NOSIZE = 0x0001
                SWP_NOZORDER = 0x0004
                SWP_NOACTIVATE = 0x0010
                SWP_HIDEWINDOW = 0x0080
                SWP_ASYNCWINDOWPOS = 0x4000
                user32.SetWindowPos(
                    hwnd_obj,
                    0,
                    -32000,
                    -32000,
                    0,
                    0,
                    SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_HIDEWINDOW | SWP_ASYNCWINDOWPOS,
                )
            except Exception:
                pass
            try:
                if getattr(user32, "ShowWindowAsync", None):
                    user32.ShowWindowAsync(hwnd_obj, SW_HIDE)
                else:
                    user32.ShowWindow(hwnd_obj, SW_HIDE)
            except Exception:
                pass

        def _window_size(hwnd_obj):  # noqa: ANN001
            try:
                rect = wintypes.RECT()
                if not user32.GetWindowRect(hwnd_obj, ctypes.byref(rect)):
                    return None, None
                return int(rect.right - rect.left), int(rect.bottom - rect.top)
            except Exception:
                return None, None

        def _log_window(hwnd_obj, reason: str, pid_val: int, class_name: str) -> None:  # noqa: ANN001
            if not debug_windows:
                return
            try:
                width, height = _window_size(hwnd_obj)
                with open(debug_log_path, "a", encoding="utf-8", errors="ignore") as fh:
                    fh.write(
                        f"{reason} hwnd={int(hwnd_obj)} pid={pid_val} class={class_name!r} "
                        f"size={width}x{height}\n"
                    )
            except Exception:
                return

        class PROCESSENTRY32(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", wintypes.ULONG_PTR),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", wintypes.LONG),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", ctypes.c_wchar * 260),
            ]

        def _snapshot_processes():
            entries = []
            try:
                kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
                kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
                kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
                kernel32.Process32FirstW.restype = wintypes.BOOL
                kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
                kernel32.Process32NextW.restype = wintypes.BOOL
                kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
                kernel32.CloseHandle.restype = wintypes.BOOL
            except Exception:
                pass
            try:
                snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
            except Exception:
                snapshot = 0
            if snapshot in (0, ctypes.c_void_p(-1).value):
                return entries

            try:
                entry = PROCESSENTRY32()
                entry.dwSize = ctypes.sizeof(entry)
                if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
                    return entries
                while True:
                    entries.append((
                        int(entry.th32ProcessID),
                        int(entry.th32ParentProcessID),
                        str(entry.szExeFile or "").strip(),
                    ))
                    if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                        break
            finally:
                try:
                    kernel32.CloseHandle(snapshot)
                except Exception:
                    pass
            return entries

        def _collect_related_pids(root_pid: int):
            entries = _snapshot_processes()
            if not entries:
                return {root_pid} if root_pid else set(), set()
            children = {}
            exe_map = {}
            for proc_pid, parent_pid, exe in entries:
                exe_map[proc_pid] = exe
                children.setdefault(parent_pid, []).append(proc_pid)
            tree = set()
            stack = [root_pid] if root_pid else []
            while stack:
                cur = stack.pop()
                if cur in tree:
                    continue
                tree.add(cur)
                stack.extend(children.get(cur, []))
            qt_roots = {
                proc_pid
                for proc_pid in tree
                if "qtwebengineprocess" in (exe_map.get(proc_pid, "") or "").lower()
            }
            qt_tree = set()
            for root in qt_roots:
                stack = [root]
                while stack:
                    cur = stack.pop()
                    if cur in qt_tree:
                        continue
                    qt_tree.add(cur)
                    stack.extend(children.get(cur, []))
            return tree if tree else ({root_pid} if root_pid else set()), qt_tree

        pid_cache = {"ts": 0.0, "pids": {pid} if pid else set(), "qt_pids": set()}

        def _get_pid_sets():
            now = time.monotonic()
            if now - pid_cache["ts"] < 0.25:
                return pid_cache["pids"], pid_cache["qt_pids"]
            tree, qt_tree = _collect_related_pids(pid)
            pid_cache["ts"] = now
            pid_cache["pids"] = tree
            pid_cache["qt_pids"] = qt_tree
            return tree, qt_tree

        EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def _poll_once():
            allowed_pids, qt_pids = _get_pid_sets()

            def _enum_cb(hwnd_obj, _lparam):  # noqa: ANN001
                try:
                    pid_val = _get_hwnd_pid(hwnd_obj)
                    if allowed_pids and pid_val not in allowed_pids:
                        return True
                    try:
                        if not user32.IsWindowVisible(hwnd_obj):
                            return True
                    except Exception:
                        return True
                    class_name = _class_name(hwnd_obj)
                    if qt_pids and pid_val in qt_pids:
                        if _is_transient(hwnd_obj, class_name=class_name):
                            _log_window(hwnd_obj, "hide-qtwebengine", pid_val, class_name)
                            _hide(hwnd_obj)
                        return True
                except Exception:
                    return True
                return True

            cb = EnumWindowsProc(_enum_cb)
            try:
                user32.EnumWindows(cb, 0)
            except Exception:
                pass

        try:
            duration_ms = int(os.environ.get("BOT_TRADINGVIEW_WINDOW_SUPPRESS_MS") or 1800)
        except Exception:
            duration_ms = 1800
        duration_ms = max(300, min(duration_ms, 5000))
        try:
            interval_ms = int(os.environ.get("BOT_TRADINGVIEW_WINDOW_SUPPRESS_INTERVAL_MS") or 30)
        except Exception:
            interval_ms = 30
        interval_ms = max(15, min(interval_ms, 120))

        timer = QtCore.QTimer(self)
        timer.setInterval(interval_ms)
        start_ts = time.monotonic()

        def _tick():
            if (time.monotonic() - start_ts) * 1000.0 >= duration_ms:
                try:
                    timer.stop()
                except Exception:
                    pass
                try:
                    timer.deleteLater()
                except Exception:
                    pass
                self._tv_window_suppress_timer = None
                self._tv_window_suppress_active = False
                return
            _poll_once()

        timer.timeout.connect(_tick)
        timer.start()
        self._tv_window_suppress_timer = timer
        _tick()

    def _prime_tradingview_chart(self, widget):
        if widget is None:
            return
        try:
            symbol_text = (self.chart_symbol_combo.currentText() or "").strip().upper()
            interval_text = (self.chart_interval_combo.currentText() or "").strip()
        except Exception:
            return
        if not symbol_text or not interval_text:
            return
        interval_code = self._map_chart_interval(interval_text)
        if not interval_code:
            return
        market_text = self._normalize_chart_market(
            self.chart_market_combo.currentText() if hasattr(self, "chart_market_combo") else None
        )
        tv_symbol = self._format_chart_symbol(symbol_text, market_text)
        try:
            theme_name = (self.theme_combo.currentText() or "").strip()
        except Exception:
            theme_name = self.config.get("theme", "Dark")
        theme_code = "light" if str(theme_name or "").lower().startswith("light") else "dark"
        try:
            widget.set_chart(tv_symbol, interval_code, theme=theme_code, timezone="Etc/UTC")
        except Exception:
            return
        try:
            if hasattr(widget, "warmup"):
                widget.warmup()
        except Exception:
            pass

    def _open_tradingview_external(self) -> bool:
        try:
            symbol_text = (self.chart_symbol_combo.currentText() or "").strip().upper()
            interval_text = (self.chart_interval_combo.currentText() or "").strip()
        except Exception:
            return False
        if not symbol_text or not interval_text:
            return False
        interval_code = self._map_chart_interval(interval_text)
        if not interval_code:
            interval_code = "60"
        market_text = self._normalize_chart_market(
            self.chart_market_combo.currentText() if hasattr(self, "chart_market_combo") else None
        )
        tv_symbol = self._format_chart_symbol(symbol_text, market_text)
        try:
            now = time.monotonic()
        except Exception:
            now = 0.0
        if now and (now - float(getattr(self, "_tradingview_external_last_open_ts", 0.0) or 0.0)) < 1.0:
            return False
        self._tradingview_external_last_open_ts = now
        url = _build_tradingview_url(tv_symbol, interval_code)
        try:
            return bool(QtGui.QDesktopServices.openUrl(QtCore.QUrl(url)))
        except Exception:
            return False

    def _on_tradingview_ready(self):
        if not getattr(self, "_pending_tradingview_switch", False):
            return
        desired_mode = str(self.chart_config.get("view_mode") or "").strip().lower()
        if desired_mode != "tradingview":
            self._pending_tradingview_switch = False
            return
        widget = getattr(self, "chart_tradingview", None)
        if widget is None:
            self._pending_tradingview_switch = False
            return
        try:
            if hasattr(widget, "is_ready") and not widget.is_ready():
                return
        except Exception:
            pass
        if not self._is_chart_visible():
            return
        self._pending_tradingview_switch = False
        self.chart_view = widget
        try:
            with QtCore.QSignalBlocker(self.chart_view_mode_combo):
                idx = self.chart_view_mode_combo.findData("tradingview")
                if idx >= 0:
                    self.chart_view_mode_combo.setCurrentIndex(idx)
        except Exception:
            pass
        try:
            index = self.chart_view_stack.indexOf(widget)
            if index >= 0:
                self.chart_view_stack.setCurrentIndex(index)
        except Exception:
            pass
        try:
            self._on_chart_theme_changed()
        except Exception:
            pass
        self._chart_needs_render = True
        self._tradingview_first_switch_done = True
        self._hide_chart_switch_overlay(delay_ms=200)
        self._stop_tradingview_visibility_guard()
        if self._is_chart_visible():
            self.load_chart(auto=True)

    def eventFilter(self, obj, event):  # noqa: N802
        try:
            if obj is getattr(self, "chart_view_stack", None):
                ev_type = event.type()
                if ev_type in {QtCore.QEvent.Type.Resize, QtCore.QEvent.Type.Show}:
                    self._update_chart_overlay_geometry()
        except Exception:
            pass
        return super().eventFilter(obj, event)

    def _apply_chart_view_mode(self, mode: str, initial: bool = False, *, allow_tradingview_init: bool = True):
        if not getattr(self, "chart_enabled", False):
            return
        requested_mode = str(mode or "").strip().lower()
        if requested_mode not in {"tradingview", "original", "lightweight"}:
            requested_mode = "original"
        self._pending_webengine_mode = None
        try:
            self._chart_debug_log(
                f"apply_chart_view_mode requested={requested_mode} initial={int(bool(initial))} "
                f"allow_tv_init={int(bool(allow_tradingview_init))}"
            )
        except Exception:
            pass
        actual_mode = requested_mode
        widget = None
        defer_switch = False
        external_opened = False
        if requested_mode == "tradingview" and _tradingview_external_preferred():
            if not initial:
                try:
                    external_opened = self._open_tradingview_external()
                except Exception:
                    external_opened = False
            requested_mode = "original"
            actual_mode = "original"
        if requested_mode == "tradingview":
            if not self._chart_view_tradingview_available:
                actual_mode = "original"
            elif allow_tradingview_init:
                self._start_tradingview_close_guard()
                self._start_tradingview_visibility_watchdog()
                if not getattr(self, "_tradingview_first_switch_done", False):
                    if self._is_chart_visible():
                        self._show_chart_switch_overlay()
                    self._start_tradingview_window_suppression()
                    self._start_tradingview_visibility_guard()
                widget = self._ensure_tradingview_widget()
                if widget is None:
                    actual_mode = "original"
                else:
                    self._bind_tradingview_ready(widget)
                    try:
                        if hasattr(widget, "is_ready") and not widget.is_ready():
                            defer_switch = True
                    except Exception:
                        pass
            else:
                # Defer TradingView creation until the chart tab is visible to avoid startup flicker.
                self._pending_tradingview_mode = True
                actual_mode = "original"
        elif requested_mode == "lightweight":
            self._pending_tradingview_mode = False
            self._pending_tradingview_switch = False
            if not allow_tradingview_init and not self._is_chart_visible():
                self._pending_webengine_mode = "lightweight"
                actual_mode = "legacy"
            else:
                widget = self._ensure_lightweight_widget()
                if widget is None:
                    actual_mode = "original"
        elif requested_mode == "original":
            self._pending_tradingview_mode = False
            self._pending_tradingview_switch = False
            if not allow_tradingview_init and not self._is_chart_visible():
                self._pending_webengine_mode = "original"
                actual_mode = "legacy"
            else:
                widget = self._ensure_binance_widget()
                if widget is None:
                    actual_mode = "legacy"
        else:
            self._pending_tradingview_mode = False
            actual_mode = "legacy"
            self._pending_tradingview_switch = False
        if actual_mode != "tradingview":
            self._pending_tradingview_switch = False
            self._hide_chart_switch_overlay()
            self._stop_tradingview_visibility_guard()
            self._stop_tradingview_visibility_watchdog()
            self._tv_close_guard_active = False

        fallback_reason = None
        config_mode = requested_mode or actual_mode
        if requested_mode == "tradingview" and actual_mode != "tradingview" and not defer_switch:
            if not getattr(self, "_pending_tradingview_mode", False):
                fallback_reason = _tradingview_unavailable_reason()
                config_mode = "original"
        elif requested_mode == "lightweight" and actual_mode != "lightweight":
            if getattr(self, "_pending_webengine_mode", None) != "lightweight":
                fallback_reason = _lightweight_unavailable_reason()
                config_mode = "original"
        elif requested_mode == "original" and actual_mode != "original":
            if getattr(self, "_pending_webengine_mode", None) != "original":
                fallback_reason = _binance_unavailable_reason()
                config_mode = "original"

        if widget is None and actual_mode == "original":
            widget = self._ensure_binance_widget()
            if widget is None:
                actual_mode = "legacy"
        if widget is None:
            widget = self._chart_view_widgets.get(actual_mode)
        if widget is None:
            return
        combo_mode = "tradingview" if defer_switch else actual_mode
        if combo_mode == "legacy":
            combo_mode = "original"
        if defer_switch:
            self._pending_tradingview_mode = False
            self._pending_tradingview_switch = True
            if not getattr(self, "_tradingview_first_switch_done", False):
                self._show_chart_switch_overlay()
            try:
                with QtCore.QSignalBlocker(self.chart_view_mode_combo):
                    idx = self.chart_view_mode_combo.findData(combo_mode)
                    if idx >= 0:
                        self.chart_view_mode_combo.setCurrentIndex(idx)
            except Exception:
                pass
            self.chart_config["view_mode"] = config_mode
            self._chart_needs_render = True
            self._prime_tradingview_chart(widget)
            return

        self._pending_tradingview_switch = False
        self.chart_view = widget
        try:
            with QtCore.QSignalBlocker(self.chart_view_mode_combo):
                idx = self.chart_view_mode_combo.findData(combo_mode)
                if idx >= 0:
                    self.chart_view_mode_combo.setCurrentIndex(idx)
        except Exception:
            pass
        try:
            index = self.chart_view_stack.indexOf(widget)
            if index >= 0:
                self.chart_view_stack.setCurrentIndex(index)
        except Exception:
            pass
        self.chart_config["view_mode"] = config_mode
        if actual_mode == "tradingview":
            self._pending_tradingview_mode = False
            tv_class, _ = _load_tradingview_widget()
            if tv_class is not None and isinstance(widget, tv_class):
                try:
                    self._on_chart_theme_changed()
                except Exception:
                    pass
        self._chart_needs_render = True
        if fallback_reason and not initial:
            if requested_mode == "tradingview":
                opened = False
                try:
                    opened = self._open_tradingview_external()
                except Exception:
                    opened = False
                if opened:
                    try:
                        self._show_chart_status("TradingView opened in your browser.", color="#94a3b8")
                    except Exception:
                        pass
                else:
                    try:
                        self._show_chart_status(fallback_reason, color="#f59e0b")
                    except Exception:
                        pass
            else:
                try:
                    self._show_chart_status(fallback_reason, color="#f59e0b")
                except Exception:
                    pass
        status_text = "Chart view ready."
        if initial:
            self._show_chart_status(status_text, color="#d1d4dc")
            return
        if self._is_chart_visible():
            self.load_chart(auto=True)
        else:
            self._show_chart_status(status_text, color="#d1d4dc")
        if external_opened:
            try:
                self._show_chart_status("TradingView opened in your browser.", color="#94a3b8")
            except Exception:
                pass
        if actual_mode == "tradingview" and not defer_switch and not getattr(self, "_tradingview_first_switch_done", False):
            self._tradingview_first_switch_done = True
            self._hide_chart_switch_overlay(delay_ms=200)
        try:
            self._chart_debug_log(
                f"apply_chart_view_mode done actual={actual_mode} defer={int(bool(defer_switch))} "
                f"fallback={str(fallback_reason or '')}"
            )
        except Exception:
            pass

    def _on_chart_view_mode_changed(self, index: int):
        try:
            mode = self.chart_view_mode_combo.itemData(index)
        except Exception:
            mode = None
        if not mode:
            mode = self.chart_view_mode_combo.currentText()
        try:
            self._chart_debug_log(f"chart_view_mode_changed mode={str(mode or '').strip().lower()}")
        except Exception:
            pass
        mode_norm = str(mode or "").strip().lower()
        if _chart_safe_mode_enabled() and mode_norm in {"tradingview", "original", "lightweight"}:
            try:
                self._chart_debug_log(f"chart_view_mode_safe_blocked mode={mode_norm}")
            except Exception:
                pass
            if mode_norm == "tradingview":
                opened = False
                try:
                    opened = self._open_tradingview_external()
                except Exception:
                    opened = False
                if opened:
                    self._show_chart_status(
                        "TradingView opened in your browser. Set BOT_SAFE_CHART_TAB=0 to embed.",
                        color="#94a3b8",
                    )
                else:
                    self._show_chart_status(
                        "TradingView embed disabled. Set BOT_SAFE_CHART_TAB=0 to embed.",
                        color="#f59e0b",
                    )
            else:
                self._show_chart_status(
                    "Web charts disabled for stability. Set BOT_SAFE_CHART_TAB=0 to enable.",
                    color="#f59e0b",
                )
            legacy = self._chart_view_widgets.get("legacy")
            if legacy is not None:
                try:
                    self.chart_view = legacy
                    idx = self.chart_view_stack.indexOf(legacy)
                    if idx >= 0:
                        self.chart_view_stack.setCurrentIndex(idx)
                except Exception:
                    pass
            try:
                with QtCore.QSignalBlocker(self.chart_view_mode_combo):
                    fallback_idx = self.chart_view_mode_combo.findData("original")
                    if fallback_idx >= 0:
                        self.chart_view_mode_combo.setCurrentIndex(fallback_idx)
            except Exception:
                pass
            try:
                self.chart_config["view_mode"] = "original"
            except Exception:
                pass
            if self._is_chart_visible():
                self.load_chart(auto=True)
            return
        self._apply_chart_view_mode(mode)

    def _restore_chart_controls_from_config(self):
        if not getattr(self, "chart_enabled", False):
            return
        market_cfg = self._normalize_chart_market(self.chart_config.get("market"))
        auto_follow_cfg = self.chart_config.get("auto_follow")
        self._chart_manual_override = False
        if auto_follow_cfg is None:
            self.chart_auto_follow = (market_cfg == "Futures")
        else:
            self.chart_auto_follow = bool(auto_follow_cfg) and market_cfg == "Futures"
        market_combo = getattr(self, "chart_market_combo", None)
        if market_combo is not None:
            try:
                with QtCore.QSignalBlocker(market_combo):
                    idx = market_combo.findText(market_cfg, QtCore.Qt.MatchFlag.MatchFixedString)
                    if idx >= 0:
                        market_combo.setCurrentIndex(idx)
                    else:
                        market_combo.setCurrentText(market_cfg)
            except Exception:
                market_combo.setCurrentText(market_cfg)
        self.chart_config["market"] = market_cfg
        self.chart_config["auto_follow"] = self.chart_auto_follow
        symbol_cfg = str(self.chart_config.get("symbol") or "").strip().upper()
        interval_cfg = str(self.chart_config.get("interval") or "").strip()
        if symbol_cfg:
            self._set_chart_symbol(symbol_cfg, ensure_option=True)
        if interval_cfg:
            self._set_chart_interval(interval_cfg)
        elif CHART_INTERVAL_OPTIONS:
            self._set_chart_interval(CHART_INTERVAL_OPTIONS[0])
        view_mode_cfg = str(self.chart_config.get("view_mode") or "").strip().lower()
        if view_mode_cfg:
            self._apply_chart_view_mode(view_mode_cfg, initial=True, allow_tradingview_init=False)

    def _update_chart_symbol_options(self, symbols=None):
        if not getattr(self, "chart_enabled", False):
            return
        if not hasattr(self, "chart_symbol_combo"):
            return
        combo = self.chart_symbol_combo
        current = combo.currentText().strip().upper()
        market = self._normalize_chart_market(getattr(self, "chart_market_combo", None).currentText() if hasattr(self, "chart_market_combo") else None)
        if symbols is None:
            symbols = list(self.chart_symbol_cache.get(market) or [])
            if not symbols and market == "Futures":
                symbols = self._current_dashboard_symbols()
                if symbols:
                    self.chart_symbol_cache[market] = list(symbols)
        uniques = []
        seen = set()
        for sym in symbols or []:
            sym_norm = str(sym or "").strip().upper()
            if sym_norm and sym_norm not in seen:
                seen.add(sym_norm)
                uniques.append(sym_norm)
        self.chart_symbol_cache[market] = list(uniques)
        display_symbols = list(uniques)
        alias_map = {}
        if market == "Futures":
            display_symbols = []
            for sym in uniques:
                disp = self._futures_display_symbol(sym)
                alias_map[disp] = sym
                if disp not in display_symbols:
                    display_symbols.append(disp)
            preferred_disp = self._futures_display_symbol("BTCUSDT")
            if "BTCUSDT" in uniques:
                if preferred_disp in display_symbols:
                    display_symbols.remove(preferred_disp)
                display_symbols.insert(0, preferred_disp)
                alias_map[preferred_disp] = "BTCUSDT"
        if not isinstance(getattr(self, "_chart_symbol_alias_map", None), dict):
            self._chart_symbol_alias_map = {}
        self._chart_symbol_alias_map[market] = alias_map
        if market == "Futures" and current:
            if current not in alias_map:
                reverse_map = {v: k for k, v in alias_map.items()}
                if current in reverse_map:
                    current = reverse_map[current]
                else:
                    current = self._futures_display_symbol(current)
        elif market != "Futures":
            alias_map = {}
        try:
            with QtCore.QSignalBlocker(combo):
                combo.clear()
                if display_symbols:
                    combo.addItems(display_symbols)
        except Exception:
            combo.clear()
            if display_symbols:
                combo.addItems(display_symbols)
        if current:
            if combo.findText(current, QtCore.Qt.MatchFlag.MatchFixedString) >= 0:
                combo.setCurrentText(current)
            else:
                combo.setEditText(current)
        elif display_symbols:
            combo.setCurrentIndex(0)

    def _chart_debug_log(self, message: str) -> None:
        try:
            ts = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
        except Exception:
            ts = "unknown-time"
        try:
            path = getattr(self, "_chart_debug_log_path", None)
            if path is None:
                path = Path(os.getenv("TEMP") or ".").resolve() / "binance_chart_debug.log"
                self._chart_debug_log_path = path
            with open(path, "a", encoding="utf-8", errors="ignore") as fh:
                fh.write(f"[{ts}] {message}\n")
        except Exception:
            return

    @staticmethod
    def _normalize_chart_market(market):
        text = str(market or "").strip().lower()
        for opt in CHART_MARKET_OPTIONS:
            if text.startswith(opt.lower()):
                return opt
        return "Futures"

    @staticmethod
    def _normalize_assets_mode(value):
        text = str(value or "").strip().lower()
        if "multi" in text:
            return "Multi-Assets"
        return "Single-Asset"

    @staticmethod
    def _normalize_account_mode(value):
        text = str(value or "").strip().lower()
        if "portfolio" in text:
            return "Portfolio Margin"
        return "Classic Trading"

    def _update_leverage_enabled(self):
        """Disable leverage control when Spot is selected."""
        try:
            acct = str(self.config.get("account_type") or "")
            is_futures = acct.strip().upper().startswith("FUT")
        except Exception:
            is_futures = True
        try:
            spin = getattr(self, "leverage_spin", None)
            if spin is not None:
                if not is_futures:
                    spin.setValue(1)
                spin.setEnabled(is_futures)
        except Exception:
            pass
        # Futures-only controls
        futures_only_widgets = []
        try:
            futures_only_widgets.extend([
                getattr(self, "margin_mode_combo", None),
                getattr(self, "position_mode_combo", None),
                getattr(self, "assets_mode_combo", None),
                getattr(self, "account_mode_combo", None),
                getattr(self, "allow_opposite_checkbox", None),
                getattr(self, "cb_add_only", None),
                getattr(self, "lead_trader_enable_cb", None),
                getattr(self, "lead_trader_combo", None),
            ])
        except Exception:
            pass
        for widget in futures_only_widgets:
            try:
                if widget is None:
                    continue
                widget.setEnabled(is_futures)
            except Exception:
                pass
        # Force side to BUY when on spot; disable other options.
        try:
            side_combo = getattr(self, "side_combo", None)
            if side_combo is not None:
                if not is_futures:
                    label_buy = SIDE_LABELS["BUY"]
                    idx_buy = side_combo.findText(label_buy)
                    if idx_buy >= 0:
                        blocker = None
                        try:
                            blocker = QtCore.QSignalBlocker(side_combo)
                        except Exception:
                            blocker = None
                        side_combo.setCurrentIndex(idx_buy)
                        if blocker is not None:
                            del blocker
                    side_combo.setEnabled(False)
                else:
                    side_combo.setEnabled(True)
        except Exception:
            pass

    def _rebuild_connector_combo_for_account(self, account_key: str, *, force_default: bool = False, current_backend: str | None = None) -> str:
        """Ensure the connector dropdown matches the selected account type (spot vs futures)."""
        allowed = FUTURES_CONNECTOR_KEYS if account_key == "FUTURES" else SPOT_CONNECTOR_KEYS
        recommended = _recommended_connector_for_key(account_key)
        target = _normalize_connector_backend(current_backend or self.config.get("connector_backend"))
        if force_default or target not in allowed:
            target = recommended
        combo = getattr(self, "connector_combo", None)
        chosen = target
        if combo is not None:
            try:
                blocker = QtCore.QSignalBlocker(combo)
            except Exception:
                blocker = None
            combo.clear()
            for label, value in CONNECTOR_OPTIONS:
                if value in allowed:
                    combo.addItem(label, value)
            if combo.count():
                idx = combo.findData(target)
                if idx < 0:
                    idx = combo.findData(recommended)
                if idx < 0:
                    idx = 0
                combo.setCurrentIndex(max(0, idx))
                try:
                    chosen = _normalize_connector_backend(combo.itemData(combo.currentIndex()))
                except Exception:
                    chosen = target
            if blocker is not None:
                del blocker
        self.config["connector_backend"] = chosen
        return chosen

    def _ensure_runtime_connector_for_account(self, account_type: str, *, force_default: bool = False, suppress_refresh: bool = False) -> str:
        account_key = "FUTURES" if str(account_type or "Futures").upper().startswith("FUT") else "SPOT"
        current_backend = _normalize_connector_backend(self.config.get("connector_backend"))
        chosen = self._rebuild_connector_combo_for_account(account_key, force_default=force_default, current_backend=current_backend)
        if not suppress_refresh:
            self._update_connector_labels()
        return self.config.get("connector_backend", chosen)

    def _runtime_connector_backend(self, *, suppress_refresh: bool = False) -> str:
        account_type = str(self.config.get("account_type", "Futures") or "Futures")
        return self._ensure_runtime_connector_for_account(account_type, force_default=False, suppress_refresh=suppress_refresh)

    def _backtest_connector_backend(self) -> str:
        source_text = ""
        if hasattr(self, "backtest_symbol_source_combo") and self.backtest_symbol_source_combo is not None:
            try:
                source_text = self.backtest_symbol_source_combo.currentText()
            except Exception:
                source_text = ""
        source_key = "SPOT" if str(source_text or "Futures").strip().lower().startswith("spot") else "FUTURES"
        allowed = FUTURES_CONNECTOR_KEYS if source_key == "FUTURES" else SPOT_CONNECTOR_KEYS
        recommended = _recommended_connector_for_key(source_key)
        backend = _normalize_connector_backend(self.backtest_config.get("connector_backend"))
        if backend not in allowed:
            backend = recommended
        self.backtest_config["connector_backend"] = backend
        self.config.setdefault("backtest", {})["connector_backend"] = backend
        return backend

    def _create_binance_wrapper(self, *, api_key: str, api_secret: str, mode: str, account_type: str, connector_backend: str | None = None, **kwargs) -> BinanceWrapper:
        backend = connector_backend or self._runtime_connector_backend(suppress_refresh=True)
        return BinanceWrapper(
            api_key,
            api_secret,
            mode=mode,
            account_type=account_type,
            connector_backend=backend,
            **kwargs,
        )

    def _invalidate_shared_binance(self, reason: str | None = None):
        try:
            existing = getattr(self, "shared_binance", None)
        except Exception:
            existing = None
        if existing is not None:
            try:
                self.shared_binance = None
            except Exception:
                self.__dict__["shared_binance"] = None
        try:
            self._shared_binance_invalidated_reason = reason
        except Exception:
            pass
        try:
            if getattr(self, "balance_label", None):
                self.balance_label.setText("N/A")
        except Exception:
            pass
        try:
            self._update_positions_balance_labels(None, None)
        except Exception:
            pass

    def _on_api_credentials_changed(self):
        self._invalidate_shared_binance("credentials_changed")
        self._reconfigure_positions_worker()

    def _on_mode_changed(self, value: str):
        try:
            self.config["mode"] = str(value or self.mode_combo.currentText() or "Live")
        except Exception:
            pass
        self._invalidate_shared_binance("mode_changed")
        self._reconfigure_positions_worker()

    def _connector_label_text(self, backend: str) -> str:
        backend = _normalize_connector_backend(backend)
        for label, value in CONNECTOR_OPTIONS:
            if value == backend:
                return label
        return backend.title()

    def _update_connector_labels(self):
        try:
            self._refresh_symbol_interval_pairs("runtime")
        except Exception:
            pass
        try:
            self._refresh_symbol_interval_pairs("backtest")
        except Exception:
            pass

    def _on_account_type_changed(self, value):
        account_text = str(value or "").strip()
        try:
            if not account_text and hasattr(self, "account_combo"):
                account_text = str(self.account_combo.currentText() or "Futures").strip()
        except Exception:
            account_text = "Futures"
        if not account_text:
            account_text = "Futures"
        normalized = "Futures" if account_text.lower().startswith("fut") else "Spot"
        self.config["account_type"] = normalized
        self._invalidate_shared_binance("account_type_changed")
        self._ensure_runtime_connector_for_account(normalized, force_default=False)
        self._update_leverage_enabled()
        desired_spot = "Binance spot"
        desired_futures = "Binance futures"
        try:
            combo = getattr(self, "ind_source_combo", None)
            if combo is not None:
                current_source = (combo.currentText() or "").strip()
                lowered = current_source.lower()
                target_source = current_source
                if normalized == "Spot" and "futures" in lowered:
                    target_source = desired_spot
                elif normalized == "Futures" and ("spot" in lowered and "futures" not in lowered):
                    target_source = desired_futures
                if target_source and target_source != current_source:
                    blocker = None
                    try:
                        blocker = QtCore.QSignalBlocker(combo)
                    except Exception:
                        blocker = None
                    combo.setCurrentText(target_source)
                    if blocker is not None:
                        del blocker
                self.config["indicator_source"] = combo.currentText()
                if hasattr(self, "shared_binance") and self.shared_binance is not None:
                    try:
                        self.shared_binance.indicator_source = combo.currentText()
                    except Exception:
                        pass
        except Exception:
            pass

    def _refresh_backtest_connector_options(self, symbol_source: str | None = None, *, force_default: bool = False) -> None:
        if not hasattr(self, "backtest_connector_combo") or self.backtest_connector_combo is None:
            return
        source_text = (symbol_source or "")
        if not source_text and hasattr(self, "backtest_symbol_source_combo") and self.backtest_symbol_source_combo is not None:
            try:
                source_text = self.backtest_symbol_source_combo.currentText()
            except Exception:
                source_text = ""
        source_key = "SPOT" if str(source_text or "Futures").strip().lower().startswith("spot") else "FUTURES"
        allowed = FUTURES_CONNECTOR_KEYS if source_key == "FUTURES" else SPOT_CONNECTOR_KEYS
        recommended = _recommended_connector_for_key(source_key)
        current_backend = _normalize_connector_backend(self.backtest_config.get("connector_backend"))
        if force_default or current_backend not in allowed:
            current_backend = recommended
        blocker = None
        try:
            blocker = QtCore.QSignalBlocker(self.backtest_connector_combo)
        except Exception:
            blocker = None
        self.backtest_connector_combo.clear()
        for label, value in CONNECTOR_OPTIONS:
            if value in allowed:
                self.backtest_connector_combo.addItem(label, value)
        idx = self.backtest_connector_combo.findData(current_backend)
        if idx < 0:
            idx = self.backtest_connector_combo.findData(recommended)
        if idx < 0 and self.backtest_connector_combo.count():
            idx = 0
        if idx >= 0 and self.backtest_connector_combo.count():
            self.backtest_connector_combo.setCurrentIndex(idx)
            current_backend = _normalize_connector_backend(self.backtest_connector_combo.currentData())
        if blocker is not None:
            del blocker
        self.backtest_config["connector_backend"] = current_backend
        self.config.setdefault("backtest", {})["connector_backend"] = current_backend
        self._update_backtest_config("connector_backend", current_backend)
        self._update_connector_labels()
        try:
            self._reconfigure_positions_worker()
        except Exception:
            pass
        if getattr(self, "_ui_initialized", False):
            try:
                self.refresh_symbols()
            except Exception:
                pass

    def _on_runtime_connector_changed(self, *_args):
        try:
            data = None
            if hasattr(self, "connector_combo") and self.connector_combo is not None:
                data = self.connector_combo.currentData()
                if data is None:
                    data = self.connector_combo.currentText()
            backend = _normalize_connector_backend(data)
        except Exception:
            backend = DEFAULT_CONNECTOR_BACKEND
        self.config["connector_backend"] = backend
        self._update_connector_labels()
        try:
            self._reconfigure_positions_worker()
        except Exception:
            pass

    def _on_backtest_connector_changed(self, *_args):
        try:
            data = None
            if hasattr(self, "backtest_connector_combo") and self.backtest_connector_combo is not None:
                data = self.backtest_connector_combo.currentData()
                if data is None:
                    data = self.backtest_connector_combo.currentText()
            backend = _normalize_connector_backend(data)
        except Exception:
            backend = DEFAULT_CONNECTOR_BACKEND
        self.backtest_config["connector_backend"] = backend
        self.config.setdefault("backtest", {})["connector_backend"] = backend
        self._update_connector_labels()

    def _futures_display_symbol(self, symbol: str) -> str:
        sym = (symbol or "").strip().upper()
        if not sym:
            return sym
        if sym.endswith(".P"):
            return sym
        if sym.endswith("USDT") and not sym.endswith("BUSD"):
            return f"{sym}.P"
        return sym

    def _resolve_chart_symbol_for_api(self, symbol: str, market: str | None = None) -> str:
        sym = (symbol or "").strip().upper()
        cfg_market = market
        if cfg_market is None:
            try:
                cfg_market = self.chart_config.get("market")
            except Exception:
                cfg_market = None
        market_norm = self._normalize_chart_market(cfg_market)
        if market_norm == "Futures":
            alias_map = {}
            mapping = getattr(self, "_chart_symbol_alias_map", {})
            if isinstance(mapping, dict):
                alias_map = mapping.get(market_norm, {}) or {}
            if sym in alias_map:
                return alias_map[sym]
            if sym.endswith(".P"):
                return sym[:-2]
        return sym

    def _current_dashboard_symbols(self):
        symbols = []
        if hasattr(self, "symbol_list") and isinstance(self.symbol_list, QtWidgets.QListWidget):
            try:
                for idx in range(self.symbol_list.count()):
                    item = self.symbol_list.item(idx)
                    if item:
                        sym = item.text().strip().upper()
                        if sym:
                            symbols.append(sym)
            except Exception:
                return symbols
        return symbols

    def _on_chart_controls_changed(self, *_args):
        if not getattr(self, "chart_enabled", False):
            return
        if not hasattr(self, "chart_config"):
            return
        try:
            symbol = (self.chart_symbol_combo.currentText() or "").strip().upper()
            interval = (self.chart_interval_combo.currentText() or "").strip()
        except Exception:
            return
        changed = False
        symbol_changed = False
        if symbol:
            if self.chart_config.get("symbol") != symbol:
                changed = True
                symbol_changed = True
            self.chart_config["symbol"] = symbol
        if interval:
            if self.chart_config.get("interval") != interval:
                changed = True
            self.chart_config["interval"] = interval
        if self._chart_updating:
            return
        market = self._normalize_chart_market(self.chart_config.get("market"))
        if market == "Futures" and symbol_changed:
            self._chart_manual_override = True
            self.chart_auto_follow = False
            self.chart_config["auto_follow"] = False
        if changed:
            self._chart_needs_render = True
            if self._is_chart_visible():
                self.load_chart(auto=True)

    def _chart_account_type(self, market: str) -> str:
        normalized = self._normalize_chart_market(market)
        return "Spot" if normalized == "Spot" else "Futures"

    def _on_chart_market_changed(self, text: str):
        if not getattr(self, "chart_enabled", False):
            return
        market = self._normalize_chart_market(text)
        self.chart_config["market"] = market
        self._chart_manual_override = False
        self.chart_auto_follow = (market == "Futures")
        self.chart_config["auto_follow"] = self.chart_auto_follow
        cache = list(self.chart_symbol_cache.get(market) or [])
        if not cache:
            cache = list(DEFAULT_CHART_SYMBOLS)
            self.chart_symbol_cache[market] = cache
        self._update_chart_symbol_options(cache)
        self._chart_needs_render = True
        if cache:
            preferred_cfg = self.chart_config.get("symbol")
            preferred_actual = self._resolve_chart_symbol_for_api(preferred_cfg, market) if preferred_cfg else None
            if not preferred_actual or preferred_actual not in cache:
                preferred_actual = cache[0]
            preferred_display = self._futures_display_symbol(preferred_actual) if market == "Futures" else preferred_actual
            changed = self._set_chart_symbol(preferred_display, ensure_option=True, from_follow=self.chart_auto_follow)
            if self.chart_auto_follow and market == "Futures":
                if changed or self._chart_needs_render:
                    self._apply_dashboard_selection_to_chart(load=False)
            elif self._is_chart_visible():
                self.load_chart(auto=True)
        self._load_chart_symbols_async(market)

    def _load_chart_symbols_async(self, market: str):
        if not getattr(self, "chart_enabled", False):
            return
        market_key = self._normalize_chart_market(market)
        if market_key in self._chart_symbol_loading:
            return
        self._chart_symbol_loading.add(market_key)
        api_key = self.api_key_edit.text().strip() if hasattr(self, "api_key_edit") else ""
        api_secret = self.api_secret_edit.text().strip() if hasattr(self, "api_secret_edit") else ""
        mode = self.mode_combo.currentText() if hasattr(self, "mode_combo") else "Live"
        account_type = self._chart_account_type(market_key)

        def _do():
            tmp_wrapper = self._create_binance_wrapper(
                api_key=api_key,
                api_secret=api_secret,
                mode=mode,
                account_type=account_type,
            )
            syms = tmp_wrapper.fetch_symbols(sort_by_volume=True, top_n=_SYMBOL_FETCH_TOP_N)
            cleaned = []
            seen_local = set()
            for sym in syms or []:
                sym_norm = str(sym or "").strip().upper()
                if not sym_norm:
                    continue
                if sym_norm in seen_local:
                    continue
                seen_local.add(sym_norm)
                cleaned.append(sym_norm)
            return cleaned

        def _chart_should_render():
            try:
                return bool(self._chart_pending_initial_load or self._is_chart_visible())
            except Exception:
                return False

        def _done(res, err):
            try:
                symbols = []
                if isinstance(res, list) and res:
                    symbols = [str(sym or "").strip().upper() for sym in res if str(sym or "").strip()]
                if err or not symbols:
                    try:
                        self.log(f"Chart symbol load error for {market_key}: {err or 'no symbols returned'}; using defaults.")
                    except Exception:
                        pass
                    symbols = list(DEFAULT_CHART_SYMBOLS)
                self.chart_symbol_cache[market_key] = symbols
                self._chart_needs_render = True
                current_market = self._normalize_chart_market(getattr(self, "chart_market_combo", None).currentText() if hasattr(self, "chart_market_combo") else None)
                if current_market == market_key:
                    self._update_chart_symbol_options(symbols)
                    if symbols:
                        preferred_cfg = self.chart_config.get("symbol")
                        preferred_actual = self._resolve_chart_symbol_for_api(preferred_cfg, market_key) if preferred_cfg else None
                        if not preferred_actual or preferred_actual not in symbols:
                            preferred_actual = symbols[0]
                        preferred_display = self._futures_display_symbol(preferred_actual) if market_key == "Futures" else preferred_actual
                        from_follow = (market_key == "Futures") and not self._chart_manual_override
                        changed = self._set_chart_symbol(preferred_display, ensure_option=True, from_follow=from_follow)
                        if from_follow:
                            if changed:
                                self._apply_dashboard_selection_to_chart(load=True)
                        elif changed and _chart_should_render():
                            self.load_chart(auto=True)
                    elif _chart_should_render():
                        self.load_chart(auto=True)
            finally:
                self._chart_symbol_loading.discard(market_key)

        worker = CallWorker(_do, parent=self)
        try:
            worker.progress.connect(self.log)
        except Exception:
            pass
        worker.done.connect(_done)
        if not hasattr(self, "_bg_workers"):
            self._bg_workers = []
        self._bg_workers.append(worker)

        def _cleanup():
            try:
                self._bg_workers.remove(worker)
            except Exception:
                pass

        worker.finished.connect(_cleanup)
        worker.start()

    def _apply_dashboard_selection_to_chart(self, load: bool = False):
        if not getattr(self, "chart_enabled", False):
            return
        should_render = self._chart_pending_initial_load or self._is_chart_visible()
        if not self.chart_auto_follow:
            if load and should_render:
                self.load_chart(auto=True)
            return
        current_market = self._normalize_chart_market(getattr(self, "chart_market_combo", None).currentText() if hasattr(self, "chart_market_combo") else None)
        if current_market != "Futures":
            if load and should_render:
                self.load_chart(auto=True)
            return
        changed = False
        symbol = self._selected_dashboard_symbol()
        interval = self._selected_dashboard_interval()
        if symbol:
            display_symbol = self._futures_display_symbol(symbol) if current_market == "Futures" else symbol
            changed = self._set_chart_symbol(display_symbol, ensure_option=True, from_follow=True) or changed
        if interval:
            changed = self._set_chart_interval(interval) or changed
        if (changed and should_render) or (load and should_render):
            self.load_chart(auto=True)

    def _selected_dashboard_symbol(self):
        if not getattr(self, "chart_enabled", False):
            return ""
        if not hasattr(self, "symbol_list"):
            return ""
        selected = []
        try:
            for idx in range(self.symbol_list.count()):
                item = self.symbol_list.item(idx)
                if item and item.isSelected():
                    sym = item.text().strip().upper()
                    if sym:
                        selected.append(sym)
        except Exception:
            return ""
        if selected:
            return selected[0]
        if self.symbol_list.count():
            first_item = self.symbol_list.item(0)
            if first_item:
                return first_item.text().strip().upper()
        return self.chart_config.get("symbol", "")

    def _selected_dashboard_interval(self):
        if not getattr(self, "chart_enabled", False):
            return ""
        if not hasattr(self, "interval_list"):
            return ""
        selected = []
        try:
            for idx in range(self.interval_list.count()):
                item = self.interval_list.item(idx)
                if item and item.isSelected():
                    iv = item.text().strip()
                    if iv:
                        selected.append(iv)
        except Exception:
            return ""
        if selected:
            return selected[0]
        if self.interval_list.count():
            first_item = self.interval_list.item(0)
            if first_item:
                return first_item.text().strip()
        return self.chart_config.get("interval", "")

    @staticmethod
    def _canonical_side_from_text(text: str) -> str:
        raw = str(text or "").strip()
        if not raw:
            return "BOTH"
        lower = raw.lower()
        if lower in SIDE_LABEL_LOOKUP:
            return SIDE_LABEL_LOOKUP[lower]
        if lower.startswith("buy"):
            return "BUY"
        if lower.startswith("sell"):
            return "SELL"
        return "BOTH"

    @staticmethod
    def _canonicalize_interval(interval: str) -> str:
        raw = str(interval or "").strip()
        if not raw:
            return ""
        lower = raw.lower()
        if lower in BINANCE_INTERVAL_LOWER:
            return lower
        if raw.upper() == "1M" or lower in {"1month", "1mo"}:
            return "1M"
        return ""

    def _resolve_dashboard_side(self) -> str:
        sel = self.side_combo.currentText() if hasattr(self, "side_combo") else ""
        return self._canonical_side_from_text(sel)

    def _collect_strategy_indicators(self, symbol: str, side_key: str, intervals: list[str] | set[str] | None = None) -> list[str]:
        indicators = set()
        metadata = getattr(self, "_engine_indicator_map", {}) or {}
        side_key = (side_key or "").upper()
        normalized_intervals: set[str] | None = None
        if intervals:
            normalized_intervals = {
                self._canonicalize_interval(iv) or str(iv).strip().lower()
                for iv in intervals
                if iv
            }
        for meta in metadata.values():
            if not isinstance(meta, dict):
                continue
            if meta.get("symbol") != symbol:
                continue
            meta_interval = self._canonicalize_interval(meta.get("interval"))
            if normalized_intervals is not None:
                if meta_interval and meta_interval in normalized_intervals:
                    pass
                elif meta_interval and meta_interval.replace(".", "") in normalized_intervals:
                    pass
                elif meta.get("interval") and str(meta.get("interval")).strip().lower() in normalized_intervals:
                    pass
                else:
                    continue
            side_cfg = (meta.get("side") or "BOTH").upper()
            if side_key in ("", "SPOT") or side_cfg == "BOTH":
                pass
            elif side_key == "L" and side_cfg != "BUY":
                continue
            elif side_key == "S" and side_cfg != "SELL":
                continue
            override_inds = meta.get("override_indicators") or []
            configured_inds = meta.get("configured_indicators") or meta.get("indicators") or []
            selected = override_inds if override_inds else configured_inds
            for ind in selected:
                if ind:
                    indicators.add(str(ind))
        return sorted(indicators)

    def _position_stop_loss_enabled(self, symbol: str, side_key: str) -> bool:
        metadata = getattr(self, "_engine_indicator_map", {}) or {}
        symbol = str(symbol or "").strip().upper()
        side_key = (side_key or "").upper()
        for meta in metadata.values():
            if not isinstance(meta, dict):
                continue
            if str(meta.get("symbol") or "").strip().upper() != symbol:
                continue
            side_cfg = str(meta.get("side") or "BOTH").upper()
            if side_cfg == "BOTH":
                pass
            elif side_cfg == "BUY" and side_key != "L":
                continue
            elif side_cfg == "SELL" and side_key != "S":
                continue
            if meta.get("stop_loss_enabled"):
                return True
        return False

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

    def _set_chart_symbol(self, symbol: str, ensure_option: bool = False, from_follow: bool = False) -> bool:
        if not getattr(self, "chart_enabled", False):
            return False
        if not hasattr(self, "chart_symbol_combo"):
            return False
        combo = self.chart_symbol_combo
        normalized = str(symbol or "").strip().upper()
        if not normalized:
            return False
        before = combo.currentText().strip().upper()
        self._chart_updating = True
        changed = False
        try:
            try:
                with QtCore.QSignalBlocker(combo):
                    idx = combo.findText(normalized, QtCore.Qt.MatchFlag.MatchFixedString)
                    if idx >= 0:
                        combo.setCurrentIndex(idx)
                    elif ensure_option:
                        combo.addItem(normalized)
                        combo.setCurrentIndex(combo.count() - 1)
                    else:
                        combo.setEditText(normalized)
            except Exception:
                idx = combo.findText(normalized, QtCore.Qt.MatchFlag.MatchFixedString)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                elif ensure_option:
                    combo.addItem(normalized)
                    combo.setCurrentIndex(combo.count() - 1)
                else:
                    combo.setEditText(normalized)
            after = combo.currentText().strip().upper()
            changed = before != after
            if after:
                self.chart_config["symbol"] = after
        finally:
            self._chart_updating = False
        if changed:
            self._chart_needs_render = True
        if from_follow:
            self._chart_manual_override = False
            self.chart_auto_follow = True
            self.chart_config["auto_follow"] = True
        return changed

    def _set_chart_interval(self, interval: str) -> bool:
        if not getattr(self, "chart_enabled", False):
            return False
        if not hasattr(self, "chart_interval_combo"):
            return False
        combo = self.chart_interval_combo
        normalized = str(interval or "").strip()
        if not normalized:
            return False
        before = combo.currentText().strip()
        self._chart_updating = True
        changed = False
        try:
            try:
                with QtCore.QSignalBlocker(combo):
                    idx = combo.findText(normalized, QtCore.Qt.MatchFlag.MatchFixedString)
                    if idx >= 0:
                        combo.setCurrentIndex(idx)
                    else:
                        combo.addItem(normalized)
                        combo.setCurrentIndex(combo.count() - 1)
            except Exception:
                idx = combo.findText(normalized, QtCore.Qt.MatchFlag.MatchFixedString)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                else:
                    combo.addItem(normalized)
                    combo.setCurrentIndex(combo.count() - 1)
            after = combo.currentText().strip()
            changed = before != after
            if after:
                self.chart_config["interval"] = after
        finally:
            self._chart_updating = False
        if changed:
            self._chart_needs_render = True
        return changed

    def _map_chart_interval(self, interval: str) -> str | None:
        key = str(interval or "").strip().lower()
        if not key:
            return None
        mapped = TRADINGVIEW_INTERVAL_MAP.get(key)
        if mapped:
            return mapped
        if key.endswith("m"):
            try:
                minutes = int(float(key[:-1]))
                if minutes > 0:
                    return str(minutes)
            except Exception:
                return None
        if key.endswith("h"):
            try:
                hours = float(key[:-1])
                minutes = int(hours * 60)
                if minutes > 0:
                    return str(minutes)
            except Exception:
                return None
        if key.endswith("d"):
            try:
                days = int(float(key[:-1]))
                if days > 0:
                    return f"{days}D"
            except Exception:
                return None
        if key.endswith("w"):
            try:
                weeks = int(float(key[:-1]))
                if weeks > 0:
                    return f"{weeks}W"
            except Exception:
                return None
        if key.endswith("mo") or key.endswith("month") or key.endswith("months"):
            digits = "".join(ch for ch in key if ch.isdigit())
            try:
                qty = int(digits) if digits else 1
            except Exception:
                qty = 1
            if qty > 0:
                return f"{qty}M"
        if key.endswith("y") or key.endswith("year") or key.endswith("years"):
            digits = "".join(ch for ch in key if ch.isdigit())
            try:
                qty = int(digits) if digits else 1
            except Exception:
                qty = 1
            if qty > 0:
                return f"{qty * 12}M"
        return None

    def _format_chart_symbol(self, symbol: str, market: str | None = None) -> str:
        raw = str(symbol or "").strip().upper().replace("/", "")
        if ":" in raw:
            return raw
        market_norm = self._normalize_chart_market(market)
        prefix = TRADINGVIEW_SYMBOL_PREFIX
        try:
            account_text = (self.account_combo.currentText() or "").strip().lower()
            if "bybit" in account_text:
                prefix = "BYBIT:"
            elif "spot" in account_text:
                prefix = "BINANCE:"
            elif "future" in account_text:
                prefix = "BINANCE:"
        except Exception:
            prefix = TRADINGVIEW_SYMBOL_PREFIX
        return f"{prefix}{raw}"

    def _show_chart_status(self, message: str, color: str = "#d1d4dc"):
        if not getattr(self, "chart_enabled", False):
            return
        view = getattr(self, "chart_view", None)
        if QT_CHARTS_AVAILABLE and isinstance(view, QChartView):
            chart = QChart()
            chart.setBackgroundBrush(QtGui.QBrush(QtGui.QColor("#0b0e11")))
            try:
                chart.legend().hide()
            except Exception:
                pass
            try:
                text_item = QtWidgets.QGraphicsSimpleTextItem(str(message), chart)
                text_item.setBrush(QtGui.QBrush(QtGui.QColor(color)))
                text_item.setPos(12, 12)
            except Exception:
                try:
                    chart.setTitle(str(message))
                    chart.setTitleBrush(QtGui.QBrush(QtGui.QColor(color)))
                except Exception:
                    pass
            view.setChart(chart)
            return
        bw_view = getattr(self, "chart_binance", None)
        if bw_view is not None and view is bw_view:
            try:
                bw_view.show_message(message, color=color)
            except Exception:
                pass
            return
        lw_view = getattr(self, "chart_lightweight", None)
        if lw_view is not None and view is lw_view:
            try:
                lw_view.show_message(message, color=color)
            except Exception:
                pass
            return
        tv_view = getattr(self, "chart_tradingview", None)
        if tv_view is not None and view is tv_view:
            try:
                tv_view.show_message(message, color=color)
            except Exception:
                pass
        elif isinstance(view, SimpleCandlestickWidget):
            view.set_message(message, color=color)

    def _render_candlestick_chart(self, symbol: str, interval_code: str, candles: list[dict]):
        if not getattr(self, "chart_enabled", False):
            return
        view = getattr(self, "chart_view", None)
        if QT_CHARTS_AVAILABLE and isinstance(view, QChartView):
            if not candles:
                self._show_chart_status("No data available.", color="#f75467")
                return
            chart = QChart()
            chart.setTitle(f"{symbol} - {interval_code}")
            chart.setBackgroundBrush(QtGui.QBrush(QtGui.QColor("#0b0e11")))
            chart.setAnimationOptions(QChart.AnimationOption.NoAnimation)
            try:
                chart.legend().hide()
            except Exception:
                pass

            series = QCandlestickSeries()
            try:
                series.setIncreasingColor(QtGui.QColor("#0ebb7a"))
                series.setDecreasingColor(QtGui.QColor("#f75467"))
            except Exception:
                pass

            lows: list[float] = []
            highs: list[float] = []
            for candle in candles:
                try:
                    open_ = float(candle.get("open", 0.0))
                    high = float(candle.get("high", 0.0))
                    low = float(candle.get("low", 0.0))
                    close = float(candle.get("close", 0.0))
                    timestamp = float(candle.get("time", 0.0)) * 1000.0
                except Exception:
                    continue
                set_item = QCandlestickSet(open_, high, low, close, timestamp)
                series.append(set_item)
                lows.append(low)
                highs.append(high)

            if not lows or not highs:
                self._show_chart_status("No data available.", color="#f75467")
                return

            chart.addSeries(series)

            axis_x = QDateTimeAxis()
            axis_x.setFormat("dd.MM HH:mm")
            axis_x.setLabelsColor(QtGui.QColor("#d1d4dc"))
            axis_x.setTitleText("Time")
            chart.addAxis(axis_x, QtCore.Qt.AlignmentFlag.AlignBottom)
            series.attachAxis(axis_x)
            try:
                axis_x.setRange(
                    QtCore.QDateTime.fromSecsSinceEpoch(int(candles[0]["time"])),
                    QtCore.QDateTime.fromSecsSinceEpoch(int(candles[-1]["time"])),
                )
            except Exception:
                pass

            axis_y = QValueAxis()
            axis_y.setLabelFormat("%.2f")
            axis_y.setTitleText("Price")
            axis_y.setLabelsColor(QtGui.QColor("#d1d4dc"))
            chart.addAxis(axis_y, QtCore.Qt.AlignmentFlag.AlignLeft)
            series.attachAxis(axis_y)
            try:
                axis_y.setRange(min(lows), max(highs))
            except Exception:
                pass

            chart.setMargins(QtCore.QMargins(8, 8, 8, 8))
            view.setChart(chart)
        elif isinstance(view, SimpleCandlestickWidget):
            if not candles:
                view.set_message("No data available.", color="#f75467")
            else:
                view.set_candles(candles)
        else:
            return

    def _build_lightweight_payload(
        self,
        df: pd.DataFrame,
        times: list[int],
        candles: list[dict],
        indicators_cfg: dict,
        theme_name: str,
    ) -> dict:
        theme_code = "light" if str(theme_name or "").lower().startswith("light") else "dark"

        def _series_from_values(values) -> list[dict]:
            data = []
            for t_val, v_val in zip(times, values):
                try:
                    if v_val is None or pd.isna(v_val):
                        continue
                    data.append({"time": int(t_val), "value": float(v_val)})
                except Exception:
                    continue
            return data

        def _add_overlay(key: str, label: str, data: list[dict], color: str, line_style: int = 0, line_width: int = 2):
            if not data:
                return
            overlays.append({
                "key": key,
                "label": label,
                "type": "line",
                "data": data,
                "color": color,
                "lineStyle": int(line_style),
                "lineWidth": int(line_width),
            })

        def _add_pane(key: str, label: str, series: list[dict], height: int = 80):
            if not series:
                return
            panes.append({
                "key": key,
                "label": label,
                "height": int(height),
                "series": series,
            })

        overlays: list[dict] = []
        panes: list[dict] = []

        volume_series = []
        try:
            opens = df["open"].tolist()
            closes = df["close"].tolist()
            volumes = df["volume"].tolist()
            for t_val, o_val, c_val, v_val in zip(times, opens, closes, volumes):
                if v_val is None or pd.isna(v_val):
                    continue
                color = "#0ebb7a" if float(c_val) >= float(o_val) else "#f75467"
                volume_series.append({"time": int(t_val), "value": float(v_val), "color": color})
        except Exception:
            volume_series = []

        indicators_cfg = indicators_cfg or {}
        enabled_map = {
            str(k).strip().lower(): v for k, v in (indicators_cfg or {}).items()
            if isinstance(v, dict) and v.get("enabled")
        }

        if enabled_map.get("volume"):
            _add_pane("volume", INDICATOR_DISPLAY_NAMES.get("volume", "Volume"), [
                {"type": "histogram", "data": volume_series, "color": "#94a3b8", "priceFormat": {"type": "volume"}},
            ], height=90)

        if enabled_map.get("ma"):
            cfg = enabled_map.get("ma", {})
            length = int(cfg.get("length") or 20)
            ma_type = str(cfg.get("type") or "SMA").strip().upper()
            if ma_type == "EMA":
                series = ema_indicator(df["close"], length)
                label = f"EMA({length})"
                color = "#38bdf8"
            else:
                series = sma_indicator(df["close"], length)
                label = f"SMA({length})"
                color = "#f59e0b"
            _add_overlay("ma", label, _series_from_values(series.tolist()), color)

        if enabled_map.get("ema"):
            cfg = enabled_map.get("ema", {})
            length = int(cfg.get("length") or 20)
            series = ema_indicator(df["close"], length)
            _add_overlay("ema", f"EMA({length})", _series_from_values(series.tolist()), "#22c55e")

        if enabled_map.get("bb"):
            cfg = enabled_map.get("bb", {})
            length = int(cfg.get("length") or 20)
            std = float(cfg.get("std") or 2)
            upper, mid, lower = bollinger_bands_indicator(df, length=length, std=std)
            _add_overlay("bb_upper", f"BB Upper({length})", _series_from_values(upper.tolist()), "#60a5fa", line_style=2)
            _add_overlay("bb_mid", f"BB Mid({length})", _series_from_values(mid.tolist()), "#fbbf24")
            _add_overlay("bb_lower", f"BB Lower({length})", _series_from_values(lower.tolist()), "#60a5fa", line_style=2)

        if enabled_map.get("donchian"):
            cfg = enabled_map.get("donchian", {})
            length = int(cfg.get("length") or 20)
            high_series = donchian_high_indicator(df, length)
            low_series = donchian_low_indicator(df, length)
            _add_overlay("donchian_high", f"DC High({length})", _series_from_values(high_series.tolist()), "#f59e0b", line_style=2)
            _add_overlay("donchian_low", f"DC Low({length})", _series_from_values(low_series.tolist()), "#22c55e", line_style=2)

        if enabled_map.get("psar"):
            cfg = enabled_map.get("psar", {})
            af = float(cfg.get("af") or 0.02)
            max_af = float(cfg.get("max_af") or 0.2)
            psar_series = psar_indicator(df, af=af, max_af=max_af)
            _add_overlay("psar", "PSAR", _series_from_values(psar_series.tolist()), "#f472b6", line_style=1)

        if enabled_map.get("supertrend"):
            cfg = enabled_map.get("supertrend", {})
            atr_period = int(cfg.get("atr_period") or 10)
            multiplier = float(cfg.get("multiplier") or 3.0)
            st_delta = supertrend_indicator(df, atr_period=atr_period, multiplier=multiplier)
            try:
                st_line = df["close"] - st_delta
            except Exception:
                st_line = st_delta
            _add_overlay("supertrend", "SuperTrend", _series_from_values(st_line.tolist()), "#a855f7", line_style=2)

        if enabled_map.get("rsi"):
            cfg = enabled_map.get("rsi", {})
            length = int(cfg.get("length") or 14)
            series = rsi_indicator(df["close"], length=length)
            _add_pane("rsi", INDICATOR_DISPLAY_NAMES.get("rsi", "RSI"), [
                {"type": "line", "data": _series_from_values(series.tolist()), "color": "#f97316"},
            ])

        if enabled_map.get("stoch_rsi"):
            cfg = enabled_map.get("stoch_rsi", {})
            length = int(cfg.get("length") or 14)
            smooth_k = int(cfg.get("smooth_k") or 3)
            smooth_d = int(cfg.get("smooth_d") or 3)
            k_series, d_series = stoch_rsi_indicator(df["close"], length=length, smooth_k=smooth_k, smooth_d=smooth_d)
            _add_pane("stoch_rsi", INDICATOR_DISPLAY_NAMES.get("stoch_rsi", "Stoch RSI"), [
                {"type": "line", "data": _series_from_values(k_series.tolist()), "color": "#22c55e"},
                {"type": "line", "data": _series_from_values(d_series.tolist()), "color": "#ef4444"},
            ])

        if enabled_map.get("willr"):
            cfg = enabled_map.get("willr", {})
            length = int(cfg.get("length") or 14)
            series = williams_r_indicator(df, length=length)
            _add_pane("willr", INDICATOR_DISPLAY_NAMES.get("willr", "Williams %R"), [
                {"type": "line", "data": _series_from_values(series.tolist()), "color": "#60a5fa"},
            ])

        if enabled_map.get("macd"):
            cfg = enabled_map.get("macd", {})
            fast = int(cfg.get("fast") or 12)
            slow = int(cfg.get("slow") or 26)
            signal = int(cfg.get("signal") or 9)
            macd_line, signal_line, hist = macd_indicator(df["close"], fast=fast, slow=slow, signal=signal)
            _add_pane("macd", INDICATOR_DISPLAY_NAMES.get("macd", "MACD"), [
                {"type": "line", "data": _series_from_values(macd_line.tolist()), "color": "#22c55e"},
                {"type": "line", "data": _series_from_values(signal_line.tolist()), "color": "#ef4444"},
                {"type": "histogram", "data": _series_from_values(hist.tolist()), "color": "#94a3b8"},
            ])

        if enabled_map.get("uo"):
            cfg = enabled_map.get("uo", {})
            short = int(cfg.get("short") or 7)
            medium = int(cfg.get("medium") or 14)
            long = int(cfg.get("long") or 28)
            series = uo_indicator(df, short=short, medium=medium, long=long)
            _add_pane("uo", INDICATOR_DISPLAY_NAMES.get("uo", "Ultimate Oscillator"), [
                {"type": "line", "data": _series_from_values(series.tolist()), "color": "#8b5cf6"},
            ])

        if enabled_map.get("adx"):
            cfg = enabled_map.get("adx", {})
            length = int(cfg.get("length") or 14)
            series = adx_indicator(df, length=length)
            _add_pane("adx", INDICATOR_DISPLAY_NAMES.get("adx", "ADX"), [
                {"type": "line", "data": _series_from_values(series.tolist()), "color": "#f59e0b"},
            ])

        if enabled_map.get("dmi"):
            cfg = enabled_map.get("dmi", {})
            length = int(cfg.get("length") or 14)
            plus_di, minus_di, adx_series = dmi_indicator(df, length=length)
            _add_pane("dmi", INDICATOR_DISPLAY_NAMES.get("dmi", "DMI"), [
                {"type": "line", "data": _series_from_values(plus_di.tolist()), "color": "#22c55e"},
                {"type": "line", "data": _series_from_values(minus_di.tolist()), "color": "#ef4444"},
                {"type": "line", "data": _series_from_values(adx_series.tolist()), "color": "#f59e0b"},
            ])

        if enabled_map.get("stochastic"):
            cfg = enabled_map.get("stochastic", {})
            length = int(cfg.get("length") or 14)
            smooth_k = int(cfg.get("smooth_k") or 3)
            smooth_d = int(cfg.get("smooth_d") or 3)
            k_series, d_series = stochastic_indicator(df, length=length, smooth_k=smooth_k, smooth_d=smooth_d)
            _add_pane("stochastic", INDICATOR_DISPLAY_NAMES.get("stochastic", "Stochastic"), [
                {"type": "line", "data": _series_from_values(k_series.tolist()), "color": "#22c55e"},
                {"type": "line", "data": _series_from_values(d_series.tolist()), "color": "#ef4444"},
            ])

        return {
            "candles": candles,
            "volume": volume_series if enabled_map.get("volume") else [],
            "overlays": overlays,
            "panes": panes,
            "theme": theme_code,
        }

    def _on_chart_theme_changed(self, *_args):
        if not getattr(self, "chart_enabled", False):
            return
        view = getattr(self, "chart_view", None)
        tv_view = getattr(self, "chart_tradingview", None)
        if tv_view is not None and view is tv_view:
            try:
                theme_name = (self.theme_combo.currentText() or "").strip()
            except Exception:
                theme_name = self.config.get("theme", "Dark")
            try:
                tv_view.apply_theme(theme_name)
            except Exception:
                pass
            return
        lw_view = getattr(self, "chart_lightweight", None)
        if lw_view is not None and view is lw_view:
            try:
                theme_name = (self.theme_combo.currentText() or "").strip()
            except Exception:
                theme_name = self.config.get("theme", "Dark")
            theme_code = "light" if str(theme_name or "").lower().startswith("light") else "dark"
            try:
                lw_view.set_chart_data({"theme": theme_code})
            except Exception:
                pass

    def _on_dashboard_selection_for_chart(self):
        if self.chart_auto_follow:
            self._apply_dashboard_selection_to_chart(load=True)

    def _is_chart_visible(self):
        if not getattr(self, "chart_enabled", False):
            return False
        try:
            tabs = getattr(self, "tabs", None)
            chart_tab = getattr(self, "chart_tab", None)
            if tabs is None or chart_tab is None:
                return False
            return tabs.currentWidget() is chart_tab
        except Exception:
            return False

    def _on_tab_changed(self, index: int):
        try:
            widget = self.tabs.widget(index)
        except Exception:
            return
        if widget is getattr(self, "chart_tab", None):
            try:
                combo_mode = self.chart_view_mode_combo.currentData()
            except Exception:
                combo_mode = None
            if not combo_mode:
                try:
                    combo_mode = self.chart_view_mode_combo.currentText()
                except Exception:
                    combo_mode = ""
            combo_mode = str(combo_mode or "").strip().lower()
            try:
                env_disable = str(os.environ.get("BOT_DISABLE_WEBENGINE_CHARTS", "")).strip()
                env_safe = str(os.environ.get("BOT_SAFE_CHART_TAB", "")).strip()
                tv_flag = str(os.environ.get("BOT_TRADINGVIEW_WINDOW_SUPPRESS", "")).strip()
                self._chart_debug_log(
                    f"chart_tab_selected mode={combo_mode} webengine_allowed={int(_webengine_charts_allowed())} "
                    f"safe_mode={int(_chart_safe_mode_enabled())} disable_env={env_disable!r} "
                    f"safe_env={env_safe!r} tv_suppress={tv_flag!r}"
                )
            except Exception:
                pass
            if _chart_safe_mode_enabled() and combo_mode in {"tradingview", "original", "lightweight"}:
                try:
                    self._chart_debug_log("chart_tab_safe_mode_redirect=1")
                except Exception:
                    pass
                if combo_mode == "tradingview":
                    opened = False
                    try:
                        opened = self._open_tradingview_external()
                    except Exception:
                        opened = False
                    if opened:
                        self._show_chart_status(
                            "TradingView opened in your browser. Set BOT_SAFE_CHART_TAB=0 to embed.",
                            color="#94a3b8",
                        )
                    else:
                        self._show_chart_status(
                            "TradingView embed disabled. Set BOT_SAFE_CHART_TAB=0 to embed.",
                            color="#f59e0b",
                        )
                else:
                    self._show_chart_status(
                        "Web charts disabled for stability. Set BOT_SAFE_CHART_TAB=0 to enable.",
                        color="#f59e0b",
                    )
                legacy = self._chart_view_widgets.get("legacy")
                if legacy is not None:
                    try:
                        self.chart_view = legacy
                        idx = self.chart_view_stack.indexOf(legacy)
                        if idx >= 0:
                            self.chart_view_stack.setCurrentIndex(idx)
                    except Exception:
                        pass
                if self._chart_needs_render or self._chart_pending_initial_load:
                    self.load_chart(auto=True)
                self._chart_pending_initial_load = False
                return
            if self._pending_tradingview_mode:
                # On Windows, do not auto-initialize TradingView/QtWebEngine just because the
                # chart tab becomes visible; it can spawn multiple helper windows that flash.
                # Users can still opt in by selecting "TradingView" in the view-mode combo.
                allow_tradingview_init = sys.platform != "win32"
                if not allow_tradingview_init:
                    allow_flag = str(os.environ.get("BOT_ALLOW_TRADINGVIEW_WINDOWS", "")).strip().lower()
                    allow_tradingview_init = allow_flag in {"1", "true", "yes", "on"}
                self._apply_chart_view_mode("tradingview", allow_tradingview_init=allow_tradingview_init)
            pending_web = getattr(self, "_pending_webengine_mode", None)
            if pending_web:
                self._pending_webengine_mode = None
                self._apply_chart_view_mode(str(pending_web), allow_tradingview_init=True)
            if getattr(self, "_pending_tradingview_switch", False):
                self._on_tradingview_ready()
            if self._chart_pending_initial_load:
                self.load_chart(auto=True)
            elif self.chart_auto_follow:
                self._apply_dashboard_selection_to_chart(load=True)
            elif self._chart_needs_render:
                self.load_chart(auto=True)
            self._chart_pending_initial_load = False
        elif widget is getattr(self, "liquidation_tab", None):
            pass
        elif widget is getattr(self, "code_tab", None):
            if not getattr(self, "_dep_version_auto_refresh_done", False):
                self._dep_version_auto_refresh_done = True
                QtCore.QTimer.singleShot(100, self._refresh_dependency_versions)

    def load_chart(self, auto: bool = False):
        if not getattr(self, "chart_enabled", False):
            return
        try:
            self._chart_debug_log(f"load_chart auto={int(bool(auto))}")
        except Exception:
            pass
        # Throttle auto refreshes to avoid spamming TradingView reloads (which are heavy).
        try:
            now_ts = time.monotonic()
            last_ts = float(getattr(self, "_last_chart_load_ts", 0.0) or 0.0)
            min_gap = 5.0 if auto else 0.0
            if auto and now_ts - last_ts < min_gap:
                return
        except Exception:
            pass
        view = getattr(self, "chart_view", None)
        if view is None:
            if not auto:
                self.log("Charts unavailable: install PyQt6-Charts for visualization.")
            self._show_chart_status("Charts unavailable.", color="#f75467")
            return
        try:
            symbol_text = (self.chart_symbol_combo.currentText() or "").strip().upper()
            interval_text = (self.chart_interval_combo.currentText() or "").strip()
        except Exception:
            if not auto:
                self.log("Chart: unable to read current selection.")
            return
        if not symbol_text:
            if not auto:
                self.log("Chart: please choose a symbol.")
            return
        if not interval_text:
            if not auto:
                self.log("Chart: please choose an interval.")
            return
        interval_code = self._map_chart_interval(interval_text)
        if not interval_code:
            if not auto:
                self.log(f"Chart: unsupported interval '{interval_text}'.")
            return
        market_text = self._normalize_chart_market(self.chart_market_combo.currentText() if hasattr(self, "chart_market_combo") else None)
        api_symbol = self._resolve_chart_symbol_for_api(symbol_text, market_text)

        existing_worker = getattr(self, "_chart_worker", None)
        if existing_worker and existing_worker.isRunning():
            try:
                existing_worker.requestInterruption()
            except Exception:
                pass
        self._chart_worker = None

        tv_view = getattr(self, "chart_tradingview", None)
        if tv_view is not None and view is tv_view:
            try:
                theme_name = (self.theme_combo.currentText() or "").strip()
            except Exception:
                theme_name = self.config.get("theme", "Dark")
            tv_symbol = self._format_chart_symbol(symbol_text, market_text)
            theme_code = "light" if str(theme_name or "").lower().startswith("light") else "dark"
            self._chart_pending_initial_load = False
            try:
                tv_view.set_chart(tv_symbol, interval_code, theme=theme_code, timezone="Etc/UTC")
                try:
                    self._last_chart_load_ts = time.monotonic()
                except Exception:
                    pass
                self.chart_config["symbol"] = symbol_text
                self.chart_config["interval"] = interval_text
                self.chart_config["market"] = market_text
                self.chart_config["auto_follow"] = bool(self.chart_auto_follow and market_text == "Futures")
                self._chart_needs_render = False
            except Exception as exc:
                self._chart_needs_render = True
                if not auto:
                    self.log(f"Chart load failed: {exc}")
                try:
                    tv_view.show_message("Failed to load TradingView chart.", color="#f75467")
                except Exception:
                    pass
            return

        bw_view = getattr(self, "chart_binance", None)
        if bw_view is not None and view is bw_view:
            try:
                self._chart_pending_initial_load = False
                bw_view.set_chart(symbol_text, interval_text, market_text)
                try:
                    self._last_chart_load_ts = time.monotonic()
                except Exception:
                    pass
                self.chart_config["symbol"] = symbol_text
                self.chart_config["interval"] = interval_text
                self.chart_config["market"] = market_text
                self.chart_config["auto_follow"] = bool(self.chart_auto_follow and market_text == "Futures")
                self._chart_needs_render = False
            except Exception as exc:
                self._chart_needs_render = True
                if not auto:
                    self.log(f"Chart load failed: {exc}")
                try:
                    bw_view.show_message("Failed to load Binance chart.", color="#f75467")
                except Exception:
                    pass
            return

        lw_view = getattr(self, "chart_lightweight", None)
        is_lightweight = lw_view is not None and view is lw_view

        if not is_lightweight and not QT_CHARTS_AVAILABLE and not isinstance(view, SimpleCandlestickWidget):
            if not auto:
                self.log("Charts unavailable: install PyQt6-Charts for visualization.")
            self._show_chart_status("Charts unavailable.", color="#f75467")
            return
        account_type = "Futures" if market_text == "Futures" else "Spot"
        api_key = self.api_key_edit.text().strip() if hasattr(self, "api_key_edit") else ""
        api_secret = self.api_secret_edit.text().strip() if hasattr(self, "api_secret_edit") else ""
        mode = self.mode_combo.currentText() if hasattr(self, "mode_combo") else "Live"
        indicators_cfg = copy.deepcopy(self.config.get("indicators", {}) or {})
        try:
            theme_name = (self.theme_combo.currentText() or "").strip()
        except Exception:
            theme_name = self.config.get("theme", "Dark")

        def _do():
            thread = QtCore.QThread.currentThread()
            if thread.isInterruptionRequested():
                return None
            wrapper = self._create_binance_wrapper(
                api_key=api_key,
                api_secret=api_secret,
                mode=mode,
                account_type=account_type,
            )
            try:
                wrapper.indicator_source = self.ind_source_combo.currentText()
            except Exception:
                pass
            df = wrapper.get_klines(api_symbol, interval_text, limit=400)
            if df is None or df.empty:
                raise RuntimeError("no_kline_data")
            df = df.tail(400)
            candles = []
            times = []
            index_used = []
            for ts, row in df.iterrows():
                if thread.isInterruptionRequested():
                    return None
                try:
                    dt = ts.to_pydatetime()
                except Exception:
                    dt = ts
                if not isinstance(dt, datetime):
                    continue
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.astimezone(timezone.utc)
                epoch = int(dt.timestamp())
                try:
                    candles.append({
                        "time": epoch,
                        "open": float(row.get('open', 0.0)),
                        "high": float(row.get('high', 0.0)),
                        "low": float(row.get('low', 0.0)),
                        "close": float(row.get('close', 0.0)),
                    })
                    times.append(epoch)
                    index_used.append(ts)
                except Exception:
                    continue
            if thread.isInterruptionRequested():
                return None
            if not candles:
                raise RuntimeError("no_valid_candles")
            if is_lightweight:
                df_used = df.loc[index_used] if index_used else df
                payload = self._build_lightweight_payload(
                    df_used,
                    times,
                    candles,
                    indicators_cfg,
                    theme_name,
                )
                return {"candles": candles, "payload": payload}
            return {"candles": candles}

        def _done(res, err, worker_ref=None):
            if worker_ref is not getattr(self, "_chart_worker", None):
                return
            self._chart_worker = None
            self._chart_pending_initial_load = False
            if err or not isinstance(res, dict):
                self._chart_needs_render = True
                if not auto and err:
                    self.log(f"Chart load failed: {err}")
                self._show_chart_status("Failed to load chart data.", color="#f75467")
                return
            candles = res.get("candles") or []
            if is_lightweight and lw_view is not None:
                payload = res.get("payload") or {}
                try:
                    if payload:
                        lw_view.set_chart_data(payload)
                except Exception as exc:
                    if not auto:
                        self.log(f"Chart load failed: {exc}")
                    self._show_chart_status("Failed to load lightweight chart.", color="#f75467")
                    return
            else:
                self._render_candlestick_chart(symbol_text, interval_code, candles)
            try:
                self._last_chart_load_ts = time.monotonic()
            except Exception:
                pass
            self.chart_config["symbol"] = symbol_text
            self.chart_config["interval"] = interval_text
            self.chart_config["market"] = market_text
            self.chart_config["auto_follow"] = bool(self.chart_auto_follow and market_text == "Futures")
            self._chart_needs_render = False

        self._show_chart_status("Loading chart...", color="#d1d4dc")
        self._chart_needs_render = True
        worker = CallWorker(_do, parent=self)
        self._chart_worker = worker
        try:
            worker.progress.connect(self.log)
        except Exception:
            pass
        worker.done.connect(lambda res, err, w=worker: _done(res, err, worker_ref=w))
        worker.start()

    def init_ui(self):
        self.setWindowTitle("Trading Bot")
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
        tab1_layout.addWidget(self.dashboard_scroll)

        scroll_contents = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_contents)
        scroll_layout.setContentsMargins(10, 10, 10, 10)
        scroll_layout.setSpacing(10)
        self.dashboard_scroll.setWidget(scroll_contents)

        # Top grid
        grid = QtWidgets.QGridLayout()

        grid.addWidget(QtWidgets.QLabel("API Key:"), 0, 0)
        self.api_key_edit = QtWidgets.QLineEdit(self.config['api_key'])
        grid.addWidget(self.api_key_edit, 0, 1)

        grid.addWidget(QtWidgets.QLabel("API Secret Key:"), 1, 0)
        self.api_secret_edit = QtWidgets.QLineEdit(self.config['api_secret'])
        self.api_secret_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        grid.addWidget(self.api_secret_edit, 1, 1)
        self.api_key_edit.editingFinished.connect(self._on_api_credentials_changed)
        self.api_secret_edit.editingFinished.connect(self._on_api_credentials_changed)

        grid.addWidget(QtWidgets.QLabel("Mode:"), 0, 2)
        self.mode_combo = QtWidgets.QComboBox()
        mode_options = [
            "Live",
            "Demo",
            "Testnet",
        ]
        self.mode_combo.addItems(mode_options)
        loaded_mode = self.config.get('mode', 'Live') or 'Live'
        # Backward compatibility for legacy label
        if loaded_mode == "Demo/Testnet":
            loaded_mode = "Demo"
        if loaded_mode == "Futures WebSocket (live market data)":
            loaded_mode = "Live"
        if loaded_mode == "Testnet WebSocket":
            loaded_mode = "Testnet"
        if loaded_mode not in mode_options:
            loaded_mode = "Live"
        self.mode_combo.setCurrentText(loaded_mode)
        grid.addWidget(self.mode_combo, 0, 3)
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)

        grid.addWidget(QtWidgets.QLabel("Theme:"), 0, 4)
        self.theme_combo = QtWidgets.QComboBox()
        self.theme_combo.addItems(["Light", "Dark", "Blue", "Yellow", "Green", "Red"])
        current_theme = (self.config.get("theme") or "Dark").title()
        if current_theme not in {"Light", "Dark", "Blue", "Yellow", "Green", "Red"}:
            current_theme = "Dark"
        self.theme_combo.setCurrentText(current_theme)
        self.theme_combo.currentTextChanged.connect(self.apply_theme)
        grid.addWidget(self.theme_combo, 0, 5)

        status_widget = QtWidgets.QWidget()
        status_layout = QtWidgets.QHBoxLayout(status_widget)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(10)
        self.pnl_active_label_tab1 = QtWidgets.QLabel()
        self.pnl_closed_label_tab1 = QtWidgets.QLabel()
        self.bot_status_label_tab1 = QtWidgets.QLabel()
        self.bot_time_label_tab1 = QtWidgets.QLabel("Bot Active Time: --")
        for lbl in (self.pnl_active_label_tab1, self.pnl_closed_label_tab1):
            lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
            status_layout.addWidget(lbl)
        status_layout.addStretch()
        for lbl in (self.bot_status_label_tab1, self.bot_time_label_tab1):
            lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
            status_layout.addWidget(lbl)
        self._register_pnl_summary_labels(self.pnl_active_label_tab1, self.pnl_closed_label_tab1)
        grid.addWidget(status_widget, 0, 6, 1, 4)

        grid.addWidget(QtWidgets.QLabel("Account Type:"), 1, 2)
        self.account_combo = QtWidgets.QComboBox()
        self.account_combo.addItems(["Spot", "Futures"])
        self.account_combo.setCurrentText(self.config.get('account_type', 'Futures'))
        grid.addWidget(self.account_combo, 1, 3)
        self.account_combo.currentTextChanged.connect(self._on_account_type_changed)

        grid.addWidget(QtWidgets.QLabel("Account Mode:"), 1, 4)
        self.account_mode_combo = QtWidgets.QComboBox()
        for mode in ACCOUNT_MODE_OPTIONS:
            self.account_mode_combo.addItem(mode, mode)
        account_mode_cfg = self._normalize_account_mode(self.config.get("account_mode", ACCOUNT_MODE_OPTIONS[0]))
        idx_account_mode = self.account_mode_combo.findData(account_mode_cfg)
        if idx_account_mode < 0:
            idx_account_mode = 0
        self.account_mode_combo.setCurrentIndex(idx_account_mode)
        self.account_mode_combo.currentIndexChanged.connect(self._on_runtime_account_mode_changed)
        self.config["account_mode"] = account_mode_cfg
        self._apply_runtime_account_mode_constraints(account_mode_cfg)
        grid.addWidget(self.account_mode_combo, 1, 5)

        grid.addWidget(QtWidgets.QLabel("Connector:"), 1, 6)
        self.connector_combo = QtWidgets.QComboBox()
        current_account_type = self.config.get("account_type", "Futures")
        account_key = "FUTURES" if str(current_account_type or "Futures").strip().lower().startswith("fut") else "SPOT"
        allowed_backends = FUTURES_CONNECTOR_KEYS if account_key == "FUTURES" else SPOT_CONNECTOR_KEYS
        for label, value in CONNECTOR_OPTIONS:
            if value in allowed_backends:
                self.connector_combo.addItem(label, value)
        runtime_backend = self._ensure_runtime_connector_for_account(current_account_type, force_default=False)
        idx_connector = self.connector_combo.findData(runtime_backend)
        if idx_connector < 0 and self.connector_combo.count():
            idx_connector = 0
        if self.connector_combo.count():
            self.connector_combo.setCurrentIndex(idx_connector)
        self.connector_combo.currentIndexChanged.connect(self._on_runtime_connector_changed)
        grid.addWidget(self.connector_combo, 1, 7, 1, 3)

        grid.addWidget(QtWidgets.QLabel("Total USDT balance:"), 2, 0)
        self.balance_label = QtWidgets.QLabel("N/A")
        grid.addWidget(self.balance_label, 2, 1)
        self.pos_mode_label = QtWidgets.QLabel("Position Mode: N/A")
        grid.addWidget(self.pos_mode_label, 2, 6, 1, 2)
        self.refresh_balance_btn = QtWidgets.QPushButton("Refresh Balance")
        self.refresh_balance_btn.clicked.connect(lambda: self.update_balance_label())
        grid.addWidget(self.refresh_balance_btn, 2, 2)

        grid.addWidget(QtWidgets.QLabel("Leverage (Futures):"), 2, 3)
        self.leverage_spin = QtWidgets.QSpinBox()
        self.leverage_spin.setRange(1, 150)
        self.leverage_spin.setValue(self.config.get('leverage', 5))
        self.leverage_spin.valueChanged.connect(self.on_leverage_changed)
        grid.addWidget(self.leverage_spin, 2, 4)
        self._update_leverage_enabled()

        grid.addWidget(QtWidgets.QLabel("Margin Mode (Futures):"), 2, 5)
        self.margin_mode_combo = QtWidgets.QComboBox()
        self.margin_mode_combo.addItems(["Cross", "Isolated"])
        self.margin_mode_combo.setCurrentText(self.config.get('margin_mode', 'Isolated'))
        grid.addWidget(self.margin_mode_combo, 2, 6)
        self._apply_runtime_account_mode_constraints(self.config.get("account_mode", ACCOUNT_MODE_OPTIONS[0]))

        grid.addWidget(QtWidgets.QLabel("Position Mode:"), 2, 7)
        self.position_mode_combo = QtWidgets.QComboBox()
        self.position_mode_combo.addItems(["One-way", "Hedge"])
        self.position_mode_combo.setCurrentText(self.config.get("position_mode", "Hedge"))
        grid.addWidget(self.position_mode_combo, 2, 8)

        grid.addWidget(QtWidgets.QLabel("Assets Mode:"), 2, 9)
        self.assets_mode_combo = QtWidgets.QComboBox()
        self.assets_mode_combo.addItem("Single-Asset Mode", "Single-Asset")
        self.assets_mode_combo.addItem("Multi-Assets Mode", "Multi-Assets")
        assets_mode_cfg = self._normalize_assets_mode(self.config.get("assets_mode", "Single-Asset"))
        idx_assets = self.assets_mode_combo.findData(assets_mode_cfg)
        if idx_assets < 0:
            idx_assets = 0
        self.assets_mode_combo.setCurrentIndex(idx_assets)
        grid.addWidget(self.assets_mode_combo, 2, 10)

        grid.addWidget(QtWidgets.QLabel("Time-in-Force:"), 3, 2)
        self.tif_combo = QtWidgets.QComboBox()
        self.tif_combo.addItems(["GTC", "IOC", "FOK", "GTD"])
        self.tif_combo.setCurrentText(self.config.get("tif", "GTC"))
        grid.addWidget(self.tif_combo, 3, 3)
        self.gtd_minutes_spin = QtWidgets.QSpinBox()
        self.gtd_minutes_spin.setRange(1, 1440)
        self.gtd_minutes_spin.setValue(self.config.get("gtd_minutes", 30))
        self.gtd_minutes_spin.setSuffix(" min (GTD)")
        self.gtd_minutes_spin.setEnabled(False)
        self.gtd_minutes_spin.setReadOnly(True)
        try:
            self.gtd_minutes_spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
        except Exception:
            pass
        grid.addWidget(self.gtd_minutes_spin, 3, 4)
        # Show GTD minutes only when TIF == 'GTD'
        def _update_gtd_visibility(text:str):
            is_gtd = (text == 'GTD')
            # Keep visible but disable when not GTD
            self.gtd_minutes_spin.setEnabled(is_gtd)
            self.gtd_minutes_spin.setReadOnly(not is_gtd)
            try:
                self.gtd_minutes_spin.setButtonSymbols(
                    QtWidgets.QAbstractSpinBox.ButtonSymbols.UpDownArrows if is_gtd else QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons
                )
            except Exception:
                pass
        self.tif_combo.currentTextChanged.connect(_update_gtd_visibility)
        _update_gtd_visibility(self.tif_combo.currentText())

        grid.addWidget(QtWidgets.QLabel("Indicator Source:"), 3, 0)
        self.ind_source_combo = QtWidgets.QComboBox()
        self.ind_source_combo.addItems([
            "Binance spot",
            "Binance futures",
            "TradingView",
            "Bybit",
            "Coinbase",
            "OKX",
            "Gate",
            "Bitget",
            "Mexc",
            "Kucoin",
            "HTX",
            "Kraken",
        ])
        self.ind_source_combo.setCurrentText(self.config.get("indicator_source", "Binance futures"))
        grid.addWidget(self.ind_source_combo, 3, 1, 1, 2)

        self._on_account_type_changed(self.account_combo.currentText())

        scroll_layout.addLayout(grid)

        exchange_group = QtWidgets.QGroupBox("Exchange")
        exchange_layout = QtWidgets.QVBoxLayout(exchange_group)
        exchange_layout.setContentsMargins(12, 10, 12, 10)
        exchange_layout.setSpacing(6)
        exchange_label = QtWidgets.QLabel("Select exchange")
        exchange_layout.addWidget(exchange_label)
        self.exchange_combo = QtWidgets.QComboBox()
        exchange_layout.addWidget(self.exchange_combo)
        exchange_options = [opt for opt in STARTER_CRYPTO_EXCHANGES if opt["key"] in EXCHANGE_PATHS]
        enabled_exchanges = []
        for opt in exchange_options:
            item_text = opt["title"]
            badge = opt.get("badge")
            if badge:
                item_text = f"{item_text} ({badge})"
            self.exchange_combo.addItem(item_text, opt["key"])
            idx = self.exchange_combo.count() - 1
            if opt.get("disabled", False):
                item = self.exchange_combo.model().item(idx)
                if item is not None:
                    item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEnabled)
                    item.setForeground(QtGui.QColor("#6b7280"))
            else:
                enabled_exchanges.append(opt["key"])
        selected_exchange = self.config.get("selected_exchange")
        if selected_exchange not in enabled_exchanges:
            selected_exchange = enabled_exchanges[0] if enabled_exchanges else None
            if selected_exchange:
                self.config["selected_exchange"] = selected_exchange
        if selected_exchange:
            idx = self.exchange_combo.findData(selected_exchange)
            if idx >= 0:
                with QtCore.QSignalBlocker(self.exchange_combo):
                    self.exchange_combo.setCurrentIndex(idx)
        self.exchange_combo.currentIndexChanged.connect(
            lambda _=None: self._on_exchange_selection_changed(self.exchange_combo.currentData())
        )
        scroll_layout.addWidget(exchange_group)

        # Markets & Intervals
        sym_group = QtWidgets.QGroupBox("Markets & Intervals")
        sgrid = QtWidgets.QGridLayout(sym_group)

        sgrid.addWidget(QtWidgets.QLabel("Symbols (select 1 or more):"), 0, 0)
        self.symbol_list = QtWidgets.QListWidget()
        self.symbol_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        self.symbol_list.setMinimumHeight(260)
        self.symbol_list.itemSelectionChanged.connect(self._reconfigure_positions_worker)
        self.symbol_list.itemSelectionChanged.connect(self._on_dashboard_selection_for_chart)
        sgrid.addWidget(self.symbol_list, 1, 0, 4, 2)

        self.refresh_symbols_btn = QtWidgets.QPushButton("Refresh Symbols")
        self.refresh_symbols_btn.clicked.connect(self.refresh_symbols)
        sgrid.addWidget(self.refresh_symbols_btn, 5, 0, 1, 2)

        sgrid.addWidget(QtWidgets.QLabel("Intervals (select 1 or more):"), 0, 2)
        self.interval_list = QtWidgets.QListWidget()
        self.interval_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        self.interval_list.setMinimumHeight(260)
        for it in CHART_INTERVAL_OPTIONS:
            self.interval_list.addItem(QtWidgets.QListWidgetItem(it))
        self.interval_list.itemSelectionChanged.connect(self._on_dashboard_selection_for_chart)
        sgrid.addWidget(self.interval_list, 1, 2, 3, 2)

        self.custom_interval_edit = QtWidgets.QLineEdit()
        self.custom_interval_edit.setPlaceholderText("e.g., 45s or 7m or 90m, comma-separated")
        self.add_interval_btn = QtWidgets.QPushButton("Add Custom Interval(s)")
        def _add_custom_intervals():
            txt = self.custom_interval_edit.text().strip()
            if not txt:
                return
            parts = [p.strip() for p in txt.split(",") if p.strip()]
            existing = set(self.interval_list.item(i).text() for i in range(self.interval_list.count()))
            source = (self.ind_source_combo.currentText() or '').strip().lower() if hasattr(self, 'ind_source_combo') else ''
            is_binance_source = 'binance' in source
            for p in parts:
                norm = p.strip()
                key = norm.lower()
                if is_binance_source and key not in BINANCE_SUPPORTED_INTERVALS:
                    self.log(f"Skipping unsupported Binance interval '{norm}'.")
                    continue
                if norm not in existing:
                    self.interval_list.addItem(QtWidgets.QListWidgetItem(norm))
                    existing.add(norm)
            self.custom_interval_edit.clear()
        self.add_interval_btn.clicked.connect(_add_custom_intervals)
        sgrid.addWidget(self.custom_interval_edit, 4, 2)
        sgrid.addWidget(self.add_interval_btn, 4, 3)
        scroll_layout.addWidget(sym_group)

        runtime_override_group = self._create_override_group("runtime", self.symbol_list, self.interval_list)

        # Strategy Controls
        strat_group = QtWidgets.QGroupBox("Strategy Controls")
        g = QtWidgets.QGridLayout(strat_group)

        g.addWidget(QtWidgets.QLabel("Side:"), 0, 0)
        self.side_combo = QtWidgets.QComboBox()
        self.side_combo.addItems([SIDE_LABELS["BUY"], SIDE_LABELS["SELL"], SIDE_LABELS["BOTH"]])
        current_side = (self.config.get("side", "BOTH") or "BOTH").upper()
        label = SIDE_LABELS.get(current_side, SIDE_LABELS["BOTH"])
        idx = self.side_combo.findText(label, QtCore.Qt.MatchFlag.MatchFixedString) if hasattr(QtCore.Qt, "MatchFlag") else self.side_combo.findText(label)
        if idx >= 0:
            self.side_combo.setCurrentIndex(idx)
        else:
            self.side_combo.setCurrentIndex(2)
        self.config["side"] = self._resolve_dashboard_side()
        self.side_combo.currentTextChanged.connect(lambda _=None: self.config.__setitem__("side", self._resolve_dashboard_side()))
        g.addWidget(self.side_combo, 0, 1)

        g.addWidget(QtWidgets.QLabel("Position % of Balance:"), 0, 2)
        self.pospct_spin = QtWidgets.QDoubleSpinBox()
        self.pospct_spin.setRange(0.01, 100.0)
        self.pospct_spin.setDecimals(2)
        # Show as percentage 0..100; config can be 0..1 or 0..100
        initial_pct = float(self.config.get("position_pct", 2.0))
        if initial_pct <= 1.0:
            initial_pct *= 100.0
        self.pospct_spin.setValue(initial_pct)
        g.addWidget(self.pospct_spin, 0, 3)

        g.addWidget(QtWidgets.QLabel("Loop Interval Override:"), 0, 4)
        self.loop_combo = QtWidgets.QComboBox()
        for label, value in DASHBOARD_LOOP_CHOICES:
            self.loop_combo.addItem(label, value)
        initial_loop = self._normalize_loop_override(self.config.get("loop_interval_override"))
        if not initial_loop:
            initial_loop = "1m"
        self.config["loop_interval_override"] = initial_loop
        if initial_loop and self.loop_combo.findData(initial_loop) < 0:
            self.loop_combo.addItem(initial_loop, initial_loop)
        idx_loop = self.loop_combo.findData(initial_loop)
        if idx_loop < 0:
            idx_loop = 0
        self.loop_combo.setCurrentIndex(idx_loop)
        self.loop_combo.currentIndexChanged.connect(self._on_runtime_loop_changed)
        g.addWidget(self.loop_combo, 0, 5)

        # Lead trader controls
        self.lead_trader_enable_cb = QtWidgets.QCheckBox("Enable Lead Trader")
        lead_trader_enabled = bool(self.config.get("lead_trader_enabled", False))
        self.lead_trader_enable_cb.setChecked(lead_trader_enabled)

        self.lead_trader_combo = QtWidgets.QComboBox()
        for label, value in LEAD_TRADER_OPTIONS:
            self.lead_trader_combo.addItem(label, value)
        lead_trader_choice = self.config.get("lead_trader_profile") or LEAD_TRADER_OPTIONS[0][1]
        idx_lead_trader = self.lead_trader_combo.findData(lead_trader_choice)
        if idx_lead_trader < 0:
            idx_lead_trader = 0
        self.lead_trader_combo.setCurrentIndex(idx_lead_trader)
        self.config["lead_trader_profile"] = str(self.lead_trader_combo.itemData(idx_lead_trader))
        self.lead_trader_combo.setMaximumWidth(260)
        try:
            self.lead_trader_combo.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Fixed,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
        except Exception:
            pass

        lead_trader_row = QtWidgets.QWidget()
        lead_trader_layout = QtWidgets.QHBoxLayout(lead_trader_row)
        lead_trader_layout.setContentsMargins(0, 0, 0, 0)
        lead_trader_layout.setSpacing(12)
        lead_trader_layout.addWidget(self.lead_trader_enable_cb)
        lead_trader_layout.addWidget(self.lead_trader_combo)
        lead_trader_layout.addStretch(1)
        g.addWidget(lead_trader_row, 1, 0, 1, 6)

        self.lead_trader_enable_cb.toggled.connect(self._on_lead_trader_toggled)
        self.lead_trader_combo.currentIndexChanged.connect(self._on_lead_trader_option_changed)

        self.cb_live_indicator_values = QtWidgets.QCheckBox("Use live candle values for signals (repaints)")
        live_values_enabled = bool(self.config.get("indicator_use_live_values", False))
        self.config["indicator_use_live_values"] = live_values_enabled
        self.cb_live_indicator_values.setChecked(live_values_enabled)
        self.cb_live_indicator_values.setToolTip(
            "When unchecked, signals use the previous closed candle (no repaint), which matches candle-close backtests "
            "and TradingView values on bar close."
        )
        self.cb_live_indicator_values.stateChanged.connect(
            lambda state: self.config.__setitem__(
                "indicator_use_live_values", bool(state == QtCore.Qt.CheckState.Checked)
            )
        )
        g.addWidget(self.cb_live_indicator_values, 2, 0, 1, 6)

        # Add-only (One-way guard) option
        self.cb_add_only = QtWidgets.QCheckBox("Add-only in current net direction (one-way)")
        self.cb_add_only.setChecked(bool(self.config.get('add_only', False)))
        g.addWidget(self.cb_add_only, 3, 0, 1, 6)

        self.allow_opposite_checkbox = QtWidgets.QCheckBox("Allow simultaneous long & short positions (hedge stacking)")
        allow_opposite_enabled = coerce_bool(self.config.get("allow_opposite_positions", True), True)
        self.config["allow_opposite_positions"] = allow_opposite_enabled
        self.allow_opposite_checkbox.setChecked(allow_opposite_enabled)
        self.allow_opposite_checkbox.setToolTip(
            "When enabled, the bot may keep both long and short positions open at the same time if hedge mode is active. "
            "Leave disabled to force the bot to close the opposite side before opening a new trade."
        )
        self.allow_opposite_checkbox.stateChanged.connect(self._on_allow_opposite_changed)
        g.addWidget(self.allow_opposite_checkbox, 4, 0, 1, 6)

        self.cb_stop_without_close = QtWidgets.QCheckBox("Stop Bot Without Closing Active Positions")
        stop_without_close = bool(self.config.get("stop_without_close", False))
        self.cb_stop_without_close.setChecked(stop_without_close)
        self.cb_stop_without_close.setToolTip(
            "When checked, the Stop button will halt strategy threads but leave all open positions untouched."
        )
        self.cb_stop_without_close.stateChanged.connect(
            lambda state: self.config.__setitem__("stop_without_close", bool(state == QtCore.Qt.CheckState.Checked))
        )
        g.addWidget(self.cb_stop_without_close, 5, 0, 1, 6)

        self.cb_close_on_exit = QtWidgets.QCheckBox("Market Close All Active Positions On Window Close (Working in progress)")
        self.cb_close_on_exit.setChecked(False)
        self.cb_close_on_exit.setEnabled(False)
        self.cb_close_on_exit.setCheckable(False)
        try:
            self.cb_close_on_exit.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        except Exception:
            pass
        try:
            pal = self.cb_close_on_exit.palette()
            disabled_color = pal.color(QtGui.QPalette.ColorGroup.Disabled, QtGui.QPalette.ColorRole.Text)
            pal.setColor(QtGui.QPalette.ColorRole.WindowText, disabled_color)
            self.cb_close_on_exit.setPalette(pal)
            # Also dim the box itself
            pal.setColor(QtGui.QPalette.ColorRole.ButtonText, disabled_color)
            pal.setColor(QtGui.QPalette.ColorRole.Text, disabled_color)
            self.cb_close_on_exit.setPalette(pal)
            self.cb_close_on_exit.setStyleSheet("color: #5a5f70;")
        except Exception:
            pass
        self.cb_close_on_exit.setToolTip("Disabled while improvements are in progress.")
        # Keep config off even if previous sessions stored True
        self.config["close_on_exit"] = False
        self.cb_close_on_exit.stateChanged.connect(self._on_close_on_exit_changed)
        g.addWidget(self.cb_close_on_exit, 6, 0, 1, 6)

        self._apply_lead_trader_state(lead_trader_enabled)

        stop_cfg = normalize_stop_loss_dict(self.config.get("stop_loss"))
        self.config["stop_loss"] = stop_cfg

        g.addWidget(QtWidgets.QLabel("Stop Loss:"), 7, 0)
        self.stop_loss_enable_cb = QtWidgets.QCheckBox("Enable")
        self.stop_loss_enable_cb.setToolTip("Toggle automatic stop-loss handling for live trades.")
        self.stop_loss_enable_cb.setChecked(stop_cfg.get("enabled", False))
        g.addWidget(self.stop_loss_enable_cb, 7, 1)

        self.stop_loss_mode_combo = QtWidgets.QComboBox()
        for mode_key in STOP_LOSS_MODE_ORDER:
            self.stop_loss_mode_combo.addItem(STOP_LOSS_MODE_LABELS.get(mode_key, mode_key.title()), mode_key)
        mode_idx = self.stop_loss_mode_combo.findData(stop_cfg.get("mode"))
        if mode_idx < 0:
            mode_idx = 0
        self.stop_loss_mode_combo.setCurrentIndex(mode_idx)
        g.addWidget(self.stop_loss_mode_combo, 7, 2, 1, 2)

        self.stop_loss_usdt_spin = QtWidgets.QDoubleSpinBox()
        self.stop_loss_usdt_spin.setRange(0.0, 1_000_000_000.0)
        self.stop_loss_usdt_spin.setDecimals(2)
        self.stop_loss_usdt_spin.setSingleStep(1.0)
        self.stop_loss_usdt_spin.setSuffix(" USDT")
        self.stop_loss_usdt_spin.setValue(float(stop_cfg.get("usdt", 0.0)))
        g.addWidget(self.stop_loss_usdt_spin, 7, 4)

        self.stop_loss_percent_spin = QtWidgets.QDoubleSpinBox()
        self.stop_loss_percent_spin.setRange(0.0, 100.0)
        self.stop_loss_percent_spin.setDecimals(2)
        self.stop_loss_percent_spin.setSingleStep(0.5)
        self.stop_loss_percent_spin.setSuffix(" %")
        self.stop_loss_percent_spin.setValue(float(stop_cfg.get("percent", 0.0)))
        g.addWidget(self.stop_loss_percent_spin, 7, 5)

        self.stop_loss_scope_combo = QtWidgets.QComboBox()
        for scope_key in STOP_LOSS_SCOPE_OPTIONS:
            label = STOP_LOSS_SCOPE_LABELS.get(scope_key, scope_key.replace("_", " ").title())
            self.stop_loss_scope_combo.addItem(label, scope_key)
        scope_idx = self.stop_loss_scope_combo.findData(stop_cfg.get("scope"))
        if scope_idx < 0:
            scope_idx = 0
        self.stop_loss_scope_combo.setCurrentIndex(scope_idx)
        g.addWidget(QtWidgets.QLabel("Stop Loss Scope:"), 8, 0)
        g.addWidget(self.stop_loss_scope_combo, 8, 1, 1, 2)

        # Strategy templates
        self._dashboard_templates = {
            "top10": {
                "label": "Top 10 %2 per trade 5x Isolated",
                "position_pct": 2.0,
                "leverage": 5,
                "margin_mode": "Isolated",
                "indicators": {
                    "rsi": {"enabled": True, "buy_value": 30, "sell_value": 70},
                    "stoch_rsi": {"enabled": True, "buy_value": 20, "sell_value": 80},
                    "willr": {"enabled": True, "buy_value": -80, "sell_value": -20},
                },
            },
            "top50": {
                "label": "Top 50 %2 per trade 20x",
                "position_pct": 2.0,
                "leverage": 20,
                "margin_mode": "Isolated",
                "indicators": {
                    "rsi": {"enabled": True, "buy_value": 30, "sell_value": 70},
                    "stoch_rsi": {"enabled": True, "buy_value": 20, "sell_value": 80},
                    "willr": {"enabled": True, "buy_value": -80, "sell_value": -20},
                },
            },
            "top100": {
                "label": "Top 100 %1 per trade 5x",
                "position_pct": 1.0,
                "leverage": 5,
                "margin_mode": "Isolated",
                "indicators": {
                    "rsi": {"enabled": True, "buy_value": 30, "sell_value": 70},
                    "stoch_rsi": {"enabled": True, "buy_value": 20, "sell_value": 80},
                    "willr": {"enabled": True, "buy_value": -80, "sell_value": -20},
                },
            },
        }
        g.addWidget(QtWidgets.QLabel("Template:"), 9, 0)
        self.template_combo = QtWidgets.QComboBox()
        self.template_combo.addItem("No Template", "")
        for key, info in self._dashboard_templates.items():
            self.template_combo.addItem(info["label"], key)
        current_template = str(self.config.get("dashboard_template") or "")
        idx_template = self.template_combo.findData(current_template)
        if idx_template < 0:
            idx_template = 0
        self.template_combo.setCurrentIndex(idx_template)
        self.template_combo.currentIndexChanged.connect(self._on_dashboard_template_changed)
        g.addWidget(self.template_combo, 9, 1, 1, 3)

        self.stop_loss_enable_cb.toggled.connect(self._on_runtime_stop_loss_enabled)
        self.stop_loss_mode_combo.currentIndexChanged.connect(self._on_runtime_stop_loss_mode_changed)
        self.stop_loss_usdt_spin.valueChanged.connect(lambda v: self._on_runtime_stop_loss_value_changed("usdt", v))
        self.stop_loss_percent_spin.valueChanged.connect(lambda v: self._on_runtime_stop_loss_value_changed("percent", v))
        self.stop_loss_scope_combo.currentTextChanged.connect(lambda _: self._on_runtime_stop_loss_scope_changed())
        self._update_runtime_stop_loss_widgets()

        scroll_layout.addWidget(strat_group)

        # Indicators
        ind_group = QtWidgets.QGroupBox("Indicators")
        il = QtWidgets.QGridLayout(ind_group)

        self._indicator_runtime_controls = []
        row = 0
        for key, params in self.config['indicators'].items():
            label = INDICATOR_DISPLAY_NAMES.get(key, key)
            cb = QtWidgets.QCheckBox(label)
            cb.setProperty('indicator_key', key)
            cb.setChecked(bool(params.get("enabled", False)))
            def make_toggle_handler(_key=key):
                def _toggle(checked):
                    self._on_indicator_toggled(_key, checked)
                return _toggle
            cb.toggled.connect(make_toggle_handler())
            btn = QtWidgets.QPushButton("Buy-Sell Values")
            def make_handler(_key=key, _params=params):
                def handler():
                    dlg = ParamDialog(_key, _params, self, display_name=INDICATOR_DISPLAY_NAMES.get(_key, _key))
                    if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
                        self.config['indicators'][_key].update(dlg.get_params())
                        self.indicator_widgets[_key][0].setChecked(bool(self.config['indicators'][_key].get("enabled", False)))
                return handler
            btn.clicked.connect(make_handler())
            il.addWidget(cb, row, 0)
            il.addWidget(btn, row, 1)
            self.indicator_widgets[key] = (cb, btn)
            self._indicator_runtime_controls.extend([cb, btn])
            row += 1

        scroll_layout.addWidget(ind_group)

        scroll_layout.addWidget(runtime_override_group)

        # Buttons
        btn_layout = QtWidgets.QHBoxLayout()
        self.start_btn = QtWidgets.QPushButton("Start")
        self.start_btn.clicked.connect(self.start_strategy)
        btn_layout.addWidget(self.start_btn)
        self.stop_btn = QtWidgets.QPushButton("Stop")
        self.stop_btn.clicked.connect(
            lambda checked=False: self.stop_strategy_async(
                close_positions=not bool(self.cb_stop_without_close.isChecked())
            )
        )
        self.stop_btn.setEnabled(False)
        btn_layout.addWidget(self.stop_btn)
        self.save_btn = QtWidgets.QPushButton("Save Config")
        self.save_btn.clicked.connect(self.save_config)
        btn_layout.addWidget(self.save_btn)
        self.load_btn = QtWidgets.QPushButton("Load Config")
        self.load_btn.clicked.connect(self.load_config)
        btn_layout.addWidget(self.load_btn)
        scroll_layout.addLayout(btn_layout)

        self._runtime_lock_widgets = [
            self.api_key_edit,
            self.api_secret_edit,
            self.mode_combo,
            self.theme_combo,
            self.account_combo,
            self.account_mode_combo,
            self.connector_combo,
            self.leverage_spin,
            self.margin_mode_combo,
            self.position_mode_combo,
            self.assets_mode_combo,
            self.tif_combo,
            self.gtd_minutes_spin,
            self.ind_source_combo,
            self.symbol_list,
            self.refresh_symbols_btn,
            self.interval_list,
            self.custom_interval_edit,
            self.add_interval_btn,
            self.side_combo,
            self.pospct_spin,
            self.loop_combo,
            self.lead_trader_enable_cb,
            self.lead_trader_combo,
            self.cb_live_indicator_values,
            self.cb_add_only,
            self.allow_opposite_checkbox,
            self.cb_stop_without_close,
            self.cb_close_on_exit,
            self.stop_loss_enable_cb,
            self.stop_loss_mode_combo,
            self.stop_loss_usdt_spin,
            self.stop_loss_percent_spin,
            self.stop_loss_scope_combo,
            self.template_combo,
            self.start_btn,
            self.save_btn,
            self.load_btn
        ] + list(self._indicator_runtime_controls)
        self._set_runtime_controls_enabled(True)


        # Log
        self.log_tab_widget = QtWidgets.QTabWidget()
        try:
            self.log_tab_widget.setDocumentMode(True)
        except Exception:
            pass
        self.log_all_edit = QtWidgets.QPlainTextEdit()
        self.log_all_edit.setReadOnly(True)
        self.log_all_edit.setMinimumHeight(220)
        try:
            self.log_all_edit.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)
        except Exception:
            pass
        try:
            self.log_all_edit.document().setMaximumBlockCount(1000)
        except Exception:
            pass
        self.log_tab_widget.addTab(self.log_all_edit, "All Logs")
        self.log_triggers_edit = QtWidgets.QPlainTextEdit()
        self.log_triggers_edit.setReadOnly(True)
        self.log_triggers_edit.setMinimumHeight(220)
        try:
            self.log_triggers_edit.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)
        except Exception:
            pass
        try:
            self.log_triggers_edit.document().setMaximumBlockCount(1000)
        except Exception:
            pass
        self.log_tab_widget.addTab(self.log_triggers_edit, "Position Trigger Logs")
        self.waiting_pos_table = QtWidgets.QTableWidget(0, 6)
        self.waiting_pos_table.setHorizontalHeaderLabels([
            "Symbol",
            "Interval",
            "Side",
            "Context",
            "State",
            "Age (s)",
        ])
        self.waiting_pos_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.waiting_pos_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        self.waiting_pos_table.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        try:
            self.waiting_pos_table.setPlaceholderText("No waiting positions")
        except Exception:
            pass
        header_waiting = self.waiting_pos_table.horizontalHeader()
        try:
            header_waiting.setStretchLastSection(True)
            header_waiting.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        except Exception:
            pass
        try:
            self.waiting_pos_table.verticalHeader().setVisible(False)
        except Exception:
            pass
        self.log_tab_widget.addTab(self.waiting_pos_table, "Waiting Positions (Queue)")
        self._waiting_positions_history = []
        self._waiting_positions_last_snapshot = {}
        try:
            self._waiting_positions_history_max = int(self.config.get("waiting_positions_history_max", 500) or 500)
        except Exception:
            self._waiting_positions_history_max = 500
        try:
            self.log_tab_widget.setCurrentIndex(0)
        except Exception:
            pass
        self.log_edit = self.log_all_edit
        scroll_layout.addWidget(self.log_tab_widget)
        self.waiting_positions_timer = QtCore.QTimer(self)
        self.waiting_positions_timer.setInterval(1000)
        self.waiting_positions_timer.timeout.connect(self._refresh_waiting_positions_tab)
        self.waiting_positions_timer.start()
        self._refresh_waiting_positions_tab()

        self.tabs.addTab(tab1, "Dashboard")

        if self.chart_enabled:
            chart_tab = self._create_chart_tab()
            self.tabs.addTab(chart_tab, "Chart")
            try:
                self._runtime_lock_widgets.extend([
                    self.chart_market_combo,
                    self.chart_symbol_combo,
                    self.chart_interval_combo,
                    self.chart_view_mode_combo,
                ])
                for widget in (self.chart_market_combo, self.chart_symbol_combo, self.chart_interval_combo, self.chart_view_mode_combo):
                    self._register_runtime_active_exemption(widget)
            except Exception:
                pass
            if self.chart_auto_follow:
                self._apply_dashboard_selection_to_chart(load=False)
            elif QT_CHARTS_AVAILABLE:
                try:
                    self.load_chart(auto=True)
                except Exception:
                    pass
        else:
            self.chart_tab = None
            self.chart_view = None
            self.chart_view_stack = None
            self.chart_tradingview = None
            self.chart_binance = None
            self.chart_lightweight = None
            self.chart_original_view = None
        self._entry_intervals = {}
        self._entry_times = {}  # (sym, 'L'/'S') -> last trade time string
        self._entry_times_by_iv = {}
        
        # Try to load persisted allocation data for interval/indicator column persistence
        _persisted_mode = None
        try:
            _mode_text = self.mode_combo.currentText() if hasattr(self, 'mode_combo') else None
            _persisted_mode = _mode_text
        except Exception:
            pass
        _loaded_allocations, _loaded_records = _load_position_allocations(mode=_persisted_mode)
        self._entry_allocations = _loaded_allocations or {}
        self._pending_close_times = {}
        self._open_position_records = _loaded_records or {}
        self._closed_position_records = []
        self._engine_indicator_map = {}
        self._live_indicator_cache: dict[tuple[str, str], dict] = {}
        try:
            ttl_value = float(self.config.get("positions_live_indicator_refresh_seconds", 8.0) or 8.0)
            self._live_indicator_cache_ttl = max(2.0, ttl_value)
        except Exception:
            self._live_indicator_cache_ttl = 8.0
        self._live_indicator_cache_last_cleanup = time.monotonic()
        self._positions_view_mode = "cumulative"
        # Retain a larger closed-history buffer so per-trade view can show prior legs.
        try:
            global MAX_CLOSED_HISTORY  # allow runtime override from config
            cfg_max_hist = int(self.config.get("positions_closed_history_max", 500) or 500)
            from .gui_consts import MAX_CLOSED_HISTORY as _GUI_MAX_HIST  # type: ignore
            MAX_CLOSED_HISTORY = max(_GUI_MAX_HIST, cfg_max_hist)  # noqa: N806
        except Exception:
            try:
                MAX_CLOSED_HISTORY = max(MAX_CLOSED_HISTORY, 500)  # type: ignore # noqa: N806,F821
            except Exception:
                MAX_CLOSED_HISTORY = 500  # type: ignore # noqa: N806,F821
        try:
            self._pos_refresh_interval_ms = int(self.config.get("positions_refresh_interval_ms", 5000) or 5000)
        except Exception:
            self._pos_refresh_interval_ms = 5000


        # ---------------- Positions tab ----------------
        tab2 = QtWidgets.QWidget()
        tab2_layout = QtWidgets.QVBoxLayout(tab2)

        ctrl_layout = QtWidgets.QHBoxLayout()
        self.refresh_pos_btn = QtWidgets.QPushButton("Refresh Positions")
        self.refresh_pos_btn.clicked.connect(self.refresh_positions)
        ctrl_layout.addWidget(self.refresh_pos_btn)
        self.close_all_btn = QtWidgets.QPushButton("Market Close ALL Positions")
        self.close_all_btn.clicked.connect(self.close_all_positions_async)
        ctrl_layout.addWidget(self.close_all_btn)
        ctrl_layout.addWidget(QtWidgets.QLabel("Positions View:"))
        self.positions_view_combo = QtWidgets.QComboBox()
        self.positions_view_combo.addItems(["Cumulative View", "Per Trade View"])
        self.positions_view_combo.setCurrentIndex(0)
        self.positions_view_combo.currentIndexChanged.connect(self._on_positions_view_changed)
        ctrl_layout.addWidget(self.positions_view_combo)
        self.positions_auto_resize_checkbox = QtWidgets.QCheckBox("Auto Row Height")
        self.positions_auto_resize_checkbox.setToolTip("Resize rows to fit multi-line indicator values.")
        self.positions_auto_resize_checkbox.setChecked(
            coerce_bool(self.config.get("positions_auto_resize_rows", True), True)
        )
        self.positions_auto_resize_checkbox.stateChanged.connect(self._on_positions_auto_resize_changed)
        ctrl_layout.addWidget(self.positions_auto_resize_checkbox)
        self.positions_auto_resize_columns_checkbox = QtWidgets.QCheckBox("Auto Column Width")
        self.positions_auto_resize_columns_checkbox.setToolTip("Resize columns to fit full indicator text.")
        self.positions_auto_resize_columns_checkbox.setChecked(
            coerce_bool(self.config.get("positions_auto_resize_columns", True), True)
        )
        self.positions_auto_resize_columns_checkbox.stateChanged.connect(
            self._on_positions_auto_resize_columns_changed
        )
        ctrl_layout.addWidget(self.positions_auto_resize_columns_checkbox)
        ctrl_layout.addStretch()
        tab2_layout.addLayout(ctrl_layout)

        tab2_status_widget = QtWidgets.QWidget()
        tab2_status_widget.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        tab2_status_layout = QtWidgets.QHBoxLayout(tab2_status_widget)
        tab2_status_layout.setContentsMargins(0, 0, 0, 0)
        tab2_status_layout.setSpacing(12)
        self.pnl_active_label_tab2 = QtWidgets.QLabel()
        self.pnl_closed_label_tab2 = QtWidgets.QLabel()
        self.positions_total_balance_label = QtWidgets.QLabel("Total Balance: --")
        self.positions_available_balance_label = QtWidgets.QLabel("Available Balance: --")
        self.bot_status_label_tab2 = QtWidgets.QLabel()
        self.bot_time_label_tab2 = QtWidgets.QLabel("Bot Active Time: --")
        for lbl in (
            self.pnl_active_label_tab2,
            self.pnl_closed_label_tab2,
            self.positions_total_balance_label,
            self.positions_available_balance_label,
        ):
            lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
            lbl.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Preferred,
            )
            tab2_status_layout.addWidget(lbl)
        tab2_status_layout.addStretch()
        for lbl in (self.bot_status_label_tab2, self.bot_time_label_tab2):
            lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
            lbl.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Minimum,
                QtWidgets.QSizePolicy.Policy.Preferred,
            )
            tab2_status_layout.addWidget(lbl)
        self._register_pnl_summary_labels(self.pnl_active_label_tab2, self.pnl_closed_label_tab2)
        self._update_positions_balance_labels(None, None)
        tab2_layout.addWidget(tab2_status_widget)
        self._sync_runtime_state()

        self.pos_table = QtWidgets.QTableWidget(0, POS_CLOSE_COLUMN + 1, tab2)
        self.pos_table.setHorizontalHeaderLabels([
            "Symbol",
            "Size (USDT)",
            "Last Price (USDT)",
            "Margin Ratio",
            "Liq Price (USDT)",
            "Margin (USDT)",
            "Quantity (Qty)",
            "PNL (ROI%)",
            "Interval",
            "Indicator",
            "Triggered Indicator Value",
            "Current Indicator Value",
            "Side",
            "Open Time",
            "Close Time",
            "Stop-Loss",
            "Status",
            "Close",
        ])
        pos_header = self.pos_table.horizontalHeader()
        pos_header.setStretchLastSection(True)
        try:
            pos_header.setSectionsMovable(True)
        except Exception:
            pass
        self.pos_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        try:
            self.pos_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        except Exception:
            self.pos_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.pos_table.setSortingEnabled(True)
        self.pos_table.setWordWrap(True)
        try:
            self.pos_table.setTextElideMode(QtCore.Qt.TextElideMode.ElideNone)
        except Exception:
            pass
        try:
            self.pos_table.verticalHeader().setDefaultSectionSize(44)
        except Exception:
            pass
        tab2_layout.addWidget(self.pos_table)

        pos_btn_layout = QtWidgets.QHBoxLayout()
        self.pos_clear_selected_btn = QtWidgets.QPushButton("Clear Selected")
        self.pos_clear_selected_btn.clicked.connect(self._clear_positions_selected)
        pos_btn_layout.addWidget(self.pos_clear_selected_btn)
        self.pos_clear_all_btn = QtWidgets.QPushButton("Clear All")
        self.pos_clear_all_btn.clicked.connect(self._clear_positions_all)
        pos_btn_layout.addWidget(self.pos_clear_all_btn)
        pos_btn_layout.addStretch()
        tab2_layout.addLayout(pos_btn_layout)

        self.tabs.addTab(tab2, "Positions")

        # Background positions worker (keeps UI thread snappy)
        self._pos_thread = QtCore.QThread(self)
        self._pos_worker = _PositionsWorker(
            self.api_key_edit.text().strip(),
            self.api_secret_edit.text().strip(),
            self.mode_combo.currentText(),
            self.account_combo.currentText(),
            connector_backend=self._runtime_connector_backend(suppress_refresh=True),
        )
        # Wire thread-safe control signals
        self.req_pos_start.connect(self._pos_worker.start_with_interval)
        self.req_pos_stop.connect(self._pos_worker.stop_timer)
        self.req_pos_set_interval.connect(self._pos_worker.set_interval)
        self._pos_worker.moveToThread(self._pos_thread)
        self._pos_worker.positions_ready.connect(self._on_positions_ready)
        self._pos_worker.error.connect(lambda e: self.log(f"Positions worker: {e}"))
        try:
            self._reconfigure_positions_worker()
        except Exception:
            pass
        
        self._pos_thread.start()
        # adjust worker refresh interval
        try:
            self._apply_positions_refresh_settings()
        except Exception:
            pass

        # ---------------- Backtest tab ----------------
        tab3 = QtWidgets.QWidget()
        tab3_layout = QtWidgets.QVBoxLayout(tab3)
        tab3_scroll_area = QtWidgets.QScrollArea(tab3)
        tab3_scroll_area.setWidgetResizable(True)
        tab3_scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tab3_layout.addWidget(tab3_scroll_area)
        tab3_scroll_widget = QtWidgets.QWidget()
        tab3_scroll_area.setWidget(tab3_scroll_widget)
        tab3_content_layout = QtWidgets.QVBoxLayout(tab3_scroll_widget)
        tab3_content_layout.setContentsMargins(12, 12, 12, 12)
        tab3_content_layout.setSpacing(16)

        top_layout = QtWidgets.QHBoxLayout()
        top_layout.setSpacing(16)

        market_group = QtWidgets.QGroupBox("Markets")
        market_group.setMinimumWidth(320)
        market_group.setMaximumWidth(620)
        market_group.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        market_layout = QtWidgets.QGridLayout(market_group)

        market_layout.addWidget(QtWidgets.QLabel("Symbol Source:"), 0, 0)
        self.backtest_symbol_source_combo = QtWidgets.QComboBox()
        self.backtest_symbol_source_combo.addItems(["Futures", "Spot"])
        self.backtest_symbol_source_combo.currentTextChanged.connect(self._backtest_symbol_source_changed)
        market_layout.addWidget(self.backtest_symbol_source_combo, 0, 1)
        self.backtest_refresh_symbols_btn = QtWidgets.QPushButton("Refresh")
        self.backtest_refresh_symbols_btn.clicked.connect(self._refresh_backtest_symbols)
        market_layout.addWidget(self.backtest_refresh_symbols_btn, 0, 2)

        market_layout.addWidget(QtWidgets.QLabel("Symbols (select 1 or more):"), 1, 0, 1, 3)
        self.backtest_symbol_list = QtWidgets.QListWidget()
        self.backtest_symbol_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        size_policy_symbols = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Expanding)
        size_policy_symbols.setHorizontalStretch(0)
        size_policy_symbols.setVerticalStretch(1)
        self.backtest_symbol_list.setSizePolicy(size_policy_symbols)
        self.backtest_symbol_list.setMinimumWidth(200)
        self.backtest_symbol_list.setMaximumWidth(260)
        self.backtest_symbol_list.itemSelectionChanged.connect(self._backtest_store_symbols)
        market_layout.addWidget(self.backtest_symbol_list, 2, 0, 4, 3)

        market_layout.addWidget(QtWidgets.QLabel("Intervals (select 1 or more):"), 1, 3)
        self.backtest_interval_list = QtWidgets.QListWidget()
        self.backtest_interval_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        size_policy_intervals = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Expanding)
        size_policy_intervals.setHorizontalStretch(0)
        size_policy_intervals.setVerticalStretch(1)
        self.backtest_interval_list.setSizePolicy(size_policy_intervals)
        self.backtest_interval_list.setMinimumWidth(160)
        self.backtest_interval_list.setMaximumWidth(240)
        self.backtest_interval_list.itemSelectionChanged.connect(self._backtest_store_intervals)
        market_layout.addWidget(self.backtest_interval_list, 2, 3, 4, 2)

        self.backtest_custom_interval_edit = QtWidgets.QLineEdit()
        self.backtest_custom_interval_edit.setPlaceholderText("e.g., 45s or 7m or 90m, comma-separated")
        self.backtest_custom_interval_edit.setMaximumWidth(240)
        market_layout.addWidget(self.backtest_custom_interval_edit, 6, 3)
        self.backtest_add_interval_btn = QtWidgets.QPushButton("Add Custom Interval(s)")
        market_layout.addWidget(self.backtest_add_interval_btn, 6, 4)

        def _add_backtest_custom_intervals():
            text = self.backtest_custom_interval_edit.text().strip()
            if not text:
                return
            parts = [p.strip() for p in text.split(",") if p.strip()]
            if not parts:
                self.backtest_custom_interval_edit.clear()
                return
            existing = {self.backtest_interval_list.item(i).text() for i in range(self.backtest_interval_list.count())}
            new_items = []
            for part in parts:
                norm = part.strip()
                if not norm or norm in existing:
                    continue
                item = QtWidgets.QListWidgetItem(norm)
                self.backtest_interval_list.addItem(item)
                item.setSelected(True)
                existing.add(norm)
                new_items.append(item)
            self.backtest_custom_interval_edit.clear()
            if new_items:
                self._backtest_store_intervals()

        self.backtest_add_interval_btn.clicked.connect(_add_backtest_custom_intervals)

        pair_group = self._create_override_group("backtest", self.backtest_symbol_list, self.backtest_interval_list)
        market_layout.addWidget(pair_group, 7, 0, 1, 5)


        market_layout.setColumnStretch(0, 2)
        market_layout.setColumnStretch(1, 1)
        market_layout.setColumnStretch(2, 1)
        market_layout.setColumnStretch(3, 1)
        market_layout.setColumnStretch(4, 1)

        top_layout.addWidget(market_group, 3)

        param_group = QtWidgets.QGroupBox("Backtest Parameters")
        param_group.setMinimumWidth(520)
        param_group.setMaximumWidth(820)
        param_group.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        param_form = QtWidgets.QFormLayout(param_group)
        param_form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        param_form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)

        self.backtest_start_edit = QtWidgets.QDateTimeEdit()
        self.backtest_start_edit.setCalendarPopup(True)
        self.backtest_start_edit.setDisplayFormat("dd.MM.yyyy HH:mm:ss")
        self.backtest_end_edit = QtWidgets.QDateTimeEdit()
        self.backtest_end_edit.setCalendarPopup(True)
        self.backtest_end_edit.setDisplayFormat("dd.MM.yyyy HH:mm:ss")
        self.backtest_start_edit.dateTimeChanged.connect(self._backtest_dates_changed)
        self.backtest_end_edit.dateTimeChanged.connect(self._backtest_dates_changed)

        param_form.addRow("Start Date/Time:", self.backtest_start_edit)
        param_form.addRow("End Date/Time:", self.backtest_end_edit)

        self.backtest_logic_combo = QtWidgets.QComboBox()
        self.backtest_logic_combo.addItems(["AND", "OR", "SEPARATE"])
        self.backtest_logic_combo.currentTextChanged.connect(lambda v: self._update_backtest_config("logic", v))
        param_form.addRow("Signal Logic:", self.backtest_logic_combo)

        self.backtest_mdd_combo = QtWidgets.QComboBox()
        for key in MDD_LOGIC_OPTIONS:
            label = MDD_LOGIC_LABELS.get(key, key.replace("_", " ").title())
            self.backtest_mdd_combo.addItem(label, key)
        self.backtest_mdd_combo.currentIndexChanged.connect(self._on_backtest_mdd_logic_changed)
        param_form.addRow("MDD Logic:", self.backtest_mdd_combo)

        self.backtest_capital_spin = QtWidgets.QDoubleSpinBox()
        self.backtest_capital_spin.setDecimals(2)
        self.backtest_capital_spin.setRange(1.0, 1_000_000_000.0)
        self.backtest_capital_spin.setSuffix(" USDT")
        self.backtest_capital_spin.valueChanged.connect(lambda v: self._update_backtest_config("capital", float(v)))
        param_form.addRow("Margin Capital:", self.backtest_capital_spin)

        self.backtest_pospct_spin = QtWidgets.QDoubleSpinBox()
        self.backtest_pospct_spin.setDecimals(2)
        self.backtest_pospct_spin.setRange(0.01, 100.0)
        self.backtest_pospct_spin.setSuffix(" %")
        self.backtest_pospct_spin.valueChanged.connect(lambda v: self._update_backtest_config("position_pct", float(v)))
        param_form.addRow("Position % of Balance:", self.backtest_pospct_spin)

        self.backtest_loop_combo = QtWidgets.QComboBox()
        for label, value in DASHBOARD_LOOP_CHOICES:
            self.backtest_loop_combo.addItem(label, value)
        loop_default = self._normalize_loop_override(self.backtest_config.get("loop_interval_override")) or ""
        if loop_default and self.backtest_loop_combo.findData(loop_default) < 0:
            self.backtest_loop_combo.addItem(loop_default, loop_default)
        idx_backtest_loop = self.backtest_loop_combo.findData(loop_default)
        if idx_backtest_loop < 0:
            idx_backtest_loop = 0
        self.backtest_loop_combo.setCurrentIndex(idx_backtest_loop)
        self.backtest_loop_combo.currentIndexChanged.connect(self._on_backtest_loop_changed)
        self.backtest_config["loop_interval_override"] = loop_default
        self.config.setdefault("backtest", {})["loop_interval_override"] = loop_default
        param_form.addRow("Loop Interval Override:", self.backtest_loop_combo)

        backtest_stop_cfg = normalize_stop_loss_dict(self.backtest_config.get("stop_loss"))
        self.backtest_config["stop_loss"] = backtest_stop_cfg
        self.config.setdefault("backtest", {})["stop_loss"] = copy.deepcopy(backtest_stop_cfg)

        stop_loss_row = QtWidgets.QWidget()
        stop_loss_layout = QtWidgets.QHBoxLayout(stop_loss_row)
        stop_loss_layout.setContentsMargins(0, 0, 0, 0)
        stop_loss_layout.setSpacing(6)

        self.backtest_stop_loss_enable_cb = QtWidgets.QCheckBox("Enable")
        self.backtest_stop_loss_enable_cb.setChecked(backtest_stop_cfg.get("enabled", False))
        stop_loss_layout.addWidget(self.backtest_stop_loss_enable_cb)

        self.backtest_stop_loss_mode_combo = QtWidgets.QComboBox()
        for mode_key in STOP_LOSS_MODE_ORDER:
            self.backtest_stop_loss_mode_combo.addItem(STOP_LOSS_MODE_LABELS.get(mode_key, mode_key.title()), mode_key)
        mode_idx = self.backtest_stop_loss_mode_combo.findData(backtest_stop_cfg.get("mode"))
        if mode_idx < 0:
            mode_idx = 0
        self.backtest_stop_loss_mode_combo.setCurrentIndex(mode_idx)
        stop_loss_layout.addWidget(self.backtest_stop_loss_mode_combo)

        stop_loss_layout.addWidget(QtWidgets.QLabel("Scope:"))
        self.backtest_stop_loss_scope_combo = QtWidgets.QComboBox()
        for scope_key in STOP_LOSS_SCOPE_OPTIONS:
            self.backtest_stop_loss_scope_combo.addItem(
                STOP_LOSS_SCOPE_LABELS.get(scope_key, scope_key.replace("_", " ").title()), scope_key
            )
        scope_idx = self.backtest_stop_loss_scope_combo.findData(backtest_stop_cfg.get("scope"))
        if scope_idx < 0:
            scope_idx = 0
        self.backtest_stop_loss_scope_combo.setCurrentIndex(scope_idx)
        stop_loss_layout.addWidget(self.backtest_stop_loss_scope_combo)

        self.backtest_stop_loss_usdt_spin = QtWidgets.QDoubleSpinBox()
        self.backtest_stop_loss_usdt_spin.setRange(0.0, 1_000_000_000.0)
        self.backtest_stop_loss_usdt_spin.setDecimals(2)
        self.backtest_stop_loss_usdt_spin.setSingleStep(1.0)
        self.backtest_stop_loss_usdt_spin.setSuffix(" USDT")
        self.backtest_stop_loss_usdt_spin.setValue(float(backtest_stop_cfg.get("usdt", 0.0)))
        stop_loss_layout.addWidget(self.backtest_stop_loss_usdt_spin)

        self.backtest_stop_loss_percent_spin = QtWidgets.QDoubleSpinBox()
        self.backtest_stop_loss_percent_spin.setRange(0.0, 100.0)
        self.backtest_stop_loss_percent_spin.setDecimals(2)
        self.backtest_stop_loss_percent_spin.setSingleStep(0.5)
        self.backtest_stop_loss_percent_spin.setSuffix(" %")
        self.backtest_stop_loss_percent_spin.setValue(float(backtest_stop_cfg.get("percent", 0.0)))
        stop_loss_layout.addWidget(self.backtest_stop_loss_percent_spin)

        stop_loss_layout.addStretch()

        param_form.addRow("Stop Loss:", stop_loss_row)

        self.backtest_stop_loss_enable_cb.toggled.connect(self._on_backtest_stop_loss_enabled)
        self.backtest_stop_loss_mode_combo.currentIndexChanged.connect(self._on_backtest_stop_loss_mode_changed)
        self.backtest_stop_loss_scope_combo.currentTextChanged.connect(lambda _: self._on_backtest_stop_loss_scope_changed())
        self.backtest_stop_loss_usdt_spin.valueChanged.connect(lambda v: self._on_backtest_stop_loss_value_changed("usdt", v))
        self.backtest_stop_loss_percent_spin.valueChanged.connect(lambda v: self._on_backtest_stop_loss_value_changed("percent", v))
        self._update_backtest_stop_loss_widgets()

        self.backtest_side_combo = QtWidgets.QComboBox()
        self.backtest_side_combo.addItems([SIDE_LABELS["BUY"], SIDE_LABELS["SELL"], SIDE_LABELS["BOTH"]])
        self.backtest_side_combo.currentTextChanged.connect(lambda v: self._update_backtest_config("side", v))
        param_form.addRow("Side:", self.backtest_side_combo)

        self.backtest_margin_mode_combo = QtWidgets.QComboBox()
        self.backtest_margin_mode_combo.addItems(["Isolated", "Cross"])
        self.backtest_margin_mode_combo.currentTextChanged.connect(lambda v: self._update_backtest_config("margin_mode", v))
        param_form.addRow("Margin Mode (Futures):", self.backtest_margin_mode_combo)

        self.backtest_position_mode_combo = QtWidgets.QComboBox()
        self.backtest_position_mode_combo.addItems(["Hedge", "One-way"])
        self.backtest_position_mode_combo.currentTextChanged.connect(lambda v: self._update_backtest_config("position_mode", v))
        param_form.addRow("Position Mode:", self.backtest_position_mode_combo)

        self.backtest_assets_mode_combo = QtWidgets.QComboBox()
        self.backtest_assets_mode_combo.addItem("Single-Asset Mode", "Single-Asset")
        self.backtest_assets_mode_combo.addItem("Multi-Assets Mode", "Multi-Assets")
        assets_mode_cfg_bt = self._normalize_assets_mode(self.backtest_config.get("assets_mode", "Single-Asset"))
        idx_assets_bt = self.backtest_assets_mode_combo.findData(assets_mode_cfg_bt)
        if idx_assets_bt < 0:
            idx_assets_bt = 0
        with QtCore.QSignalBlocker(self.backtest_assets_mode_combo):
            self.backtest_assets_mode_combo.setCurrentIndex(idx_assets_bt)
        self.backtest_assets_mode_combo.currentIndexChanged.connect(
            lambda idx: self._update_backtest_config(
                "assets_mode",
                self._normalize_assets_mode(self.backtest_assets_mode_combo.itemData(idx)),
            )
        )
        param_form.addRow("Assets Mode:", self.backtest_assets_mode_combo)

        self.backtest_account_mode_combo = QtWidgets.QComboBox()
        for mode in ACCOUNT_MODE_OPTIONS:
            self.backtest_account_mode_combo.addItem(mode, mode)
        account_mode_cfg_bt = self._normalize_account_mode(self.backtest_config.get("account_mode", ACCOUNT_MODE_OPTIONS[0]))
        idx_account_mode_bt = self.backtest_account_mode_combo.findData(account_mode_cfg_bt)
        if idx_account_mode_bt < 0:
            idx_account_mode_bt = 0
        with QtCore.QSignalBlocker(self.backtest_account_mode_combo):
            self.backtest_account_mode_combo.setCurrentIndex(idx_account_mode_bt)
        self.backtest_account_mode_combo.currentIndexChanged.connect(self._on_backtest_account_mode_changed)
        self.backtest_config["account_mode"] = account_mode_cfg_bt
        self.config.setdefault("backtest", {})["account_mode"] = account_mode_cfg_bt
        self._apply_backtest_account_mode_constraints(account_mode_cfg_bt)
        param_form.addRow("Account Mode:", self.backtest_account_mode_combo)

        self.backtest_connector_combo = QtWidgets.QComboBox()
        self._refresh_backtest_connector_options(force_default=False)
        self.backtest_connector_combo.currentIndexChanged.connect(self._on_backtest_connector_changed)
        param_form.addRow("Connector:", self.backtest_connector_combo)

        self.backtest_leverage_spin = QtWidgets.QSpinBox()
        self.backtest_leverage_spin.setRange(1, 150)
        self.backtest_leverage_spin.valueChanged.connect(lambda v: self._update_backtest_config("leverage", int(v)))
        param_form.addRow("Leverage (Futures):", self.backtest_leverage_spin)

        template_row = QtWidgets.QWidget()
        template_layout = QtWidgets.QHBoxLayout(template_row)
        template_layout.setContentsMargins(0, 0, 0, 0)
        template_layout.setSpacing(6)

        self.backtest_template_enable_cb = QtWidgets.QCheckBox("Enable")
        template_layout.addWidget(self.backtest_template_enable_cb)

        self.backtest_template_combo = QtWidgets.QComboBox()
        for key, definition in BACKTEST_TEMPLATE_DEFINITIONS.items():
            label = definition.get("label", key.replace("_", " ").title())
            self.backtest_template_combo.addItem(label, key)
        template_layout.addWidget(self.backtest_template_combo, stretch=1)

        param_form.addRow("Template:", template_row)

        scan_header = QtWidgets.QWidget()
        scan_header_layout = QtWidgets.QHBoxLayout(scan_header)
        scan_header_layout.setContentsMargins(0, 0, 0, 0)
        scan_header_layout.setSpacing(8)
        scan_title = QtWidgets.QLabel("Max MDD Scanner")
        scan_title.setStyleSheet("font-weight: 600;")
        scan_header_layout.addWidget(scan_title)
        scan_divider = QtWidgets.QFrame()
        scan_divider.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        scan_divider.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        scan_header_layout.addWidget(scan_divider, stretch=1)
        param_form.addRow(scan_header)

        scan_row = QtWidgets.QWidget()
        scan_layout = QtWidgets.QHBoxLayout(scan_row)
        scan_layout.setContentsMargins(0, 0, 0, 0)
        scan_layout.setSpacing(6)
        scan_layout.addWidget(QtWidgets.QLabel("Top N:"))
        self.backtest_scan_top_spin = QtWidgets.QSpinBox()
        self.backtest_scan_top_spin.setRange(1, max(1, int(_SYMBOL_FETCH_TOP_N)))
        scan_top_default = int(self.backtest_config.get("scan_top_n", _SYMBOL_FETCH_TOP_N) or _SYMBOL_FETCH_TOP_N)
        if scan_top_default < 1:
            scan_top_default = 1
        if scan_top_default > _SYMBOL_FETCH_TOP_N:
            scan_top_default = _SYMBOL_FETCH_TOP_N
        self.backtest_scan_top_spin.setValue(scan_top_default)
        self.backtest_scan_top_spin.valueChanged.connect(
            lambda v: self._update_backtest_config("scan_top_n", int(v))
        )
        scan_layout.addWidget(self.backtest_scan_top_spin)
        scan_layout.addWidget(QtWidgets.QLabel("Max MDD %:"))
        self.backtest_scan_mdd_spin = QtWidgets.QDoubleSpinBox()
        self.backtest_scan_mdd_spin.setRange(0.0, 100.0)
        self.backtest_scan_mdd_spin.setDecimals(2)
        self.backtest_scan_mdd_spin.setSingleStep(0.5)
        scan_mdd_default = float(self.backtest_config.get("scan_mdd_limit", 10.0) or 10.0)
        if scan_mdd_default < 0.0:
            scan_mdd_default = 0.0
        self.backtest_scan_mdd_spin.setValue(scan_mdd_default)
        self.backtest_scan_mdd_spin.valueChanged.connect(
            lambda v: self._update_backtest_config("scan_mdd_limit", float(v))
        )
        scan_layout.addWidget(self.backtest_scan_mdd_spin)
        self.backtest_scan_btn = QtWidgets.QPushButton("Scan Symbols")
        self.backtest_scan_btn.clicked.connect(self._run_backtest_scan)
        scan_layout.addWidget(self.backtest_scan_btn)
        scan_layout.addStretch()
        param_form.addRow("Max MDD Scanner:", scan_row)

        self.backtest_template_enable_cb.toggled.connect(self._on_backtest_template_enabled)
        self.backtest_template_combo.currentIndexChanged.connect(self._on_backtest_template_selected)

        self._backtest_futures_widgets = [
            self.backtest_margin_mode_combo,
            param_form.labelForField(self.backtest_margin_mode_combo),
            self.backtest_position_mode_combo,
            param_form.labelForField(self.backtest_position_mode_combo),
            self.backtest_assets_mode_combo,
            param_form.labelForField(self.backtest_assets_mode_combo),
            self.backtest_account_mode_combo,
            param_form.labelForField(self.backtest_account_mode_combo),
            self.backtest_leverage_spin,
            param_form.labelForField(self.backtest_leverage_spin),
        ]

        self._set_backtest_mdd_selection(self.backtest_config.get("mdd_logic", MDD_LOGIC_DEFAULT))
        template_cfg_bt = self.backtest_config.get("template", copy.deepcopy(BACKTEST_TEMPLATE_DEFAULT))
        selected_template = self._select_backtest_template(template_cfg_bt.get("name"), update_config=False)
        template_enabled = bool(template_cfg_bt.get("enabled", False))
        with QtCore.QSignalBlocker(self.backtest_template_enable_cb):
            self.backtest_template_enable_cb.setChecked(template_enabled)
        combo = getattr(self, "backtest_template_combo", None)
        if combo is not None:
            combo.setEnabled(template_enabled and combo.count() > 0)
        template_cfg_bt["name"] = selected_template
        self.backtest_config["template"] = template_cfg_bt
        self.config.setdefault("backtest", {})["template"] = copy.deepcopy(template_cfg_bt)
        self._backtest_template_pending_apply = selected_template if template_enabled else None

        top_layout.addWidget(param_group, 5)

        indicator_group = QtWidgets.QGroupBox("Indicators")
        indicator_group.setMinimumWidth(280)
        indicator_group.setMaximumWidth(340)
        indicator_group.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        ind_layout = QtWidgets.QGridLayout(indicator_group)
        self.backtest_indicator_widgets.clear()
        row = 0
        for key, params in self.backtest_config.get("indicators", {}).items():
            label = INDICATOR_DISPLAY_NAMES.get(key, key)
            cb = QtWidgets.QCheckBox(label)
            cb.setProperty("indicator_key", key)
            cb.setChecked(bool(params.get("enabled", False)))
            cb.toggled.connect(lambda checked, _key=key: self._backtest_toggle_indicator(_key, checked))
            btn = QtWidgets.QPushButton("Buy-Sell Values")
            btn.clicked.connect(lambda _=False, _key=key: self._open_backtest_params(_key))
            ind_layout.addWidget(cb, row, 0)
            ind_layout.addWidget(btn, row, 1)
            self.backtest_indicator_widgets[key] = (cb, btn)
            row += 1
        top_layout.addWidget(indicator_group, stretch=3)

        pending_template = getattr(self, "_backtest_template_pending_apply", None)
        if pending_template:
            self._apply_backtest_template(pending_template)
        self._backtest_template_pending_apply = None

        tab3_content_layout.addLayout(top_layout)

        output_group = QtWidgets.QGroupBox("Backtest Output")
        output_group_layout = QtWidgets.QVBoxLayout(output_group)
        output_group_layout.setContentsMargins(12, 12, 12, 12)
        output_group_layout.setSpacing(12)

        controls_layout = QtWidgets.QHBoxLayout()
        self.backtest_run_btn = QtWidgets.QPushButton("Run Backtest")
        self.backtest_run_btn.clicked.connect(self._run_backtest)
        controls_layout.addWidget(self.backtest_run_btn)
        self.backtest_stop_btn = QtWidgets.QPushButton("Stop")
        self.backtest_stop_btn.setEnabled(False)
        self.backtest_stop_btn.clicked.connect(self._stop_backtest)
        controls_layout.addWidget(self.backtest_stop_btn)
        self.backtest_status_label = QtWidgets.QLabel()
        controls_layout.addWidget(self.backtest_status_label)
        self.backtest_add_to_dashboard_btn = QtWidgets.QPushButton("Add Selected to Dashboard")
        self.backtest_add_to_dashboard_btn.clicked.connect(self._backtest_add_selected_to_dashboard)
        controls_layout.addWidget(self.backtest_add_to_dashboard_btn)
        self.backtest_add_all_to_dashboard_btn = QtWidgets.QPushButton("Add All to Dashboard")
        self.backtest_add_all_to_dashboard_btn.clicked.connect(self._backtest_add_all_to_dashboard)
        controls_layout.addWidget(self.backtest_add_all_to_dashboard_btn)
        controls_layout.addStretch()
        tab3_status_widget = QtWidgets.QWidget()
        tab3_status_layout = QtWidgets.QHBoxLayout(tab3_status_widget)
        tab3_status_layout.setContentsMargins(0, 0, 0, 0)
        tab3_status_layout.setSpacing(8)
        self.pnl_active_label_tab3 = QtWidgets.QLabel()
        self.pnl_closed_label_tab3 = QtWidgets.QLabel()
        self.bot_status_label_tab3 = QtWidgets.QLabel()
        self.bot_time_label_tab3 = QtWidgets.QLabel("Bot Active Time: --")
        for lbl in (self.pnl_active_label_tab3, self.pnl_closed_label_tab3):
            lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
            tab3_status_layout.addWidget(lbl)
        tab3_status_layout.addStretch()
        for lbl in (self.bot_status_label_tab3, self.bot_time_label_tab3):
            lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
            tab3_status_layout.addWidget(lbl)
        self._register_pnl_summary_labels(self.pnl_active_label_tab3, self.pnl_closed_label_tab3)
        controls_layout.addWidget(tab3_status_widget)
        output_group_layout.addLayout(controls_layout)
        self._update_bot_status()
        try:
            for widget in (
                self.backtest_run_btn,
                self.backtest_stop_btn,
                self.backtest_scan_btn,
                self.backtest_add_to_dashboard_btn,
                self.backtest_add_all_to_dashboard_btn,
            ):
                if widget and widget not in self._runtime_lock_widgets:
                    self._runtime_lock_widgets.append(widget)
                if widget in (self.backtest_run_btn, self.backtest_stop_btn, self.backtest_scan_btn):
                    self._register_runtime_active_exemption(widget)
        except Exception:
            pass

        self.backtest_results_table = QtWidgets.QTableWidget(0, 21)
        self.backtest_results_table.setHorizontalHeaderLabels([
            "Symbol",
            "Interval",
            "Logic",
            "Indicators",
            "Trades",
            "Loop Interval",
            "Start Date",
            "End Date",
            "Position % Of Balance",
            "Stop-Loss Options",
            "Margin Mode (Futures)",
            "Position Mode",
            "Assets Mode",
            "Account Mode",
            "Leverage (Futures)",
            "ROI (USDT)",
            "ROI (%)",
            "Max Drawdown During Position (USDT)",
            "Max Drawdown During Position (%)",
            "Max Drawdown Results (USDT)",
            "Max Drawdown Results (%)",
        ])
        header = self.backtest_results_table.horizontalHeader()
        header.setStretchLastSection(False)
        try:
            header.setSectionsMovable(True)
        except Exception:
            pass
        try:
            header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Interactive)
        except Exception:
            try:
                header.setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
            except Exception:
                pass
        try:
            font_metrics = header.fontMetrics()
            style = header.style()
            opt = QtWidgets.QStyleOptionHeader()
            opt.initFrom(header)
            base_padding = style.pixelMetric(QtWidgets.QStyle.PixelMetric.PM_HeaderMargin, opt, header)
            arrow_padding = style.pixelMetric(QtWidgets.QStyle.PixelMetric.PM_HeaderMarkSize, opt, header)
        except Exception:
            font_metrics = None
            base_padding = 12
            arrow_padding = 12
        if font_metrics is None:
            font_metrics = self.fontMetrics()
        total_padding = (base_padding or 12) * 2 + (arrow_padding or 12)
        for col in range(self.backtest_results_table.columnCount()):
            try:
                header_item = self.backtest_results_table.horizontalHeaderItem(col)
                text = header_item.text() if header_item is not None else ""
                text_width = font_metrics.horizontalAdvance(text) if font_metrics is not None else 0
                target_width = max(text_width + total_padding, 80)
                header.resizeSection(col, target_width)
            except Exception:
                continue
        self.backtest_results_table.setSortingEnabled(True)
        try:
            self.backtest_results_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        except Exception:
            self.backtest_results_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.backtest_results_table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.backtest_results_table.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.backtest_results_table.setSizeAdjustPolicy(QtWidgets.QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored)
        self.backtest_results_table.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.backtest_results_table.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.backtest_results_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.backtest_results_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        self.backtest_results_table.setMinimumHeight(420)
        output_group_layout.addWidget(self.backtest_results_table, 1)
        tab3_content_layout.addWidget(output_group)

        self.tabs.addTab(tab3, "Backtest")

        liquidation_tab = self._init_liquidation_heatmap_tab()
        if liquidation_tab is not None:
            self.liquidation_tab = liquidation_tab
            self.tabs.addTab(liquidation_tab, "Liquidation Heatmap")

        code_tab = self._init_code_language_tab()
        if code_tab is not None:
            self.code_tab = code_tab
            self.tabs.addTab(code_tab, "Code Languages")

        self._refresh_symbol_interval_pairs("runtime")
        self._refresh_symbol_interval_pairs("backtest")
        self._initialize_backtest_ui_defaults()


        

        self.resize(1200, 900)
        self._apply_initial_geometry()
        self.apply_theme(self.theme_combo.currentText())
        self._ui_initialized = True
        self._setup_log_buffer()
        try:
            self.ind_source_combo.currentTextChanged.connect(lambda v: self.config.__setitem__("indicator_source", v))
        except Exception:
            pass


def _open_external_url(self, url: str) -> bool:
    try:
        target = str(url or "").strip()
    except Exception:
        target = ""
    if not target:
        return False
    try:
        return bool(QtGui.QDesktopServices.openUrl(QtCore.QUrl(target)))
    except Exception:
        return False


def _build_liquidation_web_panel(self, title: str, url: str, note: str | None = None):
    panel = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(panel)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(8)

    header_layout = QtWidgets.QHBoxLayout()
    title_label = QtWidgets.QLabel(title)
    title_label.setStyleSheet("font-size: 16px; font-weight: 600;")
    header_layout.addWidget(title_label)
    header_layout.addStretch()
    open_btn = QtWidgets.QPushButton("Open in Browser")
    header_layout.addWidget(open_btn)
    reload_btn = QtWidgets.QPushButton("Reload")
    header_layout.addWidget(reload_btn)
    layout.addLayout(header_layout)

    if note:
        note_label = QtWidgets.QLabel(note)
        note_label.setWordWrap(True)
        note_label.setStyleSheet("color: #94a3b8;")
        layout.addWidget(note_label)

    url_row = QtWidgets.QHBoxLayout()
    url_row.addWidget(QtWidgets.QLabel("URL:"))
    url_edit = QtWidgets.QLineEdit()
    url_edit.setText(url)
    url_edit.setPlaceholderText("https://")
    url_row.addWidget(url_edit, 1)
    go_btn = QtWidgets.QPushButton("Go")
    url_row.addWidget(go_btn)
    layout.addLayout(url_row)

    web_embed = _LazyWebEmbed(url)
    layout.addWidget(web_embed, 1)
    try:
        QtCore.QTimer.singleShot(0, web_embed.prime_native_host)
    except Exception:
        pass

    def _current_url() -> str:
        try:
            return str(url_edit.text() or "").strip()
        except Exception:
            return ""

    def _apply_url() -> None:
        target = _current_url()
        if not target:
            return
        web_embed.set_url(target)

    go_btn.clicked.connect(_apply_url)
    url_edit.returnPressed.connect(_apply_url)
    reload_btn.clicked.connect(web_embed.reload)
    open_btn.clicked.connect(lambda: _open_external_url(self, _current_url()))

    return panel


def _init_liquidation_heatmap_tab(self):
    tab = QtWidgets.QWidget()
    outer_layout = QtWidgets.QVBoxLayout(tab)
    outer_layout.setContentsMargins(10, 10, 10, 10)
    outer_layout.setSpacing(12)

    intro = QtWidgets.QLabel(
        "Liquidation heatmaps from multiple providers. "
        "If a heatmap does not load, use 'Open in Browser'."
    )
    intro.setWordWrap(True)
    outer_layout.addWidget(intro)

    tabs = QtWidgets.QTabWidget()
    outer_layout.addWidget(tabs, 1)
    self.liquidation_tabs = tabs

    coinglass_tab = QtWidgets.QWidget()
    coinglass_layout = QtWidgets.QVBoxLayout(coinglass_tab)
    coinglass_layout.setContentsMargins(0, 0, 0, 0)
    coinglass_note = QtWidgets.QLabel(
        "Use the on-page controls for Model 1/2/3, pair, symbol, and time selection."
    )
    coinglass_note.setWordWrap(True)
    coinglass_layout.addWidget(coinglass_note)

    coinglass_models = QtWidgets.QTabWidget()
    coinglass_layout.addWidget(coinglass_models, 1)
    coinglass_models_urls = [
        (1, "https://www.coinglass.com/pro/futures/LiquidationHeatMap"),
        (2, "https://www.coinglass.com/pro/futures/LiquidationHeatMapNew"),
        (3, "https://www.coinglass.com/pro/futures/LiquidationHeatMapModel3"),
    ]
    for model, url in coinglass_models_urls:
        panel = _build_liquidation_web_panel(self, f"Coinglass Heatmap Model {model}", url)
        coinglass_models.addTab(panel, f"Model {model}")

    tabs.addTab(coinglass_tab, "Coinglass Heatmap")

    tabs.addTab(
        _build_liquidation_web_panel(
            self,
            "Coinank Liquidation Heatmap",
            "https://coinank.com/chart/derivatives/liq-heat-map",
        ),
        "Coinank",
    )

    tabs.addTab(
        _build_liquidation_web_panel(
            self,
            "Bitcoin Counterflow Liquidation Heatmap",
            "https://www.bitcoincounterflow.com/liquidation-heatmap/",
        ),
        "Bitcoin Counterflow",
    )

    tabs.addTab(
        _build_liquidation_web_panel(
            self,
            "Hyblock Capital Liquidation Heatmap",
            "https://www.hyblockcapital.com/heatmap",
        ),
        "Hyblock Capital",
    )

    tabs.addTab(
        _build_liquidation_web_panel(
            self,
            "Coinglass Liquidation Map",
            "https://www.coinglass.com/pro/futures/LiquidationMap",
        ),
        "Coinglass Map",
    )

    tabs.addTab(
        _build_liquidation_web_panel(
            self,
            "Hyperliquid Liquidation Map",
            "https://www.coinglass.com/hyperliquid-liquidation-map",
        ),
        "Hyperliquid Map",
    )

    return tab


def _init_code_language_tab(self):
    tab = QtWidgets.QWidget()
    outer_layout = QtWidgets.QVBoxLayout(tab)
    outer_layout.setContentsMargins(0, 0, 0, 0)
    outer_layout.setSpacing(0)

    scroll = QtWidgets.QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
    outer_layout.addWidget(scroll)

    content = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(content)
    layout.setContentsMargins(10, 10, 10, 10)
    layout.setSpacing(12)
    scroll.setWidget(content)

    description = QtWidgets.QLabel(
        "Select your preferred code language. "
        "Folders for each language are created automatically inside the project so you can keep related assets organized."
    )
    description.setWordWrap(True)
    layout.addWidget(description)

    self._starter_language_cards: dict[str, _StarterCard] = {}
    self._starter_market_cards: dict[str, _StarterCard] = {}
    self._starter_crypto_cards: dict[str, _StarterCard] = {}
    self._starter_forex_cards: dict[str, _StarterCard] = {}

    lang_label = QtWidgets.QLabel("Choose your language")
    lang_label.setStyleSheet("font-size: 20px; font-weight: 600;")
    layout.addWidget(lang_label)
    lang_row = QtWidgets.QHBoxLayout()
    lang_row.setSpacing(12)
    for opt in STARTER_LANGUAGE_OPTIONS:
        card = _StarterCard(
            opt["config_key"],
            opt["title"],
            opt["subtitle"],
            opt["accent"],
            opt.get("badge"),
            disabled=opt.get("disabled", False),
        )
        card.clicked.connect(self._code_tab_select_language)
        card.setMinimumWidth(180)
        lang_row.addWidget(card, 1)
        self._starter_language_cards[opt["config_key"]] = card
    lang_row.addStretch()
    layout.addLayout(lang_row)

    status_widget = QtWidgets.QWidget()
    status_layout = QtWidgets.QHBoxLayout(status_widget)
    status_layout.setContentsMargins(0, 0, 0, 0)
    status_layout.setSpacing(12)
    self.pnl_active_label_code_tab = QtWidgets.QLabel()
    self.pnl_closed_label_code_tab = QtWidgets.QLabel()
    self.bot_status_label_code_tab = QtWidgets.QLabel()
    self.bot_time_label_code_tab = QtWidgets.QLabel("Bot Active Time: --")
    for lbl in (self.pnl_active_label_code_tab, self.pnl_closed_label_code_tab):
        if lbl is not None:
            lbl.setStyleSheet("font-weight: 600;")
            lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
            status_layout.addWidget(lbl)
    status_layout.addStretch()
    for lbl in (self.bot_status_label_code_tab, self.bot_time_label_code_tab):
        if lbl is not None:
            lbl.setStyleSheet("font-weight: 600;")
            status_layout.addWidget(lbl)
    self._register_pnl_summary_labels(self.pnl_active_label_code_tab, self.pnl_closed_label_code_tab)
    layout.addWidget(status_widget)

    self._dep_version_labels: dict[str, tuple[QtWidgets.QLabel, QtWidgets.QLabel]] = {}
    self._dep_version_targets: list[dict[str, str]] = _dependency_targets_from_requirements(
        _iter_candidate_requirement_paths(self.config)
    )
    versions_group = QtWidgets.QGroupBox("Environment Versions")
    versions_group.setSizePolicy(
        QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
    )
    versions_group_layout = QtWidgets.QVBoxLayout(versions_group)
    versions_group_layout.setContentsMargins(8, 12, 8, 8)
    versions_group_layout.setSpacing(6)

    versions_container = QtWidgets.QWidget()
    versions_layout = QtWidgets.QGridLayout(versions_container)
    versions_layout.setContentsMargins(6, 6, 6, 6)
    versions_layout.setColumnStretch(0, 5)
    versions_layout.setColumnStretch(1, 3)
    versions_layout.setColumnStretch(2, 3)
    versions_layout.setVerticalSpacing(8)
    versions_layout.setHorizontalSpacing(12)

    versions_scroll = QtWidgets.QScrollArea()
    versions_scroll.setWidgetResizable(True)
    versions_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
    versions_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    versions_scroll.setWidget(versions_container)
    versions_scroll.setSizePolicy(
        QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
    )

    self._dep_versions_container = versions_container
    self._dep_versions_layout = versions_layout
    self._dep_versions_scroll = versions_scroll
    self._dep_versions_group = versions_group
    self._rebuild_dependency_version_rows(self._dep_version_targets)

    versions_group_layout.addWidget(versions_scroll, 1)
    layout.addWidget(versions_group, 1)
    version_btn_row = QtWidgets.QHBoxLayout()
    version_btn_row.addStretch()
    self._version_refresh_btn = QtWidgets.QPushButton("Check Versions")
    self._version_refresh_btn.clicked.connect(self._refresh_dependency_versions)
    version_btn_row.addWidget(self._version_refresh_btn)
    layout.addLayout(version_btn_row)
    # Refresh dependency versions lazily the first time this tab is opened (see _on_tab_changed),
    # so the table doesn't stay at "Checking..." without slowing down initial startup.

    self._sync_language_exchange_lists_from_config()
    self._update_bot_status()
    self._refresh_code_tab_from_config()
    return tab

def _code_tab_select_language(self, config_key: str) -> None:
    if config_key not in LANGUAGE_PATHS:
        return
    card = getattr(self, "_starter_language_cards", {}).get(config_key)
    if card is not None and card.is_disabled():
        return
    self.config["code_language"] = config_key
    self._refresh_code_tab_from_config()
    self._ensure_language_exchange_paths()


def _code_tab_select_market(self, market_key: str) -> None:
    if market_key not in {"crypto", "forex"}:
        return
    card = getattr(self, "_starter_market_cards", {}).get(market_key)
    if card is not None and card.is_disabled():
        return
    self.config["code_market"] = market_key
    self._code_tab_selected_market = market_key
    self._refresh_code_tab_from_config()
    self._ensure_language_exchange_paths()


def _code_tab_select_exchange(self, exchange_key: str) -> None:
    if exchange_key not in EXCHANGE_PATHS:
        return
    card = getattr(self, "_starter_crypto_cards", {}).get(exchange_key)
    if card is not None and card.is_disabled():
        return
    self.config["selected_exchange"] = exchange_key
    self._refresh_code_tab_from_config()
    self._ensure_language_exchange_paths()


def _code_tab_select_forex(self, broker_key: str) -> None:
    if broker_key not in FOREX_BROKER_PATHS:
        return
    card = getattr(self, "_starter_forex_cards", {}).get(broker_key)
    if card is not None and card.is_disabled():
        return
    self.config["selected_forex_broker"] = broker_key
    self._code_tab_selected_market = "forex"
    self.config["code_market"] = "forex"
    self._refresh_code_tab_from_config()
    self._ensure_language_exchange_paths()


def _refresh_code_tab_from_config(self) -> None:
    lang_cards = getattr(self, "_starter_language_cards", {})
    lang_key = self.config.get("code_language")
    if not lang_key or lang_key not in lang_cards or lang_cards[lang_key].is_disabled():
        lang_key = next((k for k, c in lang_cards.items() if not c.is_disabled()), None)
        if lang_key:
            self.config["code_language"] = lang_key
    for key, card in lang_cards.items():
        card.setSelected(bool(lang_key) and key == lang_key)
    # Dependency versions refresh lazily the first time this tab is opened (see _on_tab_changed).


def _rebuild_dependency_version_rows(self, targets: list[dict[str, str]] | None = None) -> None:
    layout = getattr(self, "_dep_versions_layout", None)
    container = getattr(self, "_dep_versions_container", None)
    scroll = getattr(self, "_dep_versions_scroll", None)
    group = getattr(self, "_dep_versions_group", None)
    target_list = targets or getattr(self, "_dep_version_targets", []) or []
    if layout is None or container is None or group is None:
        return

    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()

    header_dep = QtWidgets.QLabel("Dependency")
    header_dep.setStyleSheet("font-weight: 600; font-size: 12px;")
    header_inst = QtWidgets.QLabel("Installed")
    header_inst.setStyleSheet("font-weight: 600; font-size: 12px;")
    header_latest = QtWidgets.QLabel("Latest")
    header_latest.setStyleSheet("font-weight: 600; font-size: 12px;")
    layout.addWidget(header_dep, 0, 0)
    layout.addWidget(header_inst, 0, 1)
    layout.addWidget(header_latest, 0, 2)

    labels: dict[str, tuple[QtWidgets.QLabel, QtWidgets.QLabel]] = {}
    for row, target in enumerate(target_list, start=1):
        label_widget = QtWidgets.QLabel(target["label"])
        label_widget.setStyleSheet("font-weight: 600; font-size: 11px; padding: 2px;")
        label_widget.setMinimumHeight(20)

        installed_widget = QtWidgets.QLabel("Checking...")
        installed_widget.setStyleSheet("font-size: 11px; padding: 2px;")
        installed_widget.setMinimumHeight(20)
        installed_widget.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)

        latest_widget = QtWidgets.QLabel("Checking...")
        latest_widget.setStyleSheet("font-size: 11px; padding: 2px;")
        latest_widget.setMinimumHeight(20)
        latest_widget.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)

        layout.addWidget(label_widget, row, 0)
        layout.addWidget(installed_widget, row, 1)
        layout.addWidget(latest_widget, row, 2)
        labels[target["label"]] = (installed_widget, latest_widget)

    self._dep_version_labels = labels
    self._dep_version_targets = list(target_list)

    rows = len(target_list) + 1  # +1 for header
    try:
        fm = container.fontMetrics()
        row_height = max(30, fm.height() + 12)
    except Exception:
        row_height = 30
    target_height = rows * row_height + 32
    try:
        container.setMinimumHeight(target_height)
        group.setMinimumHeight(min(800, max(480, target_height + 60)))
    except Exception:
        pass

    if scroll is not None:
        scroll.setMinimumHeight(min(720, max(420, target_height)))
        scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        try:
            scroll.verticalScrollBar().setValue(0)
        except Exception:
            pass


def _refresh_dependency_versions(self) -> None:
    if getattr(self, "_dep_version_refresh_inflight", False):
        self._dep_version_refresh_pending = True
        return

    self._dep_version_refresh_inflight = True
    self._dep_version_refresh_pending = False
    self._dep_version_watchdog_token = time.monotonic()

    try:
        resolved_targets = _dependency_targets_from_requirements(_iter_candidate_requirement_paths(self.config))
    except Exception:
        resolved_targets = copy.deepcopy(DEPENDENCY_VERSION_TARGETS)

    # Ensure the UI rows exist for the resolved targets before applying values.
    try:
        if resolved_targets and resolved_targets != getattr(self, "_dep_version_targets", None):
            self._rebuild_dependency_version_rows(resolved_targets)
        else:
            try:
                self._dep_version_targets = list(resolved_targets or [])
            except Exception:
                pass
    except Exception:
        pass

    labels = getattr(self, "_dep_version_labels", None)
    if labels:
        for installed_widget, latest_widget in labels.values():
            try:
                latest_widget.setText("Checking...")
            except Exception:
                pass

    # Phase 1: populate installed versions immediately (no network).
    try:
        installed_snapshot = _collect_dependency_versions(resolved_targets, include_latest=False)
    except Exception:
        installed_snapshot = []
    if labels and installed_snapshot:
        for label, installed, _ in installed_snapshot:
            widgets = labels.get(label)
            if not widgets:
                continue
            installed_widget, _ = widgets
            try:
                installed_widget.setText(installed)
            except Exception:
                pass

    def _watchdog(token: float):
        try:
            if not getattr(self, "_dep_version_refresh_inflight", False):
                return
            if token != getattr(self, "_dep_version_watchdog_token", None):
                return
            labels_local = getattr(self, "_dep_version_labels", None)
            if labels_local:
                for installed_widget, latest_widget in labels_local.values():
                    try:
                        latest_widget.setText("Unknown")
                    except Exception:
                        pass
            self._dep_version_refresh_inflight = False
        except Exception:
            self._dep_version_refresh_inflight = False

    QtCore.QTimer.singleShot(20000, lambda t=self._dep_version_watchdog_token: _watchdog(t))

    # Phase 2: fetch latest versions in the background without blocking the UI.
    def _run_latest():
        try:
            installed_snapshot = list(_collect_dependency_versions(resolved_targets, include_latest=False))
        except Exception:
            installed_snapshot = []

        try:
            results = list(_collect_dependency_versions(resolved_targets, include_latest=True))
        except Exception:
            results = []
        if not results:
            # Fall back to installed values with Unknown latest so the UI never stays at "Checking..."
            if installed_snapshot:
                results = [(label, inst, "Unknown") for (label, inst, _) in installed_snapshot]
            else:
                results = [(target["label"], "Not installed", "Unknown") for target in (resolved_targets or [])]

        # Queue the UI update on the main thread using QMetaObject.invokeMethod for thread safety.
        # QTimer.singleShot can fail silently when called from a non-main thread in PyQt6.
        QtCore.QMetaObject.invokeMethod(
            self,
            "_apply_dependency_version_results",
            QtCore.Qt.ConnectionType.QueuedConnection,
            QtCore.Q_ARG(object, results),
        )

    threading.Thread(target=_run_latest, daemon=True).start()


@QtCore.pyqtSlot(object)
def _apply_dependency_version_results(self, results: list) -> None:
    """
    Apply the fetched dependency version results to the UI.
    This method is designed to be called via QMetaObject.invokeMethod from a background thread.
    """
    try:
        labels_local = getattr(self, "_dep_version_labels", None)
        if labels_local:
            installed_map = {}
            latest_map = {}
            for label, installed, latest in results:
                installed_map[label] = installed
                latest_map[label] = latest

            for label, widgets in labels_local.items():
                if widgets is None:
                    continue
                installed_widget, latest_widget = widgets
                try:
                    if label in installed_map:
                        installed_widget.setText(installed_map[label])
                except Exception:
                    pass
                try:
                    latest_widget.setText(latest_map.get(label, "Unknown"))
                except Exception:
                    pass

        self._dep_version_refresh_inflight = False
        if getattr(self, "_dep_version_refresh_pending", False):
            self._dep_version_refresh_pending = False
            QtCore.QTimer.singleShot(0, self._refresh_dependency_versions)
    except Exception:
        self._dep_version_refresh_inflight = False


def _update_code_tab_market_sections(self) -> None:
    market = getattr(self, "_code_tab_selected_market", None)
    show_crypto = market == "crypto"
    show_forex = market == "forex"
    for widget in (getattr(self, "_crypto_section_label", None), getattr(self, "_crypto_cards_widget", None)):
        if widget is not None:
            widget.setVisible(show_crypto)
    for widget in (getattr(self, "_forex_section_label", None), getattr(self, "_forex_cards_widget", None)):
        if widget is not None:
            widget.setVisible(show_forex)


def _sync_language_exchange_lists_from_config(self):
    selections = [
        ("code_language", self.language_combo, LANGUAGE_PATHS),
        ("selected_exchange", self.exchange_combo, EXCHANGE_PATHS),
        ("selected_forex_broker", self.forex_combo, FOREX_BROKER_PATHS),
    ]
    for key, widget, options_map in selections:
        if widget is None:
            continue
        desired = self.config.get(key)
        if not desired:
            try:
                blocker = QtCore.QSignalBlocker(widget)
            except Exception:
                blocker = None
            try:
                widget.setCurrentIndex(-1)
                if widget.isEditable():
                    widget.clearEditText()
            except Exception:
                pass
            if blocker is not None:
                del blocker
            continue
        if desired not in options_map and options_map:
            desired = next(iter(options_map))
            self.config[key] = desired
        with QtCore.QSignalBlocker(widget):
            idx = widget.findData(desired)
            if idx < 0:
                idx = widget.findText(desired, QtCore.Qt.MatchFlag.MatchExactly)
            if idx >= 0:
                try:
                    item = widget.model().item(idx)
                except Exception:
                    item = None
                if item is not None and not (item.flags() & QtCore.Qt.ItemFlag.ItemIsEnabled):
                    idx = -1
            if idx < 0 and widget.count() > 0:
                fallback_idx = -1
                fallback_value = None
                for i in range(widget.count()):
                    try:
                        item = widget.model().item(i)
                    except Exception:
                        item = None
                    if item is not None and not (item.flags() & QtCore.Qt.ItemFlag.ItemIsEnabled):
                        continue
                    data_value = widget.itemData(i)
                    text_value = widget.itemText(i)
                    if data_value in options_map:
                        fallback_idx = i
                        fallback_value = data_value
                        break
                    if text_value in options_map:
                        fallback_idx = i
                        fallback_value = text_value
                        break
                if fallback_idx >= 0:
                    idx = fallback_idx
                    desired = fallback_value
                    self.config[key] = desired
            if idx >= 0:
                widget.setCurrentIndex(idx)
    self._ensure_language_exchange_paths()
    self._refresh_code_tab_from_config()
    if self.exchange_list is not None:
        desired_exchange = self.config.get("selected_exchange")
        item = self._exchange_list_items.get(desired_exchange)
        if item is None or not (item.flags() & QtCore.Qt.ItemFlag.ItemIsEnabled):
            desired_exchange = None
            for opt in STARTER_CRYPTO_EXCHANGES:
                if opt.get("disabled", False):
                    continue
                desired_exchange = opt["key"]
                break
            if desired_exchange:
                self.config["selected_exchange"] = desired_exchange
                item = self._exchange_list_items.get(desired_exchange)
        if item is not None:
            with QtCore.QSignalBlocker(self.exchange_list):
                self.exchange_list.setCurrentItem(item)


def _ensure_language_exchange_paths(self):
    created_paths = []

    def _prepare_path(path: Path | None):
        if path is None:
            return
        try:
            is_new = not path.exists()
            path.mkdir(parents=True, exist_ok=True)
            if is_new:
                created_paths.append(path)
        except Exception as exc:
            try:
                self.log(f"Failed to prepare {path}: {exc}")
            except Exception:
                pass

    language_rel = LANGUAGE_PATHS.get(self.config.get("code_language"))
    language_root = (_BASE_PROJECT_PATH / language_rel).resolve() if language_rel else None
    _prepare_path(language_root)

    if language_root is None:
        base_path = _BASE_PROJECT_PATH
    else:
        base_path = language_root

    exchange_rel = EXCHANGE_PATHS.get(self.config.get("selected_exchange"))
    forex_rel = FOREX_BROKER_PATHS.get(self.config.get("selected_forex_broker"))
    _prepare_path((base_path / exchange_rel).resolve() if exchange_rel else None)
    _prepare_path((base_path / forex_rel).resolve() if forex_rel else None)

    if created_paths:
        try:
            created_text = ", ".join(str(p) for p in created_paths)
            self.log(f"Ensured directories: {created_text}")
        except Exception:
            pass


def _on_code_language_changed(self, text: str):
    if not text or text not in LANGUAGE_PATHS:
        return
    self.config["code_language"] = text
    self._ensure_language_exchange_paths()


def _on_exchange_selection_changed(self, text: str):
    exchange_key = str(text).strip() if text is not None else ""
    if exchange_key not in EXCHANGE_PATHS:
        combo = getattr(self, "exchange_combo", None)
        if combo is not None:
            data_key = combo.currentData()
            if data_key in EXCHANGE_PATHS:
                exchange_key = data_key
            else:
                text_key = combo.currentText()
                if text_key in EXCHANGE_PATHS:
                    exchange_key = text_key
    if not exchange_key or exchange_key not in EXCHANGE_PATHS:
        return
    self.config["selected_exchange"] = exchange_key
    self._ensure_language_exchange_paths()


def _on_exchange_list_changed(
    self,
    current: QtWidgets.QListWidgetItem | None,
    _previous: QtWidgets.QListWidgetItem | None = None,
) -> None:
    if current is None:
        return
    exchange_key = current.data(QtCore.Qt.ItemDataRole.UserRole) or current.text()
    if not exchange_key or exchange_key not in EXCHANGE_PATHS:
        return
    self.config["selected_exchange"] = exchange_key
    self._ensure_language_exchange_paths()


def _on_forex_selection_changed(self, text: str):
    if not text or text not in FOREX_BROKER_PATHS:
        return
    self.config["selected_forex_broker"] = text
    self._ensure_language_exchange_paths()


def _gui_on_positions_ready(self, rows: list, acct: str):
    try:
        try:
            rows = sorted(rows, key=lambda r: (str(r.get('symbol') or ''), str(r.get('side_key') or '')))
        except Exception:
            rows = rows or []

        positions_map: dict[tuple, dict] = {}
        base_rows = rows or []
        alloc_map_global = getattr(self, "_entry_allocations", {}) or {}
        prev_records = getattr(self, "_open_position_records", {}) or {}
        if not isinstance(prev_records, dict):
            prev_records = {}

        def _collect_allocations(symbol: str, side_key: str) -> list[dict]:
            try:
                entries = alloc_map_global.get((symbol, side_key), [])
                if isinstance(entries, dict):
                    entries = list(entries.values())
                if not isinstance(entries, list):
                    return []
                return [copy.deepcopy(entry) for entry in entries if isinstance(entry, dict)]
            except Exception:
                return []

        for r in base_rows:
            try:
                sym = str(r.get('symbol') or '').strip().upper()
                side_key = str(r.get('side_key') or 'SPOT').upper()
                if not sym:
                    continue
                stop_loss_enabled = False
                if side_key in ('L', 'S'):
                    stop_loss_enabled = self._position_stop_loss_enabled(sym, side_key)
                data_entry = dict(r)
                data_entry['symbol'] = sym
                data_entry['side_key'] = side_key
                positions_map[(sym, side_key)] = {
                    'symbol': sym,
                    'side_key': side_key,
                    'entry_tf': r.get('entry_tf'),
                    'open_time': r.get('open_time'),
                    'close_time': '-',
                    'status': 'Active',
                    'data': data_entry,
                    'indicators': [],
                    'stop_loss_enabled': stop_loss_enabled,
                    'leverage': data_entry.get('leverage'),
                    'liquidation_price': data_entry.get('liquidation_price') or data_entry.get('liquidationPrice'),
                }
                allocations_seed = _collect_allocations(sym, side_key)
                intervals_from_alloc: set[str] = set()
                interval_trigger_map: dict[str, set[str]] = {}
                trigger_union: set[str] = set()
                normalized_entry_triggers = _resolve_trigger_indicators(
                    data_entry.get('trigger_indicators'),
                    data_entry.get('trigger_desc'),
                )
                if normalized_entry_triggers:
                    trigger_union.update(normalized_entry_triggers)
                    data_entry['trigger_indicators'] = normalized_entry_triggers
                elif data_entry.get('trigger_indicators'):
                    data_entry.pop('trigger_indicators', None)
                if allocations_seed:
                    positions_map[(sym, side_key)]['allocations'] = allocations_seed
                    if not data_entry.get('trigger_desc'):
                        for alloc in allocations_seed:
                            if not isinstance(alloc, dict):
                                continue
                            desc = alloc.get("trigger_desc")
                            if desc:
                                data_entry['trigger_desc'] = desc
                                break
                    for alloc in allocations_seed:
                        status_flag = str(alloc.get("status") or "").strip().lower()
                        try:
                            qty_val = abs(float(alloc.get("qty") or 0.0))
                        except Exception:
                            qty_val = None
                        is_active_allocation = status_flag not in {"closed", "error"}
                        if qty_val is not None and qty_val <= 0.0:
                            qty_val = 0.0
                        if qty_val and status_flag not in {"closed", "error"}:
                            is_active_allocation = True
                        interval_val = alloc.get("interval_display") or alloc.get("interval")
                        interval_normalized = ""
                        interval_key = None
                        if interval_val:
                            try:
                                canon_iv = self._canonicalize_interval(interval_val)
                            except Exception:
                                canon_iv = None
                            if canon_iv:
                                interval_normalized = canon_iv.strip()
                            else:
                                interval_normalized = str(interval_val).strip()
                            if interval_normalized:
                                interval_key = interval_normalized.lower()
                                if is_active_allocation:
                                    intervals_from_alloc.add(interval_normalized)
                                    interval_trigger_map.setdefault(interval_key, set())
                        normalized_triggers = _resolve_trigger_indicators(
                            alloc.get("trigger_indicators"),
                            alloc.get("trigger_desc"),
                        )
                        if normalized_triggers:
                            alloc["trigger_indicators"] = normalized_triggers
                        elif alloc.get("trigger_indicators"):
                            alloc.pop("trigger_indicators", None)
                        if is_active_allocation and normalized_triggers:
                            trigger_union.update(normalized_triggers)
                            target_key = interval_key or (interval_normalized.strip().lower() if interval_normalized else None) or "-"
                            interval_trigger_map.setdefault(target_key, set()).update(normalized_triggers)
                    if trigger_union:
                        data_entry['trigger_indicators'] = sorted(dict.fromkeys(trigger_union))
                elif normalized_entry_triggers:
                    data_entry['trigger_indicators'] = normalized_entry_triggers
                try:
                    getattr(self, "_pending_close_times", {}).pop((sym, side_key), None)
                except Exception:
                    pass
            except Exception:
                continue

        # Backfill tracked allocations when exchange rows omitted the position
        tracked_keys = set(positions_map.keys())
        try:
            for (alloc_sym, alloc_side_key), allocations in alloc_map_global.items():
                if not isinstance(alloc_sym, str):
                    continue
                sym = alloc_sym.strip().upper()
                side_key = str(alloc_side_key or '').strip().upper()
                if not sym or side_key not in ('L', 'S'):
                    continue
                key = (sym, side_key)
                if key in tracked_keys:
                    continue
                if not isinstance(allocations, list) or not allocations:
                    continue
                active_any = False
                for alloc in allocations:
                    if not isinstance(alloc, dict):
                        continue
                    status_flag = str(alloc.get("status") or "").strip().lower()
                    if status_flag in {"closed", "error"}:
                        continue
                    try:
                        qty_val_chk = abs(float(alloc.get("qty") or 0.0))
                    except Exception:
                        qty_val_chk = 0.0
                    margin_val_chk = 0.0
                    notional_val_chk = 0.0
                    try:
                        margin_val_chk = abs(float(alloc.get("margin_usdt") or alloc.get("margin") or 0.0))
                    except Exception:
                        margin_val_chk = 0.0
                    try:
                        notional_val_chk = abs(float(alloc.get("notional") or alloc.get("size_usdt") or 0.0))
                    except Exception:
                        notional_val_chk = 0.0
                    if qty_val_chk > 0.0 or margin_val_chk > 0.0 or notional_val_chk > 0.0:
                        active_any = True
                        break
                if not active_any:
                    continue
                # Demo/testnet snapshots can briefly omit a just-open symbol. Keep any
                # previously tracked active row instead of scheduling an immediate close.
                try:
                    prev_rec = copy.deepcopy(prev_records.get(key) or {})
                except Exception:
                    prev_rec = {}
                if isinstance(prev_rec, dict) and prev_rec:
                    prev_rec["status"] = "Active"
                    prev_rec["close_time"] = "-"
                    try:
                        prev_rec["allocations"] = copy.deepcopy(
                            [entry for entry in allocations if isinstance(entry, dict)]
                        )
                    except Exception:
                        pass
                    positions_map[key] = prev_rec
                    tracked_keys.add(key)
                    try:
                        pending_close_map = getattr(self, "_pending_close_times", {})
                        if isinstance(pending_close_map, dict):
                            pending_close_map.pop(key, None)
                    except Exception:
                        pass
                continue
                qty_total = 0.0
                margin_total = 0.0
                notional_total = 0.0
                intervals_set: set[str] = set()
                interval_trigger_map: dict[str, set[str]] = {}
                trigger_union: set[str] = set()
                leverage_val = None
                liquidation_value = None
                open_times: list[str] = []
                for alloc in allocations:
                    if not isinstance(alloc, dict):
                        continue
                    status_flag = str(alloc.get("status") or "").strip().lower()
                    try:
                        qty_val = abs(float(alloc.get('qty') or 0.0))
                    except Exception:
                        qty_val = None
                    is_active_allocation = status_flag not in {"closed", "error"}
                    if qty_val is not None and qty_val <= 0.0:
                        qty_val = 0.0
                    if qty_val and status_flag not in {"closed", "error"}:
                        is_active_allocation = True
                    if is_active_allocation:
                        try:
                            qty_total += abs(qty_val or 0.0)
                        except Exception:
                            pass
                        try:
                            margin_total += max(float(alloc.get('margin_usdt') or 0.0), 0.0)
                        except Exception:
                            pass
                        try:
                            notional_total += max(float(alloc.get('notional') or 0.0), 0.0)
                        except Exception:
                            pass
                        interval_val = alloc.get('interval_display') or alloc.get('interval')
                        interval_normalized = ""
                        interval_key = None
                        if interval_val:
                            try:
                                canon_iv = self._canonicalize_interval(interval_val)
                            except Exception:
                                canon_iv = None
                            interval_normalized = (canon_iv or str(interval_val).strip()) or ""
                            if interval_normalized:
                                interval_key = interval_normalized.lower()
                                intervals_set.add(interval_normalized)
                        normalized_trigs = _resolve_trigger_indicators(
                            alloc.get('trigger_indicators'),
                            alloc.get('trigger_desc'),
                        )
                        if normalized_trigs:
                            alloc['trigger_indicators'] = normalized_trigs
                            trigger_union.update(normalized_trigs)
                            key = interval_key or (interval_normalized.lower() if interval_normalized else "-")
                            interval_trigger_map.setdefault(key, set()).update(normalized_trigs)
                        elif alloc.get('trigger_indicators'):
                            alloc.pop('trigger_indicators', None)
                    alloc_open = alloc.get('open_time')
                    if alloc_open:
                        open_times.append(str(alloc_open))
                    lev_val = alloc.get('leverage')
                    try:
                        lev_int = int(float(lev_val))
                        if lev_int > 0:
                            leverage_val = lev_int
                    except Exception:
                        pass
                    if liquidation_value is None:
                        for liq_key in ('liquidation_price', 'liquidationPrice', 'liq_price', 'liqPrice'):
                            cand = alloc.get(liq_key)
                            if cand in (None, '', 0, 0.0):
                                continue
                            try:
                                val = float(cand)
                            except Exception:
                                continue
                            if val > 0.0:
                                liquidation_value = val
                                break
                if qty_total <= 0.0 and margin_total <= 0.0 and notional_total <= 0.0:
                    continue
                entry_tf = '-'
                if intervals_set:
                    ordered_intervals = sorted(
                        {self._canonicalize_interval(iv) or str(iv).strip() for iv in intervals_set if str(iv).strip()},
                        key=_mw_interval_sort_key,
                    )
                    if ordered_intervals:
                        entry_tf = ', '.join(ordered_intervals)
                indicators = sorted(dict.fromkeys(trigger_union)) if trigger_union else []
                open_time_fmt = '-'
                if open_times:
                    try:
                        dt_candidates = [
                            self._parse_any_datetime(value) for value in open_times if self._parse_any_datetime(value)
                        ]
                    except Exception:
                        dt_candidates = []
                    if dt_candidates:
                        dt_candidates.sort()
                        open_time_fmt = self._format_display_time(dt_candidates[0])
                    else:
                        open_time_fmt = open_times[0]
                data_entry = {
                    'symbol': sym,
                    'qty': qty_total,
                    'margin_usdt': margin_total if margin_total > 0 else None,
                    'size_usdt': notional_total if notional_total > 0 else None,
                    'leverage': leverage_val,
                    'liquidation_price': liquidation_value,
                    'interval_display': entry_tf.split(',')[0].strip() if entry_tf and entry_tf != '-' else entry_tf,
                    'trigger_indicators': indicators,
                    'open_time': open_time_fmt,
                }
                primary_interval = entry_tf.split(',')[0].strip().lower() if entry_tf and entry_tf != '-' else None
                if primary_interval and primary_interval in interval_trigger_map:
                    indicators = sorted(dict.fromkeys(interval_trigger_map.get(primary_interval) or []))
                positions_map[key] = {
                    'symbol': sym,
                    'side_key': side_key,
                    'entry_tf': entry_tf,
                    'open_time': open_time_fmt,
                    'close_time': '-',
                    'status': 'Active',
                    'data': data_entry,
                    'indicators': indicators,
                    'stop_loss_enabled': self._position_stop_loss_enabled(sym, side_key),
                    'allocations': copy.deepcopy(allocations),
                    'leverage': leverage_val,
                    'liquidation_price': liquidation_value,
                }
                tracked_keys.add(key)
        except Exception:
            pass

        acct_upper = str(acct or '').upper()
        if acct_upper.startswith('FUT'):
            try:
                raw_entries = []
                for row in base_rows:
                    try:
                        raw_entry = dict(row.get('raw_position') or {})
                    except Exception:
                        raw_entry = {}
                    sym_val = str(raw_entry.get('symbol') or row.get('symbol') or '').strip().upper()
                    if not sym_val:
                        continue
                    if not raw_entry:
                        try:
                            qty_val = float(row.get('qty') or 0.0)
                        except Exception:
                            qty_val = 0.0
                        side_key = str(row.get('side_key') or '').upper()
                        qty_signed = -abs(qty_val) if side_key == 'S' else abs(qty_val)
                        try:
                            margin_balance_fallback = float(row.get('margin_balance') or 0.0)
                        except Exception:
                            margin_balance_fallback = 0.0
                        if margin_balance_fallback <= 0.0:
                            try:
                                margin_balance_fallback = float(row.get('margin_usdt') or 0.0) + float(row.get('pnl_value') or 0.0)
                            except Exception:
                                margin_balance_fallback = float(row.get('margin_usdt') or 0.0)
                        raw_entry = {
                            'symbol': sym_val,
                            'positionAmt': qty_signed,
                            'markPrice': row.get('mark'),
                            'isolatedWallet': margin_balance_fallback if margin_balance_fallback > 0.0 else row.get('margin_usdt'),
                            'initialMargin': row.get('margin_usdt'),
                            'marginBalance': margin_balance_fallback,
                            'maintMargin': row.get('maint_margin'),
                            'marginRatio': row.get('margin_ratio'),
                            'unRealizedProfit': row.get('pnl_value'),
                            'updateTime': row.get('update_time'),
                            'leverage': row.get('leverage'),
                            'notional': row.get('size_usdt'),
                        }
                    else:
                        raw_entry['symbol'] = sym_val
                    raw_entries.append(raw_entry)
                for p in raw_entries:
                    try:
                        sym = str(p.get('symbol') or '').strip().upper()
                        if not sym:
                            continue
                        amt = float(p.get('positionAmt') or 0.0)
                        if abs(amt) <= 0.0:
                            continue
                        mark = float(p.get('markPrice') or 0.0)
                        value = abs(amt) * mark if mark else 0.0
                        side_key = 'L' if amt > 0 else 'S'
                        entry_price = float(p.get('entryPrice') or 0.0)
                        iso_wallet = float(p.get('isolatedWallet') or 0.0)
                        margin_usdt = float(p.get('initialMargin') or 0.0)
                        try:
                            position_initial = float(p.get('positionInitialMargin') or 0.0)
                        except Exception:
                            position_initial = 0.0
                        try:
                            open_order_margin = float(p.get('openOrderMargin') or p.get('openOrderInitialMargin') or 0.0)
                        except Exception:
                            open_order_margin = 0.0
                        pnl = float(p.get('unRealizedProfit') or 0.0)
                        lev_val_raw = float(p.get('leverage') or 0.0)
                        leverage = int(lev_val_raw) if lev_val_raw else None
                        if margin_usdt <= 0.0 and iso_wallet > 0.0:
                            try:
                                margin_usdt = iso_wallet - pnl
                            except Exception:
                                margin_usdt = iso_wallet
                            if margin_usdt <= 0.0:
                                margin_usdt = iso_wallet
                        if margin_usdt <= 0.0 and entry_price > 0.0 and leverage:
                            margin_usdt = abs(amt) * entry_price / max(leverage, 1)
                        if margin_usdt <= 0.0 and leverage and leverage > 0 and value > 0.0:
                            margin_usdt = value / max(leverage, 1)
                        margin_usdt = max(margin_usdt, 0.0)
                        if position_initial > 0.0 or open_order_margin > 0.0:
                            margin_usdt = max(0.0, position_initial) + max(0.0, open_order_margin)
                        try:
                            maint = float(p.get('maintMargin') or p.get('maintenanceMargin') or 0.0)
                        except Exception:
                            maint = 0.0
                        try:
                            initial_margin_val = float(p.get('initialMargin') or 0.0)
                        except Exception:
                            initial_margin_val = 0.0
                        try:
                            maint_rate_val = float(p.get('maintMarginRate') or p.get('maintenanceMarginRate') or 0.0)
                        except Exception:
                            maint_rate_val = 0.0
                        if maint <= 0.0 and maint_rate_val > 0.0 and value > 0.0:
                            maint = abs(value) * maint_rate_val
                        baseline_margin = maint if maint > 0.0 else initial_margin_val
                        if baseline_margin <= 0.0 and margin_usdt > 0.0 and leverage:
                            baseline_margin = margin_usdt / max(leverage, 1)
                        if baseline_margin <= 0.0:
                            baseline_margin = margin_usdt
                        if position_initial > 0.0:
                            baseline_margin = position_initial
                        try:
                            margin_balance_val = float(p.get('marginBalance') or 0.0)
                        except Exception:
                            margin_balance_val = 0.0
                        if margin_balance_val <= 0.0 and iso_wallet > 0.0:
                            margin_balance_val = iso_wallet
                        if margin_balance_val <= 0.0:
                            margin_balance_val = margin_usdt + pnl
                        if margin_balance_val <= 0.0:
                            margin_balance_val = margin_usdt
                        margin_balance_val = max(margin_balance_val, 0.0)
                        try:
                            wallet_balance_val = float(p.get('walletBalance') or 0.0)
                        except Exception:
                            wallet_balance_val = 0.0
                        if wallet_balance_val <= 0.0:
                            wallet_balance_val = margin_balance_val if margin_balance_val > 0.0 else margin_usdt + pnl
                        if wallet_balance_val <= 0.0 and iso_wallet > 0.0:
                            wallet_balance_val = iso_wallet
                        wallet_balance_val = max(wallet_balance_val, 0.0)
                        raw_margin_ratio_val = None
                        for ratio_key in ('marginRatioRaw', 'marginRatio', 'margin_ratio'):
                            val = p.get(ratio_key)
                            if val in (None, '', 0, 0.0):
                                continue
                            try:
                                raw_margin_ratio_val = float(val)
                                break
                            except Exception:
                                continue
                        calc_ratio = normalize_margin_ratio(p.get('marginRatioCalc')) if p.get('marginRatioCalc') is not None else 0.0
                        margin_ratio = normalize_margin_ratio(raw_margin_ratio_val)
                        if margin_ratio <= 0.0:
                            margin_ratio = calc_ratio
                        if (margin_ratio <= 0.0 or not margin_ratio) and wallet_balance_val > 0:
                            unrealized_loss = abs(pnl) if pnl < 0 else 0.0
                            margin_ratio = ((baseline_margin + open_order_margin + unrealized_loss) / wallet_balance_val) * 100.0
                        roi_pct = 0.0
                        if margin_usdt > 0:
                            try:
                                roi_pct = (pnl / margin_usdt) * 100.0
                            except Exception:
                                roi_pct = 0.0
                            pnl_roi = f"{pnl:+.2f} USDT ({roi_pct:+.2f}%)"
                        else:
                            pnl_roi = f"{pnl:+.2f} USDT"
                        try:
                            update_time = int(float(p.get('updateTime') or p.get('update_time') or 0))
                        except Exception:
                            update_time = 0
                        try:
                            liquidation_price = float(
                                p.get('liquidationPrice')
                                or p.get('liqPrice')
                                or prev_data_entry.get('liquidation_price')
                                or 0.0
                            )
                        except Exception:
                            liquidation_price = 0.0
                        stop_loss_enabled = False
                        if side_key in ('L', 'S'):
                            try:
                                stop_loss_enabled = self._position_stop_loss_enabled(sym, side_key)
                            except Exception:
                                stop_loss_enabled = False
                        data = {
                            'symbol': sym,
                            'qty': abs(amt),
                            'mark': mark,
                            'size_usdt': value,
                            'margin_usdt': margin_usdt,
                            'margin_balance': margin_balance_val,
                            'wallet_balance': wallet_balance_val,
                            'maint_margin': maint,
                            'open_order_margin': open_order_margin,
                            'margin_ratio': margin_ratio,
                            'margin_ratio_raw': normalize_margin_ratio(raw_margin_ratio_val),
                            'margin_ratio_calc': calc_ratio,
                            'pnl_roi': pnl_roi,
                            'pnl_value': pnl,
                            'roi_percent': roi_pct,
                            'side_key': side_key,
                            'update_time': update_time,
                            'entry_price': entry_price if entry_price > 0 else None,
                            'leverage': leverage,
                            'liquidation_price': liquidation_price if liquidation_price > 0 else None,
                            'interval': None,
                            'interval_display': None,
                            'open_time': None,
                        }
                        rec = positions_map.get((sym, side_key))
                        prev_data_entry = {}
                        prev_indicators: list[str] = []
                        if rec and isinstance(rec, dict):
                            try:
                                prev_data_entry = dict(rec.get('data') or {})
                            except Exception:
                                prev_data_entry = {}
                            try:
                                prev_indicators = list(rec.get('indicators') or [])
                            except Exception:
                                prev_indicators = []
                        row_triggers = _resolve_trigger_indicators(
                            prev_data_entry.get('trigger_indicators'),
                            prev_data_entry.get('trigger_desc'),
                        )
                        if not row_triggers and prev_indicators:
                            cleaned = [str(t).strip() for t in prev_indicators if str(t).strip()]
                            if cleaned:
                                row_triggers = sorted(dict.fromkeys(cleaned))
                        if rec is None:
                            rec = {
                                'symbol': sym,
                                'side_key': side_key,
                                'entry_tf': '-',
                                'open_time': '-',
                                'close_time': '-',
                                'status': 'Active',
                            }
                        else:
                            rec = dict(rec)
                        rec['data'] = data
                        rec['leverage'] = data.get('leverage')
                        rec['liquidation_price'] = data.get('liquidation_price')
                        rec['status'] = 'Active'
                        rec['close_time'] = '-'
                        if (not rec.get('entry_tf') or rec['entry_tf'] == '-') and data.get('interval_display'):
                            rec['entry_tf'] = data['interval_display']
                        allocations_existing = _collect_allocations(sym, side_key)
                        interval_display: dict[str, str] = {}
                        interval_lookup: dict[str, str] = {}
                        entry_times_map = getattr(self, '_entry_times_by_iv', {}) or {}
                        intervals_from_alloc: set[str] = set()
                        interval_trigger_map: dict[str, set[str]] = {}
                        trigger_union: set[str] = set()
                        if allocations_existing:
                            rec['allocations'] = allocations_existing
                            for alloc in allocations_existing:
                                if not isinstance(alloc, dict):
                                    continue
                                iv_disp = alloc.get("interval_display") or alloc.get("interval")
                                iv_raw = alloc.get("interval")
                                status_flag = str(alloc.get("status") or "Active").strip().lower()
                                try:
                                    qty_val = abs(float(alloc.get("qty") or 0.0))
                                except Exception:
                                    qty_val = None
                                is_active = status_flag not in {"closed", "error"}
                                if qty_val is not None and qty_val <= 0.0:
                                    qty_val = 0.0
                                if qty_val:
                                    is_active = True
                                normalized_iv = ""
                                key_iv = "-"
                                if iv_disp:
                                    iv_text = str(iv_disp).strip()
                                    if iv_text:
                                        try:
                                            canon_iv = self._canonicalize_interval(iv_text)
                                        except Exception:
                                            canon_iv = None
                                        normalized_iv = (canon_iv or iv_text).strip()
                                        if normalized_iv:
                                            key_iv = normalized_iv.lower()
                                            if is_active:
                                                intervals_from_alloc.add(normalized_iv)
                                            if key_iv and (canon_iv or iv_text):
                                                interval_display.setdefault(key_iv, canon_iv or iv_text)
                                                lookup_val = str(iv_raw or iv_text).strip()
                                                if lookup_val:
                                                    interval_lookup.setdefault(key_iv, lookup_val)
                                normalized_triggers = _resolve_trigger_indicators(
                                    alloc.get("trigger_indicators"),
                                    alloc.get("trigger_desc"),
                                )
                                if normalized_triggers:
                                    alloc["trigger_indicators"] = normalized_triggers
                                elif alloc.get("trigger_indicators"):
                                    alloc.pop("trigger_indicators", None)
                                if is_active and normalized_triggers:
                                    trigger_union.update(normalized_triggers)
                                    interval_trigger_map.setdefault(key_iv, set()).update(normalized_triggers)
                            if not data.get('trigger_desc'):
                                for alloc in allocations_existing:
                                    if not isinstance(alloc, dict):
                                        continue
                                    desc = alloc.get("trigger_desc")
                                    if desc:
                                        data['trigger_desc'] = desc
                                        break
                            if trigger_union:
                                indicators_union = sorted(dict.fromkeys(trigger_union))
                                rec['indicators'] = indicators_union
                                data['trigger_indicators'] = indicators_union
                            elif row_triggers:
                                rec['indicators'] = row_triggers
                                data['trigger_indicators'] = row_triggers
                        elif row_triggers:
                            rec['indicators'] = row_triggers
                            data['trigger_indicators'] = row_triggers
                        if not data.get('trigger_desc') and prev_data_entry.get('trigger_desc'):
                            data['trigger_desc'] = prev_data_entry.get('trigger_desc')
                        try:
                            getattr(self, "_pending_close_times", {}).pop((sym, side_key), None)
                        except Exception:
                            pass
                        symbol_variants = [sym]
                        sym_lower = sym.lower()
                        if sym_lower and sym_lower != sym:
                            symbol_variants.append(sym_lower)
                        entry_intervals_map = getattr(self, "_entry_intervals", {}) or {}
                        intervals_tracked = set()
                        try:
                            for (sym_key, side_key_key, iv_key), ts in entry_times_map.items():
                                if sym_key not in symbol_variants or side_key_key != side_key or not ts or not iv_key:
                                    continue
                                iv_text = str(iv_key).strip()
                                if not iv_text:
                                    continue
                                try:
                                    canon_iv = self._canonicalize_interval(iv_text)
                                except Exception:
                                    canon_iv = None
                                interval_norm = canon_iv or iv_text
                                if intervals_from_alloc and interval_norm not in intervals_from_alloc:
                                    continue
                                key_iv = interval_norm.strip().lower()
                                if key_iv:
                                    interval_display.setdefault(key_iv, interval_norm)
                                    interval_lookup.setdefault(key_iv, iv_text)
                        except Exception:
                            pass
                        for sym_variant in symbol_variants:
                            side_map = entry_intervals_map.get(sym_variant)
                            if not isinstance(side_map, dict):
                                continue
                            bucket = side_map.get(side_key)
                            if not isinstance(bucket, set):
                                continue
                            for iv in bucket:
                                iv_text = str(iv).strip()
                                if not iv_text:
                                    continue
                                try:
                                    canon_iv = self._canonicalize_interval(iv_text)
                                except Exception:
                                    canon_iv = None
                                interval_norm = canon_iv or iv_text
                                if intervals_from_alloc and interval_norm not in intervals_from_alloc:
                                    continue
                                key_iv = interval_norm.strip().lower()
                                if key_iv:
                                    interval_display.setdefault(key_iv, interval_norm)
                                    interval_lookup.setdefault(key_iv, iv_text)
                                    intervals_tracked.add(interval_norm)
                        metadata = getattr(self, "_engine_indicator_map", {}) or {}
                        for meta in metadata.values():
                            if not isinstance(meta, dict):
                                continue
                            if str(meta.get("symbol") or "").strip().upper() != sym:
                                continue
                            allowed_side = str(meta.get("side") or "BOTH").upper()
                            if side_key == "L" and allowed_side == "SELL":
                                continue
                            if side_key == "S" and allowed_side == "BUY":
                                continue
                            iv_text = str(meta.get("interval") or "").strip()
                            if not iv_text:
                                continue
                            try:
                                canon_iv = self._canonicalize_interval(iv_text)
                            except Exception:
                                canon_iv = None
                            interval_norm = canon_iv or iv_text
                            if intervals_from_alloc and interval_norm not in intervals_from_alloc:
                                continue
                            key_iv = interval_norm.strip().lower()
                            if key_iv:
                                interval_display.setdefault(key_iv, interval_norm)
                                interval_lookup.setdefault(key_iv, iv_text)
                        if not interval_display and intervals_from_alloc:
                            for iv_norm in intervals_from_alloc:
                                if not iv_norm:
                                    continue
                                key_iv = str(iv_norm).strip().lower()
                                if not key_iv:
                                    continue
                                try:
                                    canon_iv = self._canonicalize_interval(iv_norm)
                                except Exception:
                                    canon_iv = None
                                interval_display.setdefault(key_iv, canon_iv or str(iv_norm))
                                interval_lookup.setdefault(key_iv, str(iv_norm))
                        ordered_keys: list[str] = []
                        primary_interval_key = None
                        if interval_display:
                            ordered_keys = sorted(interval_display.keys(), key=_mw_interval_sort_key)
                            rec['entry_tf'] = ', '.join(
                                interval_display[key] for key in ordered_keys if interval_display[key]
                            )
                            if ordered_keys:
                                primary_interval_key = ordered_keys[0]
                        else:
                            rec['entry_tf'] = '-'
                        if primary_interval_key:
                            data['interval_display'] = interval_display.get(primary_interval_key)
                            data['interval'] = interval_lookup.get(primary_interval_key) or interval_display.get(primary_interval_key)
                        else:
                            if not data.get('interval_display') and rec.get('entry_tf') and rec.get('entry_tf') != '-':
                                data['interval_display'] = rec.get('entry_tf')
                                data['interval'] = rec.get('entry_tf')

                        if (not rec.get('entry_tf') or rec['entry_tf'] == '-') and intervals_tracked:
                            try:
                                intervals_active = sorted(
                                    {self._canonicalize_interval(iv) or str(iv).strip() for iv in intervals_tracked if str(iv).strip()},
                                    key=_mw_interval_sort_key,
                                )
                                if intervals_active:
                                    rec['entry_tf'] = ', '.join(intervals_active)
                                    if not data.get('interval_display'):
                                        data['interval_display'] = intervals_active[0]
                                        data['interval'] = intervals_active[0]
                            except Exception:
                                pass
                        if not data.get('interval_display') and rec.get('entry_tf') and rec['entry_tf'] != '-':
                            first_iv = rec['entry_tf'].split(',')[0].strip()
                            if first_iv:
                                data['interval_display'] = first_iv
                                data['interval'] = first_iv
                        open_times = []
                        ordered_lookup = [
                            interval_lookup.get(key) or interval_display.get(key)
                            for key in (ordered_keys if interval_display else [])
                        ]
                        # Prefer explicit allocation open times first.
                        for alloc in allocations_existing or []:
                            if not isinstance(alloc, dict):
                                continue
                            alloc_open = alloc.get("open_time")
                            if not alloc_open:
                                continue
                            dt_obj = self._parse_any_datetime(alloc_open)
                            if dt_obj:
                                try:
                                    epoch = dt_obj.timestamp()
                                except Exception:
                                    epoch = None
                                if epoch is not None:
                                    open_times.append((epoch, dt_obj))
                        for iv in ordered_lookup:
                            if not iv:
                                continue
                            ts = entry_times_map.get((sym, side_key, iv))
                            dt_obj = self._parse_any_datetime(ts)
                            if dt_obj:
                                try:
                                    epoch = dt_obj.timestamp()
                                except Exception:
                                    epoch = None
                                if epoch is not None:
                                    open_times.append((epoch, dt_obj))
                        if not open_times:
                            entry_time_map = getattr(self, '_entry_times', {}) if hasattr(self, '_entry_times') else {}
                            base_ts = None
                            for sym_variant in symbol_variants:
                                base_ts = entry_time_map.get((sym_variant, side_key))
                                if base_ts is not None:
                                    break
                            dt_obj = self._parse_any_datetime(base_ts)
                            if dt_obj:
                                try:
                                    epoch = dt_obj.timestamp()
                                except Exception:
                                    epoch = None
                                if epoch is not None:
                                    open_times.append((epoch, dt_obj))
                        if not open_times and data.get('update_time'):
                            dt_obj = self._parse_any_datetime(data.get('update_time'))
                            if dt_obj:
                                try:
                                    epoch = dt_obj.timestamp()
                                except Exception:
                                    epoch = None
                                if epoch is not None:
                                    open_times.append((epoch, dt_obj))
                        if not open_times and allocations_existing:
                            for alloc in allocations_existing:
                                if not isinstance(alloc, dict):
                                    continue
                                alloc_open = alloc.get("open_time")
                                if not alloc_open:
                                    continue
                                dt_obj = self._parse_any_datetime(alloc_open)
                                if dt_obj:
                                    try:
                                        epoch = dt_obj.timestamp()
                                    except Exception:
                                        epoch = None
                                    if epoch is not None:
                                        open_times.append((epoch, dt_obj))
                            if open_times:
                                open_times.sort(key=lambda item: item[0])
                        if open_times:
                            open_times.sort(key=lambda item: item[0])
                            rec['open_time'] = self._format_display_time(open_times[0][1])
                            data['open_time'] = rec['open_time']
                        else:
                            entry_time_map = getattr(self, '_entry_times', {}) if hasattr(self, '_entry_times') else {}
                            base_open = None
                            for sym_variant in symbol_variants:
                                base_open = entry_time_map.get((sym_variant, side_key))
                                if base_open is not None:
                                    break
                            dt_obj = self._parse_any_datetime(base_open)
                            if dt_obj:
                                formatted = self._format_display_time(dt_obj)
                                rec['open_time'] = formatted
                                data['open_time'] = formatted
                        interval_list = [
                            interval_lookup.get(key) or interval_display.get(key)
                            for key in (ordered_keys if interval_display else [])
                            if (interval_lookup.get(key) or interval_display.get(key))
                        ]
                        primary_interval_key = None
                        if ordered_keys:
                            primary_interval_key = ordered_keys[0]
                        indicators_selected: list[str] = []
                        if trigger_union:
                            if primary_interval_key:
                                normalized_key = primary_interval_key
                                indicators_selected = sorted(
                                    dict.fromkeys(interval_trigger_map.get(normalized_key, []))
                                )
                            if not indicators_selected:
                                indicators_selected = sorted(dict.fromkeys(trigger_union))
                        if indicators_selected:
                            rec['indicators'] = indicators_selected
                            if rec.get('data'):
                                rec['data']['trigger_indicators'] = indicators_selected
                        elif rec.get('data', {}).get('trigger_indicators'):
                            rec['indicators'] = list(rec['data']['trigger_indicators'])
                        elif not rec.get('indicators'):
                            rec['indicators'] = []
                        rec['stop_loss_enabled'] = stop_loss_enabled
                        positions_map[(sym, side_key)] = rec
                    except Exception:
                        continue
            except Exception:
                pass

        self._update_position_history(positions_map)
        self._render_positions_table()
    except Exception as e:
        self.log(f"Positions render failed: {e}")


def _mw_update_position_history(self, positions_map: dict):
    try:
        if not hasattr(self, "_open_position_records"):
            self._open_position_records = {}
        if not hasattr(self, "_closed_position_records"):
            self._closed_position_records = []
        missing_counts = getattr(self, "_position_missing_counts", {})
        if not isinstance(missing_counts, dict):
            missing_counts = {}
        prev_records = getattr(self, "_open_position_records", {}) or {}
        candidates: list[tuple[str, str]] = []
        pending_close_map = getattr(self, "_pending_close_times", {})
        try:
            missing_grace_seconds = float(self.config.get("positions_missing_grace_seconds", 30) or 0.0)
        except Exception:
            missing_grace_seconds = 0.0
        missing_grace_seconds = max(0.0, missing_grace_seconds)
        for key, prev in prev_records.items():
            if key in positions_map:
                missing_counts.pop(key, None)
                continue
            count = missing_counts.get(key, 0) + 1
            missing_counts[key] = count
            try:
                threshold = int(self.config.get("positions_missing_threshold", 2) or 2)
            except Exception:
                threshold = 2
            threshold = max(1, threshold)
            try:
                if isinstance(pending_close_map, dict) and key in pending_close_map:
                    threshold = 1
            except Exception:
                try:
                    threshold = int(self.config.get("positions_missing_threshold", 2) or 2)
                except Exception:
                    threshold = 2
            if count >= threshold:
                if missing_grace_seconds > 0 and not (isinstance(pending_close_map, dict) and key in pending_close_map):
                    open_val = None
                    if isinstance(prev, dict):
                        open_val = prev.get("open_time")
                        if not open_val:
                            open_val = (prev.get("data") or {}).get("open_time")
                        if not open_val:
                            open_val = (prev.get("data") or {}).get("update_time")
                    dt_obj = self._parse_any_datetime(open_val)
                    if dt_obj is not None:
                        try:
                            age_seconds = time.time() - dt_obj.timestamp()
                        except Exception:
                            age_seconds = None
                        if age_seconds is not None and 0 <= age_seconds < missing_grace_seconds:
                            continue
                candidates.append(key)

        def _resolve_live_keys() -> set[tuple[str, str]] | None:
            if not candidates:
                return set()
            try:
                bw = getattr(self, "shared_binance", None)
                if bw is None:
                    api_key = ""
                    api_secret = ""
                    try:
                        api_key = (self.api_key_edit.text() or "").strip()
                        api_secret = (self.api_secret_edit.text() or "").strip()
                    except Exception:
                        pass
                    if api_key and api_secret:
                        try:
                            bw = self._create_binance_wrapper(
                                api_key=api_key,
                                api_secret=api_secret,
                                mode=self.mode_combo.currentText(),
                                account_type=self.account_combo.currentText(),
                                default_leverage=int(self.leverage_spin.value() or 1),
                                default_margin_mode=self.margin_mode_combo.currentText() or "Isolated",
                            )
                            self.shared_binance = bw
                        except Exception:
                            bw = None
                if bw is None:
                    return None
                live = set()
                try:
                    acct_text = self.account_combo.currentText()
                except Exception:
                    acct_text = str(self.config.get("account_type") or "")
                acct_upper = str(acct_text or "").upper()
                acct_is_futures = acct_upper.startswith("FUT")
                acct_is_spot = acct_upper.startswith("SPOT")

                # Only probe the relevant venue for the active account type. Spot keys
                # reuse the "L" side for long-only holdings, so include it in the spot
                # probe to avoid falsely auto-closing them when testnet snapshots omit
                # per-symbol rows.
                need_futures = acct_is_futures and any(side in ("L", "S") for _, side in candidates)
                need_spot = acct_is_spot and any(side in ("L", "S", "SPOT") for _, side in candidates)
                if need_futures:
                    try:
                        for pos in bw.list_open_futures_positions() or []:
                            sym = str(pos.get("symbol") or "").strip().upper()
                            if not sym:
                                continue
                            amt = float(pos.get("positionAmt") or 0.0)
                            if abs(amt) <= 0.0:
                                continue
                            side_key = "L" if amt > 0 else "S"
                            live.add((sym, side_key))
                    except Exception:
                        return None
                if need_spot:
                    try:
                        balances = bw.get_balances() or []
                        for bal in balances:
                            asset = bal.get("asset")
                            free = float(bal.get("free") or 0.0)
                            locked = float(bal.get("locked") or 0.0)
                            total = free + locked
                            if not asset or total <= 0:
                                continue
                            sym = f"{asset}USDT"
                            sym_upper = sym.strip().upper()
                            live.add((sym_upper, "SPOT"))
                            live.add((sym_upper, "L"))
                    except Exception:
                        pass
                return live
            except Exception:
                return None

        live_keys = _resolve_live_keys() if candidates else set()
        # Default to True: if a position disappears from the exchange snapshot, record it as closed history.
        allow_missing_autoclose = bool(self.config.get("positions_missing_autoclose", True))

        def _lookup_force_liquidation(symbol: str, side_key: str, update_hint_ms: int | None = None) -> dict | None:
            """Return metadata about a recent forced liquidation order for the given symbol/side."""
            try:
                bw = getattr(self, "shared_binance", None)
                if bw is None or not hasattr(bw, "get_recent_force_orders"):
                    return None
                params: dict[str, object] = {"symbol": symbol, "limit": 20}
                if update_hint_ms:
                    try:
                        params["start_time"] = max(0, int(update_hint_ms) - 900_000)
                    except Exception:
                        pass
                orders = bw.get_recent_force_orders(**params) or []
                if not orders:
                    return None
                expected_side = "SELL" if side_key == "L" else "BUY"
                now_ms = int(time.time() * 1000)
                for order in reversed(orders):
                    if not isinstance(order, dict):
                        continue
                    order_side = str(order.get("side") or "").upper()
                    if order_side != expected_side:
                        continue
                    try:
                        order_time = int(float(order.get("updateTime") or order.get("time") or 0))
                    except Exception:
                        order_time = 0
                    if order_time and abs(now_ms - order_time) > 900_000:
                        continue
                    qty_val = 0.0
                    for qty_key in ("executedQty", "origQty"):
                        val = order.get(qty_key)
                        if val in (None, "", 0, 0.0):
                            continue
                        try:
                            qty_val = abs(float(val))
                        except Exception:
                            qty_val = 0.0
                        if qty_val > 0:
                            break
                    if qty_val <= 0.0:
                        continue
                    price_val = 0.0
                    for price_key in ("avgPrice", "price"):
                        val = order.get(price_key)
                        if val in (None, "", 0, 0.0):
                            continue
                        try:
                            price_val = float(val)
                        except Exception:
                            price_val = 0.0
                        if price_val > 0.0:
                            break
                    if price_val <= 0.0:
                        continue
                    return {
                        "close_price": price_val,
                        "qty": qty_val,
                        "time": order_time or now_ms,
                        "raw": order,
                    }
            except Exception:
                return None
            return None

        confirmed_closed: list[tuple[str, str]] = []
        for key in candidates:
            if live_keys is None or key in live_keys:
                if key in prev_records:
                    positions_map.setdefault(key, prev_records[key])
                missing_counts[key] = 0
            else:
                if allow_missing_autoclose:
                    confirmed_closed.append(key)
                else:
                    # Drop stale entries when not auto-closing; rely on live snapshot.
                    prev_records.pop(key, None)
                    missing_counts.pop(key, None)

        if confirmed_closed:
            from datetime import datetime as _dt
            close_time_map = getattr(self, "_pending_close_times", {})
            for key in confirmed_closed:
                rec = prev_records.get(key)
                if not rec:
                    continue
                sym, side_key = key
                snap = copy.deepcopy(rec)
                data_prev = dict(rec.get("data") or {})
                close_status = "Closed"
                qty_reported = None
                margin_reported = None
                pnl_reported = None
                roi_reported = None
                close_price_reported = None
                entry_price_reported = None
                leverage_reported = None
                close_fmt = None
                close_raw = close_time_map.pop(key, None) if isinstance(close_time_map, dict) else None
                if close_raw:
                    dt_obj = self._parse_any_datetime(close_raw)
                    if dt_obj:
                        close_fmt = self._format_display_time(dt_obj)
                if close_fmt is None:
                    close_fmt = self._format_display_time(_dt.now().astimezone())
                if "stop_loss_enabled" not in snap:
                    snap["stop_loss_enabled"] = bool(rec.get("stop_loss_enabled"))
                try:
                    alloc_entries = copy.deepcopy(getattr(self, "_entry_allocations", {}).get(key, [])) or []
                except Exception:
                    alloc_entries = []
                entry_price_val = 0.0
                margin_prev = float(data_prev.get("margin_usdt") or 0.0)
                size_prev = float(data_prev.get("size_usdt") or 0.0)
                leverage_prev = data_prev.get("leverage")
                if isinstance(leverage_prev, (int, float)) and leverage_prev > 0:
                    leverage_reported = int(float(leverage_prev))
                else:
                    leverage_reported = None
                if alloc_entries:
                    num = 0.0
                    den = 0.0
                    for entry in alloc_entries:
                        if not isinstance(entry, dict):
                            continue
                        try:
                            qty_val = abs(float(entry.get("qty") or 0.0))
                            price_val = float(entry.get("entry_price") or data_prev.get("entry_price") or 0.0)
                        except Exception:
                            qty_val = 0.0
                            price_val = 0.0
                        if qty_val > 0 and price_val > 0:
                            num += price_val * qty_val
                            den += qty_val
                        try:
                            margin_prev = max(margin_prev, float(entry.get("margin_usdt") or 0.0))
                        except Exception:
                            pass
                        try:
                            size_prev = max(size_prev, float(entry.get("notional") or entry.get("size_usdt") or size_prev or 0.0))
                        except Exception:
                            pass
                    if den > 0:
                        entry_price_val = num / den
                if entry_price_val <= 0:
                    try:
                        entry_price_val = float(data_prev.get("entry_price") or 0.0)
                    except Exception:
                        entry_price_val = 0.0
                update_hint = None
                try:
                    update_hint = int(float(data_prev.get("update_time") or 0))
                except Exception:
                    update_hint = None
                liquidation_meta = None
                if side_key in ("L", "S"):
                    liquidation_meta = _lookup_force_liquidation(sym, side_key, update_hint)
                if liquidation_meta:
                    close_status = "Liquidated"
                    snap["close_reason"] = "Liquidation"
                    liquidation_time = liquidation_meta.get("time")
                    if liquidation_time:
                        try:
                            close_fmt = self._format_display_time(_dt.fromtimestamp(int(liquidation_time) / 1000.0).astimezone())
                        except Exception:
                            pass
                    close_price_reported = float(liquidation_meta.get("close_price") or 0.0)
                    qty_reported = float(liquidation_meta.get("qty") or 0.0)
                    if entry_price_val > 0:
                        entry_price_reported = entry_price_val
                    side_mult = 1.0 if side_key == "L" else -1.0
                    if entry_price_reported and qty_reported:
                        pnl_calc = (close_price_reported - entry_price_reported) * qty_reported * side_mult
                        pnl_reported = pnl_calc
                    if margin_prev <= 0.0 and size_prev > 0.0 and leverage_prev:
                        try:
                            lev_val = float(leverage_prev)
                            if lev_val > 0:
                                margin_prev = size_prev / lev_val
                        except Exception:
                            pass
                    if margin_prev > 0.0:
                        margin_reported = margin_prev
                    if pnl_reported is not None and margin_reported:
                        try:
                            roi_reported = (pnl_reported / margin_reported) * 100.0
                        except Exception:
                            roi_reported = None
                snap["status"] = close_status
                snap["close_time"] = close_fmt
                snap_data = snap.setdefault("data", {})
                if not snap_data and data_prev:
                    snap_data.update(data_prev)
                if qty_reported is None:
                    try:
                        qty_prev = float(data_prev.get("qty") or 0.0)
                        if abs(qty_prev) > 0.0:
                            qty_reported = abs(qty_prev)
                    except Exception:
                        qty_reported = None
                if margin_reported is None:
                    try:
                        margin_val_prev = float(data_prev.get("margin_usdt") or 0.0)
                        if margin_val_prev > 0.0:
                            margin_reported = margin_val_prev
                    except Exception:
                        margin_reported = None
                if pnl_reported is None:
                    try:
                        pnl_prev = float(data_prev.get("pnl_value") or 0.0)
                        pnl_reported = pnl_prev
                    except Exception:
                        pnl_reported = None
                if roi_reported is None:
                    try:
                        roi_prev = float(data_prev.get("roi_percent") or 0.0)
                        roi_reported = roi_prev if roi_prev != 0.0 else None
                    except Exception:
                        roi_reported = None
                if close_price_reported is None:
                    try:
                        close_price_prev = float(data_prev.get("close_price") or 0.0)
                        if close_price_prev > 0.0:
                            close_price_reported = close_price_prev
                    except Exception:
                        close_price_reported = None
                if entry_price_reported is None and entry_price_val > 0:
                    entry_price_reported = entry_price_val
                if leverage_reported is None and leverage_prev:
                    try:
                        lev_int = int(float(leverage_prev))
                        if lev_int > 0:
                            leverage_reported = lev_int
                    except Exception:
                        leverage_reported = None
                if qty_reported is not None and qty_reported > 0:
                    snap_data["qty"] = qty_reported
                if margin_reported is not None and margin_reported > 0:
                    snap_data["margin_usdt"] = margin_reported
                if pnl_reported is not None:
                    snap_data["pnl_value"] = pnl_reported
                    if margin_reported and margin_reported > 0:
                        roi_calc = roi_reported if roi_reported is not None else (pnl_reported / margin_reported) * 100.0
                        roi_reported = roi_calc
                        snap_data["roi_percent"] = roi_calc
                        snap_data["pnl_roi"] = f"{pnl_reported:+.2f} USDT ({roi_calc:+.2f}%)"
                    else:
                        snap_data["pnl_roi"] = f"{pnl_reported:+.2f} USDT"
                if roi_reported is not None and "roi_percent" not in snap_data:
                    snap_data["roi_percent"] = roi_reported
                if close_price_reported is not None and close_price_reported > 0:
                    snap_data["close_price"] = close_price_reported
                if entry_price_reported is not None and entry_price_reported > 0:
                    snap_data.setdefault("entry_price", entry_price_reported)
                if leverage_reported:
                    snap_data["leverage"] = leverage_reported
                if alloc_entries:
                    for entry in alloc_entries:
                        if isinstance(entry, dict):
                            normalized_triggers = _resolve_trigger_indicators(entry.get("trigger_indicators"), entry.get("trigger_desc"))
                            if normalized_triggers:
                                entry["trigger_indicators"] = normalized_triggers
                            elif entry.get("trigger_indicators"):
                                entry.pop("trigger_indicators", None)
                    base_data = rec.get("data", {}) or {}
                    base_qty = float(base_data.get("qty") or 0.0)
                    base_margin = float(base_data.get("margin_usdt") or 0.0)
                    base_pnl = float(base_data.get("pnl_value") or 0.0)
                    base_size = float(base_data.get("size_usdt") or 0.0)
                    total_qty = 0.0
                    for entry in alloc_entries:
                        try:
                            total_qty += abs(float(entry.get("qty") or 0.0))
                        except Exception:
                            continue
                    if total_qty <= 0 and base_qty > 0:
                        total_qty = base_qty
                    count_entries = len([entry for entry in alloc_entries if isinstance(entry, dict)])
                    for entry in alloc_entries:
                        if not isinstance(entry, dict):
                            continue
                        entry["status"] = close_status
                        entry["close_time"] = close_fmt
                        try:
                            qty_val = abs(float(entry.get("qty") or 0.0))
                        except Exception:
                            qty_val = 0.0
                        ratio = (qty_val / total_qty) if total_qty > 0 else (1.0 / count_entries if count_entries else 0.0)
                        if ratio <= 0 and count_entries:
                            ratio = 1.0 / count_entries
                        if float(entry.get("margin_usdt") or 0.0) <= 0 and base_margin > 0:
                            entry["margin_usdt"] = base_margin * ratio
                        if float(entry.get("notional") or 0.0) <= 0 and base_size > 0:
                            entry["notional"] = base_size * ratio
                        if entry.get("pnl_value") is None:
                            if base_pnl and base_qty > 0 and qty_val > 0:
                                entry["pnl_value"] = base_pnl * (qty_val / base_qty)
                            elif base_pnl and ratio > 0:
                                entry["pnl_value"] = base_pnl * ratio
                            else:
                                entry["pnl_value"] = base_pnl
                    qty_dist_sum = 0.0
                    try:
                        qty_dist_sum = sum(abs(float(e.get("qty") or 0.0)) for e in alloc_entries if isinstance(e, dict))
                    except Exception:
                        qty_dist_sum = 0.0
                    if qty_dist_sum <= 0.0 and qty_reported is not None and qty_reported > 0:
                        qty_dist_sum = qty_reported
                    entries_count = len([entry for entry in alloc_entries if isinstance(entry, dict)])
                    for entry in alloc_entries:
                        if not isinstance(entry, dict):
                            continue
                        share = 0.0
                        try:
                            if qty_dist_sum and qty_dist_sum > 0:
                                share = abs(float(entry.get("qty") or 0.0)) / qty_dist_sum
                        except Exception:
                            share = 0.0
                        if share <= 0.0 and entries_count:
                            share = 1.0 / entries_count
                        if qty_reported is not None and qty_reported > 0 and share > 0:
                            entry["qty"] = qty_reported * share
                        if margin_reported is not None and margin_reported > 0 and share > 0:
                            entry["margin_usdt"] = margin_reported * share
                        if pnl_reported is not None and share > 0:
                            entry["pnl_value"] = pnl_reported * share
                        if close_price_reported is not None and close_price_reported > 0:
                            entry["close_price"] = close_price_reported
                        if entry_price_reported is not None and entry_price_reported > 0:
                            entry.setdefault("entry_price", entry_price_reported)
                        if leverage_reported:
                            entry["leverage"] = leverage_reported
                else:
                    alloc_entries = []
                if alloc_entries:
                    snap["allocations"] = alloc_entries
                self._closed_position_records.insert(0, snap)
                try:
                    registry = getattr(self, "_closed_trade_registry", None)
                    if registry is None:
                        registry = {}
                        self._closed_trade_registry = registry
                    registry_key = snap.get("ledger_id") or f"auto:{sym}:{side_key}:{close_fmt}"
                    def _safe_float_report(value):
                        try:
                            return float(value) if value is not None else None
                        except Exception:
                            return None
                    registry[registry_key] = {
                        "pnl_value": _safe_float_report(pnl_reported),
                        "margin_usdt": _safe_float_report(margin_reported),
                        "roi_percent": _safe_float_report(roi_reported),
                    }
                    if len(registry) > MAX_CLOSED_HISTORY:
                        excess = len(registry) - MAX_CLOSED_HISTORY
                        if excess > 0:
                            for old_key in list(registry.keys())[:excess]:
                                registry.pop(old_key, None)
                    try:
                        self._update_global_pnl_display(*self._compute_global_pnl_totals())
                    except Exception:
                        pass
                except Exception:
                    pass
                missing_counts.pop(key, None)
                try:
                    getattr(self, "_entry_allocations", {}).pop(key, None)
                except Exception:
                    pass
            if len(self._closed_position_records) > MAX_CLOSED_HISTORY:
                self._closed_position_records = self._closed_position_records[:MAX_CLOSED_HISTORY]

        self._open_position_records = positions_map
        self._position_missing_counts = missing_counts
        try:
            acct_flag = str(acct or "").upper()
        except Exception:
            acct_flag = ""
        self._positions_account_type = acct_flag
        self._positions_account_is_futures = "FUT" in acct_flag
    except Exception:
        pass

def _mw_positions_records_per_trade(self, open_records: dict, closed_records: list) -> list:
    raw_records: list[dict] = []
    metadata = getattr(self, "_engine_indicator_map", {}) or {}
    meta_map: dict[tuple[str, str], list[dict]] = {}
    for meta in metadata.values():
        if not isinstance(meta, dict):
            continue
        sym = str(meta.get("symbol") or "").strip().upper()
        if not sym:
            continue
        interval = str(meta.get("interval") or "").strip()
        side_cfg = str(meta.get("side") or "BOTH").upper()
        stop_enabled = bool(meta.get("stop_loss_enabled"))
        indicators = list(meta.get("indicators") or [])
        sides = []
        if side_cfg == "BUY":
            sides = ["L"]
        elif side_cfg == "SELL":
            sides = ["S"]
        else:
            sides = ["L", "S"]
        for side in sides:
            meta_map.setdefault((sym, side), []).append(
                {
                    "interval": interval,
                    "indicators": indicators,
                    "stop_loss_enabled": stop_enabled,
                }
            )

    def _normalize_interval(value):
        try:
            canon = self._canonicalize_interval(value)
        except Exception:
            canon = None
        if canon:
            return canon
        if isinstance(value, str):
            lowered = value.strip().lower()
            return lowered or None
        return None

    def _collect_allocations(rec: dict) -> list[dict]:
        allocs = rec.get("allocations") or []
        if isinstance(allocs, dict):
            allocs = list(allocs.values())
        if not isinstance(allocs, list):
            return []
        out: list[dict] = []
        for payload in allocs:
            if not isinstance(payload, dict):
                continue
            entry = copy.deepcopy(payload)
            interval = entry.get("interval")
            if interval is None and entry.get("interval_display"):
                interval = entry.get("interval_display")
            entry["interval"] = interval
            triggers_any = entry.get("trigger_indicators")
            if isinstance(triggers_any, dict):
                merged = []
                for value in triggers_any.values():
                    if isinstance(value, (list, tuple, set)):
                        merged.extend([str(v).strip() for v in value if str(v).strip()])
                    elif isinstance(value, str) and value.strip():
                        merged.append(value.strip())
                entry["trigger_indicators"] = merged or None
            out.append(entry)
        unique: list[dict] = []
        seen: dict[tuple, dict] = {}
        for entry in out:
            indicators_tuple = tuple(sorted(str(v).strip().lower() for v in (entry.get("trigger_indicators") or []) if str(v).strip()))
            key = (
                str(entry.get("ledger_id") or ""),
                str(entry.get("interval") or "").strip().lower(),
                indicators_tuple,
            )
            existing = seen.get(key)
            if existing:
                try:
                    existing["margin_usdt"] = max(float(existing.get("margin_usdt") or 0.0), float(entry.get("margin_usdt") or 0.0))
                    existing["qty"] = max(float(existing.get("qty") or 0.0), float(entry.get("qty") or 0.0))
                    existing["notional"] = max(float(existing.get("notional") or 0.0), float(entry.get("notional") or 0.0))
                except Exception:
                    pass
                continue
            if indicators_tuple:
                entry["trigger_indicators"] = list(indicators_tuple)
            seen[key] = entry
            unique.append(entry)
        return unique

    def _compute_trade_data(base_data: dict, allocation: dict | None, side_key: str, status: str) -> dict:
        data = dict(base_data)
        base_qty = float(base_data.get("qty") or 0.0)
        base_margin = float(base_data.get("margin_usdt") or 0.0)
        base_pnl = float(base_data.get("pnl_value") or 0.0)
        base_roi = float(base_data.get("roi_percent") or 0.0)
        base_size = float(base_data.get("size_usdt") or 0.0)
        mark = float(base_data.get("mark") or 0.0)
        entry_price = float(base_data.get("entry_price") or 0.0)
        leverage = int(base_data.get("leverage") or 0) if base_data.get("leverage") else 0
        base_margin_ratio = normalize_margin_ratio(base_data.get("margin_ratio"))
        base_margin_balance = float(base_data.get("margin_balance") or 0.0)
        base_maint_margin = float(base_data.get("maint_margin") or 0.0)

        qty = base_qty
        margin = base_margin
        notional = base_size
        status_lower = str(status or "").strip().lower()
        pnl = base_pnl
        margin_ratio = 0.0
        margin_balance_val = 0.0
        maint_margin_val = 0.0
        base_liq_price = None

        def _extract_liq_value(candidate):
            try:
                if candidate is None or candidate == "":
                    return None
                value = float(candidate)
                return value if value > 0.0 else None
            except Exception:
                return None

        for cand in (
            base_data.get("liquidation_price"),
            base_data.get("liquidationPrice"),
            base_data.get("liq_price"),
            base_data.get("liqPrice"),
        ):
            found = _extract_liq_value(cand)
            if found:
                base_liq_price = found
                break
        if not base_liq_price:
            raw_base = base_data.get("raw_position") if isinstance(base_data.get("raw_position"), dict) else None
            if raw_base:
                for cand in (
                    raw_base.get("liquidationPrice"),
                    raw_base.get("liqPrice"),
                ):
                    found = _extract_liq_value(cand)
                    if found:
                        base_liq_price = found
                        break

        if allocation:
            try:
                qty = abs(float(allocation.get("qty") or 0.0))
            except Exception:
                qty = max(base_qty, 0.0)
            try:
                entry_price_alloc = float(allocation.get("entry_price") or 0.0)
                if entry_price_alloc > 0:
                    entry_price = entry_price_alloc
            except Exception:
                pass
            try:
                leverage_alloc = int(allocation.get("leverage") or 0)
                if leverage_alloc:
                    leverage = leverage_alloc
            except Exception:
                pass
            try:
                margin = float(allocation.get("margin_usdt") or 0.0)
            except Exception:
                margin = 0.0
            try:
                notional = float(allocation.get("notional") or 0.0)
            except Exception:
                notional = 0.0
            if base_liq_price is None:
                for cand in (
                    allocation.get("liquidation_price"),
                    allocation.get("liquidationPrice"),
                    allocation.get("liq_price"),
                    allocation.get("liqPrice"),
                ):
                    found = _extract_liq_value(cand)
                    if found:
                        base_liq_price = found
                        break
            alloc_pnl = allocation.get("pnl_value")
            if alloc_pnl is not None:
                try:
                    pnl = float(alloc_pnl)
                except Exception:
                    pnl = base_pnl
            if allocation.get("status"):
                status_lower = str(allocation.get("status")).strip().lower()
        allocation_data = allocation if isinstance(allocation, dict) else {}
        margin_ratio = normalize_margin_ratio(allocation_data.get("margin_ratio"))
        try:
            margin_balance_val = float(allocation_data.get("margin_balance") or 0.0)
        except Exception:
            margin_balance_val = 0.0
        try:
            maint_margin_val = float(allocation_data.get("maint_margin") or 0.0)
        except Exception:
            maint_margin_val = 0.0

        qty = max(qty, 0.0)
        if notional <= 0:
            if entry_price > 0 and qty > 0:
                notional = entry_price * qty
            elif mark > 0 and qty > 0:
                notional = mark * qty
            elif base_size > 0 and base_qty > 0:
                notional = base_size * (qty / base_qty)
            else:
                notional = 0.0

        if margin <= 0:
            if leverage and leverage > 0 and entry_price > 0 and qty > 0:
                margin = (entry_price * qty) / leverage
            elif base_margin > 0 and base_qty > 0:
                margin = base_margin * (qty / base_qty)
            else:
                margin = 0.0
        margin = max(margin, 0.0)

        if status_lower == "active":
            if allocation is None or allocation.get("pnl_value") is None:
                direction = 1.0 if side_key == "L" else -1.0 if side_key == "S" else 0.0
                if direction != 0.0 and entry_price > 0 and mark > 0 and qty > 0:
                    pnl = direction * (mark - entry_price) * qty
                elif base_pnl and base_qty > 0:
                    pnl = base_pnl * (qty / base_qty)
        else:
            if allocation is None or allocation.get("pnl_value") is None:
                if base_pnl and base_qty > 0:
                    pnl = base_pnl * (qty / base_qty)
                else:
                    pnl = base_pnl

        roi_percent = (pnl / margin * 100.0) if margin > 0 else base_roi
        pnl_roi = f"{pnl:+.2f} USDT ({roi_percent:+.2f}%)" if margin > 0 else f"{pnl:+.2f} USDT"

        raw_position = base_data.get("raw_position") if isinstance(base_data.get("raw_position"), dict) else None
        if margin_ratio <= 0.0:
            margin_ratio = base_margin_ratio
        if margin_balance_val <= 0.0:
            margin_balance_val = base_margin_balance
        if maint_margin_val <= 0.0:
            maint_margin_val = base_maint_margin
        if margin_ratio <= 0.0 and raw_position is not None:
            snap_margin, snap_balance, snap_maint, snap_unreal_loss = _derive_margin_snapshot(
                raw_position,
                qty_hint=qty if qty > 0 else base_qty,
                entry_price_hint=entry_price if entry_price > 0 else base_data.get("entry_price") or 0.0,
            )
            if margin <= 0.0 and snap_margin > 0.0:
                margin = snap_margin
            if margin_balance_val <= 0.0 and snap_balance > 0.0:
                margin_balance_val = snap_balance
            if maint_margin_val <= 0.0 and snap_maint > 0.0:
                maint_margin_val = snap_maint
            if margin_ratio <= 0.0 and snap_balance > 0.0 and snap_maint > 0.0:
                margin_ratio = ((snap_maint + snap_unreal_loss) / snap_balance) * 100.0
        if margin_balance_val <= 0.0:
            margin_balance_val = margin + max(pnl, 0.0)
        margin_balance_val = max(margin_balance_val, 0.0)
        if margin_ratio <= 0.0 and margin_balance_val > 0 and maint_margin_val > 0.0:
            unrealized_loss = max(0.0, -pnl) if status_lower == "active" else 0.0
            margin_ratio = ((maint_margin_val + unrealized_loss) / margin_balance_val) * 100.0

        data.update({
            "qty": qty,
            "margin_usdt": margin,
            "pnl_value": pnl,
            "roi_percent": roi_percent,
            "pnl_roi": pnl_roi,
            "size_usdt": max(notional, 0.0),
            "margin_balance": max(margin_balance_val, 0.0),
            "maint_margin": max(0.0, maint_margin_val),
            "margin_ratio": max(margin_ratio, 0.0),
        })
        trigger_inds = []
        if allocation and isinstance(allocation.get("trigger_indicators"), (list, tuple, set)):
            trigger_inds = [str(ind).strip() for ind in allocation.get("trigger_indicators") if str(ind).strip()]
        elif isinstance(base_data.get("trigger_indicators"), (list, tuple, set)):
            trigger_inds = [str(ind).strip() for ind in base_data.get("trigger_indicators") if str(ind).strip()]
        if trigger_inds:
            trigger_inds = list(dict.fromkeys(trigger_inds))
            data["trigger_indicators"] = trigger_inds
        if entry_price > 0:
            data["entry_price"] = entry_price
        if leverage:
            data["leverage"] = leverage
        if base_liq_price:
            data["liquidation_price"] = base_liq_price
        if allocation and isinstance(allocation, dict) and allocation.get("trigger_desc"):
            data["trigger_desc"] = allocation.get("trigger_desc")
        elif base_data.get("trigger_desc") and not data.get("trigger_desc"):
            data["trigger_desc"] = base_data.get("trigger_desc")
        return data

    def _emit_entries(base_rec: dict, sym: str, side_key: str, meta_items: list[dict | None]) -> None:
        allocations = _collect_allocations(base_rec)
        base_data = dict(base_rec.get("data") or {})
        status_text = str(base_rec.get("status") or "Active")
        stop_loss_flag = bool(base_rec.get("stop_loss_enabled"))
        default_open = base_rec.get("open_time") or "-"
        default_close = base_rec.get("close_time") or "-"
        meta_items = meta_items or [None]

        def _interval_from_meta(meta: dict | None, fallback: str | None = None) -> str:
            if isinstance(meta, dict):
                label = meta.get("interval") or meta.get("interval_display")
                if label:
                    return str(label)
            if fallback:
                return str(fallback)
            return "-"

        def _build_entry(allocation: dict | None, interval_hint: str | None, meta: dict | None = None) -> None:
            entry = copy.deepcopy(base_rec)
            interval_label = interval_hint or entry.get("entry_tf") or "-"
            entry["entry_tf"] = interval_label or "-"
            if isinstance(allocation, dict):
                try:
                    entry["allocations"] = [copy.deepcopy(allocation)]
                except Exception:
                    entry["allocations"] = [dict(allocation)]
            else:
                entry["allocations"] = []
            alloc_status = str((allocation or {}).get("status") or status_text)
            entry["status"] = alloc_status
            if isinstance(meta, dict) and meta.get("stop_loss_enabled") is not None:
                entry["stop_loss_enabled"] = bool(meta.get("stop_loss_enabled"))
            else:
                entry["stop_loss_enabled"] = bool((allocation or {}).get("stop_loss_enabled", stop_loss_flag))
            alloc_data = _compute_trade_data(base_data, allocation, side_key, alloc_status)
            entry["data"] = alloc_data
            entry["leverage"] = alloc_data.get("leverage")
            entry["liquidation_price"] = alloc_data.get("liquidation_price")
            indicators = allocation.get("trigger_indicators") if isinstance(allocation, dict) else None
            if isinstance(indicators, (list, tuple, set)):
                entry["indicators"] = list(dict.fromkeys(str(t).strip() for t in indicators if str(t).strip()))
            elif isinstance(meta, dict):
                meta_inds = meta.get("indicators")
                if meta_inds:
                    entry["indicators"] = list(meta_inds)
            trig_inds = alloc_data.get("trigger_indicators")
            if trig_inds:
                entry["indicators"] = list(dict.fromkeys(trig_inds))
            open_hint = None
            close_hint = None
            if isinstance(allocation, dict):
                open_hint = allocation.get("open_time")
                close_hint = allocation.get("close_time")
            entry["open_time"] = open_hint or default_open
            entry["close_time"] = close_hint or default_close
            entry["stop_loss_enabled"] = bool(entry.get("stop_loss_enabled"))
            normalized_inds = _normalize_indicator_values(
                entry.get("indicators") or alloc_data.get("trigger_indicators")
            )
            if normalized_inds:
                entry["indicators"] = normalized_inds
                alloc_data["trigger_indicators"] = normalized_inds
            else:
                entry.pop("indicators", None)
                alloc_data.pop("trigger_indicators", None)

            aggregate_key = None
            if isinstance(allocation, dict):
                aggregate_key = (
                    allocation.get("trade_id")
                    or allocation.get("client_order_id")
                    or allocation.get("order_id")
                    or allocation.get("ledger_id")
                )
            if not aggregate_key:
                aggregate_key = (
                    entry.get("trade_id")
                    or entry.get("client_order_id")
                    or entry.get("order_id")
                    or entry.get("ledger_id")
                    or base_rec.get("ledger_id")
                )
            if not aggregate_key:
                aggregate_key = f"{sym}|{side_key}|{interval_label}|{entry.get('open_time')}"

            indicator_source = (
                alloc_data.get("trigger_indicators")
                or entry.get("indicators")
                or base_data.get("trigger_indicators")
            )
            indicator_values = _normalize_indicator_values(indicator_source)
            if indicator_values:
                for idx, indicator_name in enumerate(indicator_values):
                    clone = copy.deepcopy(entry)
                    clone_indicators = [indicator_name]
                    clone["indicators"] = clone_indicators
                    clone_data = dict(clone.get("data") or {})
                    clone_data["trigger_indicators"] = clone_indicators
                    clone["data"] = clone_data
                    clone_allocs: list[dict] = []
                    for alloc_payload in (clone.get("allocations") or []):
                        if not isinstance(alloc_payload, dict):
                            continue
                        alloc_clone = dict(alloc_payload)
                        alloc_clone["trigger_indicators"] = clone_indicators
                        clone_allocs.append(alloc_clone)
                    clone["allocations"] = clone_allocs
                    clone["_aggregate_key"] = f"{aggregate_key}|{indicator_name.lower()}"
                    clone["_aggregate_is_primary"] = True
                    raw_records.append(clone)
                return
            entry["indicators"] = []
            entry_data = dict(entry.get("data") or {})
            entry_data["trigger_indicators"] = []
            entry["data"] = entry_data
            entry["_aggregate_key"] = aggregate_key
            entry["_aggregate_is_primary"] = True
            raw_records.append(entry)

        if allocations:
            for alloc in allocations:
                interval_label = alloc.get("interval_display") or alloc.get("interval")
                norm_iv = _normalize_interval(interval_label)
                matching_meta = None
                if norm_iv is not None:
                    for meta in meta_items:
                        if isinstance(meta, dict) and _normalize_interval(meta.get("interval")) == norm_iv:
                            matching_meta = meta
                            break
                if matching_meta is None:
                    for meta in meta_items:
                        if meta is None:
                            matching_meta = None
                            break
                _build_entry(alloc, interval_label or norm_iv, matching_meta)
        else:
            # Fallback: synthesise entries based on metadata or the base record itself.
            fallback_intervals: list[str] = []
            for meta in meta_items:
                if isinstance(meta, dict) and meta.get("interval"):
                    fallback_intervals.append(_interval_from_meta(meta))
            if not fallback_intervals:
                entry_tf = base_rec.get("entry_tf")
                if isinstance(entry_tf, str) and entry_tf.strip():
                    fallback_intervals = [part.strip() for part in entry_tf.split(",") if part.strip()]
            if not fallback_intervals:
                fallback_intervals = ["-"]
            for idx, interval_label in enumerate(fallback_intervals):
                meta = None
                if idx < len(meta_items) and isinstance(meta_items[idx], dict):
                    meta = meta_items[idx]
                _build_entry(None, interval_label, meta)

    for (sym, side_key), rec in open_records.items():
        meta_items = meta_map.get((sym, side_key)) or [None]
        _emit_entries(rec, sym, side_key, meta_items)

    for rec in closed_records:
        sym = str(rec.get("symbol") or "").strip().upper()
        side_key = str(rec.get("side_key") or "").strip().upper()
        entry_tf = rec.get("entry_tf")
        meta_items: list[dict | None] = []
        if isinstance(entry_tf, str) and entry_tf.strip():
            parts = [part.strip() for part in entry_tf.split(",") if part.strip()]
            if parts:
                meta_items = [{"interval": part} for part in parts]
        if not meta_items:
            meta_items = [None]
        _emit_entries(rec, sym, side_key, meta_items)

    grouped: dict[tuple[str, str, str, tuple[str, ...]], dict[str, list[dict]]] = {}
    dedupe_tracker: dict[tuple[str, str, str, tuple[str, ...]], set[tuple]] = {}
    for entry in raw_records:
        try:
            symbol_key = str(entry.get("symbol") or "").strip().upper()
            side_key = str(entry.get("side_key") or "").strip().upper()
            interval_key = str(entry.get("entry_tf") or "").strip().lower()
            indicators_tuple = tuple(
                sorted(
                    str(ind or "").strip().lower()
                    for ind in (entry.get("indicators") or [])
                    if str(ind or "").strip()
                )
            )
            status_key = str(entry.get("status") or "").strip().lower() or "active"
            group_key = (symbol_key, side_key, interval_key, indicators_tuple)
            bucket = grouped.setdefault(group_key, {})
            status_bucket = bucket.setdefault(status_key, [])
            aggregate_key = entry.get("_aggregate_key")

            # Stronger duplicate guard: collapse identical slot records even when aggregate_key differs.
            data = entry.get("data") or {}
            dedupe_key = (
                status_key,
                str(entry.get("open_time") or data.get("open_time") or "").strip(),
                str(entry.get("close_time") or data.get("close_time") or "").strip(),
                round(float(data.get("qty") or 0.0), 10),
            )
            seen = dedupe_tracker.setdefault(group_key, set())
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            if aggregate_key and any(existing.get("_aggregate_key") == aggregate_key for existing in status_bucket):
                continue
            status_bucket.append(entry)
        except Exception:
            continue

    def _qty_key(entry: dict) -> float:
        try:
            return abs(float((entry.get("data") or {}).get("qty") or 0.0))
        except Exception:
            return 0.0

    def _close_time_key(entry: dict) -> datetime:
        data = entry.get("data") or {}
        close_val = data.get("close_time") or entry.get("close_time") or ""
        dt = None
        try:
            dt = self._parse_any_datetime(close_val)
        except Exception:
            dt = None
        if dt is None:
            try:
                dt = datetime.min.replace(tzinfo=datetime.now().astimezone().tzinfo)
            except Exception:
                dt = datetime.min
        return dt

    records = []
    for (_sym, _side, _interval, _indicators), status_map in grouped.items():
        if not isinstance(status_map, dict):
            continue
        active_entries = status_map.get("active") or status_map.get("open") or []
        if active_entries:
            chosen_active = max(active_entries, key=_qty_key)
            records.append(chosen_active)
        closed_entries = (status_map.get("closed") or [])[:]
        closed_entries.sort(key=_close_time_key, reverse=True)
        records.extend(closed_entries)
        for status_name, entries in status_map.items():
            if status_name in {"active", "open", "closed"}:
                continue
            records.extend(entries or [])

    records.sort(key=lambda item: (
        str(item.get("symbol") or ""),
        str(item.get("side_key") or ""),
        str(item.get("entry_tf") or ""),
        -float(item.get("data", {}).get("qty") or item.get("data", {}).get("margin_usdt") or 0.0),
    ))

    def _merge_interval_labels(primary: dict, candidate: dict) -> None:
        labels: list[str] = []
        for rec in (primary, candidate):
            if not isinstance(rec, dict):
                continue
            for key in ("entry_tf",):
                value = rec.get(key)
                if isinstance(value, str) and value.strip():
                    labels.extend([part.strip() for part in value.split(",") if part.strip()])
            data = rec.get("data") or {}
            if isinstance(data, dict):
                value = data.get("interval_display")
                if isinstance(value, str) and value.strip():
                    labels.extend([part.strip() for part in value.split(",") if part.strip()])
        merged = ", ".join(dict.fromkeys(labels))
        if merged:
            primary["entry_tf"] = merged
            data = dict(primary.get("data") or {})
            data["interval_display"] = merged
            primary["data"] = data

    def _close_key(entry: dict) -> str:
        data = entry.get("data") or {}
        aggregate = str(entry.get("_aggregate_key") or data.get("_aggregate_key") or "").strip()
        ledger = str(entry.get("ledger_id") or data.get("ledger_id") or "").strip()
        close_time = entry.get("close_time") or data.get("close_time") or ""
        symbol_key = str(entry.get("symbol") or data.get("symbol") or "").strip().upper()
        side_key = str(entry.get("side_key") or data.get("side_key") or "").strip().upper()
        try:
            qty_key = f"{float(data.get('qty') or 0.0):.8f}"
        except Exception:
            qty_key = "0.0"
        if aggregate:
            return aggregate
        if ledger:
            return ledger
        return f"{symbol_key}|{side_key}|{close_time}|{qty_key}"

    deduped: list[dict] = []
    seen_closed: dict[str, dict] = {}
    for entry in records:
        data = entry.get("data") or {}
        status_flag = str(entry.get("status") or data.get("status") or "").strip().lower()
        is_closed = status_flag in _CLOSED_RECORD_STATES
        if is_closed:
            key = _close_key(entry)
            existing = seen_closed.get(key)
            if existing:
                _merge_interval_labels(existing, entry)
                continue
            seen_closed[key] = entry
        deduped.append(entry)
    records = deduped

    # Show every record (open and closed) without aggressive de-duplication, so per-trade view reflects all legs.
    for entry in records:
        entry["_aggregated_entries"] = [entry]
    return records


def _mw_positions_records_cumulative(self, entries: list[dict], closed_entries: list[dict] | None = None) -> list[dict]:
    grouped: dict[tuple[str, str], list[dict]] = {}
    for rec in entries or []:
        if not isinstance(rec, dict):
            continue
        sym = str(rec.get("symbol") or "").strip().upper()
        if not sym:
            continue
        side_key = str(rec.get("side_key") or "").strip().upper()
        if not side_key:
            continue
        grouped.setdefault((sym, side_key), []).append(rec)
    aggregated: list[dict] = []
    for (sym, side_key), bucket in grouped.items():
        if not bucket:
            continue
        primary = max(
            bucket,
            key=lambda r: float((r.get("data") or {}).get("qty") or (r.get("data") or {}).get("margin_usdt") or 0.0),
        )
        clone = copy.deepcopy(primary)
        open_time_candidates: list[datetime] = []

        def _clean_interval_label(value: object) -> str:
            """Normalize interval labels by stripping placeholder values like '-'."""
            try:
                text = str(value or "").strip()
            except Exception:
                return ""
            return text if text and text not in {"-"} else ""

        intervals: list[str] = []
        total_qty = 0.0
        total_margin = 0.0
        total_pnl = 0.0
        leverage_values: set[int] = set()

        def _collect_leverage(value: object) -> None:
            try:
                if value is None or value == "":
                    return
                lev_val = int(float(value))
                if lev_val > 0:
                    leverage_values.add(lev_val)
            except Exception:
                return

        for entry in bucket:
            label = _clean_interval_label(entry.get("entry_tf")) or _clean_interval_label(
                (entry.get("data") or {}).get("interval_display")
            )
            if label and label not in intervals:
                intervals.append(label)
            data = entry.get("data") or {}
            _collect_leverage(data.get("leverage"))
            _collect_leverage(entry.get("leverage"))
            raw_entry = data.get("raw_position")
            if not isinstance(raw_entry, dict):
                raw_entry = entry.get("raw_position") if isinstance(entry.get("raw_position"), dict) else None
            if isinstance(raw_entry, dict):
                _collect_leverage(raw_entry.get("leverage"))
            allocations = entry.get("allocations") or []
            if isinstance(allocations, dict):
                allocations = list(allocations.values())
            if isinstance(allocations, list):
                for alloc in allocations:
                    if not isinstance(alloc, dict):
                        continue
                    _collect_leverage(alloc.get("leverage"))
            # Track earliest open time across merged legs so cumulative view shows a stable timestamp.
            for ts_key in ("open_time",):
                ts_val = entry.get(ts_key) or data.get(ts_key)
                dt_obj = self._parse_any_datetime(ts_val) if hasattr(self, "_parse_any_datetime") else None
                if dt_obj:
                    open_time_candidates.append(dt_obj)
            try:
                total_qty += max(0.0, float(data.get("qty") or 0.0))
            except Exception:
                pass
            try:
                total_margin += max(0.0, float(data.get("margin_usdt") or 0.0))
            except Exception:
                pass
            try:
                total_pnl += float(data.get("pnl_value") or 0.0)
            except Exception:
                pass
        if intervals:
            clone["entry_tf"] = ", ".join(intervals)
            # Prefer the first normalized interval for downstream rendering.
            clone.setdefault("data", {}).setdefault("interval_display", intervals[0])
        else:
            # Fallback: pull intervals from allocations if exchange rows didn't carry them.
            allocations = clone.get("allocations") or []
            if isinstance(allocations, list):
                for alloc in allocations:
                    if not isinstance(alloc, dict):
                        continue
                    label = _clean_interval_label(alloc.get("interval_display")) or _clean_interval_label(
                        alloc.get("interval")
                    )
                    if label and label not in intervals:
                        intervals.append(label)
                if intervals:
                    clone["entry_tf"] = ", ".join(intervals)
                    clone.setdefault("data", {}).setdefault("interval_display", intervals[0])
        agg_data = dict(clone.get("data") or {})
        if total_qty > 0.0:
            agg_data["qty"] = total_qty
        if total_margin > 0.0:
            agg_data["margin_usdt"] = total_margin
        if total_pnl or total_pnl == 0.0:
            agg_data["pnl_value"] = total_pnl
        if total_margin > 0.0:
            try:
                agg_data["roi_percent"] = (total_pnl / total_margin) * 100.0
            except Exception:
                pass
        leverage_final = None
        if leverage_values:
            leverage_final = max(leverage_values)
        try:
            existing_lev = agg_data.get("leverage")
            if existing_lev is not None:
                existing_lev = int(float(existing_lev))
            if existing_lev and existing_lev > 0:
                leverage_final = existing_lev
        except Exception:
            pass
        if leverage_final:
            agg_data["leverage"] = leverage_final
            clone["leverage"] = leverage_final
        if open_time_candidates:
            try:
                earliest = min(open_time_candidates)
                open_fmt = (
                    self._format_display_time(earliest)
                    if hasattr(self, "_format_display_time")
                    else earliest.isoformat()
                )
                clone["open_time"] = open_fmt
                agg_data.setdefault("open_time", open_fmt)
            except Exception:
                pass
        clone["data"] = agg_data
        clone["_aggregated_entries"] = bucket
        aggregated.append(clone)
    closed_entries = list(closed_entries or [])
    def _close_dt(entry: dict):
        try:
            dt_val = entry.get("close_time") or (entry.get("data") or {}).get("close_time")
            return self._parse_any_datetime(dt_val)
        except Exception:
            return None
    closed_entries.sort(key=lambda e: (_close_dt(e) or datetime.min), reverse=True)
    aggregated.extend(closed_entries)
    aggregated.sort(key=lambda item: (item.get("symbol"), item.get("side_key"), item.get("entry_tf") or "", item.get("status") or ""))
    return aggregated


def _mw_render_positions_table(self):
    try:
        table = self.pos_table
        updates_prev = None
        signals_prev = None
        try:
            updates_prev = table.updatesEnabled()
            table.setUpdatesEnabled(False)
        except Exception:
            pass
        try:
            if hasattr(table, "blockSignals"):
                signals_prev = table.blockSignals(True)
        except Exception:
            pass
        open_records = getattr(self, "_open_position_records", {}) or {}
        closed_records = getattr(self, "_closed_position_records", []) or []
        view_mode = getattr(self, "_positions_view_mode", "cumulative")
        try:
            vbar = self.pos_table.verticalScrollBar()
            vbar_val = vbar.value()
        except Exception:
            vbar = None
            vbar_val = None
        try:
            hbar = self.pos_table.horizontalScrollBar()
            hbar_val = hbar.value()
        except Exception:
            hbar = None
            hbar_val = None
        prev_snapshot = getattr(self, "_last_positions_table_snapshot", None)
        if view_mode == "per_trade":
            display_records = _mw_positions_records_per_trade(self, open_records, closed_records)
        else:
            display_records = _mw_positions_records_cumulative(
                self,
                sorted(
                    open_records.values(),
                    key=lambda d: (d['symbol'], d.get('side_key'), d.get('entry_tf')),
                ),
                closed_records,
            )
        display_records = [rec for rec in (display_records or []) if isinstance(rec, dict)]
        snapshot_digest: list[tuple] = []
        acct_type = str(getattr(self, "_positions_account_type", "") or "").upper()
        acct_is_futures = getattr(self, "_positions_account_is_futures", None)
        if acct_is_futures is None:
            acct_is_futures = "FUT" in acct_type
        live_value_cache = getattr(self, "_live_indicator_cache", None)
        if not isinstance(live_value_cache, dict):
            live_value_cache = {}
            self._live_indicator_cache = live_value_cache
        now_ts = time.monotonic()
        ttl = float(getattr(self, "_live_indicator_cache_ttl", 8.0) or 8.0)
        cleanup_interval = max(ttl * 3.0, 30.0)
        last_cleanup = float(getattr(self, "_live_indicator_cache_last_cleanup", 0.0) or 0.0)
        if now_ts - last_cleanup >= cleanup_interval:
            cutoff = now_ts - max(ttl * 6.0, 60.0)
            stale_keys: list[tuple[str, str]] = []
            for key, entry in list(live_value_cache.items()):
                try:
                    entry_ts = float(entry.get("df_ts") or entry.get("ts") or 0.0)
                except Exception:
                    entry_ts = 0.0
                if entry_ts and entry_ts < cutoff:
                    stale_keys.append(key)
            for key in stale_keys:
                live_value_cache.pop(key, None)
            self._live_indicator_cache_last_cleanup = now_ts
        for rec in display_records:
            data = rec.get('data') or {}
            status_flag = str(rec.get('status') or data.get('status') or "").strip().lower()
            record_is_closed = status_flag in _CLOSED_RECORD_STATES
            indicators_list = tuple(
                _collect_record_indicator_keys(
                    rec,
                    include_inactive_allocs=record_is_closed,
                    include_allocation_scope=view_mode != "per_trade",
                )
            )
            interval_hint = (
                rec.get('entry_tf')
                or data.get('interval_display')
                or data.get('interval')
                or "-"
            )
            indicator_value_entries, interval_map = _collect_indicator_value_strings(rec, interval_hint)
            rec["_indicator_value_entries"] = indicator_value_entries
            rec["_indicator_interval_map"] = interval_map
            sym_digest = str(rec.get('symbol') or data.get('symbol') or "").strip().upper()
            if record_is_closed:
                current_live_entries = list(rec.get("_current_indicator_values") or [])
            else:
                current_live_entries = _collect_current_indicator_live_strings(
                    self,
                    sym_digest,
                    indicators_list,
                    live_value_cache,
                    interval_map,
                    interval_hint,
                )
            if view_mode == "per_trade":
                filtered_values = _filter_indicator_entries_for_interval(
                    indicator_value_entries,
                    interval_hint,
                    include_non_matching=False,
                )
                if filtered_values:
                    allowed = {_indicator_entry_signature(entry) for entry in filtered_values}
                    current_live_entries = [
                        entry
                        for entry in (current_live_entries or [])
                        if _indicator_entry_signature(entry) in allowed
                    ]
            if current_live_entries:
                current_live_entries = _dedupe_indicator_entries_normalized(current_live_entries)
            rec["_current_indicator_values"] = current_live_entries
            indicator_snapshot = tuple(indicator_value_entries or [])
            interval_snapshot = tuple(
                (key, tuple(values))
                for key, values in (interval_map or {}).items()
            )
            current_live_tuple = tuple(current_live_entries or [])
            snapshot_digest.append(
                (
                    str(rec.get('symbol') or "").upper(),
                    str(rec.get('side_key') or "").upper(),
                    str(rec.get('entry_tf') or ""),
                    indicators_list,
                    indicator_snapshot,
                    interval_snapshot,
                    current_live_tuple,
                    float(data.get('qty') or 0.0),
                    float(data.get('margin_usdt') or 0.0),
                    float(data.get('pnl_value') or 0.0),
                    str(rec.get('status') or ""),
                )
            )
        snapshot_key = (view_mode, tuple(snapshot_digest))
        if prev_snapshot == snapshot_key and view_mode == "per_trade":
            totals = getattr(self, "_last_positions_table_totals", None)
            if isinstance(totals, tuple) and len(totals) == 2:
                self._update_positions_pnl_summary(*totals)
                self._update_global_pnl_display(*self._compute_global_pnl_totals())
            return
        header = self.pos_table.horizontalHeader()
        try:
            sort_column = header.sortIndicatorSection()
            sort_order = header.sortIndicatorOrder()
            if sort_column is None or sort_column < 0:
                sort_column = 0
                sort_order = QtCore.Qt.SortOrder.AscendingOrder
        except Exception:
            sort_column = 0
            sort_order = QtCore.Qt.SortOrder.AscendingOrder
        self.pos_table.setSortingEnabled(False)
        self.pos_table.setRowCount(0)
        total_pnl = 0.0
        total_margin = 0.0
        pnl_has_value = False
        aggregated_keys: set[tuple[str, tuple[str, ...]] | str] = set()
        for rec in display_records:
            try:
                data = rec.get('data', {}) or {}
                sym = str(rec.get('symbol') or data.get('symbol') or "").strip().upper()
                if not sym:
                    sym = "-"
                side_key = str(rec.get('side_key') or data.get('side_key') or "").upper()
                interval = rec.get('entry_tf') or data.get('interval_display') or "-"
                row = self.pos_table.rowCount()
                self.pos_table.insertRow(row)

                qty_show = float(data.get('qty') or 0.0)
                mark = float(data.get('mark') or 0.0)
                size_usdt = float(data.get('size_usdt') or (qty_show * mark))
                mr = normalize_margin_ratio(data.get('margin_ratio'))
                margin_usdt = float(data.get('margin_usdt') or 0.0)
                pnl_roi = data.get('pnl_roi')
                pnl_raw_value = data.get('pnl_value')
                try:
                    pnl_value = float(pnl_raw_value or 0.0)
                except Exception:
                    pnl_value = 0.0
                side_text = 'Long' if side_key == 'L' else ('Short' if side_key == 'S' else 'Spot')
                open_time = data.get('open_time') or rec.get('open_time') or '-'
                status_txt = rec.get('status', 'Active')
                status_lower = str(status_txt).strip().lower()
                is_closed_like = status_lower in _CLOSED_RECORD_STATES
                close_time = rec.get('close_time') if is_closed_like else '-'
                stop_loss_enabled = bool(rec.get('stop_loss_enabled'))
                stop_loss_text = "Yes" if stop_loss_enabled else "No"

                aggregate_key = str(rec.get("_aggregate_key") or rec.get("ledger_id") or "")
                aggregate_primary = bool(rec.get("_aggregate_is_primary", True))
                should_aggregate = True
                if aggregate_key:
                    indicator_signature = tuple(_normalize_indicator_values(rec.get("indicators")))
                    interval_signature = str(rec.get("entry_tf") or "").strip().lower()
                    if indicator_signature:
                        key_entry = (aggregate_key, interval_signature, indicator_signature)
                    else:
                        key_entry = (aggregate_key, interval_signature)
                    if aggregate_primary:
                        if key_entry in aggregated_keys:
                            should_aggregate = False
                        else:
                            aggregated_keys.add(key_entry)
                    else:
                        should_aggregate = False

                raw_position = data.get("raw_position")
                if not isinstance(raw_position, dict):
                    raw_position = rec.get("raw_position") if isinstance(rec.get("raw_position"), dict) else None
                leverage_val = 0
                leverage_candidates = [
                    data.get("leverage"),
                    rec.get("leverage"),
                    (raw_position or {}).get("leverage"),
                ]
                for candidate in leverage_candidates:
                    try:
                        if candidate is None:
                            continue
                        val = int(round(float(candidate)))
                        if val > 0:
                            leverage_val = val
                            break
                    except Exception:
                        continue
                contract_label_raw = (
                    data.get("contract_type")
                    or data.get("contractType")
                    or data.get("instrument_type")
                    or data.get("instrumentType")
                    or (raw_position or {}).get("contractType")
                    or (raw_position or {}).get("contract_type")
                    or ""
                )
                contract_label = str(contract_label_raw).strip()
                if not contract_label:
                    if side_key in ("L", "S") and acct_is_futures:
                        contract_label = "Perp"
                    elif side_key == "SPOT":
                        contract_label = "Spot"
                elif side_key == "SPOT":
                    contract_label = "Spot"
                contract_display = ""
                if contract_label:
                    if contract_label.upper().startswith("PERP"):
                        contract_display = "Perp"
                    else:
                        contract_display = contract_label.title()
                info_parts: list[str] = []
                if contract_display:
                    info_parts.append(contract_display)
                if leverage_val > 0:
                    info_parts.append(f"{leverage_val}x")
                if info_parts:
                    sym_display = f"{sym}\n{'    '.join(info_parts)}"
                else:
                    sym_display = sym
                self.pos_table.setItem(row, 0, QtWidgets.QTableWidgetItem(sym_display))

                size_item = _NumericItem(f"{size_usdt:.8f}", size_usdt)
                self.pos_table.setItem(row, 1, size_item)

                mark_item = _NumericItem(f"{mark:.8f}" if mark else "-", mark)
                self.pos_table.setItem(row, 2, mark_item)

                mr_display = f"{mr:.2f}%" if mr > 0 else "-"
                mr_item = _NumericItem(mr_display, mr)
                self.pos_table.setItem(row, 3, mr_item)

                liq_price = 0.0
                liq_candidates = [
                    data.get("liquidation_price"),
                    data.get("liquidationPrice"),
                    data.get("liq_price"),
                    data.get("liqPrice"),
                    rec.get("liquidation_price"),
                    rec.get("liquidationPrice"),
                    (raw_position or {}).get("liquidationPrice"),
                    (raw_position or {}).get("liqPrice"),
                ]
                for candidate in liq_candidates:
                    try:
                        if candidate is None or candidate == "":
                            continue
                        value = float(candidate)
                        if value > 0.0:
                            liq_price = value
                            break
                    except Exception:
                        continue
                liq_text = f"{liq_price:.6f}" if liq_price > 0 else "-"
                liq_item = _NumericItem(liq_text if liq_price > 0 else "-", liq_price)
                self.pos_table.setItem(row, 4, liq_item)

                margin_item = _NumericItem(f"{margin_usdt:.2f} USDT" if margin_usdt else "-", margin_usdt)
                self.pos_table.setItem(row, 5, margin_item)
                if margin_usdt > 0.0 and should_aggregate:
                    total_margin += margin_usdt

                qty_margin_item = _NumericItem(f"{qty_show:.6f}", qty_show)
                self.pos_table.setItem(row, 6, qty_margin_item)

                pnl_item = _NumericItem(str(pnl_roi or "-"), pnl_value)
                self.pos_table.setItem(row, 7, pnl_item)
                added_to_total = False
                if pnl_raw_value is not None and should_aggregate:
                    total_pnl += pnl_value
                    pnl_has_value = True
                    added_to_total = True
                pnl_valid = (pnl_raw_value is not None) or (abs(pnl_value) > 0.0)
                if not pnl_valid and status_lower == "closed":
                    pnl_valid = True
                if status_lower == "closed" and not added_to_total and pnl_valid and should_aggregate:
                    total_pnl += pnl_value
                    pnl_has_value = True

                self.pos_table.setItem(row, 8, QtWidgets.QTableWidgetItem(interval or '-'))
                source_entries = rec.get("_aggregated_entries") or [rec]
                indicators_list: list[str] = []
                indicator_values_entries: list[str] = []
                interval_map: dict[str, list[str]] = {}
                for entry in source_entries:
                    entry_inds = _collect_record_indicator_keys(
                        entry,
                        include_inactive_allocs=is_closed_like,
                        include_allocation_scope=view_mode != "per_trade",
                    )
                    for token in entry_inds:
                        if token and token not in indicators_list:
                            indicators_list.append(token)
                    cached_values = entry.get("_indicator_value_entries")
                    cached_map = entry.get("_indicator_interval_map")
                    interval_hint_entry = (
                        entry.get("entry_tf")
                        or (entry.get("data") or {}).get("interval_display")
                        or interval
                    )
                    if cached_values is None or cached_map is None:
                        cached_values, cached_map = _collect_indicator_value_strings(entry, interval_hint_entry)
                        entry["_indicator_value_entries"] = cached_values
                        entry["_indicator_interval_map"] = cached_map
                    for value_entry in cached_values or []:
                        if value_entry not in indicator_values_entries:
                            indicator_values_entries.append(value_entry)
                    for key, slots in (cached_map or {}).items():
                        bucket = interval_map.setdefault(key, [])
                        for slot in slots:
                            if slot not in bucket:
                                bucket.append(slot)
                rec["_indicator_value_entries"] = indicator_values_entries
                rec["_indicator_interval_map"] = interval_map
                active_indicator_keys_ordered = list((interval_map or {}).keys())
                display_list: list[str] = list(indicators_list or [])
                if active_indicator_keys_ordered:
                    filtered = [ind for ind in display_list if ind.lower() in active_indicator_keys_ordered]
                    display_list = filtered if filtered else active_indicator_keys_ordered
                indicators_list = display_list
                indicators_display = _format_indicator_list(display_list) if display_list else '-'
                self.pos_table.setItem(row, 9, QtWidgets.QTableWidgetItem(indicators_display))
                interval_for_display = interval
                strict_interval_values = getattr(self, "_positions_view_mode", "cumulative") == "per_trade"
                filtered_indicator_values = _filter_indicator_entries_for_interval(
                    indicator_values_entries,
                    interval_for_display,
                    include_non_matching=not strict_interval_values,
                )
                if filtered_indicator_values:
                    filtered_indicator_values = list(dict.fromkeys(filtered_indicator_values))
                indicator_values_display = "\n".join(filtered_indicator_values) if filtered_indicator_values else "-"
                self.pos_table.setItem(row, POS_TRIGGERED_VALUE_COLUMN, QtWidgets.QTableWidgetItem(indicator_values_display))
                live_values_entries = rec.get("_current_indicator_values")
                if live_values_entries is None:
                    if not is_closed_like:
                        live_indicator_keys = indicators_list
                        live_interval_map = interval_map
                        if strict_interval_values and filtered_indicator_values:
                            label_map = {
                                _indicator_short_label(key).strip().lower(): key
                                for key in indicators_list
                            }
                            restricted_keys: list[str] = []
                            restricted_map: dict[str, list[str]] = {}
                            for entry in filtered_indicator_values:
                                label_part, interval_part = _indicator_entry_signature(entry)
                                mapped_key = label_map.get(label_part)
                                if not mapped_key:
                                    continue
                                if mapped_key not in restricted_keys:
                                    restricted_keys.append(mapped_key)
                                if interval_part:
                                    slots = restricted_map.setdefault(mapped_key.lower(), [])
                                    interval_clean = interval_part.strip().upper()
                                    if interval_clean and interval_clean not in slots:
                                        slots.append(interval_clean)
                            if restricted_keys:
                                live_indicator_keys = restricted_keys
                                live_interval_map = restricted_map
                        live_values_entries = _collect_current_indicator_live_strings(
                            self,
                            sym,
                            live_indicator_keys,
                            live_value_cache,
                            live_interval_map,
                            interval,
                        )
                        rec["_current_indicator_values"] = live_values_entries
                    else:
                        live_values_entries = []
                if live_values_entries:
                    live_values_entries = _dedupe_indicator_entries_normalized(live_values_entries)
                    rec["_current_indicator_values"] = live_values_entries
                current_values_display = "\n".join(live_values_entries) if live_values_entries else "-"
                self.pos_table.setItem(row, POS_CURRENT_VALUE_COLUMN, QtWidgets.QTableWidgetItem(current_values_display))
                if filtered_indicator_values and live_values_entries:
                    merged_trigger_entries = _backfill_trigger_entries_with_live_values(
                        filtered_indicator_values,
                        live_values_entries,
                    )
                    if merged_trigger_entries != filtered_indicator_values:
                        filtered_indicator_values = merged_trigger_entries
                        indicator_values_display = "\n".join(filtered_indicator_values)
                        self.pos_table.setItem(
                            row,
                            POS_TRIGGERED_VALUE_COLUMN,
                            QtWidgets.QTableWidgetItem(indicator_values_display),
                        )
                if indicator_values_display == "-" and live_values_entries:
                    trigger_fallback_entries = _filter_indicator_entries_for_interval(
                        live_values_entries,
                        interval_for_display,
                        include_non_matching=not strict_interval_values,
                    )
                    if not trigger_fallback_entries:
                        trigger_fallback_entries = _filter_indicator_entries_for_interval(
                            live_values_entries,
                            interval_for_display,
                            include_non_matching=True,
                        )
                    if not trigger_fallback_entries:
                        trigger_fallback_entries = list(live_values_entries)
                    trigger_fallback_entries = _dedupe_indicator_entries_normalized(trigger_fallback_entries)
                    if trigger_fallback_entries:
                        fallback_display = "\n".join(trigger_fallback_entries)
                        self.pos_table.setItem(
                            row,
                            POS_TRIGGERED_VALUE_COLUMN,
                            QtWidgets.QTableWidgetItem(fallback_display),
                        )
                self.pos_table.setItem(row, 12, QtWidgets.QTableWidgetItem(side_text))
                self.pos_table.setItem(row, 13, QtWidgets.QTableWidgetItem(str(open_time or '-')))
                self.pos_table.setItem(row, 14, QtWidgets.QTableWidgetItem(str(close_time or '-')))
                self.pos_table.setItem(row, POS_STOP_LOSS_COLUMN, QtWidgets.QTableWidgetItem(stop_loss_text))
                self.pos_table.setItem(row, POS_STATUS_COLUMN, QtWidgets.QTableWidgetItem(status_txt))
                btn_interval = interval if interval != "-" else None
                btn = self._make_close_btn(sym, side_key, btn_interval, qty_show)
                if str(status_txt).strip().lower() != 'active':
                    btn.setEnabled(False)
                self.pos_table.setCellWidget(row, POS_CLOSE_COLUMN, btn)
            except Exception:
                pass
        try:
            if coerce_bool(self.config.get("positions_auto_resize_rows", True), True):
                self.pos_table.resizeRowsToContents()
        except Exception:
            pass
        try:
            if coerce_bool(self.config.get("positions_auto_resize_columns", True), True):
                self.pos_table.resizeColumnsToContents()
        except Exception:
            pass
        summary_margin = total_margin if total_margin > 0.0 else None
        self._update_positions_pnl_summary(total_pnl if pnl_has_value else None, summary_margin)
        self._update_global_pnl_display(*self._compute_global_pnl_totals())
        try:
            if (
                getattr(self, "chart_enabled", False)
                and getattr(self, "chart_auto_follow", False)
                and not getattr(self, "_chart_manual_override", False)
                and self._is_chart_visible()
            ):
                self._sync_chart_to_active_positions()
        except Exception:
            pass
    except Exception as exc:
        try:
            self.log(f"Positions table update failed: {exc}")
        except Exception:
            pass
    finally:
        def _restore_scrollbar(bar, value):
            try:
                if bar is None or value is None:
                    return
                value_clamped = max(bar.minimum(), min(value, bar.maximum()))
                bar.setValue(value_clamped)
            except Exception:
                pass
        try:
            self.pos_table.setSortingEnabled(True)
            if sort_column is not None and sort_column >= 0:
                self.pos_table.sortItems(sort_column, sort_order)
        except Exception:
            pass
        try:
            if vbar is not None and vbar_val is not None:
                QtCore.QTimer.singleShot(0, lambda: _restore_scrollbar(vbar, vbar_val))
        except Exception:
            pass
        try:
            if hbar is not None and hbar_val is not None:
                QtCore.QTimer.singleShot(0, lambda: _restore_scrollbar(hbar, hbar_val))
        except Exception:
            pass
        try:
            self._last_positions_table_snapshot = snapshot_key
            self._last_positions_table_totals = (total_pnl if pnl_has_value else None, summary_margin)
        except Exception:
            pass
        try:
            if hasattr(self.pos_table, "blockSignals"):
                self.pos_table.blockSignals(signals_prev if signals_prev is not None else False)
        except Exception:
            pass
        try:
            if updates_prev is not None:
                self.pos_table.setUpdatesEnabled(updates_prev)
        except Exception:
            pass


def _update_positions_pnl_summary(self, total_pnl: float | None, total_margin: float | None) -> None:
    label = getattr(self, "positions_pnl_label", None)
    if label is None:
        return
    if total_pnl is None:
        label.setText("Total PNL: --")
        return
    text = f"Total PNL: {total_pnl:+.2f} USDT"
    if total_margin is not None and total_margin > 0.0:
        try:
            roi = (total_pnl / total_margin) * 100.0
        except Exception:
            roi = 0.0
        text += f" ({roi:+.2f}%)"
    label.setText(text)


def _mw_clear_positions_selected(self):
    try:
        table = getattr(self, "pos_table", None)
        if table is None:
            return
        sel_model = table.selectionModel()
        if sel_model is None:
            return
        rows = sorted({index.row() for index in sel_model.selectedRows()}, reverse=True)
        if not rows:
            return
        closed_records = list(getattr(self, "_closed_position_records", []) or [])
        changed = False
        skipped_active = False
        for row in rows:
            status_item = table.item(row, POS_STATUS_COLUMN)
            status = (status_item.text().strip().upper() if status_item else "")
            if status != "CLOSED":
                skipped_active = True
                continue
            symbol_item = table.item(row, 0)
            side_item = table.item(row, 9)
            symbol = (symbol_item.text().strip().upper() if symbol_item else "")
            side_txt = (side_item.text().strip().upper() if side_item else "")
            side_key = None
            if "LONG" in side_txt or side_txt == "BUY":
                side_key = "L"
            elif "SHORT" in side_txt or side_txt == "SELL":
                side_key = "S"
            remove_idx = None
            for idx, rec in enumerate(closed_records):
                rec_sym = str(rec.get('symbol') or '').strip().upper()
                rec_side = str(rec.get('side_key') or '').strip().upper()
                if rec_sym == symbol and (side_key is None or not rec_side or rec_side == side_key):
                    remove_idx = idx
                    break
            if remove_idx is not None:
                closed_records.pop(remove_idx)
                changed = True
        if changed:
            self._closed_position_records = closed_records
            self._render_positions_table()
        if skipped_active:
            try:
                self.log("Positions: only closed history rows can be cleared.")
            except Exception:
                pass
    except Exception:
        pass


def _mw_clear_positions_all(self):
    try:
        if QtWidgets.QMessageBox.question(
            self,
            "Clear Closed History",
            "Clear ALL closed position history? (Active positions remain untouched.)",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        ) != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self._closed_position_records = []
        self._closed_trade_registry = {}
        self._render_positions_table()
    except Exception:
        pass


def _mw_snapshot_closed_position(self, symbol: str, side_key: str) -> bool:
    try:
        if not symbol or side_key not in ("L", "S"):
            return False
        if not hasattr(self, "_closed_position_records"):
            self._closed_position_records = []
        open_records = getattr(self, "_open_position_records", {}) or {}
        rec = open_records.get((symbol, side_key))
        if not rec:
            return False
        from datetime import datetime as _dt
        snap = copy.deepcopy(rec)
        snap['status'] = 'Closed'
        snap['close_time'] = self._format_display_time(_dt.now().astimezone())
        self._closed_position_records.insert(0, snap)
        if len(self._closed_position_records) > MAX_CLOSED_HISTORY:
            self._closed_position_records = self._closed_position_records[:MAX_CLOSED_HISTORY]
        try:
            registry = getattr(self, "_closed_trade_registry", None)
            if registry is None:
                registry = {}
                self._closed_trade_registry = registry
            key = f"{symbol}-{side_key}-{int(time.time()*1000)}"
            data = snap.get("data") if isinstance(snap, dict) else {}
            def _safe_float_local(value):
                try:
                    return float(value)
                except Exception:
                    return None
            registry[key] = {
                "pnl_value": _safe_float_local((data or {}).get("pnl_value")),
                "margin_usdt": _safe_float_local((data or {}).get("margin_usdt")),
                "roi_percent": _safe_float_local((data or {}).get("roi_percent")),
            }
            if len(registry) > MAX_CLOSED_HISTORY:
                excess = len(registry) - MAX_CLOSED_HISTORY
                if excess > 0:
                    for old_key in list(registry.keys())[:excess]:
                        registry.pop(old_key, None)
        except Exception:
            pass
        try:
            open_records.pop((symbol, side_key), None)
        except Exception:
            pass
        try:
            self._update_global_pnl_display(*self._compute_global_pnl_totals())
        except Exception:
            pass
        return True
    except Exception:
        return False


def _mw_sync_chart_to_active_positions(self):
    try:
        if not getattr(self, "chart_enabled", False):
            return
        open_records = getattr(self, "_open_position_records", {}) or {}
        if not open_records:
            return
        active_syms = []
        for rec in open_records.values():
            try:
                if str(rec.get('status', 'Active')).upper() != 'ACTIVE':
                    continue
                sym = str(rec.get('symbol') or '').strip().upper()
                if sym:
                    active_syms.append(sym)
            except Exception:
                continue
        if not active_syms:
            return
        target_sym = active_syms[0]
        market_combo = getattr(self, "chart_market_combo", None)
        if market_combo is None:
            return
        current_market = self._normalize_chart_market(market_combo.currentText())
        if current_market != "Futures":
            try:
                idx = market_combo.findText("Futures", QtCore.Qt.MatchFlag.MatchFixedString)
                if idx >= 0:
                    market_combo.setCurrentIndex(idx)
                else:
                    market_combo.addItem("Futures")
                    market_combo.setCurrentIndex(market_combo.count() - 1)
            except Exception:
                try:
                    market_combo.setCurrentText("Futures")
                except Exception:
                    pass
            return
        display_sym = self._futures_display_symbol(target_sym)
        cache = self.chart_symbol_cache.setdefault("Futures", [])
        if target_sym not in cache:
            cache.append(target_sym)
        alias_map = getattr(self, "_chart_symbol_alias_map", None)
        if not isinstance(alias_map, dict):
            alias_map = {}
            self._chart_symbol_alias_map = alias_map
        futures_alias = alias_map.setdefault("Futures", {})
        futures_alias[display_sym] = target_sym
        self._update_chart_symbol_options(cache)
        changed = self._set_chart_symbol(display_sym, ensure_option=True, from_follow=True)
        if changed or self._chart_needs_render or self._is_chart_visible():
            self.load_chart(auto=True)
    except Exception:
        pass


def _mw_make_close_btn(self, symbol: str, side_key: str | None = None, interval: str | None = None, qty: float | None = None):
    label = "Close"
    if side_key == "L":
        label = "Close Long"
    elif side_key == "S":
        label = "Close Short"
    btn = QtWidgets.QPushButton(label)
    tooltip_bits = []
    if side_key == "L":
        tooltip_bits.append("Closes the long leg")
    elif side_key == "S":
        tooltip_bits.append("Closes the short leg")
    if interval and interval not in ("-", "SPOT"):
        tooltip_bits.append(f"Interval {interval}")
    if qty and qty > 0:
        try:
            tooltip_bits.append(f"Qty ~= {qty:.6f}")
        except Exception:
            pass
    if tooltip_bits:
        btn.setToolTip(" | ".join(tooltip_bits))
    btn.setEnabled(side_key in ("L", "S"))
    interval_key = interval if interval not in ("-", "SPOT") else None
    btn.clicked.connect(lambda _, s=symbol, sk=side_key, iv=interval_key, q=qty: self._close_position_single(s, sk, iv, q))
    return btn


def _mw_close_position_single(self, symbol: str, side_key: str | None, interval: str | None, qty: float | None):
    if not symbol:
        return
    try:
        from ..workers import CallWorker as _CallWorker
    except Exception as exc:
        try:
            self.log(f"Close {symbol} setup error: {exc}")
        except Exception:
            pass
        return
    if side_key not in ("L", "S"):
        try:
            self.log(f"{symbol}: manual close is only available for futures legs.")
        except Exception:
            pass
        return
    account_text = (self.account_combo.currentText() or "").upper()
    force_futures = side_key in ("L", "S")
    needs_wrapper = getattr(self, "shared_binance", None) is None
    if force_futures and not needs_wrapper:
        try:
            current_wrapper_acct = str(getattr(self.shared_binance, "account_type", "") or "").upper()
        except Exception:
            current_wrapper_acct = ""
        if not current_wrapper_acct.startswith("FUT"):
            needs_wrapper = True
    if needs_wrapper:
        try:
            self.shared_binance = self._create_binance_wrapper(
                api_key=self.api_key_edit.text().strip(),
                api_secret=self.api_secret_edit.text().strip(),
                mode=self.mode_combo.currentText(),
                account_type=("Futures" if force_futures else self.account_combo.currentText()),
                default_leverage=int(self.leverage_spin.value() or 1),
                default_margin_mode=self.margin_mode_combo.currentText() or "Isolated",
            )
        except Exception as exc:
            try:
                self.log(f"Close {symbol} setup error: {exc}")
            except Exception:
                pass
            return
    account = account_text
    try:
        qty_val = float(qty or 0.0)
    except Exception:
        qty_val = 0.0

    def _do():
        bw = self.shared_binance
        if force_futures or account.startswith("FUT"):
            if side_key in ("L", "S") and qty_val > 0:
                try:
                    dual = bool(bw.get_futures_dual_side())
                except Exception:
                    dual = False
                order_side = "SELL" if side_key == "L" else "BUY"
                pos_side = None
                if dual:
                    pos_side = "LONG" if side_key == "L" else "SHORT"
                primary_res = bw.close_futures_leg_exact(symbol, qty_val, side=order_side, position_side=pos_side)
                if isinstance(primary_res, dict) and primary_res.get("ok"):
                    return primary_res
                try:
                    fallback_res = bw.close_futures_position(symbol)
                except Exception as exc:
                    fallback_res = {"ok": False, "error": str(exc)}
                if isinstance(fallback_res, dict) and fallback_res.get("ok"):
                    fallback_res.setdefault("fallback_from", "close_futures_leg_exact")
                    if isinstance(primary_res, dict) and primary_res.get("error"):
                        fallback_res.setdefault("primary_error", primary_res.get("error"))
                    return fallback_res
                if isinstance(primary_res, dict):
                    primary_res["fallback"] = fallback_res
                    return primary_res
                return {"ok": False, "error": f"close leg failed: {primary_res!r}", "fallback": fallback_res}
            return bw.close_futures_position(symbol)
        return {"ok": False, "error": "Spot manual close via UI is not available yet"}

    def _done(res, err):
        succeeded = False
        try:
            if err:
                self.log(f"Close {symbol} error: {err}")
            else:
                self.log(f"Close {symbol} result: {res}")
                succeeded = isinstance(res, dict) and res.get("ok")
            if succeeded and interval and side_key in ("L", "S"):
                try:
                    if hasattr(self, "_track_interval_close"):
                        self._track_interval_close(symbol, side_key, interval)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            self.refresh_positions(symbols=[symbol])
        except Exception:
            pass

    worker = _CallWorker(_do, parent=self)
    try:
        worker.progress.connect(self.log)
    except Exception:
        pass
    worker.done.connect(_done)
    worker.finished.connect(worker.deleteLater)

    def _cleanup():
        try:
            self._bg_workers.remove(worker)
        except Exception:
            pass

    if not hasattr(self, "_bg_workers"):
        self._bg_workers = []
    self._bg_workers.append(worker)
    worker.finished.connect(_cleanup)
    worker.start()


def on_leverage_changed(self, value):
    try:
        value_int = int(value)
    except Exception:
        value_int = 0
    try:
        self.config['leverage'] = value_int
    except Exception:
        pass
    try:
        engines = getattr(self, "strategy_engines", {}) or {}
        for eng in engines.values():
            try:
                conf = getattr(eng, "config", None)
                if isinstance(conf, dict):
                    conf['leverage'] = value_int
            except Exception:
                pass
    except Exception:
        pass
    try:
        if value_int > 0 and hasattr(self, 'shared_binance') and self.shared_binance and (self.account_combo.currentText() or '').upper().startswith('FUT'):
            self.shared_binance.set_futures_leverage(value_int)
    except Exception:
        pass


def refresh_symbols(self):
    from ..workers import CallWorker as _CallWorker
    self.refresh_symbols_btn.setEnabled(False)
    self.refresh_symbols_btn.setText("Refreshing...")
    def _do():
        tmp_wrapper = self._create_binance_wrapper(
            api_key=self.api_key_edit.text().strip(),
            api_secret=self.api_secret_edit.text().strip(),
            mode=self.mode_combo.currentText(),
            account_type=self.account_combo.currentText(),
        )
        syms = tmp_wrapper.fetch_symbols(sort_by_volume=True, top_n=_SYMBOL_FETCH_TOP_N)
        return syms
    def _done(res, err):
        try:
            if err or not res:
                self.log(f"Failed to refresh symbols: {err or 'no symbols'}")
                return
            self.symbol_list.clear()
            all_symbols = []
            filtered = []
            seen = set()
            for sym in res or []:
                sym_norm = str(sym or "").strip().upper()
                if not sym_norm or sym_norm in seen:
                    continue
                seen.add(sym_norm)
                all_symbols.append(sym_norm)
                if sym_norm.endswith("USDT"):
                    filtered.append(sym_norm)
            if filtered:
                self.symbol_list.addItems(filtered)
            if all_symbols:
                self.chart_symbol_cache["Futures"] = all_symbols
            current_market = self._normalize_chart_market(getattr(self, "chart_market_combo", None).currentText() if hasattr(self, "chart_market_combo") else None)
            if current_market == "Futures":
                self._update_chart_symbol_options(all_symbols if all_symbols else filtered)
                self._chart_needs_render = True
                if self.chart_auto_follow and not self._chart_manual_override:
                    self._apply_dashboard_selection_to_chart(load=True)
                elif self._chart_pending_initial_load or self._is_chart_visible():
                    self.load_chart(auto=True)
            self.log(f"Loaded {self.symbol_list.count()} USDT-pair symbols for {self.account_combo.currentText()}.")
        finally:
            self.refresh_symbols_btn.setEnabled(True)
            self.refresh_symbols_btn.setText("Refresh Symbols")
    w = _CallWorker(_do, parent=self)
    try:
        w.progress.connect(self.log)
    except Exception:
        pass
    w.done.connect(_done)
    w.start()

def apply_futures_modes(self):
    from ..workers import CallWorker as _CallWorker
    mm = self.margin_mode_combo.currentText().upper()
    pos_mode = self.position_mode_combo.currentText()
    hedge = (pos_mode.strip().lower() == 'hedge')
    assets_mode_value = self.assets_mode_combo.currentData() or self.assets_mode_combo.currentText()
    assets_mode_norm = self._normalize_assets_mode(assets_mode_value)
    multi = (assets_mode_norm == 'Multi-Assets')
    tif = self.tif_combo.currentText()
    gtdm = int(self.gtd_minutes_spin.value())
    def _do():
        try:
            self.shared_binance.set_position_mode(hedge)
        except Exception:
            pass
        try:
            self.shared_binance.set_multi_assets_mode(multi)
        except Exception:
            pass
        return True
    def _done(res, err):
        if err:
            self.log(f"Apply futures modes error: {err}")
            return
        self.config['margin_mode'] = 'Isolated' if mm == 'ISOLATED' else 'Cross'
        self.config['position_mode'] = 'Hedge' if hedge else 'One-way'
        self.config['assets_mode'] = 'Multi-Assets' if multi else 'Single-Asset'
        self.config['tif'] = tif
        self.config['gtd_minutes'] = gtdm
    w = _CallWorker(_do, parent=self)
    try:
        w.progress.connect(self.log)
    except Exception:
        pass
    w.done.connect(_done)
    w.start()


def start_strategy(self):
    if getattr(self, '_is_stopping_engines', False):
        self.log('Stop in progress; cannot start new engines.')
        return
    shared = getattr(self, 'shared_binance', None)
    if shared is not None and getattr(shared, '_emergency_close_requested', False):
        self.log('Emergency close-all in progress; wait for it to finish before starting.')
        return
    try:
        StrategyEngine.resume_trading()
    except Exception:
        pass
    started = 0
    try:
        default_loop_override = self._loop_choice_value(getattr(self, "loop_combo", None))
        runtime_ctx = self._override_ctx("runtime")
        account_type_text = (self.account_combo.currentText() or "Futures").strip()
        is_futures_account = account_type_text.upper().startswith("FUT")
        pair_entries: list[dict] = []
        table = runtime_ctx.get("table") if runtime_ctx else None
        if table is not None:
            try:
                selected_rows = sorted({idx.row() for idx in table.selectionModel().selectedRows()})
            except Exception:
                selected_rows = []
            if selected_rows:
                for row in selected_rows:
                    sym_item = table.item(row, 0)
                    iv_item = table.item(row, 1)
                    sym = sym_item.text().strip().upper() if sym_item else ""
                    iv_raw = iv_item.text().strip() if iv_item else ""
                    iv_canonical = self._canonicalize_interval(iv_raw)
                    if sym and iv_canonical:
                        entry_obj = None
                        try:
                            entry_obj = sym_item.data(QtCore.Qt.ItemDataRole.UserRole)
                        except Exception:
                            entry_obj = None
                        indicators = None
                        controls = None
                        if isinstance(entry_obj, dict):
                            indicators = entry_obj.get("indicators")
                            controls = entry_obj.get("strategy_controls")
                            if isinstance(indicators, (list, tuple)):
                                indicators = sorted({str(k).strip() for k in indicators if str(k).strip()})
                            else:
                                indicators = None
                        pair_entries.append({
                            "symbol": sym,
                            "interval": iv_canonical,
                            "indicators": list(indicators) if indicators else None,
                            "strategy_controls": self._normalize_strategy_controls("runtime", controls),
                        })
                    elif sym and iv_raw:
                        self.log(f"Skipping unsupported interval '{iv_raw}' for {account_type_text} {sym}.")
        if not pair_entries:
            for entry in self.config.get("runtime_symbol_interval_pairs", []) or []:
                sym = str((entry or {}).get("symbol") or "").strip().upper()
                interval_val = str((entry or {}).get("interval") or "").strip()
                iv_canonical = self._canonicalize_interval(interval_val)
                if not (sym and iv_canonical):
                    if sym and interval_val:
                        self.log(f"Skipping unsupported interval '{interval_val}' for {account_type_text} {sym}.")
                    continue
                indicators = entry.get("indicators")
                if isinstance(indicators, (list, tuple)):
                    indicators = sorted({str(k).strip() for k in indicators if str(k).strip()})
                else:
                    indicators = None
                controls = self._normalize_strategy_controls("runtime", entry.get("strategy_controls"))
                pair_entries.append({
                    "symbol": sym,
                    "interval": iv_canonical,
                    "indicators": list(indicators) if indicators else None,
                    "strategy_controls": controls,
                })
        if not pair_entries:
            self.log("No symbol/interval overrides configured. Add entries before starting.")
            return

        combos_map: dict[tuple[str, str], dict] = {}
        for entry in pair_entries:
            sym = str(entry.get("symbol") or "").strip().upper()
            iv_raw = str(entry.get("interval") or "").strip()
            iv = self._canonicalize_interval(iv_raw)
            if not sym or not iv:
                if sym and iv_raw:
                    self.log(f"Skipping unsupported interval '{iv_raw}' for {account_type_text} {sym}.")
                continue
            indicators = entry.get("indicators")
            if isinstance(indicators, (list, tuple)):
                indicators = sorted({str(k).strip() for k in indicators if str(k).strip()})
            else:
                indicators = []
            controls = entry.get("strategy_controls")
            key = (sym, iv)
            item = combos_map.setdefault(key, {"symbol": sym, "interval": iv, "indicators": [], "strategy_controls": {}})
            if indicators:
                try:
                    ind_set = set(item.get("indicators") or [])
                    ind_set.update(indicators)
                    item["indicators"] = sorted(ind_set)
                except Exception:
                    item["indicators"] = indicators
            if isinstance(controls, dict):
                try:
                    ctrl = item.setdefault("strategy_controls", {})
                    for k, v in controls.items():
                        if v is not None:
                            ctrl[k] = v
                except Exception:
                    item["strategy_controls"] = controls

        combos = list(combos_map.values())
        if not combos:
            self.log("No valid symbol/interval overrides found.")
            return

        connector_name = self._connector_label_text(self._runtime_connector_backend(suppress_refresh=True))
        self.log(f"Starting strategy with {len(combos)} symbol/interval loops. Connector: {connector_name}.")

        try:
            self.config["position_pct_units"] = "percent"
        except Exception:
            pass

        total_jobs = len(combos)
        concurrency = StrategyEngine.concurrent_limit(total_jobs)
        if total_jobs > concurrency:
            self.log(f"{total_jobs} symbol/interval loops requested; limiting concurrent execution to {concurrency} to keep the UI responsive.")

        if getattr(self, "shared_binance", None) is None:
            self.shared_binance = self._create_binance_wrapper(
                api_key=self.api_key_edit.text().strip(),
                api_secret=self.api_secret_edit.text().strip(),
                mode=self.mode_combo.currentText(),
                account_type=self.account_combo.currentText(),
                default_leverage=int(self.leverage_spin.value() or 1),
                default_margin_mode=self.margin_mode_combo.currentText() or "Isolated",
            )

        if not hasattr(self, "strategy_engines"):
            self.strategy_engines = {}

        try:
            if self.shared_binance is not None:
                self.shared_binance.account_type = account_type_text.upper()
                indicator_source_text = (self.ind_source_combo.currentText() or "").strip()
                if indicator_source_text:
                    self.shared_binance.indicator_source = indicator_source_text
        except Exception:
            pass

        guard_obj = getattr(self, "guard", None)
        guard_can_open = getattr(guard_obj, "can_open", None) if guard_obj else None
        if guard_obj:
            try:
                if self.shared_binance is not None and hasattr(guard_obj, "attach_wrapper"):
                    guard_obj.attach_wrapper(self.shared_binance)
            except Exception as guard_attach_err:
                self.log(f"Guard attach error: {guard_attach_err}")
            if is_futures_account:
                try:
                    dual_enabled = False
                    if self.shared_binance is not None and hasattr(self.shared_binance, "get_futures_dual_side"):
                        dual_enabled = bool(self.shared_binance.get_futures_dual_side())
                    allow_opposite_cfg = coerce_bool(self.config.get("allow_opposite_positions"), True)
                    if hasattr(guard_obj, "allow_opposite"):
                        guard_obj.allow_opposite = dual_enabled and allow_opposite_cfg
                    if hasattr(guard_obj, "strict_symbol_side"):
                        guard_obj.strict_symbol_side = False
                    if dual_enabled and not allow_opposite_cfg:
                        self.log(
                            "Hedge mode detected on Binance account; opposite-side entries are disabled so the bot will close "
                            "existing positions before flipping."
                        )
                except Exception:
                    pass
            else:
                try:
                    if hasattr(guard_obj, "allow_opposite"):
                        guard_obj.allow_opposite = True
                except Exception:
                    pass
            try:
                if hasattr(guard_obj, "reset"):
                    guard_obj.reset()
            except Exception as guard_reset_err:
                self.log(f"Guard reset error: {guard_reset_err}")
            guard_jobs = [
                {"symbol": combo.get("symbol"), "interval": combo.get("interval")}
                for combo in combos
                if combo.get("symbol") and combo.get("interval")
            ]
            try:
                if hasattr(guard_obj, "reconcile_with_exchange"):
                    guard_account_type = str(
                        getattr(self.shared_binance, "account_type", account_type_text) or account_type_text
                    ).upper()
                    guard_obj.reconcile_with_exchange(
                        self.shared_binance,
                        guard_jobs,
                        account_type=guard_account_type,
                    )
            except Exception as guard_reconcile_err:
                self.log(f"Guard reconcile warning: {guard_reconcile_err}")

        for combo in combos:
            sym = combo.get("symbol")
            iv = combo.get("interval")
            if not sym or not iv:
                continue
            indicator_override = combo.get("indicators")
            indicator_list = []
            if isinstance(indicator_override, (list, tuple)):
                indicator_list = [str(k).strip() for k in indicator_override if str(k).strip()]
            elif indicator_override:
                indicator_list = [str(indicator_override).strip()]
            key = _make_engine_key(sym, iv, indicator_list)
            try:
                if key in self.strategy_engines and getattr(self.strategy_engines[key], "is_alive", lambda: False)():
                    self.log(f"Engine already running for {key}, skipping.")
                    continue

                controls = dict(combo.get("strategy_controls") or {})
                units_override = self._normalize_position_pct_units(controls.get("position_pct_units"))
                cfg = copy.deepcopy(self.config)
                cfg["symbol"] = sym
                cfg["interval"] = iv
                position_pct_override = controls.get("position_pct")
                if position_pct_override is not None:
                    try:
                        cfg["position_pct"] = float(position_pct_override)
                        if units_override:
                            cfg["position_pct_units"] = units_override
                        else:
                            cfg.pop("position_pct_units", None)
                    except Exception:
                        cfg["position_pct"] = float(self.pospct_spin.value() or self.config.get("position_pct", 100.0))
                        cfg["position_pct_units"] = "percent"
                else:
                    cfg["position_pct"] = float(self.pospct_spin.value() or self.config.get("position_pct", 100.0))
                    cfg["position_pct_units"] = "percent"
                side_override = controls.get("side") or self._resolve_dashboard_side()
                cfg["side"] = side_override
                leverage_override = controls.get("leverage")
                if leverage_override is not None:
                    try:
                        cfg["leverage"] = max(1, int(leverage_override))
                    except Exception:
                        pass
                stop_loss_override = controls.get("stop_loss")
                if isinstance(stop_loss_override, dict):
                    cfg["stop_loss"] = normalize_stop_loss_dict(copy.deepcopy(stop_loss_override))
                else:
                    cfg["stop_loss"] = normalize_stop_loss_dict(self.config.get("stop_loss"))
                account_mode_override = controls.get("account_mode")
                if account_mode_override:
                    cfg["account_mode"] = self._normalize_account_mode(account_mode_override)
                cfg["add_only"] = bool(controls.get("add_only", self.config.get("add_only", False)))
                loop_override_entry = controls.get("loop_interval_override") or default_loop_override
                loop_override_entry = self._normalize_loop_override(loop_override_entry)
                if loop_override_entry:
                    cfg["loop_interval_override"] = loop_override_entry
                else:
                    cfg.pop("loop_interval_override", None)

                indicators_cfg = cfg.get("indicators", {}) or {}
                if indicator_list:
                    indicator_set = set(indicator_list)
                    if isinstance(indicators_cfg, dict):
                        for ind_key, params in indicators_cfg.items():
                            try:
                                params["enabled"] = ind_key in indicator_set
                            except Exception:
                                try:
                                    indicators_cfg[ind_key] = dict(params)
                                    indicators_cfg[ind_key]["enabled"] = ind_key in indicator_set
                                except Exception:
                                    pass
                active_indicators = []
                try:
                    active_indicators = [
                        ind_key
                        for ind_key, params in indicators_cfg.items()
                        if isinstance(params, dict) and params.get("enabled")
                    ]
                except Exception:
                    active_indicators = []
                if not active_indicators:
                    if indicator_list:
                        active_indicators = list(indicator_list)
                    else:
                        active_indicators = self._get_selected_indicator_keys("runtime")
                # Track both configured indicator keys and any explicit overrides supplied
                active_indicators = sorted({str(k).strip() for k in (active_indicators or []) if str(k).strip()})
                override_indicators = sorted({str(k).strip() for k in (indicator_list or []) if str(k).strip()})

                eng = StrategyEngine(
                    self.shared_binance,
                    cfg,
                    log_callback=self.log,
                    trade_callback=self._on_trade_signal,
                    loop_interval_override=loop_override_entry,
                    can_open_callback=guard_can_open,
                )
                if guard_obj and hasattr(eng, "set_guard"):
                    try:
                        eng.set_guard(guard_obj)
                    except Exception:
                        pass
                eng.start()
                self.strategy_engines[key] = eng
                try:
                    self._engine_indicator_map[key] = {
                        "symbol": sym,
                        "interval": iv,
                        "side": cfg.get("side", "BOTH"),
                        "override_indicators": override_indicators,
                        "configured_indicators": active_indicators,
                        "stop_loss_enabled": bool(cfg.get("stop_loss", {}).get("enabled")),
                    }
                except Exception:
                    pass
                indicator_note = ""
                if active_indicators:
                    indicator_note = f" (Indicators: {_format_indicator_list(active_indicators)})"
                strat_summary = self._format_strategy_controls_summary("runtime", controls)
                summary_note = f" | {strat_summary}" if strat_summary and strat_summary != "-" else ""
                self.log(f"Loop start for {key}{indicator_note}{summary_note}.")
                started += 1
            except Exception as e:
                self.log(f"Failed to start engine for {key}: {e}")

        if started == 0:
            self.log("No new engines started (already running?)")
    except Exception as e:
        try:
            self.log(f"Start error: {e}")
        except Exception:
            pass
    finally:
        try:
            self._sync_runtime_state()
        except Exception:
            pass


def _stop_strategy_sync(self, close_positions: bool = True, auth: dict | None = None) -> dict:
    """Synchronous helper to stop engines and optionally close all positions."""
    result: dict = {"ok": True}
    try:
        try:
            self._is_stopping_engines = True
        except Exception:
            pass
        try:
            StrategyEngine.pause_trading()
        except Exception:
            pass
        try:
            guard_obj = getattr(self, "guard", None)
            if guard_obj and hasattr(guard_obj, "pause_new"):
                guard_obj.pause_new()
        except Exception:
            pass
        engines = {}
        if hasattr(self, "strategy_engines") and isinstance(self.strategy_engines, dict):
            engines = dict(self.strategy_engines)

        if engines:
            self._is_stopping_engines = True
            stop_deadline = time.time() + 2.5
            for _, eng in engines.items():
                try:
                    if hasattr(eng, "stop"):
                        eng.stop()
                except Exception:
                    pass
            for _, eng in engines.items():
                try:
                    remaining = max(0.0, stop_deadline - time.time())
                    if remaining <= 0.0:
                        break
                    eng.join(timeout=min(0.25, remaining))
                except Exception:
                    continue
            still_alive: list[str] = []
            for key, eng in engines.items():
                try:
                    alive = bool(getattr(eng, "is_alive", lambda: False)())
                except Exception:
                    alive = False
                if alive:
                    still_alive.append(str(key))
            try:
                self.strategy_engines.clear()
            except Exception:
                pass
            try:
                self._engine_indicator_map.clear()
            except Exception:
                pass
            if still_alive:
                self.log(f"Signaled loops to stop but {len(still_alive)} engine(s) are still shutting down: {', '.join(still_alive)}")
            else:
                self.log("Stopped all strategy engines.")
        else:
            self.log("No engines to stop.")

        close_result = None
        if close_positions:
            try:
                # Always use a fresh wrapper for close-all to honor current mode (Live/Demo) and credentials.
                if auth is None:
                    auth = _snapshot_auth_state(self)
                fast_close = False
                try:
                    mode_txt = str(auth.get("mode") or "").lower()
                    fast_close = any(tag in mode_txt for tag in ("demo", "test", "sandbox"))
                except Exception:
                    fast_close = False
                self.shared_binance = _build_wrapper_from_values(self, auth)
                try:
                    acct_text = str(auth.get("account_type") or "").upper()
                    if acct_text.startswith("FUT") and self.shared_binance is not None:
                        cancel_res = self.shared_binance.cancel_all_open_futures_orders()
                        result["cancel_open_orders_result"] = cancel_res
                except Exception as cancel_exc:
                    self.log(f"Cancel open orders failed: {cancel_exc}")
                close_result = self._close_all_positions_blocking(auth=auth, fast=fast_close)
                try:
                    acct_text = str(auth.get("account_type") or "").upper()
                    if acct_text.startswith("FUT") and self.shared_binance is not None:
                        cancel_res = self.shared_binance.cancel_all_open_futures_orders()
                        result["cancel_open_orders_after_close"] = cancel_res
                except Exception:
                    pass
            except Exception as exc:
                result["ok"] = False
                result["error"] = str(exc)
                self.log(f"Failed to trigger close-all: {exc}")
            result["close_all_result"] = close_result
    except Exception as e:
        result["ok"] = False
        result["error"] = str(e)
        try:
            self.log(f"Stop error: {e}")
        except Exception:
            pass
    finally:
        try:
            self._is_stopping_engines = False
        except Exception:
            pass
        result["_sync_runtime_state"] = True
    return result


def stop_strategy_async(self, close_positions: bool = False, blocking: bool = False):
    """Stop all StrategyEngine threads without auto-closing positions unless explicitly requested."""
    auth_snapshot = _snapshot_auth_state(self) if close_positions else None
    def _process_stop_result(res):
        if not isinstance(res, dict):
            return res
        if not res.get("ok", True):
            try:
                self.log(f"Stop warning: {res.get('error')}")
            except Exception:
                pass
        close_details = res.get("close_all_result", None)
        if close_details is not None:
            try:
                _handle_close_all_result(self, close_details)
            except Exception:
                pass
        if res.get("_sync_runtime_state"):
            try:
                self._sync_runtime_state()
            except Exception:
                pass
        return res

    if blocking:
        return _process_stop_result(_stop_strategy_sync(self, close_positions=close_positions, auth=auth_snapshot))

    try:
        from ..workers import CallWorker as _CallWorker
    except Exception:
        # fallback to synchronous if worker import fails
        return _process_stop_result(_stop_strategy_sync(self, close_positions=close_positions, auth=auth_snapshot))

    def _do():
        return _stop_strategy_sync(self, close_positions=close_positions, auth=auth_snapshot)

    def _done(res, err):
        if err:
            try:
                self.log(f"Stop error: {err}")
            except Exception:
                pass
            return
        _process_stop_result(res)

    worker = _CallWorker(_do, parent=self)
    try:
        worker.progress.connect(self.log)
    except Exception:
        pass
    worker.done.connect(_done)
    worker.finished.connect(worker.deleteLater)

    if not hasattr(self, "_bg_workers"):
        self._bg_workers = []
    self._bg_workers.append(worker)

    def _cleanup():
        try:
            self._bg_workers.remove(worker)
        except Exception:
            pass

    worker.finished.connect(_cleanup)
    worker.start()


def save_config(self):
    try:
        from PyQt6 import QtWidgets
        import json
        dlg = QtWidgets.QFileDialog(self)
        dlg.setAcceptMode(QtWidgets.QFileDialog.AcceptMode.AcceptSave)
        dlg.setNameFilter("JSON Files (*.json)")
        dlg.setDefaultSuffix("json")
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            fn = dlg.selectedFiles()[0]
            with open(fn, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            self.log(f"Saved config to {fn}")
    except Exception as e:
        try:
            self.log(f"Save config error: {e}")
        except Exception:
            pass


def load_config(self):
    try:
        from PyQt6 import QtWidgets
        import json
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Load Config", "", "JSON Files (*.json)")
        if not fn:
            return
        with open(fn, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if isinstance(cfg, dict):
            self.config.update(cfg)
        self.config["stop_loss"] = normalize_stop_loss_dict(self.config.get("stop_loss"))
        backtest_cfg = self.config.get("backtest", {})
        if not isinstance(backtest_cfg, dict):
            backtest_cfg = {}
        backtest_cfg = copy.deepcopy(backtest_cfg)
        backtest_cfg["stop_loss"] = normalize_stop_loss_dict(backtest_cfg.get("stop_loss"))
        self.config["backtest"] = backtest_cfg
        self.backtest_config.update(copy.deepcopy(backtest_cfg))
        chart_cfg = self.config.get("chart")
        if not isinstance(chart_cfg, dict):
            chart_cfg = {}
        self.config["chart"] = chart_cfg
        self.chart_config = chart_cfg
        if getattr(self, "chart_enabled", False):
            self.chart_config.setdefault("auto_follow", True)
            self.chart_auto_follow = bool(self.chart_config.get("auto_follow", True))
            default_view_mode = "tradingview" if _tradingview_supported() else "original"
            self.chart_config.setdefault("view_mode", default_view_mode)
            self._restore_chart_controls_from_config()
            current_market_text = self.chart_market_combo.currentText() if hasattr(self, "chart_market_combo") else "Futures"
            self._chart_needs_render = True
            self._on_chart_market_changed(current_market_text)
            if self.chart_auto_follow:
                self._apply_dashboard_selection_to_chart(load=True)
            elif QT_CHARTS_AVAILABLE:
                try:
                    if self._is_chart_visible() or self._chart_pending_initial_load:
                        self.load_chart(auto=True)
                except Exception:
                    pass
        self.config.setdefault('runtime_symbol_interval_pairs', [])
        self.config.setdefault('backtest_symbol_interval_pairs', [])
        self.backtest_config.setdefault('backtest_symbol_interval_pairs', list(self.config.get('backtest_symbol_interval_pairs', [])))
        self._refresh_symbol_interval_pairs("runtime")
        self._refresh_symbol_interval_pairs("backtest")
        self.config.setdefault("code_language", next(iter(LANGUAGE_PATHS)))
        self.config.setdefault("selected_exchange", next(iter(EXCHANGE_PATHS)))
        if FOREX_BROKER_PATHS:
            self.config.setdefault("selected_forex_broker", next(iter(FOREX_BROKER_PATHS)))
        else:
            self.config.setdefault("selected_forex_broker", None)
        self._sync_language_exchange_lists_from_config()
        self.log(f"Loaded config from {fn}")
        try:
            self.leverage_spin.setValue(int(self.config.get("leverage", self.leverage_spin.value())))
            self.margin_mode_combo.setCurrentText(self.config.get("margin_mode", self.margin_mode_combo.currentText()))
            self.position_mode_combo.setCurrentText(self.config.get("position_mode", self.position_mode_combo.currentText()))
            assets_mode_loaded = self._normalize_assets_mode(self.config.get("assets_mode", self.assets_mode_combo.currentData()))
            idx_assets_loaded = self.assets_mode_combo.findData(assets_mode_loaded)
            if idx_assets_loaded is not None and idx_assets_loaded >= 0:
                with QtCore.QSignalBlocker(self.assets_mode_combo):
                    self.assets_mode_combo.setCurrentIndex(idx_assets_loaded)
            account_mode_loaded = self._normalize_account_mode(self.config.get("account_mode", self.account_mode_combo.currentData()))
            idx_account_loaded = self.account_mode_combo.findData(account_mode_loaded)
            if idx_account_loaded is not None and idx_account_loaded >= 0:
                with QtCore.QSignalBlocker(self.account_mode_combo):
                    self.account_mode_combo.setCurrentIndex(idx_account_loaded)
            self.tif_combo.setCurrentText(self.config.get("tif", self.tif_combo.currentText()))
            self.gtd_minutes_spin.setValue(int(self.config.get("gtd_minutes", self.gtd_minutes_spin.value())))
            backtest_assets_mode_loaded = self._normalize_assets_mode(self.backtest_config.get("assets_mode", self.backtest_assets_mode_combo.currentData()))
            idx_backtest_assets = self.backtest_assets_mode_combo.findData(backtest_assets_mode_loaded)
            if idx_backtest_assets is not None and idx_backtest_assets >= 0:
                with QtCore.QSignalBlocker(self.backtest_assets_mode_combo):
                    self.backtest_assets_mode_combo.setCurrentIndex(idx_backtest_assets)
            backtest_account_mode_loaded = self._normalize_account_mode(self.backtest_config.get("account_mode", self.backtest_account_mode_combo.currentData()))
            idx_backtest_account = self.backtest_account_mode_combo.findData(backtest_account_mode_loaded)
            if idx_backtest_account is not None and idx_backtest_account >= 0:
                with QtCore.QSignalBlocker(self.backtest_account_mode_combo):
                    self.backtest_account_mode_combo.setCurrentIndex(idx_backtest_account)
            self._apply_runtime_account_mode_constraints(account_mode_loaded)
            self._apply_backtest_account_mode_constraints(backtest_account_mode_loaded)
            loop_loaded = self._normalize_loop_override(self.config.get("loop_interval_override"))
            if not loop_loaded:
                loop_loaded = "1m"
            self._set_loop_combo_value(getattr(self, "loop_combo", None), loop_loaded)
            self.config["loop_interval_override"] = loop_loaded or ""
            backtest_loop_loaded = self._normalize_loop_override(self.backtest_config.get("loop_interval_override"))
            self._set_loop_combo_value(getattr(self, "backtest_loop_combo", None), backtest_loop_loaded)
            self.backtest_config["loop_interval_override"] = backtest_loop_loaded or ""
            self.config.setdefault("backtest", {})["loop_interval_override"] = backtest_loop_loaded or ""
            lead_enabled_loaded = bool(self.config.get("lead_trader_enabled", False))
            if hasattr(self, "lead_trader_enable_cb") and self.lead_trader_enable_cb is not None:
                with QtCore.QSignalBlocker(self.lead_trader_enable_cb):
                    self.lead_trader_enable_cb.setChecked(lead_enabled_loaded)
            lead_profile_loaded = self.config.get("lead_trader_profile") or LEAD_TRADER_OPTIONS[0][1]
            if hasattr(self, "lead_trader_combo") and self.lead_trader_combo is not None:
                idx_lead_loaded = self.lead_trader_combo.findData(lead_profile_loaded)
                if idx_lead_loaded < 0:
                    idx_lead_loaded = 0
                with QtCore.QSignalBlocker(self.lead_trader_combo):
                    self.lead_trader_combo.setCurrentIndex(idx_lead_loaded)
                self.config["lead_trader_profile"] = str(self.lead_trader_combo.itemData(self.lead_trader_combo.currentIndex()))
            self._apply_lead_trader_state(lead_enabled_loaded)
            runtime_backend = self._runtime_connector_backend(suppress_refresh=True)
            if hasattr(self, "connector_combo") and self.connector_combo is not None:
                idx_runtime_connector = self.connector_combo.findData(runtime_backend)
                if idx_runtime_connector is not None and idx_runtime_connector >= 0:
                    with QtCore.QSignalBlocker(self.connector_combo):
                        self.connector_combo.setCurrentIndex(idx_runtime_connector)
            backtest_backend = self._backtest_connector_backend()
            if hasattr(self, "backtest_connector_combo") and self.backtest_connector_combo is not None:
                idx_backtest_connector = self.backtest_connector_combo.findData(backtest_backend)
                if idx_backtest_connector is not None and idx_backtest_connector >= 0:
                    with QtCore.QSignalBlocker(self.backtest_connector_combo):
                        self.backtest_connector_combo.setCurrentIndex(idx_backtest_connector)
            self._update_runtime_stop_loss_widgets()
            self._update_backtest_stop_loss_widgets()
            self._update_connector_labels()
        except Exception:
            pass
    except Exception as e:
        try:
            self.log(f"Load config error: {e}")
        except Exception:
            pass

def refresh_positions(self, symbols=None, *args, **kwargs):
    """Manual refresh of positions: reconfigure worker and trigger an immediate tick."""
    try:
        try:
            self._reconfigure_positions_worker(symbols=symbols)
        except Exception:
            pass
        try:
            self.trigger_positions_refresh()
        except Exception:
            pass
        self.log("Positions refresh requested.")
    except Exception as e:
        try:
            self.log(f"Refresh positions error: {e}")
        except Exception:
            pass


def _apply_positions_refresh_settings(self):
    try:
        raw_val = self.config.get("positions_refresh_interval_ms", getattr(self, "_pos_refresh_interval_ms", 5000))
        try:
            interval = int(raw_val)
        except Exception:
            interval = getattr(self, "_pos_refresh_interval_ms", 5000)
        interval = max(2000, min(interval, 60000))
        self._pos_refresh_interval_ms = interval
        self.config["positions_refresh_interval_ms"] = interval
        self.req_pos_start.emit(interval)
    except Exception:
        pass


def trigger_positions_refresh(self, interval_ms: int | None = None):
    try:
        if interval_ms is None:
            interval = getattr(self, "_pos_refresh_interval_ms", 5000)
        else:
            interval = int(interval_ms)
    except Exception:
        interval = getattr(self, "_pos_refresh_interval_ms", 5000)
    if interval <= 0:
        interval = 5000
    self._pos_refresh_interval_ms = interval
    try:
        self.req_pos_start.emit(interval)
    except Exception:
        pass

try:
    MainWindow.start_strategy = start_strategy
except Exception:
    pass
try:
    MainWindow.stop_strategy_async = stop_strategy_async
except Exception:
    pass
try:
    MainWindow.save_config = save_config
    MainWindow.load_config = load_config
except Exception:
    pass
try:
    MainWindow._open_external_url = _open_external_url
    MainWindow._build_liquidation_web_panel = _build_liquidation_web_panel
    MainWindow._init_liquidation_heatmap_tab = _init_liquidation_heatmap_tab
    MainWindow._init_code_language_tab = _init_code_language_tab
    MainWindow._sync_language_exchange_lists_from_config = _sync_language_exchange_lists_from_config
    MainWindow._ensure_language_exchange_paths = _ensure_language_exchange_paths
    MainWindow._rebuild_dependency_version_rows = _rebuild_dependency_version_rows
    MainWindow._refresh_dependency_versions = _refresh_dependency_versions
    MainWindow._apply_dependency_version_results = _apply_dependency_version_results
    MainWindow._on_code_language_changed = _on_code_language_changed
    MainWindow._on_exchange_selection_changed = _on_exchange_selection_changed
    MainWindow._on_exchange_list_changed = _on_exchange_list_changed
    MainWindow._on_forex_selection_changed = _on_forex_selection_changed
    MainWindow._code_tab_select_language = _code_tab_select_language
    MainWindow._code_tab_select_market = _code_tab_select_market
    MainWindow._code_tab_select_exchange = _code_tab_select_exchange
    MainWindow._code_tab_select_forex = _code_tab_select_forex
    MainWindow._refresh_code_tab_from_config = _refresh_code_tab_from_config
    MainWindow._update_code_tab_market_sections = _update_code_tab_market_sections
except Exception:
    pass
try:
    MainWindow.refresh_symbols = refresh_symbols
except Exception:
    pass
try:
    MainWindow.apply_futures_modes = apply_futures_modes
except Exception:
    pass
try:
    MainWindow.on_leverage_changed = on_leverage_changed
except Exception:
    pass
try:
    MainWindow.refresh_positions = refresh_positions
except Exception:
    pass
try:
    MainWindow._apply_positions_refresh_settings = _apply_positions_refresh_settings
    MainWindow.trigger_positions_refresh = trigger_positions_refresh
except Exception:
    pass

def _snapshot_auth_state(self) -> dict:
    """Capture auth/mode state on the UI thread to avoid cross-thread UI access in workers."""
    try:
        api_key = self.api_key_edit.text().strip()
    except Exception:
        api_key = ""
    try:
        api_secret = self.api_secret_edit.text().strip()
    except Exception:
        api_secret = ""
    try:
        mode = self.mode_combo.currentText()
    except Exception:
        mode = "Live"
    try:
        account_type = self.account_combo.currentText()
    except Exception:
        account_type = "Futures"
    try:
        leverage_val = int(self.leverage_spin.value() or 1)
    except Exception:
        leverage_val = 1
    try:
        margin_mode = self.margin_mode_combo.currentText() or "Isolated"
    except Exception:
        margin_mode = "Isolated"
    return {
        "api_key": api_key,
        "api_secret": api_secret,
        "mode": mode,
        "account_type": account_type,
        "default_leverage": leverage_val,
        "default_margin_mode": margin_mode,
    }

def _build_wrapper_from_values(self, auth: dict):
    return self._create_binance_wrapper(
        api_key=auth.get("api_key", ""),
        api_secret=auth.get("api_secret", ""),
        mode=auth.get("mode", "Live"),
        account_type=auth.get("account_type", "Futures"),
        default_leverage=int(auth.get("default_leverage", 1) or 1),
        default_margin_mode=auth.get("default_margin_mode", "Isolated") or "Isolated",
    )

def _build_wrapper_from_ui(self):
    """Always build a fresh wrapper using current UI values (mode, account, creds)."""
    return _build_wrapper_from_values(self, _snapshot_auth_state(self))

def _close_all_positions_sync(self, auth: dict | None = None, *, fast: bool = False):
    from ..close_all import close_all_futures_positions as _close_all_futures
    # Rebuild wrapper each time so close-all uses latest mode/credentials even if launch-time wrapper was different.
    if auth is None:
        auth = _snapshot_auth_state(self)
    timeout_override = None
    if fast:
        timeout_override = {
            "BINANCE_HTTP_CONNECT_TIMEOUT": os.environ.get("BINANCE_HTTP_CONNECT_TIMEOUT"),
            "BINANCE_HTTP_READ_TIMEOUT": os.environ.get("BINANCE_HTTP_READ_TIMEOUT"),
        }
        os.environ["BINANCE_HTTP_CONNECT_TIMEOUT"] = "2"
        os.environ["BINANCE_HTTP_READ_TIMEOUT"] = "6"
    try:
        self.shared_binance = _build_wrapper_from_values(self, auth)
        acct_text = str(auth.get("account_type") or "").upper() or (self.account_combo.currentText().upper() if hasattr(self, "account_combo") else "")
        if acct_text.startswith('FUT'):
            results = _close_all_futures(self.shared_binance, fast=fast) or []
            if not fast:
                # Verification loop: re-run close-all if any positions remain.
                try:
                    for _ in range(3):
                        remaining = []
                        try:
                            remaining = self.shared_binance.list_open_futures_positions(force_refresh=True) or []
                        except Exception:
                            remaining = []
                        open_left = [p for p in remaining if abs(float(p.get("positionAmt") or 0.0)) > 0.0]
                        if not open_left:
                            break
                        # Attempt another sweep
                        more = _close_all_futures(self.shared_binance) or []
                        results.extend(more)
                except Exception:
                    pass
            return results
        return self.shared_binance.close_all_spot_positions()
    finally:
        if timeout_override is not None:
            for key, old_val in timeout_override.items():
                if old_val is None:
                    try:
                        os.environ.pop(key, None)
                    except Exception:
                        pass
                else:
                    os.environ[key] = old_val

def _handle_close_all_result(self, res):
    try:
        details = res or []
        for r in details:
            sym = r.get('symbol') or '?'
            if not r.get('ok'):
                self.log(f"Close-all {sym}: error -> {r.get('error')}")
            elif r.get('skipped'):
                self.log(f"Close-all {sym}: skipped ({r.get('reason')})")
            else:
                self.log(f"Close-all {sym}: ok")
        n_ok = sum(1 for r in details if r.get('ok'))
        n_all = len(details)
        self.log(f"Close-all completed: {n_ok}/{n_all} ok.")
    except Exception:
        self.log(f"Close-all result: {res}")
    try:
        _apply_close_all_to_positions_cache(self, res)
    except Exception:
        pass
    try:
        self.refresh_positions()
    except Exception:
        pass
    try:
        self.trigger_positions_refresh()
    except Exception:
        pass



def _apply_close_all_to_positions_cache(self, res) -> None:
    """Mark local position state as closed when a close-all command succeeds."""
    details = res or []
    if isinstance(details, dict):
        details = [details]
    elif not isinstance(details, (list, tuple, set)):
        details = [details]

    symbols_to_mark: set[str] = set()
    had_error = False
    for item in details:
        if not isinstance(item, dict):
            continue
        sym_raw = str(item.get("symbol") or "").strip().upper()
        if not sym_raw:
            continue
        ok_flag = bool(item.get("ok"))
        skipped_flag = bool(item.get("skipped"))
        if ok_flag or skipped_flag:
            symbols_to_mark.add(sym_raw)
        else:
            had_error = True

    open_records = getattr(self, "_open_position_records", {}) or {}
    if not symbols_to_mark and not had_error and open_records:
        symbols_to_mark = {sym for sym, _ in open_records.keys()}
    if not symbols_to_mark:
        return

    from datetime import datetime as _dt

    pending_close = getattr(self, "_pending_close_times", None)
    if not isinstance(pending_close, dict):
        pending_close = {}
        self._pending_close_times = pending_close
    missing_counts = getattr(self, "_position_missing_counts", None)
    if not isinstance(missing_counts, dict):
        missing_counts = {}
        self._position_missing_counts = missing_counts

    close_time_fmt = self._format_display_time(_dt.now().astimezone())
    alloc_map = getattr(self, "_entry_allocations", {})
    closed_records = getattr(self, "_closed_position_records", None)
    if not isinstance(closed_records, list):
        closed_records = []
        self._closed_position_records = closed_records

    for key in list(open_records.keys()):
        sym_key, side_key = key
        record = open_records.get(key)
        if sym_key not in symbols_to_mark:
            continue
        if key not in pending_close:
            pending_close[key] = close_time_fmt
        missing_counts[key] = 0
        try:
            intervals_map = getattr(self, "_entry_intervals", {})
            side_bucket = intervals_map.get(sym_key, {}).get(side_key)
            if hasattr(self, "_track_interval_close") and isinstance(side_bucket, set):
                for interval in list(side_bucket):
                    self._track_interval_close(sym_key, side_key, interval)
        except Exception:
            pass

        snap = copy.deepcopy(record) if isinstance(record, dict) else {
            "symbol": sym_key,
            "side_key": side_key,
            "status": "Closed",
            "open_time": "-",
            "close_time": close_time_fmt,
            "data": {},
            "indicators": [],
            "stop_loss_enabled": False,
        }
        snap["status"] = "Closed"
        snap["close_time"] = close_time_fmt
        if "stop_loss_enabled" not in snap:
            snap["stop_loss_enabled"] = bool((record or {}).get("stop_loss_enabled"))

        base_data = dict((record or {}).get("data") or {})
        snap["data"] = base_data
        try:
            alloc_entries = copy.deepcopy(alloc_map.get(key, [])) or []
            for alloc_entry in alloc_entries:
                if isinstance(alloc_entry, dict):
                    normalized_triggers = _resolve_trigger_indicators(alloc_entry.get("trigger_indicators"), alloc_entry.get("trigger_desc"))
                    if normalized_triggers:
                        alloc_entry["trigger_indicators"] = normalized_triggers
                    elif alloc_entry.get("trigger_indicators"):
                        alloc_entry.pop("trigger_indicators", None)
        except Exception:
            alloc_entries = []
        if alloc_entries:
            snap["allocations"] = alloc_entries
        closed_records.insert(0, snap)
        if len(closed_records) > MAX_CLOSED_HISTORY:
            del closed_records[MAX_CLOSED_HISTORY:]
        alloc_map.pop(key, None)
        open_records.pop(key, None)
        try:
            getattr(self, "_entry_times", {}).pop(key, None)
        except Exception:
            pass
        try:
            iv_times = getattr(self, "_entry_times_by_iv", {})
            if isinstance(iv_times, dict):
                for (sym, side, interval) in list(iv_times.keys()):
                    if sym == sym_key and side == side_key:
                        iv_times.pop((sym, side, interval), None)
        except Exception:
            pass

    try:
        self._open_position_records = dict(open_records)
    except Exception:
        self._open_position_records = open_records
    try:
        self._update_global_pnl_display(*self._compute_global_pnl_totals())
    except Exception:
        pass
    try:
        self._render_positions_table()
    except Exception:
        pass


def _close_all_positions_blocking(self, auth: dict | None = None, *, fast: bool = False):
    return _close_all_positions_sync(self, auth=auth, fast=fast)

def close_all_positions_async(self):
    """Close all open futures positions using reduce-only market orders in a worker."""
    try:
        from ..workers import CallWorker as _CallWorker
        auth_snapshot = _snapshot_auth_state(self)
        fast_close = False
        try:
            mode_txt = str(auth_snapshot.get("mode") or "").lower()
            fast_close = any(tag in mode_txt for tag in ("demo", "test", "sandbox"))
        except Exception:
            fast_close = False
        def _do():
            return _close_all_positions_sync(self, auth=auth_snapshot, fast=fast_close)
        def _done(res, err):
            if err:
                self.log(f"Close-all error: {err}")
                return
            _handle_close_all_result(self, res)
        w = _CallWorker(_do, parent=self)
        try:
            w.progress.connect(self.log)
        except Exception:
            pass
        w.done.connect(_done)
        if not hasattr(self, "_bg_workers"):
            self._bg_workers = []
        self._bg_workers.append(w)
        def _cleanup():
            try:
                self._bg_workers.remove(w)
            except Exception:
                pass
        try:
            w.finished.connect(_cleanup)
        except Exception:
            pass
        w.start()
    except Exception as e:
        try:
            self.log(f"Close-all setup error: {e}")
        except Exception:
            pass

try:
    MainWindow.close_all_positions_async = close_all_positions_async
    MainWindow._close_all_positions_sync = _close_all_positions_sync
    MainWindow._close_all_positions_blocking = _close_all_positions_blocking
    MainWindow._handle_close_all_result = _handle_close_all_result
except Exception:
    pass


def update_balance_label(self):
    """Refresh the 'Total USDT balance' label safely after an order."""
    from ..workers import CallWorker as _CallWorker
    btn = getattr(self, "refresh_balance_btn", None)
    old_btn_text = btn.text() if btn else None
    refresh_token = time.monotonic()
    try:
        self._balance_refresh_token = refresh_token
    except Exception:
        pass
    if btn:
        try:
            btn.setEnabled(False)
            btn.setText("Refreshing...")
        except Exception:
            pass
    try:
        if getattr(self, "balance_label", None):
            self.balance_label.setText("Refreshing...")
    except Exception:
        pass

    # Capture UI state up front (safe on UI thread).
    try:
        api_key = (self.api_key_edit.text() or "").strip()
        api_secret = (self.api_secret_edit.text() or "").strip()
    except Exception:
        api_key = ""
        api_secret = ""
    try:
        mode_value = getattr(self.mode_combo, "currentText", lambda: "Live")()
    except Exception:
        mode_value = "Live"
    try:
        account_value = getattr(self.account_combo, "currentText", lambda: "Futures")()
    except Exception:
        account_value = "Futures"
    try:
        default_leverage = int(self.leverage_spin.value() or 1)
    except Exception:
        default_leverage = 1
    try:
        default_margin_mode = self.margin_mode_combo.currentText() or "Isolated"
    except Exception:
        default_margin_mode = "Isolated"
    try:
        connector_raw = None
        if hasattr(self, "connector_combo") and self.connector_combo is not None:
            connector_raw = self.connector_combo.currentData()
            if connector_raw is None:
                connector_raw = self.connector_combo.currentText()
        connector_backend = _normalize_connector_backend(connector_raw)
    except Exception:
        connector_backend = None

    if not api_key or not api_secret:
        if getattr(self, "balance_label", None):
            self.balance_label.setText("API credentials missing")
        self._update_positions_balance_labels(None, None)
        try:
            self._balance_refresh_token = None
        except Exception:
            pass
        if btn:
            try:
                btn.setEnabled(True)
                if old_btn_text is not None:
                    btn.setText(old_btn_text)
            except Exception:
                pass
        return

    wrapper_holder: dict[str, object | None] = {"wrapper": None}

    def _do():
        # Run network work off the UI thread to avoid freezing on bad credentials/slow responses.
        wrapper = getattr(self, "shared_binance", None)
        try:
            needs_rebuild = True
            if wrapper is not None:
                try:
                    needs_rebuild = (
                        str(getattr(wrapper, "api_key", "") or "") != api_key
                        or str(getattr(wrapper, "api_secret", "") or "") != api_secret
                        or str(getattr(wrapper, "mode", "") or "") != str(mode_value or "")
                        or str(getattr(wrapper, "account_type", "") or "").upper()
                        != str(account_value or "").strip().upper()
                        or (
                            connector_backend is not None
                            and str(getattr(wrapper, "_connector_backend", "") or "") != str(connector_backend or "")
                        )
                    )
                except Exception:
                    needs_rebuild = True
            if wrapper is None or needs_rebuild:
                wrapper = self._create_binance_wrapper(
                    api_key=api_key,
                    api_secret=api_secret,
                    mode=mode_value,
                    account_type=account_value,
                    connector_backend=connector_backend,
                    default_leverage=default_leverage,
                    default_margin_mode=default_margin_mode,
                )
            try:
                wrapper_holder["wrapper"] = wrapper
            except Exception:
                pass
            total_balance_value = None
            available_balance_value = None
            bal = 0.0
            acct_upper = str(account_value or "").upper()
            if acct_upper.startswith("FUT"):
                snap = wrapper.get_futures_balance_snapshot(force_refresh=True) or {}
                if not isinstance(snap, dict):
                    raise RuntimeError(f"Unexpected futures balance snapshot type: {type(snap).__name__}")
                try:
                    total_balance_value = float(snap.get("total") or snap.get("wallet") or 0.0)
                except Exception:
                    total_balance_value = 0.0
                try:
                    available_balance_value = float(snap.get("available") or 0.0)
                except Exception:
                    available_balance_value = 0.0
                bal = available_balance_value if available_balance_value > 0.0 else total_balance_value
            else:
                bal = float(wrapper.get_spot_balance("USDT") or 0.0)
                try:
                    total_balance_value = float(wrapper.get_total_usdt_value() or bal)
                except Exception:
                    total_balance_value = bal
                available_balance_value = bal
            return {"total": total_balance_value, "available": available_balance_value, "bal": bal, "wrapper": wrapper}
        except Exception as exc:
            return {"error": str(exc), "wrapper": wrapper}

    def _done(res, err):
        if getattr(self, "_balance_refresh_token", None) != refresh_token:
            return
        try:
            self._balance_refresh_token = None
        except Exception:
            pass
        try:
            if getattr(self, "_balance_refresh_worker", None) is worker:
                self._balance_refresh_worker = None
        except Exception:
            pass
        total_balance_value = None
        available_balance_value = None
        err_msg = None
        if err:
            err_msg = str(err)
        elif isinstance(res, dict) and res.get("error"):
            err_msg = str(res.get("error"))
        if err_msg or not res:
            try:
                wrapper_obj = wrapper_holder.get("wrapper")
                if wrapper_obj is not None:
                    self.shared_binance = wrapper_obj
            except Exception:
                pass
            try:
                self.log(f"Balance error: {err_msg or 'unknown error'}")
            except Exception:
                pass
            try:
                if getattr(self, "balance_label", None):
                    msg = str(err_msg or "unknown error").replace("\n", " ").strip()
                    try:
                        self.balance_label.setToolTip(msg)
                    except Exception:
                        pass
                    label_text = None
                    try:
                        import re as _re
                        m = _re.search(r"\\bcode=([-]?[0-9]+)\\b", msg)
                        code_val = int(m.group(1)) if m else None
                    except Exception:
                        code_val = None
                    if code_val in (-2014, -2015):
                        mode_txt = str(mode_value or "").lower()
                        is_test = ("test" in mode_txt) or ("demo" in mode_txt) or ("sandbox" in mode_txt)
                        acct_txt = str(account_value or "").upper()
                        if acct_txt.startswith("FUT") and is_test:
                            if ("Spot Testnet keys" in msg) or ("accepted on Spot Testnet" in msg):
                                label_text = (
                                    f"Wrong API key for Futures Testnet (code {code_val}). "
                                    "Use FUTURES Testnet keys."
                                )
                            elif ("rejected by both Spot/Futures Testnet" in msg) or ("rejected by both Spot and Futures Testnet" in msg):
                                label_text = (
                                    f"API key rejected by Testnet (code {code_val}). "
                                    "Check permissions/IP."
                                )
                            else:
                                label_text = (
                                    f"Futures Testnet key rejected (code {code_val}). "
                                    "Check permissions/IP: testnet.binancefuture.com (see Log)."
                                )
                                try:
                                    now_ts = float(time.time())
                                    last_ts = float(getattr(self, "_last_auth_help_ts", 0.0) or 0.0)
                                    if (now_ts - last_ts) > 60.0:
                                        self._last_auth_help_ts = now_ts
                                        self.log("Futures Testnet auth error (-2015/-2014). Checklist:")
                                        self.log("1) Use FUTURES Testnet keys from https://testnet.binancefuture.com (not Spot Testnet / live).")
                                        self.log("2) In API Key settings enable Futures + Reading; disable IP restriction or whitelist your IP.")
                                        self.log("3) If using VPN, your public IP changes; whitelist the current one.")
                                        try:
                                            ip = None
                                            with urllib.request.urlopen("https://api.ipify.org", timeout=5) as resp:
                                                ip = (resp.read(64) or b"").decode("utf-8", "ignore").strip()
                                            if ip and re.match(r"^[0-9]{1,3}(\\.[0-9]{1,3}){3}$", ip):
                                                self.log(f"Detected public IP: {ip}")
                                        except Exception:
                                            pass
                                except Exception:
                                    pass
                        elif is_test:
                            label_text = (
                                f"Testnet key rejected (code {code_val}). "
                                "Spot keys: testnet.binance.vision (see Log)."
                            )
                        else:
                            label_text = f"API key rejected (code {code_val}). Check permissions/IP (see Log)."
                    if label_text is None:
                        short = msg if len(msg) <= 120 else (msg[:117] + "...")
                        label_text = f"Balance error: {short}"
                    self.balance_label.setText(label_text)
            except Exception:
                pass
            self._update_positions_balance_labels(None, None)
        else:
            total_balance_value = res.get("total")
            available_balance_value = res.get("available")
            bal = res.get("bal", 0.0)
            try:
                wrapper_obj = res.get("wrapper")
                if wrapper_obj is not None:
                    self.shared_binance = wrapper_obj
            except Exception:
                pass
            try:
                if getattr(self, "balance_label", None):
                    try:
                        self.balance_label.setToolTip("")
                    except Exception:
                        pass
                    total_txt = f"{(total_balance_value if total_balance_value is not None else bal):.3f}"
                    avail_txt = f"{(available_balance_value if available_balance_value is not None else bal):.3f}"
                    if abs(float(total_txt) - float(avail_txt)) > 1e-6:
                        self.balance_label.setText(f"Total {total_txt} USDT | Available {avail_txt} USDT")
                    else:
                        self.balance_label.setText(f"{total_txt} USDT")
            except Exception:
                pass
            try:
                self._update_positions_balance_labels(total_balance_value, available_balance_value)
            except Exception:
                pass
        if btn:
            try:
                btn.setEnabled(True)
                if old_btn_text is not None:
                    btn.setText(old_btn_text)
            except Exception:
                pass

    worker = _CallWorker(_do, parent=self)
    try:
        self._balance_refresh_worker = worker
    except Exception:
        pass
    try:
        worker.progress.connect(self.log)
    except Exception:
        pass
    worker.done.connect(_done)
    worker.start()

    def _watchdog(expected_token: float):
        if getattr(self, "_balance_refresh_token", None) != expected_token:
            return
        try:
            running = bool(worker.isRunning())
        except Exception:
            running = False
        if not running:
            return
        try:
            self._balance_refresh_token = None
        except Exception:
            pass
        try:
            self._balance_refresh_worker = None
        except Exception:
            pass
        try:
            self.log("Balance refresh timed out; please check testnet connectivity/credentials and try again.")
        except Exception:
            pass
        try:
            if getattr(self, "balance_label", None):
                self.balance_label.setText("Balance timeout")
        except Exception:
            pass
        try:
            self._update_positions_balance_labels(None, None)
        except Exception:
            pass
        if btn:
            try:
                btn.setEnabled(True)
                if old_btn_text is not None:
                    btn.setText(old_btn_text)
            except Exception:
                pass

    QtCore.QTimer.singleShot(120000, lambda t=refresh_token: _watchdog(t))

try:
    MainWindow.update_balance_label = update_balance_label
except Exception:
    pass


# --- Graceful teardown to avoid "QThread destroyed while running" and timer warnings ---
def _teardown_positions_thread(self):
    try:
        if getattr(self, "_pos_worker", None) is not None:
            try:
                # Ask the worker (in its own thread) to stop its QTimer
                self.req_pos_stop.emit()
            except Exception:
                pass
        if getattr(self, "_pos_thread", None) is not None:
            try:
                self._pos_thread.quit()
                # wait up to 2 seconds for a clean exit
                self._pos_thread.wait(2000)
            except Exception:
                pass
        self._pos_worker = None
        self._pos_thread = None
    except Exception:
        pass

def _log_window_event(self, name: str, event=None) -> None:
    try:
        visible = int(bool(self.isVisible()))
    except Exception:
        visible = -1
    try:
        minimized = int(bool(self.windowState() & QtCore.Qt.WindowState.WindowMinimized))
    except Exception:
        minimized = -1
    try:
        spontaneous = int(bool(event.spontaneous())) if event is not None else -1
    except Exception:
        spontaneous = -1
    try:
        now = time.monotonic()
    except Exception:
        now = 0.0
    try:
        we_active = int(bool(getattr(self, "_webengine_close_guard_active", False)))
    except Exception:
        we_active = -1
    try:
        we_until = float(getattr(self, "_webengine_close_guard_until", 0.0) or 0.0)
    except Exception:
        we_until = 0.0
    try:
        we_rem_ms = int(max(0.0, (we_until - now) * 1000.0)) if we_until else 0
    except Exception:
        we_rem_ms = -1
    msg = (
        f"window_event {name} visible={visible} minimized={minimized} spontaneous={spontaneous} "
        f"we_guard={we_active} we_rem_ms={we_rem_ms}"
    )
    try:
        logger = getattr(self, "_chart_debug_log", None)
        if callable(logger):
            logger(msg)
            return
    except Exception:
        pass
    try:
        path = Path(os.getenv("TEMP") or ".").resolve() / "binance_chart_debug.log"
        with open(path, "a", encoding="utf-8", errors="ignore") as fh:
            fh.write(f"[{datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %z')}] {msg}\n")
    except Exception:
        pass

def _allow_guard_bypass(self) -> bool:
    try:
        if bool(getattr(self, "_force_close", False)) or bool(getattr(self, "_close_in_progress", False)):
            return True
    except Exception:
        pass
    try:
        app = QtWidgets.QApplication.instance()
    except Exception:
        app = None
    try:
        if app is not None and bool(getattr(app, "_exiting", False)):
            return True
    except Exception:
        pass
    return False

def _mark_user_close_command(self) -> None:
    try:
        self._last_user_close_command_ts = time.monotonic()
    except Exception:
        self._last_user_close_command_ts = 0.0

def _is_recent_user_close_command(self) -> bool:
    try:
        last_ts = float(getattr(self, "_last_user_close_command_ts", 0.0) or 0.0)
    except Exception:
        last_ts = 0.0
    if last_ts <= 0.0:
        return False
    try:
        ttl_ms = int(os.environ.get("BOT_USER_CLOSE_BYPASS_MS") or 1800)
    except Exception:
        ttl_ms = 1800
    ttl_ms = max(300, min(ttl_ms, 10000))
    try:
        return (time.monotonic() - last_ts) * 1000.0 <= ttl_ms
    except Exception:
        return False

def _restore_window_after_guard(self) -> None:
    def _restore_once():
        try:
            state = self.windowState()
        except Exception:
            state = QtCore.Qt.WindowState.WindowNoState
        try:
            visible = bool(self.isVisible())
        except Exception:
            visible = False
        try:
            minimized = bool(state & QtCore.Qt.WindowState.WindowMinimized)
        except Exception:
            minimized = False
        if minimized:
            try:
                if state & QtCore.Qt.WindowState.WindowMaximized:
                    self.showMaximized()
                else:
                    self.showNormal()
            except Exception:
                pass
        elif not visible:
            try:
                if state & QtCore.Qt.WindowState.WindowMaximized:
                    self.showMaximized()
                else:
                    self.show()
            except Exception:
                pass
        try:
            self.raise_()
            self.activateWindow()
        except Exception:
            pass

    _restore_once()
    try:
        QtCore.QTimer.singleShot(40, _restore_once)
        QtCore.QTimer.singleShot(140, _restore_once)
    except Exception:
        pass

def _active_close_protection_until(self) -> float:
    try:
        now = time.monotonic()
    except Exception:
        now = 0.0

    try:
        tv_active = bool(getattr(self, "_tv_close_guard_active", False))
    except Exception:
        tv_active = False
    try:
        tv_until = float(getattr(self, "_tv_close_guard_until", 0.0) or 0.0)
    except Exception:
        tv_until = 0.0
    if tv_active and tv_until and now >= tv_until:
        try:
            self._tv_close_guard_active = False
        except Exception:
            pass
        tv_active = False
        tv_until = 0.0

    try:
        we_active = bool(getattr(self, "_webengine_close_guard_active", False))
    except Exception:
        we_active = False
    try:
        we_until = float(getattr(self, "_webengine_close_guard_until", 0.0) or 0.0)
    except Exception:
        we_until = 0.0
    if we_active and we_until and now >= we_until:
        try:
            self._webengine_close_guard_active = False
        except Exception:
            pass
        we_active = False
        we_until = 0.0

    active_until = 0.0
    if tv_active and tv_until > active_until:
        active_until = tv_until
    if we_active and we_until > active_until:
        active_until = we_until
    return active_until

def _should_block_programmatic_hide(self) -> bool:
    if _allow_guard_bypass(self):
        return False
    try:
        now = time.monotonic()
    except Exception:
        now = 0.0
    guard_until = _active_close_protection_until(self)
    return bool(guard_until and now < guard_until and not _is_recent_user_close_command(self))

def setVisible(self, visible):  # noqa: N802, ANN001
    make_visible = bool(visible)
    if not make_visible and _should_block_programmatic_hide(self):
        try:
            logger = getattr(self, "_chart_debug_log", None)
            if callable(logger):
                logger("window_event setVisible_blocked visible=0 reason=webengine_guard")
        except Exception:
            pass
        _restore_window_after_guard(self)
        return
    try:
        super(MainWindow, self).setVisible(visible)
    except Exception:
        pass

def hide(self):  # noqa: ANN001
    if _should_block_programmatic_hide(self):
        try:
            logger = getattr(self, "_chart_debug_log", None)
            if callable(logger):
                logger("window_event hide_blocked reason=webengine_guard")
        except Exception:
            pass
        _restore_window_after_guard(self)
        return
    try:
        super(MainWindow, self).hide()
    except Exception:
        pass

def nativeEvent(self, eventType, message):  # noqa: N802, ANN001
    if sys.platform == "win32":
        # Native MSG parsing is opt-in because ctypes pointer casts here can
        # be unstable on some Windows/PyQt builds and break startup.
        detect_flag = str(os.environ.get("BOT_ENABLE_NATIVE_CLOSE_DETECT", "")).strip().lower()
        if detect_flag not in {"1", "true", "yes", "on"}:
            try:
                return super(MainWindow, self).nativeEvent(eventType, message)
            except Exception:
                return False, 0
        try:
            et = ""
            try:
                et = bytes(eventType).decode("utf-8", "ignore").strip().lower()
            except Exception:
                try:
                    et = str(eventType).strip().lower()
                except Exception:
                    et = ""
            # Only inspect native MSG payload for event types that are documented to carry MSG.
            if et not in {"windows_generic_msg", "windows_dispatcher_msg"}:
                raise RuntimeError("unsupported native event type")
            import ctypes
            import ctypes.wintypes as wintypes
            WM_SYSCOMMAND = 0x0112
            SC_CLOSE = 0xF060
            msg_ptr = int(message)
            if msg_ptr and msg_ptr > 0x10000:
                msg_obj = ctypes.cast(msg_ptr, ctypes.POINTER(wintypes.MSG)).contents
                if int(msg_obj.message) == WM_SYSCOMMAND:
                    cmd = int(msg_obj.wParam) & 0xFFF0
                    if cmd == SC_CLOSE:
                        _mark_user_close_command(self)
        except Exception:
            pass
    try:
        return super(MainWindow, self).nativeEvent(eventType, message)
    except Exception:
        return False, 0

def closeEvent(self, event):
    try:
        _log_window_event(self, "closeEvent", event=event)
    except Exception:
        pass
    close_guard = getattr(self, "_close_in_progress", False)
    if close_guard:
        event.ignore()
        return
    if getattr(self, "_force_close", False):
        self._force_close = False
        try:
            StrategyEngine.request_shutdown()
        except Exception:
            pass
        try:
            _teardown_positions_thread(self)
        except Exception:
            pass
        try:
            self._mark_session_inactive()
        except Exception:
            pass
        try:
            super(MainWindow, self).closeEvent(event)
        except Exception:
            try:
                event.accept()
            except Exception:
                pass
        try:
            app = QtWidgets.QApplication.instance()
            if app is not None:
                setattr(app, "_exiting", True)
                app.quit()
        except Exception:
            pass
        return
    if not _allow_guard_bypass(self):
        try:
            now = time.monotonic()
        except Exception:
            now = 0.0
        guard_until = _active_close_protection_until(self)
        if guard_until and now < guard_until:
            try:
                is_spontaneous_close = bool(event is not None and event.spontaneous())
            except Exception:
                is_spontaneous_close = False
            if is_spontaneous_close or _is_recent_user_close_command(self):
                try:
                    self._last_user_close_command_ts = 0.0
                except Exception:
                    pass
                try:
                    self._webengine_close_guard_active = False
                    self._tv_close_guard_active = False
                except Exception:
                    pass
            else:
                event.ignore()
                _restore_window_after_guard(self)
                return

    try:
        StrategyEngine.request_shutdown()
    except Exception:
        pass
    try:
        app = QtWidgets.QApplication.instance()
        if app is not None:
            setattr(app, "_exiting", True)
    except Exception:
        pass

    close_on_exit_enabled = bool(getattr(self, "cb_close_on_exit", None) and self.cb_close_on_exit.isChecked())
    should_wait = False
    if close_on_exit_enabled:
        # Always route through the close-on-exit sequence so loops stop and a popup is shown.
        event.ignore()
        self._begin_close_on_exit_sequence()
        return

    try:
        self.stop_strategy_async(close_positions=close_on_exit_enabled, blocking=True)
    except Exception:
        pass
    try:
        _teardown_positions_thread(self)
    except Exception:
        pass
    try:
        self._mark_session_inactive()
    except Exception:
        pass
    try:
        super(MainWindow, self).closeEvent(event)
    except Exception:
        try:
            event.accept()
        except Exception:
            pass
    try:
        if event.isAccepted():
            app = QtWidgets.QApplication.instance()
            if app is not None:
                app.quit()
    except Exception:
        pass

def hideEvent(self, event):  # noqa: N802
    try:
        _log_window_event(self, "hideEvent", event=event)
    except Exception:
        pass
    if not _allow_guard_bypass(self):
        try:
            now = time.monotonic()
        except Exception:
            now = 0.0
        guard_until = _active_close_protection_until(self)
        if guard_until and now < guard_until:
            if not _is_recent_user_close_command(self):
                try:
                    event.ignore()
                except Exception:
                    pass
                _restore_window_after_guard(self)
                return
    try:
        super(MainWindow, self).hideEvent(event)
    except Exception:
        try:
            event.accept()
        except Exception:
            pass

try:
    MainWindow._teardown_positions_thread = _teardown_positions_thread
    MainWindow.closeEvent = closeEvent
    MainWindow.hideEvent = hideEvent
    MainWindow.setVisible = setVisible
    MainWindow.hide = hide
    try:
        if str(os.environ.get("BOT_ENABLE_NATIVE_CLOSE_DETECT", "")).strip().lower() in {"1", "true", "yes", "on"}:
            MainWindow.nativeEvent = nativeEvent
    except Exception:
        pass
except Exception:
    pass


def _gui_apply_theme(self, name: str):
    theme = (name or '').strip().lower()
    base_stylesheet = self.DARK_THEME if theme.startswith('dark') or theme in {"blue", "yellow", "green", "red"} else self.LIGHT_THEME

    accents = {
        "blue": "#2563eb",
        "yellow": "#fbbf24",
        "green": "#22c55e",
        "red": "#ef4444",
    }
    accent = accents.get(theme)
    accent_styles = ""
    if accent:
        try:
            color = QtGui.QColor(accent)
            hover = color.lighter(115).name()
            pressed = color.darker(120).name()
            accent_text = "#0c0f16" if color.lightness() >= 160 else "#ffffff"
            outline = color.darker(170).name()
            accent_styles = f"""
            /* Buttons */
            QPushButton {{
                background-color: {accent};
                border: 1px solid {accent};
                color: #ffffff;
            }}
            QPushButton:hover {{
                background-color: {hover};
                border-color: {hover};
            }}
            QPushButton:pressed {{
                background-color: {pressed};
                border-color: {pressed};
            }}
            /* Tool buttons */
            QToolButton {{
                background-color: {accent};
                border: 1px solid {accent};
                color: #ffffff;
            }}
            QToolButton:hover {{
                background-color: {hover};
                border-color: {hover};
            }}
            QToolButton:pressed {{
                background-color: {pressed};
                border-color: {pressed};
            }}
            /* Inputs */
            QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit, QTextEdit, QPlainTextEdit {{
                selection-background-color: {accent};
                selection-color: {accent_text};
            }}
            QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:hover {{
                border: 1px solid {accent};
            }}
            QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {{
                border: 1px solid {accent};
                outline: none;
            }}
            QComboBox::drop-down {{
                border-left: 1px solid {accent};
                background-color: {accent};
                width: 18px;
            }}
            /* Checkboxes / radios */
            QCheckBox::indicator:checked {{
                background-color: {accent};
                border-color: {accent};
                image: url(:/qt-project.org/styles/commonstyle/images/checkboxchecked.png);
            }}
            QCheckBox::indicator:hover {{
                border-color: {accent};
            }}
            QRadioButton::indicator:checked {{
                background-color: {accent};
                border: 1px solid {accent};
            }}
            QRadioButton::indicator:hover {{
                border: 1px solid {accent};
            }}
            /* Tabs / group boxes */
            QTabBar::tab:selected {{
                background-color: {accent};
                border: 1px solid {accent};
                color: {accent_text};
            }}
            QTabBar::tab:hover {{
                border: 1px solid {accent};
            }}
            QTabWidget::pane {{
                border: 1px solid {outline};
            }}
            QGroupBox::title {{
                color: {accent};
            }}
            QGroupBox {{
                border: 1px solid {outline};
            }}
            /* Selection / tables */
            QAbstractItemView::item:selected {{
                background-color: {accent};
                color: {accent_text};
            }}
            QAbstractItemView::item:hover {{
                background-color: {hover};
                color: {accent_text};
            }}
            QHeaderView::section {{
                border: 1px solid {outline};
            }}
            QProgressBar::chunk {{
                background-color: {accent};
            }}
            /* Sliders / scrollbars */
            QSlider::handle:horizontal, QSlider::handle:vertical {{
                background: {accent};
                border: 1px solid {outline};
            }}
            QSlider::sub-page:horizontal, QSlider::sub-page:vertical {{
                background: {accent};
            }}
            QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
                background: {accent};
                border: 1px solid {outline};
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: {accent};
                color: {accent_text};
            }}
            """
        except Exception:
            accent_styles = ""

    # Apply only stylesheet-based accents to avoid globally recoloring controls.
    self.setStyleSheet(base_stylesheet + accent_styles)
    try:
        self.config['theme'] = name.title() if name else "Dark"
    except Exception:
        pass

try:
    MainWindow.apply_theme = _gui_apply_theme
except Exception:
    pass

try:
    MainWindow._update_position_history = _mw_update_position_history
    MainWindow._render_positions_table = _mw_render_positions_table
    MainWindow._update_positions_pnl_summary = _update_positions_pnl_summary
    MainWindow._snapshot_closed_position = _mw_snapshot_closed_position
    MainWindow._make_close_btn = _mw_make_close_btn
    MainWindow._close_position_single = _mw_close_position_single
    MainWindow._clear_positions_selected = _mw_clear_positions_selected
    MainWindow._clear_positions_all = _mw_clear_positions_all
except Exception:
    pass

try:
    MainWindow._on_positions_ready = _gui_on_positions_ready
except Exception:
    pass


def _gui_setup_log_buffer(self):
    from collections import deque
    self._log_buf = deque(maxlen=8000)
    self._log_timer = QtCore.QTimer(self)
    self._log_timer.setInterval(200)
    self._log_timer.timeout.connect(self._flush_log_buffer)
    self._log_timer.start()

def _gui_buffer_log(self, msg: str):
    try:
        self._log_buf.append(msg)
    except Exception:
        pass

def _mw_reconfigure_positions_worker(self, symbols=None):
    try:
        worker = getattr(self, '_pos_worker', None)
        if worker is None:
            return

        selected_symbols: list[str] = []
        try:
            symbol_list = getattr(self, "symbol_list", None)
            if symbol_list is not None:
                for idx in range(symbol_list.count()):
                    item = symbol_list.item(idx)
                    if item is None or not item.isSelected():
                        continue
                    text = str(item.text() or "").strip().upper()
                    if text:
                        selected_symbols.append(text)
        except Exception:
            selected_symbols = []

        extra_symbols: list[str] = []
        if symbols:
            for sym in symbols:
                try:
                    text = str(sym or "").strip().upper()
                except Exception:
                    text = ""
                if text:
                    extra_symbols.append(text)

        def _dedupe(seq: list[str]) -> list[str]:
            return list(dict.fromkeys(seq))

        selected_symbols = _dedupe(selected_symbols)
        extra_symbols = _dedupe(extra_symbols)

        if selected_symbols:
            target_symbols = _dedupe(selected_symbols + extra_symbols)
        else:
            # No explicit selection: never narrow the worker just because a caller passed hint symbols.
            target_symbols = None

        worker.configure(
            api_key=self.api_key_edit.text().strip(),
            api_secret=self.api_secret_edit.text().strip(),
            mode=self.mode_combo.currentText(),
            account_type=self.account_combo.currentText(),
            symbols=target_symbols or None,
            connector_backend=self._runtime_connector_backend(suppress_refresh=True),
        )
        setattr(self, "_pos_symbol_filter", target_symbols)
    except Exception:
        pass


def _mw_collect_strategy_intervals(self, symbol: str, side_key: str):
    intervals = set()
    try:
        engines = getattr(self, 'strategy_engines', {}) or {}
        sym_upper = (symbol or '').upper()
        side_key_upper = (side_key or '').upper()
        for eng in engines.values():
            cfg = getattr(eng, 'config', {}) or {}
            cfg_sym = str(cfg.get('symbol') or '').upper()
            if not cfg_sym or cfg_sym != sym_upper:
                continue
            interval = str(cfg.get('interval') or '').strip()
            if not interval:
                continue
            side_pref = str(cfg.get('side') or 'BOTH').upper()
            if side_pref in ('BUY', 'LONG'):
                allowed = {'L'}
            elif side_pref in ('SELL', 'SHORT'):
                allowed = {'S'}
            else:
                allowed = {'L', 'S'}
            if side_key_upper in allowed:
                intervals.add(interval)
    except Exception:
        pass
    return intervals


def _mw_parse_any_datetime(self, value):
    from datetime import datetime as _dt
    if value is None:
        return None
    if isinstance(value, _dt):
        try:
            return value.astimezone() if value.tzinfo else value
        except Exception:
            return value
    if isinstance(value, (int, float)):
        try:
            raw = float(value)
            if raw > 1e12:
                raw /= 1000.0
            return _dt.fromtimestamp(raw, tz=timezone.utc).astimezone()
        except Exception:
            pass
    try:
        s = str(value).strip()
    except Exception:
        return None
    if not s:
        return None
    s_norm = s.replace('/', '-')
    patterns = (
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%dT%H:%M:%S.%f',
        '%Y-%m-%dT%H:%M:%S.%fZ',
        '%d-%m-%Y %H:%M:%S',
        '%d.%m.%Y %H:%M:%S',
    )
    for fmt in patterns:
        try:
            dt = _dt.strptime(s_norm, fmt)
            if fmt.endswith('Z'):
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone() if dt.tzinfo else dt
        except Exception:
            continue
    try:
        dt = _dt.fromisoformat(s_norm.replace('Z', '+00:00'))
        return dt.astimezone() if dt.tzinfo else dt
    except Exception:
        return None


def _mw_format_display_time(self, value):
    dt = _mw_parse_any_datetime(self, value)
    if dt is None:
        try:
            return str(value) if value not in (None, '') else '-'
        except Exception:
            return '-'
    try:
        if getattr(dt, 'tzinfo', None):
            dt = dt.astimezone()
    except Exception:
        pass
    return dt.strftime('%d.%m.%Y %H:%M:%S')


def _mw_interval_sort_key(label: str):
    try:
        lbl = (label or '').strip().lower()
        if not lbl:
            return (float('inf'), '')
        import re as _re
        match = _re.match(r'(\d+(?:\.\d+)?)([smhdw]?)', lbl)
        if not match:
            return (float('inf'), lbl)
        value = float(match.group(1))
        unit = match.group(2) or 'm'
        factor = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400, 'w': 604800}.get(unit, 60)
        return (value * factor, lbl)
    except Exception:
        return (float('inf'), str(label))


def _is_trigger_log_line(raw_text: str) -> bool:
    try:
        text = str(raw_text or "")
    except Exception:
        text = ""
    low = text.lower()
    if not low:
        return False
    trigger_tokens = (
        "signal=buy",
        "signal=sell",
        "-> buy",
        "-> sell",
        "'side': 'buy",
        "\"side\": \"buy",
        "'side': 'sell",
        "\"side\": \"sell",
        "liquidat",
        "triggered buy",
        "triggered sell",
    )
    if any(token in low for token in trigger_tokens):
        return True
    if "trade update" in low and (" buy" in low or " sell" in low):
        return True
    return False


def _gui_flush_log_buffer(self):
    try:
        if not hasattr(self, '_log_buf') or not self._log_buf:
            return
        lines = []
        for _ in range(300):
            if not self._log_buf:
                break
            lines.append(self._log_buf.popleft())
        if not lines:
            return
        from datetime import datetime as _dt
        import re as _re
        pat = _re.compile(r'^\[?(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]?\s*(.*)$')
        pat2 = _re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*(.*)$')
        formatted = []
        formatted_triggers = []
        for raw in lines:
            line = str(raw)
            match = pat.match(line)
            if match:
                iso_ts, rest = match.groups()
                body = rest.strip()
                nested = pat2.match(body)
                if nested:
                    body = nested.group(2).strip()
                try:
                    ts = _dt.strptime(iso_ts, '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y %H:%M:%S')
                except Exception:
                    ts = _dt.now().strftime('%d.%m.%Y %H:%M:%S')
                formatted.append(f"[{ts}] {body}" if body else f"[{ts}]")
            else:
                ts = _dt.now().strftime('%d.%m.%Y %H:%M:%S')
                formatted.append(f"[{ts}] {line}")
            if _is_trigger_log_line(line):
                formatted_triggers.append(formatted[-1])
        text = '\n'.join(formatted)
        try:
            self.log_edit.appendPlainText(text)
        except Exception:
            self.log_edit.append(text)
        self.log_edit.verticalScrollBar().setValue(self.log_edit.verticalScrollBar().maximum())
        if formatted_triggers:
            target = getattr(self, "log_triggers_edit", None)
            if target is not None:
                trigger_text = '\n'.join(formatted_triggers)
                try:
                    target.appendPlainText(trigger_text)
                except Exception:
                    try:
                        target.insertPlainText(trigger_text + "\n")
                    except Exception:
                        pass
                try:
                    target.verticalScrollBar().setValue(target.verticalScrollBar().maximum())
                except Exception:
                    pass
    except Exception:
        pass

try:
    MainWindow._collect_strategy_intervals = _mw_collect_strategy_intervals
except Exception:
    pass

try:
    MainWindow._parse_any_datetime = _mw_parse_any_datetime
    MainWindow._format_display_time = _mw_format_display_time
except Exception:
    pass


def _mw_refresh_waiting_positions_tab(self):
    table = getattr(self, "waiting_pos_table", None)
    if table is None:
        return
    history = getattr(self, "_waiting_positions_history", None)
    if not isinstance(history, list):
        history = []
        self._waiting_positions_history = history
    last_snapshot = getattr(self, "_waiting_positions_last_snapshot", None)
    if not isinstance(last_snapshot, dict):
        last_snapshot = {}
        self._waiting_positions_last_snapshot = last_snapshot
    history_max = getattr(self, "_waiting_positions_history_max", None)
    try:
        history_max = int(history_max)
    except Exception:
        history_max = 500
    if history_max <= 0:
        history_max = 500
    self._waiting_positions_history_max = history_max
    try:
        guard = getattr(self, "guard", None)
    except Exception:
        guard = None
    snapshot = []
    snapshot_ok = False
    if guard is not None and hasattr(guard, "snapshot_pending_attempts"):
        try:
            raw = guard.snapshot_pending_attempts() or []
            snapshot = [item for item in raw if isinstance(item, dict)]
            snapshot_ok = True
        except Exception:
            snapshot = []
            snapshot_ok = False
    current_entries = []
    current_keys = set()
    for item in snapshot:
        symbol = str(item.get("symbol") or "").upper() or "-"
        interval_raw = str(item.get("interval") or "").strip()
        interval = interval_raw.upper() if interval_raw else "-"
        side_raw = str(item.get("side") or "").upper()
        if side_raw in ("L", "LONG"):
            side = "BUY"
        elif side_raw in ("S", "SHORT"):
            side = "SELL"
        else:
            side = side_raw or "-"
        context = str(item.get("context") or "")
        try:
            age_val = float(item.get("age") or 0.0)
        except Exception:
            age_val = 0.0
        age_seconds = max(0, int(age_val))
        state = "Late" if age_val >= WAITING_POSITION_LATE_THRESHOLD else "Queued"
        key = (symbol, interval, side, context)
        current_entries.append(
            {
                "symbol": symbol,
                "interval": interval,
                "side": side,
                "context": context,
                "age": age_val,
                "age_seconds": age_seconds,
                "state": state,
                "key": key,
            }
        )
        current_keys.add(key)
    if snapshot_ok:
        ended_keys = set(last_snapshot.keys()) - current_keys
        if ended_keys:
            now = time.time()
            for key in ended_keys:
                ended_entry = last_snapshot.get(key)
                if not isinstance(ended_entry, dict):
                    continue
                ended_copy = dict(ended_entry)
                ended_copy["state"] = "Ended"
                ended_copy["ended_at"] = now
                history.append(ended_copy)
        if len(history) > history_max:
            history = history[-history_max:]
            self._waiting_positions_history = history
        self._waiting_positions_last_snapshot = {entry["key"]: entry for entry in current_entries}
    combined_entries = current_entries + history
    table.setSortingEnabled(False)
    table.setRowCount(len(combined_entries))
    if not combined_entries:
        table.clearContents()
        table.setSortingEnabled(True)
        return
    try:
        combined_entries.sort(
            key=lambda item: (
                1 if str(item.get("state") or "").lower() == "ended" else 0,
                -float(str(item.get("age") or 0.0)),
                str(item.get("symbol") or ""),
            )
        )
    except Exception:
        pass
    for row, item in enumerate(combined_entries):
        symbol = str(item.get("symbol") or "").upper() or "-"
        interval_raw = str(item.get("interval") or "").strip()
        interval = interval_raw.upper() if interval_raw else "-"
        side_raw = str(item.get("side") or "").upper()
        if side_raw in ("L", "LONG"):
            side = "BUY"
        elif side_raw in ("S", "SHORT"):
            side = "SELL"
        else:
            side = side_raw or "-"
        context = str(item.get("context") or "")
        try:
            age_val = float(item.get("age") or 0.0)
        except Exception:
            age_val = 0.0
        try:
            age_seconds = int(item.get("age_seconds"))
        except Exception:
            age_seconds = max(0, int(age_val))
        state = str(item.get("state") or "")
        if not state:
            state = "Late" if age_val >= WAITING_POSITION_LATE_THRESHOLD else "Queued"

        symbol_item = QtWidgets.QTableWidgetItem(symbol)
        symbol_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        table.setItem(row, 0, symbol_item)

        interval_item = QtWidgets.QTableWidgetItem(interval)
        interval_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        table.setItem(row, 1, interval_item)

        side_item = QtWidgets.QTableWidgetItem(side.title() if side not in ("-", "") else "-")
        side_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        table.setItem(row, 2, side_item)

        context_item = QtWidgets.QTableWidgetItem(context or "-")
        table.setItem(row, 3, context_item)

        state_item = QtWidgets.QTableWidgetItem(state)
        state_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        table.setItem(row, 4, state_item)

        age_item = _NumericItem(f"{age_seconds}", age_val)
        table.setItem(row, 5, age_item)
    table.setSortingEnabled(True)


try:
    MainWindow._setup_log_buffer = _gui_setup_log_buffer
    MainWindow._buffer_log = _gui_buffer_log
    MainWindow._flush_log_buffer = _gui_flush_log_buffer
    MainWindow._refresh_waiting_positions_tab = _mw_refresh_waiting_positions_tab
except Exception:
    pass

try:
    MainWindow._reconfigure_positions_worker = _mw_reconfigure_positions_worker
except Exception:
    pass


def _mw_log(self, msg: str):
    try:
        self.log_signal.emit(str(msg))
    except Exception:
        pass

def _mw_trade_mux(self, evt: dict):
    try:
        guard = getattr(self, 'guard', None)
        hook = getattr(guard, 'trade_hook', None)
        if callable(hook):
            hook(evt)
    except Exception:
        pass
    try:
        self.trade_signal.emit(evt)
    except Exception:
        pass


def _mw_on_trade_signal(self, order_info: dict):
    try:
        connector_name = self._connector_label_text(self._runtime_connector_backend(suppress_refresh=True))
    except Exception:
        connector_name = "Unknown"
    info_with_connector = dict(order_info or {})
    info_with_connector.setdefault("connector", connector_name)
    self.log(f"TRADE UPDATE [{connector_name}]: {info_with_connector}")
    sym = order_info.get("symbol")
    interval = order_info.get("interval")
    side = order_info.get("side")
    position_side = order_info.get("position_side") or side
    event_type = str(order_info.get("event") or "").lower()
    status = str(order_info.get("status") or "").lower()
    ok_flag = order_info.get("ok")
    side_for_key = position_side or side
    side_key = "L" if str(side_for_key).upper() in ("BUY", "LONG") else "S"
    sym_upper = str(sym or "").strip().upper()

    alloc_map = getattr(self, "_entry_allocations", None)
    if alloc_map is None:
        self._entry_allocations = {}
        alloc_map = self._entry_allocations
    pending_close = getattr(self, "_pending_close_times", None)
    if pending_close is None:
        self._pending_close_times = {}
        pending_close = self._pending_close_times

    def _norm_interval(value):
        try:
            canon = self._canonicalize_interval(value)
        except Exception:
            canon = None
        if canon:
            return canon
        if isinstance(value, str):
            lowered = value.strip().lower()
            return lowered or None
        return None

    def _sync_open_position_snapshot(
        symbol_key: str,
        side_key_local: str,
        alloc_entries: list | None,
        trade_snapshot: dict | None,
        interval_label: str | None,
        normalized_interval: str | None,
        open_time_fmt: str | None,
    ) -> None:
        if not symbol_key or side_key_local not in ("L", "S"):
            return
        open_records = getattr(self, "_open_position_records", None)
        if not isinstance(open_records, dict):
            open_records = {}
            self._open_position_records = open_records
        record = open_records.get((symbol_key, side_key_local))
        if not isinstance(record, dict):
            record = {
                "symbol": symbol_key,
                "side_key": side_key_local,
                "entry_tf": interval_label or normalized_interval or "-",
                "open_time": open_time_fmt or (trade_snapshot.get("open_time") if isinstance(trade_snapshot, dict) else "-"),
                "close_time": "-",
                "status": "Active",
                "data": {},
                "indicators": [],
                "stop_loss_enabled": False,
            }
            open_records[(symbol_key, side_key_local)] = record
        record["status"] = "Active"
        if interval_label:
            record["entry_tf"] = interval_label
        elif normalized_interval and not record.get("entry_tf"):
            record["entry_tf"] = normalized_interval
        if open_time_fmt:
            record["open_time"] = open_time_fmt
        record["allocations"] = copy.deepcopy(alloc_entries or [])
        base_data = dict(record.get("data") or {})
        base_data.setdefault("symbol", symbol_key)
        base_data.setdefault("side_key", side_key_local)
        if interval_label:
            base_data.setdefault("interval_display", interval_label)
        if normalized_interval:
            base_data.setdefault("interval", normalized_interval)
        if isinstance(trade_snapshot, dict):
            trigger_desc = trade_snapshot.get("trigger_desc")
            if trigger_desc:
                base_data["trigger_desc"] = trigger_desc
            normalized_triggers = _resolve_trigger_indicators(
                trade_snapshot.get("trigger_indicators"),
                trigger_desc,
            )
            if normalized_triggers:
                base_data["trigger_indicators"] = normalized_triggers
            normalized_actions = _normalize_trigger_actions_map(trade_snapshot.get("trigger_actions"))
            if normalized_actions:
                base_data["trigger_actions"] = normalized_actions
            value_mappings = (
                ("qty", "qty"),
                ("margin_usdt", "margin_usdt"),
                ("pnl_value", "pnl_value"),
                ("entry_price", "entry_price"),
                ("leverage", "leverage"),
                ("notional", "size_usdt"),
                ("size_usdt", "size_usdt"),
            )
            for src_key, dest_key in value_mappings:
                value = trade_snapshot.get(src_key)
                if value is None or value == "":
                    continue
                if isinstance(value, str):
                    try:
                        value_num = float(value)
                    except Exception:
                        value_num = value
                else:
                    value_num = value
                if dest_key == "leverage":
                    try:
                        value_num = int(value_num)
                    except Exception:
                        pass
                if dest_key not in base_data or base_data.get(dest_key) in (None, "", 0):
                    base_data[dest_key] = value_num
        record["data"] = base_data

    if event_type == "close_interval":
        try:
            if hasattr(self, "_track_interval_close"):
                self._track_interval_close(sym, side_key, interval)
        except Exception:
            pass
        norm_iv = _norm_interval(interval)
        closed_snapshots: list[dict] = []
        entries = alloc_map.get((sym_upper, side_key), [])
        if isinstance(entries, dict):
            entries = list(entries.values())
        survivors: list[dict] = []
        if isinstance(entries, list):
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                entry_iv = _norm_interval(entry.get("interval") or entry.get("interval_display"))
                if norm_iv is None or entry_iv == norm_iv:
                    entry_snapshot = copy.deepcopy(entry)
                    close_time_val = order_info.get("time")
                    if close_time_val:
                        dt_obj = self._parse_any_datetime(close_time_val)
                        entry_snapshot["close_time"] = self._format_display_time(dt_obj) if dt_obj else close_time_val
                    elif not entry_snapshot.get("close_time"):
                        entry_snapshot["close_time"] = entry.get("close_time")
                    entry_snapshot["status"] = "Closed"
                    closed_snapshots.append(entry_snapshot)
                    continue
                survivors.append(entry)
        if survivors:
            alloc_map[(sym_upper, side_key)] = survivors
            entries = survivors
        else:
            alloc_map.pop((sym_upper, side_key), None)
            entries = []
        
        # Persist allocation data after close
        try:
            _mode = self.mode_combo.currentText() if hasattr(self, "mode_combo") else None
            _save_position_allocations(
                getattr(self, "_entry_allocations", {}),
                getattr(self, "_open_position_records", {}),
                mode=_mode,
            )
        except Exception:
            pass
        
        if sym_upper:
            from datetime import datetime as _dt
            close_time_val = order_info.get("time")
            dt_obj = self._parse_any_datetime(close_time_val)
            if dt_obj is None:
                dt_obj = _dt.now().astimezone()
            close_time_fmt = self._format_display_time(dt_obj)
            if close_time_val:
                pending_close[(sym_upper, side_key)] = close_time_fmt
            alloc_entries_snapshot = []
            if closed_snapshots:
                alloc_entries_snapshot = closed_snapshots
                for entry_snap in alloc_entries_snapshot:
                    if not entry_snap.get("close_time"):
                        entry_snap["close_time"] = close_time_fmt
            elif isinstance(entries, list):
                for entry in entries:
                    if isinstance(entry, dict):
                        entry_snap = copy.deepcopy(entry)
                        if not entry_snap.get("close_time"):
                            entry_snap["close_time"] = close_time_fmt
                        alloc_entries_snapshot.append(entry_snap)
            ledger_id = order_info.get("ledger_id")
            def _safe_float_event(value):
                try:
                    if value is None:
                        return None
                    if isinstance(value, str):
                        stripped = value.strip()
                        if not stripped:
                            return None
                        return float(stripped)
                    return float(value)
                except Exception:
                    return None

            qty_reported = _safe_float_event(order_info.get("qty") or order_info.get("executed_qty"))
            if qty_reported is not None:
                qty_reported = abs(qty_reported)
            close_price_reported = _safe_float_event(
                order_info.get("close_price") or order_info.get("avg_price") or order_info.get("price") or order_info.get("mark_price")
            )
            entry_price_reported = _safe_float_event(order_info.get("entry_price"))
            pnl_reported = _safe_float_event(order_info.get("pnl_value"))
            margin_reported = _safe_float_event(order_info.get("margin_usdt"))
            roi_reported = _safe_float_event(order_info.get("roi_percent"))
            leverage_reported = None
            lev_tmp = _safe_float_event(order_info.get("leverage"))
            if lev_tmp is not None and lev_tmp > 0:
                try:
                    leverage_reported = int(round(lev_tmp))
                except Exception:
                    leverage_reported = None
            processed = getattr(self, "_processed_close_events", None)
            if processed is None:
                processed = set()
                self._processed_close_events = processed
            unique_key = order_info.get("event_id")
            if not unique_key:
                identifier = ledger_id or sym_upper or ""
                qty_token = f"{qty_reported:.8f}" if qty_reported is not None else "0"
                unique_key = f"{identifier}|{close_time_fmt}|{qty_token}|{side_key}"
            if unique_key in processed:
                return
            processed.add(unique_key)
            open_records = getattr(self, "_open_position_records", {}) or {}
            base_record = copy.deepcopy(open_records.get((sym_upper, side_key)))
            if not base_record:
                base_record = {
                    "symbol": sym_upper,
                    "side_key": side_key,
                    "entry_tf": "-",
                    "open_time": "-",
                    "close_time": close_time_fmt,
                    "status": "Closed",
                    "data": {},
                    "indicators": [],
                    "stop_loss_enabled": False,
                }
            else:
                base_record["status"] = "Closed"
                base_record["close_time"] = close_time_fmt
            if ledger_id:
                base_record["ledger_id"] = ledger_id
            base_data_snap = dict(base_record.get("data") or {})
            if alloc_entries_snapshot:
                qty_total = 0.0
                margin_total = 0.0
                pnl_total = 0.0
                pnl_has_value = False
                notional_total = 0.0
                trigger_list = []
                base_qty_curr = float(base_data_snap.get("qty") or 0.0)
                base_margin_curr = float(base_data_snap.get("margin_usdt") or 0.0)
                base_pnl_curr = float(base_data_snap.get("pnl_value") or 0.0)
                base_notional_curr = float(base_data_snap.get("size_usdt") or 0.0)
                alloc_count = len(alloc_entries_snapshot)
                for entry_snap in alloc_entries_snapshot:
                    try:
                        qty_val = abs(float(entry_snap.get("qty") or 0.0))
                    except Exception:
                        qty_val = 0.0
                    qty_total += qty_val
                    margin_val = entry_snap.get("margin_usdt")
                    if (margin_val is None or float(margin_val or 0.0) == 0.0) and base_margin_curr > 0:
                        share = (qty_val / base_qty_curr) if base_qty_curr > 0 else (1.0 / alloc_count if alloc_count else 0.0)
                        entry_snap["margin_usdt"] = base_margin_curr * share if share else base_margin_curr
                    try:
                        margin_total += max(float(entry_snap.get("margin_usdt") or 0.0), 0.0)
                    except Exception:
                        pass
                    pnl_val = entry_snap.get("pnl_value")
                    if pnl_val is not None:
                        try:
                            pnl_total += float(pnl_val)
                            pnl_has_value = True
                        except Exception:
                            pass
                    elif base_pnl_curr:
                        share = (qty_val / base_qty_curr) if base_qty_curr > 0 else (1.0 / alloc_count if alloc_count else 0.0)
                        approx_pnl = base_pnl_curr * share if share else base_pnl_curr
                        entry_snap["pnl_value"] = approx_pnl
                        pnl_total += approx_pnl
                        pnl_has_value = True
                    try:
                        notional_total += max(float(entry_snap.get("notional") or 0.0), 0.0)
                    except Exception:
                        pass
                    if entry_snap.get("notional") in (None, 0.0) and base_notional_curr > 0:
                        share = (qty_val / base_qty_curr) if base_qty_curr > 0 else (1.0 / alloc_count if alloc_count else 0.0)
                        entry_snap["notional"] = base_notional_curr * share if share else base_notional_curr
                    trig = entry_snap.get("trigger_indicators")
                    if isinstance(trig, (list, tuple, set)):
                        trigger_list.extend([str(t).strip() for t in trig if str(t).strip()])
                    if close_price_reported is not None and close_price_reported > 0:
                        entry_snap["close_price"] = close_price_reported
                    if entry_price_reported is not None and entry_price_reported > 0:
                        entry_snap.setdefault("entry_price", entry_price_reported)
                    if leverage_reported:
                        entry_snap["leverage"] = leverage_reported
                if qty_reported is not None and qty_reported > 0:
                    qty_total = qty_reported
                if margin_reported is not None and margin_reported > 0:
                    margin_total = margin_reported
                if pnl_reported is not None:
                    pnl_total = pnl_reported
                    pnl_has_value = True
                if qty_total > 0:
                    base_data_snap["qty"] = qty_total
                if margin_total > 0:
                    base_data_snap["margin_usdt"] = margin_total
                if pnl_has_value:
                    base_data_snap["pnl_value"] = pnl_total
                if notional_total > 0:
                    base_data_snap["size_usdt"] = notional_total
                if margin_total > 0 and pnl_has_value:
                    roi_percent = (pnl_total / margin_total) * 100.0 if margin_total else 0.0
                    base_data_snap["roi_percent"] = roi_percent
                    base_data_snap["pnl_roi"] = f"{pnl_total:+.2f} USDT ({roi_percent:+.2f}%)"
                if (
                    pnl_reported is not None
                    and roi_reported is not None
                    and margin_reported is not None
                    and margin_reported > 0
                ):
                    base_data_snap["roi_percent"] = roi_reported
                    base_data_snap["pnl_roi"] = f"{pnl_reported:+.2f} USDT ({roi_reported:+.2f}%)"
                if trigger_list:
                    trigger_list = list(dict.fromkeys(trigger_list))
                    base_record["indicators"] = trigger_list
                    base_data_snap["trigger_indicators"] = trigger_list
            if qty_reported is not None and qty_reported > 0:
                base_data_snap["qty"] = qty_reported
            if margin_reported is not None and margin_reported > 0:
                base_data_snap["margin_usdt"] = margin_reported
            if pnl_reported is not None:
                base_data_snap["pnl_value"] = pnl_reported
                if margin_reported and margin_reported > 0:
                    roi_val = roi_reported if roi_reported is not None else (pnl_reported / margin_reported) * 100.0
                    base_data_snap["roi_percent"] = roi_val
                    base_data_snap["pnl_roi"] = f"{pnl_reported:+.2f} USDT ({roi_val:+.2f}%)"
                else:
                    base_data_snap["pnl_roi"] = f"{pnl_reported:+.2f} USDT"
            if close_price_reported is not None and close_price_reported > 0:
                base_data_snap["close_price"] = close_price_reported
            if entry_price_reported is not None and entry_price_reported > 0:
                base_data_snap.setdefault("entry_price", entry_price_reported)
            if leverage_reported:
                base_data_snap["leverage"] = leverage_reported
            base_record["data"] = base_data_snap
            base_record["allocations"] = alloc_entries_snapshot
            try:
                closed_records = getattr(self, "_closed_position_records", [])
                if ledger_id:
                    replaced = False
                    for idx, rec in enumerate(closed_records):
                        if isinstance(rec, dict) and rec.get("ledger_id") == ledger_id:
                            closed_records[idx] = base_record
                            replaced = True
                            break
                    if not replaced:
                        closed_records.insert(0, base_record)
                else:
                    closed_records.insert(0, base_record)
                self._closed_position_records = closed_records
            except Exception:
                pass
            try:
                registry = getattr(self, "_closed_trade_registry", None)
                if registry is None:
                    registry = {}
                    self._closed_trade_registry = registry
                registry_key = ledger_id or unique_key
                if registry_key:
                    registry[registry_key] = {
                        "pnl_value": _safe_float_event(base_data_snap.get("pnl_value")),
                        "margin_usdt": _safe_float_event(base_data_snap.get("margin_usdt")),
                        "roi_percent": _safe_float_event(base_data_snap.get("roi_percent")),
                    }
                    if len(registry) > MAX_CLOSED_HISTORY:
                        excess = len(registry) - MAX_CLOSED_HISTORY
                        if excess > 0:
                            for old_key in list(registry.keys())[:excess]:
                                registry.pop(old_key, None)
                try:
                    self._update_global_pnl_display(*self._compute_global_pnl_totals())
                except Exception:
                    pass
            except Exception:
                pass
        try:
            pending_close.pop((sym_upper, side_key), None)
        except Exception:
            pass
        if sym:
            self.traded_symbols.add(sym)
        if sym_upper:
            try:
                getattr(self, "_open_position_records", {}).pop((sym_upper, side_key), None)
            except Exception:
                pass
            try:
                getattr(self, "_position_missing_counts", {}).pop((sym_upper, side_key), None)
            except Exception:
                pass
        try:
            guard_obj = getattr(self, "guard", None)
            if guard_obj and hasattr(guard_obj, "mark_closed") and sym_upper:
                side_norm = "BUY" if side_key == "L" else "SELL"
                guard_obj.mark_closed(sym_upper, interval, side_norm)
        except Exception:
            pass
        self.update_balance_label()
        self.refresh_positions(symbols=[sym] if sym else None)
        return

    is_success = (status != "error") and (ok_flag is None or ok_flag is True)
    if sym and interval and side_for_key:
        side_key_local = "L" if str(side_for_key).upper() in ("BUY", "LONG") else "S"
        if is_success and status not in {"error", "failed"}:
            registry = getattr(self, "_processed_open_events", None)
            if not isinstance(registry, dict):
                from collections import deque
                registry = {"order": deque(), "set": set()}
                self._processed_open_events = registry
            queue = registry.setdefault("order", None)
            if queue is None:
                from collections import deque
                queue = registry["order"] = deque()
            registry_set = registry.setdefault("set", set())
            now_ts = time.time()
            # prune stale entries (>10 minutes) or oversize cache
            while queue and ((now_ts - queue[0][1]) > 600.0 or len(queue) > 400):
                old_key, _ = queue.popleft()
                registry_set.discard(old_key)
            qty_token = ""
            qty_source = order_info.get("executed_qty")
            if qty_source is None:
                qty_source = order_info.get("qty")
            if qty_source is not None:
                try:
                    qty_token = f"{abs(float(qty_source)):.8f}"
                except Exception:
                    qty_token = str(qty_source)
            fills_meta = order_info.get("fills_meta") or {}
            order_id_token = fills_meta.get("order_id") or order_info.get("order_id") or ""
            if order_id_token is None:
                order_id_token = ""
            else:
                order_id_token = str(order_id_token)
            client_order_token = order_info.get("client_order_id") or order_info.get("clientOrderId") or ""
            if client_order_token is None:
                client_order_token = ""
            else:
                client_order_token = str(client_order_token)
            interval_token = _norm_interval(interval) or str(interval)
            status_token = str(order_info.get("status") or "").lower()
            time_token = str(order_info.get("time") or "")
            unique_parts = [
                sym_upper,
                side_key_local,
                interval_token,
                str(order_id_token),
                qty_token,
                status_token,
            ]
            if not order_id_token:
                unique_parts.append(time_token)
            unique_key = "|".join(unique_parts)
            if unique_key and unique_key in registry_set:
                return
            if unique_key:
                registry_set.add(unique_key)
                queue.append((unique_key, now_ts))
        # ignore opens while engines are stopping
        if getattr(self, "_is_stopping_engines", False) and status.lower() not in {"closed", "error"}:
            is_success = False
        if is_success:
            tstr = order_info.get('time')
            if not tstr:
                from datetime import datetime
                tstr = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            try:
                if hasattr(self, "_track_interval_open"):
                    self._track_interval_open(sym, side_key_local, interval, tstr)
            except Exception:
                pass

            norm_iv = _norm_interval(interval) or "-"
            try:
                qty_val = abs(float(order_info.get("executed_qty") or order_info.get("qty") or 0.0))
            except Exception:
                qty_val = 0.0
            try:
                price_val = float(order_info.get("avg_price") or order_info.get("price") or 0.0)
            except Exception:
                price_val = 0.0
            try:
                leverage_val = int(float(order_info.get("leverage") or 0.0))
            except Exception:
                leverage_val = 0
            if leverage_val <= 0 and getattr(self, "leverage_spin", None):
                try:
                    leverage_val = int(self.leverage_spin.value())
                except Exception:
                    leverage_val = 0
            entry_price_val = price_val if price_val > 0 else float(order_info.get("price") or 0.0)
            if entry_price_val <= 0:
                entry_price_val = price_val
            if entry_price_val <= 0:
                try:
                    entry_price_val = float(order_info.get("mark_price") or 0.0)
                except Exception:
                    entry_price_val = 0.0
            notional_val = entry_price_val * qty_val if entry_price_val > 0 and qty_val > 0 else 0.0
            if leverage_val > 0 and notional_val > 0:
                margin_val = notional_val / leverage_val
            else:
                margin_val = notional_val
            open_time_val = order_info.get("time") or tstr
            if open_time_val:
                dt_obj = self._parse_any_datetime(open_time_val)
                open_time_fmt = self._format_display_time(dt_obj) if dt_obj else open_time_val
            else:
                open_time_fmt = None
            trigger_inds = _resolve_trigger_indicators(order_info.get("trigger_indicators"), order_info.get("trigger_desc"))
            trigger_actions = _normalize_trigger_actions_map(order_info.get("trigger_actions"))
            trade_entry = {
                "interval": norm_iv,
                "interval_display": interval,
                "qty": qty_val,
                "entry_price": entry_price_val if entry_price_val > 0 else None,
                "leverage": leverage_val if leverage_val > 0 else None,
                "margin_usdt": margin_val,
                "margin_balance": margin_val,
                "notional": notional_val,
                "symbol": sym_upper,
                "side_key": side_key_local,
                "open_time": open_time_fmt,
                "status": "Active",
                "pnl_value": None,
                "trigger_indicators": list(trigger_inds) if trigger_inds else [],
                "trigger_desc": order_info.get("trigger_desc"),
                "trigger_actions": trigger_actions,
            }
            if order_id_token:
                trade_entry["order_id"] = order_id_token
            if client_order_token:
                trade_entry["client_order_id"] = client_order_token
            order_identifier = client_order_token or order_id_token
            alloc_list = alloc_map.get((sym_upper, side_key_local))
            if isinstance(alloc_list, dict):
                alloc_list = list(alloc_list.values())
            if not isinstance(alloc_list, list):
                alloc_list = []
            existing_entry = None
            if alloc_list:
                for entry in alloc_list:
                    if not isinstance(entry, dict):
                        continue
                    if client_order_token and entry.get("client_order_id") == client_order_token:
                        existing_entry = entry
                        break
                    if order_id_token and str(entry.get("order_id") or "") == order_id_token:
                        existing_entry = entry
                        break
                    if order_identifier and entry.get("trade_id") == order_identifier:
                        existing_entry = entry
                        break
                    if (
                        not order_identifier
                        and entry.get("interval") == norm_iv
                        and list(entry.get("trigger_indicators") or []) == list(trade_entry.get("trigger_indicators") or [])
                        and entry.get("open_time") == open_time_fmt
                    ):
                        existing_entry = entry
                        break
            if existing_entry:
                for key, value in trade_entry.items():
                    if value is None:
                        continue
                    if isinstance(value, (list, tuple, set)) and not value:
                        continue
                    if key == "trade_id" and not order_identifier:
                        continue
                    existing_entry[key] = value
                if order_identifier:
                    existing_entry["trade_id"] = order_identifier
            else:
                if not order_identifier:
                    try:
                        import time as _time
                        seq_len = len(alloc_list)
                        order_identifier = f"{sym_upper}-{side_key_local}-{int(_time.time()*1000)}-{seq_len + 1}"
                    except Exception:
                        order_identifier = f"{sym_upper}-{side_key_local}-{len(alloc_list) + 1}"
                trade_entry["trade_id"] = order_identifier
                alloc_list.append(trade_entry)
                existing_entry = trade_entry
            alloc_map[(sym_upper, side_key_local)] = alloc_list
            pending_close.pop((sym_upper, side_key_local), None)
            
            # Persist allocation data so it survives restarts
            try:
                _mode = self.mode_combo.currentText() if hasattr(self, "mode_combo") else None
                _save_position_allocations(
                    getattr(self, "_entry_allocations", {}),
                    getattr(self, "_open_position_records", {}),
                    mode=_mode,
                )
            except Exception:
                pass
            
            snapshot_entry = existing_entry or trade_entry
            _sync_open_position_snapshot(
                sym_upper,
                side_key_local,
                alloc_list,
                snapshot_entry,
                interval,
                norm_iv,
                open_time_fmt,
            )
        else:
            try:
                if hasattr(self, "_track_interval_close"):
                    self._track_interval_close(sym, side_key_local, interval)
            except Exception:
                pass
    if sym:
        self.traded_symbols.add(sym)
    self.update_balance_label()
    self.refresh_positions(symbols=[sym] if sym else None)


def _mw_pos_symbol_keys(self, symbol) -> tuple:
    sym_raw = str(symbol or "").strip()
    if not sym_raw:
        return tuple()
    sym_upper = sym_raw.upper()
    if sym_upper == sym_raw:
        return (sym_upper,)
    return tuple(dict.fromkeys([sym_upper, sym_raw]))


def _mw_pos_interval_keys(self, interval) -> tuple:
    iv_raw = str(interval or "").strip()
    if not iv_raw:
        return tuple()
    try:
        canon = self._canonicalize_interval(iv_raw)
    except Exception:
        canon = None
    keys = []
    if canon:
        keys.append(canon)
    if iv_raw and iv_raw != canon:
        keys.append(iv_raw)
    return tuple(dict.fromkeys(keys))


def _mw_pos_track_interval_open(self, symbol, side_key, interval, timestamp) -> None:
    if side_key not in ("L", "S"):
        return
    symbol_keys = _mw_pos_symbol_keys(self, symbol)
    if not symbol_keys:
        sym_raw = str(symbol or "").strip()
        if not sym_raw:
            return
        symbol_keys = _mw_pos_symbol_keys(self, sym_raw)
        if not symbol_keys:
            return
    primary_symbol = symbol_keys[0]
    interval_keys = _mw_pos_interval_keys(self, interval)
    primary_interval = interval_keys[0] if interval_keys else None
    entry_map = self._entry_intervals.setdefault(primary_symbol, {"L": set(), "S": set()})
    entry_map.setdefault("L", set())
    entry_map.setdefault("S", set())
    if primary_interval:
        entry_map[side_key].add(primary_interval)
    if timestamp:
        self._entry_times[(primary_symbol, side_key)] = timestamp
        if primary_interval:
            self._entry_times_by_iv[(primary_symbol, side_key, primary_interval)] = timestamp
    for alt_symbol in symbol_keys[1:]:
        if not alt_symbol:
            continue
        legacy = self._entry_intervals.pop(alt_symbol, None)
        if isinstance(legacy, dict):
            for leg_side, iv_set in legacy.items():
                if leg_side not in ("L", "S") or not isinstance(iv_set, set):
                    continue
                target = entry_map.setdefault(leg_side, set())
                for iv in iv_set:
                    normalized = _mw_pos_interval_keys(self, iv)
                    if normalized:
                        target.add(normalized[0])
        for side_variant in ("L", "S"):
            ts_val = self._entry_times.pop((alt_symbol, side_variant), None)
            if ts_val and (primary_symbol, side_variant) not in self._entry_times:
                self._entry_times[(primary_symbol, side_variant)] = ts_val
        for (sym_key, side_variant, iv_key), ts_val in list(self._entry_times_by_iv.items()):
            if sym_key == alt_symbol:
                normalized = _mw_pos_interval_keys(self, iv_key)
                self._entry_times_by_iv.pop((sym_key, side_variant, iv_key), None)
                if normalized:
                    self._entry_times_by_iv[(primary_symbol, side_variant, normalized[0])] = ts_val


def _mw_pos_track_interval_close(self, symbol, side_key, interval) -> None:
    if side_key not in ("L", "S"):
        return
    symbol_keys = _mw_pos_symbol_keys(self, symbol)
    if not symbol_keys:
        sym_raw = str(symbol or "").strip()
        candidates = [sym_raw.upper(), sym_raw]
        symbol_keys = tuple(dict.fromkeys([c for c in candidates if c]))
    interval_keys = _mw_pos_interval_keys(self, interval)
    if not interval_keys and interval:
        iv_raw = str(interval).strip()
        if iv_raw:
            interval_keys = (iv_raw,)
    for sym_key in symbol_keys:
        if not sym_key:
            continue
        side_map = self._entry_intervals.get(sym_key)
        if not isinstance(side_map, dict):
            continue
        bucket = side_map.get(side_key)
        if not isinstance(bucket, set):
            bucket = side_map[side_key] = set()
        for iv_key in interval_keys:
            bucket.discard(iv_key)
            self._entry_times_by_iv.pop((sym_key, side_key, iv_key), None)

try:
    if not hasattr(MainWindow, 'log'):
        MainWindow.log = _mw_log
    if not hasattr(MainWindow, '_trade_mux'):
        MainWindow._trade_mux = _mw_trade_mux
    if not hasattr(MainWindow, '_on_trade_signal'):
        MainWindow._on_trade_signal = _mw_on_trade_signal
    if not hasattr(MainWindow, '_pos_symbol_keys'):
        MainWindow._pos_symbol_keys = _mw_pos_symbol_keys
    if not hasattr(MainWindow, '_pos_interval_keys'):
        MainWindow._pos_interval_keys = _mw_pos_interval_keys
    if not hasattr(MainWindow, '_track_interval_open'):
        MainWindow._track_interval_open = _mw_pos_track_interval_open
    if not hasattr(MainWindow, '_track_interval_close'):
        MainWindow._track_interval_close = _mw_pos_track_interval_close
except Exception:
    pass
def _derive_margin_snapshot(position: dict | None, qty_hint: float = 0.0, entry_price_hint: float = 0.0) -> tuple[float, float, float, float]:
    """Return margin, balance, maintenance requirement, and unrealized loss for a futures position."""
    if not isinstance(position, dict):
        return 0.0, 0.0, 0.0, 0.0
    try:
        margin = float(
            position.get("isolatedMargin")
            or position.get("isolatedWallet")
            or position.get("initialMargin")
            or 0.0
        )
    except Exception:
        margin = 0.0
    try:
        leverage = float(position.get("leverage") or 0.0)
    except Exception:
        leverage = 0.0
    try:
        entry_price = float(position.get("entryPrice") or 0.0)
    except Exception:
        entry_price = 0.0
    if entry_price <= 0.0:
        entry_price = max(0.0, float(entry_price_hint or 0.0))
    try:
        notional_val = abs(float(position.get("notional") or 0.0))
    except Exception:
        notional_val = 0.0
    if notional_val <= 0.0 and entry_price > 0.0 and qty_hint > 0.0:
        notional_val = entry_price * qty_hint
    if margin <= 0.0:
        if leverage > 0.0 and notional_val > 0.0:
            margin = notional_val / leverage
        elif notional_val > 0.0:
            margin = notional_val
    if margin <= 0.0 and entry_price > 0.0 and qty_hint > 0.0:
        if leverage > 0.0:
            margin = (entry_price * qty_hint) / leverage
        else:
            margin = entry_price * qty_hint
    margin = max(margin, 0.0)
    try:
        margin_balance = float(position.get("marginBalance") or 0.0)
    except Exception:
        margin_balance = 0.0
    try:
        iso_wallet = float(position.get("isolatedWallet") or 0.0)
    except Exception:
        iso_wallet = 0.0
    try:
        unrealized_profit = float(position.get("unRealizedProfit") or 0.0)
    except Exception:
        unrealized_profit = 0.0
    if margin_balance <= 0.0 and iso_wallet > 0.0:
        margin_balance = iso_wallet + unrealized_profit
    if margin_balance <= 0.0 and iso_wallet > 0.0:
        margin_balance = iso_wallet
    if margin_balance <= 0.0 and margin > 0.0:
        margin_balance = margin + unrealized_profit
    if margin_balance <= 0.0 and margin > 0.0:
        margin_balance = margin
    margin_balance = max(margin_balance, 0.0)
    try:
        maint_margin = float(position.get("maintMargin") or position.get("maintenanceMargin") or 0.0)
    except Exception:
        maint_margin = 0.0
    try:
        maint_rate = float(
            position.get("maintMarginRate")
            or position.get("maintenanceMarginRate")
            or position.get("maintMarginRatio")
            or position.get("maintenanceMarginRatio")
            or 0.0
        )
    except Exception:
        maint_rate = 0.0
    if maint_rate > 1.0:
        maint_rate = maint_rate / 100.0
    if maint_margin <= 0.0 and maint_rate > 0.0 and notional_val > 0.0:
        maint_margin = notional_val * maint_rate
    if margin_balance > 0.0 and maint_margin > margin_balance:
        maint_margin = margin_balance
    unrealized_loss = max(0.0, -unrealized_profit)
    return margin, margin_balance, maint_margin, unrealized_loss
def _begin_close_on_exit_sequence(self):
    if getattr(self, "_close_in_progress", False):
        return
    self._close_in_progress = True
    auth_snapshot = _snapshot_auth_state(self)
    if not hasattr(self, "_bg_workers"):
        self._bg_workers = []
    try:
        message = QtWidgets.QMessageBox(self)
        message.setWindowTitle("Closing Positions")
        message.setText("Closing open positions before exit. Please wait.")
        try:
            message.setIcon(QtWidgets.QMessageBox.Icon.Information)
        except Exception:
            pass
        message.setStandardButtons(QtWidgets.QMessageBox.StandardButton.NoButton)
        message.setModal(False)
        message.show()
        self._close_progress_dialog = message
    except Exception:
        self._close_progress_dialog = None

    def _do():
        return _stop_strategy_sync(self, close_positions=True, auth=auth_snapshot)

    def _done(res, err):
        try:
            if getattr(self, "_close_progress_dialog", None):
                self._close_progress_dialog.close()
        except Exception:
            pass
        self._close_progress_dialog = None
        self._close_in_progress = False
        def _positions_remaining() -> list:
            try:
                acct_text = str(auth_snapshot.get("account_type") or "").upper()
                if acct_text.startswith("FUT"):
                    return [
                        p for p in (self.shared_binance.list_open_futures_positions(force_refresh=True) or [])
                        if abs(float(p.get("positionAmt") or 0.0)) > 0.0
                    ]
            except Exception:
                return []
            return []
        if err:
            try:
                self.log(f"Stop error during exit: {err}")
            except Exception:
                pass
            remaining = _positions_remaining()
            if remaining:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Close-all failed",
                    "Some positions are still open. Please try closing them manually.",
                )
            return
        else:
            try:
                if isinstance(res, dict) and res.get("close_all_result"):
                    _handle_close_all_result(self, res.get("close_all_result"))
            except Exception:
                pass
            remaining = _positions_remaining()
            if remaining:
                try:
                    symbols_left = ", ".join(sorted({str(p.get('symbol') or '').upper() for p in remaining}))
                except Exception:
                    symbols_left = "some positions"
                QtWidgets.QMessageBox.warning(
                    self,
                    "Positions still open",
                    f"Could not close all positions automatically. Remaining: {symbols_left}. Please close manually.",
                )
                return
        self._force_close = True
        QtWidgets.QWidget.close(self)

        worker = CallWorker(_do, parent=self)
        try:
            worker.progress.connect(self.log)
        except Exception:
            pass
        worker.done.connect(_done)

        def _cleanup():
            try:
                self._bg_workers.remove(worker)
            except Exception:
                pass

        worker.finished.connect(_cleanup)
        worker.finished.connect(worker.deleteLater)
        self._bg_workers.append(worker)
        worker.start()
_LATEST_VERSION_CACHE: dict[str, tuple[str, float]] = {}
