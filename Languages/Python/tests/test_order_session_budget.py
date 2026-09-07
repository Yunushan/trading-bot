from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, Lock
import unittest
from unittest.mock import patch

from app.native_parity import ORDER_GUARD_BEHAVIOR
from app.integrations.exchanges.binance.positions import close_all_runtime
from app.integrations.exchanges.binance.orders import order_submit_guard_runtime as guards
from app.settings.live_safety import LiveTradingSafetyError
from test_binance_package_split_smoke import _GuardedFuturesAuditWrapper, _live_ack_config
from trading_core.orders import is_exchange_risk_reducing_order


ENTRY = {"symbol": "ETHUSDT", "side": "BUY", "type": "MARKET", "quantity": "0.1"}
CLOSE = {**ENTRY, "side": "SELL", "reduceOnly": True}


class OrderSessionBudgetTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict("os.environ", {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.network = patch("socket.socket.connect", side_effect=AssertionError("Network forbidden"))
        self.network.start()
        self.addCleanup(self.network.stop)

    def wrapper(self, **kwargs):
        wrapper = _GuardedFuturesAuditWrapper(
            live_safety_config=_live_ack_config(live_trading_max_session_orders=1), **kwargs
        )
        self.addCleanup(wrapper.close)
        return wrapper

    def test_python_owned_budget_reference_cases(self):
        for case in ORDER_GUARD_BEHAVIOR["session_budget_exit_cases"]:
            with self.subTest(name=case["name"]):
                self.assertEqual(case["exempt"], is_exchange_risk_reducing_order(case["market"], case["params"]))
                wrapper = self.wrapper()
                wrapper._live_order_submit_attempt_count = 1
                if case["exempt"]:
                    wrapper._guard_live_order_submit(market=case["market"], params=case["params"])
                else:
                    with self.assertRaisesRegex(LiveTradingSafetyError, "live session order cap 1 reached"):
                        wrapper._guard_live_order_submit(market=case["market"], params=case["params"])
                self.assertEqual(1, wrapper._live_order_submit_attempt_count)

    def test_entry_then_exit_keeps_entry_budget_and_audits_both(self):
        wrapper = self.wrapper()
        wrapper._futures_create_order_with_fallback(ENTRY)
        closed, _ = wrapper._futures_create_order_with_fallback(CLOSE)
        self.assertEqual("FILLED", closed["status"])
        self.assertEqual(1, wrapper._live_order_submit_attempt_count)
        self.assertEqual(2, len(wrapper.client.orders))
        self.assertEqual(2, wrapper.get_order_intent_status()["intent_count"])
        rows = [json.loads(line) for line in wrapper._order_audit_log_path.read_text().splitlines()]
        self.assertEqual(2, sum(row["event"] == "exchange_order_response" for row in rows))
        with self.assertRaisesRegex(LiveTradingSafetyError, "live session order cap"):
            wrapper._futures_create_order_with_fallback(ENTRY)
        self.assertEqual(2, len(wrapper.client.orders))

    def test_close_all_submission_preserves_both_hedge_exits_at_exhausted_budget(self):
        wrapper = self.wrapper()
        wrapper._live_order_submit_attempt_count = 1
        for side, position_side in (("SELL", "LONG"), ("BUY", "SHORT")):
            with self.subTest(side=side):
                close_all_runtime._submit_futures_order(
                    wrapper, {**ENTRY, "side": side, "positionSide": position_side}
                )
        self.assertEqual(2, len(wrapper.client.orders))
        self.assertEqual(1, wrapper._live_order_submit_attempt_count)

    def test_exits_do_not_consume_budget_before_first_entry(self):
        wrapper = self.wrapper()
        wrapper._futures_create_order_with_fallback(CLOSE)
        self.assertEqual(0, getattr(wrapper, "_live_order_submit_attempt_count", 0))
        wrapper._futures_create_order_with_fallback(ENTRY)
        self.assertEqual(1, wrapper._live_order_submit_attempt_count)

    def test_exempt_exit_still_requires_other_safety_gates(self):
        for condition in ("ack", "audit", "health", "quantity", "step", "intent"):
            with self.subTest(condition=condition):
                wrapper = self.wrapper()
                wrapper._live_order_submit_attempt_count = 1
                params = dict(CLOSE)
                if condition == "ack":
                    wrapper._live_safety_config = {}
                elif condition == "audit":
                    wrapper._configure_order_audit(enabled=False, path=wrapper._order_audit_log_path)
                elif condition == "health":
                    wrapper.get_connector_health_snapshot = lambda: {"state": "offline", "health": "error"}
                elif condition == "quantity":
                    params["quantity"] = "NaN"
                elif condition == "step":
                    params["quantity"] = "0.1005"
                else:
                    params["symbol"] = ""
                with self.assertRaises(LiveTradingSafetyError) as error:
                    wrapper._futures_create_order_with_fallback(params)
                self.assertNotIn("session order cap", str(error.exception))
                self.assertEqual([], wrapper.client.orders)
                self.assertEqual(1, wrapper._live_order_submit_attempt_count)

    def test_exempt_exit_still_blocks_on_unresolved_exchange_intent(self):
        wrapper = self.wrapper(fail=True)
        with self.assertRaisesRegex(RuntimeError, "exchange rejected"):
            wrapper._futures_create_order_with_fallback(ENTRY)
        wrapper.client.fail = False
        with self.assertRaisesRegex(LiveTradingSafetyError, "Unresolved exchange order intent"):
            wrapper._futures_create_order_with_fallback(CLOSE)
        self.assertEqual(1, len(wrapper.client.orders))

    def test_concurrent_entry_budget_check_and_consume_is_atomic(self):
        wrapper = self.wrapper()
        wrapper.get_spot_symbol_filters = wrapper.get_futures_symbol_filters
        start = Barrier(2)
        first_read = Event()
        second_read = Event()
        release = Event()
        read_lock = Lock()
        reads = []
        original = guards._live_submit_attempt_count

        def scheduled_read(instance):
            value = original(instance)
            with read_lock:
                reads.append(value)
                first = len(reads) == 1
            (first_read if first else second_read).set()
            if first:
                self.assertTrue(release.wait(timeout=5))
            return value

        def admit(market):
            start.wait(timeout=5)
            try:
                wrapper._guard_live_order_submit(market=market, params=ENTRY)
                return True
            except LiveTradingSafetyError:
                return False

        with patch.object(guards, "_live_submit_attempt_count", side_effect=scheduled_read):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(admit, market) for market in ("spot", "futures")]
                try:
                    self.assertTrue(first_read.wait(timeout=5))
                    # Without atomic reservation, the competing reader observes
                    # the same zero before this first call can consume its slot.
                    second_read.wait(timeout=0.2)
                finally:
                    release.set()
                admitted = [future.result(timeout=5) for future in futures]
        self.assertEqual(1, sum(admitted))
        self.assertEqual([0, 1], reads)
        self.assertEqual(1, wrapper._live_order_submit_attempt_count)
        self.assertEqual([], wrapper.client.orders)

    def test_parallel_submission_boundary_allows_only_one_entry(self):
        wrapper = self.wrapper()
        start = Barrier(8)

        def submit(index):
            start.wait(timeout=5)
            params = {**ENTRY, "newClientOrderId": f"budget-concurrent-{index}"}
            try:
                wrapper._futures_create_order_with_fallback(params)
                return True
            except LiveTradingSafetyError:
                return False

        with ThreadPoolExecutor(max_workers=8) as pool:
            admitted = list(pool.map(submit, range(8)))
        self.assertEqual(1, sum(admitted))
        self.assertEqual(1, len(wrapper.client.orders))
        self.assertEqual(1, wrapper._live_order_submit_attempt_count)

    def test_invalid_counter_blocks_entries_but_not_protective_exits(self):
        for count in (None, True, -1, 0.5, "0", "bad", float("nan"), float("inf")):
            with self.subTest(count=count):
                wrapper = self.wrapper()
                wrapper._live_order_submit_attempt_count = count
                with self.assertRaisesRegex(LiveTradingSafetyError, "counter is invalid"):
                    wrapper._futures_create_order_with_fallback(ENTRY)
                self.assertEqual([], wrapper.client.orders)
                wrapper._futures_create_order_with_fallback(CLOSE)
                self.assertEqual(1, len(wrapper.client.orders))

    def test_invalid_entry_does_not_consume_budget(self):
        wrapper = self.wrapper()
        with self.assertRaises(LiveTradingSafetyError):
            wrapper._futures_create_order_with_fallback({**ENTRY, "quantity": "NaN"})
        self.assertEqual(0, getattr(wrapper, "_live_order_submit_attempt_count", 0))
        wrapper._futures_create_order_with_fallback(ENTRY)
        self.assertEqual(1, len(wrapper.client.orders))

    def test_independent_wrappers_keep_independent_session_counters(self):
        first = self.wrapper()
        second = self.wrapper()
        first._futures_create_order_with_fallback(ENTRY)
        second._futures_create_order_with_fallback(ENTRY)
        self.assertEqual(1, first._live_order_submit_attempt_count)
        self.assertEqual(1, second._live_order_submit_attempt_count)


if __name__ == "__main__":
    unittest.main()
