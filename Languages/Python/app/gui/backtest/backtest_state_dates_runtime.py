from __future__ import annotations

from datetime import datetime

from PyQt6 import QtCore


def coerce_qdate(value):
    if isinstance(value, QtCore.QDate):
        return value
    if isinstance(value, datetime):
        return QtCore.QDate(value.year, value.month, value.day)
    if isinstance(value, str):
        for fmt in ("yyyy-MM-dd", "yyyy/MM/dd", "dd.MM.yyyy"):
            qd = QtCore.QDate.fromString(value, fmt)
            if qd.isValid():
                return qd
        try:
            dt = datetime.fromisoformat(value)
            return QtCore.QDate(dt.year, dt.month, dt.day)
        except Exception:
            pass
    return QtCore.QDate.currentDate()


def coerce_qdatetime(value):
    if isinstance(value, QtCore.QDateTime):
        return value
    if isinstance(value, datetime):
        return QtCore.QDateTime(value)
    if isinstance(value, str):
        from datetime import datetime as _dt

        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
            try:
                dt = _dt.strptime(value, fmt)
                return QtCore.QDateTime(
                    QtCore.QDate(dt.year, dt.month, dt.day),
                    QtCore.QTime(dt.hour, dt.minute),
                )
            except Exception:
                continue
        try:
            dt = _dt.fromisoformat(value)
            return QtCore.QDateTime(
                QtCore.QDate(dt.year, dt.month, dt.day),
                QtCore.QTime(dt.hour, dt.minute),
            )
        except Exception:
            pass
    return QtCore.QDateTime.currentDateTime()


def backtest_dates_changed(self):
    try:
        start_dt = self.backtest_start_edit.dateTime().toString("dd.MM.yyyy HH:mm:ss")
        end_dt = self.backtest_end_edit.dateTime().toString("dd.MM.yyyy HH:mm:ss")
        self.backtest_config["start_date"] = start_dt
        self.backtest_config["end_date"] = end_dt
        cfg = self.config.setdefault("backtest", {})
        cfg["start_date"] = start_dt
        cfg["end_date"] = end_dt
    except Exception:
        pass

