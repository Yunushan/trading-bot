from __future__ import annotations

import sys
from typing import cast
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PyQt6 import QtWidgets  # noqa: E402

from app.gui.backtest import backtest_state_context_runtime, backtest_state_lists_runtime  # noqa: E402
from app.gui.runtime.strategy import override_runtime  # noqa: E402


_TEST_APP: QtWidgets.QApplication | None = None


def _app() -> QtWidgets.QApplication:
    global _TEST_APP
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    _TEST_APP = app
    return app


class _BacktestIntervalWindow:
    def __init__(self) -> None:
        _app()
        self._bot_active = False
        self.config: dict[str, object] = {
            "symbols": ["BTCUSDT"],
            "backtest": {},
            "backtest_symbol_interval_pairs": [],
        }
        self.backtest_config: dict[str, object] = {
            "symbols": ["BTCUSDT"],
            "intervals": ["60m", "1H", "2M"],
        }
        self.backtest_symbols_all = ["BTCUSDT"]
        self.backtest_symbol_list = QtWidgets.QListWidget()
        self.backtest_interval_list = QtWidgets.QListWidget()
        self.backtest_symbol_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        self.backtest_interval_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        self.interval_list = QtWidgets.QListWidget()
        self.override_contexts: dict[str, dict[str, object]] = {}
        self.indicator_widgets: dict[str, object] = {}
        self.logged: list[str] = []

    def _update_backtest_symbol_list(self, candidates):
        return backtest_state_lists_runtime.update_backtest_symbol_list(self, candidates)

    def _backtest_store_symbols(self):
        return backtest_state_lists_runtime.backtest_store_symbols(self)

    def _backtest_store_intervals(self):
        return backtest_state_lists_runtime.backtest_store_intervals(self)

    def _normalize_strategy_controls(self, _kind: str, controls):
        return dict(controls or {})

    def _normalize_loop_override(self, value):
        return str(value or "").strip() or ""

    def _collect_strategy_controls(self, _kind: str):
        return {}

    def _prepare_controls_snapshot(self, _kind: str, controls):
        return dict(controls or {})

    def _log_override_debug(self, *_args, **_kwargs):
        return None

    def log(self, message):
        self.logged.append(str(message))

    def _refresh_symbol_interval_pairs(self, kind: str = "runtime"):
        self.logged.append(f"refresh:{kind}")

    def _add_selected_symbol_interval_pairs(self, kind: str = "runtime"):
        override_runtime._add_selected_symbol_interval_pairs(self, kind)


override_runtime.bind_main_window_override_runtime(
    _BacktestIntervalWindow,
    format_indicator_list=lambda values: ", ".join(str(value) for value in values),
    normalize_connector_backend=lambda value: value,
    normalize_indicator_values=lambda payload: [
        str(value).strip()
        for value in (payload or [])
        if str(value).strip()
    ],
    normalize_stop_loss_dict=lambda payload: dict(payload or {}),
)
backtest_state_context_runtime.configure_backtest_state_runtime(
    backtest_interval_order=["1m", "1h", "2mo", "2months", "4h"],
    side_labels={"BUY": "Buy"},
    symbol_fetch_top_n=200,
)


class BacktestIntervalAliasStabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        backtest_state_context_runtime.configure_backtest_state_runtime(
            backtest_interval_order=["1m", "1h", "2mo", "2months", "4h"],
            side_labels={"BUY": "Buy"},
            symbol_fetch_top_n=200,
        )

    def test_populate_backtest_lists_normalizes_selected_intervals(self):
        window = _BacktestIntervalWindow()

        backtest_state_lists_runtime.populate_backtest_lists(window)

        config_backtest = window.config.get("backtest")
        self.assertIsInstance(config_backtest, dict)
        config_backtest_dict = cast(dict[str, object], config_backtest)
        interval_labels: list[str] = []
        for i in range(window.backtest_interval_list.count()):
            item = window.backtest_interval_list.item(i)
            if item is not None:
                interval_labels.append(item.text())
        self.assertEqual(["1h", "2mo"], window.backtest_config["intervals"])
        self.assertEqual(["1h", "2mo"], config_backtest_dict["intervals"])
        self.assertEqual(["1m", "1h", "2mo", "4h"], interval_labels)

    def test_backtest_store_intervals_canonicalizes_aliases(self):
        window = _BacktestIntervalWindow()
        for label in ("60", "2months", "4h"):
            item = QtWidgets.QListWidgetItem(label)
            window.backtest_interval_list.addItem(item)
            if label != "4h":
                item.setSelected(True)

        backtest_state_lists_runtime.backtest_store_intervals(window)

        config_backtest = window.config.get("backtest")
        self.assertIsInstance(config_backtest, dict)
        config_backtest_dict = cast(dict[str, object], config_backtest)
        self.assertEqual(["1h", "2mo"], window.backtest_config["intervals"])
        self.assertEqual(["1h", "2mo"], config_backtest_dict["intervals"])

    def test_apply_backtest_intervals_to_dashboard_uses_canonical_values(self):
        window = _BacktestIntervalWindow()
        window.backtest_config["intervals"] = ["60m", "2months"]
        window.interval_list.addItem(QtWidgets.QListWidgetItem("1m"))

        backtest_state_lists_runtime.apply_backtest_intervals_to_dashboard(window)

        dashboard_intervals: list[str] = []
        for i in range(window.interval_list.count()):
            item = window.interval_list.item(i)
            if item is not None:
                dashboard_intervals.append(item.text())
        self.assertEqual(
            ["1m", "1h", "2mo"],
            dashboard_intervals,
        )
        self.assertEqual(["1h", "2mo"], window.config["intervals"])

    def test_backtest_override_add_selected_keeps_backtest_only_intervals(self):
        window = _BacktestIntervalWindow()
        symbol_list = QtWidgets.QListWidget()
        interval_list = QtWidgets.QListWidget()
        symbol_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        interval_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        symbol_item = QtWidgets.QListWidgetItem("BTCUSDT")
        interval_item_a = QtWidgets.QListWidgetItem("10m")
        interval_item_b = QtWidgets.QListWidgetItem("60m")
        symbol_list.addItem(symbol_item)
        interval_list.addItem(interval_item_a)
        interval_list.addItem(interval_item_b)
        symbol_item.setSelected(True)
        interval_item_a.setSelected(True)
        interval_item_b.setSelected(True)
        window.override_contexts["backtest"] = {
            "symbol_list": symbol_list,
            "interval_list": interval_list,
            "config_key": "backtest_symbol_interval_pairs",
        }

        window._add_selected_symbol_interval_pairs("backtest")

        self.assertEqual(
            [
                {"symbol": "BTCUSDT", "interval": "10m"},
                {"symbol": "BTCUSDT", "interval": "1h"},
            ],
            window.config["backtest_symbol_interval_pairs"],
        )


if __name__ == "__main__":
    unittest.main()
