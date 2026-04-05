from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PyQt6 import QtCore, QtWidgets  # noqa: E402

from app.gui.runtime.strategy import context_runtime, override_runtime, start_collect_runtime  # noqa: E402


_TEST_APP: QtWidgets.QApplication | None = None


def _app() -> QtWidgets.QApplication:
    global _TEST_APP
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    _TEST_APP = app
    return app


class _StrategyIntervalWindow:
    def __init__(self) -> None:
        _app()
        self._bot_active = False
        self.config: dict[str, object] = {"runtime_symbol_interval_pairs": []}
        self.backtest_config: dict[str, object] = {}
        self.override_contexts: dict[str, dict[str, object]] = {}
        self.indicator_widgets: dict[str, object] = {}
        self.logged: list[str] = []
        self._engine_indicator_map: dict[str, dict[str, object]] = {}

    @staticmethod
    def _canonicalize_interval(value: str) -> str:
        return context_runtime._canonicalize_interval(value)

    def _collect_strategy_indicators(
        self,
        symbol: str,
        side_key: str,
        intervals: list[str] | set[str] | None = None,
    ) -> list[str]:
        return context_runtime._collect_strategy_indicators(self, symbol, side_key, intervals)

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

    def _remove_selected_symbol_interval_pairs(self, kind: str = "runtime"):
        override_runtime._remove_selected_symbol_interval_pairs(self, kind)


context_runtime.bind_main_window_strategy_context_runtime(
    _StrategyIntervalWindow,
    side_label_lookup={"both": "BOTH", "buy": "BUY", "sell": "SELL"},
    binance_interval_lower={"1m", "1h", "4h", "1w"},
)
override_runtime.bind_main_window_override_runtime(
    _StrategyIntervalWindow,
    format_indicator_list=lambda values: ", ".join(str(value) for value in values),
    normalize_connector_backend=lambda value: value,
    normalize_indicator_values=lambda payload: [
        str(value).strip()
        for value in (payload or [])
        if str(value).strip()
    ],
    normalize_stop_loss_dict=lambda payload: dict(payload or {}),
)


class StrategyIntervalAliasStabilityTests(unittest.TestCase):
    def test_strategy_context_canonicalize_interval_collapses_aliases(self):
        window = _StrategyIntervalWindow()

        self.assertEqual("1h", window._canonicalize_interval("60"))
        self.assertEqual("1h", window._canonicalize_interval("60m"))
        self.assertEqual("1h", window._canonicalize_interval("1H"))
        self.assertEqual("1M", window._canonicalize_interval("1month"))
        self.assertEqual("", window._canonicalize_interval("10m"))

    def test_collect_strategy_indicators_matches_alias_equivalent_metadata_interval(self):
        window = _StrategyIntervalWindow()
        window._engine_indicator_map = {
            "btc-1": {
                "symbol": "BTCUSDT",
                "interval": "60",
                "side": "BUY",
                "override_indicators": ["rsi"],
            }
        }

        indicators = window._collect_strategy_indicators("BTCUSDT", "L", {"1H"})

        self.assertEqual(["rsi"], indicators)

    def test_add_selected_override_canonicalizes_alias_equivalent_intervals(self):
        window = _StrategyIntervalWindow()
        symbol_list = QtWidgets.QListWidget()
        interval_list = QtWidgets.QListWidget()
        symbol_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        interval_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        symbol_item = QtWidgets.QListWidgetItem("BTCUSDT")
        interval_item_a = QtWidgets.QListWidgetItem("60m")
        interval_item_b = QtWidgets.QListWidgetItem("1H")
        symbol_list.addItem(symbol_item)
        interval_list.addItem(interval_item_a)
        interval_list.addItem(interval_item_b)
        symbol_item.setSelected(True)
        interval_item_a.setSelected(True)
        interval_item_b.setSelected(True)
        window.override_contexts["runtime"] = {
            "symbol_list": symbol_list,
            "interval_list": interval_list,
            "config_key": "runtime_symbol_interval_pairs",
        }

        window._add_selected_symbol_interval_pairs("runtime")

        self.assertEqual(
            [{"symbol": "BTCUSDT", "interval": "1h"}],
            window.config["runtime_symbol_interval_pairs"],
        )

    def test_remove_selected_override_matches_canonical_interval_alias(self):
        window = _StrategyIntervalWindow()
        window.config["runtime_symbol_interval_pairs"] = [
            {"symbol": "BTCUSDT", "interval": "60m"},
            {"symbol": "ETHUSDT", "interval": "4h"},
        ]
        table = QtWidgets.QTableWidget(2, 2)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        first_symbol = QtWidgets.QTableWidgetItem("BTCUSDT")
        first_symbol.setData(
            QtCore.Qt.ItemDataRole.UserRole,
            {"symbol": "BTCUSDT", "interval": "60m"},
        )
        table.setItem(0, 0, first_symbol)
        table.setItem(0, 1, QtWidgets.QTableWidgetItem("1H"))
        second_symbol = QtWidgets.QTableWidgetItem("ETHUSDT")
        second_symbol.setData(
            QtCore.Qt.ItemDataRole.UserRole,
            {"symbol": "ETHUSDT", "interval": "4h"},
        )
        table.setItem(1, 0, second_symbol)
        table.setItem(1, 1, QtWidgets.QTableWidgetItem("4h"))
        table.selectRow(0)
        window.override_contexts["runtime"] = {
            "table": table,
            "config_key": "runtime_symbol_interval_pairs",
            "column_map": {"Symbol": 0, "Interval": 1},
        }

        window._remove_selected_symbol_interval_pairs("runtime")

        self.assertEqual(
            [{"symbol": "ETHUSDT", "interval": "4h"}],
            window.config["runtime_symbol_interval_pairs"],
        )

    def test_build_strategy_combos_merges_alias_equivalent_intervals(self):
        window = _StrategyIntervalWindow()
        combos = start_collect_runtime._build_strategy_combos(
            window,
            [
                {"symbol": "BTCUSDT", "interval": "60", "indicators": ["rsi"]},
                {"symbol": "BTCUSDT", "interval": "1H", "indicators": ["macd"]},
            ],
            "Futures",
        )

        self.assertEqual(
            [
                {
                    "symbol": "BTCUSDT",
                    "interval": "1h",
                    "indicators": ["macd", "rsi"],
                    "strategy_controls": {},
                }
            ],
            combos,
        )


if __name__ == "__main__":
    unittest.main()
