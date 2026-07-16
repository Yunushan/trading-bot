import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6 import QtWidgets  # noqa: E402

from app.gui.runtime.service import session_runtime  # noqa: E402
from app.gui.runtime.ui import design_layout_runtime  # noqa: E402
from app.gui.runtime.ui.theme_styles import (  # noqa: E402
    DESIGN_CLASSIC,
    DESIGN_OPTIONS,
    DESIGN_WORKSTATION,
)
from app.gui.runtime.window import state_init_runtime  # noqa: E402


def _layout_margins(layout) -> tuple[int, int, int, int]:
    margins = layout.contentsMargins()
    return margins.left(), margins.top(), margins.right(), margins.bottom()


class _LayoutWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.config = {"design": DESIGN_CLASSIC, "theme": "Dark"}
        self.workspace_root_layout = QtWidgets.QVBoxLayout(self)
        self._classic_root_layout_margins = _layout_margins(self.workspace_root_layout)
        self._classic_root_layout_spacing = self.workspace_root_layout.spacing()
        body_layout = design_layout_runtime.build_workspace_shell(
            self,
            self.workspace_root_layout,
        )

        self.tabs = QtWidgets.QTabWidget(self.workspace_body)
        self.dashboard_page = QtWidgets.QWidget(self.tabs)
        dashboard_layout = QtWidgets.QVBoxLayout(self.dashboard_page)
        self.symbol_edit = QtWidgets.QLineEdit(self.dashboard_page)
        dashboard_layout.addWidget(self.symbol_edit)
        self.positions_page = QtWidgets.QWidget(self.tabs)
        self.tabs.addTab(self.dashboard_page, "Dashboard")
        self.tabs.addTab(self.positions_page, "Positions")
        self.tabs.currentChanged.connect(
            lambda index: design_layout_runtime.update_workspace_page(self, index)
        )
        body_layout.addWidget(self.tabs, 1)

        self.design_combo = QtWidgets.QComboBox(self.dashboard_page)
        self.design_combo.addItems(DESIGN_OPTIONS)
        self.design_combo.currentTextChanged.connect(self.apply_design)
        self.dashboard_status_widget = QtWidgets.QWidget(self.dashboard_page)
        design_layout_runtime.sync_workspace_navigation(self)

    def _register_pnl_summary_labels(self, active_label, closed_label) -> None:
        active_label.setText("Active PNL: --")
        closed_label.setText("Closed PNL: --")

    def apply_design(self, design: str) -> None:
        self.config["design"] = design
        design_layout_runtime.apply_design_layout(self, design)


class WorkspaceDesignLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.window = _LayoutWindow()

    def tearDown(self):
        self.window.deleteLater()
        self.app.processEvents()

    def test_workstation_round_trip_reuses_pages_and_preserves_control_state(self):
        pages_before = tuple(
            self.window.tabs.widget(index) for index in range(self.window.tabs.count())
        )
        classic_margins = _layout_margins(self.window.workspace_root_layout)
        self.window.symbol_edit.setText("BTCUSDT")
        self.window.tabs.setCurrentIndex(1)

        self.window.apply_design(DESIGN_WORKSTATION)

        self.assertFalse(self.window.workspace_header.isHidden())
        self.assertFalse(self.window.workspace_nav_rail.isHidden())
        self.assertTrue(self.window.tabs.tabBar().isHidden())
        self.assertTrue(self.window.dashboard_status_widget.isHidden())
        self.assertEqual(1, self.window.tabs.currentIndex())
        self.assertEqual("BTCUSDT", self.window.symbol_edit.text())
        self.assertEqual(
            pages_before,
            tuple(self.window.tabs.widget(index) for index in range(self.window.tabs.count())),
        )

        self.window.apply_design(DESIGN_CLASSIC)

        self.assertTrue(self.window.workspace_header.isHidden())
        self.assertTrue(self.window.workspace_nav_rail.isHidden())
        self.assertFalse(self.window.tabs.tabBar().isHidden())
        self.assertFalse(self.window.dashboard_status_widget.isHidden())
        self.assertEqual(1, self.window.tabs.currentIndex())
        self.assertEqual("BTCUSDT", self.window.symbol_edit.text())
        self.assertEqual(classic_margins, _layout_margins(self.window.workspace_root_layout))
        self.assertEqual(
            pages_before,
            tuple(self.window.tabs.widget(index) for index in range(self.window.tabs.count())),
        )

    def test_workspace_navigation_tracks_and_selects_shared_tabs(self):
        self.window.apply_design(DESIGN_WORKSTATION)

        self.assertEqual(2, self.window.workspace_navigation.count())
        self.assertEqual("Dashboard", self.window.workspace_navigation.item(0).text())
        self.assertEqual("Positions", self.window.workspace_navigation.item(1).text())

        self.window.workspace_navigation.setCurrentRow(1)

        self.assertEqual(1, self.window.tabs.currentIndex())
        self.assertEqual("Positions", self.window.workspace_page_label.text())

    def test_workstation_header_button_returns_to_classic(self):
        self.window.design_combo.setCurrentText(DESIGN_WORKSTATION)
        self.assertFalse(self.window.workspace_header.isHidden())

        self.window.workspace_classic_btn.click()

        self.assertEqual(DESIGN_CLASSIC, self.window.design_combo.currentText())
        self.assertTrue(self.window.workspace_header.isHidden())


class WorkspaceDesignPersistenceTests(unittest.TestCase):
    def test_ui_preferences_preserve_existing_session_state(self):
        saved = []
        window = SimpleNamespace(
            _app_state={"session_active": True, "close_on_exit": False},
            _state_path=Path("state.json"),
            config={"design": DESIGN_WORKSTATION, "theme": "Green"},
        )

        with mock.patch.object(
            session_runtime,
            "_SAVE_APP_STATE_FILE",
            side_effect=lambda path, data: saved.append((path, dict(data))),
        ):
            session_runtime._persist_ui_preferences(window)

        self.assertEqual(1, len(saved))
        self.assertEqual(DESIGN_WORKSTATION, saved[0][1]["design"])
        self.assertEqual("Green", saved[0][1]["theme"])
        self.assertTrue(saved[0][1]["session_active"])
        self.assertIn("updated_at", saved[0][1])

    def test_config_state_restores_valid_saved_design_and_theme(self):
        window = SimpleNamespace(
            _app_state={"design": "workstation", "theme": "green"},
        )

        state_init_runtime._initialize_config_state(window)

        self.assertEqual(DESIGN_WORKSTATION, window.config["design"])
        self.assertEqual("Green", window.config["theme"])


if __name__ == "__main__":
    unittest.main()
