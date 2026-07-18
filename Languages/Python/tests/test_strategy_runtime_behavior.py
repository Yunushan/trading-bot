from __future__ import annotations

import sys
import unittest
from pathlib import Path

try:
    import pandas as pd

    PANDAS_AVAILABLE = True
except Exception:
    pd = None
    PANDAS_AVAILABLE = False


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import build_default_config  # noqa: E402
from app.core.strategy import StrategyEngine  # noqa: E402
from app.core.strategy.positions.strategy_close_opposite_ledger_runtime import (  # noqa: E402
    _close_interval_side_entries,
)
from app.core.strategy.runtime.strategy_cycle_risk_stop_context_runtime import (  # noqa: E402
    build_futures_stop_state,
    ensure_futures_leg_entry_price,
)
from app.core.strategy.runtime.strategy_cycle_risk_stop_runtime import (  # noqa: E402
    apply_futures_cycle_risk_management,
)
from app.core.strategy.runtime.strategy_cycle_risk_stop_directional_runtime import (  # noqa: E402
    _apply_long_futures_stop,
)
from app.core.strategy.runtime.strategy_cycle_risk_stop_cumulative_runtime import (  # noqa: E402
    apply_cumulative_futures_stop_management,
)


class _FakeStrategyBinance:
    account_type = "FUTURES"

    def __init__(self) -> None:
        self.net_amt = 0.0

    def get_total_usdt_value(self):
        return 1000.0

    def get_futures_balance_snapshot(self, force_refresh=False):  # noqa: ARG002
        return {"total": "1000", "wallet": "1000", "available": "1000"}

    def get_futures_balance_usdt(self):
        return 1000.0

    def get_total_wallet_balance(self):
        return 1000.0

    def get_futures_symbol_filters(self, _symbol):
        return {"minNotional": 0.0, "minQty": 0.0}

    def adjust_qty_to_filters_futures(self, _symbol, qty, _price):
        return float(qty), None

    def get_futures_dual_side(self):
        return False

    def get_net_futures_position_amt(self, _symbol):
        return self.net_amt


def _build_engine(*, wrapper=None, logs=None):
    config = build_default_config()
    config["symbol"] = "BTCUSDT"
    config["interval"] = "1m"
    config["account_type"] = "FUTURES"
    config["side"] = "BOTH"
    config["leverage"] = 5
    config["position_pct"] = 25
    config["position_pct_units"] = "percent"
    sink = logs if logs is not None else []
    return StrategyEngine(
        wrapper or _FakeStrategyBinance(),
        config,
        log_callback=sink.append,
    )


class StrategyRuntimeBehaviorTests(unittest.TestCase):
    def setUp(self):
        StrategyEngine._GLOBAL_SHUTDOWN.clear()
        StrategyEngine._GLOBAL_PAUSE.clear()
        with StrategyEngine._CONNECTOR_ORDER_BLOCK_LOCK:
            StrategyEngine._CONNECTOR_ORDER_BLOCK_EVENTS.clear()
            StrategyEngine._CONNECTOR_ORDER_CIRCUIT_OPEN = False

    def tearDown(self):
        StrategyEngine._GLOBAL_SHUTDOWN.clear()
        StrategyEngine._GLOBAL_PAUSE.clear()
        with StrategyEngine._CONNECTOR_ORDER_BLOCK_LOCK:
            StrategyEngine._CONNECTOR_ORDER_BLOCK_EVENTS.clear()
            StrategyEngine._CONNECTOR_ORDER_CIRCUIT_OPEN = False

    def test_pause_resume_and_shutdown_fail_closed_with_connector_circuit_reset(self):
        engine = _build_engine()
        StrategyEngine._CONNECTOR_ORDER_BLOCK_EVENTS.append({"reason": "network"})
        StrategyEngine._CONNECTOR_ORDER_CIRCUIT_OPEN = True

        StrategyEngine.pause_trading()
        self.assertTrue(engine.stopped())

        StrategyEngine.resume_trading()
        self.assertFalse(engine.stopped())
        self.assertEqual([], StrategyEngine._CONNECTOR_ORDER_BLOCK_EVENTS)
        self.assertFalse(StrategyEngine._CONNECTOR_ORDER_CIRCUIT_OPEN)

        StrategyEngine.pause_trading()
        StrategyEngine.request_shutdown()
        StrategyEngine.resume_trading()
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())
        self.assertTrue(engine.stopped())

    def test_network_outage_uses_bounded_backoff_and_escalates_once_when_connector_requested_close(self):
        logs: list[str] = []
        wrapper = _FakeStrategyBinance()
        wrapper._network_emergency_dispatched = True
        emergency_calls: list[dict[str, str]] = []

        def trigger_emergency_close_all(**kwargs):
            emergency_calls.append(kwargs)

        wrapper.trigger_emergency_close_all = trigger_emergency_close_all
        engine = _build_engine(wrapper=wrapper, logs=logs)

        first_backoff = engine._handle_network_outage("BTCUSDT", "1m", RuntimeError("network_offline: timeout"))
        second_backoff = engine._handle_network_outage("BTCUSDT", "1m", RuntimeError("network_offline: timeout"))

        self.assertEqual(5.0, first_backoff)
        self.assertEqual(7.5, second_backoff)
        self.assertTrue(engine.stopped())
        self.assertTrue(engine._emergency_close_triggered)
        self.assertEqual(1, len(emergency_calls))
        self.assertEqual("strategy", emergency_calls[0]["source"])
        self.assertIn("BTCUSDT@1m connectivity lost", "\n".join(logs))

    def test_emergency_close_dispatch_failure_is_recorded_while_strategy_stops(self):
        logs: list[str] = []
        wrapper = _FakeStrategyBinance()
        wrapper.trigger_emergency_close_all = lambda **_kwargs: {"ok": False, "error": "connector unavailable"}
        engine = _build_engine(wrapper=wrapper, logs=logs)

        engine._trigger_emergency_close("BTCUSDT", "1m", "network outage")

        self.assertTrue(engine.stopped())
        self.assertTrue(engine._emergency_close_triggered)
        self.assertEqual("dispatch_failed", engine._emergency_close_status)
        self.assertIn("emergency close dispatch was rejected", "\n".join(logs))

    def test_engine_coerces_string_boolean_runtime_flags(self):
        wrapper = _FakeStrategyBinance()
        config = build_default_config()
        config["symbol"] = "BTCUSDT"
        config["interval"] = "1m"
        config["indicator_use_live_values"] = "false"
        config["indicator_reentry_requires_signal_reset"] = "0"

        engine = StrategyEngine(wrapper, config, log_callback=lambda *_args, **_kwargs: None)

        self.assertFalse(engine._indicator_use_live_values)
        self.assertFalse(engine._indicator_reentry_requires_reset)

    def test_cycle_context_fails_closed_for_string_false_and_malformed_stop_limits(self):
        engine = _build_engine()
        engine.config["stop_loss"] = {
            "enabled": "false",
            "mode": "both",
            "scope": "per_trade",
            "usdt": 10.0,
            "percent": 1.0,
        }

        disabled = engine._build_cycle_context()

        self.assertFalse(disabled["stop_enabled"])
        self.assertFalse(disabled["apply_usdt_limit"])
        self.assertFalse(disabled["apply_percent_limit"])

        engine.config["stop_loss"] = {
            "enabled": "true",
            "mode": "both",
            "scope": "per_trade",
            "usdt": "not-a-number",
            "percent": float("inf"),
        }
        malformed = engine._build_cycle_context()

        self.assertEqual(0.0, malformed["stop_usdt_limit"])
        self.assertEqual(0.0, malformed["stop_percent_limit"])
        self.assertFalse(malformed["stop_enabled"])

    @unittest.skipUnless(PANDAS_AVAILABLE, "pandas is required for strategy signal behavior tests")
    def test_generate_signal_respects_string_indicator_enabled_flags(self):
        engine = _build_engine()
        engine.config["side"] = "BUY"
        engine.config["indicators"]["rsi"]["buy_value"] = 30
        engine.config["indicators"]["rsi"]["sell_value"] = 70

        df = pd.DataFrame({"close": [100.0, 101.0, 102.0]})
        ind = {"rsi": pd.Series([50.0, 25.0, 20.0])}

        engine.config["indicators"]["rsi"]["enabled"] = "false"
        signal, _desc, _price, sources, actions = engine.generate_signal(df, ind)
        self.assertIsNone(signal)
        self.assertEqual([], sources)
        self.assertEqual({}, actions)

        engine.config["indicators"]["rsi"]["enabled"] = "true"
        signal, _desc, _price, sources, actions = engine.generate_signal(df, ind)
        self.assertEqual("BUY", signal)
        self.assertEqual(["rsi"], sources)
        self.assertEqual({"rsi": "buy"}, actions)

    @unittest.skipUnless(PANDAS_AVAILABLE, "pandas is required for strategy signal behavior tests")
    def test_generate_signal_reports_atr_context_without_directional_action(self):
        engine = _build_engine()
        engine.config["indicators"]["rsi"]["enabled"] = False
        engine.config["indicators"]["atr"]["enabled"] = True
        df = pd.DataFrame({"close": [100.0, 101.0, 102.0]})
        ind = {"atr": pd.Series([1.0, 2.0, 3.0])}

        signal, desc, _price, sources, actions = engine.generate_signal(df, ind)

        self.assertIsNone(signal)
        self.assertIn("ATR=3.00000000", desc)
        self.assertEqual([], sources)
        self.assertEqual({}, actions)

    @unittest.skipUnless(PANDAS_AVAILABLE, "pandas is required for strategy signal behavior tests")
    def test_generate_signal_uses_natr_volatility_expansion_thresholds(self):
        engine = _build_engine()
        engine.config["side"] = "BUY"
        engine.config["indicators"]["rsi"]["enabled"] = False
        engine.config["indicators"]["natr"]["enabled"] = True
        engine.config["indicators"]["natr"]["buy_value"] = 2
        engine.config["indicators"]["natr"]["sell_value"] = 1
        df = pd.DataFrame({"close": [100.0, 101.0, 102.0]})
        ind = {"natr": pd.Series([0.5, 1.5, 2.5])}

        signal, desc, _price, sources, actions = engine.generate_signal(df, ind)

        self.assertEqual("BUY", signal)
        self.assertIn("NATR=2.5000", desc)
        self.assertIn("NATR >= 2.0000 -> BUY", desc)
        self.assertEqual(["natr"], sources)
        self.assertEqual({"natr": "buy"}, actions)

    @unittest.skipUnless(PANDAS_AVAILABLE, "pandas is required for strategy signal behavior tests")
    def test_generate_signal_reports_vwap_context_without_directional_action(self):
        engine = _build_engine()
        engine.config["indicators"]["rsi"]["enabled"] = False
        engine.config["indicators"]["vwap"]["enabled"] = True
        df = pd.DataFrame({"close": [100.0, 101.0, 102.0]})
        ind = {"vwap": pd.Series([100.0, 100.5, 101.5])}

        signal, desc, _price, sources, actions = engine.generate_signal(df, ind)

        self.assertIsNone(signal)
        self.assertIn("VWAP=101.50000000", desc)
        self.assertIn("close above", desc)
        self.assertEqual([], sources)
        self.assertEqual({}, actions)

    @unittest.skipUnless(PANDAS_AVAILABLE, "pandas is required for strategy signal behavior tests")
    def test_generate_signal_reports_keltner_context_without_directional_action(self):
        engine = _build_engine()
        engine.config["indicators"]["rsi"]["enabled"] = False
        engine.config["indicators"]["keltner"]["enabled"] = True
        df = pd.DataFrame({"close": [100.0, 101.0, 106.0]})
        ind = {
            "keltner_upper": pd.Series([103.0, 104.0, 105.0]),
            "keltner_mid": pd.Series([100.0, 101.0, 102.0]),
            "keltner_lower": pd.Series([97.0, 98.0, 99.0]),
        }

        signal, desc, _price, sources, actions = engine.generate_signal(df, ind)

        self.assertIsNone(signal)
        self.assertIn("KC_up=105.00000000", desc)
        self.assertIn("close above upper", desc)
        self.assertEqual([], sources)
        self.assertEqual({}, actions)

    @unittest.skipUnless(PANDAS_AVAILABLE, "pandas is required for strategy signal behavior tests")
    def test_generate_signal_reports_ichimoku_context_without_default_directional_action(self):
        engine = _build_engine()
        engine.config["indicators"]["rsi"]["enabled"] = False
        engine.config["indicators"]["ichimoku"]["enabled"] = True
        df = pd.DataFrame({"close": [100.0, 101.0, 106.0]})
        ind = {
            "ichimoku_tenkan": pd.Series([100.0, 101.0, 105.0]),
            "ichimoku_kijun": pd.Series([99.0, 100.0, 103.0]),
            "ichimoku_span_a": pd.Series([98.0, 100.0, 104.0]),
            "ichimoku_span_b": pd.Series([97.0, 99.0, 102.0]),
            "ichimoku": pd.Series([1.0, 1.0, 2.0]),
        }

        signal, desc, _price, sources, actions = engine.generate_signal(df, ind)

        self.assertIsNone(signal)
        self.assertIn("IC_tenkan=105.00000000", desc)
        self.assertIn("spread=2.00000000", desc)
        self.assertIn("close above cloud", desc)
        self.assertEqual([], sources)
        self.assertEqual({}, actions)

    @unittest.skipUnless(PANDAS_AVAILABLE, "pandas is required for strategy signal behavior tests")
    def test_generate_signal_reports_obv_context_without_default_directional_action(self):
        engine = _build_engine()
        engine.config["indicators"]["rsi"]["enabled"] = False
        engine.config["indicators"]["obv"]["enabled"] = True
        df = pd.DataFrame({"close": [100.0, 101.0, 102.0]})
        ind = {"obv": pd.Series([0.0, 1000.0, 2000.0])}

        signal, desc, _price, sources, actions = engine.generate_signal(df, ind)

        self.assertIsNone(signal)
        self.assertIn("OBV=2000.00", desc)
        self.assertIn("rising", desc)
        self.assertEqual([], sources)
        self.assertEqual({}, actions)

    @unittest.skipUnless(PANDAS_AVAILABLE, "pandas is required for strategy signal behavior tests")
    def test_generate_signal_uses_rvol_participation_thresholds(self):
        engine = _build_engine()
        engine.config["side"] = "BUY"
        engine.config["indicators"]["rsi"]["enabled"] = False
        engine.config["indicators"]["rvol"]["enabled"] = True
        engine.config["indicators"]["rvol"]["buy_value"] = 1.5
        engine.config["indicators"]["rvol"]["sell_value"] = 0.75
        df = pd.DataFrame({"close": [100.0, 101.0, 102.0]})
        ind = {"rvol": pd.Series([0.9, 1.2, 1.6])}

        signal, desc, _price, sources, actions = engine.generate_signal(df, ind)

        self.assertEqual("BUY", signal)
        self.assertIn("RVOL=1.6000", desc)
        self.assertIn("RVOL >= 1.5000 -> BUY", desc)
        self.assertEqual(["rvol"], sources)
        self.assertEqual({"rvol": "buy"}, actions)

    @unittest.skipUnless(PANDAS_AVAILABLE, "pandas is required for strategy signal behavior tests")
    def test_generate_signal_reports_cmf_context_without_default_directional_action(self):
        engine = _build_engine()
        engine.config["indicators"]["rsi"]["enabled"] = False
        engine.config["indicators"]["cmf"]["enabled"] = True
        df = pd.DataFrame({"close": [100.0, 101.0, 102.0]})
        ind = {"cmf": pd.Series([0.1, 0.2, 0.25])}

        signal, desc, _price, sources, actions = engine.generate_signal(df, ind)

        self.assertIsNone(signal)
        self.assertIn("CMF=0.2500", desc)
        self.assertIn("accumulation", desc)
        self.assertEqual([], sources)
        self.assertEqual({}, actions)

    @unittest.skipUnless(PANDAS_AVAILABLE, "pandas is required for strategy signal behavior tests")
    def test_generate_signal_uses_cci_oscillator_thresholds(self):
        engine = _build_engine()
        engine.config["side"] = "BUY"
        engine.config["indicators"]["rsi"]["enabled"] = False
        engine.config["indicators"]["cci"]["enabled"] = True
        engine.config["indicators"]["cci"]["buy_value"] = -100
        engine.config["indicators"]["cci"]["sell_value"] = 100
        df = pd.DataFrame({"close": [100.0, 101.0, 102.0]})
        ind = {"cci": pd.Series([0.0, -120.0, -130.0])}

        signal, desc, _price, sources, actions = engine.generate_signal(df, ind)

        self.assertEqual("BUY", signal)
        self.assertIn("CCI=-130.00", desc)
        self.assertIn("CCI <= -100.00 -> BUY", desc)
        self.assertEqual(["cci"], sources)
        self.assertEqual({"cci": "buy"}, actions)

    @unittest.skipUnless(PANDAS_AVAILABLE, "pandas is required for strategy signal behavior tests")
    def test_generate_signal_uses_bbw_volatility_expansion_thresholds(self):
        engine = _build_engine()
        engine.config["side"] = "BUY"
        engine.config["indicators"]["rsi"]["enabled"] = False
        engine.config["indicators"]["bbw"]["enabled"] = True
        engine.config["indicators"]["bbw"]["buy_value"] = 5
        engine.config["indicators"]["bbw"]["sell_value"] = 2
        df = pd.DataFrame({"close": [100.0, 101.0, 102.0]})
        ind = {"bbw": pd.Series([1.0, 4.0, 6.0])}

        signal, desc, _price, sources, actions = engine.generate_signal(df, ind)

        self.assertEqual("BUY", signal)
        self.assertIn("BBW=6.0000", desc)
        self.assertIn("BBW >= 5.0000 -> BUY", desc)
        self.assertEqual(["bbw"], sources)
        self.assertEqual({"bbw": "buy"}, actions)

    @unittest.skipUnless(PANDAS_AVAILABLE, "pandas is required for strategy signal behavior tests")
    def test_generate_signal_uses_roc_zero_line_momentum_thresholds(self):
        engine = _build_engine()
        engine.config["side"] = "BUY"
        engine.config["indicators"]["rsi"]["enabled"] = False
        engine.config["indicators"]["roc"]["enabled"] = True
        engine.config["indicators"]["roc"]["buy_value"] = 0
        engine.config["indicators"]["roc"]["sell_value"] = 0
        df = pd.DataFrame({"close": [100.0, 101.0, 102.0]})
        ind = {"roc": pd.Series([-1.0, 0.5, 2.0])}

        signal, desc, _price, sources, actions = engine.generate_signal(df, ind)

        self.assertEqual("BUY", signal)
        self.assertIn("ROC=2.00", desc)
        self.assertIn("ROC >= 0.00 -> BUY", desc)
        self.assertEqual(["roc"], sources)
        self.assertEqual({"roc": "buy"}, actions)

    @unittest.skipUnless(PANDAS_AVAILABLE, "pandas is required for strategy signal behavior tests")
    def test_generate_signal_uses_trix_smoothed_momentum_thresholds(self):
        engine = _build_engine()
        engine.config["side"] = "BUY"
        engine.config["indicators"]["rsi"]["enabled"] = False
        engine.config["indicators"]["trix"]["enabled"] = True
        engine.config["indicators"]["trix"]["buy_value"] = 0
        engine.config["indicators"]["trix"]["sell_value"] = 0
        df = pd.DataFrame({"close": [100.0, 101.0, 102.0]})
        ind = {"trix": pd.Series([-0.1, 0.2, 0.4])}

        signal, desc, _price, sources, actions = engine.generate_signal(df, ind)

        self.assertEqual("BUY", signal)
        self.assertIn("TRIX=0.4000", desc)
        self.assertIn("TRIX >= 0.0000 -> BUY", desc)
        self.assertEqual(["trix"], sources)
        self.assertEqual({"trix": "buy"}, actions)

    @unittest.skipUnless(PANDAS_AVAILABLE, "pandas is required for strategy signal behavior tests")
    def test_generate_signal_uses_ppo_histogram_thresholds(self):
        engine = _build_engine()
        engine.config["side"] = "BUY"
        engine.config["indicators"]["rsi"]["enabled"] = False
        engine.config["indicators"]["ppo"]["enabled"] = True
        engine.config["indicators"]["ppo"]["buy_value"] = 0
        engine.config["indicators"]["ppo"]["sell_value"] = 0
        df = pd.DataFrame({"close": [100.0, 101.0, 102.0]})
        ind = {
            "ppo": pd.Series([0.0, 0.5, 1.0]),
            "ppo_signal": pd.Series([0.0, 0.25, 0.5]),
            "ppo_hist": pd.Series([0.0, 0.25, 0.5]),
        }

        signal, desc, _price, sources, actions = engine.generate_signal(df, ind)

        self.assertEqual("BUY", signal)
        self.assertIn("PPO=1.0000", desc)
        self.assertIn("hist=0.5000", desc)
        self.assertIn("PPO hist >= 0.0000 -> BUY", desc)
        self.assertEqual(["ppo"], sources)
        self.assertEqual({"ppo": "buy"}, actions)

    @unittest.skipUnless(PANDAS_AVAILABLE, "pandas is required for strategy signal behavior tests")
    def test_generate_signal_uses_ao_zero_line_momentum_thresholds(self):
        engine = _build_engine()
        engine.config["side"] = "BUY"
        engine.config["indicators"]["rsi"]["enabled"] = False
        engine.config["indicators"]["ao"]["enabled"] = True
        engine.config["indicators"]["ao"]["buy_value"] = 0
        engine.config["indicators"]["ao"]["sell_value"] = 0
        df = pd.DataFrame({"close": [100.0, 101.0, 102.0]})
        ind = {"ao": pd.Series([-0.1, 0.2, 0.4])}

        signal, desc, _price, sources, actions = engine.generate_signal(df, ind)

        self.assertEqual("BUY", signal)
        self.assertIn("AO=0.4000", desc)
        self.assertIn("AO >= 0.0000 -> BUY", desc)
        self.assertEqual(["ao"], sources)
        self.assertEqual({"ao": "buy"}, actions)

    @unittest.skipUnless(PANDAS_AVAILABLE, "pandas is required for strategy signal behavior tests")
    def test_generate_signal_uses_kst_signal_spread_thresholds(self):
        engine = _build_engine()
        engine.config["side"] = "BUY"
        engine.config["indicators"]["rsi"]["enabled"] = False
        engine.config["indicators"]["kst"]["enabled"] = True
        engine.config["indicators"]["kst"]["buy_value"] = 0
        engine.config["indicators"]["kst"]["sell_value"] = 0
        df = pd.DataFrame({"close": [100.0, 101.0, 102.0]})
        ind = {
            "kst": pd.Series([0.0, 1.0, 2.0]),
            "kst_signal": pd.Series([0.0, 0.5, 1.0]),
            "kst_hist": pd.Series([0.0, 0.5, 1.0]),
        }

        signal, desc, _price, sources, actions = engine.generate_signal(df, ind)

        self.assertEqual("BUY", signal)
        self.assertIn("KST=2.0000", desc)
        self.assertIn("spread=1.0000", desc)
        self.assertIn("KST spread >= 0.0000 -> BUY", desc)
        self.assertEqual(["kst"], sources)
        self.assertEqual({"kst": "buy"}, actions)

    @unittest.skipUnless(PANDAS_AVAILABLE, "pandas is required for strategy signal behavior tests")
    def test_generate_signal_uses_aroon_trend_thresholds(self):
        engine = _build_engine()
        engine.config["side"] = "BUY"
        engine.config["indicators"]["rsi"]["enabled"] = False
        engine.config["indicators"]["aroon"]["enabled"] = True
        engine.config["indicators"]["aroon"]["buy_value"] = 50
        engine.config["indicators"]["aroon"]["sell_value"] = -50
        df = pd.DataFrame({"close": [100.0, 101.0, 102.0]})
        ind = {
            "aroon": pd.Series([0.0, 60.0, 80.0]),
            "aroon_up": pd.Series([50.0, 100.0, 100.0]),
            "aroon_down": pd.Series([50.0, 40.0, 20.0]),
        }

        signal, desc, _price, sources, actions = engine.generate_signal(df, ind)

        self.assertEqual("BUY", signal)
        self.assertIn("Aroon=80.00", desc)
        self.assertIn("Aroon >= 50.00 -> BUY", desc)
        self.assertEqual(["aroon"], sources)
        self.assertEqual({"aroon": "buy"}, actions)

    @unittest.skipUnless(PANDAS_AVAILABLE, "pandas is required for strategy signal behavior tests")
    def test_generate_signal_uses_chop_trending_thresholds(self):
        engine = _build_engine()
        engine.config["side"] = "BUY"
        engine.config["indicators"]["rsi"]["enabled"] = False
        engine.config["indicators"]["chop"]["enabled"] = True
        engine.config["indicators"]["chop"]["buy_value"] = 38.2
        engine.config["indicators"]["chop"]["sell_value"] = 61.8
        df = pd.DataFrame({"close": [100.0, 101.0, 102.0]})
        ind = {"chop": pd.Series([70.0, 45.0, 30.0])}

        signal, desc, _price, sources, actions = engine.generate_signal(df, ind)

        self.assertEqual("BUY", signal)
        self.assertIn("CHOP=30.0000", desc)
        self.assertIn("CHOP <= 38.2000 -> BUY", desc)
        self.assertEqual(["chop"], sources)
        self.assertEqual({"chop": "buy"}, actions)

    @unittest.skipUnless(PANDAS_AVAILABLE, "pandas is required for strategy signal behavior tests")
    def test_generate_signal_uses_mfi_volume_oscillator_thresholds(self):
        engine = _build_engine()
        engine.config["side"] = "BUY"
        engine.config["indicators"]["rsi"]["enabled"] = False
        engine.config["indicators"]["mfi"]["enabled"] = True
        engine.config["indicators"]["mfi"]["buy_value"] = 20
        engine.config["indicators"]["mfi"]["sell_value"] = 80
        df = pd.DataFrame({"close": [100.0, 101.0, 102.0]})
        ind = {"mfi": pd.Series([50.0, 18.0, 15.0])}

        signal, desc, _price, sources, actions = engine.generate_signal(df, ind)

        self.assertEqual("BUY", signal)
        self.assertIn("MFI=15.00", desc)
        self.assertIn("MFI <= 20.00 -> BUY", desc)
        self.assertEqual(["mfi"], sources)
        self.assertEqual({"mfi": "buy"}, actions)

    @unittest.skipUnless(PANDAS_AVAILABLE, "pandas is required for strategy indicator behavior tests")
    def test_compute_indicators_respects_string_indicator_enabled_flags(self):
        engine = _build_engine()
        engine.config["indicators"]["rsi"]["enabled"] = "false"
        engine.config["indicators"]["ema"]["enabled"] = "true"
        engine.config["indicators"]["ema"]["length"] = 2
        engine.config["indicators"]["atr"]["enabled"] = "true"
        engine.config["indicators"]["atr"]["length"] = 3
        engine.config["indicators"]["natr"]["enabled"] = "true"
        engine.config["indicators"]["natr"]["length"] = 3
        engine.config["indicators"]["vwap"]["enabled"] = "true"
        engine.config["indicators"]["vwap"]["length"] = 2
        engine.config["indicators"]["mfi"]["enabled"] = "true"
        engine.config["indicators"]["mfi"]["length"] = 2
        engine.config["indicators"]["keltner"]["enabled"] = "true"
        engine.config["indicators"]["keltner"]["length"] = 3
        engine.config["indicators"]["keltner"]["atr_length"] = 3
        engine.config["indicators"]["keltner"]["multiplier"] = 2.0
        engine.config["indicators"]["ichimoku"]["enabled"] = "true"
        engine.config["indicators"]["ichimoku"]["conversion_length"] = 2
        engine.config["indicators"]["ichimoku"]["base_length"] = 3
        engine.config["indicators"]["ichimoku"]["span_b_length"] = 3
        engine.config["indicators"]["ichimoku"]["displacement"] = 0
        engine.config["indicators"]["obv"]["enabled"] = "true"
        engine.config["indicators"]["rvol"]["enabled"] = "true"
        engine.config["indicators"]["rvol"]["length"] = 2
        engine.config["indicators"]["cmf"]["enabled"] = "true"
        engine.config["indicators"]["cmf"]["length"] = 2
        engine.config["indicators"]["cci"]["enabled"] = "true"
        engine.config["indicators"]["cci"]["length"] = 3
        engine.config["indicators"]["cci"]["constant"] = 0.015
        engine.config["indicators"]["bbw"]["enabled"] = "true"
        engine.config["indicators"]["bbw"]["length"] = 2
        engine.config["indicators"]["bbw"]["std"] = 2
        engine.config["indicators"]["roc"]["enabled"] = "true"
        engine.config["indicators"]["roc"]["length"] = 2
        engine.config["indicators"]["trix"]["enabled"] = "true"
        engine.config["indicators"]["trix"]["length"] = 2
        engine.config["indicators"]["ppo"]["enabled"] = "true"
        engine.config["indicators"]["ppo"]["fast"] = 2
        engine.config["indicators"]["ppo"]["slow"] = 3
        engine.config["indicators"]["ppo"]["signal"] = 2
        engine.config["indicators"]["ao"]["enabled"] = "true"
        engine.config["indicators"]["ao"]["fast"] = 2
        engine.config["indicators"]["ao"]["slow"] = 3
        engine.config["indicators"]["kst"]["enabled"] = "true"
        engine.config["indicators"]["kst"]["roc1"] = 1
        engine.config["indicators"]["kst"]["roc2"] = 2
        engine.config["indicators"]["kst"]["roc3"] = 3
        engine.config["indicators"]["kst"]["roc4"] = 4
        engine.config["indicators"]["kst"]["sma1"] = 1
        engine.config["indicators"]["kst"]["sma2"] = 1
        engine.config["indicators"]["kst"]["sma3"] = 1
        engine.config["indicators"]["kst"]["sma4"] = 1
        engine.config["indicators"]["kst"]["signal"] = 2
        engine.config["indicators"]["aroon"]["enabled"] = "true"
        engine.config["indicators"]["aroon"]["length"] = 3
        engine.config["indicators"]["chop"]["enabled"] = "true"
        engine.config["indicators"]["chop"]["length"] = 3

        df = pd.DataFrame(
            {
                "open": [100.0, 101.0, 102.0],
                "high": [101.0, 102.0, 103.0],
                "low": [99.0, 100.0, 101.0],
                "close": [100.0, 101.0, 102.0],
                "volume": [1000.0, 1000.0, 1000.0],
            }
        )

        indicators = engine.compute_indicators(df)

        self.assertNotIn("rsi", indicators)
        self.assertIn("ema", indicators)
        self.assertIn("atr", indicators)
        self.assertIn("natr", indicators)
        self.assertIn("vwap", indicators)
        self.assertIn("mfi", indicators)
        self.assertIn("keltner_upper", indicators)
        self.assertIn("keltner_mid", indicators)
        self.assertIn("keltner_lower", indicators)
        self.assertIn("ichimoku_tenkan", indicators)
        self.assertIn("ichimoku_kijun", indicators)
        self.assertIn("ichimoku", indicators)
        self.assertIn("obv", indicators)
        self.assertIn("rvol", indicators)
        self.assertIn("cmf", indicators)
        self.assertIn("cci", indicators)
        self.assertIn("bbw", indicators)
        self.assertIn("roc", indicators)
        self.assertIn("trix", indicators)
        self.assertIn("ppo", indicators)
        self.assertIn("ppo_signal", indicators)
        self.assertIn("ppo_hist", indicators)
        self.assertIn("ao", indicators)
        self.assertIn("kst", indicators)
        self.assertIn("kst_signal", indicators)
        self.assertIn("kst_hist", indicators)
        self.assertIn("aroon", indicators)
        self.assertIn("aroon_up", indicators)
        self.assertIn("aroon_down", indicators)
        self.assertIn("chop", indicators)
        self.assertAlmostEqual(2.0, float(indicators["atr"].iloc[-1]))
        self.assertAlmostEqual(1.960784314, float(indicators["natr"].iloc[-1]))
        self.assertAlmostEqual(101.5, float(indicators["vwap"].iloc[-1]))
        self.assertAlmostEqual(100.0, float(indicators["mfi"].iloc[-1]))
        self.assertAlmostEqual(105.25, float(indicators["keltner_upper"].iloc[-1]))
        self.assertAlmostEqual(101.25, float(indicators["keltner_mid"].iloc[-1]))
        self.assertAlmostEqual(97.25, float(indicators["keltner_lower"].iloc[-1]))
        self.assertAlmostEqual(0.5, float(indicators["ichimoku"].iloc[-1]))
        self.assertAlmostEqual(2000.0, float(indicators["obv"].iloc[-1]))
        self.assertAlmostEqual(1.0, float(indicators["rvol"].iloc[-1]))
        self.assertAlmostEqual(0.0, float(indicators["cmf"].iloc[-1]))
        self.assertAlmostEqual(100.0, float(indicators["cci"].iloc[-1]))
        self.assertAlmostEqual(2.786627709, float(indicators["bbw"].iloc[-1]))
        self.assertAlmostEqual(2.0, float(indicators["roc"].iloc[-1]))
        self.assertAlmostEqual(0.59084195, float(indicators["trix"].iloc[-1]))
        self.assertAlmostEqual(0.063741648, float(indicators["ppo_hist"].iloc[-1]))
        self.assertAlmostEqual(0.5, float(indicators["ao"].iloc[-1]))
        self.assertAlmostEqual(1.995049505, float(indicators["kst_hist"].iloc[-1]))
        self.assertAlmostEqual(100.0, float(indicators["aroon"].iloc[-1]))
        self.assertAlmostEqual(36.907024643, float(indicators["chop"].iloc[-1]))

    def test_queue_flip_on_close_respects_string_trade_and_indicator_flags(self):
        engine = _build_engine()
        entry = {"qty": 1.0, "indicator_keys": ["rsi"]}
        payload = {"qty": 1.0, "reason": "per_trade_stop_loss"}

        engine.config["auto_flip_on_close"] = "true"
        engine.config["trade_on_signal"] = "false"
        engine.config["indicators"]["rsi"]["enabled"] = True
        engine._queue_flip_on_close("1m", "BUY", entry, payload)
        self.assertEqual({}, engine._flip_on_close_requests)

        engine.config["trade_on_signal"] = "true"
        engine.config["indicators"]["rsi"]["enabled"] = "false"
        engine._queue_flip_on_close("1m", "BUY", entry, payload)
        self.assertEqual({}, engine._flip_on_close_requests)

        engine.config["indicators"]["rsi"]["enabled"] = "true"
        engine._queue_flip_on_close("1m", "BUY", entry, payload)
        self.assertEqual(1, len(engine._flip_on_close_requests))

    def test_resolve_signal_order_account_state_falls_back_from_invalid_position_pct(self):
        engine = _build_engine()

        state = engine._resolve_signal_order_account_state(
            cw={"position_pct": "not-a-number", "position_pct_units": "percent"},
            last_price=123.45,
        )

        self.assertEqual("FUTURES", state["account_type"])
        self.assertAlmostEqual(1000.0, state["free_usdt"])
        self.assertAlmostEqual(0.25, state["pct"])
        self.assertAlmostEqual(123.45, state["price"])

    def test_prepare_signal_order_margin_state_ignores_false_string_add_only(self):
        wrapper = _FakeStrategyBinance()
        wrapper.net_amt = 2.0
        engine = _build_engine(wrapper=wrapper)
        engine.config["add_only"] = "false"

        state = engine._prepare_signal_order_margin_state(
            cw={"symbol": "BTCUSDT", "interval": "1m"},
            side="SELL",
            pct=0.1,
            free_usdt=1000.0,
            price=100.0,
            futures_balance_snap={"available": 1000.0, "wallet": 1000.0},
            flip_close_qty=0.0,
            entries_side_all=[],
            active_slot_tokens_all=set(),
            existing_margin_indicator_total=0.0,
            slot_label="rsi",
            slot_token_for_order="rsi",
            lev=5,
            abort_guard=lambda: None,
        )

        self.assertFalse(state["aborted"])
        self.assertFalse(state["reduce_only"])
        self.assertAlmostEqual(5.0, state["qty_est"])

        engine.config["add_only"] = "true"
        state = engine._prepare_signal_order_margin_state(
            cw={"symbol": "BTCUSDT", "interval": "1m"},
            side="SELL",
            pct=0.1,
            free_usdt=1000.0,
            price=100.0,
            futures_balance_snap={"available": 1000.0, "wallet": 1000.0},
            flip_close_qty=0.0,
            entries_side_all=[],
            active_slot_tokens_all=set(),
            existing_margin_indicator_total=0.0,
            slot_label="rsi",
            slot_token_for_order="rsi",
            lev=5,
            abort_guard=lambda: None,
        )

        self.assertFalse(state["aborted"])
        self.assertTrue(state["reduce_only"])
        self.assertAlmostEqual(2.0, state["qty_est"])

    def test_close_leg_refuses_non_finite_live_quantity_without_submitting_order(self):
        logs: list[str] = []
        engine = _build_engine(logs=logs)
        submitted: list[tuple[object, ...]] = []
        engine._current_futures_position_qty = lambda *_args: float("nan")

        def _submit(*args):
            submitted.append(args)
            return True, {"ok": True}

        engine._execute_close_with_fallback = _submit
        closed_qty = engine._close_leg_entry(
            {"symbol": "BTCUSDT", "interval": "1m"},
            ("BTCUSDT", "1m", "BUY"),
            {"qty": 1.0, "ledger_id": "ledger-1"},
            "BUY",
            "SELL",
            None,
            loss_usdt=0.0,
            price_pct=0.0,
            margin_pct=0.0,
        )

        self.assertEqual(0.0, closed_qty)
        self.assertEqual([], submitted)
        self.assertIn("close refused: live quantity snapshot was not finite", "\n".join(logs))

    def test_close_leg_refuses_non_finite_ledger_quantity_without_submitting_order(self):
        engine = _build_engine()
        submitted: list[tuple[object, ...]] = []
        engine._current_futures_position_qty = lambda *_args: 1.0
        engine._execute_close_with_fallback = lambda *args: submitted.append(args) or (True, {"ok": True})

        closed_qty = engine._close_leg_entry(
            {"symbol": "BTCUSDT", "interval": "1m"},
            ("BTCUSDT", "1m", "BUY"),
            {"qty": float("inf"), "ledger_id": "ledger-1"},
            "BUY",
            "SELL",
            None,
            loss_usdt=0.0,
            price_pct=0.0,
            margin_pct=0.0,
        )

        self.assertEqual(0.0, closed_qty)
        self.assertEqual([], submitted)

    def test_per_trade_stop_refuses_non_finite_market_price_without_closing(self):
        logs: list[str] = []
        engine = _build_engine(logs=logs)
        close_attempts: list[tuple[object, ...]] = []
        engine._close_leg_entry = lambda *args, **kwargs: close_attempts.append(args) or 1.0

        triggered = engine._evaluate_per_trade_stop(
            {"symbol": "BTCUSDT", "interval": "1m"},
            ("BTCUSDT", "1m", "BUY"),
            [{"qty": 1.0, "entry_price": 100.0}],
            side_label="BUY",
            last_price=float("inf"),
            apply_usdt_limit=True,
            apply_percent_limit=False,
            stop_usdt_limit=1.0,
            stop_percent_limit=0.0,
            dual_side=False,
        )

        self.assertFalse(triggered)
        self.assertEqual([], close_attempts)
        self.assertIn("market price was not a positive finite value", "\n".join(logs))

    def test_hedge_close_does_not_retry_another_leg_after_position_side_mismatch(self):
        wrapper = _FakeStrategyBinance()
        calls: list[str | None] = []

        def close_futures_leg_exact(_symbol, _qty, *, side, position_side):
            self.assertEqual("SELL", side)
            calls.append(position_side)
            return {"ok": False, "error": "Position side does not match"}

        wrapper.close_futures_leg_exact = close_futures_leg_exact
        engine = _build_engine(wrapper=wrapper)

        ok, result = engine._execute_close_with_fallback("BTCUSDT", "SELL", 1.0, "LONG")

        self.assertFalse(ok)
        self.assertEqual(["LONG"], calls)
        self.assertEqual("Position side does not match", result["error"])

    def test_entire_account_stop_loss_triggers_verified_emergency_close(self):
        wrapper = _FakeStrategyBinance()
        wrapper.get_total_unrealized_pnl = lambda: -125.0
        calls: list[tuple[object, ...]] = []
        engine = _build_engine(wrapper=wrapper)
        engine._trigger_emergency_close = lambda *args: calls.append(args)

        triggered = engine._apply_entire_account_stop_loss(
            ctx={
                "cw": {"symbol": "BTCUSDT", "interval": "1m"},
                "account_type": "FUTURES",
                "is_entire_account": True,
                "apply_usdt_limit": True,
                "apply_percent_limit": False,
                "stop_usdt_limit": 100.0,
                "stop_percent_limit": 0.0,
            }
        )

        self.assertTrue(triggered)
        self.assertEqual(
            [("BTCUSDT", "1m", "entire-account-usdt-limit (-125.00)")],
            calls,
        )

    def test_entire_account_stop_loss_ignores_non_finite_threshold(self):
        wrapper = _FakeStrategyBinance()
        wrapper.get_total_unrealized_pnl = lambda: -125.0
        calls: list[tuple[object, ...]] = []
        engine = _build_engine(wrapper=wrapper)
        engine._trigger_emergency_close = lambda *args: calls.append(args)

        triggered = engine._apply_entire_account_stop_loss(
            ctx={
                "cw": {"symbol": "BTCUSDT", "interval": "1m"},
                "account_type": "FUTURES",
                "is_entire_account": True,
                "apply_usdt_limit": True,
                "apply_percent_limit": False,
                "stop_usdt_limit": "nan",
                "stop_percent_limit": 0.0,
            }
        )

        self.assertFalse(triggered)
        self.assertEqual([], calls)

    def test_per_trade_stop_loss_closes_when_loss_limit_is_reached(self):
        engine = _build_engine()
        close_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

        def close_leg(*args, **kwargs):
            close_calls.append((args, kwargs))
            return 1.0

        engine._close_leg_entry = close_leg
        triggered = engine._evaluate_per_trade_stop(
            {"symbol": "BTCUSDT", "interval": "1m"},
            ("BTCUSDT", "1m", "BUY"),
            [{"qty": 1.0, "entry_price": 100.0, "leverage": 5.0}],
            side_label="BUY",
            last_price=90.0,
            apply_usdt_limit=True,
            apply_percent_limit=False,
            stop_usdt_limit=5.0,
            stop_percent_limit=0.0,
            dual_side=False,
        )

        self.assertTrue(triggered)
        self.assertEqual(1, len(close_calls))
        args, kwargs = close_calls[0]
        self.assertEqual("BUY", args[3])
        self.assertEqual("SELL", args[4])
        self.assertEqual("per_trade_stop_loss", kwargs["reason"])

    @unittest.skipUnless(PANDAS_AVAILABLE, "pandas is required for stop-context tests")
    def test_stop_context_uses_finite_dataframe_price_and_caches_exchange_positions(self):
        wrapper = _FakeStrategyBinance()
        wrapper.get_last_price = lambda _symbol: float("nan")
        position_requests: list[bool] = []
        wrapper.list_open_futures_positions = lambda: position_requests.append(True) or []
        engine = _build_engine(wrapper=wrapper)
        frame = pd.DataFrame({"close": [80.0, 90.0]})

        state = build_futures_stop_state(engine, cw={"symbol": "BTCUSDT"}, df=frame)

        self.assertEqual(90.0, state["last_price"])
        self.assertEqual([], state["load_positions_cache"]())
        self.assertEqual([], state["load_positions_cache"]())
        self.assertEqual([True], position_requests)

    def test_stop_context_rejects_non_finite_ledger_and_exchange_position_values(self):
        wrapper = _FakeStrategyBinance()
        wrapper.list_open_futures_positions = lambda: [
            {"symbol": "BTCUSDT", "positionAmt": "nan", "entryPrice": "nan"}
        ]
        engine = _build_engine(wrapper=wrapper)
        leg_key = ("BTCUSDT", "1m", "BUY")
        engine._leg_ledger[leg_key] = {"qty": "inf", "entry_price": "nan"}
        state = {
            "load_positions_cache": lambda: wrapper.list_open_futures_positions(),
        }

        leg, qty, entry_price, matched = ensure_futures_leg_entry_price(
            engine,
            cw={"symbol": "BTCUSDT"},
            leg_key=leg_key,
            expect_long=True,
            dual_side=False,
            state=state,
        )

        self.assertEqual(0.0, qty)
        self.assertEqual(0.0, entry_price)
        self.assertIsNone(matched)
        self.assertEqual("nan", leg["entry_price"])

    @unittest.skipUnless(PANDAS_AVAILABLE, "pandas is required for stop-cycle tests")
    def test_futures_stop_cycle_routes_valid_leg_through_per_trade_stop_evaluation(self):
        wrapper = _FakeStrategyBinance()
        wrapper.get_last_price = lambda _symbol: 90.0
        wrapper.list_open_futures_positions = lambda: []
        engine = _build_engine(wrapper=wrapper)
        key_long = ("BTCUSDT", "1m", "BUY")
        key_short = ("BTCUSDT", "1m", "SELL")
        engine._leg_ledger[key_long] = {
            "qty": 1.0,
            "entry_price": 100.0,
            "entries": [{"qty": 1.0, "entry_price": 100.0}],
        }
        engine._purge_flat_futures_legs = lambda *_args, **_kwargs: None
        stop_calls: list[dict[str, object]] = []
        engine._evaluate_per_trade_stop = lambda *args, **kwargs: stop_calls.append(kwargs) or False

        result = apply_futures_cycle_risk_management(
            engine,
            cw={"symbol": "BTCUSDT", "interval": "1m"},
            df=pd.DataFrame({"close": [90.0]}),
            account_type="FUTURES",
            dual_side=False,
            key_long=key_long,
            key_short=key_short,
            long_open=True,
            short_open=False,
            stop_enabled=True,
            apply_usdt_limit=True,
            apply_percent_limit=False,
            stop_usdt_limit=5.0,
            stop_percent_limit=0.0,
            scope="per_trade",
            is_cumulative=False,
        )

        self.assertEqual(1, len(stop_calls))
        self.assertEqual("BUY", stop_calls[0]["side_label"])
        self.assertEqual(90.0, stop_calls[0]["last_price"])
        self.assertTrue(result["long_open"])
        self.assertFalse(result["short_open"])

    def test_directional_stop_partial_fill_keeps_ledger_for_reconciliation(self):
        logs: list[str] = []
        wrapper = _FakeStrategyBinance()
        wrapper.close_futures_leg_exact = lambda *_args, **_kwargs: {
            "ok": True,
            "executedQty": "0.25",
        }
        engine = _build_engine(wrapper=wrapper, logs=logs)
        engine._compute_position_margin_fields = lambda *_args, **_kwargs: (0.0, 0.0, 0.0, 0.0)
        removed: list[tuple[object, ...]] = []
        engine._remove_leg_entry = lambda *args: removed.append(args)

        _apply_long_futures_stop(
            engine,
            cw={"symbol": "BTCUSDT", "interval": "1m"},
            dual_side=False,
            key_long=("BTCUSDT", "1m", "BUY"),
            qty_long=1.0,
            entry_price_long=100.0,
            pos_long=None,
            pos_long_qty_total=1.0,
            apply_usdt_limit=True,
            apply_percent_limit=False,
            stop_usdt_limit=5.0,
            stop_percent_limit=0.0,
            last_price=90.0,
        )

        self.assertEqual([], removed)
        self.assertIn("partially filled", "\n".join(logs))

    def test_cumulative_stop_partial_fill_keeps_ledger_for_reconciliation(self):
        logs: list[str] = []
        wrapper = _FakeStrategyBinance()
        wrapper.close_futures_leg_exact = lambda *_args, **_kwargs: {
            "ok": True,
            "executedQty": "0.25",
        }
        engine = _build_engine(wrapper=wrapper, logs=logs)
        leg_key = ("BTCUSDT", "1m", "BUY")
        engine._leg_ledger[leg_key] = {
            "qty": 1.0,
            "entry_price": 100.0,
            "entries": [{"qty": 1.0, "entry_price": 100.0}],
        }
        removed: list[tuple[object, ...]] = []
        engine._remove_leg_entry = lambda *args: removed.append(args)

        triggered = apply_cumulative_futures_stop_management(
            engine,
            cw={"symbol": "BTCUSDT", "interval": "1m"},
            last_price=90.0,
            dual_side=False,
            apply_usdt_limit=True,
            apply_percent_limit=False,
            stop_usdt_limit=5.0,
            stop_percent_limit=0.0,
            state={
                "load_positions_cache": lambda: [
                    {
                        "symbol": "BTCUSDT",
                        "positionAmt": "1",
                        "entryPrice": "100",
                        "isolatedWallet": "20",
                    }
                ]
            },
        )

        self.assertTrue(triggered)
        self.assertEqual([], removed)
        self.assertIn("partially filled", "\n".join(logs))

    def test_cumulative_stop_rejects_non_finite_market_price(self):
        wrapper = _FakeStrategyBinance()
        close_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
        wrapper.close_futures_leg_exact = lambda *args, **kwargs: close_calls.append(
            (args, kwargs)
        ) or {"ok": True}
        engine = _build_engine(wrapper=wrapper)

        triggered = apply_cumulative_futures_stop_management(
            engine,
            cw={"symbol": "BTCUSDT", "interval": "1m"},
            last_price=float("nan"),
            dual_side=False,
            apply_usdt_limit=True,
            apply_percent_limit=False,
            stop_usdt_limit=5.0,
            stop_percent_limit=0.0,
            state={"load_positions_cache": lambda: []},
        )

        self.assertFalse(triggered)
        self.assertEqual([], close_calls)

    def test_close_interval_side_entries_uses_bound_interval_helper(self):
        engine = _build_engine()
        leg_key = ("BTCUSDT", "5m", "SELL")
        entry = {
            "qty": 0.5,
            "timestamp": 0.0,
            "indicator_keys": ["rsi"],
            "trigger_signature": ["rsi"],
        }
        engine._leg_ledger[leg_key] = {"qty": 0.5, "entries": [entry]}
        interval_calls: list[str] = []
        hold_calls: list[tuple[str, float]] = []
        close_calls: list[tuple[tuple[str, str, str], str, str]] = []

        def _interval_seconds(value: str) -> int:
            interval_calls.append(value)
            return 300

        def _hold_ready(
            _timestamp,
            _symbol,
            interval,
            _indicator,
            _side,
            interval_seconds,
        ):
            hold_calls.append((str(interval), float(interval_seconds)))
            return True

        def _close_leg_entry(
            _cw_ctx,
            closed_leg_key,
            _entry,
            leg_side_norm,
            close_side,
            _position_side,
            **_kwargs,
        ):
            close_calls.append((closed_leg_key, leg_side_norm, close_side))
            return 0.5

        engine._interval_to_seconds = _interval_seconds
        engine._indicator_hold_ready = _hold_ready
        engine._close_leg_entry = _close_leg_entry

        closed, failed, qty = _close_interval_side_entries(
            engine,
            symbol="BTCUSDT",
            interval_norm="5m",
            interval_tokens={"5m"},
            interval_has_filter=True,
            interval_norm_guard=("5m",),
            opp="SELL",
            dual=False,
            indicator_filter="rsi",
            signature_filter=("rsi",),
            qty_limit=None,
        )

        self.assertEqual(1, closed)
        self.assertFalse(failed)
        self.assertAlmostEqual(0.5, qty)
        self.assertEqual(["5m"], interval_calls)
        self.assertEqual([("5m", 300.0)], hold_calls)
        self.assertEqual([(leg_key, "SELL", "BUY")], close_calls)
