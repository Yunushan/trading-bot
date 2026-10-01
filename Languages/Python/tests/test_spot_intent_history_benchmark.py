"""Small real-store regressions for the disposable capacity measurement tool."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
import socket
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.settings.live_safety import LiveTradingSafetyError

TOOL_PATH = Path(__file__).resolve().parents[1] / "tools" / "benchmark_spot_intent_history.py"
SPEC = importlib.util.spec_from_file_location("spot_intent_history_benchmark", TOOL_PATH)
assert SPEC is not None and SPEC.loader is not None
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


class SpotIntentHistoryBenchmarkTests(unittest.TestCase):
    def test_opo_heavy_profile_validates_nested_history_and_refreshes_every_active_generation(self):
        with tempfile.TemporaryDirectory(prefix=benchmark.TEMP_PREFIX) as temporary:
            root = Path(temporary)
            with patch.object(Path, "home", side_effect=AssertionError("Real user home must not be inspected")):
                result = benchmark.benchmark_history(
                    root, 20, samples=2, warmup=1, unresolved_count=0, concurrent_rounds=1,
                    profile="opo-heavy", original_stops=2, residual_stops=2, attempt_depth=3, residual_depth=2,
                )
            self.assertEqual("opo-heavy", result["profile"])
            self.assertEqual(0, result["unresolved_count"])
            self.assertTrue(result["immutable_history_preserved_except_observation_clocks"])
            self.assertTrue(result["nested_client_ids_preserved"])
            self.assertTrue(result["refresh_includes_real_cas_and_atomic_publication"])
            self.assertEqual("sequential; separate from reader/writer contention", result["refresh_measurement_scope"])
            self.assertFalse(result["concurrency"]["includes_active_stop_refresh"])
            self.assertEqual([], result["concurrency"]["failures"])
            self.assertEqual(4, result["opo_workload"]["active_stop_count"])
            self.assertEqual(4, result["opo_workload"]["archived_residual_stop_count"])
            self.assertEqual([{"get_order_list": 2, "get_order": 6}] * 3,
                             result["refresh_get_cardinality_per_invocation"])
            self.assertEqual({"get_order_list": 6, "get_order": 18}, result["refresh_get_totals"])
            payload = json.loads(next(root.rglob("order_intents.json")).read_text(encoding="utf-8"))
            used_ids = benchmark.profiles.used_spot_client_order_ids(payload["intents"])
            self.assertIn("syn-exit-00000000-000", used_ids)
            self.assertIn(benchmark.profiles.spot_opo_cancel_client_id("syn-exit-00000000-000"), used_ids)
            self.assertIn(benchmark.profiles.spot_opo_cancel_client_id("syn-exit-00000000-003"), used_ids)
            self.assertIn("syn-rearm-00000002-000", used_ids)
            self.assertIn("syn-rearm-00000002-002", used_ids)
            self.assertFalse(any(benchmark.runtime._is_unresolved(record) for record in payload["intents"].values()))

    def test_canonical_opo_generator_rejects_tampered_archives_via_real_ledger_validator(self):
        with tempfile.TemporaryDirectory(prefix=benchmark.TEMP_PREFIX) as temporary:
            path = Path(temporary) / "ledger.json"
            records, _ = benchmark.profiles.synthetic_opo_records(
                8, original_stops=1, residual_stops=1, attempt_depth=2, residual_depth=2,
            )
            payload = {**benchmark.synthetic_payload(8, 1), "intents": records}
            with benchmark.store.ledger_transaction(path):
                benchmark.store.write_ledger(path, payload)
                benchmark.runtime._read_ledger(path, expected_binding=payload["binding"])
                payload["intents"]["syn-list-00000000"]["strategy_exit_history"][0][
                    "strategy_exit_request_signature"
                ] = "0" * 64
                benchmark.store.write_ledger(path, payload)
                with self.assertRaisesRegex(LiveTradingSafetyError, "no-effect"):
                    benchmark.runtime._read_ledger(path, expected_binding=payload["binding"])

    def test_maximum_bounded_attempt_and_rearm_histories_are_canonical_and_globally_unique(self):
        with tempfile.TemporaryDirectory(prefix=benchmark.TEMP_PREFIX) as temporary:
            path = Path(temporary) / "ledger.json"
            records, metadata = benchmark.profiles.synthetic_opo_records(
                2, original_stops=1, residual_stops=1, attempt_depth=100, residual_depth=100,
            )
            payload = {**benchmark.synthetic_payload(2, 1), "intents": records}
            with benchmark.store.ledger_transaction(path):
                benchmark.store.write_ledger(path, payload)
                loaded = benchmark.runtime._read_ledger(path, expected_binding=payload["binding"])
            self.assertEqual(200, metadata["archived_exit_attempt_count"])
            self.assertEqual(100, metadata["archived_residual_stop_count"])
            self.assertEqual(2, metadata["current_cancel_alias_count"])
            self.assertEqual(200, metadata["archived_cancel_alias_count"])
            self.assertEqual(511, metadata["globally_used_client_id_count"])
            used_ids = benchmark.profiles.used_spot_client_order_ids(loaded["intents"])
            self.assertEqual(511, len(used_ids))
            for record in loaded["intents"].values():
                requests = [record["strategy_exit_request"], *[
                    prior["strategy_exit_request"] for prior in record["strategy_exit_history"]
                ]]
                for request in requests:
                    alias = benchmark.profiles.spot_opo_cancel_client_id(request["newClientOrderId"])
                    self.assertEqual(alias, request["cancelNewClientOrderId"])
                    self.assertIn(alias, used_ids)
            residual = loaded["intents"]["syn-list-00000001"]
            self.assertEqual(residual["strategy_exit_request"]["cancelNewClientOrderId"],
                             residual["pending_observed_client_order_id"])
            self.assertNotIn("pending_observed_client_order_id", loaded["intents"]["syn-list-00000000"])

    def test_immutable_history_digest_excludes_only_declared_observation_clocks(self):
        records, _ = benchmark.profiles.synthetic_opo_records(
            2, original_stops=1, residual_stops=1, attempt_depth=2, residual_depth=2,
        )
        mutable_ids = set(records)
        initial = benchmark.profiles.immutable_history_digest(records, mutable_client_ids=mutable_ids)
        records["syn-list-00000000"]["updated_at"] = "2026-02-01T00:00:00+00:00"
        self.assertEqual(initial, benchmark.profiles.immutable_history_digest(records, mutable_client_ids=mutable_ids))
        records["syn-list-00000000"]["strategy_exit_history"][0]["strategy_exit_started_at"] = (
            "2026-02-01T00:00:00+00:00"
        )
        self.assertNotEqual(initial, benchmark.profiles.immutable_history_digest(records, mutable_client_ids=mutable_ids))

    def test_refresh_fails_closed_when_exact_observation_cannot_be_applied(self):
        with tempfile.TemporaryDirectory(prefix=benchmark.TEMP_PREFIX) as temporary:
            with patch.object(benchmark.runtime, "_update_order_intent_by_id", return_value=None):
                with self.assertRaisesRegex(LiveTradingSafetyError, "Fresh exact Spot protection"):
                    benchmark.benchmark_history(
                        Path(temporary), 8, samples=1, warmup=0, unresolved_count=0, concurrent_rounds=0,
                        profile="opo-heavy", original_stops=1, residual_stops=1, attempt_depth=1, residual_depth=1,
                    )

    def test_refresh_does_not_accept_wrong_child_identity(self):
        original_getter = benchmark.profiles.SyntheticOpoVenue.get_order
        def wrong_child(venue, **kwargs):
            response = original_getter(venue, **kwargs)
            response["orderId"] += 1
            return response
        with tempfile.TemporaryDirectory(prefix=benchmark.TEMP_PREFIX) as temporary:
            with patch.object(benchmark.profiles.SyntheticOpoVenue, "get_order", wrong_child):
                with self.assertRaisesRegex(LiveTradingSafetyError, "Fresh exact Spot protection"):
                    benchmark.benchmark_history(
                        Path(temporary), 8, samples=1, warmup=0, unresolved_count=0, concurrent_rounds=0,
                        profile="opo-heavy", original_stops=1, residual_stops=1, attempt_depth=1, residual_depth=1,
                    )

    def test_main_profile_removes_synthetic_state_and_reports_source_mutation(self):
        actual_mkdtemp = tempfile.mkdtemp
        with tempfile.TemporaryDirectory(prefix=benchmark.TEMP_PREFIX) as temporary:
            root = Path(temporary) / "run"
            root.mkdir()
            before = {"head": "a" * 40, "file_sha256": {"runtime.py": "a" * 64}}
            after = {"head": "b" * 40, "file_sha256": {"runtime.py": "b" * 64}}
            def owned_run_root(*args, **kwargs):
                return str(root) if kwargs.get("prefix") == benchmark.TEMP_PREFIX else actual_mkdtemp(*args, **kwargs)
            with patch.object(benchmark.tempfile, "mkdtemp", side_effect=owned_run_root), patch.object(
                benchmark, "source_identity", side_effect=[before, after],
            ):
                result = benchmark.main([
                    "--profile", "opo-heavy", "--records", "8", "--samples", "1", "--warmup", "0",
                    "--active-original-stops", "1", "--active-residual-stops", "1",
                    "--attempt-history-depth", "1", "--residual-history-depth", "1", "--concurrent-rounds", "0",
                ])
            self.assertEqual(0, result)
            report = json.loads((root / "spot-intent-history-benchmark.json").read_text(encoding="utf-8"))
            self.assertFalse(report["measured_source_unchanged"])
            self.assertTrue(report["synthetic_state_removed"])
            self.assertFalse(report["production_acceptance"])
            self.assertIsNone(report["operator_latency_budgets"])
            self.assertIn("Active-stop refresh is measured sequentially, separately from reader/writer contention.",
                          report["limitations"])
            self.assertEqual([root / "spot-intent-history-benchmark.json"], list(root.iterdir()))

    def test_residual_history_resource_bounds_reject_before_synthetic_state_allocation(self):
        base_memory, base_disk = benchmark.resource_estimates(
            8, profile="opo-heavy", attempt_depth=0, residual_stops=1, residual_depth=0,
        )
        expected_memory, expected_disk = benchmark.resource_estimates(
            8, profile="opo-heavy", attempt_depth=0, residual_stops=1, residual_depth=100,
        )
        self.assertEqual(base_memory + 100 * 12_288, expected_memory)
        self.assertEqual(base_disk + 100 * 4096, expected_disk)
        actual_mkdtemp = tempfile.mkdtemp
        for budget in ("memory", "disk"):
            with self.subTest(budget=budget), tempfile.TemporaryDirectory(prefix=benchmark.TEMP_PREFIX) as temporary:
                root = Path(temporary) / "run"
                root.mkdir()
                def owned_run_root(*args, **kwargs):
                    return str(root) if kwargs.get("prefix") == benchmark.TEMP_PREFIX else actual_mkdtemp(*args, **kwargs)
                available_memory = (base_memory + 1) * 2 if budget == "memory" else 10**10
                free_disk = base_disk + 1 if budget == "disk" else 10**10
                with patch.object(benchmark.tempfile, "mkdtemp", side_effect=owned_run_root), patch.object(
                    benchmark, "source_identity", return_value={},
                ), patch.object(benchmark, "hardware_identity", return_value={"ram_available_bytes": available_memory}), patch.object(
                    benchmark.shutil, "disk_usage", return_value=SimpleNamespace(free=free_disk),
                ), patch.object(benchmark.tempfile, "TemporaryDirectory") as create_state, patch.object(
                    benchmark, "benchmark_history",
                ) as measure:
                    result = benchmark.main([
                        "--profile", "opo-heavy", "--records", "8", "--samples", "1", "--warmup", "0",
                        "--active-original-stops", "1", "--active-residual-stops", "1",
                        "--attempt-history-depth", "0", "--residual-history-depth", "100", "--concurrent-rounds", "0",
                    ])
                    create_state.assert_not_called()
                    measure.assert_not_called()
                self.assertEqual(0, result)
                report = json.loads((root / "spot-intent-history-benchmark.json").read_text(encoding="utf-8"))
                self.assertTrue(report["histories"][0]["skipped"])
                self.assertEqual(expected_memory, report["histories"][0]["estimated_memory_bytes"])
                self.assertEqual(expected_disk, report["histories"][0]["estimated_disk_bytes"])
                self.assertTrue(report["synthetic_state_removed"])
                self.assertEqual([root / "spot-intent-history-benchmark.json"], list(root.iterdir()))

    def test_failed_main_profile_cleans_state_and_socket_access_is_rejected(self):
        actual_mkdtemp = tempfile.mkdtemp
        with tempfile.TemporaryDirectory(prefix=benchmark.TEMP_PREFIX) as temporary:
            root = Path(temporary) / "run"
            root.mkdir()
            def fail_setup(*_args, **_kwargs):
                socket.create_connection(("127.0.0.1", 9))
            def owned_run_root(*args, **kwargs):
                return str(root) if kwargs.get("prefix") == benchmark.TEMP_PREFIX else actual_mkdtemp(*args, **kwargs)
            with patch.object(benchmark.tempfile, "mkdtemp", side_effect=owned_run_root), patch.object(
                benchmark, "source_identity", return_value={},
            ), patch.object(benchmark.profiles, "synthetic_opo_records", side_effect=fail_setup):
                with self.assertRaisesRegex(AssertionError, "offline"):
                    benchmark.main(["--profile", "opo-heavy", "--records", "8"])
            self.assertEqual([], list(root.iterdir()))

    def test_unconfined_or_nonempty_state_root_is_rejected_before_any_write(self):
        with tempfile.TemporaryDirectory(prefix="other-capacity-tool-") as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(ValueError, "owned"):
                benchmark.benchmark_history(root, 8, samples=1, warmup=0, unresolved_count=1, concurrent_rounds=0)
            self.assertEqual([], list(root.iterdir()))
        with tempfile.TemporaryDirectory(prefix=benchmark.TEMP_PREFIX) as temporary:
            root = Path(temporary)
            marker = root / "existing-state.txt"
            marker.write_text("retain me", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "empty"):
                benchmark.benchmark_history(root, 8, samples=1, warmup=0, unresolved_count=1, concurrent_rounds=0)
            self.assertEqual("retain me", marker.read_text(encoding="utf-8"))

    def test_opo_count_bounds_fail_before_creating_state(self):
        cases = [
            ["--active-original-stops", "-1"], ["--active-original-stops", "129"],
            ["--attempt-history-depth", "101"], ["--residual-history-depth", "101"],
            ["--records", "100000", "--attempt-history-depth", "4"], ["--unresolved-count", "1"],
            ["--records", "2"], ["--active-original-stops", "0", "--active-residual-stops", "0"],
        ]
        for case in cases:
            with self.subTest(case=case), patch.object(benchmark.tempfile, "mkdtemp") as create:
                with self.assertRaises(SystemExit) as raised:
                    benchmark.main(["--profile", "opo-heavy", *case])
                self.assertEqual(2, raised.exception.code)
                create.assert_not_called()

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
