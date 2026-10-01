"""Real spawned-process contention for desktop and owned recovery publication."""
from __future__ import annotations

import json
import multiprocessing
import tempfile
import time
import unittest
from pathlib import Path

from app.gui.shared.allocation_persistence import (
    AllocationSnapshotSession,
    get_position_allocations_path,
    load_position_allocations,
    save_position_allocations,
)
from app.integrations.exchanges.binance.orders.order_intent_store import (
    LOCK_TIMEOUT_SECONDS,
    ledger_transaction,
)


def _hold_transaction(path, ready, release):
    with ledger_transaction(Path(path)):
        ready.set()
        if not release.wait(30):
            raise RuntimeError("parent failed to release test barrier")


def _racing_window(this_file, token, ready, publish, results):
    session = AllocationSnapshotSession()
    allocations, records = load_position_allocations(this_file=Path(this_file), mode="Live", session=session)
    ready.set()
    if not publish.wait(30):
        raise RuntimeError("parent failed to release publisher barrier")
    allocations[("BTCUSDT", "L")] = [{"qty": 0.1, "data": {"window": token}}]
    result = save_position_allocations(allocations, records, this_file=Path(this_file), mode="Live", session=session)
    results.put((token, result))


class AllocationProcessTransactionsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.this_file = Path(self.temp.name) / "Languages" / "Python" / "app" / "gui" / "shell.py"
        self.this_file.parent.mkdir(parents=True)
        self.path = get_position_allocations_path(self.this_file)
        self.context = multiprocessing.get_context("spawn")

    def hold(self, path):
        ready, release = self.context.Event(), self.context.Event()
        process = self.context.Process(target=_hold_transaction, args=(str(path), ready, release))
        process.start()
        self.assertTrue(ready.wait(15), "spawned process did not acquire the real transaction")
        return process, release

    def finish(self, process, release):
        release.set()
        process.join(15)
        if process.is_alive():
            process.terminate()
            process.join(5)
            self.fail("spawned process failed to release transaction")
        self.assertEqual(0, process.exitcode)

    def test_real_recovery_lock_busy_blocks_save_with_unchanged_five_second_bound(self):
        session = AllocationSnapshotSession()
        load_position_allocations(this_file=self.this_file, mode="Live", session=session)
        self.assertTrue(save_position_allocations({}, {}, this_file=self.this_file, mode="Live", session=session))
        original = self.path.read_bytes()
        receipt = (session._bytes, session._identity)
        process, release = self.hold(self.path)
        try:
            started = time.monotonic()
            self.assertFalse(save_position_allocations(
                {("BTCUSDT", "L"): [{"qty": 0.1}]}, {}, this_file=self.this_file, mode="Live", session=session,
            ))
            elapsed = time.monotonic() - started
            self.assertEqual(5.0, LOCK_TIMEOUT_SECONDS)
            self.assertGreaterEqual(elapsed, 4.8)
            self.assertLess(elapsed, 8.0)
            self.assertEqual(original, self.path.read_bytes())
            self.assertEqual(receipt, (session._bytes, session._identity))
        finally:
            self.finish(process, release)
        self.assertFalse(session.ready)
        load_position_allocations(this_file=self.this_file, mode="Live", session=session)
        self.assertTrue(save_position_allocations(
            {("BTCUSDT", "L"): [{"qty": 0.1}]}, {}, this_file=self.this_file, mode="Live", session=session,
        ))

    def test_real_canonical_recovery_lock_blocks_legacy_migration_before_publication(self):
        legacy = self.path.parent.parent / self.path.name
        raw = b'{"version":1,"mode":"Live","entry_allocations":{},"open_position_records":{}}'
        legacy.write_bytes(raw)
        process, release = self.hold(self.path)
        session = AllocationSnapshotSession()
        try:
            self.assertEqual(({}, {}), load_position_allocations(this_file=self.this_file, mode="Live", session=session))
            self.assertFalse(session.ready)
            self.assertFalse(self.path.exists())
            self.assertEqual(raw, legacy.read_bytes())
        finally:
            self.finish(process, release)
        self.assertEqual(({}, {}), load_position_allocations(this_file=self.this_file, mode="Live", session=session))
        self.assertTrue(session.ready)
        self.assertTrue(self.path.exists())
        self.assertFalse(legacy.exists())

    def test_two_real_windows_publish_one_cas_winner_without_lost_update(self):
        self.assertTrue(save_position_allocations({}, {}, this_file=self.this_file, mode="Live"))
        publish, results = self.context.Event(), self.context.Queue()
        ready = [self.context.Event(), self.context.Event()]
        processes = [self.context.Process(
            target=_racing_window, args=(str(self.this_file), token, barrier, publish, results),
        ) for token, barrier in zip(("A", "B"), ready, strict=True)]
        for process in processes:
            process.start()
        try:
            self.assertTrue(all(barrier.wait(15) for barrier in ready))
            publish.set()
            outcome = [results.get(timeout=15), results.get(timeout=15)]
            self.assertEqual([False, True], sorted(result for _, result in outcome))
            winner = next(token for token, result in outcome if result)
            self.assertEqual(winner, json.loads(self.path.read_text())["entry_allocations"]["BTCUSDT:L"][0]["data"]["window"])
        finally:
            publish.set()
            for process in processes:
                process.join(15)
                if process.is_alive():
                    process.terminate()
                    process.join(5)
                self.assertEqual(0, process.exitcode)
            results.close()


if __name__ == "__main__":
    unittest.main()
