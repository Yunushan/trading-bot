"""Measure the real JSON Spot intent store using disposable synthetic state only.

Run with the repository Python environment. All state is created under a named
system temporary directory; only the JSON measurement report remains afterwards.
This is capacity evidence, not an operator budget or production acceptance gate.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

PYTHON_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PYTHON_ROOT.parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.integrations.exchanges.binance.orders import order_intent_runtime as runtime  # noqa: E402
from app.integrations.exchanges.binance.orders import order_intent_store as store  # noqa: E402

MAX_RECORDS = 100_000
TEMP_PREFIX = "trading-bot-spot-intent-capacity-"
SYNTHETIC_UID = 900_000_021
SYNTHETIC_KEY = "synthetic-capacity-key-not-a-credential"
FIXED_TIME = "2026-01-01T00:00:00+00:00"


def confined_path(root: Path, path: Path) -> Path:
    """Reject paths outside the owned temporary tree, including symlink escapes."""
    root = root.resolve(strict=True)
    resolved = path.resolve()
    if resolved == root or root not in resolved.parents:
        raise ValueError("Synthetic state must stay inside its owned temporary directory.")
    for component in (path, *path.parents):
        if component == root:
            break
        if component.is_symlink():
            raise ValueError("Synthetic state paths must not contain symbolic links.")
    return resolved


def synthetic_owner() -> SimpleNamespace:
    # No secret, client, transport or credential-environment lookup is available.
    return SimpleNamespace(
        api_key=SYNTHETIC_KEY, mode="Live", account_type="SPOT",
        _enforce_spot_execution_owner=True, _operator_spot_account_uid=SYNTHETIC_UID,
    )


def synthetic_payload(count: int, unresolved_count: int) -> dict[str, Any]:
    if not 1 <= unresolved_count <= count <= MAX_RECORDS:
        raise ValueError("Require 1 <= unresolved count <= record count <= 100000.")
    owner = synthetic_owner()
    records = {}
    for index in range(count):
        client_id = f"synthetic-history-{index:08d}"
        side = "BUY" if index % 2 == 0 else "SELL"
        record = runtime._intent_record({
            "newClientOrderId": client_id, "symbol": "BTCUSDT", "side": side,
            "type": "MARKET", "quantity": "0.01",
        }, market="spot", source="synthetic-capacity-benchmark")
        record.update(created_at=FIXED_TIME, updated_at=FIXED_TIME, exchange_order_id=str(index + 1))
        if index >= count - unresolved_count:
            record.update(state="unknown", exchange_status="NEW", executed_qty="0")
        elif index % 5 == 0:
            record.update(state="rejected", exchange_status="EXPIRED", executed_qty="0")
        else:
            record.update(
                state="accepted", exchange_status="FILLED", executed_qty="0.01",
                portfolio_reconciled=True, portfolio_qty="0.01",
                portfolio_recovery_signature=hashlib.sha256(client_id.encode()).hexdigest(),
            )
        records[client_id] = record
    return {
        "format_version": runtime._INTENT_FORMAT_VERSION,
        "binding": runtime._intent_binding(owner),
        "store_id": "00000000-0000-4000-8000-000000000021",
        "created_at": FIXED_TIME, "intents": records,
    }


def latency_summary(samples: list[float]) -> dict[str, Any]:
    """Report nearest-rank quantiles; do not imply tail confidence from few samples."""
    ordered = sorted(samples)
    if not ordered:
        return {"sample_count": 0, "p50_ms": None, "p95_ms": None, "p99_ms": None, "max_ms": None}
    def quantile(fraction):
        return round(ordered[max(0, math.ceil(len(ordered) * fraction) - 1)] * 1000, 3)
    return {
        "sample_count": len(ordered), "p50_ms": quantile(0.50), "p95_ms": quantile(0.95),
        "p99_ms": quantile(0.99), "max_ms": round(max(ordered) * 1000, 3),
        "samples_ms": [round(value * 1000, 3) for value in samples],
    }


def source_identity() -> dict[str, Any]:
    def git(*args):
        result = subprocess.run(
            ["git", *args], cwd=REPOSITORY_ROOT, capture_output=True, text=True, timeout=10, check=True,
        )
        return result.stdout.strip()
    paths = (Path(runtime.__file__), Path(store.__file__), Path(__file__))
    return {
        "head": git("rev-parse", "HEAD"),
        "tracked_worktree_status": git("status", "--short", "--untracked-files=no"),
        "file_sha256": {
            path.relative_to(REPOSITORY_ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths
        },
    }


def hardware_identity() -> dict[str, Any]:
    result: dict[str, Any] = {
        "os": platform.platform(), "machine": platform.machine(), "processor": platform.processor(),
        "logical_cpus": os.cpu_count(), "python": sys.version, "implementation": platform.python_implementation(),
        "python_executable": sys.executable,
    }
    try:
        import psutil
        memory = psutil.virtual_memory()
        result.update(ram_total_bytes=memory.total, ram_available_bytes=memory.available,
                      physical_cpus=psutil.cpu_count(logical=False))
    except ImportError:
        result.update(ram_total_bytes=None, ram_available_bytes=None, physical_cpus=None)
    return result


def benchmark_history(root: Path, count: int, *, samples: int, warmup: int,
                      unresolved_count: int, concurrent_rounds: int) -> dict[str, Any]:
    """Caller owns an empty temporary root; network and home are patched locally."""
    home = confined_path(root, root / "synthetic-home")
    home.mkdir()
    owner = synthetic_owner()
    with ExitStack() as stack:
        stack.enter_context(patch.object(Path, "home", return_value=home))
        for method in ("connect", "connect_ex"):
            stack.enter_context(patch.object(socket.socket, method, side_effect=AssertionError("Benchmark is offline.")))
        stack.enter_context(patch.object(socket, "create_connection", side_effect=AssertionError("Benchmark is offline.")))
        path = confined_path(root, runtime._intent_path(owner))
        with store.ledger_transaction(path):
            store.write_ledger(path, synthetic_payload(count, unresolved_count))
        binding = runtime._intent_binding(owner)
        expected_ids = [f"synthetic-history-{index:08d}" for index in range(count - unresolved_count, count)]
        history_ids_digest = hashlib.sha256(
            "\n".join(f"synthetic-history-{index:08d}" for index in range(count)).encode()
        ).hexdigest()

        def read_validate():
            with store.ledger_transaction(path):
                payload = runtime._read_ledger(path, expected_binding=binding)
                intents = payload["intents"]
                assert isinstance(intents, dict)
                return len(intents)

        def unresolved_lookup():
            status = runtime.get_order_intent_status(owner)
            if status["intent_count"] != count or status["unresolved_client_order_ids"] != expected_ids:
                raise AssertionError("Synthetic history or unresolved identities changed.")

        def read_validate_rewrite():
            with store.ledger_transaction(path):
                payload = runtime._read_ledger(path, expected_binding=binding)
                intents = payload["intents"]
                assert isinstance(intents, dict)
                intents[expected_ids[-1]]["updated_at"] = datetime.now(timezone.utc).isoformat()
                store.write_ledger(path, payload)

        operations = {
            "locked_read_validate": read_validate,
            "unresolved_lookup_including_read_validate": unresolved_lookup,
            "locked_read_validate_fsync_atomic_rewrite": read_validate_rewrite,
        }
        timings = {}
        for name, operation in operations.items():
            for _ in range(warmup):
                operation()
            elapsed = []
            for _ in range(samples):
                started = time.perf_counter()
                operation()
                elapsed.append(time.perf_counter() - started)
            timings[name] = latency_summary(elapsed)

        concurrent: dict[str, Any] = {"same_process_threads": 2, "rounds": concurrent_rounds,
                      "lock_timeout_seconds": store.LOCK_TIMEOUT_SECONDS,
                      "includes_lock_wait": True, "failures": [], "operations": {}}
        concurrent_samples: dict[str, list[float]] = {"reader": [], "writer": []}
        def contender(role, barrier):
            barrier.wait(timeout=10)
            started = time.perf_counter()
            try:
                (unresolved_lookup if role == "reader" else read_validate_rewrite)()
                return role, time.perf_counter() - started, None
            except Exception as exc:
                return role, time.perf_counter() - started, {"type": type(exc).__name__, "message": str(exc)}
        with ThreadPoolExecutor(max_workers=2) as executor:
            for _ in range(concurrent_rounds):
                barrier = threading.Barrier(2)
                futures = [executor.submit(contender, role, barrier) for role in ("reader", "writer")]
                for future in futures:
                    role, elapsed, error = future.result(timeout=60)
                    if error is None:
                        concurrent_samples[role].append(elapsed)
                    else:
                        concurrent["failures"].append({"role": role, "elapsed_ms": elapsed * 1000, **error})
        concurrent["operations"] = {name: latency_summary(values) for name, values in concurrent_samples.items()}
        unresolved_lookup()
        with store.ledger_transaction(path):
            final = runtime._read_ledger(path, expected_binding=binding)
            final_intents = final["intents"]
            assert isinstance(final_intents, dict)
            final_digest = hashlib.sha256("\n".join(sorted(final_intents)).encode()).hexdigest()
            if final_digest != history_ids_digest:
                raise AssertionError("A benchmark rewrite changed historical client IDs.")
        result = {
            "record_count": count, "unresolved_count": unresolved_count, "ledger_size_bytes": path.stat().st_size,
            "warmup_per_operation": warmup, "latencies": timings, "concurrency": concurrent,
            "historical_ids_preserved": True, "binding_preserved": final["binding"] == binding,
            "store_id_preserved": final["store_id"] == "00000000-0000-4000-8000-000000000021",
        }
        del final
        gc.collect()
        return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=int, nargs="+", default=[10_000, 100_000])
    parser.add_argument("--samples", type=int, default=7)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--unresolved-count", type=int, default=10)
    parser.add_argument("--concurrent-rounds", type=int, default=3)
    parser.add_argument("--output-name", default="spot-intent-history-benchmark.json")
    args = parser.parse_args(argv)
    if (not 1 <= args.samples <= 25 or not 0 <= args.warmup <= 3 or not 0 <= args.concurrent_rounds <= 10
            or len(args.records) > 4 or len(set(args.records)) != len(args.records)
            or any(not 1 <= args.unresolved_count <= count <= MAX_RECORDS for count in args.records)):
        parser.error("Workload exceeds bounded records/samples/warmup/concurrency limits.")
    if Path(args.output_name).name != args.output_name or not args.output_name.endswith(".json"):
        parser.error("Output must be a single .json filename inside the owned temporary directory.")
    run_root = Path(tempfile.mkdtemp(prefix=TEMP_PREFIX)).resolve()
    report_path = confined_path(run_root, run_root / args.output_name)
    hardware = hardware_identity()
    source_before = source_identity()
    report: dict[str, Any] = {
        "schema_version": 1, "started_at": datetime.now(timezone.utc).isoformat(),
        "scope": "offline synthetic Spot JSON ledger capacity measurements",
        "production_acceptance": False, "operator_latency_budgets": None,
        "ledger_authentication": "none; JSON schema and SHA-256 credential-fingerprint binding only",
        "quantile_method": "nearest rank; p95/p99 from small samples are descriptive, not tail confidence",
        "hardware_runtime": hardware, "source_before": source_before,
        "temporary_output_directory": str(run_root),
        "workload": {"symbols": ["BTCUSDT"], "resolved_mix": "80% recovered MARKET BUY/SELL fills, 20% no-fill",
                     "unresolved_tail": "unknown MARKET BUY/SELL intents", "network": "socket connections rejected",
                     "cache": "warm filesystem cache; no cache eviction", "rewrite": "update one unresolved record timestamp",
                     "concurrency": "two threads, one reader/one writer; actual store serializes them"},
        "limitations": ["No slow/full-disk or physical power-loss simulation.",
                        "No OPO-heavy history, venue latency, urgent exit transport or multi-process contention measured.",
                        "Operator budgets and production workload remain unspecified."],
        "histories": [],
    }
    for count in args.records:
        # Conservative safety bound, not a latency or operator acceptance budget.
        estimated_memory = count * 16_384
        available_memory = hardware.get("ram_available_bytes")
        free_disk = shutil.disk_usage(run_root).free
        if (available_memory is not None and estimated_memory > available_memory // 2) or free_disk < count * 4096:
            report["histories"].append({"record_count": count, "skipped": True,
                                        "reason": "conservative memory/free-disk resource bound",
                                        "estimated_memory_bytes": estimated_memory, "free_disk_bytes": free_disk})
            continue
        print(f"Measuring {count} synthetic records...", flush=True)
        with tempfile.TemporaryDirectory(prefix="synthetic-state-", dir=run_root) as temporary:
            result = benchmark_history(Path(temporary), count, samples=args.samples, warmup=args.warmup,
                                       unresolved_count=args.unresolved_count, concurrent_rounds=args.concurrent_rounds)
            report["histories"].append(result)
    report["source_after"] = source_identity()
    report["measured_source_unchanged"] = report["source_before"]["file_sha256"] == report["source_after"]["file_sha256"]
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["synthetic_state_removed"] = not any(run_root.glob("synthetic-state-*"))
    report_path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"report_path": str(report_path), "histories": report["histories"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
