from __future__ import annotations

import os
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from PyQt6 import QtCore, QtWidgets

from . import window_runtime

_STRATEGY_ENGINE_CLS = None
_NUMERIC_ITEM_CLS = None
_WAITING_POSITION_LATE_THRESHOLD = 45.0


def _request_strategy_shutdown() -> None:
    strategy_engine_cls = _STRATEGY_ENGINE_CLS
    if strategy_engine_cls is None:
        return
    try:
        strategy_engine_cls.request_shutdown()
    except Exception:
        pass


def _teardown_positions_thread(self):
    try:
        if getattr(self, "_pos_worker", None) is not None:
            try:
                self.req_pos_stop.emit()
            except Exception:
                pass
        if getattr(self, "_pos_thread", None) is not None:
            try:
                self._pos_thread.quit()
                self._pos_thread.wait(2000)
            except Exception:
                pass
        self._pos_worker = None
        self._pos_thread = None
    except Exception:
        pass


def _log_window_event(self, name: str, event=None) -> None:
    try:
        visible = int(bool(self.isVisible()))
    except Exception:
        visible = -1
    try:
        minimized = int(bool(self.windowState() & QtCore.Qt.WindowState.WindowMinimized))
    except Exception:
        minimized = -1
    try:
        spontaneous = int(bool(event.spontaneous())) if event is not None else -1
    except Exception:
        spontaneous = -1
    try:
        now = time.monotonic()
    except Exception:
        now = 0.0
    try:
        we_active = int(bool(getattr(self, "_webengine_close_guard_active", False)))
    except Exception:
        we_active = -1
    try:
        we_until = float(getattr(self, "_webengine_close_guard_until", 0.0) or 0.0)
    except Exception:
        we_until = 0.0
    try:
        we_rem_ms = int(max(0.0, (we_until - now) * 1000.0)) if we_until else 0
    except Exception:
        we_rem_ms = -1
    msg = (
        f"window_event {name} visible={visible} minimized={minimized} spontaneous={spontaneous} "
        f"we_guard={we_active} we_rem_ms={we_rem_ms}"
    )
    try:
        logger = getattr(self, "_chart_debug_log", None)
        if callable(logger):
            logger(msg)
            return
    except Exception:
        pass
    try:
        path = Path(os.getenv("TEMP") or ".").resolve() / "binance_chart_debug.log"
        with open(path, "a", encoding="utf-8", errors="ignore") as fh:
            fh.write(f"[{datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %z')}] {msg}\n")
    except Exception:
        pass


def _allow_guard_bypass(self) -> bool:
    try:
        if (
            bool(getattr(self, "_force_close", False))
            or bool(getattr(self, "_close_in_progress", False))
            or bool(getattr(self, "_cpp_launch_handoff_active", False))
            or bool(getattr(self, "_rust_launch_handoff_active", False))
        ):
            return True
    except Exception:
        pass
    try:
        app = QtWidgets.QApplication.instance()
    except Exception:
        app = None
    try:
        if app is not None and bool(getattr(app, "_exiting", False)):
            return True
    except Exception:
        pass
    return False


def _mark_user_close_command(self) -> None:
    try:
        self._last_user_close_command_ts = time.monotonic()
    except Exception:
        self._last_user_close_command_ts = 0.0


def _is_recent_user_close_command(self) -> bool:
    try:
        last_ts = float(getattr(self, "_last_user_close_command_ts", 0.0) or 0.0)
    except Exception:
        last_ts = 0.0
    if last_ts <= 0.0:
        return False
    try:
        ttl_ms = int(os.environ.get("BOT_USER_CLOSE_BYPASS_MS") or 1800)
    except Exception:
        ttl_ms = 1800
    ttl_ms = max(300, min(ttl_ms, 10000))
    try:
        return (time.monotonic() - last_ts) * 1000.0 <= ttl_ms
    except Exception:
        return False


def _restore_window_after_guard(self) -> None:
    return window_runtime.restore_window_after_guard(self)


def _active_close_protection_until(self) -> float:
    try:
        now = time.monotonic()
    except Exception:
        now = 0.0

    try:
        tv_active = bool(getattr(self, "_tv_close_guard_active", False))
    except Exception:
        tv_active = False
    try:
        tv_until = float(getattr(self, "_tv_close_guard_until", 0.0) or 0.0)
    except Exception:
        tv_until = 0.0
    if tv_active and tv_until and now >= tv_until:
        try:
            self._tv_close_guard_active = False
        except Exception:
            pass
        tv_active = False
        tv_until = 0.0

    try:
        we_active = bool(getattr(self, "_webengine_close_guard_active", False))
    except Exception:
        we_active = False
    try:
        we_until = float(getattr(self, "_webengine_close_guard_until", 0.0) or 0.0)
    except Exception:
        we_until = 0.0
    if we_active and we_until and now >= we_until:
        try:
            self._webengine_close_guard_active = False
        except Exception:
            pass
        we_active = False
        we_until = 0.0

    active_until = 0.0
    if tv_active and tv_until > active_until:
        active_until = tv_until
    if we_active and we_until > active_until:
        active_until = we_until
    return active_until


def _should_block_programmatic_hide(self) -> bool:
    if _allow_guard_bypass(self):
        return False
    try:
        now = time.monotonic()
    except Exception:
        now = 0.0
    guard_until = _active_close_protection_until(self)
    return bool(guard_until and now < guard_until and not _is_recent_user_close_command(self))


def setVisible(self, visible):  # noqa: N802, ANN001
    make_visible = bool(visible)
    if not make_visible and _should_block_programmatic_hide(self):
        try:
            logger = getattr(self, "_chart_debug_log", None)
            if callable(logger):
                logger("window_event setVisible_blocked visible=0 reason=webengine_guard")
        except Exception:
            pass
        _restore_window_after_guard(self)
        return
    try:
        super(type(self), self).setVisible(visible)
    except Exception:
        pass


def hide(self):  # noqa: ANN001
    if _should_block_programmatic_hide(self):
        try:
            logger = getattr(self, "_chart_debug_log", None)
            if callable(logger):
                logger("window_event hide_blocked reason=webengine_guard")
        except Exception:
            pass
        _restore_window_after_guard(self)
        return
    try:
        super(type(self), self).hide()
    except Exception:
        pass


def nativeEvent(self, eventType, message):  # noqa: N802, ANN001
    if sys.platform == "win32":
        detect_flag = str(os.environ.get("BOT_ENABLE_NATIVE_CLOSE_DETECT", "")).strip().lower()
        if detect_flag not in {"1", "true", "yes", "on"}:
            try:
                return super(type(self), self).nativeEvent(eventType, message)
            except Exception:
                return False, 0
        try:
            et = ""
            try:
                et = bytes(eventType).decode("utf-8", "ignore").strip().lower()
            except Exception:
                try:
                    et = str(eventType).strip().lower()
                except Exception:
                    et = ""
            if et not in {"windows_generic_msg", "windows_dispatcher_msg"}:
                raise RuntimeError("unsupported native event type")
            import ctypes
            import ctypes.wintypes as wintypes

            wm_syscommand = 0x0112
            sc_close = 0xF060
            msg_ptr = int(message)
            if msg_ptr and msg_ptr > 0x10000:
                msg_obj = ctypes.cast(msg_ptr, ctypes.POINTER(wintypes.MSG)).contents
                if int(msg_obj.message) == wm_syscommand:
                    cmd = int(msg_obj.wParam) & 0xFFF0
                    if cmd == sc_close:
                        _mark_user_close_command(self)
        except Exception:
            pass
    try:
        return super(type(self), self).nativeEvent(eventType, message)
    except Exception:
        return False, 0


def closeEvent(self, event):
    try:
        _log_window_event(self, "closeEvent", event=event)
    except Exception:
        pass
    close_guard = getattr(self, "_close_in_progress", False)
    if close_guard:
        event.ignore()
        return
    if getattr(self, "_force_close", False):
        self._force_close = False
        _request_strategy_shutdown()
        try:
            _teardown_positions_thread(self)
        except Exception:
            pass
        try:
            self._mark_session_inactive()
        except Exception:
            pass
        try:
            super(type(self), self).closeEvent(event)
        except Exception:
            try:
                event.accept()
            except Exception:
                pass
        try:
            app = QtWidgets.QApplication.instance()
            if app is not None:
                setattr(app, "_exiting", True)
                arm_hard_exit = getattr(app, "_bot_arm_hard_exit", None)
                if callable(arm_hard_exit):
                    arm_hard_exit()
                app.quit()
        except Exception:
            pass
        return
    if not _allow_guard_bypass(self):
        try:
            now = time.monotonic()
        except Exception:
            now = 0.0
        guard_until = _active_close_protection_until(self)
        if guard_until and now < guard_until:
            if _is_recent_user_close_command(self):
                try:
                    self._last_user_close_command_ts = 0.0
                except Exception:
                    pass
                try:
                    self._webengine_close_guard_active = False
                    self._tv_close_guard_active = False
                except Exception:
                    pass
            else:
                event.ignore()
                _restore_window_after_guard(self)
                return

    _request_strategy_shutdown()
    try:
        app = QtWidgets.QApplication.instance()
        if app is not None:
            setattr(app, "_exiting", True)
            arm_hard_exit = getattr(app, "_bot_arm_hard_exit", None)
            if callable(arm_hard_exit):
                arm_hard_exit()
    except Exception:
        pass

    close_on_exit_enabled = bool(getattr(self, "cb_close_on_exit", None) and self.cb_close_on_exit.isChecked())
    if close_on_exit_enabled:
        event.ignore()
        self._begin_close_on_exit_sequence()
        return

    try:
        self.stop_strategy_async(close_positions=close_on_exit_enabled, blocking=True)
    except Exception:
        pass
    try:
        _teardown_positions_thread(self)
    except Exception:
        pass
    try:
        self._mark_session_inactive()
    except Exception:
        pass
    try:
        super(type(self), self).closeEvent(event)
    except Exception:
        try:
            event.accept()
        except Exception:
            pass
    try:
        if event.isAccepted():
            app = QtWidgets.QApplication.instance()
            if app is not None:
                arm_hard_exit = getattr(app, "_bot_arm_hard_exit", None)
                if callable(arm_hard_exit):
                    arm_hard_exit()
                app.quit()
    except Exception:
        pass


def hideEvent(self, event):  # noqa: N802
    try:
        _log_window_event(self, "hideEvent", event=event)
    except Exception:
        pass
    if not _allow_guard_bypass(self):
        try:
            now = time.monotonic()
        except Exception:
            now = 0.0
        guard_until = _active_close_protection_until(self)
        if guard_until and now < guard_until:
            if not _is_recent_user_close_command(self):
                try:
                    event.ignore()
                except Exception:
                    pass
                _restore_window_after_guard(self)
                return
    try:
        super(type(self), self).hideEvent(event)
    except Exception:
        try:
            event.accept()
        except Exception:
            pass


def _gui_setup_log_buffer(self):
    self._log_buf = deque(maxlen=8000)
    self._log_timer = QtCore.QTimer(self)
    self._log_timer.setInterval(200)
    self._log_timer.timeout.connect(self._flush_log_buffer)
    self._log_timer.start()


def _gui_buffer_log(self, msg: str):
    try:
        self._log_buf.append(msg)
    except Exception:
        pass


def _mw_reconfigure_positions_worker(self, symbols=None):
    try:
        worker = getattr(self, "_pos_worker", None)
        if worker is None:
            return

        selected_symbols: list[str] = []
        try:
            symbol_list = getattr(self, "symbol_list", None)
            if symbol_list is not None:
                for idx in range(symbol_list.count()):
                    item = symbol_list.item(idx)
                    if item is None or not item.isSelected():
                        continue
                    text = str(item.text() or "").strip().upper()
                    if text:
                        selected_symbols.append(text)
        except Exception:
            selected_symbols = []

        extra_symbols: list[str] = []
        if symbols:
            for sym in symbols:
                try:
                    text = str(sym or "").strip().upper()
                except Exception:
                    text = ""
                if text:
                    extra_symbols.append(text)

        def _dedupe(seq: list[str]) -> list[str]:
            return list(dict.fromkeys(seq))

        selected_symbols = _dedupe(selected_symbols)
        extra_symbols = _dedupe(extra_symbols)

        if selected_symbols:
            target_symbols = _dedupe(selected_symbols + extra_symbols)
        else:
            target_symbols = None

        worker.configure(
            api_key=self.api_key_edit.text().strip(),
            api_secret=self.api_secret_edit.text().strip(),
            mode=self.mode_combo.currentText(),
            account_type=self.account_combo.currentText(),
            symbols=target_symbols or None,
            connector_backend=self._runtime_connector_backend(suppress_refresh=True),
        )
        setattr(self, "_pos_symbol_filter", target_symbols)
    except Exception:
        pass


def _mw_collect_strategy_intervals(self, symbol: str, side_key: str):
    intervals = set()
    try:
        engines = getattr(self, "strategy_engines", {}) or {}
        sym_upper = (symbol or "").upper()
        side_key_upper = (side_key or "").upper()
        for eng in engines.values():
            cfg = getattr(eng, "config", {}) or {}
            cfg_sym = str(cfg.get("symbol") or "").upper()
            if not cfg_sym or cfg_sym != sym_upper:
                continue
            interval = str(cfg.get("interval") or "").strip()
            if not interval:
                continue
            side_pref = str(cfg.get("side") or "BOTH").upper()
            if side_pref in ("BUY", "LONG"):
                allowed = {"L"}
            elif side_pref in ("SELL", "SHORT"):
                allowed = {"S"}
            else:
                allowed = {"L", "S"}
            if side_key_upper in allowed:
                intervals.add(interval)
    except Exception:
        pass
    return intervals


def _mw_parse_any_datetime(self, value):
    if value is None:
        return None
    if isinstance(value, datetime):
        try:
            return value.astimezone() if value.tzinfo else value
        except Exception:
            return value
    if isinstance(value, (int, float)):
        try:
            raw = float(value)
            if raw > 1e12:
                raw /= 1000.0
            return datetime.fromtimestamp(raw, tz=timezone.utc).astimezone()
        except Exception:
            pass
    try:
        s = str(value).strip()
    except Exception:
        return None
    if not s:
        return None
    s_norm = s.replace("/", "-")
    patterns = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%d-%m-%Y %H:%M:%S",
        "%d.%m.%Y %H:%M:%S",
    )
    for fmt in patterns:
        try:
            dt = datetime.strptime(s_norm, fmt)
            if fmt.endswith("Z"):
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone() if dt.tzinfo else dt
        except Exception:
            continue
    try:
        dt = datetime.fromisoformat(s_norm.replace("Z", "+00:00"))
        return dt.astimezone() if dt.tzinfo else dt
    except Exception:
        return None


def _mw_format_display_time(self, value):
    dt = _mw_parse_any_datetime(self, value)
    if dt is None:
        try:
            return str(value) if value not in (None, "") else "-"
        except Exception:
            return "-"
    try:
        if getattr(dt, "tzinfo", None):
            dt = dt.astimezone()
    except Exception:
        pass
    return dt.strftime("%d.%m.%Y %H:%M:%S")


def _mw_interval_sort_key(label: str):
    try:
        lbl = (label or "").strip().lower()
        if not lbl:
            return (float("inf"), "")
        import re as _re

        match = _re.match(r"(\d+(?:\.\d+)?)([smhdw]?)", lbl)
        if not match:
            return (float("inf"), lbl)
        value = float(match.group(1))
        unit = match.group(2) or "m"
        factor = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}.get(unit, 60)
        return (value * factor, lbl)
    except Exception:
        return (float("inf"), str(label))


def _is_trigger_log_line(raw_text: str) -> bool:
    try:
        text = str(raw_text or "")
    except Exception:
        text = ""
    low = text.lower()
    if not low:
        return False
    trigger_tokens = (
        "signal=buy",
        "signal=sell",
        "-> buy",
        "-> sell",
        "'side': 'buy",
        '"side": "buy',
        "'side': 'sell",
        '"side": "sell',
        "liquidat",
        "triggered buy",
        "triggered sell",
    )
    if any(token in low for token in trigger_tokens):
        return True
    if "trade update" in low and (" buy" in low or " sell" in low):
        return True
    return False


def _gui_flush_log_buffer(self):
    try:
        if not hasattr(self, "_log_buf") or not self._log_buf:
            return
        lines = []
        for _ in range(300):
            if not self._log_buf:
                break
            lines.append(self._log_buf.popleft())
        if not lines:
            return
        import re as _re

        pat = _re.compile(r"^\[?(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]?\s*(.*)$")
        pat2 = _re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*(.*)$")
        formatted = []
        formatted_triggers = []
        for raw in lines:
            line = str(raw)
            match = pat.match(line)
            if match:
                iso_ts, rest = match.groups()
                body = rest.strip()
                nested = pat2.match(body)
                if nested:
                    body = nested.group(2).strip()
                try:
                    ts = datetime.strptime(iso_ts, "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y %H:%M:%S")
                except Exception:
                    ts = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
                formatted.append(f"[{ts}] {body}" if body else f"[{ts}]")
            else:
                ts = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
                formatted.append(f"[{ts}] {line}")
            if _is_trigger_log_line(line):
                formatted_triggers.append(formatted[-1])
        text = "\n".join(formatted)
        try:
            self.log_edit.appendPlainText(text)
        except Exception:
            self.log_edit.append(text)
        self.log_edit.verticalScrollBar().setValue(self.log_edit.verticalScrollBar().maximum())
        if formatted_triggers:
            target = getattr(self, "log_triggers_edit", None)
            if target is not None:
                trigger_text = "\n".join(formatted_triggers)
                try:
                    target.appendPlainText(trigger_text)
                except Exception:
                    try:
                        target.insertPlainText(trigger_text + "\n")
                    except Exception:
                        pass
                try:
                    target.verticalScrollBar().setValue(target.verticalScrollBar().maximum())
                except Exception:
                    pass
    except Exception:
        pass


def _mw_refresh_waiting_positions_tab(self):
    table = getattr(self, "waiting_pos_table", None)
    if table is None:
        return
    history = getattr(self, "_waiting_positions_history", None)
    if not isinstance(history, list):
        history = []
        self._waiting_positions_history = history
    last_snapshot = getattr(self, "_waiting_positions_last_snapshot", None)
    if not isinstance(last_snapshot, dict):
        last_snapshot = {}
        self._waiting_positions_last_snapshot = last_snapshot
    history_max = getattr(self, "_waiting_positions_history_max", None)
    try:
        history_max = int(history_max)
    except Exception:
        history_max = 500
    if history_max <= 0:
        history_max = 500
    self._waiting_positions_history_max = history_max
    try:
        guard = getattr(self, "guard", None)
    except Exception:
        guard = None
    snapshot = []
    snapshot_ok = False
    if guard is not None and hasattr(guard, "snapshot_pending_attempts"):
        try:
            raw = guard.snapshot_pending_attempts() or []
            snapshot = [item for item in raw if isinstance(item, dict)]
            snapshot_ok = True
        except Exception:
            snapshot = []
            snapshot_ok = False
    current_entries = []
    current_keys = set()
    for item in snapshot:
        symbol = str(item.get("symbol") or "").upper() or "-"
        interval_raw = str(item.get("interval") or "").strip()
        interval = interval_raw.upper() if interval_raw else "-"
        side_raw = str(item.get("side") or "").upper()
        if side_raw in ("L", "LONG"):
            side = "BUY"
        elif side_raw in ("S", "SHORT"):
            side = "SELL"
        else:
            side = side_raw or "-"
        context = str(item.get("context") or "")
        try:
            age_val = float(item.get("age") or 0.0)
        except Exception:
            age_val = 0.0
        age_seconds = max(0, int(age_val))
        state = "Late" if age_val >= _WAITING_POSITION_LATE_THRESHOLD else "Queued"
        key = (symbol, interval, side, context)
        current_entries.append(
            {
                "symbol": symbol,
                "interval": interval,
                "side": side,
                "context": context,
                "age": age_val,
                "age_seconds": age_seconds,
                "state": state,
                "key": key,
            }
        )
        current_keys.add(key)
    if snapshot_ok:
        ended_keys = set(last_snapshot.keys()) - current_keys
        if ended_keys:
            now = time.time()
            for key in ended_keys:
                ended_entry = last_snapshot.get(key)
                if not isinstance(ended_entry, dict):
                    continue
                ended_copy = dict(ended_entry)
                ended_copy["state"] = "Ended"
                ended_copy["ended_at"] = now
                history.append(ended_copy)
        if len(history) > history_max:
            history = history[-history_max:]
            self._waiting_positions_history = history
        self._waiting_positions_last_snapshot = {entry["key"]: entry for entry in current_entries}
    combined_entries = current_entries + history
    table.setSortingEnabled(False)
    table.setRowCount(len(combined_entries))
    if not combined_entries:
        table.clearContents()
        table.setSortingEnabled(True)
        return
    try:
        combined_entries.sort(
            key=lambda item: (
                1 if str(item.get("state") or "").lower() == "ended" else 0,
                -float(str(item.get("age") or 0.0)),
                str(item.get("symbol") or ""),
            )
        )
    except Exception:
        pass
    for row, item in enumerate(combined_entries):
        symbol = str(item.get("symbol") or "").upper() or "-"
        interval_raw = str(item.get("interval") or "").strip()
        interval = interval_raw.upper() if interval_raw else "-"
        side_raw = str(item.get("side") or "").upper()
        if side_raw in ("L", "LONG"):
            side = "BUY"
        elif side_raw in ("S", "SHORT"):
            side = "SELL"
        else:
            side = side_raw or "-"
        context = str(item.get("context") or "")
        try:
            age_val = float(item.get("age") or 0.0)
        except Exception:
            age_val = 0.0
        try:
            age_seconds = int(item.get("age_seconds"))
        except Exception:
            age_seconds = max(0, int(age_val))
        state = str(item.get("state") or "")
        if not state:
            state = "Late" if age_val >= _WAITING_POSITION_LATE_THRESHOLD else "Queued"

        symbol_item = QtWidgets.QTableWidgetItem(symbol)
        symbol_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        table.setItem(row, 0, symbol_item)

        interval_item = QtWidgets.QTableWidgetItem(interval)
        interval_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        table.setItem(row, 1, interval_item)

        side_item = QtWidgets.QTableWidgetItem(side.title() if side not in ("-", "") else "-")
        side_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        table.setItem(row, 2, side_item)

        context_item = QtWidgets.QTableWidgetItem(context or "-")
        table.setItem(row, 3, context_item)

        state_item = QtWidgets.QTableWidgetItem(state)
        state_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        table.setItem(row, 4, state_item)

        try:
            age_item = _NUMERIC_ITEM_CLS(f"{age_seconds}", age_val)
        except Exception:
            age_item = QtWidgets.QTableWidgetItem(f"{age_seconds}")
        table.setItem(row, 5, age_item)
    table.setSortingEnabled(True)


def bind_main_window_runtime(
    main_window_cls,
    *,
    strategy_engine_cls,
    numeric_item_cls=None,
    waiting_position_late_threshold: float = 45.0,
) -> None:
    global _STRATEGY_ENGINE_CLS, _NUMERIC_ITEM_CLS, _WAITING_POSITION_LATE_THRESHOLD

    _STRATEGY_ENGINE_CLS = strategy_engine_cls
    _NUMERIC_ITEM_CLS = numeric_item_cls
    _WAITING_POSITION_LATE_THRESHOLD = float(waiting_position_late_threshold)

    main_window_cls._teardown_positions_thread = _teardown_positions_thread
    main_window_cls._log_window_event = _log_window_event
    main_window_cls._allow_guard_bypass = _allow_guard_bypass
    main_window_cls._mark_user_close_command = _mark_user_close_command
    main_window_cls._is_recent_user_close_command = _is_recent_user_close_command
    main_window_cls._restore_window_after_guard = _restore_window_after_guard
    main_window_cls._active_close_protection_until = _active_close_protection_until
    main_window_cls._should_block_programmatic_hide = _should_block_programmatic_hide
    main_window_cls.setVisible = setVisible
    main_window_cls.hide = hide
    if str(os.environ.get("BOT_ENABLE_NATIVE_CLOSE_DETECT", "")).strip().lower() in {"1", "true", "yes", "on"}:
        main_window_cls.nativeEvent = nativeEvent
    main_window_cls.closeEvent = closeEvent
    main_window_cls.hideEvent = hideEvent
    main_window_cls._setup_log_buffer = _gui_setup_log_buffer
    main_window_cls._buffer_log = _gui_buffer_log
    main_window_cls._reconfigure_positions_worker = _mw_reconfigure_positions_worker
    main_window_cls._collect_strategy_intervals = _mw_collect_strategy_intervals
    main_window_cls._parse_any_datetime = _mw_parse_any_datetime
    main_window_cls._format_display_time = _mw_format_display_time
    main_window_cls._flush_log_buffer = _gui_flush_log_buffer
    main_window_cls._refresh_waiting_positions_tab = _mw_refresh_waiting_positions_tab
