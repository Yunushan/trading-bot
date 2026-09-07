from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.integrations.exchanges.binance.orders import order_intent_runtime as ledger
from app.integrations.exchanges.binance.orders.order_intent_provisioning import PROVISION_ACK, provision_order_intent_store
from app.settings.live_safety import LiveTradingSafetyError


class OrderIntentReconciliationSafetyTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.owner = SimpleNamespace(_order_audit_log_path=Path(directory) / "audit.jsonl", api_key="unit-api-key", mode="Live")
        provision_order_intent_store(self.owner, acknowledgement=PROVISION_ACK)
        self.params = {
            "newClientOrderId": "reconcile-A", "symbol": "BTCUSDT", "side": "BUY",
            "type": "MARKET", "quantity": "1",
        }
        ledger._begin_order_intent(self.owner, self.params, market="futures", source="offline-test")
        ledger._mark_order_intent_unknown(self.owner, self.params, error="ambiguous acknowledgement")

    def response(self, **changes):
        return {
            "status": "FILLED", "clientOrderId": "reconcile-A", "symbol": "BTCUSDT",
            "side": "BUY", "origQty": "1", "orderId": 123, "executedQty": "1", **changes,
        }

    def reconcile(self, response):
        self.owner._query_order_intent_exchange = lambda _record: response
        return ledger.reconcile_order_intent(self.owner, "reconcile-A")

    def assert_unresolved(self, response):
        result = self.reconcile(response)
        self.assertFalse(result["reconciled"])
        self.assertEqual("unknown", result["state"])
        self.assertTrue(result["error"])
        self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])
        with self.assertRaisesRegex(LiveTradingSafetyError, "Unresolved exchange order intent"):
            ledger._begin_order_intent(
                self.owner, {**self.params, "newClientOrderId": "reconcile-B"},
                market="futures", source="offline-test",
            )

    def test_unknown_or_non_string_status_does_not_resolve_an_intent(self):
        for status in ("ERROR", "SUCCESS", "NOT_FOUND", "", None, True, 200, [], {}, "PENDING_NEW"):
            with self.subTest(status=status):
                self.assert_unresolved(self.response(status=status))

    def test_response_identity_must_match_the_persisted_order(self):
        for field, values in {
            "clientOrderId": (None, "", "reconcile-B", "RECONCILE-A", [], 123),
            "symbol": (None, "", "ETHUSDT", {}, 123),
            "orderId": (None, "", False, True, 0, -1, 1.5, "nan", "1e3", [], {}),
        }.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    self.assert_unresolved(self.response(**{field: value}))

    def test_error_envelope_with_plausible_order_fields_is_not_confirmation(self):
        self.assert_unresolved(self.response(code=-2013, msg="Order does not exist"))

    def test_missing_response_or_not_found_query_preserves_block(self):
        for response in (None, [], {}, {"code": -2013, "msg": "Order does not exist"}):
            with self.subTest(response=response):
                self.assert_unresolved(response)
        self.owner._query_order_intent_exchange = lambda _record: (_ for _ in ()).throw(TimeoutError("offline"))
        result = ledger.reconcile_order_intent(self.owner, "reconcile-A")
        self.assertFalse(result["reconciled"])
        self.assertEqual("unknown", result["state"])

    def test_matching_confirmation_resolves_but_keeps_duplicate_id_blocked(self):
        result = self.reconcile(self.response(orderId="123"))
        self.assertTrue(result["reconciled"])
        self.assertEqual("accepted", result["state"])
        self.assertEqual("123", result["exchange_order_id"])
        self.assertEqual(0, ledger.get_order_intent_status(self.owner)["unresolved_count"])
        with self.assertRaisesRegex(LiveTradingSafetyError, "already has state accepted"):
            ledger._begin_order_intent(self.owner, self.params, market="futures", source="offline-test")
        ledger._begin_order_intent(
            self.owner, {**self.params, "newClientOrderId": "reconcile-B"},
            market="futures", source="offline-test",
        )

    def test_canceled_and_expired_orders_cannot_be_retried_under_the_same_id(self):
        for status in ("CANCELED", "EXPIRED", "EXPIRED_IN_MATCH"):
            with self.subTest(status=status):
                ledger._update_order_intent_by_id(self.owner, "reconcile-A", state="unknown")
                result = self.reconcile(self.response(status=status, executedQty="0.5"))
                self.assertTrue(result["reconciled"])
                self.assertEqual("accepted", result["state"])
                self.assertEqual(status, result["exchange_status"])
                with self.assertRaisesRegex(LiveTradingSafetyError, "already has state accepted"):
                    ledger._begin_order_intent(self.owner, self.params, market="futures", source="offline-test")

    def test_rejected_response_requires_explicit_zero_execution(self):
        for executed in (None, "", "nan", "inf", "-1", "0.1", False, 0, 0.0, {}, []):
            with self.subTest(executed=executed):
                self.assert_unresolved(self.response(status="REJECTED", executedQty=executed))
        result = self.reconcile(self.response(status="REJECTED", executedQty="0.000"))
        self.assertTrue(result["reconciled"])
        self.assertEqual("rejected", result["state"])

    def test_documented_spot_pending_states_are_supported_only_for_spot(self):
        for status in ("PENDING_NEW", "PENDING_CANCEL"):
            with self.subTest(status=status):
                ledger._update_order_intent_by_id(self.owner, "reconcile-A", state="unknown", market="spot")
                result = self.reconcile(self.response(status=status, executedQty="0"))
                self.assertTrue(result["reconciled"])
                self.assertEqual("accepted", result["state"])

    def test_late_query_cannot_overwrite_a_newer_acceptance(self):
        for response in (None, self.response(status="ERROR"), self.response(status="REJECTED", executedQty="0")):
            with self.subTest(response=response):
                ledger._update_order_intent_by_id(self.owner, "reconcile-A", state="unknown")

                def query(_record):
                    ledger._mark_order_intent_accepted(self.owner, self.params, via="primary", result=self.response(orderId=456))
                    return response

                self.owner._query_order_intent_exchange = query
                result = ledger.reconcile_order_intent(self.owner, "reconcile-A")
                self.assertFalse(result["reconciled"])
                self.assertEqual("accepted", result["state"])
                record = ledger._get_order_intent_record(self.owner, "reconcile-A")
                self.assertEqual("456", record["exchange_order_id"])
                self.assertEqual("primary", record["last_via"])
                self.assertEqual(0, ledger.get_order_intent_status(self.owner)["unresolved_count"])

    def test_late_transport_error_cannot_restore_the_old_pending_state(self):
        def query(_record):
            ledger._mark_order_intent_accepted(self.owner, self.params, via="primary", result=self.response(orderId=456))
            raise TimeoutError("late query")

        self.owner._query_order_intent_exchange = query
        result = ledger.reconcile_order_intent(self.owner, "reconcile-A")
        self.assertFalse(result["reconciled"])
        self.assertEqual("accepted", result["state"])
        self.assertEqual("accepted", ledger._get_order_intent_record(self.owner, "reconcile-A")["state"])

    def test_transport_error_without_a_message_is_not_reported_as_reconciled(self):
        def query(_record):
            raise TimeoutError()

        self.owner._query_order_intent_exchange = query
        result = ledger.reconcile_order_intent(self.owner, "reconcile-A")
        self.assertFalse(result["reconciled"])
        self.assertTrue(result["error"])
        self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])

    def test_late_success_cannot_resolve_a_replacement_intent(self):
        def query(_record):
            ledger._update_order_intent_by_id(self.owner, "reconcile-A", state="rejected")
            ledger._begin_order_intent(self.owner, self.params, market="futures", source="replacement")
            return self.response()

        self.owner._query_order_intent_exchange = query
        result = ledger.reconcile_order_intent(self.owner, "reconcile-A")
        self.assertFalse(result["reconciled"])
        self.assertEqual("pending", result["state"])
        self.assertEqual(1, ledger.get_order_intent_status(self.owner)["unresolved_count"])
        self.assertEqual("replacement", ledger._get_order_intent_record(self.owner, "reconcile-A")["source"])


if __name__ == "__main__":
    unittest.main()
