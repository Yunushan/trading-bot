from __future__ import annotations

import copy
import time
from datetime import datetime

from PyQt6 import QtCore, QtWidgets

_SAVE_POSITION_ALLOCATIONS = None
_CLOSED_HISTORY_MAX = None
_POS_STATUS_COLUMN = 16
_DEFAULT_MAX_CLOSED_HISTORY = 200


def _closed_history_max(self) -> int:
    func = _CLOSED_HISTORY_MAX
    if callable(func):
        try:
            return int(func(self))
        except Exception:
            pass
    try:
        cfg_val = int(self.config.get("positions_closed_history_max", 500) or 500)
    except Exception:
        cfg_val = 500
    return max(_DEFAULT_MAX_CLOSED_HISTORY, cfg_val)


def _mw_clear_positions_selected(self):
    try:
        table = getattr(self, "pos_table", None)
        if table is None:
            return
        sel_model = table.selectionModel()
        if sel_model is None:
            return
        rows = sorted({index.row() for index in sel_model.selectedRows()}, reverse=True)
        if not rows:
            return
        closed_records = list(getattr(self, "_closed_position_records", []) or [])
        changed = False
        skipped_active = False
        for row in rows:
            status_item = table.item(row, _POS_STATUS_COLUMN)
            status = (status_item.text().strip().upper() if status_item else "")
            if status != "CLOSED":
                skipped_active = True
                continue
            symbol_item = table.item(row, 0)
            side_item = table.item(row, 9)
            symbol = (symbol_item.text().strip().upper() if symbol_item else "")
            side_txt = (side_item.text().strip().upper() if side_item else "")
            side_key = None
            if "LONG" in side_txt or side_txt == "BUY":
                side_key = "L"
            elif "SHORT" in side_txt or side_txt == "SELL":
                side_key = "S"
            remove_idx = None
            for idx, rec in enumerate(closed_records):
                rec_sym = str(rec.get("symbol") or "").strip().upper()
                rec_side = str(rec.get("side_key") or "").strip().upper()
                if rec_sym == symbol and (side_key is None or not rec_side or rec_side == side_key):
                    remove_idx = idx
                    break
            if remove_idx is not None:
                closed_records.pop(remove_idx)
                changed = True
        if changed:
            self._closed_position_records = closed_records
            self._render_positions_table()
        if skipped_active:
            try:
                self.log("Positions: only closed history rows can be cleared.")
            except Exception:
                pass
    except Exception:
        pass


def _mw_clear_positions_all(self):
    try:
        if QtWidgets.QMessageBox.question(
            self,
            "Clear Closed History",
            "Clear ALL closed position history? (Active positions remain untouched.)",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        ) != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self._closed_position_records = []
        self._closed_trade_registry = {}
        self._render_positions_table()
    except Exception:
        pass


def _mw_snapshot_closed_position(self, symbol: str, side_key: str) -> bool:
    try:
        if not symbol or side_key not in ("L", "S"):
            return False
        if not hasattr(self, "_closed_position_records"):
            self._closed_position_records = []
        open_records = getattr(self, "_open_position_records", {}) or {}
        rec = open_records.get((symbol, side_key))
        if not rec:
            return False
        snap = copy.deepcopy(rec)
        snap["status"] = "Closed"
        snap["close_time"] = self._format_display_time(datetime.now().astimezone())
        self._closed_position_records.insert(0, snap)
        max_history = _closed_history_max(self)
        if len(self._closed_position_records) > max_history:
            self._closed_position_records = self._closed_position_records[:max_history]
        try:
            registry = getattr(self, "_closed_trade_registry", None)
            if registry is None:
                registry = {}
                self._closed_trade_registry = registry
            key = f"{symbol}-{side_key}-{int(time.time() * 1000)}"
            data = snap.get("data") if isinstance(snap, dict) else {}

            def _safe_float_local(value):
                try:
                    return float(value)
                except Exception:
                    return None

            registry[key] = {
                "pnl_value": _safe_float_local((data or {}).get("pnl_value")),
                "margin_usdt": _safe_float_local((data or {}).get("margin_usdt")),
                "roi_percent": _safe_float_local((data or {}).get("roi_percent")),
            }
            if len(registry) > max_history:
                excess = len(registry) - max_history
                if excess > 0:
                    for old_key in list(registry.keys())[:excess]:
                        registry.pop(old_key, None)
        except Exception:
            pass
        try:
            open_records.pop((symbol, side_key), None)
        except Exception:
            pass
        try:
            self._update_global_pnl_display(*self._compute_global_pnl_totals())
        except Exception:
            pass
        return True
    except Exception:
        return False


def _mw_clear_local_position_state(
    self,
    symbol: str,
    side_key: str,
    *,
    interval: str | None = None,
    reason: str | None = None,
) -> bool:
    """Remove a stale local position/allocations snapshot for a single futures side."""
    try:
        sym_upper = str(symbol or "").strip().upper()
        side_norm = str(side_key or "").strip().upper()
        if not sym_upper or side_norm not in ("L", "S"):
            return False
        key = (sym_upper, side_norm)
        changed = False

        try:
            changed = bool(self._snapshot_closed_position(sym_upper, side_norm)) or changed
        except Exception:
            pass

        try:
            open_records = getattr(self, "_open_position_records", None)
            if isinstance(open_records, dict) and key in open_records:
                open_records.pop(key, None)
                changed = True
        except Exception:
            pass

        try:
            alloc_map = getattr(self, "_entry_allocations", None)
            if isinstance(alloc_map, dict) and key in alloc_map:
                alloc_map.pop(key, None)
                changed = True
        except Exception:
            pass

        try:
            pending_close = getattr(self, "_pending_close_times", None)
            if isinstance(pending_close, dict):
                pending_close.pop(key, None)
        except Exception:
            pass

        try:
            missing_counts = getattr(self, "_position_missing_counts", None)
            if isinstance(missing_counts, dict):
                missing_counts.pop(key, None)
        except Exception:
            pass

        try:
            entry_times = getattr(self, "_entry_times", None)
            if isinstance(entry_times, dict):
                entry_times.pop(key, None)
        except Exception:
            pass

        intervals_to_close: list[str] = []
        try:
            entry_intervals = getattr(self, "_entry_intervals", None)
            if isinstance(entry_intervals, dict):
                side_map = entry_intervals.get(sym_upper)
                if isinstance(side_map, dict):
                    bucket = side_map.get(side_norm)
                    if isinstance(bucket, set):
                        intervals_to_close.extend([str(iv).strip() for iv in bucket if str(iv).strip()])
        except Exception:
            pass
        if interval:
            iv = str(interval).strip()
            if iv and iv not in intervals_to_close:
                intervals_to_close.append(iv)
        if intervals_to_close and hasattr(self, "_track_interval_close"):
            for iv in intervals_to_close:
                try:
                    self._track_interval_close(sym_upper, side_norm, iv)
                except Exception:
                    continue

        try:
            iv_times = getattr(self, "_entry_times_by_iv", None)
            if isinstance(iv_times, dict):
                for iv_key in list(iv_times.keys()):
                    try:
                        sym_key, side_key_key, _iv = iv_key
                    except Exception:
                        continue
                    if str(sym_key or "").strip().upper() == sym_upper and str(side_key_key or "").strip().upper() == side_norm:
                        iv_times.pop(iv_key, None)
        except Exception:
            pass

        try:
            guard_obj = getattr(self, "guard", None)
            if guard_obj and hasattr(guard_obj, "mark_closed"):
                guard_side = "BUY" if side_norm == "L" else "SELL"
                guard_obj.mark_closed(sym_upper, interval, guard_side)
        except Exception:
            pass

        if changed:
            saver = _SAVE_POSITION_ALLOCATIONS
            if callable(saver):
                try:
                    mode_value = self.mode_combo.currentText() if hasattr(self, "mode_combo") else None
                    saver(
                        getattr(self, "_entry_allocations", {}),
                        getattr(self, "_open_position_records", {}),
                        mode=mode_value,
                    )
                except Exception:
                    pass
            try:
                self._update_global_pnl_display(*self._compute_global_pnl_totals())
            except Exception:
                pass
            try:
                self._render_positions_table()
            except Exception:
                pass
            if reason:
                try:
                    self.log(f"{sym_upper} {side_norm}: cleared stale local position ({reason}).")
                except Exception:
                    pass
        return changed
    except Exception:
        return False


def _mw_sync_chart_to_active_positions(self):
    try:
        if not getattr(self, "chart_enabled", False):
            return
        open_records = getattr(self, "_open_position_records", {}) or {}
        if not open_records:
            return
        active_syms = []
        for rec in open_records.values():
            try:
                if str(rec.get("status", "Active")).upper() != "ACTIVE":
                    continue
                sym = str(rec.get("symbol") or "").strip().upper()
                if sym:
                    active_syms.append(sym)
            except Exception:
                continue
        if not active_syms:
            return
        target_sym = active_syms[0]
        market_combo = getattr(self, "chart_market_combo", None)
        if market_combo is None:
            return
        current_market = self._normalize_chart_market(market_combo.currentText())
        if current_market != "Futures":
            try:
                idx = market_combo.findText("Futures", QtCore.Qt.MatchFlag.MatchFixedString)
                if idx >= 0:
                    market_combo.setCurrentIndex(idx)
                else:
                    market_combo.addItem("Futures")
                    market_combo.setCurrentIndex(market_combo.count() - 1)
            except Exception:
                try:
                    market_combo.setCurrentText("Futures")
                except Exception:
                    pass
            return
        display_sym = self._futures_display_symbol(target_sym)
        cache = self.chart_symbol_cache.setdefault("Futures", [])
        if target_sym not in cache:
            cache.append(target_sym)
        alias_map = getattr(self, "_chart_symbol_alias_map", None)
        if not isinstance(alias_map, dict):
            alias_map = {}
            self._chart_symbol_alias_map = alias_map
        futures_alias = alias_map.setdefault("Futures", {})
        futures_alias[display_sym] = target_sym
        self._update_chart_symbol_options(cache)
        changed = self._set_chart_symbol(display_sym, ensure_option=True, from_follow=True)
        if changed or self._chart_needs_render or self._is_chart_visible():
            self.load_chart(auto=True)
    except Exception:
        pass


def _mw_make_close_btn(self, symbol: str, side_key: str | None = None, interval: str | None = None, qty: float | None = None):
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
    if tooltip_bits:
        btn.setToolTip(" | ".join(tooltip_bits))
    btn.setEnabled(side_key in ("L", "S"))
    interval_key = interval if interval not in ("-", "SPOT") else None
    btn.clicked.connect(lambda _, s=symbol, sk=side_key, iv=interval_key, q=qty: self._close_position_single(s, sk, iv, q))
    return btn


def _mw_close_position_single(self, symbol: str, side_key: str | None, interval: str | None, qty: float | None):
    if not symbol:
        return
    try:
        from ...workers import CallWorker as _CallWorker
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
        try:
            if err:
                self.log(f"Close {symbol} error: {err}")
            else:
                self.log(f"Close {symbol} result: {res}")
                succeeded = isinstance(res, dict) and res.get("ok")
                if (
                    not succeeded
                    and isinstance(res, dict)
                    and bool(res.get("no_live_position"))
                    and side_key in ("L", "S")
                ):
                    try:
                        if hasattr(self, "_clear_local_position_state"):
                            cleared = bool(
                                self._clear_local_position_state(
                                    symbol,
                                    side_key,
                                    interval=interval,
                                    reason="exchange reports no open leg",
                                )
                            )
                    except Exception:
                        cleared = False
                    if cleared:
                        succeeded = True
            if succeeded and interval and side_key in ("L", "S"):
                try:
                    if hasattr(self, "_track_interval_close"):
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


def bind_main_window_positions_actions_runtime(
    main_window_cls,
    *,
    save_position_allocations=None,
    closed_history_max_fn=None,
    pos_status_column: int = 16,
) -> None:
    global _SAVE_POSITION_ALLOCATIONS
    global _CLOSED_HISTORY_MAX
    global _POS_STATUS_COLUMN

    _SAVE_POSITION_ALLOCATIONS = save_position_allocations
    _CLOSED_HISTORY_MAX = closed_history_max_fn
    _POS_STATUS_COLUMN = int(pos_status_column)

    main_window_cls._clear_positions_selected = _mw_clear_positions_selected
    main_window_cls._clear_positions_all = _mw_clear_positions_all
    main_window_cls._snapshot_closed_position = _mw_snapshot_closed_position
    main_window_cls._clear_local_position_state = _mw_clear_local_position_state
    main_window_cls._sync_chart_to_active_positions = _mw_sync_chart_to_active_positions
    main_window_cls._make_close_btn = _mw_make_close_btn
    main_window_cls._close_position_single = _mw_close_position_single
