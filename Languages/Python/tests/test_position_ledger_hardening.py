from __future__ import annotations

import sys
import unittest
from pathlib import Path


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.config import build_default_config  # noqa: E402
from app.core.strategy import StrategyEngine  # noqa: E402


class _FakeBinance:
    account_type = "FUTURES"


def _build_engine() -> StrategyEngine:
    config = build_default_config()
    config["symbol"] = "BTCUSDT"
    config["interval"] = "1m"
    return StrategyEngine(_FakeBinance(), config, log_callback=lambda _message: None)


class PositionLedgerHardeningTests(unittest.TestCase):
    def setUp(self):
        StrategyEngine._GLOBAL_PAUSE.clear()
        StrategyEngine._GLOBAL_PAUSE_FALLBACK = False

    def tearDown(self):
        StrategyEngine._GLOBAL_PAUSE.clear()
        StrategyEngine._GLOBAL_PAUSE_FALLBACK = False

    def test_append_keeps_primary_entry_but_pauses_when_signature_index_fails(self):
        engine = _build_engine()
        key = ("BTCUSDT", "1m", "BUY")
        entry = {
            "qty": 1.0,
            "entry_price": 100.0,
            "margin_usdt": 20.0,
            "ledger_id": "ledger-1",
        }

        def fail_signature_count(*_args, **_kwargs):
            raise RuntimeError("signature index failed")

        engine._bump_symbol_signature_open = fail_signature_count

        with self.assertLogs(
            "app.core.strategy.positions.strategy_position_ledger_runtime",
            level="ERROR",
        ):
            engine._append_leg_entry(key, entry)

        self.assertEqual([entry], engine._leg_ledger[key]["entries"])
        self.assertTrue(engine._ledger_reconciliation_required)
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())

    def test_remove_clears_primary_ledger_but_pauses_when_indicator_index_fails(self):
        engine = _build_engine()
        key = ("BTCUSDT", "1m", "BUY")
        engine._leg_ledger[key] = {
            "qty": 1.0,
            "entries": [
                {
                    "qty": 1.0,
                    "ledger_id": "ledger-1",
                    "trigger_signature": ["rsi"],
                    "indicator_keys": ["rsi"],
                }
            ],
        }
        engine._bump_symbol_signature_open = lambda *_args, **_kwargs: None
        engine._extract_indicator_keys = lambda _entry: ["rsi"]

        def fail_unregister(*_args, **_kwargs):
            raise RuntimeError("indicator index failed")

        engine._indicator_unregister_entry = fail_unregister

        with self.assertLogs(
            "app.core.strategy.positions.strategy_position_ledger_runtime",
            level="ERROR",
        ):
            engine._remove_leg_entry(key, None)

        self.assertNotIn(key, engine._leg_ledger)
        self.assertTrue(engine._ledger_reconciliation_required)
        self.assertTrue(StrategyEngine._GLOBAL_PAUSE.is_set())

    def test_clean_append_does_not_request_reconciliation(self):
        engine = _build_engine()
        key = ("BTCUSDT", "1m", "BUY")
        entry = {
            "qty": 1.0,
            "entry_price": 100.0,
            "margin_usdt": 20.0,
            "ledger_id": "ledger-clean",
        }

        engine._append_leg_entry(key, entry)

        self.assertFalse(engine._ledger_reconciliation_required)
        self.assertFalse(StrategyEngine._GLOBAL_PAUSE.is_set())
        self.assertEqual([entry], engine._leg_ledger[key]["entries"])


if __name__ == "__main__":
    unittest.main()
