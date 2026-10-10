"""Bounded synthetic financial and framing equivalence tests for inert batch replay."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from fractions import Fraction
import json
import unittest
from unittest.mock import patch

from app.integrations.exchanges.binance.orders import spot_account_risk_contract as risk
from app.integrations.exchanges.binance.orders import spot_account_risk_store as store
import test_spot_account_risk_contract as fixture

COUNTS = []
CORPUS = []


def corpus():
    cases = []
    def fresh(raw=None):
        helper = fixture.ContractTests(methodName="runTest")
        helper.setUp()
        basis = deepcopy(fixture.opening() if raw is None else raw)
        return helper, basis, risk.opening_state(basis)
    h, basis, state = fresh()
    cases.append(("empty", basis, state))
    state = h.reserve(state)
    state = h.submit(state)
    state = h.fill(state)
    state = h.apply(state, "UNKNOWN", {"request_id": "request-A", "evidence_ref": "synthetic-lost"})
    state = h.observe(state)
    state = h.terminal(state)
    state = h.observe(state)
    state = h.apply(state, "RESET", h.reset_data(state))
    cases.append(("partial-unknown-terminal-reset", basis, state))
    h, basis, state = fresh()
    state = h.submit(h.reserve(state))
    state = h.fill(state)
    state = h.fill(state)
    state = h.fill(state, quantity="1", price="10", fee="0.1", trade=8)
    state = h.terminal(state, status="FILLED")
    state = h.observe(state)
    state = h.kill(state)
    state = h.reserve(state, "exit-A", buy=False, quantity="1")
    state = h.submit(state, "exit-A")
    state = h.fill(state, "exit-A", quantity="0.5", price="10", fee="0.05", trade=9, order=43)
    state = h.terminal(state, "exit-A", order=43)
    state = h.observe(state)
    state = h.apply(state, "RESET", h.reset_data(state))
    state = h.observe(state, at=state.period_end)
    state = h.apply(state, "ROLLOVER", h.rollover_data(state))
    cases.append(("buy-duplicate-venue-fill-fee-partial-exit-reset-rollover", basis, state))
    raw = fixture.opening()
    raw["positions"][0].update(quantity="3", cost_quote="1")
    raw["marks"]["BTC"] = "1"
    h, basis, state = fresh(raw)
    state = h.submit(h.reserve(state, buy=False, quantity="1"))
    state = h.fill(state, quantity="1", price="1", fee="0.01")
    state = h.terminal(state, status="FILLED")
    state = h.observe(state)
    cases.append(("exact-rational-partial-cost-sale", basis, state))
    h, basis, state = fresh()
    state = h.reserve(state)
    state = h.observe(state, at=state.period_end)
    state = h.apply(state, "ROLLOVER", h.rollover_data(state))
    state = h.submit(state)
    state = h.fill(state)
    cases.append(("expired-unsent-reservation-carry", basis, state))
    raw = fixture.opening()
    raw["positions"][0].update(quantity="1", cost_quote="10")
    raw["marks"]["BTC"] = "5"
    raw["policy"]["loss_limit_quote"] = "5"
    h, basis, state = fresh(raw)
    state = h.observe(state, marks={"BTC": "10", "ETH": "20"})
    state = h.apply(state, "RESET", h.reset_data(state))
    state = h.observe(state, at=state.period_end)
    state = h.apply(state, "ROLLOVER", h.rollover_data(state))
    cases.append(("original-automatic-kill-reset-history", basis, state))
    return cases


def ledger(basis, events, heads, final):
    identity = basis["identity"]
    proof = {"version": 1, "basis": "unverified_supplied_claim", "identity": deepcopy(identity),
             "reference": "synthetic-batch-equivalence-only", "record_digest": "1" * 64,
             "request_digest": "2" * 64, "evidence_digest": "3" * 64}
    store_id = "30000000-0000-4000-8000-000000000001"
    chain = store._sha(store._encode({"risk_store_id": store_id, "opening": basis, "provenance": proof}))
    entries = []
    for revision, (event, head) in enumerate(zip(events, heads), 2):
        raw_event = store._event_raw(event)
        candidate = {"revision": revision, "previous_chain_head": chain, "event": raw_event,
                     "provenance": proof, "state_head": head}
        next_chain = store._sha(store._encode(candidate))
        entries.append({"event": raw_event, "provenance": deepcopy(proof), "previous_chain_head": chain,
                        "chain_head": next_chain, "state_head": head})
        chain = next_chain
    return {"version": 1, "risk_store_id": store_id, "identity": deepcopy(identity), "opening": deepcopy(basis),
            "opening_provenance": proof, "entries": entries,
            "head": {"revision": len(events) + 1, "chain_head": chain, "state_head": final.head},
            "projection": store._projection(final)}


class BatchTests(unittest.TestCase):
    def assert_exact(self, left, right):
        self.assertTrue(risk._same_contract_value(left, right))
        self.assertEqual(store._encode(store._projection(left)), store._encode(store._projection(right)))

    def test_small_financial_corpus_has_exact_history_heads_projection_and_raw_commitments(self):
        for label, basis, final in corpus():
            with self.subTest(corpus=label):
                state = risk.opening_state(basis)
                heads = []
                for event in final.history:
                    state = risk.apply_event(state, event)
                    heads.append(state.head)
                result = risk.replay_events(basis, final.history)
                self.assert_exact(state, final)
                self.assert_exact(result.state, final)
                self.assertEqual(result.opening_head, risk.opening_state(basis).head)
                self.assertEqual(result.revision_state_heads, tuple(heads))
                self.assertEqual(result.state.history, final.history)
                self.assertEqual(risk.metrics(result.state), risk.metrics(final))
                old_doc = ledger(basis, final.history, heads, final)
                batch_doc = ledger(basis, result.state.history, result.revision_state_heads, result.state)
                self.assertEqual(store._encode(old_doc), store._encode(batch_doc))
                replay_doc, replay_state = store._replay(store._encode(old_doc), basis["identity"])
                self.assertEqual(store._encode(replay_doc), store._encode(batch_doc))
                self.assert_exact(replay_state, result.state)
                CORPUS.append({"label": label, "events": len(final.history), "opening_head": result.opening_head,
                               "revision_heads": heads, "final_head": final.head,
                               "ledger_raw_sha256": store._sha(store._encode(old_doc)),
                               "projection_sha256": store._sha(store._encode(store._projection(final)))})
        rational = next(state for label, _, state in corpus() if label == "exact-rational-partial-cost-sale")
        self.assertEqual(rational.positions[0].cost_quote, Fraction(2, 3))
        self.assertEqual(rational.realized_quote, Fraction("0.99") - Fraction(1, 3))
        self.assertEqual(rational.cash_quote + sum((p.cost_quote for p in rational.positions), Fraction(0)) - rational.realized_quote, 1001)
        pending = next(state for label, _, state in corpus() if label == "expired-unsent-reservation-carry")
        self.assertEqual(pending.reservations[0].remaining, Fraction(1))
        self.assertEqual(pending.period_labels, ("synthetic-period-A", "B"))
        original = next(state for label, _, state in corpus() if label == "original-automatic-kill-reset-history")
        self.assertEqual(json.loads(original.opening_payload)["marks"]["BTC"], "5")
        self.assertIsNone(original.killed)

    def test_changed_earlier_financial_proof_and_stale_later_head_refuse(self):
        label, basis, final = corpus()[1]
        events = list(final.history)
        data = json.loads(events[2].payload)
        for key, value in (("fee_quote", "0.1"), ("quantity", "2"), ("proof_basis", "unsupported")):
            changed = deepcopy(data)
            changed[key] = value
            bad = replace(events[2], payload=risk._json(changed))
            with self.subTest(field=key), self.assertRaises(risk.ContractError):
                risk.replay_events(basis, tuple(events[:2] + [bad] + events[3:]))
        with self.assertRaises(risk.ContractError):
            risk.replay_events(basis, tuple(events[1:]))
        with self.assertRaises(risk.ContractError):
            risk.replay_events(basis, tuple(events[:2] + [replace(events[2], expected_head="0" * 64)] + events[3:]))
        with self.assertRaises(risk.ContractError):
            risk.replay_events(basis, tuple(events[:2] + [events[3], events[2]] + events[4:]))

    def test_duplicate_revision_ids_refuse_exact_and_changed_duplicates(self):
        _, basis, final = corpus()[1]
        first = final.history[0]
        with self.assertRaisesRegex(risk.ContractError, "Duplicate batch"):
            risk.replay_events(basis, (first, first))
        with self.assertRaisesRegex(risk.ContractError, "Duplicate batch"):
            risk.replay_events(basis, (first, replace(final.history[1], event_id=first.event_id)))

    def test_original_public_duplicate_identity_and_full_state_validation_are_unchanged(self):
        _, _, final = corpus()[1]
        self.assertIs(risk.apply_event(final, final.history[-1]), final)
        malformed = replace(final, realized_quote=float(final.realized_quote))
        malformed = replace(malformed, head=risk._digest(malformed))
        with self.assertRaises(risk.ContractError):
            risk.metrics(malformed)
        with self.assertRaises(risk.ContractError):
            risk.apply_event(malformed, final.history[-1])

    def test_caller_state_and_missing_or_unsupported_opening_never_become_trust_tokens(self):
        _, basis, final = corpus()[1]
        for raw in (final, None, [], {**basis, "unknown": "field"}):
            with self.subTest(raw_type=type(raw).__name__), self.assertRaises(risk.ContractError):
                risk.replay_events(raw, final.history)
        for path, value in (("account_uid", True), ("version", 1.0), ("exchange", "other")):
            changed = deepcopy(basis)
            changed["identity"][path] = value
            with self.subTest(field=path), self.assertRaises(risk.ContractError):
                risk.replay_events(changed, ())
        for value in (False, 100.0, "NaN", "-0", "0.00"):
            changed = deepcopy(basis)
            changed["cash_quote"] = value
            with self.subTest(value=value), self.assertRaises(risk.ContractError):
                risk.replay_events(changed, ())

    def test_event_tuple_and_exact_scalar_types_refuse_numeric_and_string_aliases(self):
        class Text(str):
            pass
        class Number(int):
            pass
        class Sequence(tuple):
            pass
        class EventAlias(risk.Event):
            pass
        _, basis, final = corpus()[1]
        first = final.history[0]
        for events in ([first], Sequence((first,)), None):
            with self.subTest(sequence=type(events).__name__), self.assertRaises(risk.ContractError):
                risk.replay_events(basis, events)
        changes = [{"at": float(first.at)}, {"at": Number(first.at)}, {"at": True},
                   {"event_id": Text(first.event_id)}, {"expected_head": Text(first.expected_head)},
                   {"kind": Text(first.kind)}, {"payload": Text(first.payload)}]
        for fields in changes:
            with self.subTest(fields=tuple(fields)), self.assertRaises(risk.ContractError):
                risk.replay_events(basis, (replace(first, **fields),))
        with self.assertRaises(risk.ContractError):
            risk.replay_events(basis, (EventAlias(first.event_id, first.expected_head, first.at, first.kind, first.payload),))

    def test_noncanonical_duplicate_nonfinite_float_and_unicode_event_payloads_refuse(self):
        _, basis, final = corpus()[1]
        first = final.history[0]
        bad_payloads = [" " + first.payload, '{}', '[]', '{"x":1,"x":1}', '{"x":NaN}', '{"x":1.0}', "\ud800"]
        for payload in bad_payloads:
            with self.subTest(payload=repr(payload)), self.assertRaises(risk.ContractError):
                risk.replay_events(basis, (replace(first, payload=payload),))
        with self.assertRaises(risk.ContractError):
            risk.replay_events(basis, (replace(first, at=2**63 - 1),))

    def test_returned_history_is_detached_and_no_intermediate_state_callback_is_available(self):
        _, basis, final = corpus()[1]
        event_copies = tuple(replace(event) for event in final.history)
        result = risk.replay_events(basis, event_copies)
        for original, retained in zip(event_copies, result.state.history):
            self.assertIsNot(original, retained)
        basis["identity"]["account_uid"] = 999
        object.__setattr__(event_copies[0], "payload", '{}')
        self.assertEqual(result.state.identity.account_uid, 101)
        self.assertNotEqual(result.state.history[0].payload, '{}')
        self.assertEqual(risk._validate_state(result.state).head, result.state.head)
        self.assertIs(type(result.revision_state_heads), tuple)
        with self.assertRaises(FrozenInstanceError):
            result.opening_head = "0" * 64

    def test_original_outer_ledger_provenance_and_all_commitments_remain_required(self):
        _, basis, final = corpus()[1]
        result = risk.replay_events(basis, final.history)
        doc = ledger(basis, result.state.history, result.revision_state_heads, result.state)
        changes = []
        changed = deepcopy(doc)
        changed["entries"][0]["provenance"]["record_digest"] = "4" * 64
        changes.append(changed)
        changed = deepcopy(doc)
        changed["entries"][0]["state_head"] = "0" * 64
        changes.append(changed)
        changed = deepcopy(doc)
        changed["entries"][-1]["chain_head"] = "0" * 64
        changes.append(changed)
        changed = deepcopy(doc)
        changed["head"]["state_head"] = "0" * 64
        changes.append(changed)
        changed = deepcopy(doc)
        changed["projection"]["cash_quote"] = [0, 1]
        changes.append(changed)
        changed = deepcopy(doc)
        changed["entries"][1]["event"]["event_id"] = changed["entries"][0]["event"]["event_id"]
        changes.append(changed)
        for index, changed in enumerate(changes):
            with self.subTest(index=index), self.assertRaises((store.RiskStoreError, risk.ContractError)):
                store._replay(store._encode(changed), basis["identity"])

    def test_batch_has_no_public_apply_calls_and_retains_final_full_replay_counts(self):
        for count in (0, 1, 2, 4, 8, 16):
            basis = fixture.opening()
            state = risk.opening_state(basis)
            events = []
            for index in range(count):
                event = risk.parse_event({"event_id": f"count-{index:02d}", "expected_head": state.head,
                                          "at": fixture.utc(state.at + 1), "kind": "KILL",
                                          "data": {"reason": "synthetic-count", "evidence_ref": "synthetic-count-only"}})
                state = risk.apply_event(state, event)
                events.append(event)
            counts = {"events": count, "validate": 0, "reduce": 0, "digest": 0, "digest_history_slots": 0, "public_apply": 0}
            originals = {name: getattr(risk, name) for name in ("_validate_state", "_reduce_event", "_digest", "apply_event")}
            def counted_validate(value):
                counts["validate"] += 1
                return originals["_validate_state"](value)
            def counted_reduce(value, event):
                counts["reduce"] += 1
                return originals["_reduce_event"](value, event)
            def counted_digest(value):
                counts["digest"] += 1
                counts["digest_history_slots"] += len(value.history)
                return originals["_digest"](value)
            def forbidden_public_apply(*args):
                counts["public_apply"] += 1
                raise AssertionError("Batch must not repeatedly call public apply_event")
            risk._validate_state, risk._reduce_event, risk._digest, risk.apply_event = counted_validate, counted_reduce, counted_digest, forbidden_public_apply
            try:
                result = risk.replay_events(basis, tuple(events))
            finally:
                for name, function in originals.items():
                    setattr(risk, name, function)
            self.assert_exact(result.state, state)
            self.assertEqual(counts["validate"], 2)
            self.assertEqual(counts["reduce"], 2 * count)
            self.assertEqual(counts["digest"], 4 * count + 5)
            self.assertEqual(counts["digest_history_slots"], 2 * count * count + count)
            self.assertEqual(counts["public_apply"], 0)
            COUNTS.append(counts)
    def test_deep_historical_event_nesting_is_owned_contract_error_without_swallowing_interrupts(self):
        basis = fixture.opening()
        opening = risk.opening_state(basis)
        helper = fixture.ContractTests(methodName="runTest")
        helper.setUp()
        killed = helper.kill(opening)
        first = killed.history[0]
        deep_payload = '{"reason":' + '[' * 20_000 + '0' + ']' * 20_000 + ',"evidence_ref":"synthetic-deep-history"}'
        nested = risk.Event("deep-history", killed.head, killed.at + 1, "KILL", deep_payload)
        self.assertGreater(len(deep_payload.encode("utf-8")), 40_000)
        with self.assertRaises(risk.ContractError) as raised:
            risk.replay_events(basis, (first, nested))
        if str(raised.exception) == "Invalid immutable batch event framing":
            self.assertIs(type(raised.exception.__cause__), RecursionError)
        else:
            # A codec accepting this depth still changes the original unsorted keys.
            self.assertEqual(str(raised.exception), "Noncanonical exact immutable batch Event")
            self.assertIsNone(raised.exception.__cause__)
        original_decode = risk.decode_contract
        try:
            for interruption in (KeyboardInterrupt, SystemExit):
                def interrupt(raw, exception=interruption):
                    raise exception("synthetic-boundary-interruption")
                risk.decode_contract = interrupt
                with self.subTest(interruption=interruption.__name__), self.assertRaises(interruption):
                    risk._detached_batch_event(first)
        finally:
            risk.decode_contract = original_decode
    def test_batch_decoder_faults_preserve_exact_recursion_cause_and_interruptions(self):
        basis = fixture.opening()
        helper = fixture.ContractTests(methodName="runTest")
        helper.setUp()
        first = helper.kill(risk.opening_state(basis)).history[0]
        original_decode = risk.decode_contract
        payload = first.payload.encode("utf-8")
        for primary in (RecursionError("synthetic-decoder-depth"), KeyboardInterrupt("synthetic-decoder-interrupt"),
                        SystemExit("synthetic-decoder-exit")):
            with self.subTest(primary=type(primary).__name__):
                def decode(raw, fault=primary):
                    if raw == payload:
                        raise fault
                    return original_decode(raw)

                with patch.object(risk, "decode_contract", side_effect=decode):
                    if isinstance(primary, RecursionError):
                        with self.assertRaisesRegex(risk.ContractError, "^Invalid immutable batch event framing$") as raised:
                            risk.replay_events(basis, (first,))
                        self.assertIs(raised.exception.__cause__, primary)
                    else:
                        with self.assertRaises(type(primary)) as raised:
                            risk.replay_events(basis, (first,))
                        self.assertIs(raised.exception, primary)
        self.assert_exact(risk.replay_events(basis, (first,)).state, risk.apply_event(risk.opening_state(basis), first))

    def test_batch_encoder_faults_preserve_exact_recursion_cause_and_interruptions(self):
        basis = fixture.opening()
        helper = fixture.ContractTests(methodName="runTest")
        helper.setUp()
        first = helper.kill(risk.opening_state(basis)).history[0]
        data = json.loads(first.payload)
        original_dumps = risk.json.dumps
        for primary in (RecursionError("synthetic-encoder-depth"), KeyboardInterrupt("synthetic-encoder-interrupt"),
                        SystemExit("synthetic-encoder-exit")):
            with self.subTest(primary=type(primary).__name__):
                def encode(value, *args, fault=primary, **kwargs):
                    if type(value) is dict and set(value) == set(data) and value == data:
                        raise fault
                    return original_dumps(value, *args, **kwargs)

                with patch.object(risk.json, "dumps", side_effect=encode):
                    if isinstance(primary, RecursionError):
                        with self.assertRaisesRegex(risk.ContractError, "^Invalid immutable batch event framing$") as raised:
                            risk.replay_events(basis, (first,))
                        self.assertIs(raised.exception.__cause__, primary)
                    else:
                        with self.assertRaises(type(primary)) as raised:
                            risk.replay_events(basis, (first,))
                        self.assertIs(raised.exception, primary)
        self.assert_exact(risk.replay_events(basis, (first,)).state, risk.apply_event(risk.opening_state(basis), first))

    def test_iteratively_decoded_canonical_nested_reason_retains_semantic_reference_error(self):
        basis = fixture.opening()
        helper = fixture.ContractTests(methodName="runTest")
        helper.setUp()
        killed = helper.kill(risk.opening_state(basis))
        first = killed.history[0]
        reason = 0
        for _ in range(20_000):
            reason = [reason]
        data = {"reason": reason, "evidence_ref": "synthetic-deep-history"}
        payload = '{"evidence_ref":"synthetic-deep-history","reason":' + '[' * 20_000 + '0' + ']' * 20_000 + '}'
        nested = risk.Event("canonical-deep-history", killed.head, killed.at + 1, "KILL", payload)
        self.assertGreater(len(payload.encode("utf-8")), 40_000)
        original_decode, original_dumps = risk.decode_contract, risk.json.dumps

        def decode(raw):
            # Model an iterative JSON decoder only for these exact original bytes.
            if raw == payload.encode("utf-8"):
                return data
            return original_decode(raw)

        def encode(value, *args, **kwargs):
            # Match that decoder's canonical encoder, leaving the validator real.
            if value is data:
                return payload
            return original_dumps(value, *args, **kwargs)

        with patch.object(risk, "decode_contract", side_effect=decode), patch.object(risk.json, "dumps", side_effect=encode):
            with self.assertRaisesRegex(risk.ContractError, "^Invalid contract reference$") as raised:
                risk.replay_events(basis, (first, nested))
        self.assertIsNone(raised.exception.__cause__)
        self.assert_exact(risk.replay_events(basis, (first,)).state, killed)
