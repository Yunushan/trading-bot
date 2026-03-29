from __future__ import annotations

import copy

from . import signal_common_runtime


def _scale_fields(payload: dict, ratio: float) -> None:
    for field_name in ("margin_usdt", "margin_balance", "notional", "size_usdt"):
        try:
            value = float(payload.get(field_name) or 0.0)
        except Exception:
            value = 0.0
        if value > 0.0:
            payload[field_name] = max(0.0, value * ratio)


def _build_closed_snapshot(
    entry_payload: dict,
    *,
    close_time_fmt: str | None,
    qty_tol: float,
    qty_closed: float | None = None,
) -> dict:
    snapshot = copy.deepcopy(entry_payload)
    try:
        entry_qty_val = abs(float(entry_payload.get("qty") or 0.0))
    except Exception:
        entry_qty_val = 0.0
    if qty_closed is not None and entry_qty_val > qty_tol:
        qty_use = max(0.0, min(entry_qty_val, float(qty_closed)))
        ratio_use = qty_use / entry_qty_val if entry_qty_val > 0.0 else 1.0
        snapshot["qty"] = qty_use
        _scale_fields(snapshot, ratio_use)
    if close_time_fmt:
        snapshot["close_time"] = close_time_fmt
    elif not snapshot.get("close_time"):
        snapshot["close_time"] = entry_payload.get("close_time")
    snapshot["status"] = "Closed"
    return snapshot


def _consume_closed_entries(
    entries: list,
    *,
    qty_remaining,
    qty_tol: float,
    close_time_fmt: str | None,
    matcher,
):
    closed_snapshots: list[dict] = []
    survivors: list[dict] = []
    matched = False

    for entry in entries:
        if not isinstance(entry, dict):
            continue

        target_match = bool(matcher(entry))
        if target_match:
            matched = True
        if not target_match:
            survivors.append(entry)
            continue

        try:
            entry_qty = abs(float(entry.get("qty") or 0.0))
        except Exception:
            entry_qty = 0.0

        if qty_remaining is None:
            closed_snapshots.append(
                _build_closed_snapshot(
                    entry,
                    close_time_fmt=close_time_fmt,
                    qty_tol=qty_tol,
                )
            )
            continue

        if qty_remaining <= qty_tol:
            survivors.append(entry)
            continue

        qty_used = qty_remaining
        if entry_qty > qty_tol:
            qty_used = min(entry_qty, qty_remaining)

        if entry_qty > qty_tol and (entry_qty - qty_used) > qty_tol:
            closed_snapshots.append(
                _build_closed_snapshot(
                    entry,
                    close_time_fmt=close_time_fmt,
                    qty_tol=qty_tol,
                    qty_closed=qty_used,
                )
            )
            survivor_entry = copy.deepcopy(entry)
            survivor_qty = max(0.0, entry_qty - qty_used)
            survivor_entry["qty"] = survivor_qty
            ratio_remaining = survivor_qty / entry_qty if entry_qty > 0.0 else 1.0
            _scale_fields(survivor_entry, ratio_remaining)
            survivors.append(survivor_entry)
        else:
            closed_snapshots.append(
                _build_closed_snapshot(
                    entry,
                    close_time_fmt=close_time_fmt,
                    qty_tol=qty_tol,
                    qty_closed=qty_used if entry_qty > qty_tol else None,
                )
            )

        qty_remaining = max(0.0, qty_remaining - max(0.0, qty_used))

    return closed_snapshots, survivors, qty_remaining, matched


def _restore_survivor_snapshot(
    self,
    ctx: dict,
    survivors: list[dict],
    *,
    interval,
    normalized_interval,
    pending_close,
    save_position_allocations,
    resolve_trigger_indicators,
    normalize_trigger_actions_map,
) -> None:
    try:
        seed = copy.deepcopy(survivors[0]) if survivors else {}
    except Exception:
        seed = survivors[0] if survivors else {}

    try:
        seed_interval = seed.get("interval_display") or seed.get("interval") or interval
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

    try:
        pending_close.pop((ctx["sym_upper"], ctx["side_key"]), None)
    except Exception:
        pass

    signal_common_runtime._persist_trade_allocations(self, save_position_allocations)
    signal_common_runtime._refresh_trade_views(self, ctx["sym"], mark_traded=False)


__all__ = [
    "_build_closed_snapshot",
    "_consume_closed_entries",
    "_restore_survivor_snapshot",
    "_scale_fields",
]
