from __future__ import annotations
import os, importlib
from importlib import metadata as _md

# Must be set BEFORE any Qt object exists. Force the value so Qt picks it up even if the
# environment already provided something else (Windows defaults to RoundPreferFloor).
os.environ["QT_SCALE_FACTOR_ROUNDING_POLICY"] = "PassThrough"

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

_QT_LINE = "Qt=unknown"
try:
    from PyQt6.QtCore import QT_VERSION_STR as _QT_VER, PYQT_VERSION_STR as _PYQT_VER
    _QT_LINE = f"Qt={_QT_VER} (PyQt={_PYQT_VER})"
except Exception:
    pass

_WEBENGINE = "PyQt6-WebEngine=not-installed"
try:
    from PyQt6 import QtWebEngineCore as _QtWebEngineCore  # noqa: F401
    ver = (
        getattr(_QtWebEngineCore, "PYQT_WEBENGINE_VERSION_STR", None)
        or getattr(_QtWebEngineCore, "QTWEBENGINE_VERSION_STR", None)
        or getattr(_QtWebEngineCore, "PYQT_WEBENGINE_VERSION", None)
    )
    if isinstance(ver, int):
        major = (ver >> 16) & 0xFF
        minor = (ver >> 8) & 0xFF
        patch = ver & 0xFF
        ver = f"{major}.{minor}.{patch}"
    if ver:
        _WEBENGINE = f"PyQt6-WebEngine={ver}"
except Exception:
    pass

print(f"pandas={_PANDAS_VER}, pandas_ta={_PTA}, {_QT_LINE}, {_WEBENGINE}", flush=True)

PANDAS_VERSION = _PANDAS_VER
PANDAS_TA_VERSION = _PTA
PANDAS_TA_AVAILABLE = bool(_PTA and _PTA != "not-installed")
