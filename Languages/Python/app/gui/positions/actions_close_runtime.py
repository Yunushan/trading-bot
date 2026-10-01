from __future__ import annotations

from PyQt6 import QtWidgets

from app.security.redaction import redact_text
from trading_core.orders import confirmed_close_quantity

from .actions_state_runtime import (
    _allocation_reconciliation_pending,
    _close_target_identity,
    _coerce_qty_value,
    _normalize_interval_value,
    _record_positions_action_exception,
    _retain_pending_allocation_reconciliation,
)


def _manual_close_inflight(self, symbol: str, side_key: str) -> bool:
    inflight = getattr(self, "_manual_close_inflight", None)
    return bool(isinstance(inflight, dict) and (symbol, side_key) in inflight)


def make_close_btn(
    self,
    symbol: str,
    side_key: str | None = None,
    interval: str | None = None,
    qty: float | None = None,
    target_identity: dict | None = None,
):
    label = "Close"
    if side_key == "L":
        label = "Close Long"
    elif side_key == "S":
        label = "Close Short"
    btn = QtWidgets.QPushButton(label)
    tooltip_bits = []
    if side_key == "L":
        tooltip_bits.append("Closes the long leg")
    elif side_key == "S":
        tooltip_bits.append("Closes the short leg")
    if interval and interval not in ("-", "SPOT"):
        tooltip_bits.append(f"Interval {interval}")
    if qty and qty > 0:
        try:
            tooltip_bits.append(f"Qty ~= {qty:.6f}")
        except Exception:
            pass
    if isinstance(target_identity, dict):
        for field_name, label in (
            ("trade_id", "Trade"),
            ("client_order_id", "Client"),
            ("order_id", "Order"),
            ("context_key", "Context"),
            ("slot_id", "Slot"),
        ):
            value = str(target_identity.get(field_name) or "").strip()
            if value:
                tooltip_bits.append(f"{label} {value}")
                break
    if tooltip_bits:
        btn.setToolTip(" | ".join(tooltip_bits))
    btn.setEnabled(side_key in ("L", "S") and not _allocation_reconciliation_pending(
        self, str(symbol or "").strip().upper(), str(side_key or "").strip().upper(),
    ) and not _manual_close_inflight(
        self, str(symbol or "").strip().upper(), str(side_key or "").strip().upper(),
    ))
    interval_key = interval if interval not in ("-", "SPOT") else None
    if isinstance(target_identity, dict) and target_identity:
        btn.setProperty("close_target_identity", dict(target_identity))
    btn.clicked.connect(
        lambda _,
        s=symbol,
        sk=side_key,
        iv=interval_key,
        q=qty,
        ti=(dict(target_identity) if isinstance(target_identity, dict) else None): self._close_position_single(
            s,
            sk,
            iv,
            q,
            ti,
        )
    )
    return btn


def close_position_single(
    self,
    symbol: str,
    side_key: str | None,
    interval: str | None,
    qty: float | None,
    target_identity: dict | None = None,
):
    if not symbol:
        return
    symbol_key = str(symbol).strip().upper()
    normalized_side = str(side_key or "").strip().upper()
    if _manual_close_inflight(self, symbol_key, normalized_side):
        try:
            self.log(f"Close {symbol}: an earlier close is in flight or awaiting reconciliation; another close is blocked.")
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as exc:
            _record_positions_action_exception(self, "manual_close_inflight_log", exc)
        return
    if _allocation_reconciliation_pending(
        self, str(symbol or "").strip().upper(), str(side_key or "").strip().upper(),
    ):
        try:
            self.log(f"Close {symbol}: close outcome is pending local reconciliation; another close is blocked.")
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as exc:
            _record_positions_action_exception(self, "manual_close_pending_log", exc)
        return
    try:
        from app.gui.runtime.background_workers import CallWorker as _CallWorker
    except Exception as exc:
        try:
            self.log(f"Close {symbol} setup error: {redact_text(exc)}")
        except Exception:
            pass
        return
    if side_key not in ("L", "S"):
        try:
            self.log(f"{symbol}: manual close is only available for futures legs.")
        except Exception:
            pass
        return
    targeted = bool(target_identity) or bool(str(interval or "").strip())
    qty_value = _coerce_qty_value(qty) if qty is not None else None
    if (qty is not None and qty_value is None) or (qty is None and targeted):
        try:
            self.log(f"Close {symbol}: a targeted close requires an explicit finite positive quantity.")
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as exc:
            _record_positions_action_exception(self, "manual_close_quantity_rejected", exc)
        return
    # Only an untargeted None quantity is the explicit whole-symbol operation.
    qty_val = qty_value if qty_value is not None else 0.0
    account_text = (self.account_combo.currentText() or "").upper()
    force_futures = side_key in ("L", "S")
    needs_wrapper = getattr(self, "shared_binance", None) is None
    if force_futures and not needs_wrapper:
        try:
            current_wrapper_acct = str(getattr(self.shared_binance, "account_type", "") or "").upper()
        except Exception:
            current_wrapper_acct = ""
        if not current_wrapper_acct.startswith("FUT"):
            needs_wrapper = True
    if needs_wrapper:
        try:
            self.shared_binance = self._create_binance_wrapper(
                api_key=self.api_key_edit.text().strip(),
                api_secret=self.api_secret_edit.text().strip(),
                mode=self.mode_combo.currentText(),
                account_type=("Futures" if force_futures else self.account_combo.currentText()),
                default_leverage=int(self.leverage_spin.value() or 1),
                default_margin_mode=self.margin_mode_combo.currentText() or "Isolated",
            )
        except Exception as exc:
            try:
                self.log(f"Close {symbol} setup error: {redact_text(exc)}")
            except Exception:
                pass
            return
    account = account_text
    close_wrapper = self.shared_binance
    submission_session = getattr(self, "_allocation_snapshot_session", None)
    submission_generation = getattr(submission_session, "_generation", None)
    submission_mode = self.mode_combo.currentText() if hasattr(self, "mode_combo") else None
    fence_key = (symbol_key, normalized_side)
    fence_token = object()
    completion_received = False

    def _release_completed_inflight():
        if not completion_received or _allocation_reconciliation_pending(self, *fence_key):
            return
        inflight = getattr(self, "_manual_close_inflight", None)
        if isinstance(inflight, dict) and inflight.get(fence_key) is fence_token:
            inflight.pop(fence_key, None)

    def _do():
        # A queued close belongs to the account selected when the action began.
        bw = close_wrapper
        symbol_upper = str(symbol or "").strip().upper()

        def _annotate_no_live_leg(result_payload):
            if isinstance(result_payload, dict) and result_payload.get("ok"):
                return result_payload
            try:
                rows = bw.list_open_futures_positions(max_age=0.0, force_refresh=True) or []
            except Exception as exc:
                if isinstance(result_payload, dict):
                    enriched = dict(result_payload)
                    enriched.setdefault("lookup_error", redact_text(exc))
                    return enriched
                return {
                    "ok": False,
                    "error": redact_text(repr(result_payload)),
                    "lookup_error": redact_text(exc),
                }
            has_target_leg = False
            for row in rows:
                try:
                    row_sym = str(row.get("symbol") or "").strip().upper()
                    if row_sym != symbol_upper:
                        continue
                    amt = float(row.get("positionAmt") or 0.0)
                    if abs(amt) <= 0.0:
                        continue
                    row_side = str(row.get("positionSide") or row.get("positionside") or "BOTH").upper().strip()
                    if side_key == "L":
                        if row_side == "LONG" or (row_side in ("", "BOTH") and amt > 0.0):
                            has_target_leg = True
                            break
                    elif side_key == "S":
                        if row_side == "SHORT" or (row_side in ("", "BOTH") and amt < 0.0):
                            has_target_leg = True
                            break
                except Exception:
                    continue
            if not has_target_leg:
                if isinstance(result_payload, dict):
                    enriched = dict(result_payload)
                else:
                    enriched = {"ok": False, "error": f"{result_payload!r}"}
                enriched["no_live_position"] = True
                return enriched
            return result_payload

        if force_futures or account.startswith("FUT"):
            if side_key in ("L", "S") and qty_val > 0:
                try:
                    dual = bool(bw.get_futures_dual_side())
                except Exception:
                    dual = False
                order_side = "SELL" if side_key == "L" else "BUY"
                pos_side = None
                if dual:
                    pos_side = "LONG" if side_key == "L" else "SHORT"
                primary_res = bw.close_futures_leg_exact(symbol, qty_val, side=order_side, position_side=pos_side)
                # A targeted close must never expand into a symbol-wide close.
                return primary_res
            return _annotate_no_live_leg(bw.close_futures_position(symbol))
        return {"ok": False, "error": "Spot manual close via UI is not available yet"}

    def _done(res, err):
        nonlocal completion_received
        completion_received = True
        cleared_stale_state = False
        closed_qty = 0.0
        outcome_classified = False
        try:
            closed_qty = confirmed_close_quantity(res, qty_val) if qty_val > 0.0 else 0.0
            current_mode = self.mode_combo.currentText() if hasattr(self, "mode_combo") else None
            if (getattr(self, "shared_binance", None) is not close_wrapper
                    or getattr(self, "_allocation_snapshot_session", None) is not submission_session
                    or getattr(submission_session, "_generation", None) != submission_generation
                    or current_mode != submission_mode
                    or (self.account_combo.currentText() or "").upper() != account_text):
                _retain_pending_allocation_reconciliation(
                    self, *fence_key, operation="uncertain_close", interval=interval,
                    qty=closed_qty if closed_qty > 0 else None, target_identity=_close_target_identity(target_identity),
                    reason="original close outcome belongs to a changed account or allocation snapshot", venue_result=res,
                )
                outcome_classified = True
                return
            try:
                if err:
                    self.log(f"Close {symbol} error: {err}")
                else:
                    self.log(f"Close {symbol} result: {res}")
            except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as exc:
                _record_positions_action_exception(self, "manual_close_result_log", exc)
            if not err:
                if (
                    closed_qty <= 0.0
                    and isinstance(res, dict)
                    and bool(res.get("no_live_position"))
                    and side_key in ("L", "S")
                ):
                    try:
                        if hasattr(self, "_clear_local_position_state"):
                            cleared_stale_state = bool(
                                self._clear_local_position_state(
                                    symbol,
                                    side_key,
                                    interval=interval,
                                    reason="exchange reports no open leg",
                                )
                            )
                    except Exception:
                        cleared_stale_state = False
                    if not cleared_stale_state:
                        _retain_pending_allocation_reconciliation(
                            self, str(symbol).strip().upper(), side_key, operation="clear",
                            interval=interval, reason="exchange reports no open leg; local publication pending",
                            venue_result=res,
                        )
            if closed_qty > 0.0 and not cleared_stale_state and side_key in ("L", "S"):
                local_reconciled = False
                try:
                    if hasattr(self, "_reduce_local_position_allocation_state") and qty_val > 0.0:
                        local_reconciled = bool(
                            self._reduce_local_position_allocation_state(
                                symbol,
                                side_key,
                                interval=interval,
                                qty=closed_qty,
                                target_identity=target_identity,
                                close_result=res,
                            )
                        )
                except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as exc:
                    _record_positions_action_exception(self, "manual_close_reconciliation", exc)
                if not local_reconciled:
                    _retain_pending_allocation_reconciliation(
                        self, str(symbol).strip().upper(), side_key, operation="reduce",
                        interval=_normalize_interval_value(self, interval), qty=closed_qty,
                        target_identity=_close_target_identity(target_identity),
                        reason="confirmed venue fill requires local reconciliation", venue_result=res,
                    )
                    self.log(f"Close {symbol}: confirmed fill could not be attributed to its allocation; "
                             "tracking retained pending reconciliation.")
            if not cleared_stale_state and (
                err or not isinstance(res, dict)
                or (res.get("reconciliation_required") and (res.get("submission_attempted") or res.get("execution_confirmed")))
                or (res.get("execution_confirmed") is not True and not res.get("skipped")
                    and (res.get("submission_attempted") or res.get("ok")))
            ):
                _retain_pending_allocation_reconciliation(
                    self, str(symbol).strip().upper(), str(side_key).strip().upper(), operation="uncertain_close",
                    interval=interval, qty=closed_qty if closed_qty > 0 else None,
                    target_identity=_close_target_identity(target_identity),
                    reason="submitted close outcome requires exact reconciliation", venue_result=res,
                )
            outcome_classified = True
        except (AttributeError, LookupError, OSError, RuntimeError, TypeError, ValueError) as exc:
            _record_positions_action_exception(self, "manual_close_result", exc)
        finally:
            if not outcome_classified:
                _retain_pending_allocation_reconciliation(
                    self, str(symbol).strip().upper(), str(side_key).strip().upper(), operation="uncertain_close",
                    interval=interval, qty=closed_qty if closed_qty > 0 else None,
                    target_identity=_close_target_identity(target_identity),
                    reason="close result could not be safely reconciled", venue_result=res,
                )
            try:
                self.refresh_positions(symbols=[symbol])
            except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as exc:
                _record_positions_action_exception(self, "manual_close_refresh", exc)
            finally:
                _release_completed_inflight()

    inflight = getattr(self, "_manual_close_inflight", None)
    if not isinstance(inflight, dict):
        inflight = {}
        self._manual_close_inflight = inflight
    inflight[fence_key] = fence_token
    worker = None
    try:
        worker = _CallWorker(_do, parent=self)
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as exc:
        _record_positions_action_exception(self, "manual_close_worker_setup", exc)
        return
    finally:
        # Construction has not submitted the operation, including unexpected faults.
        if worker is None and inflight.get(fence_key) is fence_token:
            inflight.pop(fence_key, None)
    try:
        worker.progress.connect(self.log)
    except Exception:
        pass
    worker.done.connect(_done)
    worker.finished.connect(worker.deleteLater)

    def _cleanup():
        if not completion_received:
            _retain_pending_allocation_reconciliation(
                self, *fence_key, operation="uncertain_close", interval=interval,
                target_identity=_close_target_identity(target_identity),
                reason="close worker finished without a classified outcome",
            )
        _release_completed_inflight()
        try:
            self._bg_workers.remove(worker)
        except Exception:
            pass

    if not hasattr(self, "_bg_workers"):
        self._bg_workers = []
    self._bg_workers.append(worker)
    worker.finished.connect(_cleanup)
    start_completed = False
    try:
        worker.start()
        start_completed = True
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as exc:
        _record_positions_action_exception(self, "manual_close_worker_start", exc)
    finally:
        if not start_completed and not completion_received:
            _retain_pending_allocation_reconciliation(
                self, *fence_key, operation="uncertain_close", interval=interval,
                target_identity=_close_target_identity(target_identity), reason="close worker start outcome is uncertain",
            )
