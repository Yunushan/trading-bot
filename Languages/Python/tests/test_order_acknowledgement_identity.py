from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.integrations.exchanges.binance.orders import order_intent_runtime as intents
from app.integrations.exchanges.binance.orders.order_intent_provisioning import PROVISION_ACK, provision_order_intent_store
from app.settings.live_safety import LiveTradingSafetyError
from test_binance_package_split_smoke import _FuturesAuditWrapper, _SpotSizingWrapper


PARAMS = {"newClientOrderId": "ack-A", "symbol": "BTCUSDT", "side": "BUY", "type": "MARKET", "quantity": "1"}


def response(**changes):
    return {"clientOrderId": "ack-A", "symbol": "BTCUSDT", "side": "BUY", "orderId": 123,
            "status": "FILLED", "origQty": "1", "executedQty": "1", **changes}


class _LedgerSpotWrapper(_SpotSizingWrapper):
    pass


intents.bind_binance_order_intent_runtime(_LedgerSpotWrapper)


class OrderAcknowledgementIdentityTests(unittest.TestCase):
    def owner(self, market="futures"):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        owner = SimpleNamespace(_order_audit_log_path=Path(directory) / "audit.jsonl", api_key="unit-key", mode="Live")
        provision_order_intent_store(owner, acknowledgement=PROVISION_ACK)
        intents._begin_order_intent(owner, PARAMS, market=market, source="offline-test")
        intents._mark_order_intent_submitted(owner, PARAMS, via="primary")
        return owner

    def assert_blocked(self, owner):
        self.assertEqual(1, intents.get_order_intent_status(owner)["unresolved_count"])
        with self.assertRaisesRegex(LiveTradingSafetyError, "Unresolved exchange order intent"):
            intents._begin_order_intent(owner, dict(PARAMS, newClientOrderId="ack-B"), market="futures", source="offline-test")

    def test_invalid_primary_acknowledgement_cannot_clear_ambiguity(self):
        changes = [
            {field: value}
            for field, values in {
                "clientOrderId": (None, "", "ack-B", "ACK-A", 123, []),
                "symbol": (None, "", "ETHUSDT", 123, {}),
                "orderId": (None, "", True, False, 0, -1, "garbage", 1.5, {}),
                "status": (None, "", "SUCCESS", "ERROR", "NOT_FOUND", 200, []),
            }.items() for value in values
        ]
        changes += [{"code": -2013}, {"error": {"code": -2013}}, {"success": False}]
        for market in ("spot", "futures"):
            for payload in [None, [], {}, {"orderId": 123}] + [response(**change) for change in changes]:
                with self.subTest(market=market, payload=payload):
                    owner = self.owner(market)
                    with self.assertRaises(LiveTradingSafetyError):
                        intents._mark_order_intent_accepted(owner, PARAMS, via="primary", result=payload)
                    self.assert_blocked(owner)

    def test_matching_acknowledgement_keeps_duplicate_id_protected(self):
        for market in ("spot", "futures"):
            for status in ("NEW", "PARTIALLY_FILLED", "FILLED"):
                with self.subTest(market=market, status=status):
                    owner = self.owner(market)
                    executed = {"NEW": "0", "PARTIALLY_FILLED": "0.5", "FILLED": "1"}[status]
                    intents._mark_order_intent_accepted(owner, PARAMS, via="primary", result=response(status=status, executedQty=executed))
                    record = intents._get_order_intent_record(owner, "ack-A")
                    state = "unknown" if market == "futures" and status != "FILLED" else "accepted"
                    self.assertEqual((state, "123", status),
                                     (record["state"], record["exchange_order_id"], record["exchange_status"]))
                    with self.assertRaisesRegex(LiveTradingSafetyError, f"already has state {state}"):
                        intents._begin_order_intent(owner, PARAMS, market=market, source="offline-test")
                    if state == "unknown":
                        self.assert_blocked(owner)
                    else:
                        intents._begin_order_intent(owner, dict(PARAMS, newClientOrderId="ack-B"), market=market, source="offline-test")

    def test_late_acknowledgement_cannot_overwrite_newer_observation(self):
        for payload in (response(), response(clientOrderId="wrong")):
            with self.subTest(payload=payload):
                owner = self.owner()
                validate = intents._validate_reconciliation_response

                def concurrent_observation(record, result):
                    intents._update_order_intent_by_id(owner, "ack-A", state="unknown", newer_observation=True)
                    return validate(record, result)

                with patch.object(intents, "_validate_reconciliation_response", side_effect=concurrent_observation):
                    with self.assertRaises(LiveTradingSafetyError):
                        intents._mark_order_intent_accepted(owner, PARAMS, via="primary", result=payload)
                record = intents._get_order_intent_record(owner, "ack-A")
                self.assertTrue(record["newer_observation"])
                self.assertNotIn("accepted_at", record)
                self.assert_blocked(owner)

    def test_changed_exchange_order_id_cannot_confirm_an_ordinary_order(self):
        owner = self.owner()
        intents._update_order_intent_by_id(owner, "ack-A", state="unknown", exchange_order_id="456")
        with self.assertRaises(LiveTradingSafetyError):
            intents._mark_order_intent_accepted(owner, PARAMS, via="primary", result=response())
        self.assert_blocked(owner)

    def test_error_envelope_cannot_resolve_a_query_either(self):
        for change in ({"error": {"code": -2013}}, {"success": False}):
            with self.subTest(change=change):
                owner = self.owner()
                owner._query_order_intent_exchange = lambda _record: response(**change)
                result = intents.reconcile_order_intent(owner, "ack-A")
                self.assertFalse(result["reconciled"])
                self.assert_blocked(owner)

    def test_futures_limit_identity_failure_stops_every_fallback_stage(self):
        for stage in ("primary", "fallback-pybinance", "fallback-rest", "fallback-rest-alt"):
            with self.subTest(stage=stage):
                wrapper = _FuturesAuditWrapper(mode="Demo/Testnet")
                self.addCleanup(wrapper.close)
                wrong = response(clientOrderId="unrelated-order")
                wrapper.client.futures_create_order = Mock(
                    return_value=wrong, side_effect=None if stage == "primary" else RuntimeError("primary unavailable"),
                )
                fallback = SimpleNamespace(futures_create_order=Mock(return_value=wrong))
                wrapper._testnet_order_fallback_client = Mock(return_value=fallback if stage == "fallback-pybinance" else None)
                wrapper._futures_api_prefix = lambda: "/fapi"
                wrapper._alternate_futures_prefix = Mock(return_value="/dapi")
                wrapper._clear_futures_http_error = Mock()
                wrapper._last_futures_http_error = {"code": -2015}
                wrapper._http_signed_futures_request = Mock(
                    return_value=wrong,
                    side_effect=[RuntimeError("REST unavailable"), wrong] if stage == "fallback-rest-alt" else None,
                )
                with self.assertRaises(LiveTradingSafetyError):
                    wrapper._futures_create_order_with_fallback(dict(PARAMS, type="LIMIT", price="100"))
                self.assert_blocked(wrapper)
                wrapper.client.futures_create_order.assert_called_once()
                self.assertEqual(1 if stage == "fallback-pybinance" else 0, fallback.futures_create_order.call_count)
                self.assertEqual({"primary": 0, "fallback-pybinance": 0, "fallback-rest": 1, "fallback-rest-alt": 2}[stage],
                                 wrapper._http_signed_futures_request.call_count)
                self.assertEqual(1 if stage == "fallback-rest-alt" else 0, wrapper._alternate_futures_prefix.call_count)

    def test_spot_submission_rejects_response_for_another_order(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        wrapper = _LedgerSpotWrapper(order_response=response(clientOrderId="unrelated-order"))
        wrapper.mode, wrapper.api_key = "Live", "unit-key"
        wrapper._configure_order_audit(path=Path(directory) / "spot.jsonl")
        provision_order_intent_store(wrapper, acknowledgement=PROVISION_ACK)
        result = wrapper.place_spot_market_order("BTCUSDT", "BUY", quantity=1)
        self.assertFalse(result["ok"])
        self.assertEqual(1, len(wrapper.client.orders))
        self.assert_blocked(wrapper)

    def test_spot_submission_does_not_undo_concurrent_reconciliation(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        wrapper = _LedgerSpotWrapper()
        wrapper.mode, wrapper.api_key = "Live", "unit-key"
        wrapper._configure_order_audit(path=Path(directory) / "spot.jsonl")
        provision_order_intent_store(wrapper, acknowledgement=PROVISION_ACK)
        wrapper.client.create_order = Mock(side_effect=lambda **params: response(clientOrderId=params["newClientOrderId"]))
        validate = intents._validate_reconciliation_response

        def concurrent_observation(record, result):
            intents._update_order_intent_by_id(
                wrapper, record["client_order_id"], state="accepted", exchange_order_id="123", reconciled_at="newer",
            )
            return validate(record, result)

        with patch.object(intents, "_validate_reconciliation_response", side_effect=concurrent_observation):
            result = wrapper.place_spot_market_order("BTCUSDT", "BUY", quantity=1)
        self.assertFalse(result["ok"])
        client_id = wrapper.client.create_order.call_args.kwargs["newClientOrderId"]
        record = intents._get_order_intent_record(wrapper, client_id)
        self.assertEqual(("accepted", "newer"), (record["state"], record["reconciled_at"]))
        self.assertNotIn("uncertain_at", record)
        wrapper.client.create_order.assert_called_once()

    def test_valid_bound_spot_submission_succeeds(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        wrapper = _LedgerSpotWrapper()
        wrapper.mode, wrapper.api_key = "Live", "unit-key"
        wrapper._configure_order_audit(path=Path(directory) / "spot.jsonl")
        provision_order_intent_store(wrapper, acknowledgement=PROVISION_ACK)
        wrapper.client.create_order = Mock(side_effect=lambda **params: response(clientOrderId=params["newClientOrderId"]))
        result = wrapper.place_spot_market_order("BTCUSDT", "BUY", quantity=1)
        self.assertTrue(result["ok"])
        client_id = wrapper.client.create_order.call_args.kwargs["newClientOrderId"]
        self.assertEqual("accepted", intents._get_order_intent_record(wrapper, client_id)["state"])

    def test_terminal_market_response_confirms_zero_execution_but_spot_requires_reconciliation(self):
        for status in ("REJECTED", "CANCELED", "EXPIRED", "EXPIRED_IN_MATCH"):
            with self.subTest(status=status):
                owner = self.owner()
                intents._mark_order_intent_accepted(owner, PARAMS, via="primary", result=response(status=status, executedQty="0"))
                self.assertEqual(0, intents.get_order_intent_status(owner)["unresolved_count"])
                self.assertEqual("0", intents._get_order_intent_record(owner, "ack-A")["executed_qty"])
                spot = self.owner("spot")
                with self.assertRaises(LiveTradingSafetyError):
                    intents._mark_order_intent_accepted(spot, PARAMS, via="primary", result=response(status=status, executedQty="0"))
                self.assert_blocked(spot)

    def test_spot_pending_states_are_not_futures_acknowledgements(self):
        for status in ("PENDING_NEW", "PENDING_CANCEL"):
            for market in ("spot", "futures"):
                with self.subTest(status=status, market=market):
                    owner = self.owner(market)
                    if market == "spot":
                        intents._mark_order_intent_accepted(owner, PARAMS, via="primary", result=response(status=status))
                        self.assertEqual("accepted", intents._get_order_intent_record(owner, "ack-A")["state"])
                    else:
                        with self.assertRaises(LiveTradingSafetyError):
                            intents._mark_order_intent_accepted(owner, PARAMS, via="primary", result=response(status=status))
                        self.assert_blocked(owner)


if __name__ == "__main__":
    unittest.main()
