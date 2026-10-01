from __future__ import annotations

import copy

from app.gui.positions.actions_state_runtime import (
    _allocation_is_active,
    sync_local_position_tracking_from_allocations,
)

from . import signal_common_runtime
from .signal_close_allocations_runtime import _consume_closed_entries, _restore_survivor_snapshot
from .signal_close_records_runtime import _close_event_key, _record_closed_position


def _apply_close_interval_event(
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
) -> bool:
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
        closed_snapshots, survivors, remaining_qty, matched_by_ledger = _consume_closed_entries(
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

    else:
        return False
    if (ledger_id_evt and not matched_by_ledger) or (remaining_qty is not None and remaining_qty > qty_tol_evt):
        return False

    if survivors:
        alloc_map[(ctx["sym_upper"], ctx["side_key"])] = survivors
    else:
        alloc_map.pop((ctx["sym_upper"], ctx["side_key"]), None)
    active_survivors = [entry for entry in survivors if _allocation_is_active(entry)]

    if not closed_snapshots and active_survivors:
        return _restore_survivor_snapshot(
            self,
            ctx,
            active_survivors,
            interval=ctx["interval"],
            normalized_interval=normalized_interval,
            pending_close=pending_close,
            save_position_allocations=save_position_allocations,
            resolve_trigger_indicators=resolve_trigger_indicators,
            normalize_trigger_actions_map=normalize_trigger_actions_map,
        )
    if not closed_snapshots:
        return False

    if ctx["sym_upper"]:
        recorded = _record_closed_position(
            self,
            order_info,
            ctx,
            closed_snapshots=closed_snapshots,
            max_closed_history=max_closed_history,
            notify=False,
        )
        if not recorded:
            return False

    try:
        pending_close.pop((ctx["sym_upper"], ctx["side_key"]), None)
    except Exception:
        pass

    if ctx["sym_upper"]:
        if active_survivors:
            try:
                seed = copy.deepcopy(active_survivors[0])
            except Exception:
                seed = active_survivors[0]
            try:
                seed_interval = seed.get("interval_display") or seed.get("interval") or ctx["interval"]
                seed_norm_iv = signal_common_runtime._normalize_interval(self, seed_interval) or normalized_interval
                seed_open_time = seed.get("open_time")
                signal_common_runtime._sync_open_position_snapshot(
                    self,
                    ctx["sym_upper"],
                    ctx["side_key"],
                    active_survivors,
                    seed if isinstance(seed, dict) else None,
                    seed_interval,
                    seed_norm_iv,
                    seed_open_time,
                    resolve_trigger_indicators=resolve_trigger_indicators,
                    normalize_trigger_actions_map=normalize_trigger_actions_map,
                )
            except Exception:
                return False
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
                sync_local_position_tracking_from_allocations(
                    self,
                    ctx["sym_upper"],
                    ctx["side_key"],
                    [],
                )
            except Exception:
                pass

    if not signal_common_runtime._persist_trade_allocations(self, save_position_allocations):
        return False

    try:
        guard_obj = getattr(self, "guard", None)
        if guard_obj and hasattr(guard_obj, "mark_closed") and ctx["sym_upper"]:
            side_norm = "BUY" if ctx["side_key"] == "L" else "SELL"
            resolver = getattr(guard_obj, "context_key_from_entry", None)

            def _context_key_for(payload: dict | None) -> str | None:
                if not isinstance(payload, dict):
                    return None
                if callable(resolver):
                    try:
                        context_value = resolver(ctx["interval"], side_norm, payload)
                    except Exception:
                        context_value = None
                    if context_value:
                        return str(context_value).strip() or None
                context_value = str(payload.get("context_key") or "").strip()
                return context_value or None

            survivor_contexts = {
                context_key
                for entry in active_survivors
                if (context_key := _context_key_for(entry))
            }
            closed_contexts = {
                context_key
                for entry in closed_snapshots
                if (context_key := _context_key_for(entry))
            }
            if not closed_contexts and not active_survivors:
                event_context = _context_key_for(order_info)
                if event_context:
                    closed_contexts.add(event_context)
            contexts_to_clear = sorted(closed_contexts - survivor_contexts)
            if contexts_to_clear:
                for context_key in contexts_to_clear:
                    guard_obj.mark_closed(
                        ctx["sym_upper"],
                        ctx["interval"],
                        side_norm,
                        context=context_key,
                    )
            elif not active_survivors:
                guard_obj.mark_closed(ctx["sym_upper"], ctx["interval"], side_norm)
    except Exception:
        pass

    try:
        self._update_global_pnl_display(*self._compute_global_pnl_totals())
    except (ArithmeticError, AttributeError, LookupError, OSError, ReferenceError, RuntimeError, TypeError, ValueError):
        pass
    try:
        signal_common_runtime._refresh_trade_views(self, ctx["sym"])
    except (AttributeError, LookupError, OSError, ReferenceError, RuntimeError, TypeError, ValueError):
        pass
    return True


def _handle_close_interval_event(self, order_info: dict, ctx: dict, **kwargs) -> None:
    receipt = None
    try:
        receipt = signal_common_runtime._trade_event_receipt(order_info, ctx, "SELL")
        if (ctx.get("ok_flag") is False or ctx.get("status") in {"error", "failed"}
                or order_info.get("reconciliation_required") is True or order_info.get("execution_confirmed") is False):
            raise ValueError("Close event still needs exact execution reconciliation")
        allocation_event = dict(order_info, qty=float(receipt["quantity"]), executed_qty=float(receipt["quantity"]))
        if signal_common_runtime._has_trade_event_receipt(self, receipt):
            signal_common_runtime._clear_pending_trade_event(self, ctx, receipt)
            return
        if _close_event_key(self, allocation_event, ctx) in getattr(self, "_processed_close_events", set()):
            return
        snapshot = signal_common_runtime._capture_trade_state(self)
    except (ArithmeticError, AttributeError, LookupError, OSError, ReferenceError, RuntimeError, TypeError, ValueError):
        signal_common_runtime._retain_pending_trade_event(self, order_info, ctx, receipt)
        return
    self._active_trade_event_receipt = receipt
    persisted = False
    try:
        persisted = _apply_close_interval_event(self, allocation_event, ctx, **kwargs)
    except (ArithmeticError, AttributeError, LookupError, OSError, ReferenceError, RuntimeError, TypeError, ValueError):
        persisted = False
    finally:
        self._active_trade_event_receipt = None
        if not persisted:
            signal_common_runtime._restore_trade_state(self, snapshot)
            signal_common_runtime._retain_pending_trade_event(self, order_info, ctx, receipt)
    if not persisted:
        return
    signal_common_runtime._clear_pending_trade_event(self, ctx, receipt)


__all__ = ["_handle_close_interval_event"]
