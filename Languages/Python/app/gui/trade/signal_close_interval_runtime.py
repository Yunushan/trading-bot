from __future__ import annotations

import copy

from . import signal_common_runtime
from .signal_close_allocations_runtime import _consume_closed_entries, _restore_survivor_snapshot
from .signal_close_records_runtime import _record_closed_position


def _handle_close_interval_event(
    self,
    order_info: dict,
    ctx: dict,
    *,
    alloc_map,
    pending_close,
    max_closed_history: int,
    resolve_trigger_indicators,
    normalize_trigger_actions_map,
    save_position_allocations,
) -> None:
    try:
        if hasattr(self, "_track_interval_close"):
            self._track_interval_close(ctx["sym"], ctx["side_key"], ctx["interval"])
    except Exception:
        pass

    normalized_interval = signal_common_runtime._normalize_interval(self, ctx["interval"])
    close_time_val_evt = order_info.get("time")
    dt_close_evt = self._parse_any_datetime(close_time_val_evt) if close_time_val_evt else None
    close_time_fmt_evt = self._format_display_time(dt_close_evt) if dt_close_evt else close_time_val_evt
    ledger_id_evt = str(order_info.get("ledger_id") or "").strip()

    qty_reported_evt = signal_common_runtime._safe_float(order_info.get("qty") or order_info.get("executed_qty"))
    if qty_reported_evt is not None:
        qty_reported_evt = abs(qty_reported_evt)
    qty_tol_evt = 1e-9

    entries = alloc_map.get((ctx["sym_upper"], ctx["side_key"]), [])
    if isinstance(entries, dict):
        entries = list(entries.values())

    closed_snapshots: list[dict] = []
    survivors: list[dict] = []
    matched_by_ledger = False
    if isinstance(entries, list):
        closed_snapshots, survivors, _, matched_by_ledger = _consume_closed_entries(
            entries,
            qty_remaining=qty_reported_evt,
            qty_tol=qty_tol_evt,
            close_time_fmt=close_time_fmt_evt,
            matcher=lambda entry: (
                bool(str(entry.get("ledger_id") or "").strip())
                and str(entry.get("ledger_id") or "").strip() == ledger_id_evt
            )
            if ledger_id_evt
            else (
                normalized_interval is None
                or signal_common_runtime._normalize_interval(
                    self,
                    entry.get("interval") or entry.get("interval_display"),
                )
                == normalized_interval
            ),
        )

    if ledger_id_evt and not matched_by_ledger and isinstance(entries, list):
        closed_snapshots, survivors, _, _ = _consume_closed_entries(
            entries,
            qty_remaining=qty_reported_evt,
            qty_tol=qty_tol_evt,
            close_time_fmt=close_time_fmt_evt,
            matcher=lambda entry: (
                normalized_interval is None
                or signal_common_runtime._normalize_interval(
                    self,
                    entry.get("interval") or entry.get("interval_display"),
                )
                == normalized_interval
            ),
        )

    if survivors:
        alloc_map[(ctx["sym_upper"], ctx["side_key"])] = survivors
    else:
        alloc_map.pop((ctx["sym_upper"], ctx["side_key"]), None)

    if not closed_snapshots and survivors:
        _restore_survivor_snapshot(
            self,
            ctx,
            survivors,
            interval=ctx["interval"],
            normalized_interval=normalized_interval,
            pending_close=pending_close,
            save_position_allocations=save_position_allocations,
            resolve_trigger_indicators=resolve_trigger_indicators,
            normalize_trigger_actions_map=normalize_trigger_actions_map,
        )
        return

    signal_common_runtime._persist_trade_allocations(self, save_position_allocations)

    if ctx["sym_upper"]:
        recorded = _record_closed_position(
            self,
            order_info,
            ctx,
            closed_snapshots=closed_snapshots,
            max_closed_history=max_closed_history,
        )
        if not recorded:
            return

    try:
        pending_close.pop((ctx["sym_upper"], ctx["side_key"]), None)
    except Exception:
        pass

    if ctx["sym_upper"]:
        if survivors:
            try:
                seed = copy.deepcopy(survivors[0]) if survivors else {}
            except Exception:
                seed = survivors[0] if survivors else {}
            try:
                seed_interval = seed.get("interval_display") or seed.get("interval") or ctx["interval"]
                seed_norm_iv = signal_common_runtime._normalize_interval(self, seed_interval) or normalized_interval
                seed_open_time = seed.get("open_time")
                signal_common_runtime._sync_open_position_snapshot(
                    self,
                    ctx["sym_upper"],
                    ctx["side_key"],
                    survivors,
                    seed if isinstance(seed, dict) else None,
                    seed_interval,
                    seed_norm_iv,
                    seed_open_time,
                    resolve_trigger_indicators=resolve_trigger_indicators,
                    normalize_trigger_actions_map=normalize_trigger_actions_map,
                )
            except Exception:
                pass
        else:
            try:
                getattr(self, "_open_position_records", {}).pop((ctx["sym_upper"], ctx["side_key"]), None)
            except Exception:
                pass
            try:
                getattr(self, "_position_missing_counts", {}).pop((ctx["sym_upper"], ctx["side_key"]), None)
            except Exception:
                pass

    try:
        guard_obj = getattr(self, "guard", None)
        if guard_obj and hasattr(guard_obj, "mark_closed") and ctx["sym_upper"]:
            side_norm = "BUY" if ctx["side_key"] == "L" else "SELL"
            guard_obj.mark_closed(ctx["sym_upper"], ctx["interval"], side_norm)
    except Exception:
        pass

    signal_common_runtime._refresh_trade_views(self, ctx["sym"])


__all__ = ["_handle_close_interval_event"]
