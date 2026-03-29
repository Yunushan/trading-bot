from __future__ import annotations

import time
from collections import deque
from datetime import datetime, timezone

from PyQt6 import QtCore


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
    try:
        self._service_record_log_event(str(msg), source="desktop-log", level="info")
    except Exception:
        pass


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
