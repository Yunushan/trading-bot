"""Conditional synthetic storage controls; no limits/claims are product defaults."""

from copy import copy, deepcopy
from dataclasses import replace
from fractions import Fraction
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from app.integrations.exchanges.binance.orders import spot_account_risk_contract as risk
from app.integrations.exchanges.binance.orders import spot_account_risk_store as store
from test_spot_account_risk_contract import opening, token, utc


class FakeProtectedPort:
    """Independently persists only inside this synthetic fixture."""

    def __init__(self):
        self.values = {}
        self.reads = self.writes = 0
        self.write_hook = self.read_hook = None

    def read(self, slot):
        self.reads += 1
        value = self.values.get(slot)
        return value if self.read_hook is None else self.read_hook(slot, value)

    def write(self, slot, value):
        self.writes += 1
        if self.write_hook:
            self.write_hook(slot, value)
        else:
            self.values[slot] = value


class RiskStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="synthetic-risk-storage-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "risk.json"
        self.port = FakeProtectedPort()
        self.live = True
        self.deadline = time.monotonic() + 60.0
        self.raw_opening = opening()
        self.identity = self.raw_opening["identity"]
        self.serial = 0

    def guard(self):
        hook = getattr(self, "guard_hook", None)
        if hook is not None:
            hook()
        if not self.live:
            raise store.RiskStoreError("Synthetic lifetime revoked")

    def scope(self, path=None):
        return store._storage_scope(path or self.path, protected=self.port, guard=self.guard, deadline=self.deadline)

    def proof(self, reference="synthetic-claim"):
        return {
            "version": 1,
            "basis": "unverified_supplied_claim",
            "identity": deepcopy(self.identity),
            "reference": reference,
            "record_digest": "1" * 64,
            "request_digest": "2" * 64,
            "evidence_digest": "3" * 64,
        }

    def boot(self):
        return store.bootstrap_risk_store(self.path, self.raw_opening, self.proof(), operation_id="synthetic-bootstrap")

    def event(self, receipt, kind, data, *, at=None, event_id=None):
        self.serial += 1
        return risk.parse_event(
            {
                "event_id": event_id or f"synthetic-event-{self.serial}",
                "expected_head": receipt.state.head,
                "at": utc(receipt.state.at + 1 if at is None else at),
                "kind": kind,
                "data": data,
            }
        )

    def append(self, receipt, kind="KILL", data=None, **kwargs):
        event = self.event(
            receipt, kind, data or {"reason": "synthetic-review", "evidence_ref": "synthetic-only"}, **kwargs
        )
        return store.append_risk_event(self.path, receipt, event, self.proof(event.event_id)), event

    def reserve(self, receipt):
        return self.append(
            receipt,
            "RESERVE_ENTRY",
            {
                "request_id": "request-A",
                "asset": "BTC",
                "quantity": "2",
                "order_type": "LIMIT_FOK",
                "limit_price": "10",
            },
        )[0]

    def raw_anchor(self):
        return next(iter(self.port.values.values()))

    def set_anchor(self, value):
        self.port.values[next(iter(self.port.values))] = store._encode(value)

    def pending_failure(self, receipt=None, *, after_source=False):
        real = store._write_exact

        def fail(path, raw, scope_path, *, exclusive, **kwargs):
            if not exclusive:
                if after_source:
                    real(path, raw, scope_path, exclusive=exclusive, **kwargs)
                raise OSError("synthetic source publication interruption")
            return real(path, raw, scope_path, exclusive=exclusive, **kwargs)

        with patch.object(store, "_write_exact", side_effect=fail), self.assertRaises(store.RiskStoreError):
            self.boot() if receipt is None else self.append(receipt, event_id="prepared-event")
        return self.raw_anchor()

    def journal(self):
        return store._journal(self.path, store._decode(self.raw_anchor())["operation_digest"])

    def assert_no_temps(self):
        self.assertFalse(any(entry.name.startswith(self.path.name + ".write-") for entry in self.path.parent.iterdir()))

    def test_default_missing_port_or_scope_fences_before_file_mutation(self):
        with self.assertRaises(store.RiskStoreError):
            self.boot()
        self.assertFalse(self.path.exists())
        self.assertEqual(self.port.reads, 0)
        with self.assertRaises(store.RiskStoreError):
            with store._storage_scope(self.path, protected=None, guard=self.guard, deadline=self.deadline):
                pass
        self.assertFalse(self.path.exists())

    def test_actual_fsync_canonical_publication_full_reopen_and_isolation(self):
        with self.scope(), patch.object(store.os, "fsync", wraps=os.fsync) as fsync:
            original = self.boot()
            changed, event = self.append(original)
            self.assertGreaterEqual(fsync.call_count, 4)
            self.assertEqual(changed.raw, self.path.read_bytes())
            self.assertEqual(changed.raw, store._encode(store._decode(changed.raw)))
            self.assertEqual(changed.state.history, (event,))
            self.assertEqual(original.state.history, ())
            self.assertEqual(changed.revision, 2)
            self.assertEqual(store.read_risk_store(self.path, self.identity).state, changed.state)
        self.assert_no_temps()
        self.assertFalse(list(self.path.parent.glob("*.risk-pending.*")))

    def test_exact_duplicate_noop_changed_event_or_provenance_fences(self):
        with self.scope():
            current, event = self.append(self.boot())
            before = (self.path.read_bytes(), self.raw_anchor(), self.port.writes)
            self.assertIs(store.append_risk_event(self.path, current, event, self.proof(event.event_id)), current)
            self.assertEqual(before, (self.path.read_bytes(), self.raw_anchor(), self.port.writes))
            bad = replace(event, payload='{"reason":"different","evidence_ref":"synthetic-only"}')
            for changed, proof in [
                (bad, self.proof(event.event_id)),
                (event, dict(self.proof(event.event_id), evidence_digest="4" * 64)),
            ]:
                with self.subTest(changed=changed), self.assertRaises(store.RiskStoreError):
                    store.append_risk_event(self.path, current, changed, proof)
            self.assertEqual(before, (self.path.read_bytes(), self.raw_anchor(), self.port.writes))

    def test_copied_plain_forged_stale_and_wrong_path_receipts_reject(self):
        with self.scope():
            original = self.boot()
            event = self.event(original, "KILL", {"reason": "synthetic", "evidence_ref": "synthetic"})
            for receipt in [copy(original), replace(original), original.__dict__]:
                with self.subTest(kind=type(receipt)), self.assertRaises(store.RiskStoreError):
                    store.append_risk_event(self.path, receipt, event, self.proof())
            current = store.append_risk_event(self.path, original, event, self.proof())
            with self.assertRaises(store.RiskStoreError):
                store.append_risk_event(
                    self.path,
                    original,
                    self.event(original, "KILL", {"reason": "stale", "evidence_ref": "stale"}),
                    self.proof(),
                )
        other = self.path.with_name("other.json")
        with self.scope(other), self.assertRaises(store.RiskStoreError):
            store.append_risk_event(other, current, event, self.proof())
        self.assertFalse(other.exists())

    def test_coherent_source_rollback_deletion_and_identity_strip_reject(self):
        with self.scope():
            original = self.boot()
            current, _ = self.append(original)
            protected = self.raw_anchor()
            for source in [original.raw, None, store._encode({"version": 1})]:
                with self.subTest(source=source):
                    self.path.unlink() if source is None else self.path.write_bytes(source)
                    with self.assertRaises(store.RiskStoreError):
                        store.read_risk_store(self.path, self.identity)
                    self.assertEqual(self.raw_anchor(), protected)
                    self.path.write_bytes(current.raw)

    def test_earlier_history_ids_policy_and_projection_revalidated(self):
        with self.scope():
            current, _ = self.append(self.reserve(self.boot()))
            good_anchor = self.raw_anchor()
            data = store._decode(current.raw)
            cases = []
            bad = deepcopy(data)
            bad["entries"][0]["event"]["data"]["quantity"] = "-1"
            cases.append(bad)
            bad = deepcopy(data)
            bad["entries"][1]["event"]["event_id"] = bad["entries"][0]["event"]["event_id"]
            cases.append(bad)
            bad = deepcopy(data)
            bad["opening"]["policy"]["fee_basis"] = "base-fee"
            cases.append(bad)
            bad = deepcopy(data)
            bad["projection"]["cash_quote"] = [9999, 1]
            cases.append(bad)
            bad = deepcopy(data)
            bad["entries"][0]["provenance"]["evidence_digest"] = "5" * 64
            cases.append(bad)
            for index, bad in enumerate(cases):
                with self.subTest(index=index):
                    raw = store._encode(bad)
                    self.path.write_bytes(raw)
                    anchor = store._decode(good_anchor)
                    anchor["head"] = store._head(raw, bad)
                    self.set_anchor(anchor)
                    # Fake-anchor rewrite deliberately isolates semantic validation.
                    with self.assertRaises(store.RiskStoreError):
                        store.read_risk_store(self.path, self.identity)
            self.path.write_bytes(current.raw)
            self.port.values[next(iter(self.port.values))] = good_anchor
            self.assertEqual(store.read_risk_store(self.path, self.identity).state, current.state)

    def test_strict_anchor_and_provenance_types_duplicates_unknown_and_floats(self):
        with self.scope():
            receipt = self.boot()
            good = self.raw_anchor()
            anchor = store._decode(good)
            cases = [
                store._encode(bad)
                for bad in [
                    dict(anchor, version=True),
                    dict(anchor, unknown=1),
                    dict(anchor, state="STABLE"),
                    dict(anchor, head=dict(anchor["head"], revision=True)),
                ]
            ]
            cases += [
                good.replace(b'"version": 1', b'"version": 1, "version": 1'),
                good.rstrip(),
                good.replace(b'"version": 1', b'"version": 1e309'),
            ]
            for raw in cases:
                with self.subTest(raw=raw):
                    self.port.values[next(iter(self.port.values))] = raw
                    with self.assertRaises(store.RiskStoreError):
                        store.read_risk_store(self.path, self.identity)
            self.port.values[next(iter(self.port.values))] = good
            for proof in [
                dict(self.proof(), version=True),
                dict(self.proof(), unexpected=1),
                dict(self.proof(), basis="authenticated"),
                dict(self.proof(), record_digest="A" * 64),
            ]:
                with self.subTest(proof=proof), self.assertRaises(store.RiskStoreError):
                    store.append_risk_event(
                        self.path, receipt, self.event(receipt, "KILL", {"reason": "x", "evidence_ref": "x"}), proof
                    )

    def test_same_uid_other_root_store_policy_cannot_create_second_budget(self):
        with self.scope():
            receipt = self.boot()
        other = self.path.with_name("second-root-risk.json")
        for index in ("store", "policy", "same"):
            changed = deepcopy(self.raw_opening)
            if index == "store":
                changed["identity"]["ledger_store_id"] = "10000000-0000-4000-8000-000000000002"
            if index == "policy":
                changed["policy"]["policy_id"] = "20000000-0000-4000-8000-000000000002"
            with self.subTest(index=index), self.scope(other), self.assertRaises(store.RiskStoreError):
                store.bootstrap_risk_store(other, changed, self.proof(), operation_id="second-bootstrap")
            self.assertFalse(other.exists())
        self.assertEqual(self.path.read_bytes(), receipt.raw)
        self.assertEqual(
            store._slot(self.identity),
            store._slot(dict(self.identity, ledger_store_id="10000000-0000-4000-8000-000000000002")),
        )

    def test_missing_protected_existing_source_or_orphan_never_reseeds(self):
        with self.scope():
            receipt = self.boot()
            self.port.values.clear()
            with self.assertRaises(store.RiskStoreError):
                self.boot()
            with self.assertRaises(store.RiskStoreError):
                store.read_risk_store(self.path, self.identity)
            self.path.unlink()
            orphan = self.path.with_name(self.path.name + ".risk-pending." + "0" * 64 + ".json")
            orphan.write_bytes(receipt.raw)
            with self.assertRaises(store.RiskStoreError):
                self.boot()
            with self.assertRaises(store.RiskStoreError):
                store.recover_risk_store(self.path, self.identity, operation_id="synthetic-bootstrap")
            self.assertEqual(orphan.read_bytes(), receipt.raw)
            self.assertFalse(self.path.exists())
            self.assertEqual(self.port.values, {})

    def test_bootstrap_pending_absent_predecessor_recovers_exact_opening(self):
        with self.scope():
            self.pending_failure()
            pending = store._decode(self.raw_anchor())
            self.assertIsNone(pending["previous"])
            self.assertFalse(self.path.exists())
            target = self.journal().read_bytes()
            with self.assertRaises(store.RiskStoreError):
                store.read_risk_store(self.path, self.identity)
            recovered = store.recover_risk_store(self.path, self.identity, operation_id="synthetic-bootstrap")
            self.assertEqual(recovered.raw, target)
            self.assertEqual(recovered.revision, 1)
            self.assertEqual(recovered.state.history, ())
            self.assertIsNone(store.recover_risk_store(self.path, self.identity, operation_id="not-reseed"))
        self.assert_no_temps()

    def test_pending_old_and_target_forward_recovery_preserves_history(self):
        for after in (False, True):
            with self.subTest(after_source=after):
                self.setUp()
                with self.scope():
                    original = self.boot()
                    self.pending_failure(original, after_source=after)
                    target = self.journal().read_bytes()
                    self.assertEqual(self.path.read_bytes(), target if after else original.raw)
                    recovered = store.recover_risk_store(self.path, self.identity, operation_id="prepared-event")
                    self.assertEqual(recovered.raw, target)
                    self.assertEqual(recovered.revision, 2)
                    self.assertEqual(len(recovered.state.history), 1)
                    self.assertEqual(recovered.state.history[0].event_id, "prepared-event")
                    self.assertFalse(list(self.path.parent.glob("*.risk-pending.*")))
                self.assert_no_temps()

    def test_pending_changed_operation_namespace_and_third_source_fence(self):
        with self.scope():
            original = self.boot()
            self.pending_failure(original)
            raw_pending = self.raw_anchor()
            target = self.journal().read_bytes()
            with self.assertRaises(store.RiskStoreError):
                store.recover_risk_store(self.path, self.identity, operation_id="different")
            foreign = dict(self.identity, ledger_store_id="10000000-0000-4000-8000-000000000002")
            with self.assertRaises(store.RiskStoreError):
                store.recover_risk_store(self.path, foreign, operation_id="prepared-event")
            self.path.write_bytes(store._encode({"third": "unrecognized"}))
            with self.assertRaises(store.RiskStoreError):
                store.recover_risk_store(self.path, self.identity, operation_id="prepared-event")
            self.assertEqual(self.raw_anchor(), raw_pending)
            self.assertEqual(self.journal().read_bytes(), target)

    def test_missing_truncated_substituted_hardlinked_journal_fences(self):
        for damage in ("missing", "truncated", "substituted", "hardlink"):
            with self.subTest(damage=damage):
                self.setUp()
                with self.scope():
                    original = self.boot()
                    self.pending_failure(original)
                    journal = self.journal()
                    protected = self.raw_anchor()
                    raw = journal.read_bytes()
                    if damage == "missing":
                        journal.unlink()
                    elif damage == "truncated":
                        journal.write_bytes(raw[:100])
                    elif damage == "substituted":
                        journal.write_bytes(original.raw)
                    else:
                        os.link(journal, journal.with_name("linked-target.json"))
                    with self.assertRaises(store.RiskStoreError):
                        store.recover_risk_store(self.path, self.identity, operation_id="prepared-event")
                    self.assertEqual(self.path.read_bytes(), original.raw)
                    self.assertEqual(self.raw_anchor(), protected)

    def test_pending_persisted_write_then_error_retains_exact_journal(self):
        with self.scope():
            original = self.boot()

            def persisted(slot, value):
                self.port.values[slot] = value
                raise OSError("pending persisted then raised")

            self.port.write_hook = persisted
            with self.assertRaises(store.RiskStoreError):
                self.append(original, event_id="pending-ambiguous")
            self.port.write_hook = None
            self.assertEqual(self.path.read_bytes(), original.raw)
            self.assertEqual(store._decode(self.raw_anchor())["state"], "pending")
            self.assertTrue(self.journal().exists())
            self.assertEqual(
                store.recover_risk_store(self.path, self.identity, operation_id="pending-ambiguous").revision, 2
            )

    def test_failed_pending_readback_never_publishes_or_reseeds(self):
        with self.scope():
            original = self.boot()
            old_anchor = self.raw_anchor()
            stale = [False]

            def written(slot, value):
                self.port.values[slot] = value
                stale[0] = True

            def readback(slot, value):
                if stale[0]:
                    stale[0] = False
                    return old_anchor
                return value

            self.port.write_hook = written
            self.port.read_hook = readback
            with self.assertRaises(store.RiskStoreError):
                self.append(original, event_id="stale-readback")
            self.port.write_hook = self.port.read_hook = None
            self.assertEqual(self.path.read_bytes(), original.raw)
            self.assertEqual(store._decode(self.raw_anchor())["state"], "pending")
            self.assertEqual(
                store.recover_risk_store(self.path, self.identity, operation_id="stale-readback").revision, 2
            )

    def test_stable_persisted_write_then_error_leftover_conservatively_fences(self):
        with self.scope():
            original = self.boot()

            def stable_error(slot, value):
                self.port.values[slot] = value
                if store._decode(value)["state"] == "stable":
                    raise OSError("stable persisted then raised")

            self.port.write_hook = stable_error
            with self.assertRaises(store.RiskStoreError):
                self.append(original, event_id="stable-ambiguous")
            self.port.write_hook = None
            anchor = self.raw_anchor()
            journal = next(self.path.parent.glob("*.risk-pending.*"))
            raw = journal.read_bytes()
            self.assertEqual(store._decode(anchor)["state"], "stable")
            self.assertEqual(self.path.read_bytes(), raw)
            for action in [
                lambda: store.read_risk_store(self.path, self.identity),
                lambda: store.recover_risk_store(self.path, self.identity, operation_id="stable-ambiguous"),
            ]:
                with self.assertRaises(store.RiskStoreError):
                    action()
            self.assertEqual(journal.read_bytes(), raw)
            self.assertEqual(self.raw_anchor(), anchor)

    def test_cleanup_failure_never_undoes_stable_or_deletes_unknown_journal(self):
        with self.scope():
            original = self.boot()
            real = Path.unlink

            def before_unlink(path, *args, **kwargs):
                if ".risk-pending." in path.name:
                    raise OSError("stable journal cleanup failure")
                return real(path, *args, **kwargs)

            with patch.object(Path, "unlink", new=before_unlink), self.assertRaises(store.RiskStoreError):
                self.append(original, event_id="cleanup-failure")
            anchor = self.raw_anchor()
            raw = self.path.read_bytes()
            journal = next(self.path.parent.glob("*.risk-pending.*"))
            journal.write_bytes(b"altered unknown journal")
            with self.assertRaises(store.RiskStoreError):
                store.read_risk_store(self.path, self.identity)
            self.assertEqual(self.path.read_bytes(), raw)
            self.assertEqual(self.raw_anchor(), anchor)
            self.assertEqual(journal.read_bytes(), b"altered unknown journal")

    def test_guard_loss_at_pending_write_fences_before_source_and_forward_recovers(self):
        with self.scope():
            original = self.boot()

            def lost(slot, value):
                self.port.values[slot] = value
                if store._decode(value)["state"] == "pending":
                    self.live = False

            self.port.write_hook = lost
            with self.assertRaises(store.RiskStoreError):
                self.append(original, event_id="lost-lifetime")
            self.live = True
            self.port.write_hook = None
            self.assertEqual(self.path.read_bytes(), original.raw)
            self.assertEqual(
                store.recover_risk_store(self.path, self.identity, operation_id="lost-lifetime").revision, 2
            )

    def test_context_loss_and_copied_thread_reject_even_guard_callback_returns(self):
        with self.scope():
            receipt = self.boot()
            raw = self.path.read_bytes()
            errors = []
            context = __import__("contextvars").copy_context()

            def foreign():
                try:
                    context.run(store.read_risk_store, self.path, self.identity)
                except BaseException as exc:
                    errors.append(exc)

            thread = threading.Thread(target=foreign)
            thread.start()
            thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(len(errors), 1)
            self.assertIsInstance(errors[0], store.RiskStoreError)
            token = store._CONTEXT.set(None)
            try:
                with self.assertRaises(store.RiskStoreError):
                    store.append_risk_event(
                        self.path,
                        receipt,
                        self.event(receipt, "KILL", {"reason": "x", "evidence_ref": "x"}),
                        self.proof(),
                    )
            finally:
                store._CONTEXT.reset(token)
            self.assertEqual(self.path.read_bytes(), raw)

    def test_foreign_pid_expired_and_nested_scope_fence(self):
        with self.scope():
            receipt = self.boot()
            with (
                patch.object(store.os, "getpid", return_value=os.getpid() + 1),
                self.assertRaises(store.RiskStoreError),
            ):
                store.read_risk_store(self.path, self.identity)
            with self.assertRaises(store.RiskStoreError):
                with self.scope():
                    pass
            with (
                patch.object(store.time, "monotonic", return_value=self.deadline),
                self.assertRaises(store.RiskStoreError),
            ):
                store.read_risk_store(self.path, self.identity)
            self.assertEqual(self.path.read_bytes(), receipt.raw)
        with self.assertRaises(store.RiskStoreError):
            with store._storage_scope(
                self.path, protected=self.port, guard=self.guard, deadline=time.monotonic() - 1.0
            ):
                pass

    def test_post_replay_lifetime_and_deadline_never_return_read_or_duplicate(self):
        with self.scope():
            original = self.boot()
            current, event = self.append(original)
            raw = self.path.read_bytes()
            real = store._replay

            def invalidated(*args):
                result = real(*args)
                self.live = False
                return result

            with patch.object(store, "_replay", side_effect=invalidated), self.assertRaises(store.RiskStoreError):
                store.read_risk_store(self.path, self.identity)
            self.live = True
            calls = [0]

            def expired(*args):
                result = real(*args)
                calls[0] += 1
                if calls[0] == 2:
                    store._CONTEXT.get().deadline = time.monotonic() - 1.0
                return result

            original_deadline = self.deadline
            with patch.object(store, "_replay", side_effect=expired), self.assertRaises(store.RiskStoreError):
                store.append_risk_event(self.path, current, event, self.proof(event.event_id))
            store._CONTEXT.get().deadline = original_deadline
            self.assertEqual(self.path.read_bytes(), raw)

    def test_actual_close_double_fault_preserves_primary_cancellation_identity(self):
        for interruption in (KeyboardInterrupt("synthetic-interrupt"), SystemExit("synthetic-exit")):
            with self.subTest(interruption=interruption):
                self.setUp()
                real_close = os.close
                cleanup = OSError("after actual fd close")

                def closed(fd):
                    real_close(fd)
                    raise cleanup

                with (
                    self.scope(),
                    patch.object(store.os, "write", side_effect=interruption),
                    patch.object(store.os, "close", side_effect=closed),
                ):
                    with self.assertRaises(type(interruption)) as caught:
                        self.boot()
                    self.assertIs(caught.exception, interruption)
                    self.assertIs(caught.exception.__cause__, cleanup)
                    self.assertFalse(self.path.exists())
                    self.assertEqual(self.port.values, {})

    def test_protected_cancellation_after_persist_keeps_pending_and_exact_identity(self):
        with self.scope():
            original = self.boot()
            interruption = KeyboardInterrupt("pending persisted interrupt")

            def persisted(slot, value):
                self.port.values[slot] = value
                raise interruption

            self.port.write_hook = persisted
            with self.assertRaises(KeyboardInterrupt) as caught:
                self.append(original, event_id="cancelled-pending")
            self.assertIs(caught.exception, interruption)
            self.port.write_hook = None
            self.assertEqual(self.path.read_bytes(), original.raw)
            self.assertEqual(
                store.recover_risk_store(self.path, self.identity, operation_id="cancelled-pending").revision, 2
            )

    def test_partial_unknown_terminal_reset_rollover_finance_history_persists(self):
        with self.scope():
            receipt = self.reserve(self.boot())
            receipt, _ = self.append(receipt, "TRANSPORT", {"request_id": "request-A"})
            receipt, _ = self.append(
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
            receipt, _ = self.append(receipt, "UNKNOWN", {"request_id": "request-A", "evidence_ref": "uncertain"})
            self.assertEqual(receipt.state.reservations[0].remaining, Fraction(1))
            self.assertEqual(receipt.state.cash_quote, Fraction("990.91"))
            self.assertEqual(store.read_risk_store(self.path, self.identity).state, receipt.state)
            receipt, _ = self.append(
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
                "marks": {a: token(v) for a, v in receipt.state.marks},
                "balances_at": utc(at),
                "marks_at": utc(at),
                "external_open_request_ids": [],
            }
            receipt, _ = self.append(receipt, "OBSERVE", observe, at=at)
            receipt, _ = self.append(
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
            receipt, _ = self.append(receipt, "OBSERVE", observe, at=at)
            receipt, _ = self.append(
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
            restored = store.read_risk_store(self.path, self.identity)
            self.assertEqual(restored.state, receipt.state)
            self.assertEqual(
                finance,
                (
                    restored.state.positions,
                    restored.state.cash_quote,
                    restored.state.realized_quote,
                    restored.state.reservations,
                    restored.state.trades,
                    restored.state.attempts,
                ),
            )
            self.assertEqual(len(restored.state.history), 9)
            self.assertEqual(restored.state.history[3].kind, "UNKNOWN")
            self.assertEqual(restored.state.history[6].kind, "RESET")

    def test_real_close_and_unlink_double_fault_retain_both_cleanup_causes(self):
        for interruption in (KeyboardInterrupt("primary-write"), SystemExit("primary-write")):
            with self.subTest(interruption=interruption):
                self.setUp()
                real_close = os.close
                real_unlink = Path.unlink
                close_error = OSError("after actual writer fd close")
                unlink_error = OSError("after actual temporary unlink")

                def closed(fd):
                    real_close(fd)
                    raise close_error

                def unlinked(path, *args, **kwargs):
                    real_unlink(path, *args, **kwargs)
                    raise unlink_error

                with (
                    self.scope(),
                    patch.object(store.os, "write", side_effect=interruption),
                    patch.object(store.os, "close", side_effect=closed),
                    patch.object(Path, "unlink", new=unlinked),
                ):
                    with self.assertRaises(type(interruption)) as caught:
                        store._write_exact(self.path, b"benign-synthetic-payload", self.path, exclusive=False)
                    self.assertIs(caught.exception, interruption)
                    self.assertIs(caught.exception.__cause__, unlink_error)
                    self.assertIs(unlink_error.__cause__, close_error)
                self.assertFalse(self.path.exists())
                self.assert_no_temps()
                self.assertEqual(self.port.values, {})

    def test_port_callback_cannot_change_original_deadline_port_or_guard(self):
        for field in ("deadline", "port", "guard"):
            with self.subTest(field=field):
                self.setUp()
                with self.scope():
                    receipt = self.boot()
                    original_scope = store._CONTEXT.get()
                    original = getattr(original_scope, field)
                    other_port = FakeProtectedPort()
                    other_port.values = dict(self.port.values)
                    changed = {"deadline": self.deadline + 3600.0, "port": other_port, "guard": lambda: None}[field]
                    armed = [True]

                    def mutate(slot, value):
                        if armed[0]:
                            armed[0] = False
                            setattr(original_scope, field, changed)
                        return value

                    self.port.read_hook = mutate
                    try:
                        with self.assertRaises(store.RiskStoreError):
                            store.read_risk_store(self.path, self.identity)
                    finally:
                        setattr(original_scope, field, original)
                        self.port.read_hook = None
                    self.assertEqual(self.path.read_bytes(), receipt.raw)
                    self.assertEqual(self.raw_anchor(), receipt.protected_raw)
                    self.assertEqual(other_port.writes, 0)

    def test_original_guard_cannot_redirect_bootstrap_path_after_precheck(self):
        with self.scope():
            original_scope = store._CONTEXT.get()
            original_path = original_scope.path
            other = self.path.with_name("redirected-risk.json")
            armed = [True]

            def redirected():
                if armed[0]:
                    armed[0] = False
                    original_scope.path = other

            self.guard_hook = redirected
            try:
                with self.assertRaises(store.RiskStoreError):
                    self.boot()
            finally:
                original_scope.path = original_path
                self.guard_hook = None
            self.assertFalse(self.path.exists())
            self.assertFalse(other.exists())
            self.assertEqual(self.port.values, {})

    def test_expired_original_receipt_cannot_adopt_cloned_port_in_new_scope(self):
        with self.scope():
            receipt = self.boot()
        original_port = self.port
        clone = FakeProtectedPort()
        clone.values = dict(original_port.values)
        self.port = clone
        with self.scope():
            event = self.event(receipt, "KILL", {"reason": "different-scope", "evidence_ref": "synthetic"})
            with self.assertRaises(store.RiskStoreError):
                store.append_risk_event(self.path, receipt, event, self.proof())
        self.assertEqual(self.path.read_bytes(), receipt.raw)
        self.assertEqual(clone.writes, 0)
        self.assertEqual(original_port.values, clone.values)

    def test_manually_malformed_event_scalar_errors_are_owned_before_writes(self):
        with self.scope():
            receipt = self.boot()
            event = self.event(receipt, "KILL", {"reason": "synthetic", "evidence_ref": "synthetic"})
            before = (self.path.read_bytes(), self.raw_anchor(), self.port.writes)
            for bad in (
                replace(event, at=float("inf")),
                replace(event, at=2**63 - 1),
                replace(event, payload=None),
                replace(event, at=True),
            ):
                with self.subTest(bad=bad), self.assertRaises(store.RiskStoreError):
                    store.append_risk_event(self.path, receipt, bad, self.proof())
            self.assertEqual(before, (self.path.read_bytes(), self.raw_anchor(), self.port.writes))

    def test_final_replace_rechecks_original_source_and_pending_after_temp_fsync(self):
        for bootstrap in (False, True):
            for changed in ("source", "anchor"):
                with self.subTest(bootstrap=bootstrap, changed=changed):
                    self.setUp()
                    with self.scope():
                        original = None if bootstrap else self.boot()
                        before = None if original is None else original.raw
                        old_anchor = None if original is None else self.raw_anchor()
                        real_write = store._write_exact
                        real_fsync = os.fsync
                        active = [False]
                        mutated = [False]
                        third = store._encode({"third_source": "synthetic-concurrent-change"})

                        def writing(path, raw, scope_path, *, exclusive, **kwargs):
                            active[0] = not exclusive
                            try:
                                return real_write(path, raw, scope_path, exclusive=exclusive, **kwargs)
                            finally:
                                active[0] = False

                        def fsynced(fd):
                            real_fsync(fd)
                            if active[0] and not mutated[0]:
                                mutated[0] = True
                                if changed == "source":
                                    self.path.write_bytes(third)
                                elif old_anchor is None:
                                    self.port.values.clear()
                                else:
                                    self.port.values[next(iter(self.port.values))] = old_anchor

                        with (
                            patch.object(store, "_write_exact", side_effect=writing),
                            patch.object(store.os, "fsync", side_effect=fsynced),
                        ):
                            with self.assertRaises(store.RiskStoreError):
                                self.boot() if bootstrap else self.append(original, event_id="final-boundary")
                        self.assertTrue(mutated[0])
                        if changed == "source":
                            self.assertEqual(self.path.read_bytes(), third)
                        elif before is None:
                            self.assertFalse(self.path.exists())
                        else:
                            self.assertEqual(self.path.read_bytes(), before)
                        self.assertTrue(list(self.path.parent.glob("*.risk-pending.*")))
                        self.assert_no_temps()

    def test_prepublication_temp_corruption_or_identity_substitution_preserves_old_source(self):
        import hashlib
        import json

        for bootstrap in (False, True):
            for damage in ("bytes", "identical_inode", "hardlink"):
                with self.subTest(bootstrap=bootstrap, damage=damage):
                    self.setUp()
                    with self.scope():
                        original = None if bootstrap else self.boot()
                        before = None if original is None else original.raw
                        real_write, real_close = store._write_exact, os.close
                        active, mutated, retained = [False], [False], {}

                        def writing(path, raw, scope_path, *, exclusive, **kwargs):
                            active[0] = not exclusive
                            try:
                                return real_write(path, raw, scope_path, exclusive=exclusive, **kwargs)
                            finally:
                                active[0] = False

                        def closed(fd):
                            real_close(fd)
                            if active[0] and not mutated[0]:
                                candidates = list(self.path.parent.glob(self.path.name + ".write-*"))
                                self.assertEqual(len(candidates), 1)
                                temp = candidates[0]
                                retained["target"] = temp.read_bytes()
                                retained["protected"] = self.raw_anchor()
                                retained["journal_path"] = self.journal()
                                retained["journal"] = retained["journal_path"].read_bytes()
                                mutated[0] = True
                                if damage == "bytes":
                                    temp.write_bytes(b"detectable-prepublication-temp-corruption\n")
                                elif damage == "identical_inode":
                                    original_temp = temp.with_name(temp.name + ".retained-original")
                                    temp.rename(original_temp)
                                    temp.write_bytes(retained["target"])
                                    self.assertNotEqual(temp.stat().st_ino, original_temp.stat().st_ino)
                                else:
                                    os.link(temp, temp.with_name(temp.name + ".retained-alias"))
                                    self.assertEqual(temp.stat().st_nlink, 2)

                        caught = None
                        with (
                            patch.object(store, "_write_exact", side_effect=writing),
                            patch.object(store.os, "close", side_effect=closed),
                        ):
                            try:
                                self.boot() if bootstrap else self.append(original, event_id="temp-boundary-event")
                            except BaseException as error:
                                caught = error
                        actual = self.path.read_bytes() if self.path.exists() else None
                        protected_same = self.raw_anchor() == retained["protected"]
                        journal_same = (
                            retained["journal_path"].exists()
                            and retained["journal_path"].read_bytes() == retained["journal"]
                        )
                        print(
                            json.dumps(
                                {
                                    "control": "prepared_temp",
                                    "bootstrap": bootstrap,
                                    "damage": damage,
                                    "mutated_after_actual_close": mutated[0],
                                    "actual_error": None if caught is None else type(caught).__name__,
                                    "source_preserved": actual == before,
                                    "protected_pending_preserved": protected_same,
                                    "exact_target_journal_preserved": journal_same,
                                    "before_sha256": None if before is None else hashlib.sha256(before).hexdigest(),
                                    "after_sha256": None if actual is None else hashlib.sha256(actual).hexdigest(),
                                },
                                sort_keys=True,
                            )
                        )
                        self.assertTrue(mutated[0])
                        self.assertIsInstance(caught, store.RiskStoreError)
                        self.assertEqual(actual, before)
                        self.assertTrue(protected_same)
                        self.assertTrue(journal_same)

    def test_invalid_utf8_or_oversized_integer_event_payload_is_owned_before_mutation(self):
        import json

        with self.scope():
            original = self.boot()
            event = self.event(original, "KILL", {"reason": "synthetic", "evidence_ref": "synthetic"})
            before = (self.path.read_bytes(), self.raw_anchor(), self.port.writes)
            cases = {
                "surrogate": '{"reason":"\ud800","evidence_ref":"synthetic"}',
                "oversized_integer": '{"reason":' + "1" * 5000 + ',"evidence_ref":"synthetic"}',
            }
            for name, payload in cases.items():
                with self.subTest(payload_case=name):
                    caught = None
                    try:
                        store.append_risk_event(self.path, original, replace(event, payload=payload), self.proof())
                    except BaseException as error:
                        caught = error
                    unchanged = before == (self.path.read_bytes(), self.raw_anchor(), self.port.writes)
                    print(
                        json.dumps(
                            {
                                "control": "event_payload_framing",
                                "payload_case": name,
                                "actual_error": None if caught is None else type(caught).__name__,
                                "storage_unchanged": unchanged,
                            },
                            sort_keys=True,
                        )
                    )
                    self.assertTrue(unchanged)
                    self.assertIsInstance(caught, store.RiskStoreError)

    def test_grouped_untrusted_json_parser_failures_are_owned_without_storage_mutation(self):
        import json

        cases = {
            "oversized_integer": ('{"nested":' + "1" * 5000 + "}").encode("ascii"),
            "deep_nesting": ('{"nested":' + "[" * 1100 + "0" + "]" * 1100 + "}").encode("ascii"),
            "deep_recursion": ('{"nested":' + "[" * 20000 + "0" + "]" * 20000 + "}").encode("ascii"),
        }
        for where in ("source", "journal", "anchor"):
            for name, raw in cases.items():
                with self.subTest(where=where, parser_case=name):
                    self.setUp()
                    with self.scope():
                        original = self.boot()
                        journal = None
                        if where == "journal":
                            self.pending_failure(original)
                            journal = self.journal()
                            journal.write_bytes(raw)
                        elif where == "source":
                            self.path.write_bytes(raw)
                        else:
                            self.port.values[next(iter(self.port.values))] = raw
                        before = (
                            self.path.read_bytes(),
                            self.raw_anchor(),
                            self.port.writes,
                            None if journal is None else journal.read_bytes(),
                        )
                        caught = None
                        try:
                            if where == "journal":
                                store.recover_risk_store(self.path, self.identity, operation_id="prepared-event")
                            else:
                                store.read_risk_store(self.path, self.identity)
                        except BaseException as error:
                            caught = error
                        after = (
                            self.path.read_bytes(),
                            self.raw_anchor(),
                            self.port.writes,
                            None if journal is None else journal.read_bytes(),
                        )
                        print(
                            json.dumps(
                                {
                                    "control": "stored_json_framing",
                                    "where": where,
                                    "parser_case": name,
                                    "raw_bytes": len(raw),
                                    "actual_error": None if caught is None else type(caught).__name__,
                                    "supplied_state_unchanged": before == after,
                                    "pristine_source_retained": self.path.read_bytes() == original.raw,
                                },
                                sort_keys=True,
                            )
                        )
                        self.assertEqual(before, after)
                        self.assertIsInstance(caught, store.RiskStoreError)
        self.setUp()
        with self.scope():
            original = self.boot()
            event = self.event(original, "KILL", {"reason": "synthetic", "evidence_ref": "synthetic"})
            before = (self.path.read_bytes(), self.raw_anchor(), self.port.writes)
            caught = None
            try:
                store.append_risk_event(
                    self.path, original, replace(event, payload=cases["deep_recursion"].decode("ascii")), self.proof()
                )
            except BaseException as error:
                caught = error
            print(
                json.dumps(
                    {
                        "control": "event_recursive_payload",
                        "actual_error": None if caught is None else type(caught).__name__,
                        "storage_unchanged": before == (self.path.read_bytes(), self.raw_anchor(), self.port.writes),
                    },
                    sort_keys=True,
                )
            )
            self.assertEqual(before, (self.path.read_bytes(), self.raw_anchor(), self.port.writes))
            self.assertIsInstance(caught, store.RiskStoreError)
