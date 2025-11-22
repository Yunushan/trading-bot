from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from datetime import datetime

os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
_chromium_flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
_dns_guard_flags = "--dns-prefetch-disable --disable-features=WinUseBrowserSignal"
_gpu_flags = "--ignore-gpu-blocklist --enable-gpu-rasterization --enable-zero-copy --use-gl=angle"
if _dns_guard_flags not in _chromium_flags or _gpu_flags not in _chromium_flags:
    merged_flags = f"{_chromium_flags} {_dns_guard_flags} {_gpu_flags}".strip()
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = merged_flags

from PyQt6 import QtCore, QtGui, QtWidgets

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parents[3] if len(BASE_DIR.parents) >= 4 else BASE_DIR
WINDOWS_TASKBAR_DIR = REPO_ROOT / "Languages" / "Python" / "Crypto-Exchanges" / "Binance"

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
BINANCE_CPP_PROJECT = (
    REPO_ROOT / "Languages" / "C++" / "Crypto-Exchanges" / "Binance" / "backtest_tab"
)
BINANCE_CPP_BUILD_ROOT = REPO_ROOT / "build" / "backtest_tab"
BINANCE_CPP_EXECUTABLE_BASENAME = "binance_backtest_tab"
APP_ICON_BASENAME = "crypto_forex_logo"
APP_ICON_PATH = REPO_ROOT / "assets" / f"{APP_ICON_BASENAME}.ico"
APP_ICON_FALLBACK = REPO_ROOT / "assets" / f"{APP_ICON_BASENAME}.png"
WINDOWS_APP_ID = "com.tradingbot.starter"
DEBUG_LOG_PATH = Path(os.getenv("TEMP") or ".").resolve() / "starter_debug.log"


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
        "subtitle": "Qt native - coming soon",
        "accent": "#38bdf8",
        "badge": "Coming Soon",
        "disabled": True,
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
        "subtitle": "Derivatives-focused - coming soon",
        "accent": "#fb7185",
        "badge": "Coming Soon",
        "disabled": True,
    },
    {
        "key": "okx",
        "title": "OKX",
        "subtitle": "Options + spot - coming soon",
        "accent": "#a78bfa",
        "badge": "Coming Soon",
        "disabled": True,
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
        self._launch_status_timer.timeout.connect(self._mark_bot_ready)
        self._process_watch_timer = QtCore.QTimer(self)
        self._process_watch_timer.setInterval(250)  # Check every 250ms for faster response
        self._process_watch_timer.timeout.connect(self._monitor_bot_process)
        self._auto_launch_timer: QtCore.QTimer | None = None

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

        self.primary_button = QtWidgets.QPushButton("Next")
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

    def _resolve_cpp_binance_executable(self, refresh: bool = False) -> Path | None:
        if not refresh and self._cpp_binance_executable and self._cpp_binance_executable.is_file():
            return self._cpp_binance_executable
        self._cpp_binance_executable = self._find_cpp_binance_executable()
        return self._cpp_binance_executable

    def _find_cpp_binance_executable(self) -> Path | None:
        candidate_names = {BINANCE_CPP_EXECUTABLE_BASENAME}
        if sys.platform == "win32":
            candidate_names.add(f"{BINANCE_CPP_EXECUTABLE_BASENAME}.exe")
        else:
            candidate_names.add(BINANCE_CPP_EXECUTABLE_BASENAME)

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
                    if path.name in candidate_names or path.stem == BINANCE_CPP_EXECUTABLE_BASENAME:
                        return path
            except (PermissionError, OSError):
                continue
        return None

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
        configure_cmd = ["cmake", "-S", str(BINANCE_CPP_PROJECT), "-B", str(build_dir)]
        if prefix_env:
            configure_cmd.append(f"-DCMAKE_PREFIX_PATH={prefix_env}")

        ok, error = self._run_command_capture(configure_cmd)
        if not ok:
            return None, error

        build_cmd = ["cmake", "--build", str(build_dir)]
        build_configs = []
        if sys.platform == "win32":
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
        if self._can_launch_selected():
            self.launch_selected_bot()
        else:
            self._update_status_message()

    def _update_nav_state(self) -> None:
        page_idx = self.stack.currentIndex()
        self.back_button.setVisible(page_idx > 0)
        if page_idx == 0:
            self.primary_button.setText("Next")
            self.primary_button.setEnabled(self.selected_language is not None)
        else:
            if self._is_launching:
                if self._bot_ready:
                    self.primary_button.setText("Bot running (close to relaunch)")
                else:
                    self.primary_button.setText("Bot is starting...")
                self.primary_button.setEnabled(False)
            else:
                self.primary_button.setText("Launch Selected Bot")
                self.primary_button.setEnabled(self._can_launch_selected())

    def _set_launch_in_progress(self, launching: bool) -> None:
        self._is_launching = launching
        if not launching:
            self._bot_ready = False
        self._update_nav_state()

    def _mark_bot_ready(self) -> None:
        if self._active_bot_process and self._active_bot_process.poll() is None:
            self._bot_ready = True
            message = self._running_ready_message or "Selected bot is running. Close it to relaunch."
            self.status_label.setText(message)
            self._update_nav_state()

    def _monitor_bot_process(self) -> None:
        if not self._active_bot_process:
            self._process_watch_timer.stop()
            return
        if self._active_bot_process.poll() is not None:
            message = self._closed_message or "Selected bot closed. Launch it again anytime."
            self._reset_launch_tracking()
            self.status_label.setText(message)

    def _schedule_auto_launch(self) -> None:
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
            self.launch_selected_bot()

    def _reset_launch_tracking(self) -> None:
        self._launch_status_timer.stop()
        self._process_watch_timer.stop()
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
        if self._is_launching:
            return
        if self.selected_market is None:
            self.status_label.setText("Select a market to continue.")
            return
        if self.selected_market == "forex":
            self.status_label.setText(
                "Forex brokers (OANDA, FXCM, IG) are coming soon. Choose Crypto → Binance to launch today."
            )
            return
        if self.selected_market != "crypto":
            self.status_label.setText("Select 'Crypto Exchange' to reveal supported exchanges.")
            return
        language = self.selected_language
        exchange = self.selected_exchange
        if language == "python":
            if exchange == "binance":
                self.status_label.setText("Binance is ready. Press 'Launch Selected Bot' to open the PyQt app.")
                return
            if exchange in {"bybit", "okx"}:
                self.status_label.setText(f"{exchange.title()} workspace is being scaffolded.")
                return
            self.status_label.setText("Select Binance to launch the Python workspace. Other exchanges are coming soon.")
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
            if exchange in {"bybit", "okx"}:
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
        if self.selected_market != "crypto" or self.selected_exchange != "binance":
            return False
        language = self.selected_language
        if language == "python":
            return BINANCE_MAIN.is_file()
        if language == "cpp":
            return BINANCE_CPP_PROJECT.is_dir()
        return False

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._update_exchange_card_widths()

    def launch_selected_bot(self) -> None:
        if not self._can_launch_selected():
            _debug_log("Launch blocked: _can_launch_selected returned False.")
            self._update_status_message()
            return
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
            if not BINANCE_MAIN.is_file():
                _debug_log(f"Binance main missing: {BINANCE_MAIN}")
                QtWidgets.QMessageBox.critical(
                    self,
                    "Binance bot missing",
                    f"Could not find {BINANCE_MAIN}. Make sure the repository is intact.",
                )
                return
            python_exec = sys.executable
            if sys.platform == "win32":
                pythonw = Path(sys.executable).with_name("pythonw.exe")
                if pythonw.is_file():
                    python_exec = str(pythonw)
                    _debug_log(f"Using pythonw for child process: {python_exec}")
            command = [python_exec, str(BINANCE_MAIN)]
            cwd = BINANCE_MAIN.parent
            start_message = "Bot is starting... Opening the Binance workspace."
            running_label = "Binance Python bot"
            ready_message = "Binance Python bot is running. Close it to relaunch."
            closed_message = "Binance Python bot closed. Launch it again anytime."
            _debug_log(f"Launching Python bot: exec={python_exec}, cwd={cwd}")
        elif self.selected_language == "cpp":
            exe_path = self._resolve_cpp_binance_executable(refresh=True)
            if exe_path is None or not exe_path.is_file():
                self.status_label.setText(
                    "Building Qt C++ Binance backtest tab (this may take a minute—requires Qt + CMake)..."
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
        self._set_launch_in_progress(True)
        self._active_launch_label = running_label
        self._running_ready_message = ready_message
        self._closed_message = closed_message
        launch_log_hint = ""
        if self.selected_language == "python":
            launch_log_hint = f" | Launch log: {os.getenv('TEMP') or cwd}\\binance_launch.log"
        self.status_label.setText(start_message + launch_log_hint)
        try:
            popen_kwargs: dict[str, object] = {"cwd": str(cwd)}
            # Unconditionally force no window creation for the subprocess
            # This is the most reliable way to suppress console windows on Windows
            create_no_window = 0x08000000  # CREATE_NO_WINDOW
            popen_kwargs["creationflags"] = create_no_window

            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0)
                startupinfo.wShowWindow = 0  # SW_HIDE
                popen_kwargs["startupinfo"] = startupinfo

            # ALWAYS disable taskbar metadata to prevent window flashing
            env = os.environ.copy()
            # env["BOT_DISABLE_TASKBAR"] = "1"  <-- REMOVED to fix taskbar icon issue
            
            # QtWebEngine suppression
            env["QTWEBENGINE_DISABLE_SANDBOX"] = "1"
            # Inject flags to suppress QtWebEngine helper surface while keeping GPU on for TradingView
            current_flags = env.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
            extra_flags = (
                "--no-sandbox "
                "--disable-logging "
                "--window-position=-10000,-10000"
            )
            if extra_flags not in current_flags:
                env["QTWEBENGINE_CHROMIUM_FLAGS"] = f"{current_flags} {extra_flags}".strip()
            
            popen_kwargs["env"] = env
            # Capture early stdout/stderr so failures are visible when using hidden window flags.
            try:
                log_dir = Path(os.getenv("TEMP") or cwd)
                log_dir.mkdir(parents=True, exist_ok=True)
                self._launch_log_path = log_dir / "binance_launch.log"
                popen_kwargs["stdout"] = open(self._launch_log_path, "w", encoding="utf-8", errors="ignore")
                popen_kwargs["stderr"] = subprocess.STDOUT
                _debug_log(f"Child stdout/stderr redirected to {self._launch_log_path}")
            except Exception as log_exc:
                self._launch_log_path = None
                _debug_log(f"Failed to attach launch log: {log_exc}")
            self._active_bot_process = subprocess.Popen(command, **popen_kwargs)
            _debug_log(f"Spawned process pid={self._active_bot_process.pid}")
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
            QtWidgets.QMessageBox.critical(self, "Launch failed", str(exc))
            self._update_status_message()
            return
        self._process_watch_timer.start()
        self._launch_status_timer.start(2000)


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
