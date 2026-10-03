"""Offline indexed capacity evidence must preserve integrity and report failures."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import benchmark_spot_indexed_admission as benchmark
from tools.benchmark_spot_intent_history import TEMP_PREFIX


class IndexedCapacityBenchmarkTests(unittest.TestCase):
    def test_actual_callers_preserve_history_all_stops_and_report_write_proof(self):
        with tempfile.TemporaryDirectory(prefix=TEMP_PREFIX) as directory:
            result = benchmark.benchmark_indexed(
                Path(directory), 8, samples=1, original_stops=1, residual_stops=1,
                attempt_depth=1, residual_depth=1, concurrent_rounds=1,
            )
        self.assertTrue(result["completed"])
        self.assertTrue(result["history_preserved"])
        self.assertTrue(result["historical_ids_preserved"])
        self.assertTrue(result["store_id_preserved"])
        self.assertEqual(result["orders_submitted"], 0)
        self.assertEqual(result["active_stop_get_totals"], {"get_order_list": 3, "get_order": 9})
        self.assertFalse(result["operator_budget_accepted"])
        self.assertFalse(result["physical_io_measured"])
        self.assertTrue(result["paired_operations_all_completed"])
        read = result["warm_sql_traffic_by_operation"]["warm_record_read"][0]
        self.assertEqual(read["full_ledger_reads"], 0)
        self.assertEqual(read["full_verifications"], 0)
        if sys.platform == "win32":
            self.assertEqual(result["warm_sql_traffic"]["full_verifications"], 0)
        else:
            self.assertGreater(result["warm_sql_traffic"]["full_verifications"], 0)
            self.assertGreater(result["warm_sql_traffic_by_operation"]["warm_record_cas"][0]["full_verifications"], 0)

    def test_invalid_or_unowned_target_is_rejected_before_synthetic_state(self):
        with tempfile.TemporaryDirectory(prefix=TEMP_PREFIX) as directory:
            root = Path(directory)
            for options in ({"samples": 0}, {"concurrent_rounds": True}, {"original_stops": 0, "residual_stops": 0}):
                with self.subTest(options=options), self.assertRaises(ValueError):
                    benchmark.benchmark_indexed(root, 8, **options)
                self.assertEqual(list(root.iterdir()), [])
        with tempfile.TemporaryDirectory(prefix="unowned-indexed-probe-") as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                benchmark.benchmark_indexed(root, 8)
            self.assertEqual(list(root.iterdir()), [])

    def test_failed_probe_keeps_evidence_and_returns_failure(self):
        with tempfile.TemporaryDirectory(prefix="trading-bot-indexed-capacity-evidence-test-") as directory:
            evidence = Path(directory)
            original_mkdtemp = tempfile.mkdtemp
            def owned_directory(*args, **kwargs):
                if kwargs.get("prefix") == "trading-bot-indexed-capacity-evidence-":
                    return directory
                return original_mkdtemp(*args, **kwargs)
            with (patch.object(benchmark.tempfile, "mkdtemp", side_effect=owned_directory),
                  patch.object(benchmark.baseline, "source_identity", return_value={"synthetic": True}),
                  patch.object(benchmark.baseline, "hardware_identity", return_value={"ram_available_bytes": None}),
                  patch.object(benchmark, "benchmark_indexed", side_effect=AssertionError("synthetic integrity failure"))):
                status = benchmark.main(["--records", "8", "--samples", "1"])
            report = json.loads((evidence / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(status, 1)
        self.assertTrue(report["source_unchanged"])
        self.assertFalse(report["results"][0]["completed"])
        self.assertEqual(report["results"][0]["error_type"], "AssertionError")


if __name__ == "__main__":
    unittest.main()
