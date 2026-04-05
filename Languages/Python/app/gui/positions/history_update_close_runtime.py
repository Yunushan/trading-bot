from __future__ import annotations

from .history_update_registry_runtime import update_closed_trade_registry
from .history_update_snapshot_runtime import build_closed_position_snapshot


def close_confirmed_positions(
    self,
    confirmed_closed: list[tuple[str, str]],
    prev_records: dict,
    close_time_map,
    *,
    closed_history_max: int,
    resolve_trigger_indicators_safe,
    lookup_force_liquidation,
) -> None:
    closed_records = getattr(self, "_closed_position_records", None)
    if not isinstance(closed_records, list):
        closed_records = []
        self._closed_position_records = closed_records

    for key in confirmed_closed:
        try:
            rec = prev_records.pop(key, None)
            if not isinstance(rec, dict):
                continue

            payload = build_closed_position_snapshot(
                self,
                key,
                rec,
                close_time_map,
                resolve_trigger_indicators_safe=resolve_trigger_indicators_safe,
                lookup_force_liquidation=lookup_force_liquidation,
            )
            if not isinstance(payload, dict):
                continue

            snap = payload.get("snap")
            if not isinstance(snap, dict):
                continue

            closed_records.insert(0, snap)
            if len(closed_records) > closed_history_max:
                del closed_records[closed_history_max:]

            update_closed_trade_registry(
                self,
                snap=snap,
                sym=str(payload.get("sym") or ""),
                side_key=str(payload.get("side_key") or ""),
                close_fmt=str(payload.get("close_fmt") or ""),
                pnl_reported=payload.get("pnl_reported"),
                margin_reported=payload.get("margin_reported"),
                roi_reported=payload.get("roi_reported"),
                closed_history_max=closed_history_max,
            )

            try:
                alloc_map = getattr(self, "_entry_allocations", None)
                if isinstance(alloc_map, dict):
                    alloc_map.pop(key, None)
            except Exception:
                pass
            try:
                guard_obj = getattr(self, "guard", None)
                if guard_obj and hasattr(guard_obj, "clear_symbol_side"):
                    guard_side = "BUY" if key[1] == "L" else "SELL"
                    guard_obj.clear_symbol_side(str(key[0] or ""), guard_side)
            except Exception:
                pass
        except Exception:
            continue


__all__ = ["close_confirmed_positions"]
