from __future__ import annotations

from PyQt6 import QtWidgets


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
    btn.setEnabled(side_key in ("L", "S"))
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
    try:
        from app.gui.runtime.background_workers import CallWorker as _CallWorker
    except Exception as exc:
        try:
            self.log(f"Close {symbol} setup error: {exc}")
        except Exception:
            pass
        return
    if side_key not in ("L", "S"):
        try:
            self.log(f"{symbol}: manual close is only available for futures legs.")
        except Exception:
            pass
        return
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
                self.log(f"Close {symbol} setup error: {exc}")
            except Exception:
                pass
            return
    account = account_text
    try:
        qty_val = float(qty or 0.0)
    except Exception:
        qty_val = 0.0

    def _do():
        bw = self.shared_binance
        symbol_upper = str(symbol or "").strip().upper()

        def _annotate_no_live_leg(result_payload):
            if isinstance(result_payload, dict) and result_payload.get("ok"):
                return result_payload
            try:
                rows = bw.list_open_futures_positions(max_age=0.0, force_refresh=True) or []
            except Exception as exc:
                if isinstance(result_payload, dict):
                    enriched = dict(result_payload)
                    enriched.setdefault("lookup_error", str(exc))
                    return enriched
                return {"ok": False, "error": f"{result_payload!r}", "lookup_error": str(exc)}
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
                if isinstance(primary_res, dict) and primary_res.get("ok"):
                    return primary_res
                try:
                    fallback_res = bw.close_futures_position(symbol)
                except Exception as exc:
                    fallback_res = {"ok": False, "error": str(exc)}
                if isinstance(fallback_res, dict) and fallback_res.get("ok"):
                    fallback_res.setdefault("fallback_from", "close_futures_leg_exact")
                    if isinstance(primary_res, dict) and primary_res.get("error"):
                        fallback_res.setdefault("primary_error", primary_res.get("error"))
                    return fallback_res
                if isinstance(primary_res, dict):
                    primary_res["fallback"] = fallback_res
                    return _annotate_no_live_leg(primary_res)
                return _annotate_no_live_leg(
                    {"ok": False, "error": f"close leg failed: {primary_res!r}", "fallback": fallback_res}
                )
            return _annotate_no_live_leg(bw.close_futures_position(symbol))
        return {"ok": False, "error": "Spot manual close via UI is not available yet"}

    def _done(res, err):
        succeeded = False
        cleared_stale_state = False
        try:
            if err:
                self.log(f"Close {symbol} error: {err}")
            else:
                self.log(f"Close {symbol} result: {res}")
                succeeded = bool(isinstance(res, dict) and res.get("ok"))
                if (
                    not succeeded
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
                    if cleared_stale_state:
                        succeeded = True
            if succeeded and not cleared_stale_state and side_key in ("L", "S"):
                try:
                    local_reconciled = False
                    if hasattr(self, "_reduce_local_position_allocation_state") and qty_val > 0.0:
                        local_reconciled = bool(
                            self._reduce_local_position_allocation_state(
                                symbol,
                                side_key,
                                interval=interval,
                                qty=qty_val,
                                target_identity=target_identity,
                            )
                        )
                    if not local_reconciled and interval and hasattr(self, "_track_interval_close"):
                        self._track_interval_close(symbol, side_key, interval)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            self.refresh_positions(symbols=[symbol])
        except Exception:
            pass

    worker = _CallWorker(_do, parent=self)
    try:
        worker.progress.connect(self.log)
    except Exception:
        pass
    worker.done.connect(_done)
    worker.finished.connect(worker.deleteLater)

    def _cleanup():
        try:
            self._bg_workers.remove(worker)
        except Exception:
            pass

    if not hasattr(self, "_bg_workers"):
        self._bg_workers = []
    self._bg_workers.append(worker)
    worker.finished.connect(_cleanup)
    worker.start()
