from __future__ import annotations

import time

try:
    from . import strategy_signal_order_guard_runtime
    from . import strategy_signal_order_result_runtime
    from . import strategy_signal_order_sizing_runtime
    from . import strategy_signal_order_submit_runtime
except ImportError:  # pragma: no cover - standalone execution fallback
    import strategy_signal_order_guard_runtime  # type: ignore[no-redef]
    import strategy_signal_order_result_runtime  # type: ignore[no-redef]
    import strategy_signal_order_sizing_runtime  # type: ignore[no-redef]
    import strategy_signal_order_submit_runtime  # type: ignore[no-redef]


def _execute_signal_order(
    self,
    *,
    cw,
    order_side: str,
    indicator_labels: list[str],
    order_signature: tuple[str, ...],
    origin_timestamp: float | None,
    flip_from_side: str | None = None,
    flip_qty: float | int | None = None,
    flip_qty_target: float | int | None = None,
    order_trigger_desc: str | None = None,
    order_trigger_actions: dict[str, str] | None = None,
    trigger_desc: str | None = None,
    trigger_sources=None,
    last_price: float | None = None,
    current_bar_marker=None,
    positions_cache_holder: dict | None = None,
    order_batch_state: dict | None = None,
) -> None:
    positions_cache = positions_cache_holder.get("value") if isinstance(positions_cache_holder, dict) else None
    if not isinstance(order_batch_state, dict):
        order_batch_state = {}
    try:
        order_batch_counter = int(order_batch_state.get("counter") or 0)
    except Exception:
        order_batch_counter = 0
    try:
        order_batch_total = int(order_batch_state.get("total") or 0)
    except Exception:
        order_batch_total = 0
    base_trigger_labels = list(dict.fromkeys(trigger_sources or []))
    try:
        side = str(order_side or "").upper()
        if side not in ("BUY", "SELL"):
            return
        interval_norm = str(cw.get("interval") or "").strip()
        flip_from_norm = str(flip_from_side or "").upper()
        try:
            flip_qty_val = float(flip_qty or 0.0)
        except Exception:
            flip_qty_val = 0.0
        try:
            flip_qty_target_val = float(
                flip_qty_target if flip_qty_target is not None else (flip_qty or 0.0)
            )
        except Exception:
            flip_qty_target_val = 0.0
        flip_active = flip_from_norm in ("BUY", "SELL") and flip_from_norm != side
        flip_close_qty = 0.0
        if flip_active:
            if flip_qty_target_val > 0.0:
                flip_close_qty = flip_qty_target_val
            if flip_qty_val > 0.0:
                try:
                    self.log(
                        f"{cw['symbol']}@{interval_norm or 'default'} flip {flip_from_norm}→{side} "
                        f"request (qty {flip_qty_val:.10f})."
                    )
                except Exception:
                    pass
        current_batch_index = order_batch_counter
        order_batch_counter += 1
        try:
            order_event_uid = (
                f"{str(cw.get('symbol') or '').upper()}|{interval_norm or 'default'}|{side}|"
                f"{time.time_ns()}"
            )
        except Exception:
            order_event_uid = (
                f"{str(cw.get('symbol') or '').upper()}|{interval_norm or 'default'}|{side}|"
                f"{int(time.time() * 1_000_000)}"
            )
        trigger_labels = list(dict.fromkeys(indicator_labels or base_trigger_labels))
        if not trigger_labels:
            trigger_labels = [side.lower()]
        trigger_desc_for_order = str(order_trigger_desc or "").strip() or str(trigger_desc or "")
        trigger_actions_for_order: dict[str, str] = {}
        if isinstance(order_trigger_actions, dict):
            for raw_key, raw_action in order_trigger_actions.items():
                key_norm = self._canonical_indicator_token(raw_key) or str(raw_key or "").strip().lower()
                action_norm = str(raw_action or "").strip().lower()
                if key_norm and action_norm in {"buy", "sell"}:
                    trigger_actions_for_order[key_norm] = action_norm
        if not trigger_actions_for_order:
            inferred_action = "buy" if side == "BUY" else "sell"
            for label in trigger_labels:
                key_norm = self._canonical_indicator_token(label) or str(label or "").strip().lower()
                if key_norm:
                    trigger_actions_for_order[key_norm] = inferred_action
        signature = tuple(order_signature or tuple(sorted(trigger_labels)))
        primary_indicator_for_order = self._indicator_token_from_signature(signature, trigger_labels)
        if not primary_indicator_for_order:
            for action_key in (trigger_actions_for_order or {}).keys():
                action_key_norm = self._canonical_indicator_token(action_key) or str(action_key or "").strip().lower()
                if action_key_norm:
                    primary_indicator_for_order = action_key_norm
                    break
        if primary_indicator_for_order:
            primary_indicator_for_order = (
                self._canonical_indicator_token(primary_indicator_for_order)
                or str(primary_indicator_for_order).strip().lower()
            )
            trigger_labels = [primary_indicator_for_order]
            signature = (primary_indicator_for_order,)
            action_value = trigger_actions_for_order.get(primary_indicator_for_order)
            if action_value not in {"buy", "sell"}:
                action_value = "buy" if side == "BUY" else "sell"
            trigger_actions_for_order = {primary_indicator_for_order: action_value}
            if trigger_desc_for_order:
                narrowed_segments = [
                    segment.strip()
                    for segment in str(trigger_desc_for_order).split("|")
                    if str(segment).strip()
                    and self._segment_matches_indicator_context(primary_indicator_for_order, segment)
                ]
                if narrowed_segments:
                    trigger_desc_for_order = " | ".join(dict.fromkeys(narrowed_segments))
        interval_key = interval_norm or "default"
        context_key = f"{interval_key}:{side}:{'|'.join(signature) if signature else side}"
        bar_sig_key = (cw["symbol"], interval_key, side)
        sig_sorted = tuple(sorted(signature)) if signature else (side.lower(),)
        signature_guard_key = sig_sorted if sig_sorted else (side.lower(),)
        signature_label = (
            "|".join(str(part) for part in signature_guard_key)
            if signature_guard_key
            else side.lower()
        )

        indicator_tokens_for_order = type(self)._normalize_indicator_token_list(signature)
        if not indicator_tokens_for_order:
            indicator_tokens_for_order = type(self)._normalize_indicator_token_list(trigger_labels)
        indicator_key_hint = self._indicator_token_from_signature(signature, trigger_labels)
        slot_indicator_token = indicator_key_hint or (indicator_tokens_for_order[0] if indicator_tokens_for_order else None)

        qty_tol_slot_guard = 1e-9
        if slot_indicator_token:
            slot_live_qty = self._indicator_live_qty_total(
                cw["symbol"],
                interval_norm,
                slot_indicator_token,
                side,
                interval_aliases={interval_norm},
                strict_interval=True,
                use_exchange_fallback=False,
            )
            slot_book_qty = self._indicator_trade_book_qty(
                cw["symbol"],
                interval_norm,
                slot_indicator_token,
                side,
            )
            slot_qty_guard = max(slot_live_qty, slot_book_qty)
            if slot_qty_guard > qty_tol_slot_guard:
                if flip_active:
                    try:
                        desired_ps_check = None
                        if self.binance.get_futures_dual_side():
                            desired_ps_check = "LONG" if side == "BUY" else "SHORT"
                        exch_qty = max(
                            0.0,
                            float(self._current_futures_position_qty(cw["symbol"], side, desired_ps_check) or 0.0),
                        )
                    except Exception:
                        exch_qty = 0.0
                    if exch_qty <= qty_tol_slot_guard:
                        try:
                            self._purge_indicator_tracking(cw["symbol"], interval_norm, slot_indicator_token, side)
                        except Exception:
                            pass
                    else:
                        try:
                            self.log(
                                f"{cw['symbol']}@{interval_norm or 'default'} {slot_indicator_token} {side} blocked: "
                                f"slot still open on exchange ({exch_qty:.10f})."
                            )
                        except Exception:
                            pass
                        return
                else:
                    try:
                        self.log(
                            f"{cw['symbol']}@{interval_norm or 'default'} {slot_indicator_token} {side} blocked: slot already active "
                            f"(tracked qty {slot_qty_guard:.10f})."
                        )
                    except Exception:
                        pass
                    return

        guard_state = self._prepare_signal_order_guard(
            cw=cw,
            side=side,
            interval_norm=interval_norm,
            interval_key=interval_key,
            trigger_labels=trigger_labels,
            signature=signature,
            sig_sorted=sig_sorted,
            signature_guard_key=signature_guard_key,
            signature_label=signature_label,
            indicator_key_hint=indicator_key_hint,
            indicator_tokens_for_order=indicator_tokens_for_order,
            current_bar_marker=current_bar_marker,
            bar_sig_key=bar_sig_key,
            flip_active=flip_active,
        )
        indicator_tokens_for_guard = list(guard_state.get("indicator_tokens_for_guard") or [])
        guard_key_symbol = guard_state.get("guard_key_symbol") or (cw["symbol"], interval_key, side)
        try:
            guard_window = float(guard_state.get("guard_window") or 0.0)
        except Exception:
            guard_window = 0.0
        guard_claimed = bool(guard_state.get("guard_claimed"))
        if guard_state.get("aborted"):
            return

        def _guard_abort():
            nonlocal guard_claimed
            if guard_claimed:
                self._abort_signal_order_guard(guard_key_symbol, signature_guard_key)
                guard_claimed = False

        try:
            account_state = self._resolve_signal_order_account_state(cw=cw, last_price=last_price)
            account_type = str(account_state.get("account_type") or "").upper()
            futures_balance_snap = account_state.get("futures_balance_snap")
            try:
                pct = float(account_state.get("pct") or 0.0)
            except Exception:
                pct = 0.0
            try:
                free_usdt = float(account_state.get("free_usdt") or 0.0)
            except Exception:
                free_usdt = 0.0
            try:
                price = float(account_state.get("price") or 0.0)
            except Exception:
                price = 0.0

            if account_type == "FUTURES":
                futures_order_state = self._prepare_futures_signal_order_state(
                    cw=cw,
                    side=side,
                    interval_norm=interval_norm,
                    signature=signature,
                    trigger_labels=trigger_labels,
                    context_key=context_key,
                    indicator_key_hint=indicator_key_hint,
                    indicator_tokens_for_order=indicator_tokens_for_order,
                    indicator_tokens_for_guard=indicator_tokens_for_guard,
                    flip_active=flip_active,
                    flip_close_qty=flip_close_qty,
                    qty_tol_slot_guard=qty_tol_slot_guard,
                    free_usdt=free_usdt,
                    price=price,
                    pct=pct,
                    futures_balance_snap=futures_balance_snap,
                    abort_guard=_guard_abort,
                )
                if futures_order_state.get("aborted"):
                    return
                signature = tuple(futures_order_state.get("signature") or signature)
                trigger_labels = list(futures_order_state.get("trigger_labels") or trigger_labels)
                context_key = str(futures_order_state.get("context_key") or context_key)
                slot_key_tuple = futures_order_state.get("slot_key_tuple")
                try:
                    lev = int(futures_order_state.get("lev") or 0)
                except Exception:
                    lev = 0
                try:
                    qty_est = float(futures_order_state.get("qty_est") or 0.0)
                except Exception:
                    qty_est = 0.0
                reduce_only = bool(futures_order_state.get("reduce_only"))
                desired_ps = futures_order_state.get("desired_ps")
                key_bar = futures_order_state.get("key_bar") or (cw["symbol"], cw.get("interval"), side)
                key_dup = futures_order_state.get("key_dup") or key_bar

                order_res, order_success, submit_aborted = self._submit_futures_signal_order(
                    cw=cw,
                    side=side,
                    flip_active=flip_active,
                    context_key=context_key,
                    signature=signature,
                    key_bar=key_bar,
                    key_dup=key_dup,
                    current_batch_index=current_batch_index,
                    order_batch_total=order_batch_total,
                    desired_ps=desired_ps,
                    qty_est=qty_est,
                    reduce_only=reduce_only,
                    last_price=last_price,
                    lev=lev,
                    abort_guard=_guard_abort,
                )
                if submit_aborted:
                    return
                order_ok, qty_display = self._handle_futures_signal_order_result(
                    cw=cw,
                    side=side,
                    order_res=order_res,
                    trigger_labels=trigger_labels,
                    trigger_desc_for_order=trigger_desc_for_order,
                    order_event_uid=order_event_uid,
                    trigger_actions_for_order=trigger_actions_for_order,
                    current_bar_marker=current_bar_marker,
                    bar_sig_key=bar_sig_key,
                    sig_sorted=sig_sorted,
                    guard_claimed=guard_claimed,
                    guard_key_symbol=guard_key_symbol,
                    signature_guard_key=signature_guard_key,
                    guard_window=guard_window,
                    signature=signature,
                    context_key=context_key,
                    slot_key_tuple=slot_key_tuple,
                    price=price,
                    qty_est=qty_est,
                    lev=lev,
                )
            else:
                filters = self.binance.get_spot_symbol_filters(cw["symbol"])
                min_notional = float(filters.get("minNotional", 0.0) or 0.0)
                price = float(last_price or 0.0)
                if side == "BUY":
                    total_usdt = float(self.binance.get_spot_balance("USDT") or 0.0)
                    use_usdt = total_usdt * pct
                    if min_notional > 0 and use_usdt < min_notional and total_usdt >= min_notional:
                        use_usdt = min_notional
                    order_res = self.binance.place_spot_market_order(
                        cw["symbol"], "BUY", quantity=0.0, price=price, use_quote=True, quote_amount=use_usdt
                    )
                    qty_display = order_res.get("executedQty") or order_res.get("origQty")
                else:
                    base_asset, _ = self.binance.get_base_quote_assets(cw["symbol"])
                    base_free = float(self.binance.get_spot_balance(base_asset) or 0.0)
                    if base_free <= 0:
                        self.log(
                            f"Skip SELL for {cw['symbol']}: no {base_asset} balance. Spot cannot open shorts with USDT. "
                            "Switch Account Type to FUTURES to short."
                        )
                        return
                    est_notional = base_free * (price or 0.0) * pct
                    if min_notional > 0 and est_notional < min_notional:
                        self.log(
                            f"Skip SELL for {cw['symbol']}: position value {est_notional:.8f} < minNotional {min_notional:.8f}."
                        )
                        return
                    qty_to_sell = base_free * pct
                    order_res = self.binance.place_spot_market_order(
                        cw["symbol"], "SELL", quantity=qty_to_sell, price=price, use_quote=False
                    )
                    qty_display = order_res.get("executedQty") or order_res.get("origQty") or qty_to_sell

            leverage_used = None
            try:
                leverage_used = lev
            except Exception:
                leverage_used = None
            self._emit_signal_order_info(
                cw=cw,
                side=side,
                order_res=order_res,
                price=price,
                qty_display=qty_display,
                trigger_labels=trigger_labels,
                trigger_desc_for_order=trigger_desc_for_order,
                trigger_signature=signature,
                context_key=context_key,
                order_event_uid=order_event_uid,
                trigger_actions_for_order=trigger_actions_for_order,
                origin_timestamp=origin_timestamp,
                slot_key_tuple=slot_key_tuple,
                leverage_used=leverage_used,
            )
        except Exception as e:
            self.log(f"{cw['symbol']}@{cw['interval']} Order failed: {e}")
            if guard_claimed:
                self._abort_signal_order_guard(guard_key_symbol, signature_guard_key)
    finally:
        if isinstance(positions_cache_holder, dict):
            positions_cache_holder["value"] = positions_cache
        if isinstance(order_batch_state, dict):
            order_batch_state["counter"] = order_batch_counter
            order_batch_state["total"] = order_batch_total


def bind_strategy_signal_order_execute_runtime(strategy_cls) -> None:
    strategy_signal_order_guard_runtime.bind_strategy_signal_order_guard_runtime(strategy_cls)
    strategy_signal_order_result_runtime.bind_strategy_signal_order_result_runtime(strategy_cls)
    strategy_signal_order_sizing_runtime.bind_strategy_signal_order_sizing_runtime(strategy_cls)
    strategy_signal_order_submit_runtime.bind_strategy_signal_order_submit_runtime(strategy_cls)
    strategy_cls._execute_signal_order = _execute_signal_order
