"""Conditional batch integration controls; no account or order authority."""

from copy import deepcopy
from fractions import Fraction
import unittest
from unittest.mock import patch

from app.integrations.exchanges.binance.orders import spot_account_risk_contract as risk
from app.integrations.exchanges.binance.orders import spot_account_risk_store as store
from test_spot_account_risk_contract import token, utc
import test_spot_account_risk_store as fixture


def _legacy_replay(raw: bytes, identity: dict) -> tuple[dict, risk.State]:
    value = store._fields(store._decode(raw), {"version", "risk_store_id", "identity", "opening", "opening_provenance", "entries", "head", "projection"})
    if store._positive(value["version"]) != 1 or store._encode(value["identity"]) != store._encode(identity):
        store._fail("Risk snapshot identity/version changed")
    risk.parse_identity(value["identity"])
    store_id = store._uuid(value["risk_store_id"])
    opening = value["opening"]
    state = risk.opening_state(opening)
    if store._encode(opening["identity"]) != store._encode(identity):
        store._fail("Opening account/store identity changed")
    proof = store._provenance(value["opening_provenance"], identity)
    chain = store._sha(store._encode({"risk_store_id": store_id, "opening": opening, "provenance": proof}))
    if type(value["entries"]) is not list:
        store._fail("Complete ordered event history required")
    seen = set()
    for revision, row in enumerate(value["entries"], 2):
        row = store._fields(row, {"event", "provenance", "previous_chain_head", "chain_head", "state_head"})
        event = risk.parse_event(row["event"])
        if event.event_id in seen or row["previous_chain_head"] != chain:
            store._fail("Historical event identity/chain changed")
        proof = store._provenance(row["provenance"], identity)
        state = risk.apply_event(state, event)
        candidate = {"revision": revision, "previous_chain_head": chain, "event": row["event"],
                     "provenance": proof, "state_head": state.head}
        chain = store._sha(store._encode(candidate))
        if store._hash(row["chain_head"]) != chain or store._hash(row["state_head"]) != state.head:
            store._fail("Historical revision commitment changed")
        seen.add(event.event_id)
    expected_head = {"revision": len(value["entries"]) + 1, "chain_head": chain, "state_head": state.head}
    if store._encode(value["head"]) != store._encode(expected_head) or store._encode(value["projection"]) != store._encode(store._projection(state)):
        store._fail("Head/projection differs from complete history replay")
    return value, state



class RiskStoreBatchReplayTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture.RiskStoreTests(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def mixed_history(self):
        f = self.f
        receipt = f.reserve(f.boot())
        receipt, _ = f.append(receipt, "TRANSPORT", {"request_id": "request-A"})
        receipt, _ = f.append(
            receipt,
            "FILL",
            {
                "request_id": "request-A",
                "order_id": 42,
                "trade_id": 7,
                "quantity": "1",
                "price": "9",
                "quote_quantity": "9",
                "fee_quote": "0.09",
                "proof_basis": "exact_trade_USDT_fee",
            },
        )
        receipt, _ = f.append(receipt, "UNKNOWN", {"request_id": "request-A", "evidence_ref": "uncertain"})
        receipt, _ = f.append(
            receipt,
            "TERMINAL",
            {
                "request_id": "request-A",
                "status": "CANCELED",
                "order_id": 42,
                "executed_quantity": "1",
                "trade_ids": [7],
                "proof_basis": "complete_request_bound_terminal_and_trades",
                "evidence_ref": "complete",
            },
        )
        at = receipt.state.at + 1
        observe = {
            "positions": [
                {"asset": row.asset, "quantity": token(row.quantity), "external_locked": token(row.external_locked)}
                for row in receipt.state.positions
            ],
            "cash_quote": token(receipt.state.cash_quote),
            "marks": {asset: token(value) for asset, value in receipt.state.marks},
            "balances_at": utc(at),
            "marks_at": utc(at),
            "external_open_request_ids": [],
        }
        receipt, _ = f.append(receipt, "OBSERVE", observe, at=at)
        receipt, _ = f.append(
            receipt,
            "RESET",
            {
                "kill_event_id": receipt.state.killed[0],
                "operator_authorizer_ref": receipt.state.policy.operator_authorizer_ref,
                "evidence_ref": "supplied-reference-not-authorization",
            },
        )
        finance = (
            receipt.state.positions,
            receipt.state.cash_quote,
            receipt.state.realized_quote,
            receipt.state.reservations,
            receipt.state.trades,
            receipt.state.attempts,
        )
        at = receipt.state.period_end
        observe["balances_at"] = observe["marks_at"] = utc(at)
        receipt, _ = f.append(receipt, "OBSERVE", observe, at=at)
        receipt, _ = f.append(
            receipt,
            "ROLLOVER",
            {
                "next_period": "synthetic-B",
                "starts_at": utc(at),
                "ends_at": utc(at + 100),
                "evidence_ref": "supplied-period-only",
            },
            at=at,
        )
        return receipt, finance

    def test_complete_financial_history_matches_original_replay_and_storage(self):
        f = self.f
        with f.scope():
            receipt, finance = self.mixed_history()
            original_raw = f.path.read_bytes()
            protected = f.raw_anchor()
            writes = f.port.writes
            old_value, old_state = _legacy_replay(original_raw, f.identity)
            new_value, new_state = store._replay(original_raw, f.identity)
            reopened = store.read_risk_store(f.path, f.identity)
            self.assertEqual(new_value, old_value)
            self.assertEqual(new_state, old_state)
            self.assertEqual(reopened.state, receipt.state)
            self.assertEqual(reopened.raw, receipt.raw)
            self.assertEqual(reopened.file_identity, receipt.file_identity)
            self.assertEqual(reopened.protected_raw, receipt.protected_raw)
            self.assertEqual(reopened.risk_store_id, receipt.risk_store_id)
            self.assertEqual(reopened.chain_head, receipt.chain_head)
            self.assertEqual(reopened.revision, 10)
            self.assertEqual(reopened.state.cash_quote, Fraction("990.91"))
            self.assertEqual(
                finance,
                (
                    reopened.state.positions,
                    reopened.state.cash_quote,
                    reopened.state.realized_quote,
                    reopened.state.reservations,
                    reopened.state.trades,
                    reopened.state.attempts,
                ),
            )
            self.assertEqual(
                tuple(event.kind for event in reopened.state.history),
                ("RESERVE_ENTRY", "TRANSPORT", "FILL", "UNKNOWN", "TERMINAL", "OBSERVE", "RESET", "OBSERVE", "ROLLOVER"),
            )
            self.assertEqual(store._projection(new_state), old_value["projection"])
            self.assertEqual(f.path.read_bytes(), original_raw)
            self.assertEqual(f.raw_anchor(), protected)
            self.assertEqual(f.port.writes, writes)

    def test_coherent_false_earlier_state_head_cannot_hide_behind_valid_final_state(self):
        f = self.f
        with f.scope():
            receipt, _ = f.append(f.reserve(f.boot()))
            original_raw, protected = receipt.raw, f.raw_anchor()
            value = deepcopy(store._decode(original_raw))
            self.assertNotEqual(value["entries"][0]["state_head"], "a" * 64)
            value["entries"][0]["state_head"] = "a" * 64
            chain = store._sha(
                store._encode(
                    {
                        "risk_store_id": value["risk_store_id"],
                        "opening": value["opening"],
                        "provenance": value["opening_provenance"],
                    }
                )
            )
            for revision, row in enumerate(value["entries"], 2):
                row["previous_chain_head"] = chain
                chain = store._sha(
                    store._encode(
                        {
                            "revision": revision,
                            "previous_chain_head": chain,
                            "event": row["event"],
                            "provenance": row["provenance"],
                            "state_head": row["state_head"],
                        }
                    )
                )
                row["chain_head"] = chain
            value["head"]["chain_head"] = chain
            raw = store._encode(value)
            anchor = store._decode(protected)
            anchor["head"] = store._head(raw, value)
            f.path.write_bytes(raw)
            f.set_anchor(anchor)
            adversarial_protected = f.raw_anchor()
            writes = f.port.writes
            # The fake anchor rewrite isolates full historical semantic verification.
            with self.assertRaisesRegex(store.RiskStoreError, "Historical revision commitment changed"):
                _legacy_replay(raw, f.identity)
            with self.assertRaisesRegex(store.RiskStoreError, "Historical revision commitment changed"):
                store.read_risk_store(f.path, f.identity)
            self.assertEqual(f.path.read_bytes(), raw)
            self.assertEqual(f.raw_anchor(), adversarial_protected)
            self.assertEqual(f.port.writes, writes)
            f.path.write_bytes(original_raw)
            f.port.values[next(iter(f.port.values))] = protected
            self.assertEqual(store.read_risk_store(f.path, f.identity).state, receipt.state)

    def test_actual_complete_batch_then_scope_loss_cannot_issue_receipt(self):
        f = self.f
        with f.scope():
            receipt, _ = f.append(f.boot())
            original_raw, protected, writes = receipt.raw, f.raw_anchor(), f.port.writes
            real = risk.replay_events

            def revoke_after_replay(opening, events):
                result = real(opening, events)
                f.live = False
                return result

            try:
                with patch.object(risk, "replay_events", side_effect=revoke_after_replay):
                    with self.assertRaisesRegex(store.RiskStoreError, "Synthetic lifetime revoked"):
                        store.read_risk_store(f.path, f.identity)
            finally:
                f.live = True
            self.assertEqual(f.path.read_bytes(), original_raw)
            self.assertEqual(f.raw_anchor(), protected)
            self.assertEqual(f.port.writes, writes)
            self.assertEqual(store.read_risk_store(f.path, f.identity).state, receipt.state)

    def test_actual_complete_batch_cancellation_preserves_exact_primary_and_storage(self):
        f = self.f
        with f.scope():
            receipt, _ = f.append(f.boot())
            original_raw, protected, writes = receipt.raw, f.raw_anchor(), f.port.writes
            real = risk.replay_events
            for interruption in (KeyboardInterrupt("after-complete-batch"), SystemExit("after-complete-batch")):
                with self.subTest(kind=type(interruption).__name__):
                    def cancel_after_replay(opening, events):
                        real(opening, events)
                        raise interruption

                    with patch.object(risk, "replay_events", side_effect=cancel_after_replay):
                        with self.assertRaises(type(interruption)) as caught:
                            store.read_risk_store(f.path, f.identity)
                    self.assertIs(caught.exception, interruption)
                    self.assertEqual(f.path.read_bytes(), original_raw)
                    self.assertEqual(f.raw_anchor(), protected)
                    self.assertEqual(f.port.writes, writes)
            self.assertEqual(store.read_risk_store(f.path, f.identity).state, receipt.state)


if __name__ == "__main__":
    unittest.main()
