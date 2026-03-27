from __future__ import annotations

from collections.abc import Iterable
import time

from . import strategy_close_opposite_runtime


def _close_opposite_position(
    self,
    symbol: str,
    interval: str,
    next_side: str,
    trigger_signature: tuple[str, ...] | None = None,
    indicator_key: Iterable[str] | str | None = None,
    target_qty: float | None = None,
) -> bool:
    return strategy_close_opposite_runtime._close_opposite_position(
        self,
        symbol,
        interval,
        next_side,
        trigger_signature=trigger_signature,
        indicator_key=indicator_key,
        target_qty=target_qty,
    )

def _reconcile_liquidations(self, symbol: str) -> None:
    """Clear internal state for a symbol if exchange shows no exposure (e.g., liquidation)."""
    try:
        positions = self.binance.list_open_futures_positions(max_age=0.0, force_refresh=True) or []
    except Exception:
        # Do not mutate miss counters on API failure; treat as inconclusive.
        return
    try:
        dual_mode = bool(self.binance.get_futures_dual_side())
    except Exception:
        dual_mode = False
    tol = 1e-9
    long_active = False
    short_active = False
    for pos in positions:
        if str(pos.get("symbol") or "").upper() != str(symbol or "").upper():
            continue
        try:
            amt_val = float(pos.get("positionAmt") or 0.0)
        except Exception:
            amt_val = 0.0
        pos_side = str(pos.get("positionSide") or pos.get("positionside") or "BOTH").upper()
        if dual_mode:
            if pos_side == "LONG" and amt_val > tol:
                long_active = True
            elif pos_side == "SHORT" and amt_val < -tol:
                short_active = True
            elif pos_side in {"BOTH", ""}:
                if amt_val > tol:
                    long_active = True
                elif amt_val < -tol:
                    short_active = True
        else:
            if amt_val > tol:
                long_active = True
            elif amt_val < -tol:
                short_active = True
    # Debounce: require two consecutive "no exposure" reads before purging local state.
    sym_norm = str(symbol or "").upper()
    if long_active or short_active:
        self._reconcile_miss_counts[sym_norm] = 0
        return
    miss_count = self._reconcile_miss_counts.get(sym_norm, 0) + 1
    self._reconcile_miss_counts[sym_norm] = miss_count
    if miss_count <= 1:
        # First miss: wait for a confirming read before clearing.
        return
    self._reconcile_miss_counts[sym_norm] = 0
    for key in list(self._leg_ledger.keys()):
        leg_sym, _, leg_side = key
        if str(leg_sym or "").upper() != str(symbol or "").upper():
            continue
        leg_side_norm = str(leg_side or "").upper()
        side_is_long = leg_side_norm in {"BUY", "LONG"}
        side_is_short = leg_side_norm in {"SELL", "SHORT"}
        clear_side = (side_is_long and not long_active) or (side_is_short and not short_active)
        if not clear_side:
            continue
        entries = self._leg_entries(key) or []
        for entry in entries:
            try:
                self._mark_indicator_reentry_signal_block(
                    symbol,
                    key[1],
                    entry,
                    leg_side_norm,
                )
            except Exception:
                pass
            try:
                for indicator_key in self._extract_indicator_keys(entry):
                    self._record_indicator_close(symbol, key[1], indicator_key, leg_side_norm, entry.get("qty"))
            except Exception:
                pass
            try:
                self._queue_flip_on_close(key[1], leg_side_norm, entry, None)
            except Exception:
                pass
        for entry in entries:
            for ind in self._extract_indicator_keys(entry):
                try:
                    self._purge_indicator_tracking(symbol, key[1], ind, leg_side_norm)
                except Exception:
                    pass
        self._remove_leg_entry(key, None)
        self._guard_mark_leg_closed(key)


def _merge_flip_requests_into_indicator_orders(
    self,
    *,
    cw: dict,
    indicator_order_requests: list[dict[str, object]],
    qty_tol_indicator: float,
) -> list[dict[str, object]]:
    flip_requests = self._drain_flip_on_close_requests(cw.get("interval"))
    if not flip_requests:
        return indicator_order_requests

    require_flip_signal = self._strategy_coerce_bool(
        self.config.get("require_indicator_flip_signal"), True
    )
    strict_flip_guard = self._strategy_coerce_bool(
        self.config.get("strict_indicator_flip_enforcement"), True
    )
    allow_without_signal = self._strategy_coerce_bool(
        self.config.get("allow_indicator_close_without_signal"), False
    )
    enforce_flip_signal_confirmation = (
        require_flip_signal and strict_flip_guard and not allow_without_signal
    )

    existing_map: dict[tuple[str, str], dict[str, object]] = {}
    for req in indicator_order_requests:
        side_val = str(req.get("side") or "").upper()
        if side_val not in ("BUY", "SELL"):
            continue
        indicator_token = self._canonical_indicator_token(req.get("indicator_key")) or None
        if not indicator_token:
            sig = req.get("signature") or ()
            if sig:
                indicator_token = self._canonical_indicator_token(sig[0]) or str(sig[0] or "").strip().lower()
        if not indicator_token:
            continue
        existing_map[(indicator_token, side_val)] = req

    interval_current = cw.get("interval")
    indicator_interval_tokens = set(self._tokenize_interval_label(interval_current))
    for req in flip_requests:
        indicator_key = self._canonical_indicator_token(req.get("indicator_key")) or str(
            req.get("indicator_key") or ""
        ).strip().lower()
        side_value = str(req.get("side") or "").upper()
        if not indicator_key or side_value not in ("BUY", "SELL"):
            continue
        flip_from = str(req.get("flip_from") or "").upper()
        if flip_from in ("BUY", "SELL") and flip_from != side_value:
            try:
                self._purge_indicator_tracking(
                    cw["symbol"], interval_current, indicator_key, side_value
                )
            except Exception:
                pass
        existing_req = existing_map.get((indicator_key, side_value))
        if existing_req is not None:
            if not existing_req.get("indicator_key"):
                existing_req["indicator_key"] = indicator_key
            if not existing_req.get("flip_from") and req.get("flip_from"):
                existing_req["flip_from"] = req.get("flip_from")
            try:
                existing_flip_qty = float(existing_req.get("flip_qty") or 0.0)
            except Exception:
                existing_flip_qty = 0.0
            try:
                existing_flip_target = float(existing_req.get("flip_qty_target") or 0.0)
            except Exception:
                existing_flip_target = 0.0
            try:
                req_flip_qty = float(req.get("qty") or 0.0)
            except Exception:
                req_flip_qty = 0.0
            if existing_flip_qty <= 0.0 and req_flip_qty > 0.0:
                existing_req["flip_qty"] = req_flip_qty
            if existing_flip_target <= 0.0 and req_flip_qty > 0.0:
                existing_req["flip_qty_target"] = req_flip_qty
            existing_actions = existing_req.get("trigger_actions")
            if not isinstance(existing_actions, dict):
                existing_actions = {}
            existing_actions[indicator_key] = side_value.lower()
            existing_req["trigger_actions"] = existing_actions
            continue
        if enforce_flip_signal_confirmation:
            try:
                self.log(
                    f"{cw['symbol']}@{interval_current or 'default'} {indicator_key} {side_value} "
                    "flip request ignored (waiting for live indicator confirmation)."
                )
            except Exception:
                pass
            continue
        allow_exchange_fallback = True
        try:
            allow_exchange_fallback = not self._strategy_coerce_bool(
                self.config.get("allow_opposite_positions"), True
            )
            live_qty = self._indicator_live_qty_total(
                cw["symbol"],
                interval_current,
                indicator_key,
                side_value,
                interval_aliases=indicator_interval_tokens,
                strict_interval=True,
                use_exchange_fallback=allow_exchange_fallback,
            )
        except Exception:
            live_qty = 0.0
        if live_qty > qty_tol_indicator and allow_exchange_fallback:
            try:
                desired_ps_check = None
                if self.binance.get_futures_dual_side():
                    desired_ps_check = "LONG" if side_value == "BUY" else "SHORT"
                exch_qty = max(
                    0.0,
                    float(
                        self._current_futures_position_qty(
                            cw["symbol"], side_value, desired_ps_check
                        )
                        or 0.0
                    ),
                )
            except Exception:
                exch_qty = 0.0
            tol_live = max(1e-9, exch_qty * 1e-6)
            if exch_qty <= tol_live:
                try:
                    self._purge_indicator_tracking(
                        cw["symbol"], interval_current, indicator_key, side_value
                    )
                except Exception:
                    pass
                live_qty = 0.0
        if live_qty > qty_tol_indicator:
            continue
        try:
            flip_qty_val = float(req.get("qty") or 0.0)
        except Exception:
            flip_qty_val = 0.0
        indicator_order_requests.append(
            {
                "side": side_value,
                "labels": [indicator_key],
                "signature": (indicator_key,),
                "indicator_key": indicator_key,
                "flip_from": req.get("flip_from"),
                "flip_qty": flip_qty_val,
                "flip_qty_target": flip_qty_val,
                "trigger_desc": f"{indicator_key.upper()} flip-on-close -> {side_value}",
                "trigger_actions": {indicator_key: side_value.lower()},
            }
        )
    return indicator_order_requests


# ---- indicator computation (uses pandas_ta when available)


def bind_strategy_position_flip_runtime(strategy_cls) -> None:
    strategy_cls._close_opposite_position = _close_opposite_position
    strategy_cls._merge_flip_requests_into_indicator_orders = _merge_flip_requests_into_indicator_orders


