from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PyQt6 import QtWidgets  # noqa: E402

from app.gui.chart import selection_runtime, view_runtime  # noqa: E402


_TEST_APP: QtWidgets.QApplication | None = None


def _app() -> QtWidgets.QApplication:
    global _TEST_APP
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    _TEST_APP = app
    return app


class _ChartWindowStub:
    def __init__(self) -> None:
        _app()
        self.chart_enabled = True
        self.chart_config = {
            "market": "Spot",
            "symbol": "BTCUSDT",
            "interval": "1h",
            "view_mode": "original",
            "auto_follow": False,
        }
        self.chart_auto_follow = False
        self._chart_manual_override = False
        self._chart_updating = False
        self._chart_needs_render = False
        self.load_calls: list[bool] = []
        self.view_mode_calls: list[tuple[str, bool, bool]] = []
        self.chart_market_combo = QtWidgets.QComboBox()
        self.chart_market_combo.addItems(["Futures", "Spot"])
        self.chart_market_combo.setCurrentText("Spot")
        self.chart_symbol_combo = QtWidgets.QComboBox()
        self.chart_symbol_combo.addItems(["BTCUSDT", "ETHUSDT"])
        self.chart_symbol_combo.setCurrentText("BTCUSDT")
        self.chart_interval_combo = QtWidgets.QComboBox()
        self.chart_interval_combo.addItems(["1h", "4h", "1month", "1mo"])
        self.chart_interval_combo.setCurrentText("1h")
        self.interval_list = QtWidgets.QListWidget()

    @staticmethod
    def _canonicalize_chart_interval(value: str | None) -> str:
        return selection_runtime._canonicalize_chart_interval(value)

    @staticmethod
    def _normalize_chart_market(value) -> str:
        text = str(value or "").strip().lower()
        if text.startswith("spot"):
            return "Spot"
        return "Futures"

    def _set_chart_symbol(self, symbol: str, ensure_option: bool = False, from_follow: bool = False) -> bool:
        del ensure_option, from_follow
        normalized = str(symbol or "").strip().upper()
        if not normalized:
            return False
        if self.chart_symbol_combo.findText(normalized) < 0:
            self.chart_symbol_combo.addItem(normalized)
        self.chart_symbol_combo.setCurrentText(normalized)
        self.chart_config["symbol"] = normalized
        return True

    def _set_chart_interval(self, interval: str) -> bool:
        return selection_runtime._set_chart_interval(self, interval)

    def _apply_chart_view_mode(
        self,
        mode: str,
        initial: bool = False,
        *,
        allow_tradingview_init: bool = True,
    ) -> None:
        self.view_mode_calls.append((str(mode), bool(initial), bool(allow_tradingview_init)))

    def _is_chart_visible(self) -> bool:
        return False

    def load_chart(self, auto: bool = False) -> None:
        self.load_calls.append(bool(auto))


class ChartIntervalAliasStabilityTests(unittest.TestCase):
    def test_set_chart_interval_collapses_alias_without_duplicate_option(self):
        window = _ChartWindowStub()
        window.chart_interval_combo.clear()
        window.chart_interval_combo.addItems(["1h", "4h"])
        window.chart_interval_combo.setCurrentText("4h")

        changed = selection_runtime._set_chart_interval(window, "60m")

        self.assertTrue(changed)
        self.assertEqual("1h", window.chart_interval_combo.currentText())
        self.assertEqual("1h", window.chart_config["interval"])
        self.assertEqual(2, window.chart_interval_combo.count())

    def test_map_chart_interval_accepts_equivalent_aliases(self):
        window = _ChartWindowStub()

        self.assertEqual("60", selection_runtime._map_chart_interval(window, "60"))
        self.assertEqual("60", selection_runtime._map_chart_interval(window, "60m"))
        self.assertEqual("60", selection_runtime._map_chart_interval(window, "1H"))
        self.assertEqual("1M", selection_runtime._map_chart_interval(window, "1month"))
        self.assertEqual("1M", selection_runtime._map_chart_interval(window, "1M"))

    def test_on_chart_controls_changed_canonicalizes_selected_alias(self):
        window = _ChartWindowStub()
        window.chart_interval_combo.setCurrentText("60m")

        selection_runtime._on_chart_controls_changed(window)

        self.assertEqual("1h", window.chart_interval_combo.currentText())
        self.assertEqual("1h", window.chart_config["interval"])
        self.assertEqual([], window.load_calls)

    def test_selected_dashboard_interval_returns_canonical_value(self):
        window = _ChartWindowStub()
        item = QtWidgets.QListWidgetItem("60")
        window.interval_list.addItem(item)
        item.setSelected(True)

        self.assertEqual("1h", selection_runtime._selected_dashboard_interval(window))

    def test_restore_chart_controls_from_config_normalizes_interval_state(self):
        window = _ChartWindowStub()
        window.chart_config["interval"] = "60"

        view_runtime._restore_chart_controls_from_config(window)

        self.assertEqual("1h", window.chart_config["interval"])
        self.assertEqual("1h", window.chart_interval_combo.currentText())


if __name__ == "__main__":
    unittest.main()
