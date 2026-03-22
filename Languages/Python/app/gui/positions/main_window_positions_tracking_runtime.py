from __future__ import annotations

import copy
import os
from datetime import datetime

_RESOLVE_TRIGGER_INDICATORS = None
_CLOSED_HISTORY_MAX = None
_STOP_STRATEGY_SYNC = None
_DEFAULT_MAX_CLOSED_HISTORY = 200


def _resolve_trigger_indicators_safe(raw, desc: str | None = None) -> list[str]:
    func = _RESOLVE_TRIGGER_INDICATORS
    if not callable(func):
        return []
    try:
        return list(func(raw, desc))
    except Exception:
        return []


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


def _mw_pos_symbol_keys(self, symbol) -> tuple:
    sym_raw = str(symbol or "").strip()
    if not sym_raw:
        return tuple()
    sym_upper = sym_raw.upper()
    if sym_upper == sym_raw:
        return (sym_upper,)
    return tuple(dict.fromkeys([sym_upper, sym_raw]))


def _mw_pos_interval_keys(self, interval) -> tuple:
    iv_raw = str(interval or "").strip()
    if not iv_raw:
        return tuple()
    try:
        canon = self._canonicalize_interval(iv_raw)
    except Exception:
        canon = None
    keys = []
    if canon:
        keys.append(canon)
    if iv_raw and iv_raw != canon:
        keys.append(iv_raw)
    return tuple(dict.fromkeys(keys))


def _mw_pos_track_interval_open(self, symbol, side_key, interval, timestamp) -> None:
    if side_key not in ("L", "S"):
        return
    symbol_keys = _mw_pos_symbol_keys(self, symbol)
    if not symbol_keys:
        sym_raw = str(symbol or "").strip()
        if not sym_raw:
            return
        symbol_keys = _mw_pos_symbol_keys(self, sym_raw)
        if not symbol_keys:
            return
    primary_symbol = symbol_keys[0]
    interval_keys = _mw_pos_interval_keys(self, interval)
    primary_interval = interval_keys[0] if interval_keys else None
    entry_map = self._entry_intervals.setdefault(primary_symbol, {"L": set(), "S": set()})
    entry_map.setdefault("L", set())
    entry_map.setdefault("S", set())
    if primary_interval:
        entry_map[side_key].add(primary_interval)
    if timestamp:
        self._entry_times[(primary_symbol, side_key)] = timestamp
        if primary_interval:
            self._entry_times_by_iv[(primary_symbol, side_key, primary_interval)] = timestamp
    for alt_symbol in symbol_keys[1:]:
        if not alt_symbol:
            continue
        legacy = self._entry_intervals.pop(alt_symbol, None)
        if isinstance(legacy, dict):
            for leg_side, iv_set in legacy.items():
                if leg_side not in ("L", "S") or not isinstance(iv_set, set):
                    continue
                target = entry_map.setdefault(leg_side, set())
                for iv in iv_set:
                    normalized = _mw_pos_interval_keys(self, iv)
                    if normalized:
                        target.add(normalized[0])
        for side_variant in ("L", "S"):
            ts_val = self._entry_times.pop((alt_symbol, side_variant), None)
            if ts_val and (primary_symbol, side_variant) not in self._entry_times:
                self._entry_times[(primary_symbol, side_variant)] = ts_val
        for (sym_key, side_variant, iv_key), ts_val in list(self._entry_times_by_iv.items()):
            if sym_key == alt_symbol:
                normalized = _mw_pos_interval_keys(self, iv_key)
                self._entry_times_by_iv.pop((sym_key, side_variant, iv_key), None)
                if normalized:
                    self._entry_times_by_iv[(primary_symbol, side_variant, normalized[0])] = ts_val


def _mw_pos_track_interval_close(self, symbol, side_key, interval) -> None:
    if side_key not in ("L", "S"):
        return
    symbol_keys = _mw_pos_symbol_keys(self, symbol)
    if not symbol_keys:
        sym_raw = str(symbol or "").strip()
        candidates = [sym_raw.upper(), sym_raw]
        symbol_keys = tuple(dict.fromkeys([c for c in candidates if c]))
    interval_keys = _mw_pos_interval_keys(self, interval)
    if not interval_keys and interval:
        iv_raw = str(interval).strip()
        if iv_raw:
            interval_keys = (iv_raw,)
    for sym_key in symbol_keys:
        if not sym_key:
            continue
        side_map = self._entry_intervals.get(sym_key)
        if not isinstance(side_map, dict):
            continue
        bucket = side_map.get(side_key)
        if not isinstance(bucket, set):
            bucket = side_map[side_key] = set()
        for iv_key in interval_keys:
            bucket.discard(iv_key)
            self._entry_times_by_iv.pop((sym_key, side_key, iv_key), None)


def _handle_close_all_result(self, res):
    try:
        details = res or []
        for r in details:
            sym = r.get("symbol") or "?"
            if not r.get("ok"):
                self.log(f"Close-all {sym}: error -> {r.get('error')}")
            elif r.get("skipped"):
                self.log(f"Close-all {sym}: skipped ({r.get('reason')})")
            else:
                self.log(f"Close-all {sym}: ok")
        n_ok = sum(1 for r in details if r.get("ok"))
        n_all = len(details)
        self.log(f"Close-all completed: {n_ok}/{n_all} ok.")
    except Exception:
        self.log(f"Close-all result: {res}")
    try:
        self._apply_close_all_to_positions_cache(res)
    except Exception:
        pass
    try:
        self.refresh_positions()
    except Exception:
        pass
    try:
        self.trigger_positions_refresh()
    except Exception:
        pass


def _apply_close_all_to_positions_cache(self, res) -> None:
    """Mark local position state as closed when a close-all command succeeds."""
    details = res or []
    if isinstance(details, dict):
        details = [details]
    elif not isinstance(details, (list, tuple, set)):
        details = [details]

    symbols_to_mark: set[str] = set()
    had_error = False
    for item in details:
        if not isinstance(item, dict):
            continue
        sym_raw = str(item.get("symbol") or "").strip().upper()
        if not sym_raw:
            continue
        ok_flag = bool(item.get("ok"))
        skipped_flag = bool(item.get("skipped"))
        if ok_flag or skipped_flag:
            symbols_to_mark.add(sym_raw)
        else:
            had_error = True

    open_records = getattr(self, "_open_position_records", {}) or {}
    if not symbols_to_mark and not had_error and open_records:
        symbols_to_mark = {sym for sym, _ in open_records.keys()}
    if not symbols_to_mark:
        return

    pending_close = getattr(self, "_pending_close_times", None)
    if not isinstance(pending_close, dict):
        pending_close = {}
        self._pending_close_times = pending_close
    missing_counts = getattr(self, "_position_missing_counts", None)
    if not isinstance(missing_counts, dict):
        missing_counts = {}
        self._position_missing_counts = missing_counts

    close_time_fmt = self._format_display_time(datetime.now().astimezone())
    alloc_map = getattr(self, "_entry_allocations", {})
    closed_records = getattr(self, "_closed_position_records", None)
    if not isinstance(closed_records, list):
        closed_records = []
        self._closed_position_records = closed_records
    max_history = _closed_history_max(self)

    for key in list(open_records.keys()):
        sym_key, side_key = key
        record = open_records.get(key)
        if sym_key not in symbols_to_mark:
            continue
        if key not in pending_close:
            pending_close[key] = close_time_fmt
        missing_counts[key] = 0
        try:
            intervals_map = getattr(self, "_entry_intervals", {})
            side_bucket = intervals_map.get(sym_key, {}).get(side_key)
            if hasattr(self, "_track_interval_close") and isinstance(side_bucket, set):
                for interval in list(side_bucket):
                    self._track_interval_close(sym_key, side_key, interval)
        except Exception:
            pass

        snap = copy.deepcopy(record) if isinstance(record, dict) else {
            "symbol": sym_key,
            "side_key": side_key,
            "status": "Closed",
            "open_time": "-",
            "close_time": close_time_fmt,
            "data": {},
            "indicators": [],
            "stop_loss_enabled": False,
        }
        snap["status"] = "Closed"
        snap["close_time"] = close_time_fmt
        if "stop_loss_enabled" not in snap:
            snap["stop_loss_enabled"] = bool((record or {}).get("stop_loss_enabled"))

        base_data = dict((record or {}).get("data") or {})
        snap["data"] = base_data
        try:
            alloc_entries = copy.deepcopy(alloc_map.get(key, [])) or []
            for alloc_entry in alloc_entries:
                if isinstance(alloc_entry, dict):
                    normalized_triggers = _resolve_trigger_indicators_safe(
                        alloc_entry.get("trigger_indicators"),
                        alloc_entry.get("trigger_desc"),
                    )
                    if normalized_triggers:
                        alloc_entry["trigger_indicators"] = normalized_triggers
                    elif alloc_entry.get("trigger_indicators"):
                        alloc_entry.pop("trigger_indicators", None)
        except Exception:
            alloc_entries = []
        if alloc_entries:
            snap["allocations"] = alloc_entries
        closed_records.insert(0, snap)
        if len(closed_records) > max_history:
            del closed_records[max_history:]
        alloc_map.pop(key, None)
        open_records.pop(key, None)
        try:
            getattr(self, "_entry_times", {}).pop(key, None)
        except Exception:
            pass
        try:
            iv_times = getattr(self, "_entry_times_by_iv", {})
            if isinstance(iv_times, dict):
                for (sym, side, interval) in list(iv_times.keys()):
                    if sym == sym_key and side == side_key:
                        iv_times.pop((sym, side, interval), None)
        except Exception:
            pass

    try:
        self._open_position_records = dict(open_records)
    except Exception:
        self._open_position_records = open_records
    try:
        self._update_global_pnl_display(*self._compute_global_pnl_totals())
    except Exception:
        pass
    try:
        self._render_positions_table()
    except Exception:
        pass


def _close_all_positions_blocking(self, auth: dict | None = None, *, fast: bool = False):
    return self._close_all_positions_sync(auth=auth, fast=fast)


def _close_all_positions_sync(self, auth: dict | None = None, *, fast: bool = False):
    from ...close_all import close_all_futures_positions as _close_all_futures

    # Rebuild wrapper each time so close-all uses latest mode/credentials even if launch-time wrapper was different.
    if auth is None:
        auth = self._snapshot_auth_state()
    timeout_override = None
    if fast:
        timeout_override = {
            "BINANCE_HTTP_CONNECT_TIMEOUT": os.environ.get("BINANCE_HTTP_CONNECT_TIMEOUT"),
            "BINANCE_HTTP_READ_TIMEOUT": os.environ.get("BINANCE_HTTP_READ_TIMEOUT"),
        }
        os.environ["BINANCE_HTTP_CONNECT_TIMEOUT"] = "2"
        os.environ["BINANCE_HTTP_READ_TIMEOUT"] = "6"
    try:
        self.shared_binance = self._build_wrapper_from_values(auth)
        acct_text = str(auth.get("account_type") or "").upper() or (
            self.account_combo.currentText().upper() if hasattr(self, "account_combo") else ""
        )
        if acct_text.startswith("FUT"):
            results = _close_all_futures(self.shared_binance, fast=fast) or []
            if not fast:
                # Verification loop: re-run close-all if any positions remain.
                try:
                    for _ in range(3):
                        try:
                            remaining = self.shared_binance.list_open_futures_positions(force_refresh=True) or []
                        except Exception:
                            remaining = []
                        open_left = [p for p in remaining if abs(float(p.get("positionAmt") or 0.0)) > 0.0]
                        if not open_left:
                            break
                        more = _close_all_futures(self.shared_binance) or []
                        results.extend(more)
                except Exception:
                    pass
            return results
        return self.shared_binance.close_all_spot_positions()
    finally:
        if timeout_override is not None:
            for key, old_val in timeout_override.items():
                if old_val is None:
                    try:
                        os.environ.pop(key, None)
                    except Exception:
                        pass
                else:
                    os.environ[key] = old_val


def close_all_positions_async(self):
    """Close all open futures positions using reduce-only market orders in a worker."""
    try:
        from ...workers import CallWorker as _CallWorker

        auth_snapshot = self._snapshot_auth_state()
        fast_close = False
        try:
            mode_txt = str(auth_snapshot.get("mode") or "").lower()
            fast_close = any(tag in mode_txt for tag in ("demo", "test", "sandbox"))
        except Exception:
            fast_close = False

        def _do():
            return self._close_all_positions_sync(auth=auth_snapshot, fast=fast_close)

        def _done(res, err):
            if err:
                self.log(f"Close-all error: {err}")
                return
            self._handle_close_all_result(res)

        worker = _CallWorker(_do, parent=self)
        try:
            worker.progress.connect(self.log)
        except Exception:
            pass
        worker.done.connect(_done)
        if not hasattr(self, "_bg_workers"):
            self._bg_workers = []
        self._bg_workers.append(worker)

        def _cleanup():
            try:
                self._bg_workers.remove(worker)
            except Exception:
                pass

        try:
            worker.finished.connect(_cleanup)
        except Exception:
            pass
        worker.start()
    except Exception as e:
        try:
            self.log(f"Close-all setup error: {e}")
        except Exception:
            pass


def _begin_close_on_exit_sequence(self):
    if getattr(self, "_close_in_progress", False):
        return
    self._close_in_progress = True
    auth_snapshot = self._snapshot_auth_state()
    if not hasattr(self, "_bg_workers"):
        self._bg_workers = []
    try:
        from PyQt6 import QtWidgets

        message = QtWidgets.QMessageBox(self)
        message.setWindowTitle("Closing Positions")
        message.setText("Closing open positions before exit. Please wait.")
        try:
            message.setIcon(QtWidgets.QMessageBox.Icon.Information)
        except Exception:
            pass
        message.setStandardButtons(QtWidgets.QMessageBox.StandardButton.NoButton)
        message.setModal(False)
        message.show()
        self._close_progress_dialog = message
    except Exception:
        self._close_progress_dialog = None

    def _do():
        stop_strategy_sync = _STOP_STRATEGY_SYNC
        if callable(stop_strategy_sync):
            return stop_strategy_sync(self, close_positions=True, auth=auth_snapshot)
        return {"ok": False, "error": "_stop_strategy_sync is not configured"}

    def _done(res, err):
        try:
            if getattr(self, "_close_progress_dialog", None):
                self._close_progress_dialog.close()
        except Exception:
            pass
        self._close_progress_dialog = None
        self._close_in_progress = False

        def _positions_remaining() -> list:
            try:
                acct_text = str(auth_snapshot.get("account_type") or "").upper()
                if acct_text.startswith("FUT"):
                    return [
                        p
                        for p in (self.shared_binance.list_open_futures_positions(force_refresh=True) or [])
                        if abs(float(p.get("positionAmt") or 0.0)) > 0.0
                    ]
            except Exception:
                return []
            return []

        try:
            from PyQt6 import QtWidgets
        except Exception:
            QtWidgets = None

        if err:
            try:
                self.log(f"Stop error during exit: {err}")
            except Exception:
                pass
            remaining = _positions_remaining()
            if remaining and QtWidgets is not None:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Close-all failed",
                    "Some positions are still open. Please try closing them manually.",
                )
            return
        try:
            if isinstance(res, dict) and res.get("close_all_result"):
                self._handle_close_all_result(res.get("close_all_result"))
        except Exception:
            pass
        remaining = _positions_remaining()
        if remaining:
            try:
                symbols_left = ", ".join(sorted({str(p.get("symbol") or "").upper() for p in remaining}))
            except Exception:
                symbols_left = "some positions"
            if QtWidgets is not None:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Positions still open",
                    f"Could not close all positions automatically. Remaining: {symbols_left}. Please close manually.",
                )
            return
        self._force_close = True
        if QtWidgets is not None:
            QtWidgets.QWidget.close(self)
            return
        try:
            self.close()
        except Exception:
            pass

    try:
        from ...workers import CallWorker as _CallWorker

        worker = _CallWorker(_do, parent=self)
        try:
            worker.progress.connect(self.log)
        except Exception:
            pass
        worker.done.connect(_done)

        def _cleanup():
            try:
                self._bg_workers.remove(worker)
            except Exception:
                pass

        worker.finished.connect(_cleanup)
        worker.finished.connect(worker.deleteLater)
        self._bg_workers.append(worker)
        worker.start()
    except Exception as e:
        self._close_in_progress = False
        try:
            if getattr(self, "_close_progress_dialog", None):
                self._close_progress_dialog.close()
        except Exception:
            pass
        self._close_progress_dialog = None
        try:
            self.log(f"Exit close setup error: {e}")
        except Exception:
            pass


def bind_main_window_positions_tracking_runtime(
    main_window_cls,
    *,
    resolve_trigger_indicators=None,
    closed_history_max_fn=None,
    stop_strategy_sync=None,
) -> None:
    global _RESOLVE_TRIGGER_INDICATORS
    global _CLOSED_HISTORY_MAX
    global _STOP_STRATEGY_SYNC

    _RESOLVE_TRIGGER_INDICATORS = resolve_trigger_indicators
    _CLOSED_HISTORY_MAX = closed_history_max_fn
    _STOP_STRATEGY_SYNC = stop_strategy_sync

    main_window_cls._pos_symbol_keys = _mw_pos_symbol_keys
    main_window_cls._pos_interval_keys = _mw_pos_interval_keys
    main_window_cls._track_interval_open = _mw_pos_track_interval_open
    main_window_cls._track_interval_close = _mw_pos_track_interval_close
    main_window_cls._handle_close_all_result = _handle_close_all_result
    main_window_cls._apply_close_all_to_positions_cache = _apply_close_all_to_positions_cache
    main_window_cls._close_all_positions_sync = _close_all_positions_sync
    main_window_cls._close_all_positions_blocking = _close_all_positions_blocking
    main_window_cls.close_all_positions_async = close_all_positions_async
    main_window_cls._begin_close_on_exit_sequence = _begin_close_on_exit_sequence
