from __future__ import annotations

import importlib.metadata as importlib_metadata
import os
import sys
import urllib.parse
from pathlib import Path

from PyQt6 import QtCore

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
    if sys.platform != "win32":
        return True
    flag = str(os.environ.get("BOT_PRIME_NATIVE_CHART_HOST", "1")).strip().lower()
    return flag in {"1", "true", "yes", "on"}


def _configure_tradingview_webengine_env() -> None:
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
        disable_gpu = False if force_gpu else False
    flags = str(os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "") or "").strip()
    parts = [part for part in flags.split() if part]
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
    if str(os.environ.get("BOT_DISABLE_CHARTS", "")).strip().lower() in {"1", "true", "yes", "on"}:
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
    global TradingViewWidget, TRADINGVIEW_EMBED_AVAILABLE, _TRADINGVIEW_IMPORT_ERROR
    disable_tradingview = str(os.environ.get("BOT_DISABLE_TRADINGVIEW", "")).strip().lower() in {"1", "true", "yes", "on"}
    disable_charts = str(os.environ.get("BOT_DISABLE_CHARTS", "")).strip().lower() in {"1", "true", "yes", "on"}
    if disable_tradingview or disable_charts:
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
        from .tradingview_widget import TradingViewWidget as _TVW, TRADINGVIEW_EMBED_AVAILABLE as _EMBED  # type: ignore
    except Exception as exc:
        _TRADINGVIEW_IMPORT_ERROR = exc
        TradingViewWidget = None  # type: ignore[assignment]
        TRADINGVIEW_EMBED_AVAILABLE = False
        return TradingViewWidget, TRADINGVIEW_EMBED_AVAILABLE
    TradingViewWidget = _TVW  # type: ignore[assignment]
    TRADINGVIEW_EMBED_AVAILABLE = bool(_EMBED and _TVW is not None)
    return TradingViewWidget, TRADINGVIEW_EMBED_AVAILABLE


def _load_binance_widget():
    global BinanceWebWidget, BINANCE_WEB_AVAILABLE, _BINANCE_IMPORT_ERROR
    disable_charts = str(os.environ.get("BOT_DISABLE_CHARTS", "")).strip().lower() in {"1", "true", "yes", "on"}
    if disable_charts:
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
        from .binance_web_widget import BinanceWebWidget as _BW  # type: ignore
    except Exception as exc:
        _BINANCE_IMPORT_ERROR = exc
        BinanceWebWidget = None  # type: ignore[assignment]
        BINANCE_WEB_AVAILABLE = False
        return BinanceWebWidget, BINANCE_WEB_AVAILABLE
    BinanceWebWidget = _BW  # type: ignore[assignment]
    BINANCE_WEB_AVAILABLE = bool(_BW is not None)
    return BinanceWebWidget, BINANCE_WEB_AVAILABLE


def _load_lightweight_widget():
    global LightweightChartWidget, LIGHTWEIGHT_CHART_AVAILABLE, _LIGHTWEIGHT_IMPORT_ERROR
    disable_charts = str(os.environ.get("BOT_DISABLE_CHARTS", "")).strip().lower() in {"1", "true", "yes", "on"}
    if disable_charts:
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
        from .lightweight_widget import LightweightChartWidget as _LW  # type: ignore
    except Exception as exc:
        _LIGHTWEIGHT_IMPORT_ERROR = exc
        LightweightChartWidget = None  # type: ignore[assignment]
        LIGHTWEIGHT_CHART_AVAILABLE = False
        return LightweightChartWidget, LIGHTWEIGHT_CHART_AVAILABLE
    LightweightChartWidget = _LW  # type: ignore[assignment]
    LIGHTWEIGHT_CHART_AVAILABLE = bool(_LW is not None)
    return LightweightChartWidget, LIGHTWEIGHT_CHART_AVAILABLE


def _tradingview_supported(*, probe: bool = False) -> bool:
    disable_tradingview = str(os.environ.get("BOT_DISABLE_TRADINGVIEW", "")).strip().lower() in {"1", "true", "yes", "on"}
    disable_charts = str(os.environ.get("BOT_DISABLE_CHARTS", "")).strip().lower() in {"1", "true", "yes", "on"}
    if disable_tradingview or disable_charts:
        return False
    if TradingViewWidget is not None and TRADINGVIEW_EMBED_AVAILABLE:
        return True
    if _TRADINGVIEW_IMPORT_ERROR is not None:
        return False
    if not probe:
        return False
    widget_class, available = _load_tradingview_widget()
    return bool(available and widget_class is not None)


def _binance_supported(*, probe: bool = False) -> bool:
    disable_charts = str(os.environ.get("BOT_DISABLE_CHARTS", "")).strip().lower() in {"1", "true", "yes", "on"}
    if disable_charts:
        return False
    if BinanceWebWidget is not None and BINANCE_WEB_AVAILABLE:
        return True
    if _BINANCE_IMPORT_ERROR is not None:
        return False
    if not probe:
        return False
    widget_class, available = _load_binance_widget()
    return bool(available and widget_class is not None)


def _lightweight_supported(*, probe: bool = False) -> bool:
    disable_charts = str(os.environ.get("BOT_DISABLE_CHARTS", "")).strip().lower() in {"1", "true", "yes", "on"}
    if disable_charts:
        return False
    if LightweightChartWidget is not None and LIGHTWEIGHT_CHART_AVAILABLE:
        return True
    if _LIGHTWEIGHT_IMPORT_ERROR is not None:
        return False
    if not probe:
        return False
    widget_class, available = _load_lightweight_widget()
    return bool(available and widget_class is not None)


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
