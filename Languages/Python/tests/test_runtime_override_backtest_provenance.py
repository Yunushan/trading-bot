from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import QtCore, QtWidgets

    PYQT_AVAILABLE = True
    PYQT_UNAVAILABLE_REASON = ""
except Exception as exc:
    QtCore = None
    QtWidgets = None
    PYQT_AVAILABLE = False
    PYQT_UNAVAILABLE_REASON = str(exc)

from app.gui.runtime.strategy.override_runtime import bind_main_window_override_runtime  # noqa: E402


class _DummyOverrideWindow:
    def __init__(self, entries: list[dict] | None = None) -> None:
        self._bot_active = False
        self.config = {"runtime_symbol_interval_pairs": list(entries or [])}
        self.backtest_config = {}
        self.override_contexts = {}
        self.logged: list[str] = []

    def _normalize_strategy_controls(self, _kind: str, controls):
        return dict(controls or {})

    def _normalize_loop_override(self, value):
        return str(value or "").strip()

    def _log_override_debug(self, *_args, **_kwargs):
        return None

    def _runtime_connector_backend(self, suppress_refresh=False):
        self.logged.append(f"runtime-connector:{suppress_refresh}")
        return "binance-sdk"

    def _backtest_connector_backend(self):
        return "binance-sdk"

    def _connector_label_text(self, backend):
        return str(backend)

    def _format_strategy_controls_summary(self, _kind: str, controls):
        if not controls:
            return "-"
        return ", ".join(f"{key}={value}" for key, value in sorted(controls.items()))

    def log(self, message):
        self.logged.append(str(message))


@unittest.skipUnless(
    PYQT_AVAILABLE,
    f"PyQt6 Qt runtime is unavailable in this interpreter: {PYQT_UNAVAILABLE_REASON}",
)
class RuntimeOverrideBacktestProvenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        assert QtWidgets is not None
        app = QtWidgets.QApplication.instance()
        if app is None:
            app = QtWidgets.QApplication([])
        self._app = app

        bind_main_window_override_runtime(
            _DummyOverrideWindow,
            format_indicator_list=lambda values: ", ".join(str(v) for v in values or []),
            normalize_connector_backend=lambda value: value,
            normalize_indicator_values=lambda payload: list(payload or []),
            normalize_stop_loss_dict=lambda payload: dict(payload or {}),
        )

    def _build_group(self, window: _DummyOverrideWindow):
        assert QtWidgets is not None
        symbol_list = QtWidgets.QListWidget()
        interval_list = QtWidgets.QListWidget()
        group = window._create_override_group("runtime", symbol_list, interval_list)
        window._test_group = group
        return group

    def test_refresh_preserves_backtest_provenance_and_renders_summary(self):
        entry = {
            "symbol": "btcusdt",
            "interval": "1h",
            "indicators": ["ema", "volume"],
            "leverage": 3,
            "backtest_result": {
                "source": "python-backtest",
                "optimizer_rank": 1,
                "optimizer_metric": "roi_percent",
                "roi_percent": 12.5,
                "max_drawdown_percent": 3.25,
                "trades": 4,
            },
        }
        window = _DummyOverrideWindow([entry])

        self._build_group(window)

        table = window.override_contexts["runtime"]["table"]
        column_map = window.override_contexts["runtime"]["column_map"]
        backtest_col = column_map["Backtest"]
        self.assertEqual(1, table.rowCount())
        rendered = table.item(0, backtest_col).text()
        self.assertIn("Rank 1", rendered)
        self.assertIn("ROI 12.5%", rendered)
        self.assertIn("DD 3.25%", rendered)
        cleaned_entry = window.config["runtime_symbol_interval_pairs"][0]
        self.assertEqual("BTCUSDT", cleaned_entry["symbol"])
        self.assertEqual(
            "python-backtest",
            cleaned_entry["backtest_result"]["source"],
        )
        self.assertEqual(1, cleaned_entry["backtest_result"]["optimizer_rank"])
        assert QtCore is not None
        stored_row = table.item(0, column_map["Symbol"]).data(
            QtCore.Qt.ItemDataRole.UserRole
        )
        self.assertEqual(1, stored_row["backtest_result"]["optimizer_rank"])

    def test_remove_selected_override_keeps_remaining_backtest_provenance(self):
        remove_entry = {
            "symbol": "BTCUSDT",
            "interval": "1h",
            "indicators": ["rsi"],
        }
        keep_entry = {
            "symbol": "ETHUSDT",
            "interval": "4h",
            "indicators": ["ema"],
            "backtest_result": {
                "source": "python-backtest",
                "optimizer_rank": 2,
                "roi_percent": 7.25,
            },
        }
        window = _DummyOverrideWindow([remove_entry, keep_entry])
        self._build_group(window)
        table = window.override_contexts["runtime"]["table"]
        column_map = window.override_contexts["runtime"]["column_map"]
        symbol_col = column_map["Symbol"]

        remove_row = None
        for row in range(table.rowCount()):
            item = table.item(row, symbol_col)
            if item and item.text() == "BTCUSDT":
                remove_row = row
                break
        self.assertIsNotNone(remove_row)
        table.selectRow(remove_row)
        window._remove_selected_symbol_interval_pairs("runtime")

        entries = window.config["runtime_symbol_interval_pairs"]
        self.assertEqual(1, len(entries))
        self.assertEqual("ETHUSDT", entries[0]["symbol"])
        self.assertEqual(2, entries[0]["backtest_result"]["optimizer_rank"])
        self.assertEqual(7.25, entries[0]["backtest_result"]["roi_percent"])


if __name__ == "__main__":
    unittest.main()
