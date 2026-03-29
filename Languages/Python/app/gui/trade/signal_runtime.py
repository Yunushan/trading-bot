from __future__ import annotations

from . import signal_close_runtime, signal_common_runtime, signal_open_runtime

_connector_name = signal_common_runtime._connector_name
_side_key = signal_common_runtime._side_key
_ensure_trade_maps = signal_common_runtime._ensure_trade_maps
_normalize_interval = signal_common_runtime._normalize_interval
_safe_float = signal_common_runtime._safe_float
_persist_trade_allocations = signal_common_runtime._persist_trade_allocations
_refresh_trade_views = signal_common_runtime._refresh_trade_views
_sync_open_position_snapshot = signal_common_runtime._sync_open_position_snapshot

_scale_fields = signal_close_runtime._scale_fields
_build_closed_snapshot = signal_close_runtime._build_closed_snapshot
_consume_closed_entries = signal_close_runtime._consume_closed_entries
_restore_survivor_snapshot = signal_close_runtime._restore_survivor_snapshot
_record_closed_position = signal_close_runtime._record_closed_position
_handle_close_interval_event = signal_close_runtime._handle_close_interval_event


def handle_trade_signal(
    self,
    order_info: dict,
    *,
    max_closed_history: int,
    resolve_trigger_indicators,
    normalize_trigger_actions_map,
    save_position_allocations,
) -> None:
    connector_name = _connector_name(self)
    info_with_connector = dict(order_info or {})
    info_with_connector.setdefault("connector", connector_name)
    self.log(f"TRADE UPDATE [{connector_name}]: {info_with_connector}")

    sym = order_info.get("symbol")
    side = order_info.get("side")
    position_side = order_info.get("position_side") or side
    side_for_key = position_side or side
    ctx = {
        "sym": sym,
        "interval": order_info.get("interval"),
        "side_for_key": side_for_key,
        "side_key": _side_key(side_for_key),
        "sym_upper": str(sym or "").strip().upper(),
        "event_type": str(order_info.get("event") or "").lower(),
        "status": str(order_info.get("status") or "").lower(),
        "ok_flag": order_info.get("ok"),
    }

    alloc_map, pending_close = _ensure_trade_maps(self)

    if ctx["event_type"] == "close_interval":
        _handle_close_interval_event(
            self,
            order_info,
            ctx,
            alloc_map=alloc_map,
            pending_close=pending_close,
            max_closed_history=max_closed_history,
            resolve_trigger_indicators=resolve_trigger_indicators,
            normalize_trigger_actions_map=normalize_trigger_actions_map,
            save_position_allocations=save_position_allocations,
        )
        return

    signal_open_runtime.handle_non_close_trade_signal(
        self,
        order_info,
        ctx,
        alloc_map=alloc_map,
        pending_close=pending_close,
        resolve_trigger_indicators=resolve_trigger_indicators,
        normalize_trigger_actions_map=normalize_trigger_actions_map,
        save_position_allocations=save_position_allocations,
        normalize_interval=_normalize_interval,
        side_key_from_value=_side_key,
        refresh_trade_views=_refresh_trade_views,
        persist_trade_allocations=_persist_trade_allocations,
        sync_open_position_snapshot=_sync_open_position_snapshot,
    )
