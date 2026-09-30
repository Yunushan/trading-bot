"""Small real-store regressions for the disposable capacity measurement tool."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.settings.live_safety import LiveTradingSafetyError

TOOL_PATH = Path(__file__).resolve().parents[1] / "tools" / "benchmark_spot_intent_history.py"
SPEC = importlib.util.spec_from_file_location("spot_intent_history_benchmark", TOOL_PATH)
assert SPEC is not None and SPEC.loader is not None
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


class SpotIntentHistoryBenchmarkTests(unittest.TestCase):
    def test_actual_store_workload_preserves_history_and_unknown_tail_with_contention(self):
        with tempfile.TemporaryDirectory(prefix=benchmark.TEMP_PREFIX) as temporary:
            root = Path(temporary)
            with patch.object(Path, "home", side_effect=AssertionError("Real user home must not be inspected")):
                result = benchmark.benchmark_history(root, 40, samples=2, warmup=0,
                                                     unresolved_count=3, concurrent_rounds=2)
            self.assertEqual(40, result["record_count"])
            self.assertTrue(result["historical_ids_preserved"])
            self.assertTrue(result["binding_preserved"])
            self.assertTrue(result["store_id_preserved"])
            self.assertEqual([], result["concurrency"]["failures"])
            for measurement in result["latencies"].values():
                self.assertEqual(2, measurement["sample_count"])
                self.assertGreaterEqual(measurement["p99_ms"], measurement["p50_ms"])
            ledgers = list(root.rglob("order_intents.json"))
            self.assertEqual(1, len(ledgers))
            payload = json.loads(ledgers[0].read_text(encoding="utf-8"))
            unknown = [key for key, record in payload["intents"].items() if record["state"] == "unknown"]
            self.assertEqual([f"synthetic-history-{index:08d}" for index in range(37, 40)], unknown)

    def test_wrong_binding_and_corrupt_synthetic_record_are_rejected_by_real_validator(self):
        with tempfile.TemporaryDirectory(prefix=benchmark.TEMP_PREFIX) as temporary:
            path = Path(temporary) / "ledger.json"
            payload = benchmark.synthetic_payload(12, 2)
            with benchmark.store.ledger_transaction(path):
                benchmark.store.write_ledger(path, payload)
                with self.assertRaisesRegex(LiveTradingSafetyError, "different credentials"):
                    benchmark.runtime._read_ledger(path, expected_binding={**payload["binding"], "credential_fingerprint": "0" * 64})
                payload["intents"]["synthetic-history-00000000"]["state"] = "pretend-resolved"
                benchmark.store.write_ledger(path, payload)
                with self.assertRaisesRegex(LiveTradingSafetyError, "invalid record"):
                    benchmark.runtime._read_ledger(path, expected_binding=payload["binding"])

    def test_output_escape_and_oversized_workload_fail_before_creating_state(self):
        for argv in (["--output-name", "../escape.json"], ["--records", "100001"], ["--samples", "26"]):
            with self.subTest(argv=argv), patch.object(benchmark.tempfile, "mkdtemp") as create:
                with self.assertRaises(SystemExit) as raised:
                    benchmark.main(argv)
                self.assertEqual(2, raised.exception.code)
                create.assert_not_called()
        with tempfile.TemporaryDirectory(prefix=benchmark.TEMP_PREFIX) as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(ValueError, "inside"):
                benchmark.confined_path(root, root / ".." / "outside.json")


if __name__ == "__main__":
    unittest.main()
