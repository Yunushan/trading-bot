from __future__ import annotations

import logging
import math
import time

from ....security.redaction import redact_text
from .strategy_cycle_risk_stop_context_runtime import (
    _reconciled_close_qty,
    validate_futures_stop_positions,
)
from ..positions.close_execution import _pause_for_close_uncertainty


_LOGGER = logging.getLogger(__name__)


def _safe_log(self, message: str, *, level: int = logging.WARNING) -> bool:
    safe_message = redact_text(message)
    callback = getattr(self, "log", None)
    if callable(callback):
        try:
            callback(safe_message)
            return True
        except Exception:
            _LOGGER.error("Cumulative stop-loss log callback failed while reporting: %s", safe_message)
            return False
    _LOGGER.log(level, "%s", safe_message)
    return False


def apply_cumulative_futures_stop_management(
    self,
    *,
    cw,
    last_price: float,
    dual_side: bool,
    apply_usdt_limit: bool,
    apply_percent_limit: bool,
    stop_usdt_limit: float,
    stop_percent_limit: float,
    state,
) -> bool:
    if not math.isfinite(last_price) or last_price <= 0.0:
        return False
    load_positions_cache = state.get("load_positions_cache")
    try:
        if state.get("positions_cache_ok") is False:
            return False
        if callable(load_positions_cache):
            cache = load_positions_cache()
        else:
            cache = state.get("positions_cache")
            if cache is None:
                raise ValueError("futures stop position snapshot was not loaded")
        positions = validate_futures_stop_positions(
            cache,
            symbol=cw["symbol"],
            dual_side=dual_side,
            require_margin=apply_percent_limit,
        )
    except Exception as exc:
        _pause_for_close_uncertainty(
            self,
            f"{cw.get('symbol', 'Futures')} cumulative stop-loss position snapshot is invalid: {exc}",
            reconciliation_required=False,
        )
        return False
    totals = {
        "LONG": {"qty": 0.0, "loss": 0.0, "margin": 0.0},
        "SHORT": {"qty": 0.0, "loss": 0.0, "margin": 0.0},
    }
    try:
        for _pos, position_symbol, amt, entry_px, pos_side, qty_pos, margin_val in positions:
            if position_symbol != str(cw["symbol"]).strip().upper() or qty_pos <= 0.0:
                continue
            if dual_side:
                side_key = pos_side
                if side_key not in {"LONG", "SHORT"}:
                    raise ValueError("hedge-mode position side is unavailable")
            else:
                side_key = "LONG" if amt > 0.0 else "SHORT"
            if side_key == "LONG":
                loss_val = max(0.0, (entry_px - last_price) * qty_pos)
            else:
                loss_val = max(0.0, (last_price - entry_px) * qty_pos)
            if not math.isfinite(loss_val):
                raise ValueError("cumulative stop-loss amount overflowed")
            totals[side_key]["qty"] += qty_pos
            totals[side_key]["loss"] += loss_val
            totals[side_key]["margin"] += margin_val
            if any(not math.isfinite(value) for value in totals[side_key].values()):
                raise ValueError("cumulative stop-loss totals are non-finite")
    except Exception as exc:
        _pause_for_close_uncertainty(
            self,
            f"{cw.get('symbol', 'Futures')} cumulative stop-loss totals are invalid: {exc}",
            reconciliation_required=False,
        )
        return False
    cumulative_triggered = False
    for side_key in ("LONG", "SHORT"):
        data = totals[side_key]
        if data["qty"] <= 0.0:
            continue
        triggered = False
        if apply_usdt_limit and data["loss"] >= stop_usdt_limit:
            triggered = True
        if (
            not triggered
            and apply_percent_limit
            and data["margin"] > 0.0
            and (data["loss"] / data["margin"] * 100.0) >= stop_percent_limit
        ):
            triggered = True
        if not triggered:
            continue
        cumulative_triggered = True
        close_side = "SELL" if side_key == "LONG" else "BUY"
        position_side = side_key if dual_side else None
        start_ts = time.time()
        try:
            ok_close, res = self._execute_close_with_fallback(
                cw["symbol"], close_side, data["qty"], position_side
            )
        except Exception as exc:
            _safe_log(self, f"Cumulative stop-loss close error for {cw['symbol']} ({side_key}): {exc}")
            continue
        if ok_close and not getattr(self, "_ledger_reconciliation_required", False):
            closed_qty = _reconciled_close_qty(res, data["qty"])
            if closed_qty + max(1e-9, data["qty"] * 1e-6) < data["qty"]:
                _safe_log(
                    self,
                    f"Cumulative stop-loss close partially filled for {cw['symbol']} ({side_key}): "
                    f"{closed_qty:.10f}/{data['qty']:.10f}; preserving ledger for reconciliation.",
                )
                continue
            latency_s = max(0.0, time.time() - start_ts)
            target_side_label = "BUY" if side_key == "LONG" else "SELL"
            try:
                payload = self._build_close_event_payload(
                    cw["symbol"], cw.get("interval"), target_side_label, closed_qty, res
                )
            except Exception as exc:
                payload = {"qty": closed_qty}
                _safe_log(
                    self,
                    f"Cumulative stop-loss close metadata failed for "
                    f"{cw['symbol']} ({side_key}); using minimal payload: {exc}",
                )
            payload["reason"] = "cumulative_stop_loss"
            for leg_key in list(self._leg_ledger.keys()):
                if leg_key[0] == cw["symbol"] and leg_key[2] == target_side_label:
                    try:
                        for entry in self._leg_entries(leg_key):
                            try:
                                self._mark_indicator_reentry_signal_block(
                                    cw["symbol"],
                                    cw.get("interval"),
                                    entry,
                                    target_side_label,
                                )
                            except Exception as exc:
                                _safe_log(
                                    self,
                                    f"Failed to mark cumulative {target_side_label} stop-loss reentry state "
                                    f"for {cw['symbol']}@{cw.get('interval')}: {exc}",
                                )
                            try:
                                for indicator_key in self._extract_indicator_keys(entry):
                                    self._record_indicator_close(
                                        cw["symbol"],
                                        cw.get("interval"),
                                        indicator_key,
                                        target_side_label,
                                        entry.get("qty"),
                                    )
                            except Exception as exc:
                                _safe_log(
                                    self,
                                    f"Failed to record cumulative {target_side_label} stop-loss indicator close "
                                    f"for {cw['symbol']}@{cw.get('interval')}: {exc}",
                                )
                            try:
                                self._queue_flip_on_close(
                                    cw.get("interval"),
                                    target_side_label,
                                    entry,
                                    payload,
                                )
                            except Exception as exc:
                                _safe_log(
                                    self,
                                    f"Failed to queue cumulative {target_side_label} stop-loss flip "
                                    f"for {cw['symbol']}@{cw.get('interval')}: {exc}",
                                )
                    except Exception as exc:
                        _safe_log(
                            self,
                            f"Failed to inspect cumulative {target_side_label} stop-loss ledger "
                            f"for {cw['symbol']}@{cw.get('interval')}: {exc}",
                        )
                    try:
                        self._remove_leg_entry(leg_key, None)
                    except Exception as exc:
                        _safe_log(
                            self,
                            f"Failed to remove closed cumulative {target_side_label} stop-loss ledger "
                            f"for {cw['symbol']}@{cw.get('interval')}: {exc}",
                        )
            try:
                self._mark_guard_closed(cw["symbol"], cw.get("interval"), target_side_label)
            except Exception as exc:
                _safe_log(
                    self,
                    f"Failed to mark cumulative {target_side_label} stop-loss guard closed "
                    f"for {cw['symbol']}@{cw.get('interval')}: {exc}",
                )
            try:
                self._notify_interval_closed(
                    cw["symbol"],
                    cw.get("interval"),
                    target_side_label,
                    **payload,
                    latency_seconds=latency_s,
                    latency_ms=latency_s * 1000.0,
                )
            except Exception as exc:
                _safe_log(
                    self,
                    f"Failed to notify cumulative {target_side_label} stop-loss close "
                    f"for {cw['symbol']}@{cw.get('interval')}: {exc}",
                )
            try:
                self._log_latency_metric(
                    cw["symbol"],
                    cw.get("interval"),
                    f"cumulative stop-loss {target_side_label}",
                    latency_s,
                )
            except Exception as exc:
                _safe_log(
                    self,
                    f"Failed to record cumulative {target_side_label} stop-loss latency "
                    f"for {cw['symbol']}@{cw.get('interval')}: {exc}",
                )
            margin_val = data["margin"] or 0.0
            pct_loss = (data["loss"] / margin_val * 100.0) if margin_val > 0.0 else 0.0
            _safe_log(
                self,
                f"Cumulative stop-loss closed {target_side_label} for {cw['symbol']}@{cw.get('interval')} "
                f"(loss {data['loss']:.4f} USDT / {pct_loss:.2f}%).",
                level=logging.INFO,
            )
        else:
            _safe_log(self, f"Cumulative stop-loss close failed for {cw['symbol']} ({side_key}): {res}")
    return cumulative_triggered


__all__ = ["apply_cumulative_futures_stop_management"]
