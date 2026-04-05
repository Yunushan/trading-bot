from __future__ import annotations

import time
from collections import deque
from datetime import datetime


def _identity_token(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _signature_tokens(payload: dict | None) -> tuple[str, ...]:
    if not isinstance(payload, dict):
        return ()
    raw = payload.get("trigger_signature")
    if not isinstance(raw, (list, tuple, set)):
        raw = payload.get("trigger_indicators")
    if not isinstance(raw, (list, tuple, set)):
        return ()
    tokens = [
        str(token).strip().lower()
        for token in raw
        if str(token).strip()
    ]
    return tuple(sorted(dict.fromkeys(tokens)))


def _has_open_identity(payload: dict | None) -> bool:
    if not isinstance(payload, dict):
        return False
    return any(
        _identity_token(payload.get(field_name))
        for field_name in (
            "client_order_id",
            "order_id",
            "trade_id",
            "event_uid",
            "context_key",
            "slot_id",
        )
    )


def _matches_existing_open_entry(
    entry: dict,
    *,
    client_order_token: str,
    order_id_token: str,
    order_identifier: str,
    event_uid_token: str,
    context_key: str,
    slot_id: str,
    signature_tokens: tuple[str, ...],
    trigger_desc_token: str,
    norm_iv: str,
    open_time_fmt: str | None,
) -> bool:
    entry_client_order = _identity_token(entry.get("client_order_id"))
    entry_order_id = _identity_token(entry.get("order_id"))
    entry_trade_id = _identity_token(entry.get("trade_id"))
    entry_event_uid = _identity_token(entry.get("event_uid"))
    entry_context = _identity_token(entry.get("context_key"))
    entry_slot = _identity_token(entry.get("slot_id"))

    if client_order_token and entry_client_order == client_order_token:
        return True
    if order_id_token and entry_order_id == order_id_token:
        return True
    if order_identifier and entry_trade_id == order_identifier:
        return True
    if event_uid_token and entry_event_uid == event_uid_token:
        return True
    if slot_id and entry_slot == slot_id:
        if context_key and entry_context and entry_context != context_key:
            return False
        return True
    if context_key and entry_context == context_key:
        if slot_id and entry_slot and entry_slot != slot_id:
            return False
        return True

    if _has_open_identity(entry) or any(
        (client_order_token, order_id_token, order_identifier, event_uid_token, context_key, slot_id)
    ):
        return False

    entry_interval = _identity_token(entry.get("interval"))
    entry_open_time = _identity_token(entry.get("open_time"))
    entry_trigger_desc = _identity_token(entry.get("trigger_desc")).lower()
    if entry_interval != _identity_token(norm_iv):
        return False
    if entry_open_time != _identity_token(open_time_fmt):
        return False
    if signature_tokens and _signature_tokens(entry) != signature_tokens:
        return False
    if trigger_desc_token and entry_trigger_desc and entry_trigger_desc != trigger_desc_token:
        return False
    return True


def _has_order_identity(order_info: dict) -> bool:
    fills_meta = order_info.get("fills_meta") or {}
    return bool(
        order_info.get("order_id")
        or order_info.get("client_order_id")
        or order_info.get("clientOrderId")
        or (fills_meta.get("order_id") if isinstance(fills_meta, dict) else None)
    )


def _is_duplicate_open_event(self, order_info: dict, ctx: dict, *, normalize_interval) -> bool:
    registry = getattr(self, "_processed_open_events", None)
    if not isinstance(registry, dict):
        registry = {"order": deque(), "set": set()}
        self._processed_open_events = registry

    queue = registry.setdefault("order", None)
    if queue is None:
        queue = registry["order"] = deque()
    registry_set = registry.setdefault("set", set())

    now_ts = time.time()
    while queue and ((now_ts - queue[0][1]) > 600.0 or len(queue) > 400):
        old_key, _ = queue.popleft()
        registry_set.discard(old_key)

    qty_token = ""
    qty_source = order_info.get("executed_qty")
    if qty_source is None:
        qty_source = order_info.get("qty")
    if qty_source is not None:
        try:
            qty_token = f"{abs(float(qty_source)):.8f}"
        except Exception:
            qty_token = str(qty_source)

    fills_meta = order_info.get("fills_meta") or {}
    order_id_token = fills_meta.get("order_id") or order_info.get("order_id") or ""
    if order_id_token is None:
        order_id_token = ""
    else:
        order_id_token = str(order_id_token)

    client_order_token = order_info.get("client_order_id") or order_info.get("clientOrderId") or ""
    if client_order_token is None:
        client_order_token = ""
    else:
        client_order_token = str(client_order_token)
    context_token = _identity_token(order_info.get("context_key"))
    slot_token = _identity_token(order_info.get("slot_id"))
    signature_token = "|".join(_signature_tokens(order_info))

    event_uid_token = (
        order_info.get("event_uid") or order_info.get("event_id") or order_info.get("ledger_id") or ""
    )
    if event_uid_token is None:
        event_uid_token = ""
    else:
        event_uid_token = str(event_uid_token).strip()

    interval_token = normalize_interval(self, ctx["interval"]) or str(ctx["interval"])
    status_token = str(order_info.get("status") or "").lower()
    time_token = str(order_info.get("time") or "")
    unique_parts = [
        ctx["sym_upper"],
        ctx["side_key"],
        interval_token,
        str(client_order_token),
        str(order_id_token),
        event_uid_token,
        context_token,
        slot_token,
        signature_token,
        qty_token,
        status_token,
    ]
    if not order_id_token and not client_order_token and not event_uid_token and not context_token and not slot_token:
        unique_parts.append(time_token)
        trigger_sig_token = str(order_info.get("trigger_desc") or "").strip()
        if trigger_sig_token:
            unique_parts.append(trigger_sig_token)

    unique_key = "|".join(unique_parts)
    if unique_key and unique_key in registry_set:
        return True
    if unique_key:
        registry_set.add(unique_key)
        queue.append((unique_key, now_ts))
    return False


def handle_non_close_trade_signal(
    self,
    order_info: dict,
    ctx: dict,
    *,
    alloc_map,
    pending_close,
    resolve_trigger_indicators,
    normalize_trigger_actions_map,
    save_position_allocations,
    normalize_interval,
    side_key_from_value,
    refresh_trade_views,
    persist_trade_allocations,
    sync_open_position_snapshot,
) -> None:
    status = ctx["status"]
    is_success = (status != "error") and (ctx["ok_flag"] is None or ctx["ok_flag"] is True)

    if ctx["sym"] and ctx["interval"] and ctx["side_for_key"]:
        trigger_desc_raw = str(order_info.get("trigger_desc") or "").strip()
        trigger_inds_raw = resolve_trigger_indicators(
            order_info.get("trigger_indicators"),
            trigger_desc_raw or None,
        )
        has_trigger_context = bool(trigger_desc_raw or trigger_inds_raw)

        if is_success and status in {"placed", "new"} and (not has_trigger_context) and (not _has_order_identity(order_info)):
            refresh_trade_views(self, ctx["sym"])
            return

        side_key_local = side_key_from_value(ctx["side_for_key"])
        dedupe_ctx = dict(ctx)
        dedupe_ctx["side_key"] = side_key_local
        if is_success and status not in {"error", "failed"}:
            if _is_duplicate_open_event(
                self,
                order_info,
                dedupe_ctx,
                normalize_interval=normalize_interval,
            ):
                return

        if getattr(self, "_is_stopping_engines", False) and status.lower() not in {"closed", "error"}:
            is_success = False

        if is_success:
            tstr = order_info.get("time")
            if not tstr:
                tstr = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            try:
                if hasattr(self, "_track_interval_open"):
                    self._track_interval_open(ctx["sym"], side_key_local, ctx["interval"], tstr)
            except Exception:
                pass

            norm_iv = normalize_interval(self, ctx["interval"]) or "-"
            try:
                qty_val = abs(float(order_info.get("executed_qty") or order_info.get("qty") or 0.0))
            except Exception:
                qty_val = 0.0
            try:
                price_val = float(order_info.get("avg_price") or order_info.get("price") or 0.0)
            except Exception:
                price_val = 0.0
            try:
                leverage_val = int(float(order_info.get("leverage") or 0.0))
            except Exception:
                leverage_val = 0
            if leverage_val <= 0 and getattr(self, "leverage_spin", None):
                try:
                    leverage_val = int(self.leverage_spin.value())
                except Exception:
                    leverage_val = 0

            entry_price_val = price_val if price_val > 0 else float(order_info.get("price") or 0.0)
            if entry_price_val <= 0:
                entry_price_val = price_val
            if entry_price_val <= 0:
                try:
                    entry_price_val = float(order_info.get("mark_price") or 0.0)
                except Exception:
                    entry_price_val = 0.0

            notional_val = entry_price_val * qty_val if entry_price_val > 0 and qty_val > 0 else 0.0
            if leverage_val > 0 and notional_val > 0:
                margin_val = notional_val / leverage_val
            else:
                margin_val = notional_val

            open_time_val = order_info.get("time") or tstr
            if open_time_val:
                dt_obj = self._parse_any_datetime(open_time_val)
                open_time_fmt = self._format_display_time(dt_obj) if dt_obj else open_time_val
            else:
                open_time_fmt = None

            trigger_inds = resolve_trigger_indicators(
                order_info.get("trigger_indicators"),
                order_info.get("trigger_desc"),
            )
            trigger_actions = normalize_trigger_actions_map(order_info.get("trigger_actions"))
            trigger_signature = order_info.get("trigger_signature")
            if isinstance(trigger_signature, (list, tuple)):
                trigger_signature = [
                    str(token).strip() for token in trigger_signature if str(token).strip()
                ]
            else:
                trigger_signature = []
            context_key = str(order_info.get("context_key") or "").strip()
            slot_id = str(order_info.get("slot_id") or "").strip()
            event_uid_token = _identity_token(order_info.get("event_uid") or order_info.get("event_id"))
            trigger_signature_tokens = _signature_tokens(order_info)
            trigger_desc_token = str(order_info.get("trigger_desc") or "").strip().lower()

            trade_entry = {
                "interval": norm_iv,
                "interval_display": ctx["interval"],
                "qty": qty_val,
                "entry_price": entry_price_val if entry_price_val > 0 else None,
                "leverage": leverage_val if leverage_val > 0 else None,
                "margin_usdt": margin_val,
                "margin_balance": margin_val,
                "notional": notional_val,
                "symbol": ctx["sym_upper"],
                "side_key": side_key_local,
                "open_time": open_time_fmt,
                "status": "Active",
                "pnl_value": None,
                "trigger_indicators": list(trigger_inds) if trigger_inds else [],
                "trigger_signature": trigger_signature,
                "trigger_desc": order_info.get("trigger_desc"),
                "trigger_actions": trigger_actions,
            }
            if context_key:
                trade_entry["context_key"] = context_key
            if slot_id:
                trade_entry["slot_id"] = slot_id
            if event_uid_token:
                trade_entry["event_uid"] = event_uid_token

            fills_meta = order_info.get("fills_meta") or {}
            order_id_token = fills_meta.get("order_id") or order_info.get("order_id") or ""
            if order_id_token is None:
                order_id_token = ""
            else:
                order_id_token = str(order_id_token)
            client_order_token = order_info.get("client_order_id") or order_info.get("clientOrderId") or ""
            if client_order_token is None:
                client_order_token = ""
            else:
                client_order_token = str(client_order_token)

            if order_id_token:
                trade_entry["order_id"] = order_id_token
            if client_order_token:
                trade_entry["client_order_id"] = client_order_token

            order_identifier = client_order_token or order_id_token or event_uid_token
            alloc_list = alloc_map.get((ctx["sym_upper"], side_key_local))
            if isinstance(alloc_list, dict):
                alloc_list = list(alloc_list.values())
            if not isinstance(alloc_list, list):
                alloc_list = []

            existing_entry = None
            if alloc_list:
                for entry in alloc_list:
                    if not isinstance(entry, dict):
                        continue
                    if _matches_existing_open_entry(
                        entry,
                        client_order_token=client_order_token,
                        order_id_token=order_id_token,
                        order_identifier=order_identifier,
                        event_uid_token=event_uid_token,
                        context_key=context_key,
                        slot_id=slot_id,
                        signature_tokens=trigger_signature_tokens,
                        trigger_desc_token=trigger_desc_token,
                        norm_iv=norm_iv,
                        open_time_fmt=open_time_fmt,
                    ):
                        existing_entry = entry
                        break

            if existing_entry:
                for key, value in trade_entry.items():
                    if value is None:
                        continue
                    if isinstance(value, (list, tuple, set)) and not value:
                        continue
                    if key == "trade_id" and not order_identifier:
                        continue
                    existing_entry[key] = value
                if order_identifier:
                    existing_entry["trade_id"] = order_identifier
            else:
                if not order_identifier:
                    try:
                        seq_len = len(alloc_list)
                        order_identifier = f"{ctx['sym_upper']}-{side_key_local}-{int(time.time() * 1000)}-{seq_len + 1}"
                    except Exception:
                        order_identifier = f"{ctx['sym_upper']}-{side_key_local}-{len(alloc_list) + 1}"
                trade_entry["trade_id"] = order_identifier
                alloc_list.append(trade_entry)
                existing_entry = trade_entry

            alloc_map[(ctx["sym_upper"], side_key_local)] = alloc_list
            pending_close.pop((ctx["sym_upper"], side_key_local), None)

            persist_trade_allocations(self, save_position_allocations)

            snapshot_entry = existing_entry or trade_entry
            sync_open_position_snapshot(
                self,
                ctx["sym_upper"],
                side_key_local,
                alloc_list,
                snapshot_entry,
                ctx["interval"],
                norm_iv,
                open_time_fmt,
                resolve_trigger_indicators=resolve_trigger_indicators,
                normalize_trigger_actions_map=normalize_trigger_actions_map,
            )
        else:
            try:
                if hasattr(self, "_track_interval_close"):
                    self._track_interval_close(ctx["sym"], side_key_local, ctx["interval"])
            except Exception:
                pass

    refresh_trade_views(self, ctx["sym"])
