from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PyQt6 import QtCore, QtGui, QtWidgets

BASE_DIR = Path(__file__).resolve().parent
BINANCE_MAIN = BASE_DIR / "Languages" / "Python" / "Crypto-Exchanges" / "Binance" / "main.py"

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
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Trading Bot Starter")
        self.resize(1100, 720)
        self.setStyleSheet(
            f"background-color: {WINDOW_BG}; color: {TEXT_COLOR};"
            "font-family: 'Segoe UI', 'Inter', 'Helvetica Neue', sans-serif;"
        )

        self.selected_language = "python"
        self.selected_market: str | None = None
        self.selected_exchange: str | None = None

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

        self._update_language_selection("python")
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
        self.crypto_exchange_group.setStyleSheet(
            f"QGroupBox {{ background-color: {PANEL_BG}; border: 1px solid #202635;"
            "border-radius: 14px; margin-top: 12px; font-size: 16px; }}\n"
            "QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 4px 8px; color: #cbd5f5; }"
        )

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
        self.selected_language = key
        for card_key, card in self.language_cards.items():
            card.setSelected(card_key == key)
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

    def _go_back(self) -> None:
        if self.stack.currentIndex() == 1:
            self.stack.setCurrentIndex(0)
            self._update_nav_state()

    def _on_primary_clicked(self) -> None:
        if self.stack.currentIndex() == 0:
            self.stack.setCurrentIndex(1)
            self._update_nav_state()
            self._update_status_message()
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
            self.primary_button.setText("Launch Selected Bot")
            self.primary_button.setEnabled(self._can_launch_selected())

    def _update_status_message(self) -> None:
        if self.stack.currentIndex() == 0:
            self.status_label.setText("Python stays selected by default. Pick another language if needed.")
            return
        if self.selected_market != "crypto":
            self.status_label.setText("Select 'Crypto Exchange' to reveal supported exchanges (Forex coming soon).")
            return
        if self.selected_language != "python":
            self.status_label.setText("C++ and Rust launchers are on the roadmap. Choose Python to run today.")
            return
        if self.selected_exchange == "binance":
            self.status_label.setText("Binance is ready. Press 'Launch Selected Bot' to open the PyQt app.")
            return
        if self.selected_exchange in {"bybit", "okx"}:
            self.status_label.setText(f"{self.selected_exchange.title()} workspace is being scaffolded.")
            return
        self.status_label.setText("Pick Binance, Bybit, or OKX to prepare their workspace.")

    def _can_launch_selected(self) -> bool:
        return (
            self.stack.currentIndex() == 1
            and self.selected_language == "python"
            and self.selected_market == "crypto"
            and self.selected_exchange == "binance"
        )

    def launch_selected_bot(self) -> None:
        if not self._can_launch_selected():
            return
        if not BINANCE_MAIN.is_file():
            QtWidgets.QMessageBox.critical(
                self,
                "Binance bot missing",
                f"Could not find {BINANCE_MAIN}. Make sure the repository is intact.",
            )
            return
        try:
            subprocess.Popen([sys.executable, str(BINANCE_MAIN)], cwd=str(BINANCE_MAIN.parent))
            self.status_label.setText("Binance bot launched. Check the new window to continue.")
        except Exception as exc:  # pragma: no cover - UI only
            QtWidgets.QMessageBox.critical(self, "Launch failed", str(exc))


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("Trading Bot Starter")
    window = StarterWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
