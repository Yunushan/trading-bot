import sys
import unittest
from pathlib import Path


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.gui.runtime.ui import theme_runtime  # noqa: E402
from app.gui.runtime.ui.theme_styles import (  # noqa: E402
    CHECKBOX_CHECK_IMAGE,
    DARK_THEME,
    DESIGN_OPTIONS,
    WORKSTATION_DESIGN_STYLES,
    LIGHT_THEME,
)


class _FakeWindow:
    DARK_THEME = DARK_THEME
    LIGHT_THEME = LIGHT_THEME

    def __init__(self):
        self.config = {}
        self.stylesheet = ""

    def setStyleSheet(self, stylesheet: str) -> None:
        self.stylesheet = stylesheet


class ThemeAccentCoverageTests(unittest.TestCase):
    def test_accent_theme_styles_include_full_surface_selectors(self):
        styles = theme_runtime._accent_theme_styles("#fbbf24")

        expected_selectors = [
            "QWidget {",
            "QMainWindow, QDialog {",
            "QGroupBox {",
            "QTabBar::tab {",
            "QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit, QTextEdit, QPlainTextEdit {",
            "QListWidget, QTreeWidget, QTableWidget, QTableView, QTreeView, QListView, QAbstractItemView {",
            "QScrollBar:vertical, QScrollBar:horizontal {",
            "QStatusBar {",
        ]
        for selector in expected_selectors:
            with self.subTest(selector=selector):
                self.assertIn(selector, styles)

        self.assertIn("background-color: #fbbf24;", styles)
        self.assertIn("selection-background-color: #fbbf24;", styles)
        self.assertIn(f"image: {CHECKBOX_CHECK_IMAGE};", styles)
        self.assertIn("QCheckBox::indicator:unchecked {\n        image: none;", styles)

    def test_base_themes_use_packaged_checked_icon_and_empty_unchecked_state(self):
        for theme in (LIGHT_THEME, DARK_THEME):
            with self.subTest(theme=theme[:20]):
                self.assertIn("checkbox_checked.svg", theme)
                self.assertIn(f"image: {CHECKBOX_CHECK_IMAGE};", theme)
                self.assertIn("QCheckBox::indicator:unchecked {\n    image: none;", theme)

    def test_workstation_design_styles_cover_primary_desktop_surfaces(self):
        self.assertEqual(("Classic", "Workstation"), DESIGN_OPTIONS)
        for selector in (
            "QMainWindow, QDialog {",
            "QGroupBox {",
            "QTabBar::tab:selected {",
            "QTableWidget, QTableView, QTreeWidget",
            "QProgressBar::chunk {",
            "QStatusBar {",
            "QFrame#workspaceHeader {",
            "QFrame#workspaceNavigationRail {",
            "QListWidget#workspaceNavigation::item:selected {",
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, WORKSTATION_DESIGN_STYLES)

    def test_apply_accent_theme_overrides_dark_base_surfaces(self):
        window = _FakeWindow()

        theme_runtime._gui_apply_theme(window, "Green")

        self.assertEqual(window.config["theme"], "Green")
        self.assertIn("QWidget { background-color: #121212;", window.stylesheet)
        self.assertIn("QWidget {\n        background-color:", window.stylesheet)
        self.assertIn("QGroupBox {\n        background-color:", window.stylesheet)
        self.assertIn("QScrollBar:vertical, QScrollBar:horizontal", window.stylesheet)

    def test_apply_workstation_design_stacks_on_selected_theme(self):
        window = _FakeWindow()

        theme_runtime._gui_apply_design(window, "Workstation")

        self.assertEqual(window.config["theme"], "Dark")
        self.assertEqual(window.config["design"], "Workstation")
        self.assertIn("QWidget { background-color: #121212;", window.stylesheet)
        self.assertIn("QTabBar::tab:selected {\n    background-color: #16345B;", window.stylesheet)


if __name__ == "__main__":
    unittest.main()
