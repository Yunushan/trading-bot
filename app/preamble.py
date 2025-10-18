from __future__ import annotations
import os, importlib
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
except Exception:
    # Never allow env-setup failures to abort app startup.
    pass

try:
    from PyQt6 import QtCore  # type: ignore[import]
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.ApplicationAttribute.AA_UseSoftwareOpenGL, True)
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

_QT_LINE = "Qt=unknown"
try:
    from PyQt6.QtCore import QT_VERSION_STR as _QT_VER, PYQT_VERSION_STR as _PYQT_VER
    _QT_LINE = f"Qt={_QT_VER} (PyQt={_PYQT_VER})"
except Exception:
    pass

def _resolve_webengine_version():
    for dist in ("PyQt6-WebEngine", "pyqt6-webengine", "PyQt6_WebEngine"):
        try:
            return _md.version(dist)
        except Exception:
            pass
    try:
        from PyQt6 import QtWebEngineCore as _QtWebEngineCore  # noqa: F401
        ver = (
            getattr(_QtWebEngineCore, "PYQT_WEBENGINE_VERSION_STR", None)
            or getattr(_QtWebEngineCore, "QTWEBENGINE_VERSION_STR", None)
            or getattr(_QtWebEngineCore, "PYQT_WEBENGINE_VERSION", None)
        )
        if not ver:
            try:
                from PyQt6 import QtWebEngineWidgets as _QtWebEngineWidgets  # noqa: F401
                ver = getattr(_QtWebEngineWidgets, "PYQT_WEBENGINE_VERSION_STR", None)
            except Exception:
                pass
        if isinstance(ver, int):
            major = (ver >> 16) & 0xFF
            minor = (ver >> 8) & 0xFF
            patch = ver & 0xFF
            ver = f"{major}.{minor}.{patch}"
        if ver:
            return str(ver)
        return "installed"
    except Exception:
        return None

_WEBENGINE_VER = _resolve_webengine_version()
_WEBENGINE = f"PyQt6-WebEngine={_WEBENGINE_VER}" if _WEBENGINE_VER else "PyQt6-WebEngine=not-installed"

_PYBINANCE_VER = _resolve_module_version("python-binance", "python_binance", "binance")
_NUMPY_VER = _resolve_module_version("numpy")
_REQUESTS_VER = _resolve_module_version("requests")

print(
    f"pandas={_PANDAS_VER}, pandas_ta={_PTA}, {_QT_LINE}, {_WEBENGINE}, "
    f"python-binance={_PYBINANCE_VER}, numpy={_NUMPY_VER}, requests={_REQUESTS_VER}",
    flush=True,
)

PANDAS_VERSION = _PANDAS_VER
PANDAS_TA_VERSION = _PTA
PANDAS_TA_AVAILABLE = bool(_PTA and _PTA != "not-installed")
