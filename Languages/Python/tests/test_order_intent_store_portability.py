"""Exercise real filesystem primitives without importing exchange SDKs."""
from __future__ import annotations

import importlib.util
import json
import multiprocessing
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Binance's package initializer loads optional SDKs; this suite targets only storage.
SPEC = importlib.util.spec_from_file_location(
    "order_intent_store_portability",
    ROOT / "app/integrations/exchanges/binance/orders/order_intent_store.py",
)
store = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(store)


def _increment(directory, barrier):
    path = Path(directory) / "nested" / "ledger.json"
    barrier.wait(timeout=20)
    for _ in range(8):
        with store.ledger_transaction(path):
            payload = json.loads(path.read_text()) if path.exists() else {"count": 0}
            payload["count"] += 1
            store.write_ledger(path, payload)


class OrderIntentStorePortabilityTests(unittest.TestCase):
    def test_process_transactions_preserve_every_update(self):
        context = multiprocessing.get_context("spawn")
        with tempfile.TemporaryDirectory() as directory:
            barrier = context.Barrier(3)
            processes = [context.Process(target=_increment, args=(directory, barrier)) for _ in range(3)]
            try:
                for process in processes:
                    process.start()
                for process in processes:
                    process.join(timeout=30)
                    self.assertEqual(0, process.exitcode)
                path = Path(directory) / "nested" / "ledger.json"
                self.assertEqual({"count": 24}, json.loads(path.read_text()))
                self.assertEqual([], list(path.parent.glob("*.tmp")))
                if os.name != "nt":
                    self.assertEqual(0o600, path.stat().st_mode & 0o777)
            finally:
                for process in processes:
                    if process.is_alive():
                        process.terminate()
                    if process.pid is not None:
                        process.join(timeout=10)


if __name__ == "__main__":
    unittest.main()
