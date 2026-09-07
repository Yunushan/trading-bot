from __future__ import annotations

import errno
import json
import multiprocessing
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.integrations.exchanges.binance.orders import order_intent_runtime as ledger  # noqa: E402
from app.integrations.exchanges.binance.orders import order_intent_store as store  # noqa: E402
from app.integrations.exchanges.binance.orders.order_intent_provisioning import PROVISION_ACK, provision_order_intent_store  # noqa: E402
from app.settings.live_safety import LiveTradingSafetyError  # noqa: E402


def _owner(directory):
    return SimpleNamespace(_order_audit_log_path=Path(directory) / "orders.jsonl", api_key="unit-api-key", mode="Live")


def _params(identifier="fixture-A"):
    return {"newClientOrderId": identifier, "symbol": "BTCUSDT", "side": "BUY", "type": "MARKET", "quantity": "1"}


def _begin(owner, identifier="fixture-A"):
    return ledger._begin_order_intent(owner, _params(identifier), market="futures", source="offline-test")


def _race(directory, index, barrier, results, update=False):
    owner = _owner(directory)
    barrier.wait(timeout=30)
    try:
        if update:
            ledger._update_order_intent_by_id(owner, "fixture-A", state="accepted", **{f"worker_{index}": True})
        else:
            _begin(owner, f"fixture-{index}")
        results.put((index, "ok"))
    except LiveTradingSafetyError as exc:
        results.put((index, str(exc)))


def _holder(directory, phase, ready, release):
    owner = _owner(directory)
    if phase == "lock":
        with store.ledger_transaction(ledger._intent_path(owner)):
            ready.set()
            release.wait(timeout=30)
    elif phase == "before-publish":
        def pause_publish(*_args):
            ready.set()
            if not release.wait(timeout=30):
                raise RuntimeError("Test was not released")
        with patch.object(store, "_publish", side_effect=pause_publish):
            _begin(owner, "interrupted")
    else:
        _begin(owner, "interrupted")
        ready.set()
        release.wait(timeout=30)


def _attempt_with_timeout(directory, results):
    with patch.object(store, "LOCK_TIMEOUT_SECONDS", 0.2):
        try:
            _begin(_owner(directory))
            results.put("ok")
        except LiveTradingSafetyError as exc:
            results.put(str(exc))


class OrderIntentTransactionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = self.enterContext(tempfile.TemporaryDirectory())
        self.owner = _owner(self.tmp)
        self.path = ledger._intent_path(self.owner)
        provision_order_intent_store(self.owner, acknowledgement=PROVISION_ACK)
        self.context = multiprocessing.get_context("spawn")

    def start_process(self, target, args):
        process = self.context.Process(target=target, args=args)
        process.start()
        self.addCleanup(self.stop_process, process)
        return process

    @staticmethod
    def stop_process(process):
        if process.is_alive():
            process.terminate()
        process.join(timeout=10)

    def queue(self):
        queue = self.context.Queue()
        self.addCleanup(queue.close)
        return queue

    def accepted(self):
        _begin(self.owner)
        ledger._mark_order_intent_accepted(self.owner, _params(), via="test", result={
            "orderId": 123, "clientOrderId": "fixture-A", "symbol": "BTCUSDT", "status": "FILLED",
            "side": "BUY", "origQty": "1", "executedQty": "1",
        })

    def test_existing_version_two_ledger_and_duplicate_ids_remain_protected(self):
        self.accepted()
        self.assertEqual(2, json.loads(self.path.read_text())["format_version"])
        with self.assertRaisesRegex(LiveTradingSafetyError, "already has state accepted"):
            _begin(self.owner)
        _begin(self.owner, "fixture-B")
        self.assertEqual(2, ledger.get_order_intent_status(self.owner)["intent_count"])

    def test_malformed_record_cannot_hide_an_unresolved_intent(self):
        records = [None, [], {}, {"client_order_id": "wrong", "state": "pending"}]
        records += [{"client_order_id": "fixture-A", "state": state} for state in (None, [], {}, "", "unrecognized")]
        for record in records:
            with self.subTest(record=record):
                self.path.write_text(json.dumps({"format_version": 1, "intents": {"fixture-A": record}}))
                with self.assertRaisesRegex(LiveTradingSafetyError, "invalid record"):
                    _begin(self.owner, "fixture-B")
                with self.assertRaises(LiveTradingSafetyError):
                    ledger.get_order_intent_status(self.owner)

    def test_invalid_schema_duplicate_keys_and_unreadable_path_fail_closed(self):
        payloads = ["", "{", "[]", '{"intents": {}}', '{"format_version":true,"intents":{}}',
                    '{"format_version":2,"intents":{}}', '{"format_version":1,"intents":{},"intents":{}}']
        for text in payloads:
            with self.subTest(text=text):
                self.path.write_text(text)
                with self.assertRaises(LiveTradingSafetyError):
                    _begin(self.owner)
        self.path.unlink()
        self.path.mkdir()
        with self.assertRaises(LiveTradingSafetyError):
            _begin(self.owner)

    def test_missing_record_cannot_be_marked_submitted_or_reconciled(self):
        with self.assertRaisesRegex(LiveTradingSafetyError, "record is missing"):
            ledger._mark_order_intent_submitted(self.owner, _params(), via="primary")
        with self.assertRaisesRegex(LiveTradingSafetyError, "record is missing"):
            ledger._update_order_intent_by_id(self.owner, "missing", state="accepted")

    def test_flush_precedes_publish_and_files_use_unique_temporary_names(self):
        calls, temp_names = [], []
        fsync, publish = store.os.fsync, store._publish

        def sync(fd):
            calls.append("fsync")
            return fsync(fd)

        def publish_file(temp_path, path):
            calls.append("publish")
            temp_names.append(temp_path)
            self.assertEqual(self.path.parent, temp_path.parent)
            self.assertEqual("fsync", calls[-2])
            return publish(temp_path, path)

        with patch.object(store.os, "fsync", side_effect=sync), patch.object(store, "_publish", side_effect=publish_file):
            _begin(self.owner)
            ledger._mark_order_intent_submitted(self.owner, _params(), via="primary")
        self.assertEqual(2, len(set(temp_names)))
        self.assertFalse(any(path.exists() for path in temp_names))
        if os.name != "nt":
            self.assertEqual(0o600, self.path.stat().st_mode & 0o777)

    def test_storage_failures_preserve_old_ledger_and_clean_temporary_files(self):
        self.accepted()
        previous = self.path.read_bytes()
        for target, attribute, error in (
            (store.os, "fsync", OSError(errno.EIO, "sync failed")),
            (store, "_publish", OSError(errno.ENOSPC, "disk full")),
            (store, "_publish", PermissionError("read only")),
            (store.json, "dumps", ValueError("invalid serialization")),
        ):
            with self.subTest(attribute=attribute, error=type(error).__name__):
                with patch.object(target, attribute, side_effect=error):
                    with self.assertRaises(LiveTradingSafetyError):
                        _begin(self.owner, "fixture-B")
                self.assertEqual(previous, self.path.read_bytes())
                self.assertEqual([], list(Path(self.tmp).glob("*.tmp")))

    def test_uncertain_publish_keeps_pending_intent_blocked(self):
        publish = store._publish

        def fail_after_publish(*args):
            publish(*args)
            raise OSError(errno.EIO, "sync completion unknown")

        with patch.object(store, "_publish", side_effect=fail_after_publish):
            with self.assertRaises(LiveTradingSafetyError):
                _begin(self.owner)
        with self.assertRaisesRegex(LiveTradingSafetyError, "Unresolved exchange order intent"):
            _begin(self.owner, "fixture-B")
        self.assertEqual(["fixture-A"], ledger.get_order_intent_status(self.owner)["unresolved_client_order_ids"])

    def test_storage_error_never_reaches_primary_or_fallback_exchange(self):
        from test_binance_package_split_smoke import _FuturesAuditWrapper

        wrapper = _FuturesAuditWrapper()
        wrapper._initialize_test_order_store(path=Path(self.tmp) / "futures.jsonl")
        wrapper._testnet_order_fallback_client = Mock(side_effect=AssertionError("fallback must not be tried"))
        with patch.object(store, "_publish", side_effect=OSError(errno.ENOSPC, "disk full")):
            with self.assertRaises(LiveTradingSafetyError):
                wrapper._futures_create_order_with_fallback(_params())
        self.assertEqual([], wrapper.client.orders)
        wrapper._testnet_order_fallback_client.assert_not_called()

    def test_concurrent_processes_cannot_both_begin_an_unresolved_order(self):
        barrier, results = self.context.Barrier(3), self.queue()
        processes = [self.start_process(_race, (self.tmp, index, barrier, results)) for index in range(3)]
        outcomes = [results.get(timeout=45) for _ in processes]
        for process in processes:
            process.join(timeout=10)
            self.assertEqual(0, process.exitcode)
        self.assertEqual(1, sum(result == "ok" for _, result in outcomes), outcomes)
        self.assertTrue(all(result == "ok" or "Unresolved exchange order intent" in result for _, result in outcomes))
        self.assertEqual(1, ledger.get_order_intent_status(self.owner)["intent_count"])

    def test_submit_or_accept_persistence_failure_preserves_ambiguity_block(self):
        from test_binance_package_split_smoke import _FuturesAuditWrapper

        for failing_write in (2, 3):
            with self.subTest(failing_write=failing_write):
                wrapper = _FuturesAuditWrapper()
                wrapper._initialize_test_order_store(path=Path(self.tmp) / f"stage-{failing_write}.jsonl")
                wrapper._testnet_order_fallback_client = Mock(side_effect=AssertionError("no storage-error fallback"))
                publish, writes = store._publish, []

                def fail_selected_write(*args):
                    writes.append(args)
                    if len(writes) == failing_write:
                        raise OSError(errno.ENOSPC, "disk full")
                    publish(*args)

                with patch.object(store, "_publish", side_effect=fail_selected_write):
                    with self.assertRaises(LiveTradingSafetyError):
                        wrapper._futures_create_order_with_fallback(_params())
                self.assertEqual(0 if failing_write == 2 else 1, len(wrapper.client.orders))
                with self.assertRaisesRegex(LiveTradingSafetyError, "Unresolved exchange order intent"):
                    wrapper._futures_create_order_with_fallback(_params("fixture-B"))
                self.assertEqual(1, wrapper.get_order_intent_status()["unresolved_count"])
                wrapper._testnet_order_fallback_client.assert_not_called()

    def test_concurrent_updates_merge_without_losing_fields(self):
        self.accepted()
        barrier, results = self.context.Barrier(3), self.queue()
        processes = [self.start_process(_race, (self.tmp, index, barrier, results, True)) for index in range(3)]
        self.assertEqual(["ok"] * 3, sorted(results.get(timeout=45)[1] for _ in processes))
        for process in processes:
            process.join(timeout=10)
            self.assertEqual(0, process.exitcode)
        record = ledger._get_order_intent_record(self.owner, "fixture-A")
        self.assertTrue(all(record[f"worker_{index}"] for index in range(3)))

    def test_busy_lock_fails_closed_and_is_reusable_after_release(self):
        results = self.queue()
        with store.ledger_transaction(self.path):
            process = self.start_process(_attempt_with_timeout, (self.tmp, results))
            self.assertIn("ledger is busy", results.get(timeout=30))
            process.join(timeout=10)
            self.assertEqual(0, process.exitcode)
        _begin(self.owner)

    def test_killed_holder_releases_os_lock_without_deleting_lock_file(self):
        ready, release = self.context.Event(), self.context.Event()
        process = self.start_process(_holder, (self.tmp, "lock", ready, release))
        self.assertTrue(ready.wait(timeout=30))
        self.stop_process(process)
        self.assertTrue(self.path.with_name(f".{self.path.name}.lock").is_file())
        _begin(self.owner)

    def test_killed_writer_before_publish_preserves_original_ledger(self):
        self.accepted()
        previous = self.path.read_bytes()
        ready, release = self.context.Event(), self.context.Event()
        process = self.start_process(_holder, (self.tmp, "before-publish", ready, release))
        self.assertTrue(ready.wait(timeout=30))
        self.stop_process(process)
        self.assertEqual(previous, self.path.read_bytes())
        _begin(self.owner, "fixture-B")
        self.assertEqual(2, ledger.get_order_intent_status(self.owner)["intent_count"])

    def test_killed_writer_after_pending_commit_preserves_restart_block(self):
        ready, release = self.context.Event(), self.context.Event()
        process = self.start_process(_holder, (self.tmp, "after-publish", ready, release))
        self.assertTrue(ready.wait(timeout=30))
        self.stop_process(process)
        with self.assertRaisesRegex(LiveTradingSafetyError, "Unresolved exchange order intent"):
            _begin(self.owner)
        self.assertEqual(["interrupted"], ledger.get_order_intent_status(self.owner)["unresolved_client_order_ids"])


if __name__ == "__main__":
    unittest.main()
