from __future__ import annotations

from pathlib import Path

_ASSET_DIR = Path(__file__).resolve().parents[3] / "assets"
CHECKBOX_CHECK_IMAGE = f'url("{(_ASSET_DIR / "checkbox_checked.svg").as_posix()}")'

DESIGN_CLASSIC = "Classic"
DESIGN_WORKSTATION = "Workstation"
DESIGN_OPTIONS = (DESIGN_CLASSIC, DESIGN_WORKSTATION)

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
    image: {checkbox_check_image};
}
QCheckBox::indicator:hover {
    border-color: #0A84FF;
}
QComboBox { background-color: #FFFFFF; color: #000000; }
QListWidget { background-color: #FFFFFF; color: #000000; }
QLabel { color: #000000; }
QLabel:disabled { color: #7A7A7A; }
""".replace("{checkbox_check_image}", CHECKBOX_CHECK_IMAGE)

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
    image: {checkbox_check_image};
}
QCheckBox::indicator:hover {
    border-color: #3FB950;
}
QComboBox { background-color: #1E1E1E; color: #E0E0E0; }
QListWidget { background-color: #0E0E0E; color: #E0E0E0; }
QLabel { color: #E0E0E0; }
QLabel:disabled { color: #6F6F6F; }
""".replace("{checkbox_check_image}", CHECKBOX_CHECK_IMAGE)

WORKSTATION_DESIGN_STYLES = """
QWidget {
    background-color: #0B111C;
    color: #E6EDF7;
    font-family: "Segoe UI", Arial;
    font-size: 12px;
}
QMainWindow, QDialog {
    background-color: #070B12;
    color: #E6EDF7;
}
QScrollArea, QFrame, QSplitter, QStackedWidget {
    background-color: #0B111C;
    border: none;
}
QGroupBox {
    background-color: #0F1726;
    border: 1px solid #26364F;
    border-radius: 6px;
    margin-top: 14px;
    padding: 10px 8px 8px 8px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    top: 2px;
    padding: 0 6px;
    color: #A8C7FF;
    background-color: #0F1726;
    font-weight: 600;
}
QLabel {
    background-color: transparent;
    color: #E6EDF7;
}
QLabel:disabled {
    color: #6F7F96;
}
QPushButton, QToolButton {
    background-color: #16243A;
    border: 1px solid #2B4161;
    border-radius: 5px;
    color: #EEF6FF;
    padding: 6px 10px;
    font-weight: 600;
}
QPushButton:hover, QToolButton:hover {
    background-color: #1D3556;
    border-color: #3B82F6;
}
QPushButton:pressed, QPushButton:checked, QToolButton:pressed, QToolButton:checked {
    background-color: #0F2E52;
    border-color: #60A5FA;
}
QPushButton:disabled, QToolButton:disabled {
    background-color: #101725;
    border: 1px solid #223047;
    color: #697891;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit {
    background-color: #0A1020;
    border: 1px solid #243247;
    border-radius: 5px;
    color: #E6EDF7;
    padding: 5px 7px;
    selection-background-color: #1F6FEB;
    selection-color: #FFFFFF;
}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover,
QTextEdit:hover, QPlainTextEdit:hover {
    border-color: #3B82F6;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QTextEdit:focus, QPlainTextEdit:focus {
    border-color: #60A5FA;
    background-color: #0D1628;
}
QLineEdit:disabled, QComboBox:disabled, QListWidget:disabled, QSpinBox:disabled,
QDoubleSpinBox:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {
    background-color: #0B1220;
    border-color: #1C273A;
    color: #66758B;
}
QComboBox QAbstractItemView {
    background-color: #0A1020;
    border: 1px solid #243247;
    selection-background-color: #1F6FEB;
    selection-color: #FFFFFF;
}
QComboBox::drop-down {
    border: none;
    border-left: 1px solid #243247;
    background-color: #111C2F;
    width: 20px;
}
QCheckBox, QRadioButton {
    background-color: transparent;
    color: #E6EDF7;
    spacing: 7px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #52627A;
    border-radius: 4px;
    background-color: #0A1020;
}
QCheckBox::indicator:unchecked {
    image: none;
}
QCheckBox::indicator:checked {
    background-color: #2EA043;
    border-color: #3FB950;
    image: {checkbox_check_image};
}
QCheckBox::indicator:hover {
    border-color: #58A6FF;
}
QRadioButton::indicator {
    width: 15px;
    height: 15px;
    border: 1px solid #52627A;
    border-radius: 8px;
    background-color: #0A1020;
}
QRadioButton::indicator:checked {
    background-color: #58A6FF;
    border: 1px solid #8AB4FF;
}
QTabWidget::pane {
    border: 1px solid #26364F;
    top: -1px;
    background-color: #0B111C;
}
QTabBar::tab {
    background-color: #0F1726;
    border: 1px solid #26364F;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    color: #B8C7DD;
    margin-right: 3px;
    padding: 8px 14px;
}
QTabBar::tab:hover {
    background-color: #132238;
    border-color: #3B82F6;
    color: #FFFFFF;
}
QTabBar::tab:selected {
    background-color: #16345B;
    border-color: #2F6FB3;
    color: #FFFFFF;
}
QTableWidget, QTableView, QTreeWidget, QTreeView, QListWidget, QListView, QAbstractItemView {
    background-color: #0A1020;
    alternate-background-color: #101A2D;
    border: 1px solid #243247;
    color: #E6EDF7;
    gridline-color: #1D2A3F;
    selection-background-color: #1F6FEB;
    selection-color: #FFFFFF;
}
QAbstractItemView::item {
    min-height: 24px;
}
QAbstractItemView::item:hover {
    background-color: rgba(88, 166, 255, 0.18);
}
QAbstractItemView::item:selected {
    background-color: #1F6FEB;
    color: #FFFFFF;
}
QHeaderView::section {
    background-color: #111C2F;
    border: 1px solid #26364F;
    color: #B8C7DD;
    font-weight: 600;
    padding: 5px;
}
QProgressBar {
    background-color: #0A1020;
    border: 1px solid #243247;
    border-radius: 5px;
    color: #E6EDF7;
    text-align: center;
}
QProgressBar::chunk {
    background-color: #22C55E;
    border-radius: 4px;
}
QSlider::groove:horizontal {
    background: #182235;
    border: 1px solid #26364F;
    border-radius: 3px;
    height: 6px;
}
QSlider::handle:horizontal {
    background: #58A6FF;
    border: 1px solid #8AB4FF;
    border-radius: 7px;
    margin: -5px 0;
    width: 14px;
}
QScrollBar:vertical, QScrollBar:horizontal {
    background: #0B111C;
    border: 1px solid #1B2840;
}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: #263B5C;
    border: 1px solid #36537D;
    border-radius: 4px;
    min-height: 24px;
    min-width: 24px;
}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
    background: #31517D;
}
QScrollBar::add-line, QScrollBar::sub-line {
    background: #111C2F;
    border: 1px solid #26364F;
}
QScrollBar::add-page, QScrollBar::sub-page {
    background: #0B111C;
}
QMenu {
    background-color: #0A1020;
    border: 1px solid #243247;
    color: #E6EDF7;
}
QMenu::item {
    padding: 6px 18px;
}
QMenu::item:selected {
    background-color: #1F6FEB;
    color: #FFFFFF;
}
QStatusBar {
    background-color: #0F1726;
    border-top: 1px solid #26364F;
    color: #B8C7DD;
}
QFrame#workspaceHeader {
    background-color: #080E18;
    border: none;
    border-bottom: 1px solid #26364F;
}
QLabel#workspaceHeaderTitle {
    color: #F4F8FF;
    font-size: 16px;
    font-weight: 700;
}
QLabel#workspacePageTitle {
    color: #8DA4C2;
    font-size: 11px;
}
QLabel#workspaceKpi {
    background-color: #0F1726;
    border: 1px solid #26364F;
    border-radius: 4px;
    color: #C8D7EB;
    padding: 6px 9px;
}
QFrame#workspaceNavigationRail {
    background-color: #080E18;
    border: none;
    border-right: 1px solid #26364F;
}
QLabel#workspaceNavigationLabel {
    color: #6F86A5;
    font-size: 10px;
    font-weight: 700;
}
QListWidget#workspaceNavigation {
    background-color: transparent;
    border: none;
    outline: none;
    padding: 0;
}
QListWidget#workspaceNavigation::item {
    border: 1px solid transparent;
    border-radius: 4px;
    color: #AFC0D8;
    min-height: 34px;
    padding: 2px 10px;
}
QListWidget#workspaceNavigation::item:hover {
    background-color: #101D31;
    border-color: #223A5A;
    color: #FFFFFF;
}
QListWidget#workspaceNavigation::item:selected {
    background-color: #123760;
    border-color: #2F6FB3;
    color: #FFFFFF;
}
QPushButton#workspaceClassicButton {
    background-color: transparent;
    border-color: #36537D;
    color: #B8C7DD;
}
QPushButton#workspaceClassicButton:hover {
    background-color: #132238;
    border-color: #58A6FF;
    color: #FFFFFF;
}
""".replace("{checkbox_check_image}", CHECKBOX_CHECK_IMAGE)
