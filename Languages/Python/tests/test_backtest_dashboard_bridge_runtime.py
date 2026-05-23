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

from app.gui.backtest import bridge_runtime  # noqa: E402


class _StatusLabel:
    def __init__(self) -> None:
        self.text = ""

    def setText(self, value: object) -> None:
        self.text = str(value)


@unittest.skipUnless(
    PYQT_AVAILABLE,
    f"PyQt6 Qt runtime is unavailable in this interpreter: {PYQT_UNAVAILABLE_REASON}",
)
class BacktestDashboardBridgeRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        assert QtWidgets is not None
        app = QtWidgets.QApplication.instance()
        if app is None:
            app = QtWidgets.QApplication([])
        self._app = app

        class _DummyWindow:
            def __init__(self) -> None:
                self.config = {"runtime_symbol_interval_pairs": []}
                self.backtest_config = {}
                self.override_contexts = {
                    "runtime": {"config_key": "runtime_symbol_interval_pairs"}
                }
                self.backtest_results = []
                self.backtest_status_label = _StatusLabel()
                self.logged: list[str] = []
                self.live_controls: dict[str, object] = {}

            def _normalize_backtest_run(self, run):
                return dict(run or {})

            def _override_ctx(self, kind: str):
                return self.override_contexts.get(kind, {})

            def _override_config_list(self, _kind: str):
                return self.config.setdefault("runtime_symbol_interval_pairs", [])

            def _collect_strategy_controls(self, _kind: str):
                return dict(self.live_controls)

            def _normalize_loop_override(self, value):
                return str(value or "").strip()

            def log(self, message):
                self.logged.append(str(message))

        bridge_runtime.bind_main_window_backtest_bridge_runtime(
            _DummyWindow,
            normalize_indicator_values=lambda payload: [
                str(item).strip() for item in (payload or []) if str(item).strip()
            ],
            normalize_stop_loss_dict=lambda payload: dict(payload or {}),
        )
        self.window = _DummyWindow()

    def _result_table(self, payload: dict):
        return self._result_table_rows([payload])

    def _result_table_rows(self, payloads: list[dict]):
        assert QtCore is not None
        assert QtWidgets is not None
        table = QtWidgets.QTableWidget(len(payloads), 1)
        for row, payload in enumerate(payloads):
            item = QtWidgets.QTableWidgetItem(str(payload.get("symbol") or ""))
            item.setData(QtCore.Qt.ItemDataRole.UserRole, dict(payload))
            table.setItem(row, 0, item)
        return table

    def test_backtest_import_adds_optimizer_provenance_to_dashboard_override(self):
        payload = {
            "symbol": "BTCUSDT",
            "interval": "1h",
            "indicator_keys": ["ema", "volume"],
            "logic": "AND",
            "trades": 4,
            "roi_value": 125.0,
            "roi_percent": 12.5,
            "max_drawdown_percent": 3.25,
            "optimizer_rank": 1,
            "optimizer_metric": "roi_percent",
            "optimizer_primary_score": 12.5,
            "optimizer_eligible": True,
            "optimizer_mode": "pairs",
            "optimizer_scope": "top_n",
            "optimizer_mdd_limit": 5.0,
            "optimizer_min_trades": 2,
            "optimizer_candidate_count": 16,
            "optimizer_eligible_count": 6,
            "optimizer_filtered_count": 10,
            "optimizer_run_count": 16,
            "leverage": 3,
        }
        self.window.backtest_results = [dict(payload)]
        self.window.backtest_results_table = self._result_table(payload)

        self.window._backtest_add_selected_to_dashboard(rows=[0])

        entries = self.window.config["runtime_symbol_interval_pairs"]
        self.assertEqual(1, len(entries))
        entry = entries[0]
        self.assertEqual("BTCUSDT", entry["symbol"])
        self.assertEqual(["ema", "volume"], entry["indicators"])
        self.assertEqual(3, entry["leverage"])
        provenance = entry["backtest_result"]
        self.assertEqual("python-backtest", provenance["source"])
        self.assertEqual(1, provenance["optimizer_rank"])
        self.assertEqual("roi_percent", provenance["optimizer_metric"])
        self.assertEqual(12.5, provenance["optimizer_primary_score"])
        self.assertTrue(provenance["optimizer_eligible"])
        self.assertEqual("pairs", provenance["optimizer_mode"])
        self.assertEqual("top_n", provenance["optimizer_scope"])
        self.assertEqual(5.0, provenance["optimizer_mdd_limit"])
        self.assertEqual(2, provenance["optimizer_min_trades"])
        self.assertEqual(16, provenance["optimizer_candidate_count"])
        self.assertEqual(6, provenance["optimizer_eligible_count"])
        self.assertEqual(10, provenance["optimizer_filtered_count"])
        self.assertEqual(16, provenance["optimizer_run_count"])
        self.assertEqual(["ema", "volume"], provenance["indicator_keys"])
        self.assertIn("Added 1 backtest result", self.window.backtest_status_label.text)

    def test_backtest_import_refreshes_existing_override_provenance(self):
        self.window.config["runtime_symbol_interval_pairs"] = [
            {
                "symbol": "BTCUSDT",
                "interval": "1h",
                "indicators": ["ema"],
                "leverage": 5,
                "backtest_result": {"optimizer_rank": 4},
            }
        ]
        payload = {
            "symbol": "BTCUSDT",
            "interval": "1h",
            "indicator_keys": ["ema"],
            "roi_percent": 8.0,
            "optimizer_rank": 1,
            "optimizer_metric": "roi_drawdown",
            "optimizer_primary_score": 2.0,
            "optimizer_eligible": True,
            "leverage": 5,
        }
        self.window.backtest_results = [dict(payload)]
        self.window.backtest_results_table = self._result_table(payload)

        self.window._backtest_add_selected_to_dashboard(rows=[0])

        entries = self.window.config["runtime_symbol_interval_pairs"]
        self.assertEqual(1, len(entries))
        provenance = entries[0]["backtest_result"]
        self.assertEqual(1, provenance["optimizer_rank"])
        self.assertEqual("roi_drawdown", provenance["optimizer_metric"])
        self.assertEqual(2.0, provenance["optimizer_primary_score"])
        self.assertIn("Updated 1 existing", self.window.backtest_status_label.text)

    def test_backtest_import_prefers_result_controls_over_current_ui_snapshot(self):
        payload = {
            "symbol": "BTCUSDT",
            "interval": "1h",
            "indicator_keys": ["ema"],
            "side": "SELL",
            "position_pct": 0.25,
            "position_pct_units": "fraction",
            "leverage": 4,
            "loop_interval_override": "15m",
            "account_mode": "Classic Trading",
            "stop_loss_enabled": True,
            "stop_loss_mode": "percent",
            "stop_loss_scope": "per_trade",
            "stop_loss_percent": 2.5,
        }
        self.window.live_controls = {
            "side": "BUY",
            "position_pct": 99.0,
            "position_pct_units": "percent",
            "leverage": 20,
            "loop_interval_override": "1m",
            "stop_loss": {"enabled": False},
        }
        self.window.backtest_results = [dict(payload)]
        self.window.backtest_results_table = self._result_table(payload)

        self.window._backtest_add_selected_to_dashboard(rows=[0])

        entries = self.window.config["runtime_symbol_interval_pairs"]
        self.assertEqual(1, len(entries))
        entry = entries[0]
        controls = entry["strategy_controls"]
        self.assertEqual("SELL", controls["side"])
        self.assertEqual(0.25, controls["position_pct"])
        self.assertEqual("fraction", controls["position_pct_units"])
        self.assertEqual(4, controls["leverage"])
        self.assertEqual("15m", controls["loop_interval_override"])
        self.assertEqual("Classic Trading", controls["account_mode"])
        self.assertTrue(controls["stop_loss"]["enabled"])
        self.assertEqual("percent", controls["stop_loss"]["mode"])
        self.assertEqual(2.5, controls["stop_loss"]["percent"])
        self.assertEqual(4, entry["leverage"])
        self.assertEqual("SELL", entry["backtest_result"]["side"])
        self.assertEqual("fraction", entry["backtest_result"]["position_pct_units"])

    def test_backtest_import_skips_filtered_optimizer_rows(self):
        rejected = {
            "symbol": "BTCUSDT",
            "interval": "1h",
            "indicator_keys": ["ema"],
            "roi_percent": 4.0,
            "optimizer_rank": None,
            "optimizer_metric": "roi_percent",
            "optimizer_eligible": False,
            "optimizer_rejection_reason": "trades 0 < 1",
        }
        accepted = {
            "symbol": "ETHUSDT",
            "interval": "4h",
            "indicator_keys": ["rsi"],
            "roi_percent": 6.0,
            "optimizer_rank": 1,
            "optimizer_metric": "roi_percent",
            "optimizer_eligible": True,
            "leverage": 2,
        }
        self.window.backtest_results = [dict(rejected), dict(accepted)]
        self.window.backtest_results_table = self._result_table_rows([rejected, accepted])

        self.window._backtest_add_selected_to_dashboard(rows=[0, 1])

        entries = self.window.config["runtime_symbol_interval_pairs"]
        self.assertEqual(1, len(entries))
        self.assertEqual("ETHUSDT", entries[0]["symbol"])
        self.assertEqual(1, entries[0]["backtest_result"]["optimizer_rank"])
        self.assertIn("Added 1 backtest result", self.window.backtest_status_label.text)
        self.assertIn("Skipped 1 filtered optimizer result", self.window.backtest_status_label.text)

    def test_backtest_import_reports_when_only_filtered_optimizer_rows_selected(self):
        rejected = {
            "symbol": "BTCUSDT",
            "interval": "1h",
            "indicator_keys": ["ema"],
            "roi_percent": 4.0,
            "optimizer_eligible": False,
            "optimizer_rejection_reason": "MDD 12.00% > 5.00%",
        }
        self.window.backtest_results = [dict(rejected)]
        self.window.backtest_results_table = self._result_table(rejected)

        self.window._backtest_add_selected_to_dashboard(rows=[0])

        self.assertEqual([], self.window.config["runtime_symbol_interval_pairs"])
        self.assertIn("Skipped 1 filtered optimizer result", self.window.backtest_status_label.text)


if __name__ == "__main__":
    unittest.main()
