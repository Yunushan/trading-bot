"""Standalone draft tests. All numbers are synthetic test inputs, not policy defaults."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from fractions import Fraction
import json
import unittest

from app.integrations.exchanges.binance.orders import spot_account_risk_contract as risk


def token(value):
    value = Fraction(value)
    denominator = value.denominator
    twos = fives = 0
    while denominator % 2 == 0:
        twos += 1
        denominator //= 2
    while denominator % 5 == 0:
        fives += 1
        denominator //= 5
    if denominator != 1:
        raise AssertionError("Observed amount cannot use a rounded decimal")
    scale = max(twos, fives)
    numerator = abs(value.numerator) * 2 ** (scale - twos) * 5 ** (scale - fives)
    digits = str(numerator).rjust(scale + 1, "0")
    text = digits if scale == 0 else (digits[:-scale] + "." + digits[-scale:]).rstrip("0").rstrip(".")
    return ("-" if value < 0 else "") + text


def utc(stamp):
    return datetime.fromtimestamp(stamp, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def policy():
    return {
        "version": 1,
        "policy_id": "20000000-0000-4000-8000-000000000001",
        "operator_authorizer_ref": "synthetic-policy-review-only",
        "quote_asset": "USDT",
        "exposure_basis": "long_asset_marks_plus_remaining_entry_max_mark_or_limit_with_fee_bound",
        "loss_basis": "cumulative_realized_plus_unrealized_inclusive_quote_fees",
        "cost_basis": "exact_weighted_average",
        "balance_basis": "total_base_external_base_locks_quote_net_external_locks",
        "fee_basis": "nonnegative_USDT_only_rate_bound_no_rebates",
        "time_basis": "caller_verified_UTC_seconds",
        "limit_semantics": "exposure_lte_loss_lt",
        "exit_semantics": "unencumbered_base_no_borrow",
        "reset_semantics": "clear_kill_only_preserve_all_accounting",
        "rollover_semantics": "fresh_reconciled_contiguous_explicit_UTC_interval_carry_all",
        "attempt_semantics": "entry_total_entry_window_all_order_handoff_window_keep_all",
        "gross_limit_quote": "1000",
        "net_limit_quote": "1000",
        "asset_limit_quote": "1000",
        "loss_limit_quote": "100",
        "max_quote_fee_rate": "0.01",
        "position_limit": 2,
        "entry_attempt_limit": 3,
        "entry_rate_limit": 2,
        "rate_window_seconds": 60,
        "transport_rate_limit": 10,
        "transport_rate_window_seconds": 60,
        "balance_max_age_seconds": 30,
        "mark_max_age_seconds": 30,
        "max_clock_step_seconds": 120,
        "future_skew_seconds": 0,
    }


def opening():
    return {
        "identity": {"version": 1, "exchange": "binance", "market": "spot", "environment": "live",
                     "account_uid": 101, "ledger_store_id": "10000000-0000-4000-8000-000000000001"},
        "policy": policy(),
        "positions": [{"asset": "BTC", "quantity": "0", "cost_quote": "0", "external_locked": "0"},
                      {"asset": "ETH", "quantity": "0", "cost_quote": "0", "external_locked": "0"}],
        "cash_quote": "1000", "marks": {"BTC": "10", "ETH": "20"}, "realized_quote": "0",
        "at": "2026-10-04T00:00:00Z",
        "period": {"label": "synthetic-period-A", "starts_at": "2026-10-04T00:00:00Z", "ends_at": "2026-10-04T00:01:40Z"},
    }


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.serial = 0

    def event(self, state, kind, data, *, at=None, event_id=None):
        self.serial += 1
        return risk.parse_event({"event_id": event_id or f"event-{self.serial}", "expected_head": state.head,
                                 "at": utc(state.at + 1 if at is None else at), "kind": kind, "data": data})

    def apply(self, state, kind, data, **kwargs):
        return risk.apply_event(state, self.event(state, kind, data, **kwargs))

    def reserve(self, state, request="request-A", *, buy=True, quantity="2", price="10", asset="BTC"):
        return self.apply(state, "RESERVE_ENTRY" if buy else "RESERVE_EXIT",
                          {"request_id": request, "asset": asset, "quantity": quantity,
                           "order_type": "LIMIT_FOK" if buy else "MARKET", "limit_price": price if buy else None})

    def submit(self, state, request="request-A"):
        return self.apply(state, "TRANSPORT", {"request_id": request})

    def fill(self, state, request="request-A", *, quantity="1", price="9", fee="0.09", trade=7, order=42):
        return self.apply(state, "FILL", {"request_id": request, "order_id": order, "trade_id": trade,
                          "quantity": quantity, "price": price, "quote_quantity": token(Fraction(quantity) * Fraction(price)),
                          "fee_quote": fee, "proof_basis": "exact_trade_USDT_fee"})

    def terminal(self, state, request="request-A", *, status="CANCELED", order=42):
        row = next(row for row in state.reservations if row.request_id == request)
        return self.apply(state, "TERMINAL", {"request_id": request, "status": status, "order_id": order,
                          "executed_quantity": token(row.filled), "trade_ids": sorted(row.trade_ids),
                          "proof_basis": "complete_request_bound_terminal_and_trades", "evidence_ref": "synthetic-query-and-trades"})

    def observation(self, state, *, marks=None, at=None, marks_at=None):
        at = state.at + 1 if at is None else at
        return {"positions": [{"asset": row.asset, "quantity": token(row.quantity), "external_locked": token(row.external_locked)}
                              for row in state.positions], "cash_quote": token(state.cash_quote),
                "marks": marks or {asset: token(price) for asset, price in state.marks}, "balances_at": utc(at),
                "marks_at": utc(at if marks_at is None else marks_at),
                "external_open_request_ids": sorted(row.request_id for row in state.reservations
                                                     if row.status in {"submitted", "partial"} and row.remaining > 0)}

    def observe(self, state, **kwargs):
        at = kwargs.get("at", state.at + 1)
        return self.apply(state, "OBSERVE", self.observation(state, **kwargs), at=at)

    def kill(self, state):
        return self.apply(state, "KILL", {"reason": "synthetic-review", "evidence_ref": "synthetic-kill"})

    def reset_data(self, state):
        return {"kill_event_id": state.killed[0], "operator_authorizer_ref": state.policy.operator_authorizer_ref,
                "evidence_ref": "explicit-reference-is-not-authorization"}

    def finance(self, state):
        return (state.identity, state.policy, state.positions, state.cash_quote, state.realized_quote,
                state.reservations, state.trades, state.attempts)

    def rollover_data(self, state, label="B"):
        return {"next_period": label, "starts_at": utc(state.period_end), "ends_at": utc(state.period_end + 100),
                "evidence_ref": "synthetic-explicit-interval-review"}

    def test_all_policy_fields_mandatory_and_unsupported_bases_reject(self):
        for key in policy():
            with self.subTest(missing=key):
                raw = policy()
                del raw[key]
                with self.assertRaises(risk.ContractError):
                    risk.parse_policy(raw)
        for key, value in {"daily_loss_basis": "new-default", "fee_basis": "base_asset_deduction",
                           "reset_semantics": "zero_counters", "quote_asset": "USDC",
                           "entry_rate_limit": True, "max_quote_fee_rate": False}.items():
            with self.subTest(key=key):
                raw = policy()
                raw[key] = value
                with self.assertRaises(risk.ContractError):
                    risk.parse_policy(raw)

    def test_identity_literals_reject_unsupported_canonical_json(self):
        identity = opening()["identity"]
        expected = risk.Identity(identity["account_uid"], identity["ledger_store_id"])
        self.assertEqual(risk.parse_identity(identity), expected)
        self.assertEqual(risk.parse_identity(risk.decode_contract(json.dumps(identity).encode("utf-8"))), expected)
        for name, wrong in (("exchange", "coinbase"), ("market", "futures"), ("environment", "paper")):
            with self.subTest(field=name):
                raw = dict(identity, **{name: wrong})
                with self.assertRaises(risk.ContractError):
                    risk.parse_identity(raw)
                with self.assertRaises(risk.ContractError):
                    risk.parse_identity(risk.decode_contract(json.dumps(raw).encode("utf-8")))

    def test_identity_literals_require_exact_string_types(self):
        class PlainString(str):
            pass

        class EqualString(str):
            def __eq__(self, other):
                return True

            def __ne__(self, other):
                return False

        class EqualObject:
            def __eq__(self, other):
                return True

            def __ne__(self, other):
                return False

        class RaisingString(str):
            def __ne__(self, other):
                raise AssertionError("Literal comparison must not precede exact type rejection")

        identity = opening()["identity"]
        for name, expected, wrong in (("exchange", "binance", "coinbase"),
                                      ("market", "spot", "futures"), ("environment", "live", "paper")):
            cases = (PlainString(expected), EqualString(expected), EqualString(wrong), EqualObject(),
                     RaisingString(wrong), expected.encode("ascii"), None, True, 1)
            for index, invalid in enumerate(cases):
                with self.subTest(field=name, case=index):
                    with self.assertRaises(risk.ContractError):
                        risk.parse_identity(dict(identity, **{name: invalid}))

    def test_canonical_decimals_json_and_identity(self):
        for bad in [True, 1, 1.0, "NaN", "Infinity", "1e2", "01", "1.0", "-0", " 1", "0.10", "1\n"]:
            with self.subTest(decimal=bad):
                raw = policy()
                raw["gross_limit_quote"] = bad
                with self.assertRaises(risk.ContractError):
                    risk.parse_policy(raw)
        for raw in [b'[]', b'{"a":1,"a":2}', b'{"a":NaN}', b'{"x":1e309}', b'{"nested":[1e309]}',
                    b'{"price":1.5}', b'\xff', '{"a":1}']:
            with self.subTest(json=raw):
                with self.assertRaises(risk.ContractError):
                    risk.decode_contract(raw)
        for key, value in [("account_uid", True), ("environment", "testnet"), ("credential_fingerprint", "key-A"),
                           ("ledger_store_id", "NOT-A-UUID")]:
            raw = opening()["identity"]
            raw[key] = value
            with self.assertRaises(risk.ContractError):
                risk.parse_identity(raw)

    def test_detached_inputs_exact_event_and_state_cas(self):
        raw = opening()
        state = risk.opening_state(raw)
        raw["policy"]["gross_limit_quote"] = "1"
        raw["positions"][0]["quantity"] = "100"
        self.assertEqual(state.policy.value("gross_limit_quote"), 1000)
        self.assertEqual(state.positions[0].quantity, 0)
        payload = {"reason": "review", "evidence_ref": "proof"}
        event = self.event(state, "KILL", payload)
        payload["reason"] = "changed"
        result = risk.apply_event(state, event)
        self.assertEqual(result.killed[1], "review")
        self.assertIs(risk.apply_event(result, event), result)
        with self.assertRaises(risk.ContractError):
            risk.apply_event(result, replace(event, payload=event.payload.replace("review", "changed")))
        with self.assertRaises(risk.ContractError):
            risk.apply_event(result, self.event(state, "ROLLOVER", self.rollover_data(state)))
        with self.assertRaises(risk.ContractError):
            risk.apply_event(replace(state, cash_quote=Fraction(2000)), event)
        for forged in [replace(event, kind=[]), replace(event, payload="[]"), replace(event, at=True),
                       replace(event, payload=json.dumps(json.loads(event.payload), indent=2))]:
            with self.assertRaises(risk.ContractError):
                risk.apply_event(state, forged)

    def test_cash_exposure_asset_position_and_fee_bounds(self):
        state = risk.opening_state(opening())
        reserved = self.reserve(state, quantity="99")
        self.assertEqual(risk.metrics(reserved)["cash_bound"], Fraction("999.9"))
        self.assertEqual(risk.metrics(reserved)["gross"], Fraction("999.9"))
        with self.assertRaises(risk.ContractError):
            self.reserve(state, quantity="100")
        raw = opening()
        raw["marks"]["BTC"] = "20"
        with self.assertRaises(risk.ContractError):
            self.reserve(risk.opening_state(raw), quantity="50", price="10")
        raw = opening()
        raw["policy"]["asset_limit_quote"] = "15"
        with self.assertRaises(risk.ContractError):
            self.reserve(risk.opening_state(raw))
        raw = opening()
        raw["policy"]["position_limit"] = 1
        reserved = self.reserve(risk.opening_state(raw), quantity="1")
        with self.assertRaises(risk.ContractError):
            self.reserve(reserved, "ETH-entry", asset="ETH", quantity="1", price="20")

    def test_market_entry_has_no_claimed_hard_price_cap(self):
        state = risk.opening_state(opening())
        data = {"request_id": "market-buy", "asset": "BTC", "quantity": "1", "order_type": "MARKET", "limit_price": "10"}
        with self.assertRaisesRegex(risk.ContractError, "no hard price cap"):
            self.apply(state, "RESERVE_ENTRY", data)

    def test_partial_unknown_retains_remaining_and_exact_terminal_only_releases(self):
        state = self.submit(self.reserve(risk.opening_state(opening())))
        partial = self.fill(state)
        self.assertEqual(partial.cash_quote, Fraction("990.91"))
        self.assertEqual(partial.positions[0].cost_quote, Fraction("9.09"))
        self.assertEqual(partial.reservations[0].remaining, 1)
        self.assertEqual(risk.metrics(partial)["cash_bound"], Fraction("10.1"))
        unknown = self.apply(partial, "UNKNOWN", {"request_id": "request-A", "evidence_ref": "lost-response"})
        self.assertEqual(unknown.reservations[0].remaining, 1)
        self.assertIsNone(unknown.balance_at)
        self.assertIsNotNone(unknown.killed)
        observed = self.observe(unknown)
        self.assertEqual(risk.metrics(observed)["cash_bound"], Fraction("10.1"))
        with self.assertRaises(risk.ContractError):
            self.terminal(observed, status="FILLED")
        done = self.terminal(observed)
        self.assertEqual(done.reservations[0].remaining, 0)
        self.assertEqual(done.positions, partial.positions)
        self.assertEqual(done.cash_quote, partial.cash_quote)
        self.assertEqual(done.attempts, state.attempts)
        self.assertEqual(done.trades, partial.trades)
        self.assertEqual(done.killed, unknown.killed)
        self.assertEqual(len(done.reservations), 1)
        self.assertEqual(done.cash_quote + sum((row.cost_quote for row in done.positions), Fraction(0)), 1000)

    def test_terminal_trade_set_quantity_order_and_evidence_must_match(self):
        state = self.fill(self.submit(self.reserve(risk.opening_state(opening()))))
        data = {"request_id": "request-A", "status": "CANCELED", "order_id": 42, "executed_quantity": "1",
                "trade_ids": [7], "proof_basis": "complete_request_bound_terminal_and_trades", "evidence_ref": "proof"}
        for key, bad in [("executed_quantity", "0"), ("trade_ids", []), ("trade_ids", [7, 7]),
                         ("trade_ids", [True]), ("order_id", 43), ("order_id", 0), ("evidence_ref", ""),
                         ("status", "REJECTED"), ("status", []), ("proof_basis", "absence")]:
            changed = deepcopy(data)
            changed[key] = bad
            with self.subTest(key=key, bad=bad), self.assertRaises(risk.ContractError):
                self.apply(state, "TERMINAL", changed)
        reserved = self.reserve(risk.opening_state(opening()))
        with self.assertRaises(risk.ContractError):
            self.terminal(reserved, status="REJECTED")

    def test_duplicate_trade_is_idempotent_but_changed_ids_never_adopt(self):
        state = self.fill(self.submit(self.reserve(risk.opening_state(opening()))))
        same = self.fill(state)
        self.assertEqual(self.finance(same), self.finance(state))
        self.assertEqual(len(same.history), len(state.history) + 1)
        with self.assertRaises(risk.ContractError):
            self.fill(state, price="8", fee="0.08")
        with self.assertRaises(risk.ContractError):
            self.reserve(state, "request-A")
        with self.assertRaises(risk.ContractError):
            self.submit(state)

    def test_entry_total_and_rate_budgets_survive_terminal_rollover_and_wrapperless_state(self):
        raw = opening()
        raw["policy"].update(entry_attempt_limit=1, entry_rate_limit=1)
        state = self.terminal(self.submit(self.reserve(risk.opening_state(raw))), status="REJECTED")
        state = self.observe(state, at=state.period_end)
        state = self.apply(state, "ROLLOVER", self.rollover_data(state))
        reserved = self.reserve(state, "second-request")
        with self.assertRaisesRegex(risk.ContractError, "budgets"):
            self.submit(reserved, "second-request")
        self.assertEqual(len(state.attempts), 1)
        self.assertEqual(len(state.reservations), 1)
        raw = opening()
        raw["policy"].update(entry_rate_limit=1)
        state = self.terminal(self.submit(self.reserve(risk.opening_state(raw))), status="REJECTED")
        reserved = self.reserve(self.observe(state), "rate-second")
        with self.assertRaises(risk.ContractError):
            self.submit(reserved, "rate-second")
        later = self.observe(reserved, at=reserved.at + 61)
        submitted = self.submit(later, "rate-second")
        self.assertEqual(len(submitted.attempts), 2)
        self.assertEqual(submitted.attempts[0], state.attempts[0])

    def test_historical_order_id_owner_cannot_alias_new_request_even_with_new_trade(self):
        state = self.terminal(self.submit(self.reserve(risk.opening_state(opening()))), status="REJECTED")
        state = self.submit(self.reserve(self.observe(state), "second-request"), "second-request")
        with self.assertRaisesRegex(risk.ContractError, "different request"):
            self.fill(state, "second-request", trade=8, order=42)
        with self.assertRaisesRegex(risk.ContractError, "different request"):
            self.terminal(state, "second-request", status="REJECTED", order=42)
        filled = self.fill(state, "second-request", trade=8, order=43)
        self.assertEqual(len(filled.trades), 1)
        self.assertEqual(filled.reservations[0].order_id, 42)
        self.assertEqual(filled.reservations[1].order_id, 43)

    def test_risk_reducing_exit_uses_base_and_survives_kill_and_entry_budget(self):
        raw = opening()
        raw["positions"][0].update(quantity="3", cost_quote="30", external_locked="1")
        raw["policy"].update(entry_attempt_limit=1, entry_rate_limit=1)
        state = self.submit(self.reserve(risk.opening_state(raw), quantity="1"))
        state = self.fill(state, quantity="1", price="10", fee="0")
        state = self.observe(self.terminal(state, status="FILLED"))
        state = self.kill(state)
        reserved = self.reserve(state, "exit-A", buy=False, quantity="2")
        with self.assertRaises(risk.ContractError):
            self.reserve(reserved, "exit-B", buy=False, quantity="2")
        submitted = self.submit(reserved, "exit-A")
        self.assertEqual(submitted.killed, state.killed)
        self.assertEqual(sum(row[1] == "BUY" for row in submitted.attempts), 1)
        self.assertEqual(sum(row[1] == "SELL" for row in submitted.attempts), 1)
        with self.assertRaises(risk.ContractError):
            self.reserve(submitted, "new-entry")

    def test_partial_sale_exact_rational_cost_and_observation_cannot_rewrite_it(self):
        raw = opening()
        raw["positions"][0].update(quantity="3", cost_quote="1")
        raw["marks"]["BTC"] = "1"
        state = self.submit(self.reserve(risk.opening_state(raw), buy=False, quantity="1"))
        sold = self.fill(state, quantity="1", price="1", fee="0.01")
        self.assertEqual(sold.positions[0].cost_quote, Fraction(2, 3))
        self.assertEqual(sold.realized_quote, Fraction("0.99") - Fraction(1, 3))
        self.assertEqual(sold.cash_quote + sum((row.cost_quote for row in sold.positions), Fraction(0)) - sold.realized_quote, 1001)
        fresh = self.observe(sold)
        self.assertEqual(fresh.positions[0].cost_quote, Fraction(2, 3))
        data = self.observation(fresh)
        data["positions"][0]["cost_quote"] = "0.67"
        with self.assertRaises(risk.ContractError):
            self.apply(fresh, "OBSERVE", data)
        data = {"request_id": "request-A", "order_id": 42, "trade_id": 8, "quantity": "1", "price": "1",
                "quote_quantity": "1", "fee_quote": "0.01", "proof_basis": "exact_trade_USDT_fee", "fee_asset": "BTC"}
        with self.assertRaises(risk.ContractError):
            self.apply(fresh, "FILL", data)

    def test_reset_only_clear_kill_with_exact_head_freshness_and_no_unresolved(self):
        known_pending = self.kill(self.reserve(risk.opening_state(opening())))
        with self.assertRaises(risk.ContractError):
            self.apply(known_pending, "RESET", self.reset_data(known_pending))
        state = self.submit(self.reserve(risk.opening_state(opening())))
        state = self.apply(state, "UNKNOWN", {"request_id": "request-A", "evidence_ref": "lost"})
        with self.assertRaises(risk.ContractError):
            self.apply(state, "RESET", self.reset_data(state))
        observed = self.observe(state)
        with self.assertRaises(risk.ContractError):
            self.apply(observed, "RESET", self.reset_data(observed))
        observed = self.observe(self.terminal(observed, status="REJECTED"))
        wrong = self.reset_data(observed)
        wrong["operator_authorizer_ref"] = "different-reference"
        with self.assertRaises(risk.ContractError):
            self.apply(observed, "RESET", wrong)
        reset = self.apply(observed, "RESET", self.reset_data(observed))
        self.assertIsNone(reset.killed)
        self.assertEqual(self.finance(reset), self.finance(observed))
        self.assertEqual(reset.history[:-1], observed.history)
        self.assertEqual(reset.period_labels, observed.period_labels)
        # The literal operator reference is not an authentication capability.
        self.assertEqual(reset.policy.operator_authorizer_ref, "synthetic-policy-review-only")

    def test_rollover_carries_all_risk_and_never_reuses_opening_label(self):
        state = self.kill(self.submit(self.reserve(risk.opening_state(opening()))))
        state = self.observe(self.terminal(state, status="REJECTED"), at=state.period_end)
        rolled = self.apply(state, "ROLLOVER", self.rollover_data(state))
        self.assertEqual(self.finance(rolled), self.finance(state))
        self.assertEqual(rolled.killed, state.killed)
        self.assertEqual(rolled.history[:-1], state.history)
        rolled = self.observe(rolled, at=rolled.period_end)
        for reused in ["B", "synthetic-period-A"]:
            with self.assertRaises(risk.ContractError):
                self.apply(rolled, "ROLLOVER", self.rollover_data(rolled, reused))

    def test_stale_marks_block_entry_without_barring_fresh_base_exit(self):
        raw = opening()
        raw["positions"][0].update(quantity="2", cost_quote="20")
        state = risk.opening_state(raw)
        state = self.observe(state, at=state.at + 31, marks_at=state.at)
        with self.assertRaisesRegex(risk.ContractError, "Fresh"):
            self.reserve(state, "stale-entry")
        exit_state = self.reserve(state, "fresh-balance-exit", buy=False, quantity="1")
        self.assertEqual(exit_state.reservations[0].side, "SELL")
        with self.assertRaises(risk.ContractError):
            self.submit(replace(exit_state, head=state.head), "fresh-balance-exit")

    def test_clock_external_changes_and_future_observations_fence(self):
        state = self.kill(risk.opening_state(opening()))
        for at in [state.at - 1, state.at + 121]:
            with self.assertRaises(risk.ContractError):
                self.apply(state, "ROLLOVER", self.rollover_data(state), at=at)
        data = self.observation(state)
        data["balances_at"] = utc(state.at + 2)
        with self.assertRaises(risk.ContractError):
            self.apply(state, "OBSERVE", data)
        for mutation in ["cash", "position", "external", "locked"]:
            data = self.observation(state)
            if mutation == "cash":
                data["cash_quote"] = "1001"
            elif mutation == "position":
                data["positions"][0]["quantity"] = "1"
            elif mutation == "external":
                data["external_open_request_ids"] = ["untracked"]
            else:
                data["positions"][0]["external_locked"] = "1"
            with self.subTest(mutation=mutation), self.assertRaises(risk.ContractError):
                self.apply(state, "OBSERVE", data)

    def test_mark_loss_latches_and_reset_never_erases_breach(self):
        raw = opening()
        raw["positions"][0].update(quantity="1", cost_quote="10")
        raw["policy"]["loss_limit_quote"] = "5"
        state = self.observe(risk.opening_state(raw), marks={"BTC": "5", "ETH": "20"})
        self.assertEqual(risk.metrics(state)["loss"], 5)
        self.assertIn("loss", state.killed[1])
        with self.assertRaises(risk.ContractError):
            self.apply(state, "RESET", self.reset_data(state))
        with self.assertRaises(risk.ContractError):
            self.apply(state, "KILL", {"reason": True, "evidence_ref": "proof"})
        state = self.observe(state, at=state.period_end)
        rolled = self.apply(state, "ROLLOVER", self.rollover_data(state))
        self.assertEqual(risk.metrics(rolled)["loss"], 5)
        self.assertEqual(rolled.killed, state.killed)

    def test_policy_requires_explicit_common_transport_safety(self):
        raw = policy()
        raw.pop("transport_rate_limit", None)
        raw.pop("transport_rate_window_seconds", None)
        with self.assertRaises(risk.ContractError):
            risk.parse_policy(raw)

    def test_reducing_exit_obeys_common_rate_without_spending_entry_budget(self):
        raw = opening()
        raw["policy"].update(transport_rate_limit=1, transport_rate_window_seconds=60)
        raw["positions"][0].update(quantity="2", cost_quote="20")
        state = self.submit(self.reserve(risk.opening_state(raw), quantity="1"))
        state = self.kill(self.observe(self.terminal(state, status="REJECTED")))
        reserved = self.reserve(state, "rate-exit", buy=False, quantity="1")
        with self.assertRaisesRegex(risk.ContractError, "transport"):
            self.submit(reserved, "rate-exit")
        later = self.observe(reserved, at=reserved.at + 61)
        submitted = self.submit(later, "rate-exit")
        self.assertEqual(submitted.killed, state.killed)
        self.assertEqual(sum(row[1] == "BUY" for row in submitted.attempts), 1)
        self.assertEqual(sum(row[1] == "SELL" for row in submitted.attempts), 1)
        self.assertEqual(submitted.attempts[0], state.attempts[0])

    def test_rollover_requires_fresh_complete_reconciliation(self):
        state = risk.opening_state(opening())
        data = self.rollover_data(state)
        with self.assertRaises(risk.ContractError):
            self.apply(state, "ROLLOVER", data, at=state.period_end)
        submitted = self.submit(self.reserve(state))
        with self.assertRaisesRegex(risk.ContractError, "Fresh"):
            self.apply(submitted, "ROLLOVER", data, at=submitted.period_end)

    def test_balance_highwater_survives_terminal_invalidation(self):
        opening_state = risk.opening_state(opening())
        state = self.terminal(self.submit(self.reserve(opening_state)), status="REJECTED")
        data = self.observation(state)
        data["balances_at"] = utc(opening_state.at)
        with self.assertRaisesRegex(risk.ContractError, "timestamp"):
            self.apply(state, "OBSERVE", data)
        fresh = self.observe(state)
        self.assertEqual(fresh.reservations, state.reservations)
        self.assertEqual(fresh.attempts, state.attempts)

    def test_fee_envelope_cannot_admit_cash_exit_that_needs_borrow_after_fill(self):
        raw = opening()
        raw["cash_quote"] = "0"
        raw["positions"][0].update(quantity="1", cost_quote="1")
        raw["marks"]["BTC"] = "1"
        raw["policy"]["max_quote_fee_rate"] = "2"
        try:
            state = risk.opening_state(raw)
        except risk.ContractError as exc:
            self.assertIn("fee", str(exc).lower())
            return
        submitted = self.submit(self.reserve(state, buy=False, quantity="1"))
        with self.assertRaises(risk.ContractError):
            self.fill(submitted, quantity="1", price="1", fee="2")
        self.fail("Unsupported fee envelope admitted exit, then rejected only after execution")

    def test_resealed_state_requires_full_financial_and_policy_validation(self):
        state = risk.opening_state(opening())
        bad_position = replace(state.positions[0], quantity=Fraction(-1))
        bad_policy = replace(state.policy, values=tuple((name, Fraction(-1) if name == "gross_limit_quote" else value)
                                                       for name, value in state.policy.values))
        for malformed in [replace(state, positions=(bad_position,) + state.positions[1:]),
                          replace(state, policy=bad_policy)]:
            resealed = risk._seal(malformed)
            with self.subTest(malformed=type(malformed)), self.assertRaises(risk.ContractError):
                self.apply(resealed, "KILL", {"reason": "review", "evidence_ref": "proof"})
            with self.assertRaises(risk.ContractError):
                risk.metrics(resealed)

    def test_interval_time_and_original_automatic_kill_evidence_survive_reset(self):
        raw = opening()
        raw["positions"][0].update(quantity="1", cost_quote="10")
        raw["marks"]["BTC"] = "5"
        raw["policy"]["loss_limit_quote"] = "5"
        state = risk.opening_state(raw)
        self.assertEqual(state.killed[0], "opening")
        state = self.observe(state, marks={"BTC": "10", "ETH": "20"})
        reset = self.apply(state, "RESET", self.reset_data(state))
        self.assertIsNone(reset.killed)
        self.assertEqual(json.loads(reset.opening_payload)["marks"]["BTC"], "5")
        self.assertEqual(risk.opening_state(json.loads(reset.opening_payload)).killed[1], "limit:loss")
        with self.assertRaises(risk.ContractError):
            self.apply(reset, "ROLLOVER", self.rollover_data(reset))
        expired = self.observe(reset, at=reset.period_end)
        with self.assertRaises(risk.ContractError):
            self.reserve(expired, "expired-entry", quantity="1")
        exit_state = self.reserve(expired, "expired-risk-reduction", buy=False, quantity="1")
        self.assertEqual(exit_state.reservations[0].side, "SELL")
        for change in [{"starts_at": utc(expired.period_end + 1)}, {"ends_at": utc(expired.period_end)}]:
            data = self.rollover_data(expired)
            data.update(change)
            with self.assertRaises(risk.ContractError):
                self.apply(expired, "ROLLOVER", data)

    def test_expired_never_sent_reservation_carries_without_releasing_bound(self):
        state = self.observe(self.reserve(risk.opening_state(opening())), at=risk.opening_state(opening()).period_end)
        with self.assertRaises(risk.ContractError):
            self.submit(state)
        with self.assertRaises(risk.ContractError):
            self.terminal(state, status="REJECTED")
        rolled = self.apply(state, "ROLLOVER", self.rollover_data(state))
        self.assertEqual(self.finance(rolled), self.finance(state))
        self.assertEqual(rolled.reservations[0].status, "reserved")
        self.assertEqual(risk.metrics(rolled)["cash_bound"], Fraction("20.2"))
        self.assertEqual(rolled.history[:-1], state.history)
        submitted = self.submit(rolled)
        self.assertEqual(len(submitted.attempts), 1)
        self.assertEqual(submitted.reservations[0].remaining, 2)

    def test_partial_rollover_carry_requires_joined_observation_unknown_stays_fenced(self):
        state = self.fill(self.submit(self.reserve(risk.opening_state(opening()))))
        with self.assertRaises(risk.ContractError):
            self.apply(state, "ROLLOVER", self.rollover_data(state), at=state.period_end)
        state = self.observe(state, at=state.period_end)
        missing = self.observation(state)
        missing["external_open_request_ids"] = []
        with self.assertRaises(risk.ContractError):
            self.apply(state, "OBSERVE", missing)
        rolled = self.apply(state, "ROLLOVER", self.rollover_data(state))
        self.assertEqual(self.finance(rolled), self.finance(state))
        self.assertEqual(risk.metrics(rolled)["cash_bound"], Fraction("10.1"))
        self.assertEqual(rolled.reservations[0].trade_ids, (7,))
        self.assertEqual(rolled.history[:-1], state.history)
        unknown = self.apply(rolled, "UNKNOWN", {"request_id": "request-A", "evidence_ref": "lost-later-query"})
        unknown = self.observe(unknown, at=unknown.period_end)
        with self.assertRaises(risk.ContractError):
            self.apply(unknown, "ROLLOVER", self.rollover_data(unknown))


    def test_public_boundaries_reject_original_head_numeric_type_erasure(self):
        raw = opening()
        raw["positions"][0].update(quantity="1", cost_quote="1")
        raw["marks"]["BTC"] = "0.99"
        state = risk.opening_state(raw)
        proof = risk.metrics(state)
        self.assertEqual(proof["loss"], Fraction(1, 100))
        self.assertIs(type(proof["loss"]), Fraction)
        mutations = {
            "realized_float": replace(state, realized_quote=0.0),
            "realized_bool": replace(state, realized_quote=False),
            "cash_float": replace(state, cash_quote=1000.0),
            "identity_uid_float": replace(state, identity=replace(state.identity, account_uid=101.0)),
            "balance_time_float": replace(state, balance_at=float(state.balance_at)),
            "balance_watermark_float": replace(state, balance_watermark=float(state.balance_watermark)),
            "position_quantity_bool": replace(state, positions=(replace(state.positions[0], quantity=True),) + state.positions[1:]),
            "position_cost_float": replace(state, positions=(replace(state.positions[0], cost_quote=1.0),) + state.positions[1:]),
            "position_locked_bool": replace(state, positions=(replace(state.positions[0], external_locked=False),) + state.positions[1:]),
            "mark_integer": replace(state, marks=(state.marks[0], ("ETH", 20))),
            "policy_integer_float": replace(state, policy=replace(state.policy, values=tuple(
                (key, 2.0 if key == "position_limit" else value) for key, value in state.policy.values))),
        }
        pending = self.reserve(risk.opening_state(opening()))
        submitted = self.submit(pending)
        mutations.update({
            "reservation_quantity_int": replace(pending, reservations=(replace(pending.reservations[0], quantity=2),)),
            "reservation_remaining_float": replace(pending, reservations=(replace(pending.reservations[0], remaining=2.0),)),
            "reservation_filled_bool": replace(pending, reservations=(replace(pending.reservations[0], filled=False),)),
            "attempt_time_float": replace(submitted, attempts=((submitted.attempts[0][0], "BUY", float(submitted.attempts[0][2])),)),
        })
        for label, malformed in mutations.items():
            self.assertEqual(malformed.head, state.head if label not in {
                "reservation_quantity_int", "reservation_remaining_float", "reservation_filled_bool", "attempt_time_float"
            } else (submitted.head if label == "attempt_time_float" else pending.head))
            for boundary in ("metrics", "apply_event"):
                with self.subTest(mutation=label, boundary=boundary), self.assertRaises(risk.ContractError):
                    if boundary == "metrics":
                        risk.metrics(malformed)
                    else:
                        self.kill(malformed)
        self.assertEqual(risk.metrics(state), proof)

    def test_public_boundaries_reject_resealed_malformed_nested_state(self):
        state = risk.opening_state(opening())
        malformed = [
            replace(state, realized_quote=0.0),
            replace(state, positions=(replace(state.positions[0], quantity=False),) + state.positions[1:]),
            replace(state, policy=replace(state.policy, values=tuple(
                (key, False if key == "future_skew_seconds" else value) for key, value in state.policy.values))),
            replace(state, identity=replace(state.identity, account_uid=101.0)),
        ]
        for altered in malformed:
            resealed = risk._seal(altered)
            for boundary in ("metrics", "apply_event"):
                with self.subTest(altered=repr(altered.identity), boundary=boundary), self.assertRaises(risk.ContractError):
                    risk.metrics(resealed) if boundary == "metrics" else self.kill(resealed)
        # Generated exact rational values retain their type after full replay.
        raw = opening()
        raw["positions"][0].update(quantity="3", cost_quote="1")
        raw["marks"]["BTC"] = "1"
        partial = self.fill(self.submit(self.reserve(risk.opening_state(raw), buy=False, quantity="1")),
                            quantity="1", price="1", fee="0.01")
        self.assertEqual(partial.positions[0].cost_quote, Fraction(2, 3))
        for key in ("gross", "net", "loss", "cash_bound"):
            self.assertIs(type(risk.metrics(partial)[key]), Fraction)
        self.assertEqual(self.kill(partial).positions, partial.positions)

    def test_state_serialization_rejects_nonfinite_and_normalizes_unsupported_values(self):
        state = risk.opening_state(opening())
        for value in (float("nan"), float("inf"), -float("inf"), complex(1), b"unsupported"):
            with self.subTest(value=repr(value)), self.assertRaises(risk.ContractError):
                risk._seal(replace(state, realized_quote=value))
            for boundary in ("metrics", "apply_event"):
                with self.subTest(value=repr(value), boundary=boundary), self.assertRaises(risk.ContractError):
                    altered = replace(state, realized_quote=value)
                    risk.metrics(altered) if boundary == "metrics" else self.kill(altered)


    def test_public_boundaries_reject_same_digest_numeric_subclasses(self):
        class UnownedFraction(Fraction):
            pass

        class UnownedInt(int):
            pass

        state = risk.opening_state(opening())
        mutations = {
            "realized": replace(state, realized_quote=UnownedFraction(0)),
            "quantity": replace(state, positions=(replace(state.positions[0], quantity=UnownedFraction(0)),) + state.positions[1:]),
            "account": replace(state, identity=replace(state.identity, account_uid=UnownedInt(101))),
            "policy": replace(state, policy=replace(state.policy, values=tuple(
                (key, UnownedInt(2) if key == "position_limit" else value) for key, value in state.policy.values))),
        }
        for label, malformed in mutations.items():
            self.assertEqual(risk._digest(malformed), state.head)
            self.assertEqual(malformed, state)
            for boundary in ("metrics", "apply_event"):
                with self.subTest(mutation=label, boundary=boundary), self.assertRaises(risk.ContractError):
                    risk.metrics(malformed) if boundary == "metrics" else self.kill(malformed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
