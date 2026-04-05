from __future__ import annotations

import time
from typing import Any


def _signal_order_has_opposite_open(
    self,
    *,
    positions,
    symbol: str,
    side: str,
    dual_mode: bool,
    tol: float,
) -> bool:
    symbol_upper = str(symbol or "").upper()
    for pos in positions or []:
        if str(pos.get("symbol") or "").upper() != symbol_upper:
            continue
        try:
            amt_existing = float(pos.get("positionAmt") or 0.0)
        except Exception:
            amt_existing = 0.0
        pos_side = str(pos.get("positionSide") or pos.get("positionside") or "BOTH").upper()
        if side == "BUY":
            if amt_existing < -tol and (not dual_mode or pos_side in {"BOTH", ""}):
                return True
        elif side == "SELL":
            if amt_existing > tol and (not dual_mode or pos_side in {"BOTH", ""}):
                return True
    return False


def _submit_futures_signal_order(
    self,
    *,
    cw,
    side: str,
    flip_active: bool,
    context_key: str,
    signature,
    key_bar,
    key_dup,
    current_batch_index: int,
    order_batch_total: int,
    desired_ps,
    qty_est: float,
    reduce_only: bool,
    last_price,
    lev,
    abort_guard,
) -> tuple[object, bool, bool]:
    allow_hedge_open = self._strategy_coerce_bool(self.config.get("allow_opposite_positions"), True)
    guard_obj = getattr(self, "guard", None)
    guard_side = side
    can_open_claimed = False

    def _release_can_open_claim() -> None:
        nonlocal can_open_claimed
        if not can_open_claimed:
            return
        can_open_claimed = False
        if guard_obj and hasattr(guard_obj, "end_open"):
            try:
                guard_obj.end_open(cw["symbol"], cw.get("interval"), guard_side, False, context=context_key)
            except Exception:
                pass

    if callable(self.can_open_cb) and not allow_hedge_open:
        if not self.can_open_cb(cw["symbol"], cw.get("interval"), side, context_key):
            self.log(f"{cw['symbol']}@{cw.get('interval')} Duplicate guard: {side} already open - skipping.")
            abort_guard()
            return {}, False, True
        can_open_claimed = True

    try:
        backend_key = str(getattr(self.binance, "_connector_backend", "") or "").lower()
        guard_duplicates = backend_key == "binance-sdk-derivatives-trading-usds-futures" and not allow_hedge_open
        tol = 1e-8
        dual_mode = bool(self.binance.get_futures_dual_side())
        existing_positions = None
        flip_refresh = False
        if flip_active:
            try:
                mode_text = str(getattr(self.binance, "mode", "") or "").lower()
                flip_refresh = any(tag in mode_text for tag in ("demo", "test", "paper"))
            except Exception:
                flip_refresh = False
        if flip_refresh:
            # Demo/testnet positions can lag after flips; retry a fresh snapshot once.
            for attempt in range(2):
                try:
                    invalidator = getattr(self.binance, "_invalidate_futures_positions_cache", None)
                    if callable(invalidator):
                        invalidator()
                except Exception:
                    pass
                try:
                    existing_positions = self.binance.list_open_futures_positions(
                        max_age=0.0,
                        force_refresh=True,
                    ) or []
                except Exception:
                    existing_positions = []
                if not self._signal_order_has_opposite_open(
                    positions=existing_positions,
                    symbol=cw["symbol"],
                    side=side,
                    dual_mode=dual_mode,
                    tol=tol,
                ):
                    break
                if attempt == 0:
                    time.sleep(0.35)
        if existing_positions is None:
            existing_positions = self.binance.list_open_futures_positions(
                max_age=0.0,
                force_refresh=True,
            ) or []
        for pos in existing_positions:
            if str(pos.get("symbol") or "").upper() != cw["symbol"].upper():
                continue
            try:
                amt_existing = float(pos.get("positionAmt") or 0.0)
            except Exception:
                amt_existing = 0.0
            pos_side = str(pos.get("positionSide") or pos.get("positionside") or "BOTH").upper()
            if side == "BUY":
                if amt_existing < -tol and (not dual_mode or pos_side in {"BOTH", ""}):
                    self.log(f"{cw['symbol']}@{cw.get('interval')} guard: short still open on exchange; skipping long entry.")
                    _release_can_open_claim()
                    abort_guard()
                    return {}, False, True
                if guard_duplicates:
                    long_active = False
                    if dual_mode:
                        if pos_side == "LONG":
                            long_active = abs(amt_existing) > tol
                        elif pos_side == "BOTH":
                            long_active = amt_existing > tol
                    else:
                        long_active = amt_existing > tol
                    if long_active:
                        entries_dup = self._leg_entries(key_bar)
                        sig_sorted = signature if signature else ()
                        if any(tuple(sorted(entry.get("trigger_signature") or [])) == sig_sorted for entry in entries_dup):
                            self.log(f"{cw['symbol']}@{cw.get('interval')} guard: long already active on exchange; skipping duplicate long entry.")
                            _release_can_open_claim()
                            abort_guard()
                            return {}, False, True
            elif side == "SELL":
                if amt_existing > tol and (not dual_mode or pos_side in {"BOTH", ""}):
                    self.log(f"{cw['symbol']}@{cw.get('interval')} guard: long still open on exchange; skipping short entry.")
                    _release_can_open_claim()
                    abort_guard()
                    return {}, False, True
                if guard_duplicates:
                    short_active = False
                    if dual_mode:
                        if pos_side == "SHORT":
                            short_active = abs(amt_existing) > tol
                        elif pos_side == "BOTH":
                            short_active = amt_existing < -tol
                    else:
                        short_active = amt_existing < -tol
                    if short_active:
                        entries_dup = self._leg_entries(key_dup)
                        sig_sorted = signature if signature else ()
                        if any(tuple(sorted(entry.get("trigger_signature") or [])) == sig_sorted for entry in entries_dup):
                            self.log(f"{cw['symbol']}@{cw.get('interval')} guard: short already active on exchange; skipping duplicate short entry.")
                            _release_can_open_claim()
                            abort_guard()
                            return {}, False, True
    except Exception as ex_chk:
        self.log(f"{cw['symbol']}@{cw.get('interval')} guard check warning: {ex_chk}")
        _release_can_open_claim()
        abort_guard()
        return {}, False, True

    order_res: dict[str, Any] = {}
    order_success = False
    if guard_obj and hasattr(guard_obj, "begin_open"):
        try:
            if not guard_obj.begin_open(cw["symbol"], cw.get("interval"), guard_side, context=context_key):
                _release_can_open_claim()
                self.log(f"{cw['symbol']}@{cw.get('interval')} guard blocked {guard_side} entry (pending or opposite side active).")
                abort_guard()
                return order_res, order_success, True
            can_open_claimed = False
        except Exception:
            pass
    if self.stopped():
        if guard_obj and hasattr(guard_obj, "end_open"):
            try:
                guard_obj.end_open(cw["symbol"], cw.get("interval"), guard_side, False, context=context_key)
            except Exception:
                pass
        return {"ok": False, "symbol": cw["symbol"], "error": "stop_requested"}, False, True

    try:
        order_attempts = 0
        order_success = False
        price_for_order = last_price if (last_price is not None and last_price > 0.0) else cw.get("price")
        backoff_base = self._order_rate_retry_backoff
        rate_limit_tokens = ("too frequent", "-1003", "frequency", "rate limit", "request too many", "too many requests")
        while True:
            if self.stopped():
                order_res = {"ok": False, "symbol": cw["symbol"], "error": "stop_requested"}
                order_success = False
                break
            order_attempts += 1
            spacing_to_use = self._order_rate_min_spacing
            if order_batch_total > 1 and current_batch_index > 0 and order_attempts == 1:
                spacing_to_use = min(
                    spacing_to_use,
                    max(0.1, spacing_to_use * 0.35),
                )
            try:
                type(self)._reserve_order_slot(spacing_to_use)
                if self.stopped():
                    order_res = {"ok": False, "symbol": cw["symbol"], "error": "stop_requested"}
                else:
                    order_res = self.binance.place_futures_market_order(
                        cw["symbol"],
                        side,
                        percent_balance=None,
                        leverage=lev,
                        reduce_only=(False if self.binance.get_futures_dual_side() else reduce_only),
                        position_side=desired_ps,
                        price=price_for_order,
                        quantity=qty_est,
                        strict=True,
                        timeInForce=self.config.get("tif", "GTC"),
                        gtd_minutes=int(self.config.get("gtd_minutes", 30)),
                        interval=cw.get("interval"),
                        max_auto_bump_percent=float(self.config.get("max_auto_bump_percent", 5.0)),
                        auto_bump_percent_multiplier=float(self.config.get("auto_bump_percent_multiplier", 10.0)),
                    )
            except Exception as exc_order:
                order_res = {"ok": False, "symbol": cw["symbol"], "error": str(exc_order)}
            finally:
                type(self)._release_order_slot()

            order_success = bool(order_res.get("ok", True))
            if self.stopped():
                order_success = False
                break
            if order_success:
                break
            try:
                err_text = order_res.get("error") or order_res
                self.log(f"{cw['symbol']}@{cw.get('interval')} order error: {err_text}")
            except Exception:
                pass
            err_text = str(order_res.get("error") or "").lower()
            if order_attempts < 3 and any(token in err_text for token in rate_limit_tokens):
                wait_time = min(5.0, backoff_base * order_attempts)
                time.sleep(wait_time)
                continue
            break
    finally:
        if guard_obj and hasattr(guard_obj, "end_open"):
            try:
                guard_obj.end_open(cw["symbol"], cw.get("interval"), guard_side, order_success, context=context_key)
            except Exception:
                pass

    if self.stopped():
        return order_res, order_success, True
    if order_success:
        try:
            via = order_res.get("via") or getattr(order_res.get("info", {}), "get", lambda *_: None)("via")
            qty_dbg = order_res.get("computed", {}).get("qty") or order_res.get("info", {}).get("origQty")
            self.log(f"{cw['symbol']}@{cw.get('interval')} order placed {side} qty={qty_dbg} via={via or 'primary'}")
        except Exception:
            pass
    else:
        try:
            self.log(f"{cw['symbol']}@{cw.get('interval')} order failed: {order_res}", lvl="error")
        except Exception:
            pass
    return order_res, order_success, False


def bind_strategy_signal_order_submit_runtime(strategy_cls) -> None:
    strategy_cls._signal_order_has_opposite_open = _signal_order_has_opposite_open
    strategy_cls._submit_futures_signal_order = _submit_futures_signal_order
