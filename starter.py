from __future__ import annotations

import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

from PyQt6 import QtCore, QtGui, QtWidgets

from windows_taskbar import apply_taskbar_metadata, build_relaunch_command, ensure_app_user_model_id

BASE_DIR = Path(__file__).resolve().parent
BINANCE_MAIN = BASE_DIR / "Languages" / "Python" / "Crypto-Exchanges" / "Binance" / "main.py"
BINANCE_CPP_PROJECT = (
    BASE_DIR / "Languages" / "C++" / "Crypto-Exchanges" / "Binance" / "backtest_tab"
)
BINANCE_CPP_BUILD_ROOT = BASE_DIR / "build" / "backtest_tab"
BINANCE_CPP_EXECUTABLE_BASENAME = "binance_backtest_tab"
APP_ICON_BASENAME = "crypto_forex_logo"
APP_ICON_PATH = BASE_DIR / "assets" / f"{APP_ICON_BASENAME}.ico"
APP_ICON_FALLBACK = BASE_DIR / "assets" / f"{APP_ICON_BASENAME}.png"
WINDOWS_APP_ID = "com.tradingbot.starter"


def _load_app_icon() -> QtGui.QIcon | None:
    for path in (APP_ICON_PATH, APP_ICON_FALLBACK):
        if path.is_file():
            return QtGui.QIcon(str(path))
    return None


LANGUAGE_OPTIONS = [
    {
        "key": "python",
        "title": "Python",
        "subtitle": "Fast to build · Huge ecosystem",
        "accent": "#3b82f6",
        "badge": "Recommended",
    },
    {
        "key": "cpp",
        "title": "C++",
        "subtitle": "Qt native · Max performance",
        "accent": "#38bdf8",
    },
    {
        "key": "rust",
        "title": "Rust",
        "subtitle": "Memory safe · Near-C speed",
        "accent": "#fb923c",
    },
]

MARKET_OPTIONS = [
    {"key": "crypto", "title": "Crypto Exchange", "subtitle": "Binance, Bybit, KuCoin…", "accent": "#34d399"},
    {"key": "forex", "title": "Forex Exchange", "subtitle": "OANDA, FXCM, MetaTrader…", "accent": "#93c5fd"},
]

CRYPTO_EXCHANGES = [
    {"key": "binance", "title": "Binance", "subtitle": "Advanced desktop bot ready to launch", "accent": "#fbbf24"},
    {"key": "bybit", "title": "Bybit", "subtitle": "Derivatives-focused · coming soon", "accent": "#fb7185"},
    {"key": "okx", "title": "OKX", "subtitle": "Options + spot · coming soon", "accent": "#a78bfa"},
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
    ) -> None:
        super().__init__()
        self.option_key = option_key
        self.accent_color = accent_color
        self._selected = False
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setObjectName(f"card_{option_key}")

        wrapper = QtWidgets.QVBoxLayout(self)
        wrapper.setContentsMargins(0, 0, 0, 0)
        wrapper.setSpacing(0)

        self.accent_bar = QtWidgets.QFrame()
        self.accent_bar.setFixedHeight(6)
        wrapper.addWidget(self.accent_bar)

        body = QtWidgets.QWidget()
        body_layout = QtWidgets.QVBoxLayout(body)
        body_layout.setContentsMargins(18, 18, 18, 18)
        body_layout.setSpacing(10)
        wrapper.addWidget(body)

        self.badge_label = QtWidgets.QLabel(badge_text or "")
        self.badge_label.setStyleSheet(
            "padding: 2px 8px; border-radius: 8px; font-size: 11px; font-weight: 600;"
            "background-color: rgba(59, 130, 246, 0.15); color: #93c5fd;"
        )
        self.badge_label.setVisible(bool(badge_text))
        body_layout.addWidget(self.badge_label, alignment=QtCore.Qt.AlignmentFlag.AlignLeft)

        self.title_label = QtWidgets.QLabel(title)
        self.title_label.setStyleSheet("font-size: 24px; font-weight: 600;")
        body_layout.addWidget(self.title_label)

        self.subtitle_label = QtWidgets.QLabel(subtitle)
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setStyleSheet(f"color: {MUTED_TEXT}; font-size: 13px;")
        body_layout.addWidget(self.subtitle_label)
        body_layout.addStretch()

        self._refresh_style()

    def setSelected(self, selected: bool) -> None:
        self._selected = bool(selected)
        self._refresh_style()

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.clicked.emit(self.option_key)
        super().mouseReleaseEvent(event)

    def _refresh_style(self) -> None:
        bg = "#1b2231" if self._selected else "#141925"
        border = self.accent_color if self._selected else "#262c3f"
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
            f"background-color: {self.accent_color if self._selected else '#1f2433'};"
            "border-top-left-radius: 18px; border-top-right-radius: 18px;"
        )


class StarterWindow(QtWidgets.QWidget):
    def __init__(self, app_icon: QtGui.QIcon | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Trading Bot Starter")
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
        self._process_watch_timer.setInterval(1000)
        self._process_watch_timer.timeout.connect(self._monitor_bot_process)

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
        self._update_nav_state()

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

        heading = QtWidgets.QLabel("Choose your language")
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
        exchange_row = QtWidgets.QHBoxLayout()
        exchange_row.setSpacing(18)
        exch_layout.addLayout(exchange_row)

        for opt in CRYPTO_EXCHANGES:
            card = SelectableCard(opt["key"], opt["title"], opt["subtitle"], opt["accent"])
            card.setMinimumWidth(240)
            card.clicked.connect(self._update_exchange_selection)
            self.exchange_cards[opt["key"]] = card
            exchange_row.addWidget(card)

        layout.addWidget(self.crypto_exchange_group)
        layout.addStretch()
        return page

    def _update_language_selection(self, key: str) -> None:
        if key not in self.language_cards:
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

    def _update_market_selection(self, key: str) -> None:
        if key not in self.market_cards:
            return
        self.selected_market = key
        for card_key, card in self.market_cards.items():
            card.setSelected(card_key == key)
        self.crypto_exchange_group.setVisible(key == "crypto")
        if key != "crypto":
            self.selected_exchange = None
            for card in self.exchange_cards.values():
                card.setSelected(False)
        self._update_status_message()
        self._update_nav_state()

    def _update_exchange_selection(self, key: str) -> None:
        if key not in self.exchange_cards:
            return
        self.selected_exchange = key
        for card_key, card in self.exchange_cards.items():
            card.setSelected(card_key == key)
        self._update_status_message()
        self._update_nav_state()
        if self._can_launch_selected() and not self._is_launching:
            QtCore.QTimer.singleShot(100, self.launch_selected_bot)

    def _show_market_page(self) -> None:
        self.stack.setCurrentIndex(1)
        self._update_nav_state()
        self._update_status_message()

    def _go_back(self) -> None:
        if self.stack.currentIndex() == 1:
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
            self.primary_button.setEnabled(True)
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

    def _reset_launch_tracking(self) -> None:
        self._launch_status_timer.stop()
        self._process_watch_timer.stop()
        self._active_bot_process = None
        self._bot_ready = False
        self._active_launch_label = "Selected bot"
        self._running_ready_message = "Selected bot is running. Close it to relaunch."
        self._closed_message = "Selected bot closed. Launch it again anytime."
        self._set_launch_in_progress(False)

    def _update_status_message(self) -> None:
        if self.stack.currentIndex() == 0:
            self.status_label.setText("Python stays selected by default. Pick another language if needed.")
            return
        if self._is_launching:
            return
        if self.selected_market != "crypto":
            self.status_label.setText("Select 'Crypto Exchange' to reveal supported exchanges (Forex coming soon).")
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
            self.status_label.setText("Pick Binance, Bybit, or OKX to prepare their workspace.")
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
            self.status_label.setText("Pick Binance to launch the Qt C++ backtest tab preview.")
            return

        self.status_label.setText(
            "This language launcher is still under construction. Select Python or C++ Binance to launch an app."
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

    def launch_selected_bot(self) -> None:
        if not self._can_launch_selected():
            self._update_status_message()
            return
        if self._active_bot_process and self._active_bot_process.poll() is None:
            label = self._active_launch_label or "Selected bot"
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
                QtWidgets.QMessageBox.critical(
                    self,
                    "Binance bot missing",
                    f"Could not find {BINANCE_MAIN}. Make sure the repository is intact.",
                )
                return
            command = [sys.executable, str(BINANCE_MAIN)]
            cwd = BINANCE_MAIN.parent
            start_message = "Bot is starting... Opening the Binance workspace."
            running_label = "Binance Python bot"
            ready_message = "Binance Python bot is running. Close it to relaunch."
            closed_message = "Binance Python bot closed. Launch it again anytime."
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
                    return
            command = [str(exe_path)]
            cwd = exe_path.parent
            start_message = "Launching the Qt C++ Binance backtest tab..."
            running_label = "Qt C++ Binance backtest tab"
            ready_message = "Qt C++ Binance backtest tab is running. Close it to relaunch."
            closed_message = "Qt C++ Binance backtest tab closed. Launch it again anytime."
        else:
            self.status_label.setText(
                "Selected language does not have a launcher yet. Choose Python or C++ Binance."
            )
            return

        self._launch_status_timer.stop()
        self._bot_ready = False
        self._set_launch_in_progress(True)
        self._active_launch_label = running_label
        self._running_ready_message = ready_message
        self._closed_message = closed_message
        self.status_label.setText(start_message)
        try:
            self._active_bot_process = subprocess.Popen(
                command,
                cwd=str(cwd),
            )
        except Exception as exc:  # pragma: no cover - UI only
            self._reset_launch_tracking()
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
    window.show()
    window.winId()
    if app_icon is not None:
        QtCore.QTimer.singleShot(0, lambda: window.setWindowIcon(app_icon))
    if sys.platform == "win32":
        icon_location = None
        if APP_ICON_PATH.is_file():
            icon_location = APP_ICON_PATH
        elif APP_ICON_FALLBACK.is_file():
            icon_location = APP_ICON_FALLBACK
        relaunch_cmd = build_relaunch_command(Path(__file__))

        def _apply_taskbar(attempts: int = 4) -> None:
            if attempts <= 0:
                return
            success = apply_taskbar_metadata(
                window,
                app_id=WINDOWS_APP_ID,
                display_name="Trading Bot Starter",
                icon_path=icon_location,
                relaunch_command=relaunch_cmd,
            )
            if not success:
                QtCore.QTimer.singleShot(120, lambda: _apply_taskbar(attempts - 1))

        QtCore.QTimer.singleShot(0, _apply_taskbar)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
