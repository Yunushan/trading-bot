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
        checkpoints = []
        def mutate_detached_checkpoint(snapshot):
            checkpoints.append(json.loads(json.dumps(snapshot)))
            snapshot["completed"] = False
            snapshot["workload"]["expected_gets_per_refresh"].clear()
            snapshot.get("warm_sql_traffic", {}).clear()
        with tempfile.TemporaryDirectory(prefix=TEMP_PREFIX) as directory:
            result = benchmark.benchmark_indexed(
                Path(directory), 8, samples=1, original_stops=1, residual_stops=1,
                attempt_depth=1, residual_depth=1, concurrent_rounds=1,
                checkpoint=mutate_detached_checkpoint,
            )
        pending = next(row for row in checkpoints if row["final_audit"] == "running")
        self.assertFalse(pending["completed"])
        self.assertIsNone(pending["history_preserved"])
        self.assertIsNone(pending["historical_ids_preserved"])
        self.assertIsNone(pending["store_id_preserved"])
        self.assertEqual(pending["warm_latencies"], result["warm_latencies"])
        self.assertEqual(pending["warm_sql_traffic"], result["warm_sql_traffic"])
        self.assertEqual(result, checkpoints[-1])
        self.assertEqual("completed", result["final_audit"])
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

    def test_actual_warm_checkpoint_survives_final_audit_failure(self):
        for failure in ("read", "get_count"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory(
                prefix="trading-bot-indexed-capacity-evidence-test-",
            ) as directory:
                evidence = Path(directory)
                original_mkdtemp = tempfile.mkdtemp
                original_report, original_read = benchmark._atomic_report, benchmark.runtime._read_ledger
                original_owner = benchmark._CapacityOwner
                pending, actual_owners = [], []
                def owned_directory(*args, **kwargs):
                    if kwargs.get("prefix") == "trading-bot-indexed-capacity-evidence-":
                        return directory
                    return original_mkdtemp(*args, **kwargs)
                def capture_actual_owner(records):
                    owner = original_owner(records)
                    actual_owners.append(owner)
                    return owner
                def persist_and_observe(path, report):
                    original_report(path, report)
                    if report.get("result", {}).get("final_audit") == "running":
                        row = json.loads(path.read_text(encoding="utf-8"))["result"]
                        pending.append(row)
                        if failure == "get_count" and row["history_preserved"] is True:
                            actual_owners[0].client.calls["get_order"] += 1
                def fail_final_read(*args, **kwargs):
                    if failure == "read" and pending:
                        raise AssertionError("synthetic final audit read failure")
                    return original_read(*args, **kwargs)
                with (patch.object(benchmark.tempfile, "mkdtemp", side_effect=owned_directory),
                      patch.object(benchmark.baseline, "source_identity", return_value={"synthetic": True}),
                      patch.object(benchmark.baseline, "hardware_identity", return_value={"ram_available_bytes": None}),
                      patch.object(benchmark, "_CapacityOwner", side_effect=capture_actual_owner),
                      patch.object(benchmark, "_atomic_report", side_effect=persist_and_observe),
                      patch.object(benchmark.runtime, "_read_ledger", side_effect=fail_final_read)):
                    status = benchmark.main([
                        "--records", "8", "--samples", "1", "--original-stops", "1", "--residual-stops", "1",
                        "--attempt-depth", "1", "--residual-depth", "1", "--concurrent-rounds", "1",
                    ])
                report = json.loads((evidence / "report.json").read_text(encoding="utf-8"))
                checkpoint = json.loads((evidence / "workload-001-8.json").read_text(encoding="utf-8"))
                self.assertFalse(any(evidence.glob("*.tmp")))
                self.assertEqual(status, 1)
                self.assertEqual(1 if failure == "read" else 2, len(pending))
                self.assertEqual("running", pending[0]["final_audit"])
                self.assertFalse(pending[0]["completed"])
                self.assertGreater(pending[0]["warm_sql_traffic"]["sql_calls"], 0)
                self.assertEqual(5, len(pending[0]["warm_latencies"]))
                self.assertEqual(2, len(pending[0]["paired_contention"]))
                failed = report["results"][0]
                for key in ("offline_migration_ms", "full_startup_ms", "warm_latencies", "warm_sql_traffic",
                            "warm_sql_traffic_by_operation", "paired_contention", "active_stop_get_totals"):
                    self.assertEqual(pending[0][key], failed[key], key)
                for key in ("history_preserved", "historical_ids_preserved", "store_id_preserved"):
                    self.assertIsNone(pending[0][key])
                    if failure == "read":
                        self.assertIsNone(failed[key])
                    else:
                        self.assertTrue(pending[-1][key])
                        self.assertTrue(failed[key])
                self.assertEqual("failed", failed["final_audit"])
                self.assertEqual("final_audit", failed["failed_stage"])
                self.assertFalse(failed["completed"])
                self.assertEqual("AssertionError", failed["error_type"])
                self.assertIn("synthetic final audit read failure" if failure == "read" else
                              "omitted an exact active-stop GET", failed["error"])
                self.assertEqual(failed, checkpoint["result"])
                self.assertTrue(report["source_unchanged"])
                self.assertTrue(checkpoint["source_unchanged"])

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
