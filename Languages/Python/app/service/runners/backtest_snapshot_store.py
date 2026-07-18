"""Durable, sanitized snapshots for service-owned backtest sessions.

Backtests may be expensive, but automatically resuming one after a process
restart is unsafe: market data can change and an operator may have intended to
cancel it.  This store retains the latest observable result and turns an
interrupted running session into an explicit recovery state.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

from ..schemas.backtest import ServiceBacktestSnapshot, build_backtest_snapshot

BACKTEST_SNAPSHOT_FILE_KIND = "trading-bot-backtest-snapshot"
BACKTEST_SNAPSHOT_FORMAT_VERSION = 1
BACKTEST_SNAPSHOT_ENV_PATH = "BOT_BACKTEST_SNAPSHOT_PATH"


def resolve_backtest_snapshot_path(config_path: str | Path) -> Path:
    configured = str(os.environ.get(BACKTEST_SNAPSHOT_ENV_PATH) or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(config_path).expanduser().resolve().with_name("backtest-session.json")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_backtest_snapshot_file(snapshot: ServiceBacktestSnapshot, *, path: str | Path) -> dict[str, object]:
    resolved = Path(path).expanduser().resolve()
    payload = {
        "kind": BACKTEST_SNAPSHOT_FILE_KIND,
        "format_version": BACKTEST_SNAPSHOT_FORMAT_VERSION,
        "saved_at": _now_iso(),
        "snapshot": snapshot.to_dict(),
    }
    resolved.parent.mkdir(parents=True, exist_ok=True)
    temporary = resolved.with_name(f".{resolved.name}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(resolved)
    try:
        directory_fd = os.open(resolved.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError:
        # Windows and some network filesystems do not support directory fsync.
        pass
    try:
        os.chmod(resolved, 0o600)
    except OSError:
        pass
    return {"path": str(resolved), "saved_at": payload["saved_at"]}


def _snapshot_from_mapping(payload: Mapping[str, object]) -> ServiceBacktestSnapshot:
    return build_backtest_snapshot(
        session_id=str(payload.get("session_id") or ""),
        state=str(payload.get("state") or "idle"),
        workload_kind=str(payload.get("workload_kind") or "backtest-run"),
        status_message=str(payload.get("status_message") or "No backtest submitted yet."),
        symbols=payload.get("symbols"),
        intervals=payload.get("intervals"),
        indicator_keys=payload.get("indicator_keys"),
        logic=str(payload.get("logic") or ""),
        symbol_source=str(payload.get("symbol_source") or ""),
        capital=payload.get("capital"),
        run_count=payload.get("run_count"),
        error_count=payload.get("error_count"),
        cancelled=payload.get("cancelled"),
        started_at=str(payload.get("started_at") or ""),
        completed_at=str(payload.get("completed_at") or ""),
        updated_at=str(payload.get("updated_at") or ""),
        source=str(payload.get("source") or "service-backtest-executor"),
        top_run=payload.get("top_run"),
        runs=payload.get("runs"),
        top_runs=payload.get("top_runs"),
        errors=payload.get("errors"),
    )


def load_backtest_snapshot_file(path: str | Path) -> ServiceBacktestSnapshot | None:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        return None
    try:
        with resolved.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(payload, Mapping) or payload.get("kind") != BACKTEST_SNAPSHOT_FILE_KIND:
        return None
    if int(payload.get("format_version") or 0) != BACKTEST_SNAPSHOT_FORMAT_VERSION:
        return None
    raw_snapshot = payload.get("snapshot")
    if not isinstance(raw_snapshot, Mapping):
        return None
    snapshot = _snapshot_from_mapping(raw_snapshot)
    if snapshot.state not in {"running", "cancelling"}:
        return snapshot
    errors = [item.to_dict() for item in snapshot.errors]
    errors.append({"error": "Backtest session was interrupted by a service restart; resubmit it to run again."})
    return build_backtest_snapshot(
        session_id=snapshot.session_id,
        state="interrupted",
        workload_kind=snapshot.workload_kind,
        status_message="Backtest session interrupted by service restart. Review saved partial results before resubmitting.",
        symbols=snapshot.symbols,
        intervals=snapshot.intervals,
        indicator_keys=snapshot.indicator_keys,
        logic=snapshot.logic,
        symbol_source=snapshot.symbol_source,
        capital=snapshot.capital,
        run_count=snapshot.run_count,
        error_count=len(errors),
        cancelled=False,
        started_at=snapshot.started_at,
        completed_at=_now_iso(),
        updated_at=_now_iso(),
        source="service-backtest-recovery",
        runs=snapshot.runs,
        top_runs=snapshot.top_runs,
        errors=errors,
    )
