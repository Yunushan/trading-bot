from __future__ import annotations

import time

from app.settings import is_live_trading_mode

from .strategy_indicator_order_common_runtime import _indicator_exchange_qty
from .strategy_order_error_logging import pause_for_order_uncertainty, safe_strategy_log


def _live_mode_for_position_gate(self) -> bool:  # noqa: ANN001
    config = getattr(self, "config", {}) or {}
    mode = config.get("mode") if isinstance(config, dict) else None
    if mode in (None, ""):
        mode = getattr(getattr(self, "binance", None), "mode", "")
    return bool(is_live_trading_mode(mode))


def _prepare_signal_order_position_gate(
    self,
    *,
    cw,
    side: str,
    interval_norm: str,
    signature,
    indicator_key_hint,
    indicator_tokens_for_order,
    indicator_tokens_for_guard,
    flip_close_qty: float,
    qty_tol_slot_guard: float,
    abort_guard,
) -> dict[str, object]:
    def _abort() -> dict[str, object]:
        abort_guard()
        return {"aborted": True}

    live_mode = _live_mode_for_position_gate(self)

    key_bar = (cw["symbol"], cw.get("interval"), side)
    key_dup = key_bar
    try:
        now_ts = time.time()
        secs = self._interval_to_seconds(str(cw.get("interval") or "1m"))
        last_ts = self._last_order_time.get(key_bar, 0)
        if now_ts - last_ts < max(5, secs * 0.9):
            existing_entries = self._leg_entries(key_bar)
            if any(tuple(sorted(entry.get("trigger_signature") or [])) == signature for entry in existing_entries):
                return _abort()
        guard_stale_secs = max(30.0, secs * 3.0)
        if now_ts - last_ts > guard_stale_secs:
            self._last_order_time.pop(key_bar, None)
            self._leg_ledger.pop(key_bar, None)
    except Exception as exc:
        if live_mode:
            pause_for_order_uncertainty(
                self,
                f"{cw['symbol']}@{interval_norm or 'default'} order timing guard failed: {exc}",
                reconciliation_required=True,
            )
            return _abort()
        safe_strategy_log(
            self,
            f"{cw['symbol']}@{interval_norm or 'default'} demo order timing guard failed: {exc}",
            level="warning",
        )

    target_flip_qty = flip_close_qty if flip_close_qty > 0.0 else None
    if not self._close_opposite_position(
        cw["symbol"],
        cw.get("interval"),
        side,
        signature,
        indicator_tokens_for_order,
        target_qty=target_flip_qty,
    ):
        return _abort()

    if indicator_tokens_for_guard:
        opp_side_guard = "SELL" if side == "BUY" else "BUY"
        indicator_interval_tokens = set(self._tokenize_interval_label(interval_norm))
        remaining_opp_qty = 0.0
        indicator_qty_lookup_failed = False
        for token in indicator_tokens_for_guard:
            try:
                qty_val = self._indicator_live_qty_total(
                    cw["symbol"],
                    interval_norm,
                    token,
                    opp_side_guard,
                    interval_aliases=indicator_interval_tokens,
                    strict_interval=True,
                    use_exchange_fallback=False,
                )
            except Exception as exc:
                indicator_qty_lookup_failed = True
                if live_mode:
                    pause_for_order_uncertainty(
                        self,
                        f"{cw['symbol']}@{interval_norm or 'default'} indicator quantity lookup failed: {exc}",
                        reconciliation_required=True,
                    )
                else:
                    safe_strategy_log(
                        self,
                        f"{cw['symbol']}@{interval_norm or 'default'} demo indicator quantity lookup failed: {exc}",
                        level="warning",
                    )
                qty_val = 0.0
            if qty_val > remaining_opp_qty:
                remaining_opp_qty = qty_val
        if indicator_qty_lookup_failed and live_mode:
            return _abort()
        if remaining_opp_qty <= qty_tol_slot_guard:
            try:
                account_type_check = str(
                    (self.config.get("account_type") or self.binance.account_type)
                ).upper()
            except Exception as exc:
                pause_for_order_uncertainty(
                    self,
                    f"{cw['symbol']}@{interval_norm or 'default'} account type lookup failed: {exc}",
                    reconciliation_required=False,
                )
                return _abort()
            if account_type_check == "FUTURES":
                protect_other = False
                for token in indicator_tokens_for_guard:
                    try:
                        if self._symbol_side_has_other_positions(
                            cw["symbol"], interval_norm, token, opp_side_guard
                        ):
                            protect_other = True
                            break
                    except Exception as exc:
                        pause_for_order_uncertainty(
                            self,
                            f"{cw['symbol']}@{interval_norm or 'default'} position ownership lookup failed: {exc}",
                            reconciliation_required=True,
                        )
                        return _abort()
                if not protect_other:
                    try:
                        desired_ps_check = None
                        if self.binance.get_futures_dual_side():
                            desired_ps_check = "LONG" if opp_side_guard == "BUY" else "SHORT"
                        exch_qty = _indicator_exchange_qty(
                            self,
                            cw["symbol"],
                            opp_side_guard,
                            desired_ps_check,
                        )
                    except Exception:
                        return _abort()
                    if exch_qty > qty_tol_slot_guard:
                        remaining_opp_qty = exch_qty
        if remaining_opp_qty > qty_tol_slot_guard:
            indicator_label_guard = (
                indicator_key_hint
                or (indicator_tokens_for_guard[0] if indicator_tokens_for_guard else "indicator")
            ).upper()
            safe_strategy_log(
                self,
                f"{cw['symbol']}@{interval_norm or 'default'} {indicator_label_guard} {side} blocked: "
                f"opposite {opp_side_guard} still open ({remaining_opp_qty:.10f}).",
                level="warning",
            )
            safe_strategy_log(
                self,
                f"{cw['symbol']}@{interval_norm or 'default'} {indicator_label_guard} "
                f"guard=opp_open block {side}.",
                level="warning",
            )
            return _abort()

    return {
        "aborted": False,
        "key_bar": key_bar,
        "key_dup": key_dup,
    }


def bind_strategy_signal_order_position_gate_runtime(strategy_cls) -> None:
    strategy_cls._live_mode_for_position_gate = _live_mode_for_position_gate
    strategy_cls._prepare_signal_order_position_gate = _prepare_signal_order_position_gate
