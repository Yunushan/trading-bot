"""Measure actual indexed admission callers in owned offline synthetic state.

Reports descriptive timings and logical SQL traffic, never production budgets.
The unchanged live strategy route remains disabled. No venue order is submitted.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import socket
import sys
import shutil
import tempfile
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

from app.settings.live_safety import LiveTradingSafetyError
from app.gui.shared import allocation_persistence
from app.integrations.exchanges.binance.orders.spot_inventory_namespace_runtime import namespace_for_owner
from app.integrations.exchanges.binance.orders import order_intent_runtime as runtime
from app.integrations.exchanges.binance.orders import order_intent_store as locks
from app.integrations.exchanges.binance.orders import spot_indexed_intent_store as backend
from app.integrations.exchanges.binance.orders.spot_indexed_intent_hot_runtime import indexed_admission_view
from app.integrations.exchanges.binance.orders.spot_indexed_intent_selective import close_indexed_session
from app.integrations.exchanges.binance.orders.order_intent_provisioning import (
    PROVISION_ACK, provision_order_intent_store, rearm_spot_execution_owner,
)
from app.integrations.exchanges.binance.orders.spot_indexed_intent_migration import migrate_spot_indexed_intent_store
from tools import benchmark_spot_intent_history as baseline
from tools import spot_intent_capacity_profiles as profiles


class _CapacityOwner:
    """Product intent methods and actual owner gate; synthetic signed-account/GET boundary."""
    def __init__(self, records: dict[str, Any]):
        self.api_key = baseline.SYNTHETIC_KEY
        self.api_secret = "synthetic-capacity-secret-not-a-credential"
        self.mode = "Live"
        self.account_type = "SPOT"
        self._enforce_spot_execution_owner = True
        self.client = profiles.SyntheticOpoVenue(records)

    def _http_signed_spot(self, endpoint: str):
        if endpoint != "/v3/account":
            raise AssertionError("Synthetic account boundary cannot submit orders.")
        return {"uid": baseline.SYNTHETIC_UID, "accountType": "SPOT"}


runtime.bind_binance_order_intent_runtime(_CapacityOwner)


def _bytes(values) -> int:
    return sum(len(value.encode("utf-8")) if isinstance(value, str) else len(value)
               if isinstance(value, bytes) else 0 for value in values)


class _Traffic:
    def __init__(self):
        self.values = {"sql_calls": 0, "returned_rows": 0, "returned_text_bytes": 0,
                       "write_parameter_text_bytes": 0, "full_ledger_reads": 0, "full_verifications": 0}
        self.original_sql = backend._sql

    def sql(self, connection, deadline, query, parameters=()):
        self.values["sql_calls"] += 1
        if query.startswith(("INSERT", "UPDATE", "DELETE")):
            self.values["write_parameter_text_bytes"] += _bytes(parameters)
        traffic = self
        cursor = self.original_sql(connection, deadline, query, parameters)

        class Cursor:
            def fetchone(self):
                row = cursor.fetchone()
                if row is not None:
                    traffic.values["returned_rows"] += 1
                    traffic.values["returned_text_bytes"] += _bytes(row)
                return row

            def fetchall(self):
                rows = cursor.fetchall()
                traffic.values["returned_rows"] += len(rows)
                traffic.values["returned_text_bytes"] += sum(_bytes(row) for row in rows)
                return rows
        return Cursor()

    def read(self, original, *args, **kwargs):
        self.values["full_ledger_reads"] += 1
        return original(*args, **kwargs)

    def verify(self, original, *args, **kwargs):
        self.values["full_verifications"] += 1
        return original(*args, **kwargs)


def _checkpoint(result: dict[str, Any], callback: Callable[[dict[str, Any]], None] | None) -> None:
    if callback is not None:
        callback(json.loads(json.dumps(result, allow_nan=False)))


def _atomic_report(path: Path, report: dict[str, Any]) -> None:
    raw = json.dumps(report, indent=2, allow_nan=False) + "\n"
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def benchmark_indexed(root: Path, count: int, *, samples: int = 3, original_stops: int = 2,
                      residual_stops: int = 2, attempt_depth: int = 3, residual_depth: int = 3,
                      concurrent_rounds: int = 2,
                      checkpoint: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    profiles.validate_opo_counts(count, original_stops, residual_stops, attempt_depth, residual_depth)
    if type(samples) is not int or not 1 <= samples <= 25 or type(concurrent_rounds) is not int or not 0 <= concurrent_rounds <= 10:
        raise ValueError("Bounded positive samples and concurrency rounds are required.")
    root = baseline.owned_temporary_root(root)
    home = root / "synthetic-home"
    home.mkdir()
    records, workload = profiles.synthetic_opo_records(
        count, original_stops=original_stops, residual_stops=residual_stops,
        attempt_depth=attempt_depth, residual_depth=residual_depth,
    )
    initial_ids = frozenset(records)
    active_ids = frozenset(runtime._active_spot_protection_records(records))
    immutable_digest = profiles.immutable_history_digest(records, mutable_client_ids=set(active_ids))
    used_ids = runtime.used_spot_client_order_ids(records)
    owner: Any = _CapacityOwner(records)  # Methods are bound by the actual product runtime.
    result: dict[str, Any] = {"record_count": count, "workload": workload,
                              "completed": False, "stage": "synthetic_setup", "final_audit": "not_started",
                              "history_preserved": None, "historical_ids_preserved": None, "store_id_preserved": None,
                              "post_write_proof": ("continuous native Windows SQLite share-deny guard and change receipt"
                                                   if sys.platform == "win32" else
                                                   "fresh complete verification within a pinned file-change receipt")}
    with ExitStack() as stack:
        stack.enter_context(patch.object(Path, "home", return_value=home))
        allocation_path = root / "synthetic-live-allocations.json"
        stack.enter_context(patch.object(allocation_persistence, "get_position_allocations_path",
                                        return_value=allocation_path))
        stack.enter_context(patch.object(allocation_persistence, "_get_allocations_file_path",
                                        return_value=allocation_path))
        for method in ("connect", "connect_ex"):
            stack.enter_context(patch.object(socket.socket, method, side_effect=AssertionError("Offline benchmark")))
        stack.enter_context(patch.object(socket, "create_connection", side_effect=AssertionError("Offline benchmark")))
        provision_order_intent_store(owner, acknowledgement=PROVISION_ACK)
        path = runtime._intent_path(owner)
        with locks.ledger_transaction(path):
            payload = runtime._read_ledger(path, expected_binding=runtime._intent_binding(owner))
            payload["intents"] = records
            locks.write_ledger(path, payload)
        source_size = path.stat().st_size
        original_store_id = payload["store_id"]
        result.update(source_json_bytes=source_size, stage="offline_migration")
        _checkpoint(result, checkpoint)
        started = time.perf_counter()
        cutover = migrate_spot_indexed_intent_store(
            owner, acknowledgement=PROVISION_ACK, reconciliation_reference="synthetic-indexed-capacity-cutover",
        )
        result["offline_migration_ms"] = (time.perf_counter() - started) * 1000
        result["stage"] = "offline_rearm"
        _checkpoint(result, checkpoint)
        rearm_spot_execution_owner(owner, acknowledgement=PROVISION_ACK,
                                  reconciliation_reference="synthetic-indexed-capacity-rearm")
        result["stage"] = "full_startup"
        _checkpoint(result, checkpoint)
        started = time.perf_counter()
        owner._ensure_spot_execution_owner()
        result["full_startup_ms"] = (time.perf_counter() - started) * 1000
        del records, payload
        gc.collect()
        try:
            # This offline fixture authors its synthetic inventory header explicitly;
            # product first-use bootstrap may not claim a nonempty historical ledger.
            inventory_namespace = namespace_for_owner(owner)
            _atomic_report(allocation_path, {"version": 1, "mode": "Live",
                                            "spot_account_namespace": inventory_namespace,
                                            "entry_allocations": {}, "open_position_records": {}})
            result["synthetic_inventory_namespace"] = inventory_namespace
            result["stage"] = "warm_measurement"
            _checkpoint(result, checkpoint)
            traffic = _Traffic()
            original_read, original_verify = runtime._read_ledger, backend._verified
            stack.enter_context(patch.object(backend, "_sql", side_effect=traffic.sql))
            stack.enter_context(patch.object(runtime, "_read_ledger",
                                            side_effect=lambda *a, **k: traffic.read(original_read, *a, **k)))
            stack.enter_context(patch.object(backend, "_verified",
                                            side_effect=lambda *a, **k: traffic.verify(original_verify, *a, **k)))
            record_id = sorted(active_ids)[0]
            samples_by_operation: dict[str, list[float]] = {}
            traffic_by_operation: dict[str, list[dict[str, int]]] = {}
            admission_ids: list[str] = []
            contention: list[dict[str, Any]] = []
            def report_measurements(stage):
                result.update(
                    stage=stage, warm_latencies={name: baseline.latency_summary(values)
                                                for name, values in samples_by_operation.items()},
                    warm_sql_traffic=dict(traffic.values), warm_sql_traffic_by_operation=traffic_by_operation,
                    paired_contention=contention,
                    active_stop_get_totals=dict(owner.client.calls), orders_submitted=0,
                )
                _checkpoint(result, checkpoint)
            def measure(name, function):
                before = dict(traffic.values)
                started = time.perf_counter()
                value = function()
                samples_by_operation.setdefault(name, []).append(time.perf_counter() - started)
                delta = {key: traffic.values[key] - before[key] for key in before}
                traffic_by_operation.setdefault(name, []).append(delta)
                if name == "warm_record_read" and (delta["full_ledger_reads"] or delta["full_verifications"]):
                    raise AssertionError("Read-only warm lookup performed a full history scan.")
                return value

            for iteration in range(samples):
                measure("warm_record_read", lambda: owner._get_order_intent_record(record_id))
                expected = owner._get_order_intent_record(record_id)
                measure("warm_record_cas", lambda: runtime._update_order_intent_by_id(
                    owner, record_id, state=expected["state"], expected_record=expected,
                    last_reconciliation_at=datetime.now(timezone.utc).isoformat(),
                ))
                proof = measure("warm_all_active_stop_refresh", lambda: runtime._refresh_spot_active_protection(owner))
                with locks.ledger_transaction(path):
                    view = indexed_admission_view(owner, path)
                    if view is None:
                        raise AssertionError("Actual indexed admission view is missing.")
                    view.assert_fresh(proof)
                if set(proof[1]) != active_ids:
                    raise AssertionError("Fresh refresh omitted an active stop.")
                request = profiles.request_for(profiles.MAX_RECORDS + iteration + 1)
                record = measure("warm_opo_begin_including_refresh", lambda: owner._begin_spot_opo_intent(
                    request, source="synthetic-indexed-capacity",
                ))
                admission_ids.append(record["client_order_id"])
                measure("warm_opo_submitted_including_refresh", lambda: owner._mark_spot_opo_submitted(
                    record["client_order_id"], via="synthetic-no-post",
                ))
                terminal_list_id = 10_000 + (profiles.MAX_RECORDS + iteration + 1) * 4
                runtime._update_order_intent_by_id(
                    owner, record["client_order_id"], state="rejected", protection_state="none",
                    exchange_order_list_id=terminal_list_id, list_status="ALL_DONE",
                    working_order_id=terminal_list_id + 1, pending_order_id=terminal_list_id + 2,
                    working_status="EXPIRED", pending_status="CANCELED", working_executed_qty="0",
                    pending_executed_qty="0", pending_original_qty="0",
                )

            report_measurements("paired_measurement")
            def contender(role, barrier):
                barrier.wait(timeout=10)
                started = time.perf_counter()
                try:
                    if role == "reader":
                        owner._get_order_intent_record(record_id)
                    else:
                        runtime._update_order_intent_by_id(
                            owner, record_id, state="accepted",
                            last_reconciliation_at=datetime.now(timezone.utc).isoformat(),
                        )
                except LiveTradingSafetyError as exc:
                    return {"role": role, "outcome": "fenced", "error": str(exc),
                            "elapsed_ms": (time.perf_counter() - started) * 1000}
                return {"role": role, "outcome": "completed",
                        "elapsed_ms": (time.perf_counter() - started) * 1000}
            with ThreadPoolExecutor(max_workers=2) as executor:
                for _ in range(concurrent_rounds):
                    barrier = threading.Barrier(2)
                    futures = [executor.submit(contender, role, barrier) for role in ("reader", "writer")]
                    contention.extend(future.result(timeout=1800) for future in futures)
            result["paired_operations_all_completed"] = all(row["outcome"] == "completed" for row in contention)
            report_measurements("warm_measurements_complete")
        finally:
            # Close the actual session before releasing the owner and checking the full backend.
            close_indexed_session(owner._spot_execution_owner)
            owner._spot_execution_owner.close()
        # Verification is intentionally outside the instrumented warm measurement.
        result.update(stage="final_audit", final_audit="running")
        _checkpoint(result, checkpoint)
        started = time.perf_counter()
        with locks.ledger_transaction(path):
            final = original_read(path, expected_binding=runtime._intent_binding(owner))
            final_records = final["intents"]
            originals = {key: row for key, row in final_records.items() if key in initial_ids}
            if (final["store_id"] != original_store_id or len(originals) != count
                    or set(final_records) != initial_ids | set(admission_ids)
                    or profiles.immutable_history_digest(originals, mutable_client_ids=set(active_ids)) != immutable_digest
                    or runtime.used_spot_client_order_ids(originals) != used_ids
                    or any(final_records[key]["state"] != "rejected" for key in admission_ids)):
                raise AssertionError("History, identifiers or synthetic terminal admissions changed.")
            result.update(history_preserved=True, historical_ids_preserved=True,
                          store_id_preserved=final["store_id"] == original_store_id)
        _checkpoint(result, checkpoint)
        expected_gets = {name: number * samples * 3 for name, number in workload["expected_gets_per_refresh"].items()}
        if owner.client.calls != expected_gets:
            raise AssertionError("An actual admission boundary omitted an exact active-stop GET.")
        result.update(source_json_bytes=source_size, database_bytes=Path(cast(str, cutover["database_path"])).stat().st_size,
                      active_stop_get_totals=dict(owner.client.calls), orders_submitted=0,
                      scope="actual product intent methods and owner gate with synthetic account and GET replies",
                      physical_io_measured=False, operator_budget_accepted=False, completed=True,
                      stage="completed", final_audit="completed", final_audit_ms=(time.perf_counter() - started) * 1000)
        _checkpoint(result, checkpoint)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=int, nargs="+", default=[10_000, 100_000])
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--original-stops", type=int, default=2)
    parser.add_argument("--residual-stops", type=int, default=2)
    parser.add_argument("--attempt-depth", type=int, default=3)
    parser.add_argument("--residual-depth", type=int, default=3)
    parser.add_argument("--concurrent-rounds", type=int, default=2)
    args = parser.parse_args(argv)
    for count in args.records:
        try:
            profiles.validate_opo_counts(count, args.original_stops, args.residual_stops,
                                         args.attempt_depth, args.residual_depth)
            if not 1 <= args.samples <= 25 or not 0 <= args.concurrent_rounds <= 10:
                raise ValueError("Bounded samples and concurrency rounds are required.")
        except ValueError as exc:
            parser.error(str(exc))
    evidence = Path(tempfile.mkdtemp(prefix="trading-bot-indexed-capacity-evidence-")).resolve()
    source = baseline.source_identity()
    source["indexed_benchmark_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    source["allocation_reader_sha256"] = hashlib.sha256(Path(allocation_persistence.__file__).read_bytes()).hexdigest()
    report = {"source": source, "hardware": baseline.hardware_identity(), "results": [],
              "samples_are_descriptive": True, "source_unchanged": None,
              "started_at": datetime.now(timezone.utc).isoformat()}
    report_path = evidence / "report.json"
    _atomic_report(report_path, report)
    for index, count in enumerate(args.records):
        checkpoint_path = evidence / f"workload-{index + 1:03d}-{count}.json"
        report["results"].append({"record_count": count, "completed": False, "stage": "resource_check",
                                  "final_audit": "not_started", "history_preserved": None,
                                  "historical_ids_preserved": None, "store_id_preserved": None})
        def checkpoint(snapshot):
            report["results"][index] = json.loads(json.dumps(snapshot, allow_nan=False))
            _atomic_report(checkpoint_path, {"source": source, "source_unchanged": report["source_unchanged"],
                                             "result": report["results"][index]})
            _atomic_report(report_path, report)
        checkpoint(report["results"][index])
        estimated_memory, estimated_disk = baseline.resource_estimates(
            count, profile="opo-heavy", attempt_depth=args.attempt_depth,
            residual_stops=args.residual_stops, residual_depth=args.residual_depth,
        )
        # Full source import and two physical SQLite record copies coexist.
        estimated_memory *= 2
        estimated_disk *= 4
        available_memory = baseline.hardware_identity().get("ram_available_bytes")
        free_disk = shutil.disk_usage(evidence).free
        if (available_memory is not None and estimated_memory > available_memory // 2) or free_disk < estimated_disk:
            row = report["results"][index]
            row.update(skipped=True, stage="skipped", reason="conservative memory/free-disk resource bound",
                       estimated_memory_bytes=estimated_memory, estimated_disk_bytes=estimated_disk,
                       ram_available_bytes=available_memory, free_disk_bytes=free_disk)
            checkpoint(row)
            continue
        print(json.dumps({"measuring_synthetic_records": count, "checkpoint": str(checkpoint_path),
                          "report": str(report_path)}), flush=True)
        try:
            with tempfile.TemporaryDirectory(prefix=baseline.TEMP_PREFIX) as directory:
                result = benchmark_indexed(
                    Path(directory), count, samples=args.samples, original_stops=args.original_stops,
                    residual_stops=args.residual_stops, attempt_depth=args.attempt_depth,
                    residual_depth=args.residual_depth, concurrent_rounds=args.concurrent_rounds,
                    checkpoint=checkpoint,
                )
                checkpoint(result)
        except (LiveTradingSafetyError, AssertionError, OSError) as exc:
            row = report["results"][index]
            row.update(completed=False, failed_stage=row["stage"], stage="failed",
                       error_type=type(exc).__name__, error=str(exc))
            if row["final_audit"] == "running":
                row["final_audit"] = "failed"
            checkpoint(row)
    final_source = baseline.source_identity()
    final_source["indexed_benchmark_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    final_source["allocation_reader_sha256"] = hashlib.sha256(Path(allocation_persistence.__file__).read_bytes()).hexdigest()
    report["source_unchanged"] = report["source"] == final_source
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    path = report_path
    for index, row in enumerate(report["results"]):
        _atomic_report(evidence / f"workload-{index + 1:03d}-{row['record_count']}.json",
                       {"source": source, "source_unchanged": report["source_unchanged"], "result": row})
    _atomic_report(path, report)
    completed = all(row.get("completed") for row in report["results"])
    print(json.dumps({"report": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                      "source_unchanged": report["source_unchanged"], "all_workloads_completed": completed}))
    return 0 if completed and report["source_unchanged"] else 1



if __name__ == "__main__":
    raise SystemExit(main())
