import importlib
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
    from PyQt6 import QtCore as _QtCore, QtWidgets as _QtWidgets  # noqa: F401

    PYQT_AVAILABLE = True
    PYQT_UNAVAILABLE_REASON = ""
except Exception as exc:
    PYQT_AVAILABLE = False
    PYQT_UNAVAILABLE_REASON = str(exc)

if PYQT_AVAILABLE:
    from app.gui.positions import (
        main_window_positions_build_runtime as positions_build_runtime,
        main_window_positions_record_build_runtime as positions_record_build_runtime,
    )
    from app.gui.runtime.account.main_window_account_runtime import (
        bind_main_window_account_runtime as new_bind_account,
    )
    from app.gui.runtime.composition.main_window_bindings_runtime import (
        bind_main_window_class as new_bind_main_window_class,
    )
    from app.gui.runtime.composition.main_window_module_state_runtime import (
        install_main_window_module_state as new_install_main_window_module_state,
    )
    from app.gui.runtime.account.main_window_margin_runtime import (
        _derive_margin_snapshot as new_derive_margin_snapshot,
    )
    from app.gui.runtime.service.main_window_service_api_runtime import (
        bind_main_window_service_api_runtime as new_bind_service_api,
    )
    from app.gui.runtime.service.main_window_session_runtime import (
        bind_main_window_session_runtime as new_bind_session,
    )
    from app.gui.runtime.service.main_window_status_runtime import (
        bind_main_window_status_runtime as new_bind_status,
    )
    from app.gui.runtime.strategy.main_window_control_runtime import (
        bind_main_window_control_runtime as new_bind_control,
        on_leverage_changed as new_on_leverage_changed,
    )
    from app.gui.runtime.strategy.main_window_indicator_runtime import (
        _normalize_trigger_actions_map as new_normalize_trigger_actions_map,
    )
    from app.gui.runtime.strategy.main_window_override_runtime import (
        bind_main_window_override_runtime as new_bind_override,
        _remove_selected_symbol_interval_pairs as new_remove_selected_symbol_interval_pairs,
    )
    from app.gui.runtime.strategy.main_window_stop_strategy_runtime import (
        stop_strategy_sync as new_stop_strategy_sync,
    )
    from app.gui.runtime.strategy.main_window_start_strategy_runtime import (
        start_strategy as new_start_strategy,
    )
    from app.gui.runtime.strategy.main_window_stop_loss_runtime import (
        bind_main_window_stop_loss_runtime as new_bind_stop_loss,
        _runtime_stop_loss_update as new_runtime_stop_loss_update,
    )
    from app.gui.runtime.strategy.main_window_strategy_ui_runtime import (
        bind_main_window_strategy_ui_runtime as new_bind_strategy_ui,
        _normalize_loop_override as new_normalize_loop_override,
    )
    from app.gui.runtime.strategy.main_window_strategy_controls_runtime import (
        bind_main_window_strategy_controls_runtime as new_bind_strategy_controls,
        _normalize_position_pct_units as new_normalize_position_pct_units,
    )
    from app.gui.runtime.ui.main_window_tab_runtime import (
        _code_tab_visibility_auto_prepare_cpp_enabled as new_code_tab_visibility_auto_prepare_cpp_enabled,
        bind_main_window_tab_runtime as new_bind_tab,
    )
    from app.gui.runtime.ui.main_window_theme_runtime import (
        bind_main_window_theme_runtime as new_bind_theme,
    )
    from app.gui.runtime.ui.main_window_theme_styles import LIGHT_THEME as new_light_theme
    from app.gui.runtime.window.main_window_bootstrap_runtime import (
        _compute_global_pnl_totals as new_compute_global_pnl_totals,
        _initialize_main_window_state as new_initialize_main_window_state,
        bind_main_window_bootstrap_runtime as new_bind_bootstrap,
    )
    from app.gui.runtime.window.main_window_runtime import (
        _allow_guard_bypass as new_allow_guard_bypass,
        _mw_interval_sort_key as new_interval_sort_key,
        bind_main_window_runtime as new_bind_runtime,
    )
    from app.gui.runtime.window.window_webengine_guard_runtime import (
        schedule_webengine_runtime_prewarm as new_schedule_webengine_runtime_prewarm,
    )


@unittest.skipUnless(
    PYQT_AVAILABLE,
    f"PyQt6 Qt runtime is unavailable in this interpreter: {PYQT_UNAVAILABLE_REASON}",
)
class GuiRuntimePackageSplitSmokeTests(unittest.TestCase):
    def test_final_gui_runtime_subpackages_expose_expected_objects(self):
        binders = [
            new_bind_account,
            new_bind_main_window_class,
            new_install_main_window_module_state,
            new_bind_service_api,
            new_bind_session,
            new_bind_status,
            new_bind_control,
            new_bind_override,
            new_bind_stop_loss,
            new_bind_strategy_controls,
            new_bind_strategy_ui,
            new_bind_tab,
            new_bind_theme,
            new_bind_bootstrap,
            new_bind_runtime,
        ]
        for binder in binders:
            self.assertTrue(callable(binder))

        helpers = [
            new_start_strategy,
            new_normalize_loop_override,
            new_on_leverage_changed,
            new_runtime_stop_loss_update,
            new_derive_margin_snapshot,
            new_stop_strategy_sync,
            new_normalize_trigger_actions_map,
            new_initialize_main_window_state,
            new_compute_global_pnl_totals,
            new_remove_selected_symbol_interval_pairs,
            new_normalize_position_pct_units,
            new_code_tab_visibility_auto_prepare_cpp_enabled,
            new_schedule_webengine_runtime_prewarm,
            new_allow_guard_bypass,
            new_interval_sort_key,
        ]
        for helper in helpers:
            self.assertTrue(callable(helper))

        self.assertTrue(new_light_theme)

    def test_removed_intermediate_gui_runtime_modules_raise_import_error(self):
        removed_modules = [
            "app.gui.runtime.main_window_account_runtime",
            "app.gui.runtime.main_window_balance_runtime",
            "app.gui.runtime.main_window_bindings_runtime",
            "app.gui.runtime.main_window_bootstrap_runtime",
            "app.gui.runtime.main_window_control_runtime",
            "app.gui.runtime.main_window_indicator_runtime",
            "app.gui.runtime.main_window_init_finalize_runtime",
            "app.gui.runtime.main_window_init_ui_runtime",
            "app.gui.runtime.main_window_margin_runtime",
            "app.gui.runtime.main_window_module_state_runtime",
            "app.gui.runtime.main_window_override_runtime",
            "app.gui.runtime.main_window_runtime",
            "app.gui.runtime.main_window_secondary_tabs_runtime",
            "app.gui.runtime.main_window_service_api_runtime",
            "app.gui.runtime.main_window_session_runtime",
            "app.gui.runtime.main_window_start_strategy_runtime",
            "app.gui.runtime.main_window_startup_runtime",
            "app.gui.runtime.main_window_status_runtime",
            "app.gui.runtime.main_window_stop_loss_runtime",
            "app.gui.runtime.main_window_stop_strategy_runtime",
            "app.gui.runtime.main_window_strategy_context_runtime",
            "app.gui.runtime.main_window_strategy_controls_runtime",
            "app.gui.runtime.main_window_strategy_ui_runtime",
            "app.gui.runtime.main_window_tab_runtime",
            "app.gui.runtime.main_window_theme_runtime",
            "app.gui.runtime.main_window_theme_styles",
            "app.gui.runtime.main_window_ui_misc_runtime",
            "app.gui.runtime.main_window_window_events_runtime",
            "app.gui.runtime.window_code_tab_suppression_runtime",
            "app.gui.runtime.window_runtime",
            "app.gui.runtime.window_webengine_guard_runtime",
            "app.gui.runtime.window.window_runtime",
        ]

        for module_name in removed_modules:
            with self.subTest(module_name=module_name):
                with self.assertRaises(ModuleNotFoundError):
                    importlib.import_module(module_name)

    def test_main_window_still_exposes_bound_helpers(self):
        from app.gui.main_window import MainWindow

        expected_methods = [
            "_initialize_main_window_state",
            "_update_positions_balance_labels",
            "update_balance_label",
            "_refresh_desktop_service_api_ui",
            "_mark_session_active",
            "_sync_runtime_state",
            "start_strategy",
            "stop_strategy_async",
            "_stop_strategy_sync",
            "_override_ctx",
            "_collect_strategy_controls",
            "_on_dashboard_template_changed",
            "_apply_lead_trader_state",
            "_runtime_stop_loss_update",
            "apply_theme",
            "closeEvent",
        ]
        for method_name in expected_methods:
            with self.subTest(method_name=method_name):
                self.assertTrue(hasattr(MainWindow, method_name))
                self.assertTrue(callable(getattr(MainWindow, method_name)))

    def test_positions_build_runtime_shim_still_exposes_record_build_helpers(self):
        helpers = [
            positions_build_runtime._copy_allocations_for_key,
            positions_build_runtime._seed_positions_map_from_rows,
            positions_build_runtime._apply_interval_metadata_to_row,
            positions_build_runtime._merge_futures_rows_into_positions_map,
            positions_build_runtime._gui_on_positions_ready,
            positions_record_build_runtime.copy_allocations_for_key,
            positions_record_build_runtime.seed_positions_map_from_rows,
            positions_record_build_runtime.apply_interval_metadata_to_row,
            positions_record_build_runtime.merge_futures_rows_into_positions_map,
            positions_record_build_runtime._gui_on_positions_ready,
        ]
        for helper in helpers:
            self.assertTrue(callable(helper))

    def test_main_window_module_globals_still_expose_expected_runtime_state(self):
        import app.gui.main_window as main_window_module

        self.assertTrue(main_window_module.CONNECTOR_OPTIONS)
        self.assertEqual(
            main_window_module.DEFAULT_CONNECTOR_BACKEND,
            main_window_module.CONNECTOR_OPTIONS[0][1],
        )
        self.assertEqual(main_window_module.SIDE_LABEL_LOOKUP["buy (long)"], "BUY")
        self.assertEqual(main_window_module.TRADINGVIEW_INTERVAL_MAP["1h"], "60")
        self.assertIn("Classic Trading", main_window_module.ACCOUNT_MODE_OPTIONS)
        self.assertGreaterEqual(main_window_module._SYMBOL_FETCH_TOP_N, 50)

    def test_remove_selected_overrides_keeps_unaffected_entry_metadata(self):
        from PyQt6 import QtCore, QtWidgets

        app = QtWidgets.QApplication.instance()
        if app is None:
            app = QtWidgets.QApplication([])

        class _DummyOverrideWindow:
            def __init__(self):
                self._bot_active = False
                self.config = {"runtime_symbol_interval_pairs": []}
                self.backtest_config = {}
                self.override_contexts = {}
                self.logged = []

            def _normalize_strategy_controls(self, _kind, controls):
                return dict(controls or {})

            def _normalize_loop_override(self, value):
                return str(value or "").strip() or ""

            def _log_override_debug(self, *_args, **_kwargs):
                return None

            def log(self, message):
                self.logged.append(str(message))

        new_bind_override(
            _DummyOverrideWindow,
            format_indicator_list=lambda values: ", ".join(str(v) for v in values),
            normalize_connector_backend=lambda value: value,
            normalize_indicator_values=lambda payload: list(payload or []),
            normalize_stop_loss_dict=lambda payload: dict(payload or {}),
        )

        window = _DummyOverrideWindow()
        entry_remove = {
            "symbol": "BTCUSDT",
            "interval": "1h",
            "indicators": ["rsi"],
            "strategy_controls": {
                "side": "BUY",
                "leverage": 3,
                "connector_backend": "ccxt",
                "stop_loss": {"enabled": True, "mode": "usdt", "scope": "per_trade", "usdt": 25},
            },
            "leverage": 3,
        }
        entry_keep = {
            "symbol": "ETHUSDT",
            "interval": "4h",
            "indicators": ["ema", "macd"],
            "strategy_controls": {
                "side": "SELL",
                "leverage": 7,
                "connector_backend": "binance-sdk-spot",
                "stop_loss": {"enabled": True, "mode": "percent", "scope": "cumulative", "percent": 4.5},
            },
            "loop_interval_override": "15m",
            "connector_backend": "binance-sdk-spot",
            "stop_loss": {"enabled": True, "mode": "percent", "scope": "cumulative", "percent": 4.5},
            "leverage": 7,
        }
        window.config["runtime_symbol_interval_pairs"] = [dict(entry_remove), dict(entry_keep)]

        table = QtWidgets.QTableWidget(2, 2)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)

        first_symbol = QtWidgets.QTableWidgetItem("BTCUSDT")
        first_symbol.setData(QtCore.Qt.ItemDataRole.UserRole, dict(entry_remove))
        table.setItem(0, 0, first_symbol)
        table.setItem(0, 1, QtWidgets.QTableWidgetItem("1h"))

        second_symbol = QtWidgets.QTableWidgetItem("ETHUSDT")
        second_symbol.setData(QtCore.Qt.ItemDataRole.UserRole, dict(entry_keep))
        table.setItem(1, 0, second_symbol)
        table.setItem(1, 1, QtWidgets.QTableWidgetItem("4h"))
        table.selectRow(0)

        window.override_contexts["runtime"] = {
            "table": table,
            "config_key": "runtime_symbol_interval_pairs",
            "column_map": {"Symbol": 0, "Interval": 1},
        }

        refresh_calls = []
        window._refresh_symbol_interval_pairs = lambda kind="runtime": refresh_calls.append(kind)

        new_remove_selected_symbol_interval_pairs(window, "runtime")

        self.assertEqual(refresh_calls, ["runtime"])
        self.assertEqual(len(window.config["runtime_symbol_interval_pairs"]), 1)
        remaining = window.config["runtime_symbol_interval_pairs"][0]
        self.assertEqual(remaining["symbol"], "ETHUSDT")
        self.assertEqual(remaining["interval"], "4h")
        self.assertEqual(remaining.get("indicators"), ["ema", "macd"])
        self.assertEqual(remaining.get("loop_interval_override"), "15m")
        self.assertEqual(remaining.get("leverage"), 7)
        self.assertEqual(remaining.get("connector_backend"), "binance-sdk-spot")
        self.assertIn("strategy_controls", remaining)
        self.assertEqual(remaining["strategy_controls"].get("connector_backend"), "binance-sdk-spot")
        self.assertTrue(remaining["strategy_controls"].get("stop_loss", {}).get("enabled"))

    def test_start_strategy_merges_runtime_pairs_and_records_indicator_state(self):
        class _Value:
            def __init__(self, value):
                self._value = value

            def text(self):
                return str(self._value)

            def currentText(self):
                return str(self._value)

            def value(self):
                return self._value

        class _Guard:
            def __init__(self):
                self.allow_opposite = False
                self.strict_symbol_side = True
                self.attached_wrapper = None
                self.reset_called = False
                self.reconcile_calls = []

            def attach_wrapper(self, wrapper):
                self.attached_wrapper = wrapper

            def reset(self):
                self.reset_called = True

            def reconcile_with_exchange(self, wrapper, jobs, *, account_type):
                self.reconcile_calls.append((wrapper, list(jobs), account_type))

            def can_open(self, *_args, **_kwargs):
                return True

        class _Wrapper:
            def __init__(self):
                self.account_type = ""
                self.indicator_source = ""

            def get_futures_dual_side(self):
                return True

        class _Engine:
            resume_calls = 0
            instances = []

            @classmethod
            def resume_trading(cls):
                cls.resume_calls += 1

            @classmethod
            def concurrent_limit(cls, total_jobs):
                return total_jobs

            def __init__(
                self,
                wrapper,
                config,
                *,
                log_callback=None,
                trade_callback=None,
                loop_interval_override=None,
                can_open_callback=None,
            ):
                self.wrapper = wrapper
                self.config = config
                self.log_callback = log_callback
                self.trade_callback = trade_callback
                self.loop_interval_override = loop_interval_override
                self.can_open_callback = can_open_callback
                self.guard = None
                self.started = False
                type(self).instances.append(self)

            def set_guard(self, guard):
                self.guard = guard

            def start(self):
                self.started = True

            def is_alive(self):
                return self.started

        class _DummyStartWindow:
            def __init__(self):
                self.logged = []
                self.service_starts = []
                self.sync_snapshot_calls = 0
                self.sync_runtime_state_calls = 0
                self.created_wrappers = []
                self._engine_indicator_map = {}
                self.strategy_engines = {}
                self.shared_binance = None
                self.guard = _Guard()
                self._is_stopping_engines = False
                self.loop_combo = None
                self.account_combo = _Value("Futures")
                self.api_key_edit = _Value("key")
                self.api_secret_edit = _Value("secret")
                self.mode_combo = _Value("Testnet")
                self.leverage_spin = _Value(5)
                self.margin_mode_combo = _Value("Isolated")
                self.ind_source_combo = _Value("mark")
                self.pospct_spin = _Value(25.0)
                self.config = {
                    "allow_opposite_positions": False,
                    "position_pct": 100.0,
                    "stop_loss": {"enabled": False},
                    "indicators": {
                        "rsi": {"enabled": False},
                        "macd": {"enabled": False},
                    },
                    "runtime_symbol_interval_pairs": [
                        {
                            "symbol": "BTCUSDT",
                            "interval": "1h",
                            "indicators": ["rsi"],
                            "strategy_controls": {
                                "side": "BUY",
                                "leverage": 3,
                                "loop_interval_override": "15m",
                            },
                        },
                        {
                            "symbol": "BTCUSDT",
                            "interval": "1h",
                            "indicators": ["macd"],
                            "strategy_controls": {
                                "stop_loss": {
                                    "enabled": True,
                                    "mode": "percent",
                                    "scope": "per_trade",
                                    "percent": 2.5,
                                }
                            },
                        },
                    ],
                }

            def log(self, message):
                self.logged.append(str(message))

            def _loop_choice_value(self, _combo):
                return ""

            def _override_ctx(self, _kind):
                return {}

            def _canonicalize_interval(self, value):
                value_text = str(value or "").strip()
                return value_text if value_text in {"1h", "4h"} else ""

            def _normalize_strategy_controls(self, _kind, controls):
                return dict(controls or {})

            def _connector_label_text(self, backend):
                return f"Connector {backend}"

            def _runtime_connector_backend(self, suppress_refresh=False):
                self.logged.append(f"connector-backend:{suppress_refresh}")
                return "binance-sdk"

            def _sync_service_config_snapshot(self):
                self.sync_snapshot_calls += 1

            def _service_request_start(self, **payload):
                self.service_starts.append(dict(payload))

            def _create_binance_wrapper(self, **kwargs):
                self.created_wrappers.append(dict(kwargs))
                return _Wrapper()

            def _normalize_position_pct_units(self, value):
                return str(value or "").strip().lower()

            def _resolve_dashboard_side(self):
                return "BOTH"

            def _normalize_account_mode(self, value):
                return str(value)

            def _normalize_loop_override(self, value):
                return str(value or "").strip()

            def _get_selected_indicator_keys(self, _kind):
                return ["ema"]

            def _on_trade_signal(self, *_args, **_kwargs):
                return None

            def _format_strategy_controls_summary(self, _kind, controls):
                return f"side={controls.get('side', 'BOTH')}"

            def _sync_runtime_state(self):
                self.sync_runtime_state_calls += 1

            def _service_mark_start_failed(self, **_kwargs):
                raise AssertionError("start should not be marked failed")

        window = _DummyStartWindow()
        _Engine.instances = []
        _Engine.resume_calls = 0

        new_start_strategy(
            window,
            strategy_engine_cls=_Engine,
            make_engine_key=lambda symbol, interval, indicators: (
                f"{symbol}:{interval}|{','.join(indicators or [])}"
            ),
            coerce_bool=lambda value, default=False: default if value is None else bool(value),
            normalize_stop_loss_dict=lambda payload: dict(payload or {}),
            format_indicator_list=lambda values: ", ".join(values or []),
        )

        self.assertEqual(_Engine.resume_calls, 1)
        self.assertEqual(window.sync_snapshot_calls, 1)
        self.assertEqual(window.sync_runtime_state_calls, 1)
        self.assertEqual(len(window.service_starts), 1)
        self.assertEqual(window.service_starts[0]["requested_job_count"], 1)
        self.assertEqual(len(window.created_wrappers), 1)
        self.assertEqual(len(_Engine.instances), 1)

        engine = _Engine.instances[0]
        self.assertTrue(engine.started)
        self.assertIs(engine.guard, window.guard)
        self.assertEqual(engine.loop_interval_override, "15m")
        self.assertEqual(engine.config["symbol"], "BTCUSDT")
        self.assertEqual(engine.config["interval"], "1h")
        self.assertEqual(engine.config["side"], "BUY")
        self.assertEqual(engine.config["leverage"], 3)
        self.assertTrue(engine.config["stop_loss"]["enabled"])
        self.assertEqual(window.shared_binance.account_type, "FUTURES")
        self.assertEqual(window.shared_binance.indicator_source, "mark")
        self.assertIs(window.guard.attached_wrapper, window.shared_binance)
        self.assertTrue(window.guard.reset_called)
        self.assertEqual(len(window.guard.reconcile_calls), 1)
        self.assertFalse(window.guard.allow_opposite)
        self.assertFalse(window.guard.strict_symbol_side)

        self.assertEqual(len(window.strategy_engines), 1)
        engine_key = next(iter(window.strategy_engines))
        self.assertEqual(engine_key, "BTCUSDT:1h|macd,rsi")
        self.assertIn(engine_key, window._engine_indicator_map)
        indicator_state = window._engine_indicator_map[engine_key]
        self.assertEqual(indicator_state["override_indicators"], ["macd", "rsi"])
        self.assertEqual(indicator_state["configured_indicators"], ["macd", "rsi"])
        self.assertTrue(indicator_state["stop_loss_enabled"])
        self.assertTrue(any("Loop start for BTCUSDT:1h|macd,rsi" in msg for msg in window.logged))

    def test_stop_loss_runtime_and_backtest_widgets_stay_in_sync(self):
        from PyQt6 import QtWidgets

        app = QtWidgets.QApplication.instance()
        if app is None:
            app = QtWidgets.QApplication([])

        class _DummyStopLossWindow:
            def __init__(self):
                self._bot_active = False
                self.config = {"stop_loss": {}, "backtest": {}}
                self.backtest_config = {"stop_loss": {}}

        new_bind_stop_loss(
            _DummyStopLossWindow,
            normalize_stop_loss_dict=lambda payload: dict(payload or {}),
            stop_loss_mode_order=("usdt", "percent", "both"),
            stop_loss_scope_options=("per_trade", "cumulative"),
        )

        window = _DummyStopLossWindow()

        window.stop_loss_enable_cb = QtWidgets.QCheckBox()
        window.stop_loss_mode_combo = QtWidgets.QComboBox()
        window.stop_loss_mode_combo.addItem("USDT", "usdt")
        window.stop_loss_mode_combo.addItem("Percent", "percent")
        window.stop_loss_mode_combo.addItem("Both", "both")
        window.stop_loss_usdt_spin = QtWidgets.QDoubleSpinBox()
        window.stop_loss_percent_spin = QtWidgets.QDoubleSpinBox()
        window.stop_loss_scope_combo = QtWidgets.QComboBox()
        window.stop_loss_scope_combo.addItem("Per Trade", "per_trade")
        window.stop_loss_scope_combo.addItem("Cumulative", "cumulative")

        window.backtest_stop_loss_enable_cb = QtWidgets.QCheckBox()
        window.backtest_stop_loss_mode_combo = QtWidgets.QComboBox()
        window.backtest_stop_loss_mode_combo.addItem("USDT", "usdt")
        window.backtest_stop_loss_mode_combo.addItem("Percent", "percent")
        window.backtest_stop_loss_mode_combo.addItem("Both", "both")
        window.backtest_stop_loss_usdt_spin = QtWidgets.QDoubleSpinBox()
        window.backtest_stop_loss_percent_spin = QtWidgets.QDoubleSpinBox()
        window.backtest_stop_loss_scope_combo = QtWidgets.QComboBox()
        window.backtest_stop_loss_scope_combo.addItem("Per Trade", "per_trade")
        window.backtest_stop_loss_scope_combo.addItem("Cumulative", "cumulative")

        window._runtime_stop_loss_update(
            enabled=True,
            mode="both",
            scope="cumulative",
            usdt=12.5,
            percent=3.5,
        )
        window._update_runtime_stop_loss_widgets()

        self.assertTrue(window.stop_loss_enable_cb.isChecked())
        self.assertEqual(window.stop_loss_mode_combo.currentData(), "both")
        self.assertEqual(window.stop_loss_scope_combo.currentData(), "cumulative")
        self.assertAlmostEqual(window.stop_loss_usdt_spin.value(), 12.5)
        self.assertAlmostEqual(window.stop_loss_percent_spin.value(), 3.5)
        self.assertTrue(window.stop_loss_mode_combo.isEnabled())
        self.assertTrue(window.stop_loss_usdt_spin.isEnabled())
        self.assertTrue(window.stop_loss_percent_spin.isEnabled())

        window._bot_active = True
        window._update_runtime_stop_loss_widgets()
        self.assertFalse(window.stop_loss_mode_combo.isEnabled())
        self.assertFalse(window.stop_loss_usdt_spin.isEnabled())
        self.assertFalse(window.stop_loss_percent_spin.isEnabled())

        window._backtest_stop_loss_update(
            enabled=True,
            mode="percent",
            scope="per_trade",
            usdt=7.0,
            percent=1.25,
        )
        window._update_backtest_stop_loss_widgets()

        self.assertTrue(window.backtest_stop_loss_enable_cb.isChecked())
        self.assertEqual(window.backtest_stop_loss_mode_combo.currentData(), "percent")
        self.assertEqual(window.backtest_stop_loss_scope_combo.currentData(), "per_trade")
        self.assertAlmostEqual(window.backtest_stop_loss_percent_spin.value(), 1.25)
        self.assertFalse(window.backtest_stop_loss_usdt_spin.isEnabled())
        self.assertTrue(window.backtest_stop_loss_percent_spin.isEnabled())
        self.assertEqual(window.backtest_config["stop_loss"]["mode"], "percent")
        self.assertEqual(window.config["backtest"]["stop_loss"]["scope"], "per_trade")

    def test_on_leverage_changed_updates_runtime_config_and_wrapper(self):
        class _Combo:
            def currentText(self):
                return "Futures"

        class _Wrapper:
            def __init__(self):
                self.values = []

            def set_futures_leverage(self, value):
                self.values.append(int(value))

        class _Engine:
            def __init__(self, config):
                self.config = config

        class _DummyControlWindow:
            def __init__(self):
                self.config = {"leverage": 1}
                self.strategy_engines = {
                    "a": _Engine({"leverage": 1}),
                    "b": _Engine({"leverage": 2}),
                }
                self.shared_binance = _Wrapper()
                self.account_combo = _Combo()

        window = _DummyControlWindow()
        new_on_leverage_changed(window, 9)

        self.assertEqual(window.config["leverage"], 9)
        self.assertEqual(window.strategy_engines["a"].config["leverage"], 9)
        self.assertEqual(window.strategy_engines["b"].config["leverage"], 9)
        self.assertEqual(window.shared_binance.values, [9])


if __name__ == "__main__":
    unittest.main()
