from __future__ import annotations
import os, importlib, sys
from importlib import metadata as _md

# Must be set BEFORE any Qt object exists. Force the value so Qt picks it up even if the
# environment already provided something else (Windows defaults to RoundPreferFloor).
os.environ["QT_SCALE_FACTOR_ROUNDING_POLICY"] = "PassThrough"

# When running PyQt WebEngine as root (common on some server setups / Docker),
# Chromium refuses to launch without disabling the sandbox. Detect that case
# early and append the required flags so the TradingView/QtWebEngine widgets
# can start without crashing.
try:
    if os.name == "posix":
        is_root = hasattr(os, "geteuid") and os.geteuid() == 0
        flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").strip()
        flag_parts = [part for part in flags.split() if part]
        needed_flags = [
            "--no-sandbox",
            "--disable-gpu",
            "--disable-gpu-sandbox",
            "--disable-software-rasterizer",
            "--disable-dev-shm-usage",
            "--no-zygote",
        ]
        for flag in needed_flags:
            if flag not in flag_parts:
                flag_parts.append(flag)
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(flag_parts).strip()
        os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1" if is_root else os.environ.get("QTWEBENGINE_DISABLE_SANDBOX", "0"))
        os.environ.setdefault("QTWEBENGINE_USE_SANDBOX", "0" if is_root else os.environ.get("QTWEBENGINE_USE_SANDBOX", "1"))
        os.environ.setdefault("QT_OPENGL", "software")
        os.environ.setdefault("QSG_RHI_BACKEND", "software")
        os.environ.setdefault("QT_QUICK_BACKEND", "software")
        os.environ.setdefault("QT_XCB_GL_INTEGRATION", "none")
        # Some distros crash unless XDG_RUNTIME_DIR is defined; fallback to /tmp for headless runs.
        if is_root and not os.environ.get("XDG_RUNTIME_DIR"):
            tmp_runtime = "/tmp/qt-runtime-root"
            try:
                os.makedirs(tmp_runtime, mode=0o700, exist_ok=True)
            except Exception:
                tmp_runtime = "/tmp"
            try:
                os.chmod(tmp_runtime, 0o700)
            except Exception:
                pass
            os.environ["XDG_RUNTIME_DIR"] = tmp_runtime
    
    # Windows-specific QtWebEngine tuning: prefer GPU acceleration for responsiveness
    if os.name == "nt":
        flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").strip()
        gpu_flag = str(os.environ.get("BOT_TRADINGVIEW_DISABLE_GPU", "")).strip().lower()
        force_gpu = str(os.environ.get("BOT_TRADINGVIEW_FORCE_GPU", "")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if gpu_flag:
            disable_gpu = gpu_flag in {"1", "true", "yes", "on"}
        elif force_gpu:
            disable_gpu = False
        else:
            disable_gpu = False

        drop_flags = {
            "--single-process",
            "--in-process-gpu",
        }
        if disable_gpu:
            drop_flags |= {
                "--ignore-gpu-blocklist",
                "--enable-gpu-rasterization",
                "--enable-zero-copy",
                "--use-gl=angle",
                "--disable-software-rasterizer",
            }
        else:
            drop_flags |= {
                "--disable-gpu",
                "--disable-software-rasterizer",
            }

        flag_parts = [part for part in flags.split() if part and part not in drop_flags]
        windows_flags = [
            "--no-sandbox",
            "--disable-logging",
            "--disable-renderer-backgrounding",
            "--disable-background-timer-throttling",
        ]
        if disable_gpu:
            windows_flags += [
                "--disable-gpu",
                "--disable-gpu-compositing",
                "--disable-features=Vulkan,UseSkiaRenderer",
            ]
            os.environ.setdefault("QTWEBENGINE_DISABLE_GPU", "1")
            os.environ.setdefault("QT_OPENGL", "software")
            os.environ.setdefault("QSG_RHI_BACKEND", "software")
            os.environ.setdefault("QT_QUICK_BACKEND", "software")
            os.environ.setdefault("BOT_FORCE_SOFTWARE_OPENGL", "1")
        else:
            windows_flags += [
                "--ignore-gpu-blocklist",
                "--enable-gpu-rasterization",
                "--enable-zero-copy",
                "--use-gl=angle",
            ]
        for flag in windows_flags:
            if flag not in flag_parts:
                flag_parts.append(flag)
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(flag_parts).strip()
        os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
except Exception:
    # Never allow env-setup failures to abort app startup.
    pass

try:
    from PyQt6 import QtCore  # type: ignore[import]
    disable_share = str(os.environ.get("BOT_DISABLE_SHARE_OPENGL_CONTEXTS", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    force_sw = str(os.environ.get("BOT_FORCE_SOFTWARE_OPENGL", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    qt_open_gl = str(os.environ.get("QT_OPENGL", "")).strip().lower()
    if not disable_share and not force_sw and qt_open_gl != "software":
        QtCore.QCoreApplication.setAttribute(QtCore.Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
except Exception:
    pass

def _resolve_pandas_version():
    try:
        import pandas as _pd
        return getattr(_pd, "__version__", "installed")
    except Exception:
        try:
            _pd = importlib.import_module("pandas")
            return getattr(_pd, "__version__", "installed")
        except Exception:
            return "not-installed"

def _resolve_pandas_ta_version():
    # Try distribution metadata first (works even if import would fail)
    for _dist in ("pandas_ta", "pandas-ta"):
        try:
            return _md.version(_dist)
        except Exception:
            pass
    # Fallback to module import
    try:
        import pandas_ta as _pta
        return getattr(_pta, "__version__", "installed")
    except Exception:
        return "not-installed"

# Resolve versions FIRST so the print never raises NameError
_PANDAS_VER = _resolve_pandas_version()
_PTA = _resolve_pandas_ta_version()

def _resolve_module_version(primary: str, *alternates: str) -> str:
    candidates = [primary, *alternates]
    for cand in candidates:
        if not cand:
            continue
        try:
            return _md.version(cand)
        except Exception:
            continue
    module_name = primary.replace("-", "_")
    try:
        module = importlib.import_module(module_name)
        return getattr(module, "__version__", "installed")
    except Exception:
        return "not-installed"

_QT_LINE = "PyQt6=unknown"
try:
    from PyQt6.QtCore import QT_VERSION_STR as _QT_VER, PYQT_VERSION_STR as _PYQT_VER
    _QT_LINE = f"PyQt6={_PYQT_VER} (Qt={_QT_VER})"
except Exception:
    pass

def _resolve_webengine_version():
    for dist in ("PyQt6-WebEngine", "pyqt6-webengine", "PyQt6_WebEngine"):
        try:
            return _md.version(dist)
        except Exception:
            pass
    # Avoid importing QtWebEngine modules during startup on Windows.
    # Importing them can spawn helper processes that briefly flash windows
    # before the main UI appears. Rely on package metadata instead.
    return "installed"

_WEBENGINE_VER = _resolve_webengine_version()
_WEBENGINE = f"PyQt6-WebEngine={_WEBENGINE_VER}" if _WEBENGINE_VER else "PyQt6-WebEngine=not-installed"

_PYBINANCE_VER = _resolve_module_version("python-binance", "python_binance", "binance")
_BINANCE_CONNECTOR_VER = _resolve_module_version("binance-connector", "binance_connector")
_CCXT_VER = _resolve_module_version("ccxt")
_SDK_USDS_VER = _resolve_module_version("binance-sdk-derivatives-trading-usds-futures", "binance_sdk_derivatives_trading_usds_futures")
_SDK_COIN_VER = _resolve_module_version("binance-sdk-derivatives-trading-coin-futures", "binance_sdk_derivatives_trading_coin_futures")
_SDK_SPOT_VER = _resolve_module_version("binance-sdk-spot", "binance_sdk_spot")
_NUMPY_VER = _resolve_module_version("numpy")
_REQUESTS_VER = _resolve_module_version("requests")

print(
    f"pandas={_PANDAS_VER}, pandas_ta={_PTA}, {_QT_LINE}, {_WEBENGINE}, "
    f"python-binance={_PYBINANCE_VER}, binance-connector={_BINANCE_CONNECTOR_VER}, ccxt={_CCXT_VER}, "
    f"binance-sdk-derivatives-trading-usds-futures={_SDK_USDS_VER}, "
    f"binance-sdk-derivatives-trading-coin-futures={_SDK_COIN_VER}, "
    f"binance-sdk-spot={_SDK_SPOT_VER}, "
    f"numpy={_NUMPY_VER}, requests={_REQUESTS_VER}",
    flush=True,
)

PANDAS_VERSION = _PANDAS_VER
PANDAS_TA_VERSION = _PTA
PANDAS_TA_AVAILABLE = bool(_PTA and _PTA != "not-installed")
