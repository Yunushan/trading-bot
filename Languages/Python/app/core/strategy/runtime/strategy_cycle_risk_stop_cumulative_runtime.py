from __future__ import annotations

import logging
import math
import time

from ....security.redaction import redact_text
from .strategy_cycle_risk_stop_context_runtime import _reconciled_close_qty


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
    cache = load_positions_cache() if callable(load_positions_cache) else []
    totals = {
        "LONG": {"qty": 0.0, "loss": 0.0, "margin": 0.0},
        "SHORT": {"qty": 0.0, "loss": 0.0, "margin": 0.0},
    }
    for pos in cache:
        try:
            if str(pos.get("symbol") or "").upper() != cw["symbol"]:
                continue
            pos_side = str(pos.get("positionSide") or "").upper()
            amt = float(pos.get("positionAmt") or 0.0)
            entry_px = float(pos.get("entryPrice") or 0.0)
            if not math.isfinite(amt) or not math.isfinite(entry_px) or entry_px <= 0.0:
                continue
            if dual_side:
                if pos_side == "LONG":
                    qty_pos = max(0.0, float(pos.get("positionAmt") or 0.0))
                    side_key = "LONG"
                elif pos_side == "SHORT":
                    qty_pos = max(0.0, abs(float(pos.get("positionAmt") or 0.0)))
                    side_key = "SHORT"
                else:
                    continue
            else:
                if amt > 0.0:
                    qty_pos = amt
                    side_key = "LONG"
                elif amt < 0.0:
                    qty_pos = abs(amt)
                    side_key = "SHORT"
                else:
                    continue
            if not math.isfinite(qty_pos) or qty_pos <= 0.0:
                continue
            margin_val = float(pos.get("isolatedWallet") or 0.0)
            if not math.isfinite(margin_val) or margin_val <= 0.0:
                margin_val = float(pos.get("initialMargin") or 0.0)
            if not math.isfinite(margin_val) or margin_val <= 0.0:
                notional_val = abs(float(pos.get("notional") or 0.0))
                lev = float(pos.get("leverage") or 1.0) or 1.0
                if math.isfinite(notional_val) and math.isfinite(lev) and lev > 0.0:
                    margin_val = notional_val / lev
            if side_key == "LONG":
                loss_val = max(0.0, (entry_px - last_price) * qty_pos)
            else:
                loss_val = max(0.0, (last_price - entry_px) * qty_pos)
            totals[side_key]["qty"] += qty_pos
            totals[side_key]["loss"] += loss_val
            totals[side_key]["margin"] += max(0.0, margin_val) if math.isfinite(margin_val) else 0.0
        except Exception:
            _LOGGER.debug("Skipping malformed cumulative stop-loss position", exc_info=True)
            continue
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
            res = self.binance.close_futures_leg_exact(
                cw["symbol"], data["qty"], side=close_side, position_side=position_side
            )
        except Exception as exc:
            _safe_log(self, f"Cumulative stop-loss close error for {cw['symbol']} ({side_key}): {exc}")
            continue
        if isinstance(res, dict) and res.get("ok"):
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
