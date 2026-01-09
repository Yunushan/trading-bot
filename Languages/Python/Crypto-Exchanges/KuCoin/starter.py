from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import textwrap
from uuid import uuid4
from pathlib import Path
from datetime import datetime

os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
_chromium_flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
_dns_guard_flags = "--dns-prefetch-disable"
_gpu_flags = ""
if sys.platform == "win32":
    _dns_guard_flags = f"{_dns_guard_flags} --disable-features=WinUseBrowserSignal"
    _gpu_flags = "--ignore-gpu-blocklist --enable-gpu-rasterization --enable-zero-copy --use-gl=angle"
if _dns_guard_flags not in _chromium_flags or (_gpu_flags and _gpu_flags not in _chromium_flags):
    merged_flags = f"{_chromium_flags} {_dns_guard_flags} {_gpu_flags}".strip()
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = merged_flags


def _strip_foreign_site_packages() -> None:
    """
    Remove site-packages entries from other Python versions that can shadow the venv.
    Fixes ModuleNotFoundError for compiled wheels (e.g., PyQt6.sip) when PYTHONPATH
    points at a different interpreter's user site.
    """
    expected_tokens = (
        f"python{sys.version_info.major}.{sys.version_info.minor}",
        f"python{sys.version_info.major}{sys.version_info.minor}",
    )
    prefix = Path(sys.prefix).resolve()
    base_prefix = Path(getattr(sys, "base_prefix", sys.prefix)).resolve()
    cleaned: list[str] = []
    removed: list[str] = []
    for path in sys.path:
        lower = path.lower()
        if "site-packages" in lower:
            keep = False
            try:
                resolved = Path(path).resolve()
            except Exception:
                resolved = None
            if resolved is not None:
                if resolved == prefix or prefix in resolved.parents:
                    keep = True
                elif resolved == base_prefix or base_prefix in resolved.parents:
                    keep = True
            if not keep and "python" in lower and any(token in lower for token in expected_tokens):
                keep = True
            if not keep:
                removed.append(path)
                continue
        cleaned.append(path)
    if removed:
        sys.path[:] = cleaned
        os.environ.pop("PYTHONPATH", None)


_strip_foreign_site_packages()
from PyQt6 import QtCore, QtGui, QtWidgets

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parents[3] if len(BASE_DIR.parents) >= 4 else BASE_DIR
WINDOWS_TASKBAR_DIR = REPO_ROOT / "Languages" / "Python" / "Crypto-Exchanges" / "Binance"
PREFERRED_QT_VERSION = os.environ.get("STARTER_QT_VERSION") or "6.5.3"

_WINDOWS_TASKBAR_SPEC = importlib.util.spec_from_file_location(
    "windows_taskbar", WINDOWS_TASKBAR_DIR / "windows_taskbar.py"
)
if _WINDOWS_TASKBAR_SPEC is None or _WINDOWS_TASKBAR_SPEC.loader is None:  # pragma: no cover - sanity guard
    raise ImportError(f"Unable to locate windows_taskbar module at {WINDOWS_TASKBAR_DIR}")
windows_taskbar = importlib.util.module_from_spec(_WINDOWS_TASKBAR_SPEC)
_WINDOWS_TASKBAR_SPEC.loader.exec_module(windows_taskbar)

apply_taskbar_metadata = windows_taskbar.apply_taskbar_metadata
build_relaunch_command = windows_taskbar.build_relaunch_command
ensure_app_user_model_id = windows_taskbar.ensure_app_user_model_id
BINANCE_MAIN = WINDOWS_TASKBAR_DIR / "main.py"
BYBIT_MAIN = REPO_ROOT / "Languages" / "Python" / "Crypto-Exchanges" / "Bybit" / "main.py"
OKX_MAIN = REPO_ROOT / "Languages" / "Python" / "Crypto-Exchanges" / "OKX" / "main.py"
GATE_MAIN = REPO_ROOT / "Languages" / "Python" / "Crypto-Exchanges" / "Gate" / "main.py"
BITGET_MAIN = REPO_ROOT / "Languages" / "Python" / "Crypto-Exchanges" / "Bitget" / "main.py"
MEXC_MAIN = REPO_ROOT / "Languages" / "Python" / "Crypto-Exchanges" / "MEXC" / "main.py"
KUCOIN_MAIN = REPO_ROOT / "Languages" / "Python" / "Crypto-Exchanges" / "KuCoin" / "main.py"
BINANCE_CPP_PROJECT = REPO_ROOT / "Languages" / "C++" / "Crypto-Exchanges" / "Binance"
BINANCE_CPP_BUILD_ROOT = REPO_ROOT / "build" / "binance_cpp"
BINANCE_CPP_EXECUTABLE_BASENAME = "binance_backtest_tab"
APP_ICON_BASENAME = "crypto_forex_logo"
APP_ICON_PATH = REPO_ROOT / "assets" / f"{APP_ICON_BASENAME}.ico"
APP_ICON_FALLBACK = REPO_ROOT / "assets" / f"{APP_ICON_BASENAME}.png"
WINDOWS_APP_ID = "com.tradingbot.starter"
TEMP_DIR = Path(os.getenv("TEMP") or ".").resolve()
DEBUG_LOG_PATH = TEMP_DIR / "starter_debug.log"
STARTER_CHILD_WINDOW_EVENTS_LOG_PATH = TEMP_DIR / "starter_child_window_events.log"
BINANCE_WINDOW_EVENTS_LOG_PATH = TEMP_DIR / "binance_window_events.log"

PYTHON_EXCHANGE_MAIN = {
    "binance": BINANCE_MAIN,
    "bybit": BYBIT_MAIN,
    "okx": OKX_MAIN,
    "gate": GATE_MAIN,
    "bitget": BITGET_MAIN,
    "mexc": MEXC_MAIN,
    "kucoin": KUCOIN_MAIN,
}
PYTHON_EXCHANGE_LABELS = {
    "binance": "Binance",
    "bybit": "Bybit",
    "okx": "OKX",
    "gate": "Gate",
    "bitget": "Bitget",
    "mexc": "MEXC",
    "kucoin": "KuCoin",
}


def _debug_log(message: str) -> None:
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(DEBUG_LOG_PATH, "a", encoding="utf-8", errors="ignore") as fh:
            fh.write(f"[{timestamp}] {message}\n")
        try:
            print(f"[starter] {message}", flush=True)
        except Exception:
            pass
    except Exception:
        pass


def _load_app_icon() -> QtGui.QIcon | None:
    for path in (APP_ICON_PATH, APP_ICON_FALLBACK):
        if path.is_file():
            return QtGui.QIcon(str(path))
    return None


LANGUAGE_OPTIONS = [
    {
        "key": "python",
        "title": "Python",
        "subtitle": "Fast to build - Huge ecosystem",
        "accent": "#3b82f6",
        "badge": "Recommended",
    },
    {
        "key": "cpp",
        "title": "C++",
        "subtitle": "Qt native desktop (preview)",
        "accent": "#38bdf8",
        "badge": "Preview",
    },
    {
        "key": "rust",
        "title": "Rust",
        "subtitle": "Memory safe - coming soon",
        "accent": "#fb923c",
        "badge": "Coming Soon",
        "disabled": True,
    },
    {
        "key": "c",
        "title": "C",
        "subtitle": "Low-level power - coming soon",
        "accent": "#f87171",
        "badge": "Coming Soon",
        "disabled": True,
    },
]

MARKET_OPTIONS = [
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

CRYPTO_EXCHANGES = [
    {"key": "binance", "title": "Binance", "subtitle": "Advanced desktop bot ready to launch", "accent": "#fbbf24"},
    {
        "key": "bybit",
        "title": "Bybit",
        "subtitle": "Advanced desktop bot ready to launch",
        "accent": "#fb7185",
    },
    {
        "key": "okx",
        "title": "OKX",
        "subtitle": "Advanced desktop bot ready to launch",
        "accent": "#a78bfa",
    },
    {
        "key": "gate",
        "title": "Gate",
        "subtitle": "Advanced desktop bot ready to launch",
        "accent": "#22c55e",
    },
    {
        "key": "bitget",
        "title": "Bitget",
        "subtitle": "Advanced desktop bot ready to launch",
        "accent": "#0ea5e9",
    },
    {
        "key": "mexc",
        "title": "MEXC",
        "subtitle": "Advanced desktop bot ready to launch",
        "accent": "#10b981",
    },
    {
        "key": "kucoin",
        "title": "KuCoin",
        "subtitle": "Advanced desktop bot ready to launch",
        "accent": "#eab308",
    },
]

FOREX_BROKERS = [
    {
        "key": "oanda",
        "title": "OANDA",
        "subtitle": "Popular REST API - coming soon",
        "accent": "#60a5fa",
        "badge": "Coming Soon",
        "disabled": True,
    },
    {
        "key": "fxcm",
        "title": "FXCM",
        "subtitle": "Streaming quotes - coming soon",
        "accent": "#c084fc",
        "badge": "Coming Soon",
        "disabled": True,
    },
    {
        "key": "ig",
        "title": "IG",
        "subtitle": "Global CFD trading - coming soon",
        "accent": "#f472b6",
        "badge": "Coming Soon",
        "disabled": True,
    },
]

WINDOW_BG = "#0d1117"
PANEL_BG = "#161b22"
TEXT_COLOR = "#e6edf3"
MUTED_TEXT = "#94a3b8"


class SelectableCard(QtWidgets.QFrame):
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
    ) -> None:
        super().__init__()
        self.option_key = option_key
        self.accent_color = accent_color
        self._selected = False
        self._disabled = bool(disabled)
        self.setCursor(
            QtCore.Qt.CursorShape.ArrowCursor if self._disabled else QtCore.Qt.CursorShape.PointingHandCursor
        )
        self.setObjectName(f"card_{option_key}")

        wrapper = QtWidgets.QVBoxLayout(self)
        wrapper.setContentsMargins(0, 0, 0, 0)
        wrapper.setSpacing(0)

        self.accent_bar = QtWidgets.QFrame(self)
        self.accent_bar.setFixedHeight(6)
        wrapper.addWidget(self.accent_bar)

        body = QtWidgets.QWidget(self)
        body_layout = QtWidgets.QVBoxLayout(body)
        body_layout.setContentsMargins(18, 18, 18, 18)
        body_layout.setSpacing(10)
        wrapper.addWidget(body)

        self.badge_label = QtWidgets.QLabel(badge_text or "", parent=body)
        self.badge_label.setStyleSheet(
            "padding: 2px 8px; border-radius: 8px; font-size: 11px; font-weight: 600;"
            "background-color: rgba(59, 130, 246, 0.15); color: #93c5fd;"
        )
        body_layout.addWidget(self.badge_label, alignment=QtCore.Qt.AlignmentFlag.AlignLeft)
        self.badge_label.setVisible(bool(badge_text))

        self.title_label = QtWidgets.QLabel(title, parent=body)
        self.title_label.setStyleSheet("font-size: 24px; font-weight: 600;")
        body_layout.addWidget(self.title_label)

        self.subtitle_label = QtWidgets.QLabel(subtitle, parent=body)
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setStyleSheet(f"color: {MUTED_TEXT}; font-size: 13px;")
        body_layout.addWidget(self.subtitle_label)
        body_layout.addStretch()

        self.setDisabledState(self._disabled)

        self._refresh_style()

    def setSelected(self, selected: bool) -> None:
        if self._disabled:
            self._selected = False
        else:
            self._selected = bool(selected)
        self._refresh_style()

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if event.button() == QtCore.Qt.MouseButton.LeftButton and not self._disabled:
            self.clicked.emit(self.option_key)
        super().mouseReleaseEvent(event)

    def setDisabledState(self, disabled: bool) -> None:
        self._disabled = bool(disabled)
        super().setEnabled(not self._disabled)
        self.setCursor(
            QtCore.Qt.CursorShape.ArrowCursor if self._disabled else QtCore.Qt.CursorShape.PointingHandCursor
        )
        self._refresh_style()

    def is_disabled(self) -> bool:
        return self._disabled

    def _refresh_style(self) -> None:
        if self._disabled:
            bg = "#111827"
            border = "#1f2433"
            accent = "#1f2433"
            title_color = "#6b7280"
            subtitle_color = "#4b5563"
        else:
            bg = "#1b2231" if self._selected else "#141925"
            border = self.accent_color if self._selected else "#262c3f"
            accent = self.accent_color if self._selected else "#1f2433"
            title_color = TEXT_COLOR
            subtitle_color = MUTED_TEXT
        self.setStyleSheet(
            f"""
            QFrame#{self.objectName()} {{
                background-color: {bg};
                border: 2px solid {border};
                border-radius: 18px;
            }}
            """
        )
        self.accent_bar.setStyleSheet(
            f"background-color: {accent}; border-top-left-radius: 18px; border-top-right-radius: 18px;"
        )
        self.title_label.setStyleSheet(f"font-size: 24px; font-weight: 600; color: {title_color};")
        self.subtitle_label.setStyleSheet(f"color: {subtitle_color}; font-size: 13px;")


class LoadingButton(QtWidgets.QPushButton):
    def __init__(self, text: str = "", parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._loading = False
        self._spinner_angle = 0
        self._spinner_timer = QtCore.QTimer(self)
        self._spinner_timer.setInterval(45)
        self._spinner_timer.timeout.connect(self._advance_spinner)

    def set_loading(self, loading: bool) -> None:
        loading = bool(loading)
        if loading == self._loading:
            return
        self._loading = loading
        if self._loading:
            self._spinner_angle = 0
            self._spinner_timer.start()
        else:
            self._spinner_timer.stop()
        self.update()

    def is_loading(self) -> bool:
        return bool(self._loading)

    def _advance_spinner(self) -> None:
        self._spinner_angle = (self._spinner_angle + 30) % 360
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # noqa: N802
        super().paintEvent(event)
        if not self._loading:
            return
        try:
            painter = QtGui.QPainter(self)
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
            if self.isEnabled():
                color = QtGui.QColor(255, 255, 255, 225)
            else:
                color = QtGui.QColor(147, 197, 253, 210)
            pen = QtGui.QPen(color)
            pen.setWidth(2)
            pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)

            size = max(12, min(18, self.height() - 10))
            x = self.width() - size - 14
            y = int((self.height() - size) / 2)
            rect = QtCore.QRect(x, y, size, size)
            painter.drawArc(rect, int(self._spinner_angle * 16), int(120 * 16))
        except Exception:
            return
        finally:
            try:
                painter.end()
            except Exception:
                pass


class SpinnerWidget(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None, *, diameter: int = 48) -> None:
        super().__init__(parent)
        self._angle = 0
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(45)
        self._timer.timeout.connect(self._advance)
        self._diameter = max(18, int(diameter))
        self.setFixedSize(self._diameter, self._diameter)

    def start(self) -> None:
        self._angle = 0
        self._timer.start()
        self.update()

    def stop(self) -> None:
        self._timer.stop()
        self.update()

    def _advance(self) -> None:
        self._angle = (self._angle + 30) % 360
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # noqa: N802
        super().paintEvent(event)
        try:
            painter = QtGui.QPainter(self)
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
            color = QtGui.QColor(255, 255, 255, 235)
            pen = QtGui.QPen(color)
            pen.setWidth(4)
            pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            size = min(self.width(), self.height()) - 6
            rect = QtCore.QRect(3, 3, size, size)
            painter.drawArc(rect, int(self._angle * 16), int(120 * 16))
        except Exception:
            return
        finally:
            try:
                painter.end()
            except Exception:
                pass


class LaunchOverlay(QtWidgets.QWidget):
    def __init__(
        self,
        message: str,
        *,
        parent_window: QtWidgets.QWidget | None = None,
        owner_window: QtWidgets.QWidget | None = None,
        cover_owner: bool | None = None,
        fullscreen: bool | None = None,
        all_screens: bool | None = None,
        background_mode: str | None = None,
    ) -> None:
        if cover_owner is None:
            cover_owner = str(os.environ.get("BOT_LAUNCH_OVERLAY_COVER_OWNER", "")).strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
        if fullscreen is None:
            fullscreen = str(os.environ.get("BOT_LAUNCH_OVERLAY_FULLSCREEN", "")).strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
        if all_screens is None:
            all_screens = str(os.environ.get("BOT_LAUNCH_OVERLAY_ALL_SCREENS", "")).strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
        if background_mode is None:
            background_mode = str(os.environ.get("BOT_LAUNCH_OVERLAY_BACKGROUND", "")).strip().lower() or None
        flags = QtCore.Qt.WindowType.FramelessWindowHint | QtCore.Qt.WindowType.Tool
        # Only stay-topmost when explicitly requested (full-screen flicker masking).
        if fullscreen or cover_owner:
            flags |= QtCore.Qt.WindowType.WindowStaysOnTopHint
        super().__init__(parent_window, flags)
        self._fullscreen = bool(fullscreen)
        self._all_screens = bool(all_screens)
        self._cover_owner = bool(cover_owner)
        self._owner_window = owner_window or parent_window
        self._background_mode = (
            str(background_mode or "").strip().lower()
            if str(background_mode or "").strip().lower() in {"solid", "snapshot"}
            else "solid"
        )
        self._background_pixmap: QtGui.QPixmap | None = None
        self._topmost_timer: QtCore.QTimer | None = None
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        if self._fullscreen or self._cover_owner:
            self.setAttribute(QtCore.Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self._bg_color = QtGui.QColor(13, 17, 23, 255)

        self._panel = QtWidgets.QFrame(self)
        self._panel.setObjectName("launchOverlayPanel")
        self._panel.setStyleSheet(
            """
            QFrame#launchOverlayPanel {
                background-color: rgba(13, 17, 23, 235);
                border: 1px solid rgba(59, 130, 246, 110);
                border-radius: 18px;
            }
            QLabel {
                color: #e6edf3;
            }
            """
        )
        panel_layout = QtWidgets.QVBoxLayout(self._panel)
        panel_layout.setContentsMargins(36, 32, 36, 28)
        panel_layout.setSpacing(18)

        self._spinner = SpinnerWidget(self._panel, diameter=52)
        panel_layout.addWidget(self._spinner, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)

        self._label = QtWidgets.QLabel(message, parent=self._panel)
        self._label.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        self._label.setStyleSheet("font-size: 16px; font-weight: 600;")
        self._label.setWordWrap(True)
        panel_layout.addWidget(self._label)

        hint = QtWidgets.QLabel("Please wait…", parent=self._panel)
        hint.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        hint.setStyleSheet("color: #94a3b8; font-size: 13px;")
        panel_layout.addWidget(hint)

        self._spinner.start()
        self._reposition()
        if self._fullscreen and self._background_mode == "snapshot":
            try:
                self._background_pixmap = self._capture_background_snapshot()
            except Exception:
                self._background_pixmap = None
            if self._background_pixmap is None or self._background_pixmap.isNull():
                self._background_pixmap = None
                self._background_mode = "solid"
                self._fullscreen = False
                try:
                    self._reposition()
                except Exception:
                    pass

    @staticmethod
    def _env_flag(name: str) -> bool:
        return str(os.environ.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}

    def _mask_overlay_enabled(self) -> bool:
        # Default: show only the centered panel (do not cover the whole window).
        # Enable full-screen masking with BOT_LAUNCH_OVERLAY_FULLSCREEN=1.
        try:
            return bool(getattr(self, "_fullscreen", False) or getattr(self, "_cover_owner", False))
        except Exception:
            return False

    def set_message(self, message: str) -> None:
        try:
            self._label.setText(str(message))
        except Exception:
            pass

    def _target_screen_geometry(self) -> QtCore.QRect:
        try:
            if self._owner_window is not None:
                pos = self._owner_window.mapToGlobal(self._owner_window.rect().center())
                screen = QtGui.QGuiApplication.screenAt(pos)
                if screen is not None:
                    return screen.geometry()
        except Exception:
            pass
        try:
            screen = QtGui.QGuiApplication.primaryScreen()
            if screen is not None:
                return screen.geometry()
        except Exception:
            pass
        return QtCore.QRect(0, 0, 1024, 768)

    def _virtual_geometry(self) -> QtCore.QRect:
        try:
            screen = QtGui.QGuiApplication.primaryScreen()
            if screen is not None and hasattr(screen, "virtualGeometry"):
                return screen.virtualGeometry()
        except Exception:
            pass
        return self._target_screen_geometry()

    def _owner_geometry(self) -> QtCore.QRect | None:
        try:
            if self._owner_window is None:
                return None
            try:
                frame = self._owner_window.frameGeometry()
                if frame.isValid():
                    return frame
            except Exception:
                pass
            rect = self._owner_window.rect()
            top_left = self._owner_window.mapToGlobal(rect.topLeft())
            return QtCore.QRect(top_left, rect.size())
        except Exception:
            return None

    def _overlay_geometry(self) -> QtCore.QRect:
        if bool(getattr(self, "_cover_owner", False)):
            owner_geo = self._owner_geometry()
            if owner_geo is not None and owner_geo.isValid():
                return owner_geo
        if bool(getattr(self, "_all_screens", False)) or self._env_flag("BOT_LAUNCH_OVERLAY_ALL_SCREENS"):
            return self._virtual_geometry()
        return self._target_screen_geometry()

    def _capture_background_snapshot(self) -> QtGui.QPixmap | None:
        try:
            screen = None
            if self._parent_window is not None:
                try:
                    pos = self._parent_window.mapToGlobal(self._parent_window.rect().center())
                    screen = QtGui.QGuiApplication.screenAt(pos)
                except Exception:
                    screen = None
            if screen is None:
                screen = QtGui.QGuiApplication.primaryScreen()
            if screen is None:
                return None
            return screen.grabWindow(0)
        except Exception:
            return None

    def _reposition(self) -> None:
        screen_geo = self._target_screen_geometry()
        panel_w = min(520, max(360, int(screen_geo.width() * 0.32)))
        panel_h = 220
        x_global = int(screen_geo.x() + (screen_geo.width() - panel_w) / 2)
        y_global = int(screen_geo.y() + (screen_geo.height() - panel_h) / 2)

        if self._mask_overlay_enabled():
            overlay_geo = self._overlay_geometry()
            self.setGeometry(overlay_geo)
            x = int(x_global - overlay_geo.x())
            y = int(y_global - overlay_geo.y())
            self._panel.setGeometry(x, y, panel_w, panel_h)
        else:
            # Panel-only mode: the overlay window is exactly the size of the panel.
            self.setGeometry(x_global, y_global, panel_w, panel_h)
            self._panel.setGeometry(0, 0, panel_w, panel_h)

    def _force_topmost(self) -> None:
        if sys.platform != "win32":
            return
        if not self._mask_overlay_enabled():
            return
        try:
            import ctypes
            import ctypes.wintypes as wintypes
        except Exception:
            return
        try:
            user32 = ctypes.windll.user32
            hwnd = wintypes.HWND(int(self.winId()))
            HWND_TOPMOST = wintypes.HWND(-1)
            SWP_NOSIZE = 0x0001
            SWP_NOMOVE = 0x0002
            SWP_NOACTIVATE = 0x0010
            SWP_SHOWWINDOW = 0x0040
            user32.SetWindowPos(
                hwnd,
                HWND_TOPMOST,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
            )
        except Exception:
            self._set_launch_mask(False)
            return

    def _start_topmost_timer(self) -> None:
        if not self._mask_overlay_enabled():
            return
        if self._topmost_timer is not None:
            return
        timer = QtCore.QTimer(self)
        timer.setInterval(200)
        timer.timeout.connect(self._force_topmost)
        timer.start()
        self._topmost_timer = timer

    def _stop_topmost_timer(self) -> None:
        timer = self._topmost_timer
        if timer is None:
            return
        try:
            timer.stop()
        except Exception:
            pass
        try:
            timer.deleteLater()
        except Exception:
            pass
        self._topmost_timer = None

    def showEvent(self, event: QtGui.QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        try:
            self._reposition()
            self.raise_()
            self._force_topmost()
            self._start_topmost_timer()
        except Exception:
            pass

    def hideEvent(self, event: QtGui.QHideEvent) -> None:  # noqa: N802
        try:
            self._stop_topmost_timer()
        except Exception:
            pass
        super().hideEvent(event)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # noqa: N802
        super().paintEvent(event)
        if not self._mask_overlay_enabled():
            return
        try:
            painter = QtGui.QPainter(self)
            if (
                self._background_mode == "snapshot"
                and self._background_pixmap is not None
                and not self._background_pixmap.isNull()
            ):
                painter.drawPixmap(self.rect(), self._background_pixmap)
            else:
                painter.fillRect(self.rect(), self._bg_color)
        except Exception:
            return
        finally:
            try:
                painter.end()
            except Exception:
                pass

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
        try:
            self._spinner.stop()
        except Exception:
            pass
        try:
            self._stop_topmost_timer()
        except Exception:
            pass
        super().closeEvent(event)


class StarterWindow(QtWidgets.QWidget):
    def __init__(self, app_icon: QtGui.QIcon | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Trading Bot Starter")
        self.setMinimumSize(1024, 640)
        self.resize(1100, 720)
        self.setStyleSheet(
            f"background-color: {WINDOW_BG}; color: {TEXT_COLOR};"
            "font-family: 'Segoe UI', 'Inter', 'Helvetica Neue', sans-serif;"
        )
        if app_icon is not None:
            self.setWindowIcon(app_icon)

        self.selected_language = "python"
        self.selected_market: str | None = None
        self.selected_exchange: str | None = None
        self._is_launching = False
        self._bot_ready = False
        self._cpp_binance_executable: Path | None = None
        self._active_launch_label = "Selected bot"
        self._running_ready_message = "Selected bot is running. Close it to relaunch."
        self._closed_message = "Selected bot closed. Launch it again anytime."
        self._active_bot_process: subprocess.Popen[str] | None = None
        self._launch_status_timer = QtCore.QTimer(self)
        self._launch_status_timer.setSingleShot(True)
        self._launch_status_timer.timeout.connect(self._handle_launch_timeout)
        self._process_watch_timer = QtCore.QTimer(self)
        self._process_watch_timer.setInterval(250)  # Check every 250ms for faster response
        self._process_watch_timer.timeout.connect(self._monitor_bot_process)
        self._auto_launch_timer: QtCore.QTimer | None = None
        self._child_startup_suppress_stop = None
        self._child_startup_suppress_thread = None
        self._child_startup_suppress_proc = None
        self._child_startup_suppress_hooks = {}
        self._launch_overlay: LaunchOverlay | None = None
        self._win32_topmost_prev: bool | None = None
        self._win32_topmost_timer: QtCore.QTimer | None = None
        self._win32_last_child_main_hwnd: int = 0
        self._child_ready_file: Path | None = None
        self._verbose_launch_logging = False
        self._verbose_launch_session_id = ""
        self._launch_mask_active = False
        self._launch_mask_prev_opacity: float | None = None
        self._launch_timed_out = False

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(40, 32, 40, 32)
        outer.setSpacing(24)

        title = QtWidgets.QLabel("Trading Bot Quick Start")
        title.setStyleSheet("font-size: 36px; font-weight: 700;")
        outer.addWidget(title)

        subtitle = QtWidgets.QLabel(
            "Launch the right workspace by choosing a programming language and market. "
            "You can change any of these choices later from Settings."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color: {MUTED_TEXT}; font-size: 15px;")
        outer.addWidget(subtitle)

        self.stack = QtWidgets.QStackedWidget()
        self.stack.addWidget(self._build_language_step())
        self.stack.addWidget(self._build_market_step())
        outer.addWidget(self.stack, stretch=1)

        nav_bar = QtWidgets.QHBoxLayout()
        nav_bar.addStretch()
        self.back_button = QtWidgets.QPushButton("Back")
        self.back_button.clicked.connect(self._go_back)
        self.back_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.back_button.setStyleSheet(self._button_style(outlined=True))
        nav_bar.addWidget(self.back_button)

        self.primary_button = LoadingButton("Next")
        self.primary_button.clicked.connect(self._on_primary_clicked)
        self.primary_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.primary_button.setStyleSheet(self._button_style())
        nav_bar.addWidget(self.primary_button)
        outer.addLayout(nav_bar)

        self.status_label = QtWidgets.QLabel("Python comes pre-selected. Click Next to choose your market.")
        self.status_label.setStyleSheet(f"color: {MUTED_TEXT}; font-size: 13px;")
        outer.addWidget(self.status_label)

        self._allow_language_auto_advance = False
        self._update_language_selection("python")
        self._allow_language_auto_advance = True
        QtCore.QTimer.singleShot(0, lambda: self.resize(1100, 720))
        QtCore.QTimer.singleShot(0, self._update_exchange_card_widths)
        self._update_nav_state()
        self._update_status_message()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
        try:
            self._stop_child_startup_window_suppression()
        except Exception:
            pass
        try:
            self._hide_launch_overlay()
        except Exception:
            pass
        try:
            self._set_launch_mask(False)
        except Exception:
            pass
        try:
            self._end_launch_focus_shield()
        except Exception:
            pass
        super().closeEvent(event)

    @staticmethod
    def _button_style(outlined: bool = False) -> str:
        if outlined:
            return (
                "QPushButton {"
                "border: 1px solid #2b3245; border-radius: 8px; padding: 10px 26px;"
                f"background-color: transparent; color: {TEXT_COLOR};"
                "font-size: 15px; font-weight: 600;}"
                "QPushButton:hover {border-color: #3b82f6; color: #93c5fd;}"
                "QPushButton:disabled {color: #4b5563; border-color: #1f2433;}"
            )
        return (
            "QPushButton {"
            "border: none; border-radius: 8px; padding: 12px 32px;"
            "background-color: #2563eb; color: white; font-size: 16px; font-weight: 600;}"
            "QPushButton:hover {background-color: #1d4ed8;}"
            "QPushButton:disabled {background-color: #1f2a44; color: #6b7280;}"
        )

    def _verbose_log(self, message: str) -> None:
        if not self._verbose_launch_logging:
            return
        session_id = self._verbose_launch_session_id or "unknown"
        _debug_log(f"[verbose:{session_id}] {message}")

    def _write_verbose_log_header(self, reason: str) -> None:
        session_id = self._verbose_launch_session_id or "unknown"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _debug_log(f"[verbose:{session_id}] session-start time={timestamp} reason={reason}")
        _debug_log(
            f"[verbose:{session_id}] starter pid={os.getpid()} exe={sys.executable} cwd={Path.cwd()} "
            f"platform={sys.platform} qt_pref={PREFERRED_QT_VERSION}"
        )
        _debug_log(
            f"[verbose:{session_id}] selection language={self.selected_language} "
            f"market={self.selected_market} exchange={self.selected_exchange}"
        )
        _debug_log(
            f"[verbose:{session_id}] log paths: starter={DEBUG_LOG_PATH} "
            f"window_parent={STARTER_CHILD_WINDOW_EVENTS_LOG_PATH} window_child={BINANCE_WINDOW_EVENTS_LOG_PATH}"
        )
        env_keys = [
            "BOT_DEBUG_WINDOW_EVENTS",
            "BOT_ENABLE_CBT_STARTUP_WINDOW_SUPPRESS",
            "BOT_NO_STARTUP_WINDOW_SUPPRESS",
            "BOT_NO_CBT_STARTUP_WINDOW_SUPPRESS",
            "BOT_NO_WINEVENT_STARTUP_WINDOW_SUPPRESS",
            "BOT_DISABLE_STARTUP_WINDOW_HOOKS",
            "BOT_DISABLE_APP_ICON",
            "BOT_ENABLE_NATIVE_ICON",
            "BOT_ENABLE_DELAYED_QT_ICON",
            "BOT_DELAYED_APP_ICON_MS",
            "BOT_NATIVE_ICON_DELAY_MS",
            "BOT_ICON_ENFORCE_ATTEMPTS",
            "BOT_ICON_ENFORCE_INTERVAL_MS",
            "BOT_TASKBAR_METADATA_DELAY_MS",
            "BOT_TASKBAR_ENSURE_MS",
            "BINANCE_BOT_ICON",
            "BYBIT_BOT_ICON",
            "OKX_BOT_ICON",
            "GATE_BOT_ICON",
            "BITGET_BOT_ICON",
            "MEXC_BOT_ICON",
            "KUCOIN_BOT_ICON",
            "BOT_STARTUP_WINDOW_SUPPRESS_DURATION_MS",
            "BOT_STARTUP_WINDOW_POLL_MS",
            "BOT_STARTUP_WINDOW_POLL_INTERVAL_MS",
            "BOT_STARTUP_WINDOW_POLL_FAST_MS",
            "BOT_STARTUP_WINDOW_POLL_FAST_INTERVAL_MS",
            "BOT_LAUNCH_OVERLAY_FULLSCREEN",
            "BOT_LAUNCH_OVERLAY_ALL_SCREENS",
            "BOT_LAUNCH_OVERLAY_BACKGROUND",
            "BOT_LAUNCH_OVERLAY_COVER_OWNER",
            "BOT_FORCE_SOFTWARE_OPENGL",
            "BOT_STARTER_TOPMOST_SHIELD_MS",
            "QTWEBENGINE_DISABLE_SANDBOX",
            "QTWEBENGINE_CHROMIUM_FLAGS",
            "QT_OPENGL",
            "QSG_RHI_BACKEND",
            "QT_QUICK_BACKEND",
            "PYTHONPATH",
        ]
        for key in env_keys:
            _debug_log(f"[verbose:{session_id}] env {key}={os.environ.get(key, '')!r}")
        header = f"\n=== verbose session {session_id} @ {timestamp} ({reason}) ===\n"
        for path in (STARTER_CHILD_WINDOW_EVENTS_LOG_PATH, BINANCE_WINDOW_EVENTS_LOG_PATH):
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with open(path, "a", encoding="utf-8", errors="ignore") as fh:
                    fh.write(header)
            except Exception:
                pass

    def _enable_verbose_launch_logging(self, reason: str) -> None:
        if self._verbose_launch_logging:
            return
        self._verbose_launch_logging = True
        self._verbose_launch_session_id = uuid4().hex[:8]
        os.environ["BOT_DEBUG_WINDOW_EVENTS"] = "1"
        session_id = self._verbose_launch_session_id
        _debug_log(f"[verbose:{session_id}] enabled (reason={reason})")
        self._write_verbose_log_header(reason)

    @staticmethod
    def _merge_chromium_flags(current: str, extra_flags: list[str]) -> str:
        parts = [part for part in current.split() if part]
        for flag in extra_flags:
            if flag not in parts:
                parts.append(flag)
        return " ".join(parts)

    def _set_launch_mask(self, active: bool) -> None:
        if sys.platform != "win32":
            return
        if self.selected_language != "python" or self.selected_exchange not in PYTHON_EXCHANGE_MAIN:
            return
        if active:
            if self._launch_mask_active:
                return
            self._launch_mask_active = True
            try:
                self._launch_mask_prev_opacity = float(self.windowOpacity())
            except Exception:
                self._launch_mask_prev_opacity = 1.0
            try:
                self.setWindowOpacity(0.0)
            except Exception:
                pass
            try:
                self.setEnabled(False)
            except Exception:
                pass
            self._verbose_log("launch mask enabled")
            return
        if not self._launch_mask_active:
            return
        prev = self._launch_mask_prev_opacity
        if prev is None:
            prev = 1.0
        try:
            self.setWindowOpacity(prev)
        except Exception:
            pass
        try:
            self.setEnabled(True)
        except Exception:
            pass
        self._launch_mask_active = False
        self._verbose_log("launch mask disabled")

    def _resolve_cpp_binance_executable(self, refresh: bool = False) -> Path | None:
        if not refresh and self._cpp_binance_executable and self._cpp_binance_executable.is_file():
            return self._cpp_binance_executable
        self._cpp_binance_executable = self._find_cpp_binance_executable()
        return self._cpp_binance_executable

    def _find_cpp_binance_executable(self) -> Path | None:
        candidate_names = {BINANCE_CPP_EXECUTABLE_BASENAME}
        allowed_suffixes = {""}
        if sys.platform == "win32":
            candidate_names.add(f"{BINANCE_CPP_EXECUTABLE_BASENAME}.exe")
            allowed_suffixes.add(".exe")

        search_roots = [
            BINANCE_CPP_PROJECT,
            BINANCE_CPP_PROJECT / "build",
            BINANCE_CPP_PROJECT / "Release",
            BINANCE_CPP_PROJECT / "Debug",
            BINANCE_CPP_PROJECT / "bin",
            BINANCE_CPP_PROJECT / "out",
            BINANCE_CPP_BUILD_ROOT,
            BINANCE_CPP_BUILD_ROOT / "Release",
            BINANCE_CPP_BUILD_ROOT / "Debug",
            BINANCE_CPP_BUILD_ROOT / "bin",
            BINANCE_CPP_BUILD_ROOT / "out",
        ]

        seen: set[Path] = set()
        # Fast path: direct file checks in the most common directories.
        for root in search_roots:
            if root is None or root in seen:
                continue
            seen.add(root)
            for name in candidate_names:
                candidate = root / name
                if candidate.is_file():
                    return candidate

        # Fallback: walk limited roots to discover generator-specific subfolders.
        for root in search_roots:
            if not root.is_dir():
                continue
            try:
                for path in root.rglob("*"):
                    if not path.is_file():
                        continue
                    suffix = path.suffix.lower()
                    if suffix not in allowed_suffixes:
                        continue
                    if path.name in candidate_names or path.stem == BINANCE_CPP_EXECUTABLE_BASENAME:
                        return path
            except (PermissionError, OSError):
                continue
        return None

    def _detect_mingw_toolchain(self, prefix_path: Path) -> tuple[str | None, Path | None, Path | None]:
        """
        Heuristic to locate a bundled MinGW toolchain when the Qt prefix lives under a mingw_* path.
        Returns (generator, make_path, cxx_path) or (None, None, None) if not found.
        """
        if "mingw" not in str(prefix_path).lower():
            return None, None, None
        search_roots = [prefix_path] + list(prefix_path.parents)[:5]
        seen: set[Path] = set()
        for root in search_roots:
            if root in seen or not root.exists():
                continue
            seen.add(root)
            try:
                for make_path in root.rglob("mingw32-make.exe"):
                    bin_dir = make_path.parent
                    cxx_path = bin_dir / "g++.exe"
                    if cxx_path.is_file():
                        return "MinGW Makefiles", make_path, cxx_path
            except (PermissionError, OSError):
                continue
        return None, None, None

    def _detect_msvc_generator(self, prefix_path: Path) -> tuple[str | None, str | None]:
        """
        If the Qt prefix comes from an MSVC kit, hint CMake to use the matching generator.
        """
        name = prefix_path.name.lower()
        if "msvc" not in name:
            return None, None
        return "Visual Studio 17 2022", "x64"

    @staticmethod
    def _qt_prefix_has_webengine(prefix_path: Path) -> bool:
        try:
            return (prefix_path.parent / "Qt6WebEngineWidgets").is_dir()
        except Exception:
            return False

    def _qt_prefix_from_cache(self, build_dir: Path) -> Path | None:
        cache_file = build_dir / "CMakeCache.txt"
        qt_dir = self._read_cache_value(cache_file, "Qt6_DIR")
        if qt_dir:
            try:
                qt_path = Path(qt_dir).resolve()
                if qt_path.exists():
                    return qt_path
            except Exception:
                return None
        return None

    @staticmethod
    def _read_cache_value(cache_file: Path, key: str) -> str | None:
        if not cache_file.is_file():
            return None
        needle = f"{key}:"
        try:
            for line in cache_file.read_text(errors="ignore").splitlines():
                if line.startswith(needle):
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        return parts[1].strip()
        except Exception:
            return None
        return None

    def _detect_cached_qt_prefix(self, build_dir: Path) -> Path | None:
        cache_file = build_dir / "CMakeCache.txt"
        qt_dir = self._read_cache_value(cache_file, "Qt6_DIR")
        if qt_dir:
            qt_path = Path(qt_dir)
            if qt_path.exists():
                return qt_path
        return None

    def _detect_default_qt_prefix(self) -> Path | None:
        candidates = [
            Path("C:/Qt"),
            Path.home() / "Qt",
        ]

        def iter_kits(base: Path) -> list[tuple[Path, bool, str]]:
            found: list[tuple[Path, bool, str]] = []
            for version_dir in sorted(base.glob("6.*"), reverse=True):
                version_str = version_dir.name
                for kit_dir in sorted(version_dir.iterdir(), reverse=True):
                    qt_cmake = kit_dir / "lib" / "cmake" / "Qt6"
                    if not qt_cmake.is_dir():
                        continue
                    has_webengine = (qt_cmake.parent / "Qt6WebEngineWidgets").is_dir()
                    found.append((qt_cmake, has_webengine, version_str))
            return found

        best: Path | None = None
        preferred_versions = [v for v in {PREFERRED_QT_VERSION, os.environ.get("STARTER_QT_VERSION")} if v]
        for base in candidates:
            if not base.exists():
                continue
            try:
                kits = iter_kits(base)
                if not kits:
                    continue
                # Prefer preferred_versions with WebEngine, then preferred_versions without,
                # then newest with WebEngine, then newest overall.
                for pref in preferred_versions:
                    for path, has_webengine, ver in kits:
                        if pref in ver and has_webengine:
                            return path
                for pref in preferred_versions:
                    for path, has_webengine, ver in kits:
                        if pref in ver:
                            return path
                for path, has_webengine, _ in kits:
                    if has_webengine:
                        return path
                if best is None and kits:
                    best = kits[0][0]
            except Exception:
                continue
        return best

    def _candidate_qt_prefixes(self) -> list[Path]:
        prefixes: list[Path] = []
        env_prefix = os.environ.get("QT_CMAKE_PREFIX_PATH") or os.environ.get("CMAKE_PREFIX_PATH")
        if env_prefix:
            for token in env_prefix.split(os.pathsep):
                token = token.strip()
                if token:
                    prefixes.append(Path(token))
        cached = self._detect_cached_qt_prefix(BINANCE_CPP_BUILD_ROOT)
        if cached:
            prefixes.append(cached)
        detected = self._detect_default_qt_prefix()
        if detected:
            prefixes.append(detected)
        # Deduplicate while preserving order
        seen: set[Path] = set()
        unique: list[Path] = []
        for p in prefixes:
            rp = p.resolve()
            if rp in seen:
                continue
            seen.add(rp)
            unique.append(rp)
        return unique

    def _discover_qt_bin_dirs(self) -> list[Path]:
        bin_dirs: list[Path] = []
        preferred_prefix = self._qt_prefix_from_cache(BINANCE_CPP_BUILD_ROOT)
        candidate_prefixes = [preferred_prefix] if preferred_prefix else []
        candidate_prefixes += self._candidate_qt_prefixes()

        for prefix in candidate_prefixes:
            if not prefix:
                continue
            for base in [prefix] + list(prefix.parents):
                candidate = base / "bin"
                if not candidate.is_dir():
                    continue
                if (candidate / "Qt6Core.dll").is_file() or (candidate / "Qt6Widgets.dll").is_file():
                    bin_dirs.append(candidate.resolve())
                    break
            if bin_dirs:
                break

        # Add the build output dir to pick up local DLLs if present
        build_bin = BINANCE_CPP_BUILD_ROOT / "bin"
        if build_bin.is_dir():
            bin_dirs.append(build_bin.resolve())
        seen: set[Path] = set()
        unique: list[Path] = []
        for b in bin_dirs:
            if b in seen:
                continue
            seen.add(b)
            unique.append(b)
        return unique

    def _reset_conflicting_cmake_cache(
        self, build_dir: Path, desired_generator: str | None, desired_qt_prefix: str | None
    ) -> None:
        cache_file = build_dir / "CMakeCache.txt"
        if not cache_file.exists():
            return
        cached_gen = self._read_cache_value(cache_file, "CMAKE_GENERATOR")
        cached_qt = self._read_cache_value(cache_file, "Qt6_DIR")
        desired_qt = Path(desired_qt_prefix).resolve() if desired_qt_prefix else None
        mismatch_gen = bool(cached_gen and desired_generator and cached_gen != desired_generator)
        mismatch_qt = False
        if cached_qt and desired_qt:
            try:
                mismatch_qt = Path(cached_qt).resolve() != desired_qt
            except Exception:
                mismatch_qt = True
        if mismatch_gen or mismatch_qt:
            _debug_log(
                f"CMake cache mismatch (gen: {cached_gen} vs {desired_generator}, "
                f"qt: {cached_qt} vs {desired_qt}). Resetting build dir."
            )
            try:
                shutil.rmtree(build_dir)
            except Exception as exc:
                _debug_log(f"Failed to clear build dir '{build_dir}': {exc}")

    def _ensure_cpp_binance_executable(self) -> tuple[Path | None, str | None]:
        exe_path = self._resolve_cpp_binance_executable(refresh=True)
        if exe_path and exe_path.is_file():
            return exe_path, None
        exe_path, error = self._build_cpp_binance_project()
        if exe_path and exe_path.is_file():
            return exe_path, None
        return None, error

    def _build_cpp_binance_project(self) -> tuple[Path | None, str | None]:
        if not BINANCE_CPP_PROJECT.is_dir():
            return None, "C++ Binance project directory is missing."
        if shutil.which("cmake") is None:
            return None, "CMake was not found in PATH. Install CMake and try again."
        build_dir = BINANCE_CPP_BUILD_ROOT
        try:
            build_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return None, f"Could not create build directory '{build_dir}': {exc}"

        prefix_env = os.environ.get("QT_CMAKE_PREFIX_PATH") or os.environ.get("CMAKE_PREFIX_PATH")

        if not prefix_env:
            cached_qt_prefix = self._detect_cached_qt_prefix(build_dir)
            auto_qt_prefix = self._detect_default_qt_prefix()

            def choose_prefix(cached: Path | None, auto: Path | None) -> Path | None:
                preferred_versions = [v for v in {PREFERRED_QT_VERSION, os.environ.get("STARTER_QT_VERSION")} if v]
                candidates = [p for p in (auto, cached) if p]
                # Prefer preferred_versions first
                for pref in preferred_versions:
                    for p in candidates:
                        if pref in str(p):
                            return p
                # Prefer WebEngine if available
                for p in candidates:
                    if self._qt_prefix_has_webengine(p):
                        return p
                return candidates[0] if candidates else None

            chosen = choose_prefix(cached_qt_prefix, auto_qt_prefix)
            if chosen:
                prefix_env = str(chosen)
                _debug_log(
                    f"Selected Qt prefix: {prefix_env} "
                    f"(webengine={'yes' if self._qt_prefix_has_webengine(chosen) else 'no'})"
                )

        # If user points to an MSVC kit but MSVC compiler is missing, drop it and fall back.
        if prefix_env and "msvc" in prefix_env.lower() and shutil.which("cl") is None:
            _debug_log(
                f"MSVC Qt kit detected ({prefix_env}) but MSVC compiler not found in PATH. "
                "Falling back to auto-detected Qt kit (likely MinGW)."
            )
            prefix_env = None

        generator_override = os.environ.get("CMAKE_GENERATOR")
        generator_platform: str | None = None
        make_override: Path | None = None
        cxx_override: Path | None = None
        if generator_override is None and prefix_env:
            gen, make_path, cxx_path = self._detect_mingw_toolchain(Path(prefix_env))
            if gen:
                generator_override = gen
                make_override = make_path
                cxx_override = cxx_path
                _debug_log(
                    f"Detected MinGW Qt toolchain; forcing generator '{gen}' "
                    f"(make={make_override}, cxx={cxx_override})"
                )
            else:
                gen, platform = self._detect_msvc_generator(Path(prefix_env))
                if gen and shutil.which("cl"):
                    generator_override = gen
                    generator_platform = platform
                    _debug_log(f"Detected MSVC Qt toolchain; using generator '{gen}' platform '{platform}'")
        elif prefix_env:
            gen, make_path, cxx_path = self._detect_mingw_toolchain(Path(prefix_env))
            if gen and "mingw" in gen.lower() and generator_override and "visual studio" in generator_override.lower():
                generator_override = gen
                make_override = make_path
                cxx_override = cxx_path
                _debug_log(
                    f"Overriding Visual Studio generator with MinGW because Qt prefix is MinGW: '{gen}' "
                    f"(make={make_override}, cxx={cxx_override})"
                )

        self._reset_conflicting_cmake_cache(build_dir, generator_override, prefix_env)
        build_dir.mkdir(parents=True, exist_ok=True)

        configure_cmd = ["cmake", "-S", str(BINANCE_CPP_PROJECT), "-B", str(build_dir)]
        if generator_override:
            configure_cmd.extend(["-G", generator_override])
        if generator_platform:
            configure_cmd.extend(["-A", generator_platform])
        if prefix_env:
            configure_cmd.append(f"-DCMAKE_PREFIX_PATH={prefix_env}")
        if make_override:
            configure_cmd.append(f"-DCMAKE_MAKE_PROGRAM={make_override}")
        if cxx_override:
            gcc_path = cxx_override.parent / "gcc.exe"
            configure_cmd.append(f"-DCMAKE_C_COMPILER={gcc_path}")
            configure_cmd.append(f"-DCMAKE_CXX_COMPILER={cxx_override}")
        single_config_generator = bool(generator_override and generator_override.lower().startswith("mingw"))
        if single_config_generator and not any(arg.startswith("-DCMAKE_BUILD_TYPE=") for arg in configure_cmd):
            configure_cmd.append("-DCMAKE_BUILD_TYPE=Release")

        ok, error = self._run_command_capture(configure_cmd)
        if not ok:
            return None, error

        build_cmd = ["cmake", "--build", str(build_dir)]
        build_configs = []
        if single_config_generator:
            build_configs = [None]
        elif sys.platform == "win32":
            preferred = os.environ.get("CMAKE_BUILD_CONFIG") or "Release"
            build_configs = [preferred, "Debug"] if preferred.lower() != "debug" else ["Debug", "Release"]
        else:
            build_configs = [None]

        ok = False
        error: str | None = None
        for config in build_configs:
            cmd = list(build_cmd)
            if config:
                cmd.extend(["--config", config])
            ok, error = self._run_command_capture(cmd)
            if ok:
                break
        if not ok:
            return None, error
        exe_path = self._resolve_cpp_binance_executable(refresh=True)
        if exe_path and exe_path.is_file():
            return exe_path, None
        return None, "Build finished but the Qt executable was not found. Check your CMake install paths."

    def _run_command_capture(self, command: list[str]) -> tuple[bool, str | None]:
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except FileNotFoundError:
            return False, f"Command not found: {command[0]}"
        except subprocess.CalledProcessError as exc:
            output = (exc.stdout or "") + (exc.stderr or "")
            snippet = output.strip() or f"{command[0]} exited with code {exc.returncode}"
            return False, snippet
        return True, None

    def _build_language_step(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setSpacing(24)

        heading = QtWidgets.QLabel("Choose your programming language")
        heading.setStyleSheet("font-size: 28px; font-weight: 700;")
        layout.addWidget(heading)

        sub = QtWidgets.QLabel("Pick which language this project should start with.")
        sub.setStyleSheet(f"color: {MUTED_TEXT}; font-size: 15px;")
        layout.addWidget(sub)

        cards = QtWidgets.QHBoxLayout()
        cards.setSpacing(18)
        layout.addLayout(cards)

        self.language_cards: dict[str, SelectableCard] = {}
        for opt in LANGUAGE_OPTIONS:
            card = SelectableCard(
                opt["key"],
                opt["title"],
                opt["subtitle"],
                opt["accent"],
                opt.get("badge"),
                disabled=opt.get("disabled", False),
            )
            card.setMinimumWidth(250)
            card.clicked.connect(self._update_language_selection)
            self.language_cards[opt["key"]] = card
            cards.addWidget(card)

        layout.addStretch()
        return page

    def _build_market_step(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setSpacing(24)

        heading = QtWidgets.QLabel("Choose your market")
        heading.setStyleSheet("font-size: 28px; font-weight: 700;")
        layout.addWidget(heading)

        sub = QtWidgets.QLabel("Pick where this bot should trade.")
        sub.setStyleSheet(f"color: {MUTED_TEXT}; font-size: 15px;")
        layout.addWidget(sub)

        self.market_cards: dict[str, SelectableCard] = {}
        market_row = QtWidgets.QHBoxLayout()
        market_row.setSpacing(18)
        layout.addLayout(market_row)
        for opt in MARKET_OPTIONS:
            card = SelectableCard(opt["key"], opt["title"], opt["subtitle"], opt["accent"])
            card.setMinimumWidth(320)
            card.clicked.connect(self._update_market_selection)
            self.market_cards[opt["key"]] = card
            market_row.addWidget(card)

        self.crypto_exchange_group = QtWidgets.QGroupBox("Crypto exchanges")
        self.crypto_exchange_group.setVisible(False)
        crypto_group_style = textwrap.dedent(
            f"""
            QGroupBox {{
                background-color: {PANEL_BG};
                border: 1px solid #202635;
                border-radius: 14px;
                margin-top: 12px;
                font-size: 16px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 14px;
                padding: 4px 8px;
                color: #cbd5f5;
            }}
            """
        ).strip()
        self.crypto_exchange_group.setStyleSheet(crypto_group_style)

        exch_layout = QtWidgets.QVBoxLayout(self.crypto_exchange_group)
        exch_layout.setContentsMargins(16, 20, 16, 16)
        exch_layout.setSpacing(14)

        hint = QtWidgets.QLabel("Pick an exchange to auto-create its workspace.")
        hint.setStyleSheet(f"color: {MUTED_TEXT};")
        exch_layout.addWidget(hint)

        self.exchange_cards: dict[str, SelectableCard] = {}
        self.exchange_row = QtWidgets.QHBoxLayout()
        self.exchange_row.setSpacing(18)
        exch_layout.addLayout(self.exchange_row)

        for opt in CRYPTO_EXCHANGES:
            card = SelectableCard(
                opt["key"],
                opt["title"],
                opt["subtitle"],
                opt["accent"],
                opt.get("badge"),
                disabled=opt.get("disabled", False),
            )
            card.setMinimumHeight(150)
            card.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Preferred)
            card.clicked.connect(self._update_exchange_selection)
            self.exchange_cards[opt["key"]] = card
            self.exchange_row.addWidget(card)

        layout.addWidget(self.crypto_exchange_group)

        self.forex_broker_group = QtWidgets.QGroupBox("Forex brokers")
        self.forex_broker_group.setVisible(False)
        self.forex_broker_group.setStyleSheet(crypto_group_style)

        forex_layout = QtWidgets.QVBoxLayout(self.forex_broker_group)
        forex_layout.setContentsMargins(16, 20, 16, 16)
        forex_layout.setSpacing(14)

        forex_hint = QtWidgets.QLabel("Forex integrations are in progress. Desktop workspaces will arrive soon.")
        forex_hint.setStyleSheet(f"color: {MUTED_TEXT};")
        forex_layout.addWidget(forex_hint)

        self.forex_cards: dict[str, SelectableCard] = {}
        self.forex_row = QtWidgets.QHBoxLayout()
        self.forex_row.setSpacing(18)
        forex_layout.addLayout(self.forex_row)
        for opt in FOREX_BROKERS:
            card = SelectableCard(
                opt["key"],
                opt["title"],
                opt["subtitle"],
                opt["accent"],
                opt.get("badge"),
                disabled=True,
            )
            card.setMinimumWidth(240)
            self.forex_cards[opt["key"]] = card
            self.forex_row.addWidget(card)

        layout.addWidget(self.forex_broker_group)
        layout.addStretch()
        return page

    def _update_language_selection(self, key: str) -> None:
        if key not in self.language_cards:
            return
        card_selected = self.language_cards.get(key)
        if card_selected is not None and card_selected.is_disabled():
            QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), "Coming soon")
            return
        allow_auto = getattr(self, "_allow_language_auto_advance", True)
        auto_advance = (self.stack.currentIndex() == 0) and allow_auto
        self.selected_language = key
        if key == "python" and self.selected_exchange in PYTHON_EXCHANGE_MAIN:
            self._enable_verbose_launch_logging("language-selected")
        self._verbose_log(f"language selection: {key} auto_advance={auto_advance}")
        for card_key, card in self.language_cards.items():
            card.setSelected(card_key == key)
        if auto_advance:
            self._show_market_page()
        else:
            self._update_status_message()
            self._update_nav_state()

    def _update_exchange_card_widths(self) -> None:
        try:
            cards = getattr(self, "exchange_cards", {})
            row = getattr(self, "exchange_row", None)
            group = getattr(self, "crypto_exchange_group", None)
            if cards and row is not None and group is not None:
                available = max(0, group.contentsRect().width())
                margins = row.contentsMargins()
                available -= margins.left() + margins.right()
                spacing = max(0, row.spacing())
                count = len(cards)
                if count:
                    width = max(320, (available - spacing * (count - 1)) / count)
                    for card in cards.values():
                        card.setFixedWidth(int(width))
            forex_cards = getattr(self, "forex_cards", {})
            forex_row = getattr(self, "forex_row", None)
            forex_group = getattr(self, "forex_broker_group", None)
            if forex_cards and forex_row is not None and forex_group is not None:
                available = max(0, forex_group.contentsRect().width())
                margins = forex_row.contentsMargins()
                available -= margins.left() + margins.right()
                spacing = max(0, forex_row.spacing())
                count = len(forex_cards)
                if count:
                    width = max(300, (available - spacing * (count - 1)) / count)
                    for card in forex_cards.values():
                        card.setFixedWidth(int(width))
        except Exception:
            pass

    def _update_market_selection(self, key: str) -> None:
        if key not in self.market_cards:
            return
        self.selected_market = key
        self._verbose_log(f"market selection: {key}")
        for card_key, card in self.market_cards.items():
            card.setSelected(card_key == key)
        self.crypto_exchange_group.setVisible(key == "crypto")
        if hasattr(self, "forex_broker_group"):
            self.forex_broker_group.setVisible(key == "forex")
        if key != "crypto":
            self.selected_exchange = None
            for card in self.exchange_cards.values():
                card.setSelected(False)
        if key != "forex" and hasattr(self, "forex_cards"):
            for card in self.forex_cards.values():
                card.setSelected(False)
        QtCore.QTimer.singleShot(0, self._update_exchange_card_widths)
        self._update_status_message()
        self._update_nav_state()

    def _update_exchange_selection(self, key: str) -> None:
        if key not in self.exchange_cards:
            return
        card = self.exchange_cards.get(key)
        if card is not None and card.is_disabled():
            QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), "Coming soon")
            return
        self.selected_exchange = key
        if self.selected_language == "python" and key in PYTHON_EXCHANGE_MAIN:
            self._enable_verbose_launch_logging("exchange-selected")
        self._verbose_log(f"exchange selection: {key}")
        for card_key, card in self.exchange_cards.items():
            card.setSelected(card_key == key)
        self._update_status_message()
        self._update_nav_state()
        if self._can_launch_selected():
            self._schedule_auto_launch()

    def _show_market_page(self) -> None:
        self.stack.setCurrentIndex(1)
        QtCore.QTimer.singleShot(0, self._update_exchange_card_widths)
        self._update_nav_state()
        self._update_status_message()

    def _go_back(self) -> None:
        if self.stack.currentIndex() == 1:
            # Clear market/exchange selections when returning to language step
            if self.selected_market is not None:
                for card in self.market_cards.values():
                    card.setSelected(False)
            self.selected_market = None
            if self.selected_exchange is not None:
                for card in self.exchange_cards.values():
                    card.setSelected(False)
            self.selected_exchange = None
            self.crypto_exchange_group.setVisible(False)
            if hasattr(self, "forex_cards"):
                for card in self.forex_cards.values():
                    card.setSelected(False)
            if hasattr(self, "forex_broker_group"):
                self.forex_broker_group.setVisible(False)
            # Also clear language highlight so the user must reselect
            self.selected_language = None
            for card in self.language_cards.values():
                card.setSelected(False)
            self.stack.setCurrentIndex(0)
            self._update_nav_state()
            self._update_status_message()

    def _on_primary_clicked(self) -> None:
        if self.stack.currentIndex() == 0:
            self._show_market_page()
            return
        can_launch = self._can_launch_selected()
        self._verbose_log(
            f"primary click: page={self.stack.currentIndex()} can_launch={can_launch} "
            f"language={self.selected_language} market={self.selected_market} exchange={self.selected_exchange}"
        )
        if can_launch and self.selected_language == "python" and self.selected_exchange in PYTHON_EXCHANGE_MAIN:
            self._enable_verbose_launch_logging("launch-clicked")
        if can_launch:
            self.launch_selected_bot()
        else:
            self._update_status_message()

    def _update_nav_state(self) -> None:
        page_idx = self.stack.currentIndex()
        self.back_button.setVisible(page_idx > 0)
        show_spinner = False
        if page_idx == 0:
            self.primary_button.setText("Next")
            self.primary_button.setEnabled(self.selected_language is not None)
        else:
            if self._is_launching:
                if self._bot_ready:
                    self.primary_button.setText("Bot running (close to relaunch)")
                    self.primary_button.setEnabled(False)
                elif self._launch_timed_out:
                    self.primary_button.setText("Launch Selected Bot")
                    self.primary_button.setEnabled(self._can_launch_selected())
                else:
                    self.primary_button.setText("Bot is starting...")
                    show_spinner = True
                    self.primary_button.setEnabled(False)
            else:
                self.primary_button.setText("Launch Selected Bot")
                self.primary_button.setEnabled(self._can_launch_selected())
        try:
            if hasattr(self.primary_button, "set_loading"):
                self.primary_button.set_loading(show_spinner)
        except Exception:
            pass
        if not (self._is_launching and not self._bot_ready and not self._launch_timed_out):
            try:
                self._hide_launch_overlay()
            except Exception:
                pass

    def _set_launch_in_progress(self, launching: bool) -> None:
        self._is_launching = launching
        if launching:
            self._launch_timed_out = False
        else:
            self._bot_ready = False
            self._launch_timed_out = False
            try:
                self._end_launch_focus_shield()
            except Exception:
                pass
        self._update_nav_state()

    def _mark_bot_ready(self) -> None:
        if self._active_bot_process and self._active_bot_process.poll() is None:
            self._verbose_log("bot marked ready")
            self._launch_timed_out = False
            self._bot_ready = True
            message = self._running_ready_message or "Selected bot is running. Close it to relaunch."
            self.status_label.setText(message)
            try:
                self._hide_launch_overlay()
            except Exception:
                pass
            try:
                self._end_launch_focus_shield()
            except Exception:
                pass
            try:
                self._focus_child_main_window()
            except Exception:
                pass
            self._update_nav_state()

    def _handle_launch_timeout(self) -> None:
        if not self._is_launching or self._bot_ready:
            return
        self._verbose_log("launch timeout reached")
        self._launch_timed_out = True
        exchange_label = PYTHON_EXCHANGE_LABELS.get(self.selected_exchange, "Selected bot")
        self.status_label.setText(
            f"{exchange_label} is taking longer than expected to start. "
            "If the window opened, switch to it; otherwise close it and try again."
        )
        try:
            self._hide_launch_overlay()
        except Exception:
            pass
        try:
            self._end_launch_focus_shield()
        except Exception:
            pass
        self._update_nav_state()

    def _launch_overlay_options(self) -> dict[str, object]:
        if sys.platform != "win32":
            return {}
        if self.selected_language != "python" or self.selected_exchange not in PYTHON_EXCHANGE_MAIN:
            return {}
        options: dict[str, object] = {}
        fullscreen_env = os.environ.get("BOT_LAUNCH_OVERLAY_FULLSCREEN")
        if fullscreen_env is not None:
            options["fullscreen"] = str(fullscreen_env).strip().lower() in {"1", "true", "yes", "on"}
        cover_env = os.environ.get("BOT_LAUNCH_OVERLAY_COVER_OWNER")
        if cover_env is not None:
            options["cover_owner"] = str(cover_env).strip().lower() in {"1", "true", "yes", "on"}
        if options.get("fullscreen"):
            if os.environ.get("BOT_LAUNCH_OVERLAY_ALL_SCREENS") is None:
                options["all_screens"] = True
            if os.environ.get("BOT_LAUNCH_OVERLAY_BACKGROUND") is None:
                options["background_mode"] = "solid"
        if options:
            self._verbose_log(
                "launch overlay options: "
                f"fullscreen={options.get('fullscreen')} "
                f"cover_owner={options.get('cover_owner')} "
                f"all_screens={options.get('all_screens')} "
                f"background={options.get('background_mode')}"
            )
        return options

    def _show_launch_overlay(self, message: str) -> None:
        if sys.platform != "win32":
            self._verbose_log("launch overlay skipped: non-win32")
            return
        if str(os.environ.get("BOT_NO_LAUNCH_OVERLAY", "")).strip().lower() in {"1", "true", "yes", "on"}:
            self._verbose_log("launch overlay skipped: BOT_NO_LAUNCH_OVERLAY")
            return
        self._verbose_log(f"launch overlay show: {message}")
        try:
            if self._launch_overlay is None:
                overlay_kwargs = self._launch_overlay_options()
                fullscreen_env = str(os.environ.get("BOT_LAUNCH_OVERLAY_FULLSCREEN", "")).strip().lower() in {
                    "1",
                    "true",
                    "yes",
                    "on",
                }
                fullscreen_requested = bool(overlay_kwargs.get("fullscreen")) or fullscreen_env
                cover_requested = bool(overlay_kwargs.get("cover_owner"))
                overlay_parent = self
                if fullscreen_requested or cover_requested:
                    overlay_parent = None
                overlay_kwargs["owner_window"] = self
                overlay_kwargs["parent_window"] = overlay_parent
                if fullscreen_requested:
                    self._set_launch_mask(True)
                self._launch_overlay = LaunchOverlay(
                    str(message),
                    **overlay_kwargs,
                )
            else:
                self._launch_overlay.set_message(str(message))
            self._launch_overlay.show()
            self._launch_overlay.raise_()
            QtWidgets.QApplication.processEvents()
        except Exception:
            return

    def _hide_launch_overlay(self) -> None:
        overlay = getattr(self, "_launch_overlay", None)
        if overlay is None:
            return
        self._verbose_log("launch overlay hide")
        self._set_launch_mask(False)
        try:
            overlay.hide()
        except Exception:
            pass
        try:
            overlay.deleteLater()
        except Exception:
            pass
        self._launch_overlay = None

    def _win32_is_topmost(self) -> bool:
        if sys.platform != "win32":
            return False
        try:
            import ctypes
        except Exception:
            return False
        try:
            user32 = ctypes.windll.user32
            hwnd = int(self.winId())
            if not hwnd:
                return False
            GWL_EXSTYLE = -20
            WS_EX_TOPMOST = 0x00000008
            get_exstyle = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
            ex_style = int(get_exstyle(hwnd, GWL_EXSTYLE))
            return bool(ex_style & WS_EX_TOPMOST)
        except Exception:
            return False

    def _win32_set_topmost(self, enabled: bool) -> None:
        if sys.platform != "win32":
            return
        try:
            import ctypes
            import ctypes.wintypes as wintypes
        except Exception:
            return
        try:
            user32 = ctypes.windll.user32
            hwnd = wintypes.HWND(int(self.winId()))
            if not hwnd:
                return
            HWND_TOPMOST = wintypes.HWND(-1)
            HWND_NOTOPMOST = wintypes.HWND(-2)
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOACTIVATE = 0x0010
            user32.SetWindowPos(
                hwnd,
                HWND_TOPMOST if enabled else HWND_NOTOPMOST,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
            )
        except Exception:
            return

    def _begin_launch_focus_shield(self) -> None:
        if sys.platform != "win32":
            self._verbose_log("focus shield skipped: non-win32")
            return
        if str(os.environ.get("BOT_NO_STARTER_TOPMOST_SHIELD", "")).strip().lower() in {"1", "true", "yes", "on"}:
            self._verbose_log("focus shield skipped: BOT_NO_STARTER_TOPMOST_SHIELD")
            return
        if self._win32_topmost_timer is not None:
            try:
                self._win32_topmost_timer.stop()
            except Exception:
                pass
            try:
                self._win32_topmost_timer.deleteLater()
            except Exception:
                pass
            self._win32_topmost_timer = None
        try:
            self._win32_topmost_prev = bool(self._win32_is_topmost())
        except Exception:
            self._win32_topmost_prev = False
        try:
            self._win32_set_topmost(True)
        except Exception:
            pass
        try:
            shield_ms = int(os.environ.get("BOT_STARTER_TOPMOST_SHIELD_MS") or 2500)
        except Exception:
            shield_ms = 2500
        shield_ms = max(250, min(shield_ms, 15000))
        self._verbose_log(f"focus shield enabled: duration_ms={shield_ms}")
        timer = QtCore.QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(shield_ms)
        timer.timeout.connect(self._end_launch_focus_shield)
        timer.start()
        self._win32_topmost_timer = timer

    def _end_launch_focus_shield(self) -> None:
        if sys.platform != "win32":
            return
        timer = getattr(self, "_win32_topmost_timer", None)
        if timer is not None:
            try:
                timer.stop()
            except Exception:
                pass
            try:
                timer.deleteLater()
            except Exception:
                pass
            self._win32_topmost_timer = None
        if bool(getattr(self, "_win32_topmost_prev", False)):
            return
        self._verbose_log("focus shield ended")
        try:
            self._win32_set_topmost(False)
        except Exception:
            return

    def _focus_child_main_window(self) -> None:
        if sys.platform != "win32":
            self._verbose_log("focus child skipped: non-win32")
            return
        proc = getattr(self, "_active_bot_process", None)
        if proc is None or getattr(proc, "poll", lambda: 0)() is not None:
            self._verbose_log("focus child skipped: no active process")
            return
        try:
            pid_val = int(proc.pid)
        except Exception:
            pid_val = 0
        try:
            self._is_child_main_window_visible(pid_val)
        except Exception:
            pass
        hwnd_val = int(getattr(self, "_win32_last_child_main_hwnd", 0) or 0)
        if not hwnd_val:
            self._verbose_log(f"focus child skipped: no main hwnd pid={pid_val}")
            return
        self._verbose_log(f"focus child window: pid={pid_val} hwnd={hwnd_val}")
        try:
            import ctypes
            import ctypes.wintypes as wintypes
        except Exception:
            return
        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            hwnd = wintypes.HWND(hwnd_val)
            SW_RESTORE = 9
            SW_SHOW = 5
            try:
                if user32.IsIconic(hwnd):
                    if getattr(user32, "ShowWindowAsync", None):
                        user32.ShowWindowAsync(hwnd, SW_RESTORE)
                    else:
                        user32.ShowWindow(hwnd, SW_RESTORE)
                else:
                    if getattr(user32, "ShowWindowAsync", None):
                        user32.ShowWindowAsync(hwnd, SW_SHOW)
                    else:
                        user32.ShowWindow(hwnd, SW_SHOW)
            except Exception:
                pass

            try:
                fg_hwnd = user32.GetForegroundWindow()
                fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None) if fg_hwnd else 0
                target_tid = user32.GetWindowThreadProcessId(hwnd, None)
                current_tid = kernel32.GetCurrentThreadId()
                attached_fg = False
                attached_target = False
                try:
                    if fg_tid:
                        user32.AttachThreadInput(current_tid, fg_tid, True)
                        attached_fg = True
                    if target_tid:
                        user32.AttachThreadInput(current_tid, target_tid, True)
                        attached_target = True
                    user32.SetForegroundWindow(hwnd)
                    user32.BringWindowToTop(hwnd)
                finally:
                    try:
                        if attached_target and target_tid:
                            user32.AttachThreadInput(current_tid, target_tid, False)
                    except Exception:
                        pass
                    try:
                        if attached_fg and fg_tid:
                            user32.AttachThreadInput(current_tid, fg_tid, False)
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                HWND_TOP = wintypes.HWND(0)
                SWP_NOMOVE = 0x0002
                SWP_NOSIZE = 0x0001
                SWP_SHOWWINDOW = 0x0040
                user32.SetWindowPos(hwnd, HWND_TOP, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
            except Exception:
                pass
        except Exception:
            return

    def _is_child_main_window_visible(self, pid: int) -> bool:
        if sys.platform != "win32" or not pid:
            return False
        detector = getattr(self, "_win32_main_window_detector", None)
        if detector is None:
            try:
                import ctypes
                import ctypes.wintypes as wintypes
                import time
            except Exception:
                setattr(self, "_win32_main_window_detector", False)
                return False

            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            try:
                user32.EnumWindows.argtypes = [EnumWindowsProc, wintypes.LPARAM]
                user32.EnumWindows.restype = wintypes.BOOL
                user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
                user32.GetWindowThreadProcessId.restype = wintypes.DWORD
                user32.GetForegroundWindow.argtypes = []
                user32.GetForegroundWindow.restype = wintypes.HWND
                user32.IsWindowVisible.argtypes = [wintypes.HWND]
                user32.IsWindowVisible.restype = wintypes.BOOL
                user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
                user32.GetWindowRect.restype = wintypes.BOOL
                user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
                user32.GetClassNameW.restype = ctypes.c_int
                user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
                user32.GetWindowTextW.restype = ctypes.c_int
            except Exception:
                pass

            # Cache descendant PID lookups briefly so the timer-based polling is cheap.
            pid_tree_cache: dict[int, tuple[float, set[int]]] = {}

            def _descendant_pids(root_pid: int) -> set[int]:
                now = time.monotonic()
                cached = pid_tree_cache.get(int(root_pid))
                if cached and (now - cached[0]) < 0.75:
                    return set(cached[1])

                pids: set[int] = {int(root_pid)}
                try:
                    TH32CS_SNAPPROCESS = 0x00000002
                    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
                    if snapshot in (0, ctypes.c_void_p(-1).value):
                        pid_tree_cache[int(root_pid)] = (now, pids)
                        return set(pids)

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
                            ("szExeFile", wintypes.WCHAR * 260),
                        ]

                    entry = PROCESSENTRY32()
                    entry.dwSize = ctypes.sizeof(entry)

                    parent_to_children: dict[int, list[int]] = {}
                    try:
                        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
                            return set(pids)
                        while True:
                            child_pid = int(entry.th32ProcessID)
                            parent_pid = int(entry.th32ParentProcessID)
                            if child_pid > 0 and parent_pid > 0:
                                parent_to_children.setdefault(parent_pid, []).append(child_pid)
                            if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                                break
                    finally:
                        try:
                            kernel32.CloseHandle(snapshot)
                        except Exception:
                            pass

                    queue = [int(root_pid)]
                    while queue:
                        current = queue.pop()
                        for child in parent_to_children.get(int(current), []):
                            if child not in pids:
                                pids.add(int(child))
                                queue.append(int(child))
                                if len(pids) >= 64:
                                    break
                        if len(pids) >= 64:
                            break
                except Exception:
                    pids = {int(root_pid)}

                pid_tree_cache[int(root_pid)] = (now, set(pids))
                return set(pids)

            def _window_text(hwnd_obj) -> str:  # noqa: ANN001
                try:
                    buf = ctypes.create_unicode_buffer(512)
                    user32.GetWindowTextW(hwnd_obj, buf, 512)
                    return str(buf.value or "")
                except Exception:
                    return ""

            def _class_name(hwnd_obj) -> str:  # noqa: ANN001
                try:
                    buf = ctypes.create_unicode_buffer(256)
                    user32.GetClassNameW(hwnd_obj, buf, 256)
                    return str(buf.value or "")
                except Exception:
                    return ""

            def _looks_like_main_window(hwnd_obj) -> bool:  # noqa: ANN001
                try:
                    if not user32.IsWindowVisible(hwnd_obj):
                        return False
                    rect = wintypes.RECT()
                    if not user32.GetWindowRect(hwnd_obj, ctypes.byref(rect)):
                        return False
                    width = int(rect.right - rect.left)
                    height = int(rect.bottom - rect.top)
                    if width <= 0 or height <= 0:
                        return False

                    cls = _class_name(hwnd_obj)
                    if cls.startswith("_q_") or cls.startswith("QEventDispatcherWin32_Internal_Widget"):
                        return False
                    if cls in {"Intermediate D3D Window", "ConsoleWindowClass", "PseudoConsoleWindow"}:
                        return False
                    if cls.startswith("Chrome_WidgetWin_"):
                        return False

                    if width >= 500 and height >= 300:
                        return True

                    title = _window_text(hwnd_obj).strip()
                    if title and width >= 350 and height >= 200:
                        return True
                except Exception:
                    return False
                return False

            def _detect(target_pid: int) -> bool:
                pid_family = _descendant_pids(int(target_pid))

                # Fast-path: if the foreground window belongs to the launched process family,
                # treat it as ready even if EnumWindows misses it for any reason.
                try:
                    fg_hwnd = user32.GetForegroundWindow()
                    if fg_hwnd:
                        out_pid = wintypes.DWORD()
                        user32.GetWindowThreadProcessId(fg_hwnd, ctypes.byref(out_pid))
                        if int(out_pid.value) in pid_family and _looks_like_main_window(fg_hwnd):
                            try:
                                self._win32_last_child_main_hwnd = int(fg_hwnd)
                            except Exception:
                                pass
                            return True
                except Exception:
                    pass

                found = False

                def _enum_cb(hwnd_obj, _lparam):  # noqa: ANN001
                    nonlocal found
                    try:
                        out_pid = wintypes.DWORD()
                        user32.GetWindowThreadProcessId(hwnd_obj, ctypes.byref(out_pid))
                        if int(out_pid.value) not in pid_family:
                            return True
                        if _looks_like_main_window(hwnd_obj):
                            found = True
                            try:
                                self._win32_last_child_main_hwnd = int(hwnd_obj)
                            except Exception:
                                pass
                            return False
                    except Exception:
                        return True
                    return True

                cb = EnumWindowsProc(_enum_cb)
                try:
                    user32.EnumWindows(cb, 0)
                except Exception:
                    return False
                return found

            detector = _detect
            setattr(self, "_win32_main_window_detector", detector)

        if detector is False:
            return False
        try:
            return bool(detector(int(pid)))
        except Exception:
            return False

    def _monitor_bot_process(self) -> None:
        if not self._active_bot_process:
            self._process_watch_timer.stop()
            return
        if self._active_bot_process.poll() is not None:
            try:
                exit_code = int(self._active_bot_process.returncode)
            except Exception:
                exit_code = -1
            self._verbose_log(f"process exited: code={exit_code}")
            message = self._closed_message or "Selected bot closed. Launch it again anytime."
            try:
                self._stop_child_startup_window_suppression()
            except Exception:
                pass
            try:
                self._hide_launch_overlay()
            except Exception:
                pass
            self._reset_launch_tracking()
            self.status_label.setText(message)
            return
        if self._is_launching and not self._bot_ready:
            ready_file = getattr(self, "_child_ready_file", None)
            if ready_file is not None:
                try:
                    if ready_file.is_file():
                        try:
                            self._launch_status_timer.stop()
                        except Exception:
                            pass
                        self._verbose_log(f"ready file detected: {ready_file}")
                        self._mark_bot_ready()
                        return
                except Exception:
                    pass
            try:
                pid_val = int(self._active_bot_process.pid)
            except Exception:
                pid_val = 0
            if pid_val and self._is_child_main_window_visible(pid_val):
                try:
                    self._launch_status_timer.stop()
                except Exception:
                    pass
                self._verbose_log(f"main window detected: pid={pid_val}")
                self._mark_bot_ready()

    def _start_child_startup_window_suppression(self, root_pid: int) -> None:
        """Hide transient startup windows created by the launched bot (Windows only)."""
        if sys.platform != "win32" or not root_pid:
            self._verbose_log("child window suppression skipped: non-win32 or missing pid")
            return
        if str(os.environ.get("BOT_NO_STARTER_CHILD_WINDOW_SUPPRESS", "")).strip().lower() in {"1", "true", "yes", "on"}:
            self._verbose_log("child window suppression skipped: BOT_NO_STARTER_CHILD_WINDOW_SUPPRESS")
            return
        try:
            self._stop_child_startup_window_suppression()
        except Exception:
            pass
        try:
            import ctypes
            import ctypes.wintypes as wintypes
            import threading
            import time
        except Exception:
            return

        try:
            duration_ms = int(os.environ.get("BOT_STARTUP_WINDOW_SUPPRESS_DURATION_MS") or 12000)
        except Exception:
            duration_ms = 12000
        duration_ms = max(1000, min(duration_ms, 20000))

        try:
            poll_ms = int(os.environ.get("BOT_STARTUP_WINDOW_POLL_MS") or duration_ms)
        except Exception:
            poll_ms = duration_ms
        poll_ms = max(200, min(poll_ms, duration_ms))
        try:
            interval_ms = int(os.environ.get("BOT_STARTUP_WINDOW_POLL_INTERVAL_MS") or 30)
        except Exception:
            interval_ms = 30
        interval_ms = max(20, min(interval_ms, 200))
        try:
            fast_ms = int(os.environ.get("BOT_STARTUP_WINDOW_POLL_FAST_MS") or 800)
        except Exception:
            fast_ms = 800
        fast_ms = max(0, min(fast_ms, poll_ms))
        try:
            fast_interval_ms = int(os.environ.get("BOT_STARTUP_WINDOW_POLL_FAST_INTERVAL_MS") or 10)
        except Exception:
            fast_interval_ms = 10
        fast_interval_ms = max(10, min(fast_interval_ms, interval_ms))

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        try:
            user32.SetWinEventHook.argtypes = [
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.HMODULE,
                ctypes.c_void_p,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.DWORD,
            ]
            user32.SetWinEventHook.restype = wintypes.HANDLE
            user32.UnhookWinEvent.argtypes = [wintypes.HANDLE]
            user32.UnhookWinEvent.restype = wintypes.BOOL
        except Exception:
            pass

        EVENT_OBJECT_CREATE = 0x8000
        EVENT_OBJECT_SHOW = 0x8002
        WINEVENT_OUTOFCONTEXT = 0x0000
        OBJID_WINDOW = 0
        SW_HIDE = 0
        debug_window_events = str(os.environ.get("BOT_DEBUG_WINDOW_EVENTS", "")).strip().lower() in {"1", "true", "yes", "on"}
        debug_log_path = STARTER_CHILD_WINDOW_EVENTS_LOG_PATH

        self._verbose_log(
            "child window suppression config: "
            f"root_pid={root_pid} duration_ms={duration_ms} poll_ms={poll_ms} "
            f"interval_ms={interval_ms} fast_ms={fast_ms} fast_interval_ms={fast_interval_ms}"
        )

        def _get_hwnd_pid(hwnd_obj) -> int:  # noqa: ANN001
            try:
                out_pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd_obj, ctypes.byref(out_pid))
                return int(out_pid.value)
            except Exception:
                return 0

        def _log_window(hwnd_obj, reason: str) -> None:  # noqa: ANN001
            if not debug_window_events:
                return
            try:
                class_buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd_obj, class_buf, 256)
                try:
                    vis = int(bool(user32.IsWindowVisible(hwnd_obj)))
                except Exception:
                    vis = 0
                try:
                    get_style = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
                    style_val = int(get_style(hwnd_obj, -16))
                except Exception:
                    style_val = 0
                try:
                    get_exstyle = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
                    exstyle_val = int(get_exstyle(hwnd_obj, -20))
                except Exception:
                    exstyle_val = 0
                rect = wintypes.RECT()
                user32.GetWindowRect(hwnd_obj, ctypes.byref(rect))
                width = int(rect.right - rect.left)
                height = int(rect.bottom - rect.top)
                pid_val = _get_hwnd_pid(hwnd_obj)
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                with open(debug_log_path, "a", encoding="utf-8", errors="ignore") as fh:
                    fh.write(
                        f"[{timestamp}] {reason} hwnd={int(hwnd_obj)} pid={pid_val} "
                        f"class={class_buf.value!r} size={width}x{height} "
                        f"vis={vis} style=0x{style_val:08X} exstyle=0x{exstyle_val:08X}\n"
                    )
            except Exception:
                return

        def _enum_descendant_pids(root: int) -> set[int]:
            pids: set[int] = {int(root)}
            try:
                TH32CS_SNAPPROCESS = 0x00000002
                snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
                if snapshot in (0, ctypes.c_void_p(-1).value):
                    return pids

                class PROCESSENTRY32(ctypes.Structure):
                    _fields_ = [
                        ("dwSize", wintypes.DWORD),
                        ("cntUsage", wintypes.DWORD),
                        ("th32ProcessID", wintypes.DWORD),
                        ("th32DefaultHeapID", ctypes.c_void_p),
                        ("th32ModuleID", wintypes.DWORD),
                        ("cntThreads", wintypes.DWORD),
                        ("th32ParentProcessID", wintypes.DWORD),
                        ("pcPriClassBase", wintypes.LONG),
                        ("dwFlags", wintypes.DWORD),
                        ("szExeFile", wintypes.WCHAR * 260),
                    ]

                entry = PROCESSENTRY32()
                entry.dwSize = ctypes.sizeof(entry)
                parent_to_children: dict[int, list[int]] = {}
                try:
                    if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
                        return pids
                    while True:
                        pid_val = int(entry.th32ProcessID)
                        parent_val = int(entry.th32ParentProcessID)
                        parent_to_children.setdefault(parent_val, []).append(pid_val)
                        if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                            break
                finally:
                    try:
                        kernel32.CloseHandle(snapshot)
                    except Exception:
                        pass
                queue = [int(root)]
                while queue:
                    current = queue.pop()
                    for child in parent_to_children.get(current, []):
                        if child not in pids:
                            pids.add(child)
                            queue.append(child)
            except Exception:
                return pids
            return pids

        def _is_transient_window(hwnd_obj) -> bool:  # noqa: ANN001
            try:
                rect = wintypes.RECT()
                if not user32.GetWindowRect(hwnd_obj, ctypes.byref(rect)):
                    return False
                width = int(rect.right - rect.left)
                height = int(rect.bottom - rect.top)
                if width <= 0 or height <= 0:
                    return False
                class_buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd_obj, class_buf, 256)
                class_name = (class_buf.value or "").strip()
                title_buf = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(hwnd_obj, title_buf, 256)
                title = (title_buf.value or "").strip()
                if class_name in {"Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Progman", "WorkerW"}:
                    return False
                # Skip child windows early.
                try:
                    GWL_STYLE = -16
                    WS_CHILD = 0x40000000
                    get_style = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
                    style = int(get_style(hwnd_obj, GWL_STYLE))
                    if style & WS_CHILD:
                        return False
                except Exception:
                    pass

                if class_name.startswith("Qt") and any(
                    class_name.endswith(suffix)
                    for suffix in (
                        "PowerDummyWindow",
                        "ClipboardView",
                        "ScreenChangeObserverWindow",
                        "ThemeChangeObserverWindow",
                    )
                ):
                    return True
                if "QWindowPopup" in class_name or "QWindowToolTip" in class_name:
                    return False
                if class_name in {"ComboLBox", "#32768"}:
                    return False
                if class_name in {"ConsoleWindowClass", "PseudoConsoleWindow"}:
                    return True
                if class_name.startswith("_q_"):
                    return height <= 260 and width <= 3200
                if class_name == "Intermediate D3D Window":
                    return height <= 500 and width <= 4000
                if class_name.startswith("Chrome_WidgetWin_"):
                    return height <= 400 and width <= 4000
                try:
                    GW_OWNER = 4
                    owner = user32.GetWindow(hwnd_obj, GW_OWNER)
                    if owner:
                        return False
                except Exception:
                    pass
                if width >= 500 and height >= 300:
                    return False

                # Only treat truly tiny top-level windows as transient.
                return height <= 120 and width <= 4000
            except Exception:
                return False

        def _hide_hwnd(hwnd_obj) -> None:  # noqa: ANN001
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

        WinEventProc = ctypes.WINFUNCTYPE(
            None,
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.HWND,
            wintypes.LONG,
            wintypes.LONG,
            wintypes.DWORD,
            wintypes.DWORD,
        )

        tracked_pids = {int(root_pid)}
        tracked_lock = threading.Lock()
        hooks: dict[int, int] = {}
        pid_snapshot = {"ts": 0.0, "pids": set(tracked_pids)}
        related_pids: set[int] = set(tracked_pids)
        path_cache: dict[int, tuple[float, str]] = {}

        python_exe = Path(sys.executable).resolve()
        venv_root = python_exe.parent.parent if python_exe.parent.name.lower() in {"scripts", "bin"} else python_exe.parent
        allowed_roots = [
            str(python_exe.parent.resolve()),
            str(venv_root.resolve()),
            str(REPO_ROOT.resolve()),
        ]
        allowed_roots_lower = [root.lower() for root in allowed_roots if root]

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        try:
            kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel32.OpenProcess.restype = wintypes.HANDLE
            kernel32.QueryFullProcessImageNameW.argtypes = [
                wintypes.HANDLE,
                wintypes.DWORD,
                wintypes.LPWSTR,
                ctypes.POINTER(wintypes.DWORD),
            ]
            kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.restype = wintypes.BOOL
        except Exception:
            pass

        def _get_process_path(pid_val: int) -> str:
            if pid_val <= 0:
                return ""
            now = time.monotonic()
            cached = path_cache.get(pid_val)
            if cached and (now - cached[0]) < 1.0:
                return cached[1]
            handle = None
            try:
                handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid_val))
                if not handle:
                    return ""
                buf_len = wintypes.DWORD(260)
                buf = ctypes.create_unicode_buffer(buf_len.value)
                if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(buf_len)):
                    path = str(buf.value or "")
                else:
                    path = ""
            except Exception:
                path = ""
            finally:
                if handle:
                    try:
                        kernel32.CloseHandle(handle)
                    except Exception:
                        pass
            if path:
                path_cache[pid_val] = (now, path)
            return path

        def _refresh_descendants(force: bool = False) -> set[int]:
            now = time.monotonic()
            if not force and (now - float(pid_snapshot["ts"])) < 0.2:
                return set(pid_snapshot["pids"])
            try:
                pid_snapshot["pids"] = _enum_descendant_pids(int(root_pid))
                pid_snapshot["ts"] = now
            except Exception:
                pass
            return set(pid_snapshot["pids"])

        def _pid_is_related(pid_val: int) -> bool:
            if not pid_val:
                return False
            with tracked_lock:
                if pid_val in tracked_pids:
                    return True
                if pid_val in related_pids:
                    return True
            if pid_val not in _refresh_descendants():
                exe_path = _get_process_path(pid_val)
                if not exe_path:
                    return False
                exe_lower = exe_path.lower()
                if not any(root in exe_lower for root in allowed_roots_lower):
                    return False
                related_pids.add(pid_val)
                return True
            return True

        def _maybe_track_pid(pid_val: int) -> bool:
            if not _pid_is_related(pid_val):
                return False
            with tracked_lock:
                if pid_val not in tracked_pids:
                    tracked_pids.add(pid_val)
                    _install_hook_for_pid(pid_val)
            return True

        def _maybe_hide(hwnd_obj) -> None:  # noqa: ANN001
            if not hwnd_obj:
                return
            pid_val = _get_hwnd_pid(hwnd_obj)
            try:
                is_visible = bool(user32.IsWindowVisible(hwnd_obj))
            except Exception:
                is_visible = False
            if not _is_transient_window(hwnd_obj):
                return
            if not _maybe_track_pid(pid_val):
                return
            if is_visible:
                _log_window(hwnd_obj, "starter-hide-startup")
            else:
                _log_window(hwnd_obj, "starter-prehide-startup")
            _hide_hwnd(hwnd_obj)

        def _win_event_proc(_hook, _event, hwnd_obj, id_object, _id_child, _thread, _time):  # noqa: ANN001
            try:
                if id_object != OBJID_WINDOW:
                    return
                _maybe_hide(hwnd_obj)
            except Exception:
                return

        proc = WinEventProc(_win_event_proc)
        self._child_startup_suppress_proc = proc
        stop_event = threading.Event()
        self._child_startup_suppress_stop = stop_event

        try:
            global_hook = user32.SetWinEventHook(
                EVENT_OBJECT_CREATE,
                EVENT_OBJECT_SHOW,
                0,
                proc,
                0,
                0,
                WINEVENT_OUTOFCONTEXT,
            )
            if global_hook:
                hooks[0] = int(global_hook)
        except Exception:
            pass

        def _install_hook_for_pid(pid_val: int) -> None:
            if not pid_val or pid_val in hooks:
                return
            try:
                hook = user32.SetWinEventHook(
                    EVENT_OBJECT_CREATE,
                    EVENT_OBJECT_SHOW,
                    0,
                    proc,
                    int(pid_val),
                    0,
                    WINEVENT_OUTOFCONTEXT,
                )
                if hook:
                    hooks[int(pid_val)] = int(hook)
            except Exception:
                return

        def _poll_once() -> None:
            EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

            def _enum_cb(hwnd_obj, _lparam):  # noqa: ANN001
                try:
                    try:
                        if not user32.IsWindowVisible(hwnd_obj):
                            return True
                    except Exception:
                        return True
                    if not _is_transient_window(hwnd_obj):
                        return True
                    pid_val = _get_hwnd_pid(hwnd_obj)
                    if not _maybe_track_pid(pid_val):
                        return True
                    _hide_hwnd(hwnd_obj)
                except Exception:
                    return True
                return True

            cb = EnumWindowsProc(_enum_cb)
            try:
                user32.EnumWindows(cb, 0)
            except Exception:
                pass

        def _main_window_visible() -> bool:
            found = False
            EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

            def _enum_cb(hwnd_obj, _lparam):  # noqa: ANN001
                nonlocal found
                try:
                    pid_val = _get_hwnd_pid(hwnd_obj)
                    if pid_val != int(root_pid):
                        return True
                    if not user32.IsWindowVisible(hwnd_obj):
                        return True
                    rect = wintypes.RECT()
                    if not user32.GetWindowRect(hwnd_obj, ctypes.byref(rect)):
                        return True
                    width = int(rect.right - rect.left)
                    height = int(rect.bottom - rect.top)
                    if width >= 500 and height >= 300:
                        found = True
                        return False
                except Exception:
                    return True
                return True

            cb = EnumWindowsProc(_enum_cb)
            try:
                user32.EnumWindows(cb, 0)
            except Exception:
                return False
            return found

        def _run() -> None:
            started = time.monotonic()
            deadline = started + (duration_ms / 1000.0)
            fast_deadline = started + (fast_ms / 1000.0)
            next_process_scan = 0.0

            while time.monotonic() < deadline and not stop_event.is_set():
                now = time.monotonic()
                try:
                    if now - started > 0.6 and _main_window_visible():
                        break
                except Exception:
                    pass
                if now >= next_process_scan:
                    next_process_scan = now + 0.25
                    try:
                        new_pids = _enum_descendant_pids(int(root_pid))
                        pid_snapshot["pids"] = set(new_pids)
                        pid_snapshot["ts"] = now
                        with tracked_lock:
                            for pid_val in new_pids:
                                if pid_val not in tracked_pids:
                                    tracked_pids.add(pid_val)
                                    _install_hook_for_pid(pid_val)
                    except Exception:
                        pass
                _poll_once()
                if now < fast_deadline:
                    time.sleep(fast_interval_ms / 1000.0)
                else:
                    time.sleep(interval_ms / 1000.0)

            for hook in list(hooks.values()):
                try:
                    user32.UnhookWinEvent(hook)
                except Exception:
                    pass
            hooks.clear()
            with tracked_lock:
                tracked_pids.clear()

        for pid_val in list(tracked_pids):
            _install_hook_for_pid(pid_val)

        thread = threading.Thread(target=_run, name="starter-child-window-suppress", daemon=True)
        self._child_startup_suppress_thread = thread
        self._child_startup_suppress_hooks = hooks
        self._verbose_log("child window suppression thread started")
        thread.start()

    def _stop_child_startup_window_suppression(self) -> None:
        if sys.platform != "win32":
            return
        self._verbose_log("child window suppression stop requested")
        stop_event = getattr(self, "_child_startup_suppress_stop", None)
        try:
            if stop_event is not None:
                stop_event.set()
        except Exception:
            pass
        thread = getattr(self, "_child_startup_suppress_thread", None)
        if thread is not None and getattr(thread, "is_alive", lambda: False)():
            try:
                thread.join(timeout=0.5)
            except Exception:
                pass
        try:
            hooks = getattr(self, "_child_startup_suppress_hooks", None) or {}
            if hooks:
                import ctypes
                user32 = ctypes.windll.user32
                for hook in list(hooks.values()):
                    try:
                        user32.UnhookWinEvent(hook)
                    except Exception:
                        pass
        except Exception:
            pass
        self._child_startup_suppress_stop = None
        self._child_startup_suppress_thread = None
        self._child_startup_suppress_proc = None
        self._child_startup_suppress_hooks = {}

    def _schedule_auto_launch(self) -> None:
        self._verbose_log("auto-launch schedule requested")
        if self._auto_launch_timer is not None:
            try:
                self._auto_launch_timer.stop()
            except Exception:
                pass
            try:
                self._auto_launch_timer.deleteLater()
            except Exception:
                pass
            self._auto_launch_timer = None
        if not self._can_launch_selected():
            return
        timer = QtCore.QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(200)
        timer.timeout.connect(self._perform_auto_launch_if_ready)
        timer.start()
        self._auto_launch_timer = timer

    def _perform_auto_launch_if_ready(self) -> None:
        self._auto_launch_timer = None
        if self._is_launching:
            return
        if self._active_bot_process and self._active_bot_process.poll() is None:
            return
        if self._can_launch_selected():
            self._verbose_log("auto-launch triggered")
            self.launch_selected_bot()

    def _reset_launch_tracking(self) -> None:
        self._launch_status_timer.stop()
        self._process_watch_timer.stop()
        ready_file = getattr(self, "_child_ready_file", None)
        if ready_file is not None:
            try:
                ready_file.unlink(missing_ok=True)
            except Exception:
                pass
        self._child_ready_file = None
        try:
            self._stop_child_startup_window_suppression()
        except Exception:
            pass
        try:
            self._hide_launch_overlay()
        except Exception:
            pass
        if self._auto_launch_timer is not None:
            try:
                self._auto_launch_timer.stop()
            except Exception:
                pass
            try:
                self._auto_launch_timer.deleteLater()
            except Exception:
                pass
            self._auto_launch_timer = None
        self._active_bot_process = None
        self._bot_ready = False
        self._launch_timed_out = False
        self._active_launch_label = "Selected bot"
        self._running_ready_message = "Selected bot is running. Close it to relaunch."
        self._closed_message = "Selected bot closed. Launch it again anytime."
        self._set_launch_in_progress(False)

    def _update_status_message(self) -> None:
        if self.stack.currentIndex() == 0:
            if self.selected_language:
                label = next(
                    (opt["title"] for opt in LANGUAGE_OPTIONS if opt["key"] == self.selected_language),
                    self.selected_language.title(),
                )
                self.status_label.setText(f"{label} selected. Click Next to choose your market.")
            else:
                self.status_label.setText("Select a programming language to continue.")
            return
        if self._is_launching and not self._launch_timed_out:
            return
        if self.selected_market is None:
            self.status_label.setText("Select a market to continue.")
            return
        if self.selected_market == "forex":
            self.status_label.setText(
                "Forex brokers (OANDA, FXCM, IG) are coming soon. Choose Crypto -> Binance, Bybit, OKX, Gate, Bitget, MEXC, or KuCoin to launch today."
            )
            return
        if self.selected_market != "crypto":
            self.status_label.setText("Select 'Crypto Exchange' to reveal supported exchanges.")
            return
        language = self.selected_language
        exchange = self.selected_exchange
        if language == "python":
            if exchange in PYTHON_EXCHANGE_MAIN:
                label = PYTHON_EXCHANGE_LABELS.get(exchange, exchange.title())
                self.status_label.setText(f"{label} is ready. Press 'Launch Selected Bot' to open the PyQt app.")
                return
            self.status_label.setText("Select Binance, Bybit, OKX, Gate, Bitget, MEXC, or KuCoin to launch the Python workspace.")
            return

        if language == "cpp":
            exe_path = self._resolve_cpp_binance_executable(refresh=True)
            if exchange == "binance":
                if exe_path:
                    self.status_label.setText(
                        "Qt C++ Binance backtest tab is ready. Press 'Launch Selected Bot' to open it."
                    )
                else:
                    self.status_label.setText(
                        "Qt C++ Binance backtest tab needs to be built. Press 'Launch Selected Bot' to build and run "
                        "(requires Qt + CMake in PATH)."
                    )
                return
            if exchange in {"bybit", "okx", "gate", "bitget", "mexc", "kucoin"}:
                self.status_label.setText(
                    "Only the Binance Qt C++ preview is available today. Select Binance to launch it."
                )
                return
            self.status_label.setText(
                "Select Binance to launch the Qt C++ backtest tab preview. Other exchanges are coming soon."
            )
            return

        self.status_label.setText(
            "This language launcher is still under construction. Select Python to launch the available workspace."
        )

    def _can_launch_selected(self) -> bool:
        if self.stack.currentIndex() != 1:
            return False
        if self.selected_market != "crypto":
            return False
        language = self.selected_language
        if language == "python":
            main_path = PYTHON_EXCHANGE_MAIN.get(self.selected_exchange)
            return bool(main_path and main_path.is_file())
        if language == "cpp":
            return self.selected_exchange == "binance" and BINANCE_CPP_PROJECT.is_dir()
        return False

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._update_exchange_card_widths()

    def launch_selected_bot(self) -> None:
        if not self._can_launch_selected():
            _debug_log("Launch blocked: _can_launch_selected returned False.")
            self._update_status_message()
            return
        if self.selected_language == "python" and self.selected_exchange in PYTHON_EXCHANGE_MAIN:
            self._enable_verbose_launch_logging("launch-start")
        self._verbose_log(
            f"launch requested: language={self.selected_language} "
            f"market={self.selected_market} exchange={self.selected_exchange}"
        )
        if self._active_bot_process and self._active_bot_process.poll() is None:
            label = self._active_launch_label or "Selected bot"
            _debug_log(f"Launch blocked: {label} already running (pid={self._active_bot_process.pid}).")
            self.status_label.setText(f"{label} is already running. Close it to relaunch.")
            return

        command: list[str]
        cwd: Path
        start_message: str
        running_label: str
        ready_message: str
        closed_message: str

        if self.selected_language == "python":
            exchange_key = self.selected_exchange
            exchange_label = PYTHON_EXCHANGE_LABELS.get(exchange_key, "Selected bot")
            main_path = PYTHON_EXCHANGE_MAIN.get(exchange_key or "")
            if main_path is None or not main_path.is_file():
                _debug_log(f"{exchange_label} main missing: {main_path}")
                QtWidgets.QMessageBox.critical(
                    self,
                    f"{exchange_label} bot missing",
                    f"Could not find {main_path}. Make sure the repository is intact.",
                )
                return
            python_exec = sys.executable
            if sys.platform == "win32":
                pythonw = Path(sys.executable).with_name("pythonw.exe")
                if pythonw.is_file():
                    python_exec = str(pythonw)
                    _debug_log(f"Using pythonw for child process: {python_exec}")
            command = [python_exec, str(main_path)]
            cwd = main_path.parent
            start_message = f"Bot is starting... Opening the {exchange_label} workspace."
            running_label = f"{exchange_label} Python bot"
            ready_message = f"{exchange_label} Python bot is running. Close it to relaunch."
            closed_message = f"{exchange_label} Python bot closed. Launch it again anytime."
            _debug_log(f"Launching Python bot: exec={python_exec}, cwd={cwd}")
            self._verbose_log(f"python launch command: {command} cwd={cwd}")
        elif self.selected_language == "cpp":
            exe_path = self._resolve_cpp_binance_executable(refresh=True)
            if exe_path is None or not exe_path.is_file():
                self.status_label.setText(
                    "Building Qt C++ Binance backtest tab (this may take a minute-requires Qt + CMake)..."
                )
                QtWidgets.QApplication.processEvents()
                self.primary_button.setEnabled(False)
                exe_path, error = self._ensure_cpp_binance_executable()
                self.primary_button.setEnabled(True)
                self._update_nav_state()
                if exe_path is None or not exe_path.is_file():
                    detail = error or "Automatic build failed. Check that Qt 6 and CMake are installed."
                    QtWidgets.QMessageBox.warning(
                        self,
                        "Qt build required",
                        textwrap.dedent(
                            f"""\
                            Could not build the Qt/C++ Binance backtest tab automatically.

                            {detail}

                            Make sure Qt (with Widgets) and CMake are installed. If Qt lives outside the default
                            install path, set QT_CMAKE_PREFIX_PATH or CMAKE_PREFIX_PATH before launching."""
                        ),
                    )
                    self._update_status_message()
                    _debug_log(f"CPP launch failed during build: {detail}")
                    return
            command = [str(exe_path)]
            cwd = exe_path.parent
            start_message = "Launching the Qt C++ Binance backtest tab..."
            running_label = "Qt C++ Binance backtest tab"
            ready_message = "Qt C++ Binance backtest tab is running. Close it to relaunch."
            closed_message = "Qt C++ Binance backtest tab closed. Launch it again anytime."
            _debug_log(f"Launching C++ bot: exe={exe_path}, cwd={cwd}")
        else:
            self.status_label.setText(
                "Selected language does not have a launcher yet. Choose Python or C++ Binance."
            )
            _debug_log(f"Launch blocked: unsupported language {self.selected_language}")
            return

        self._launch_status_timer.stop()
        self._bot_ready = False
        ready_file = getattr(self, "_child_ready_file", None)
        if ready_file is not None:
            try:
                ready_file.unlink(missing_ok=True)
            except Exception:
                pass
        self._child_ready_file = None
        self._set_launch_in_progress(True)
        self._active_launch_label = running_label
        self._running_ready_message = ready_message
        self._closed_message = closed_message
        launch_log_hint = ""
        if self.selected_language == "python":
            launch_log_hint = f" | Launch log: {os.getenv('TEMP') or cwd}\\binance_launch.log"
        self.status_label.setText(start_message + launch_log_hint)
        if sys.platform == "win32" and self.selected_language == "python":
            try:
                self._begin_launch_focus_shield()
            except Exception:
                pass
        try:
            self._show_launch_overlay(start_message)
        except Exception:
            pass
        try:
            popen_kwargs: dict[str, object] = {"cwd": str(cwd)}
            # Hide only the Python console window; keep the Qt/C++ UI visible
            hide_console = False
            if sys.platform == "win32" and self.selected_language == "python":
                try:
                    hide_console = Path(str(command[0])).name.lower() != "pythonw.exe"
                except Exception:
                    hide_console = True
            if hide_console:
                create_no_window = 0x08000000  # CREATE_NO_WINDOW
                popen_kwargs["creationflags"] = create_no_window
            self._verbose_log(
                f"popen config: hide_console={hide_console} "
                f"creationflags={popen_kwargs.get('creationflags', 0)}"
            )

            # ALWAYS disable taskbar metadata to prevent window flashing
            env = os.environ.copy()
            # env["BOT_DISABLE_TASKBAR"] = "1"  <-- REMOVED to fix taskbar icon issue
            if self._verbose_launch_logging:
                env["BOT_DEBUG_WINDOW_EVENTS"] = "1"
                self._verbose_log("child env BOT_DEBUG_WINDOW_EVENTS=1")
            if self.selected_language == "python":
                exchange_label = PYTHON_EXCHANGE_LABELS.get(self.selected_exchange)
                if exchange_label:
                    env["BOT_SELECTED_EXCHANGE"] = exchange_label
                    self._verbose_log(f"child env BOT_SELECTED_EXCHANGE={exchange_label!r}")
                if sys.platform == "win32":
                    env.setdefault("BOT_DISABLE_APP_ICON", "1")
                    env.setdefault("BOT_ENABLE_NATIVE_ICON", "1")
                    env.setdefault("BOT_ENABLE_DELAYED_QT_ICON", "1")
                    env.setdefault("BOT_DELAYED_APP_ICON_MS", "800")
                    env.setdefault("BOT_NATIVE_ICON_DELAY_MS", "150")
                    env.setdefault("BOT_ICON_ENFORCE_ATTEMPTS", "6")
                    env.setdefault("BOT_ICON_ENFORCE_INTERVAL_MS", "500")
                    env.setdefault("BOT_DISABLE_TASKBAR", "0")
                    env.setdefault("BOT_TASKBAR_METADATA_DELAY_MS", "1200")
                    env.setdefault("BOT_TASKBAR_ENSURE_MS", "8000")
                    env.setdefault("BOT_NO_STARTUP_WINDOW_SUPPRESS", "1")
                    env.setdefault("BOT_NO_CBT_STARTUP_WINDOW_SUPPRESS", "1")
                    env.setdefault("BOT_NO_WINEVENT_STARTUP_WINDOW_SUPPRESS", "1")
                    env.setdefault("BOT_DISABLE_STARTUP_WINDOW_HOOKS", "1")
                no_cbt = str(env.get("BOT_NO_CBT_STARTUP_WINDOW_SUPPRESS", "")).strip().lower() in {
                    "1",
                    "true",
                    "yes",
                    "on",
                }
                no_startup = str(env.get("BOT_NO_STARTUP_WINDOW_SUPPRESS", "")).strip().lower() in {
                    "1",
                    "true",
                    "yes",
                    "on",
                }
                if not (no_cbt or no_startup):
                    env.setdefault("BOT_ENABLE_CBT_STARTUP_WINDOW_SUPPRESS", "1")
                    self._verbose_log(
                        "child env BOT_ENABLE_CBT_STARTUP_WINDOW_SUPPRESS="
                        f"{env.get('BOT_ENABLE_CBT_STARTUP_WINDOW_SUPPRESS', '')!r}"
                    )

            # Starter->child "ready" handshake (prevents the starter from getting stuck in
            # "Bot is starting..." if Win32 window detection misses the main window).
            if self.selected_language == "python":
                try:
                    ready_dir = Path(os.getenv("TEMP") or str(cwd))
                    ready_dir.mkdir(parents=True, exist_ok=True)
                    ready_path = ready_dir / f"binance_ready_{uuid4().hex}.flag"
                    try:
                        ready_path.unlink(missing_ok=True)
                    except Exception:
                        pass
                    env["BOT_STARTER_READY_FILE"] = str(ready_path)
                    self._child_ready_file = ready_path
                    _debug_log(f"Ready signal file: {ready_path}")
                    self._verbose_log(f"ready file path: {ready_path}")
                except Exception as ready_exc:
                    self._child_ready_file = None
                    _debug_log(f"Ready signal file setup failed: {ready_exc}")

            # Startup window suppression stays configurable in main.py. Avoid forcing CBT
            # hooks here because they can interfere with QtWebEngine window creation.

            # QtWebEngine suppression
            env["QTWEBENGINE_DISABLE_SANDBOX"] = "1"
            self._verbose_log(
                f"child env QTWEBENGINE_DISABLE_SANDBOX={env.get('QTWEBENGINE_DISABLE_SANDBOX', '')!r}"
            )
            # Inject flags to suppress QtWebEngine helper surface while keeping GPU on for TradingView
            current_flags = env.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
            extra_flags = ["--no-sandbox", "--window-position=-10000,-10000"]
            if self._verbose_launch_logging:
                current_flags = " ".join(
                    flag for flag in current_flags.split() if flag != "--disable-logging"
                )
                extra_flags.extend(["--enable-logging=stderr", "--v=1"])
            else:
                extra_flags.append("--disable-logging")
            merged_flags = self._merge_chromium_flags(current_flags, extra_flags)
            env["QTWEBENGINE_CHROMIUM_FLAGS"] = merged_flags
            self._verbose_log(f"child env QTWEBENGINE_CHROMIUM_FLAGS={merged_flags!r}")

            if self.selected_language == "cpp":
                qt_bins = self._discover_qt_bin_dirs()
                if qt_bins:
                    env["PATH"] = os.pathsep.join([*(str(p) for p in qt_bins), env.get("PATH", "")])
                    _debug_log(f"Augmented PATH with Qt bin dirs: {qt_bins}")

            popen_kwargs["env"] = env
            # Capture early stdout/stderr so failures are visible when using hidden window flags.
            try:
                log_dir = Path(os.getenv("TEMP") or cwd)
                log_dir.mkdir(parents=True, exist_ok=True)
                self._launch_log_path = log_dir / "binance_launch.log"
                popen_kwargs["stdout"] = open(self._launch_log_path, "w", encoding="utf-8", errors="ignore")
                popen_kwargs["stderr"] = subprocess.STDOUT
                _debug_log(f"Child stdout/stderr redirected to {self._launch_log_path}")
                self._verbose_log(f"child launch log path: {self._launch_log_path}")
            except Exception as log_exc:
                self._launch_log_path = None
                _debug_log(f"Failed to attach launch log: {log_exc}")
                self._verbose_log(f"child launch log attach failed: {log_exc}")
            self._active_bot_process = subprocess.Popen(command, **popen_kwargs)
            _debug_log(f"Spawned process pid={self._active_bot_process.pid}")
            self._verbose_log(f"spawned process pid={self._active_bot_process.pid}")
            if sys.platform == "win32" and self.selected_language == "python":
                try:
                    self._start_child_startup_window_suppression(int(self._active_bot_process.pid))
                except Exception as suppress_exc:
                    _debug_log(f"Child window suppression failed: {suppress_exc}")
                    self._verbose_log(f"child window suppression failed: {suppress_exc}")
            # If the child dies immediately, surface the error instead of leaving the user waiting.
            if self._active_bot_process.poll() is not None:
                rc = self._active_bot_process.returncode
                self._reset_launch_tracking()
                log_tail = ""
                try:
                    if self._launch_log_path and self._launch_log_path.is_file():
                        with open(self._launch_log_path, "r", encoding="utf-8", errors="ignore") as fh:
                            lines = fh.readlines()
                            log_tail = "".join(lines[-12:])
                except Exception as tail_exc:
                    _debug_log(f"Reading launch log failed: {tail_exc}")
                    log_tail = ""
                _debug_log(f"Process exited immediately code={rc}. Tail:\n{log_tail}")
                self._verbose_log(f"process exited immediately: code={rc}")
                QtWidgets.QMessageBox.critical(
                    self,
                    "Bot failed to start",
                    f"{running_label} exited immediately (code {rc}).\n\n{log_tail or 'Check that dependencies are installed.'}",
                )
                self._update_status_message()
                return
        except Exception as exc:  # pragma: no cover - UI only
            self._reset_launch_tracking()
            _debug_log(f"Launch exception: {exc}")
            self._verbose_log(f"launch exception: {exc}")
            QtWidgets.QMessageBox.critical(self, "Launch failed", str(exc))
            self._update_status_message()
            return
        self._process_watch_timer.start()
        # Fallback: if we cannot detect the main window, stop blocking the UI after a timeout.
        self._launch_status_timer.start(30000)


def main() -> None:
    ensure_app_user_model_id(WINDOWS_APP_ID)
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("Trading Bot Starter")
    app.setApplicationDisplayName("Trading Bot Starter")
    app_icon = _load_app_icon()
    if app_icon is not None:
        app.setWindowIcon(app_icon)
        QtGui.QGuiApplication.setWindowIcon(app_icon)
    window = StarterWindow(app_icon=app_icon)
    window.showMaximized()
    window.winId()
    if app_icon is not None:
        QtCore.QTimer.singleShot(0, lambda: window.setWindowIcon(app_icon))
    if sys.platform == "win32":
        icon_location = None
        if APP_ICON_PATH.is_file():
            icon_location = APP_ICON_PATH.resolve()
        elif APP_ICON_FALLBACK.is_file():
            icon_location = APP_ICON_FALLBACK.resolve()
        icon_str = str(icon_location) if icon_location is not None else None
        relaunch_cmd = build_relaunch_command(Path(__file__))

        def _attempt_taskbar(attempts_remaining: int = 1, delay_ms: int = 0) -> None:
            if attempts_remaining <= 0:
                return
            def _run():
                success = apply_taskbar_metadata(
                    window,
                    app_id=WINDOWS_APP_ID,
                    display_name="Trading Bot Starter",
                    icon_path=icon_str,
                    relaunch_command=relaunch_cmd,
                )
                if not success and attempts_remaining > 0:
                    QtCore.QTimer.singleShot(
                        300,
                        lambda: _attempt_taskbar(attempts_remaining - 1, 0),
                    )
            if delay_ms > 0:
                QtCore.QTimer.singleShot(delay_ms, _run)
            else:
                _run()

        QtCore.QTimer.singleShot(500, lambda: _attempt_taskbar(1, 0))
    sys.exit(app.exec())


if __name__ == "__main__":
    _debug_log("Starter launched.")
    main()
