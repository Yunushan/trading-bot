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
    from PyQt6 import QtWidgets

    from app.config import build_default_backtest_config, normalize_stop_loss_dict
    from app.gui.backtest import backtest_tab_market_runtime
    from app.gui.backtest import backtest_tab_context_runtime
    from app.gui.backtest import backtest_tab_params_runtime

    PYQT_AVAILABLE = True
    PYQT_UNAVAILABLE_REASON = ""
except Exception as exc:
    PYQT_AVAILABLE = False
    PYQT_UNAVAILABLE_REASON = str(exc)


@unittest.skipUnless(PYQT_AVAILABLE, f"PyQt6 unavailable: {PYQT_UNAVAILABLE_REASON}")
class BacktestMarketLayoutRuntimeTests(unittest.TestCase):
    def test_backtest_market_lists_are_height_bounded(self):
        _app = QtWidgets.QApplication.instance()
        if _app is None:
            _app = QtWidgets.QApplication([])

        class _DummyBacktestWindow:
            def _backtest_symbol_source_changed(self, *_args):
                return None

            def _refresh_backtest_symbols(self):
                return None

            def _backtest_store_symbols(self):
                return None

            def _backtest_store_intervals(self):
                return None

            def _create_override_group(self, _kind, _symbol_list, _interval_list):
                return QtWidgets.QGroupBox("Symbol / Interval Overrides")

        window = _DummyBacktestWindow()
        group = backtest_tab_market_runtime.build_backtest_market_group(window)

        self.assertEqual(group.sizePolicy().verticalPolicy(), QtWidgets.QSizePolicy.Policy.Maximum)
        self.assertEqual(
            window.backtest_symbol_list.minimumHeight(),
            backtest_tab_market_runtime.BACKTEST_MARKET_LIST_MIN_HEIGHT,
        )
        self.assertEqual(
            window.backtest_symbol_list.maximumHeight(),
            backtest_tab_market_runtime.BACKTEST_MARKET_LIST_MAX_HEIGHT,
        )
        self.assertEqual(
            window.backtest_interval_list.minimumHeight(),
            backtest_tab_market_runtime.BACKTEST_MARKET_LIST_MIN_HEIGHT,
        )
        self.assertEqual(
            window.backtest_interval_list.maximumHeight(),
            backtest_tab_market_runtime.BACKTEST_MARKET_LIST_MAX_HEIGHT,
        )


@unittest.skipUnless(PYQT_AVAILABLE, f"PyQt6 unavailable: {PYQT_UNAVAILABLE_REASON}")
class BacktestParamsRuntimeTests(unittest.TestCase):
    def test_max_combo_is_enabled_only_for_combination_optimizer_mode(self):
        _app = QtWidgets.QApplication.instance()
        if _app is None:
            _app = QtWidgets.QApplication([])

        class _DummyBacktestWindow:
            def __init__(self):
                self.config = {"backtest": {}}
                self.backtest_config = build_default_backtest_config()
                self.backtest_config["optimizer_mode"] = "current"

            def _backtest_dates_changed(self, *_args):
                return None

            def _update_backtest_config(self, key, value):
                self.backtest_config[key] = value
                self.config.setdefault("backtest", {})[key] = value

            def _on_backtest_mdd_logic_changed(self, *_args):
                return None

            def _normalize_loop_override(self, value):
                return str(value or "").strip()

            def _on_backtest_loop_changed(self, *_args):
                return None

            def _on_backtest_stop_loss_enabled(self, *_args):
                return None

            def _on_backtest_stop_loss_mode_changed(self, *_args):
                return None

            def _on_backtest_stop_loss_scope_changed(self):
                return None

            def _on_backtest_stop_loss_value_changed(self, *_args):
                return None

            def _update_backtest_stop_loss_widgets(self):
                return None

            def _normalize_assets_mode(self, value):
                return str(value or "Single-Asset")

            def _normalize_account_mode(self, value):
                return str(value or "Classic Trading")

            def _on_backtest_account_mode_changed(self, *_args):
                return None

            def _apply_backtest_account_mode_constraints(self, *_args):
                return None

            def _refresh_backtest_connector_options(self, *_args, **_kwargs):
                self.backtest_connector_combo.addItem("Binance", "binance")

            def _on_backtest_connector_changed(self, *_args):
                return None

            def _run_backtest_scan(self):
                return None

            def _on_backtest_template_enabled(self, *_args):
                return None

            def _on_backtest_template_selected(self, *_args):
                return None

            def _set_backtest_mdd_selection(self, *_args):
                return None

            def _select_backtest_template(self, value, *, update_config=False):
                return value

            def _refresh_backtest_optimizer_estimate(self):
                return backtest_tab_params_runtime.refresh_backtest_optimizer_estimate(self)

        backtest_tab_context_runtime.configure_backtest_tab_context(
            mdd_logic_options=("per_trade", "cumulative", "entire_account"),
            mdd_logic_labels={
                "per_trade": "Per Trade MDD",
                "cumulative": "Cumulative MDD",
                "entire_account": "Entire Account MDD",
            },
            mdd_logic_default="per_trade",
            dashboard_loop_choices=(("Default", ""), ("30 seconds", "30s")),
            stop_loss_mode_order=("usdt", "percent", "both"),
            stop_loss_scope_options=("per_trade", "cumulative"),
            stop_loss_mode_labels={"usdt": "USDT Based Stop", "percent": "Percent Stop", "both": "USDT or Percent"},
            stop_loss_scope_labels={"per_trade": "Per Trade Stop Loss", "cumulative": "Cumulative Stop Loss"},
            side_labels={"BUY": "Buy (Long)", "SELL": "Sell (Short)", "BOTH": "Both (Long/Short)"},
            account_mode_options=("Classic Trading", "Portfolio Margin"),
            backtest_template_definitions={"first_50_volume": {"label": "First 50 Highest Volume"}},
            backtest_template_default={"enabled": False, "name": "first_50_volume"},
            indicator_display_names={},
            symbol_fetch_top_n=200,
            normalize_stop_loss_dict=normalize_stop_loss_dict,
        )

        window = _DummyBacktestWindow()
        group = backtest_tab_params_runtime.build_backtest_params_group(window)

        self.assertFalse(window.backtest_optimizer_combo_size_label.isEnabled())
        self.assertFalse(window.backtest_optimizer_combo_size_spin.isEnabled())

        combinations_idx = window.backtest_optimizer_mode_combo.findData("combinations")
        self.assertGreaterEqual(combinations_idx, 0)
        window.backtest_optimizer_mode_combo.setCurrentIndex(combinations_idx)
        self.assertTrue(window.backtest_optimizer_combo_size_label.isEnabled())
        self.assertTrue(window.backtest_optimizer_combo_size_spin.isEnabled())
        self.assertEqual("combinations", window.backtest_config["optimizer_mode"])

        pairs_idx = window.backtest_optimizer_mode_combo.findData("pairs")
        self.assertGreaterEqual(pairs_idx, 0)
        window.backtest_optimizer_mode_combo.setCurrentIndex(pairs_idx)
        self.assertFalse(window.backtest_optimizer_combo_size_label.isEnabled())
        self.assertFalse(window.backtest_optimizer_combo_size_spin.isEnabled())
        self.assertEqual("pairs", window.backtest_config["optimizer_mode"])
        group.deleteLater()

    def test_optimizer_estimate_label_disables_scan_when_over_limit(self):
        _app = QtWidgets.QApplication.instance()
        if _app is None:
            _app = QtWidgets.QApplication([])

        class _DummyBacktestWindow:
            def __init__(self):
                self.config = {"backtest": {}}
                self.backtest_symbols_all = [f"SYM{i}USDT" for i in range(150)]
                self.backtest_config = build_default_backtest_config()
                self.backtest_config.update(
                    {
                        "intervals": [f"{i}h" for i in range(20)],
                        "optimizer_mode": "combinations",
                        "optimizer_combo_size": 3,
                        "scan_scope": "all_loaded",
                        "indicators": {
                            "rsi": {"enabled": True},
                            "macd": {"enabled": True},
                            "ema": {"enabled": True},
                            "bb": {"enabled": True},
                        },
                    }
                )

            def _backtest_dates_changed(self, *_args):
                return None

            def _update_backtest_config(self, key, value):
                self.backtest_config[key] = value
                self.config.setdefault("backtest", {})[key] = value
                self._refresh_backtest_optimizer_estimate()

            def _on_backtest_mdd_logic_changed(self, *_args):
                return None

            def _normalize_loop_override(self, value):
                return str(value or "").strip()

            def _on_backtest_loop_changed(self, *_args):
                return None

            def _on_backtest_stop_loss_enabled(self, *_args):
                return None

            def _on_backtest_stop_loss_mode_changed(self, *_args):
                return None

            def _on_backtest_stop_loss_scope_changed(self):
                return None

            def _on_backtest_stop_loss_value_changed(self, *_args):
                return None

            def _update_backtest_stop_loss_widgets(self):
                return None

            def _normalize_assets_mode(self, value):
                return str(value or "Single-Asset")

            def _normalize_account_mode(self, value):
                return str(value or "Classic Trading")

            def _on_backtest_account_mode_changed(self, *_args):
                return None

            def _apply_backtest_account_mode_constraints(self, *_args):
                return None

            def _refresh_backtest_connector_options(self, *_args, **_kwargs):
                self.backtest_connector_combo.addItem("Binance", "binance")

            def _on_backtest_connector_changed(self, *_args):
                return None

            def _run_backtest_scan(self):
                return None

            def _on_backtest_template_enabled(self, *_args):
                return None

            def _on_backtest_template_selected(self, *_args):
                return None

            def _set_backtest_mdd_selection(self, *_args):
                return None

            def _select_backtest_template(self, value, *, update_config=False):
                return value

            def _refresh_backtest_optimizer_estimate(self):
                return backtest_tab_params_runtime.refresh_backtest_optimizer_estimate(self)

        window = _DummyBacktestWindow()
        group = backtest_tab_params_runtime.build_backtest_params_group(window)

        self.assertIn("Estimated optimizer runs:", window.backtest_optimizer_estimate_label.text())
        self.assertIn("reduce selection", window.backtest_optimizer_estimate_label.text())
        self.assertFalse(window.backtest_scan_btn.isEnabled())

        selected_idx = window.backtest_scan_scope_combo.findData("selected")
        self.assertGreaterEqual(selected_idx, 0)
        window.backtest_scan_scope_combo.setCurrentIndex(selected_idx)

        self.assertNotIn("reduce selection", window.backtest_optimizer_estimate_label.text())
        self.assertTrue(window.backtest_scan_btn.isEnabled())
        group.deleteLater()


if __name__ == "__main__":
    unittest.main()
