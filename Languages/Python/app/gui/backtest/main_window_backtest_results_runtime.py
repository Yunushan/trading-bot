from __future__ import annotations

from dataclasses import asdict, is_dataclass

from PyQt6 import QtCore, QtGui, QtWidgets

from app.config import INDICATOR_DISPLAY_NAMES, MDD_LOGIC_DEFAULT, MDD_LOGIC_OPTIONS
from ..shared.main_window_helper_runtime import (
    _normalize_datetime_pair,
    _safe_float,
    _safe_int,
)
from ..shared.main_window_ui_support import _NumericItem

_MDD_LOGIC_LABELS: dict[str, str] = {}
_normalize_loop_override = lambda value: None  # type: ignore


def _select_backtest_scan_best(self, runs, mdd_limit: float):
    best = None
    best_score = None
    for run in runs or []:
        if is_dataclass(run):
            data = asdict(run)
        elif isinstance(run, dict):
            data = dict(run)
        else:
            data = {
                "symbol": getattr(run, "symbol", ""),
                "interval": getattr(run, "interval", ""),
                "indicator_keys": getattr(run, "indicator_keys", []),
                "trades": getattr(run, "trades", 0),
                "roi_percent": getattr(run, "roi_percent", 0.0),
                "roi_value": getattr(run, "roi_value", 0.0),
                "max_drawdown_percent": getattr(run, "max_drawdown_percent", 0.0),
                "mdd_logic": getattr(run, "mdd_logic", None),
            }
        try:
            trades = int(data.get("trades", 0) or 0)
        except Exception:
            trades = 0
        if trades <= 0:
            continue
        try:
            mdd = float(data.get("max_drawdown_percent", 0.0) or 0.0)
        except Exception:
            mdd = 0.0
        if mdd > mdd_limit:
            continue
        try:
            roi_pct = float(data.get("roi_percent", 0.0) or 0.0)
        except Exception:
            roi_pct = 0.0
        try:
            roi_val = float(data.get("roi_value", 0.0) or 0.0)
        except Exception:
            roi_val = 0.0
        symbol = str(data.get("symbol") or "").strip().upper()
        interval = str(data.get("interval") or "").strip()
        if not symbol or not interval:
            continue
        score = (roi_pct, roi_val, -mdd)
        if best_score is None or score > best_score:
            best_score = score
            best = {
                "symbol": symbol,
                "interval": interval,
                "roi_percent": roi_pct,
                "roi_value": roi_val,
                "max_drawdown_percent": mdd,
                "trades": trades,
                "indicator_keys": list(data.get("indicator_keys") or []),
                "mdd_logic": data.get("mdd_logic"),
            }
    return best


def _select_backtest_scan_row(
    self,
    symbol: str,
    interval: str,
    indicator_keys: list | None = None,
) -> None:
    try:
        symbol = str(symbol or "").upper()
        interval = str(interval or "")
        if not symbol or not interval:
            return
        for row in range(self.backtest_results_table.rowCount()):
            item = self.backtest_results_table.item(row, 0)
            if item is None:
                continue
            data = item.data(QtCore.Qt.ItemDataRole.UserRole) or {}
            sym_val = str(data.get("symbol") or "").upper()
            iv_val = str(data.get("interval") or "")
            if sym_val != symbol or iv_val != interval:
                continue
            if indicator_keys:
                row_keys = data.get("indicator_keys") or []
                if set(row_keys) != set(indicator_keys):
                    continue
            self.backtest_results_table.selectRow(row)
            try:
                self.backtest_results_table.scrollToItem(item)
            except Exception:
                pass
            break
    except Exception:
        pass


def _apply_backtest_scan_best(self, best: dict) -> None:
    symbol = str(best.get("symbol") or "").upper()
    interval = str(best.get("interval") or "")
    if symbol:
        self._set_backtest_symbol_selection([symbol])
    if interval:
        self._set_backtest_interval_selection([interval])
    self._select_backtest_scan_row(symbol, interval, best.get("indicator_keys"))


def _on_backtest_scan_finished(self, result: dict, error: object):
    self.backtest_scan_worker = None
    self._on_backtest_finished(result, error)
    try:
        self.backtest_scan_btn.setEnabled(True)
    except Exception:
        pass
    if error:
        return
    if not isinstance(result, dict):
        return
    runs_raw = result.get("runs", []) or []
    try:
        mdd_limit = float(getattr(self, "_backtest_scan_mdd_limit", 0.0) or 0.0)
    except Exception:
        mdd_limit = 0.0
    best = self._select_backtest_scan_best(runs_raw, mdd_limit)
    if not best:
        self.backtest_status_label.setText(
            f"Scan complete, but no runs met MDD <= {mdd_limit:.2f}% with trades."
        )
        return
    auto_apply = False
    if auto_apply:
        self._apply_backtest_scan_best(best)
    summary = (
        f"Scan best: {best['symbol']}@{best['interval']} "
        f"ROI {best['roi_percent']:+.2f}% | MDD {best['max_drawdown_percent']:.2f}% "
        f"| trades {best['trades']}"
    )
    self.backtest_status_label.setText(summary)


def _stop_backtest(self):
    try:
        worker = getattr(self, "backtest_worker", None)
        if worker and worker.isRunning():
            if hasattr(worker, "request_stop"):
                worker.request_stop()
            self.backtest_status_label.setText("Stopping backtest...")
            try:
                self.backtest_stop_btn.setEnabled(False)
            except Exception:
                pass
            return
        scan_worker = getattr(self, "backtest_scan_worker", None)
        if scan_worker and scan_worker.isRunning():
            if hasattr(scan_worker, "request_stop"):
                scan_worker.request_stop()
            self.backtest_status_label.setText("Stopping scan...")
            try:
                self.backtest_stop_btn.setEnabled(False)
            except Exception:
                pass
            return
        self.backtest_status_label.setText("No backtest running.")
    except Exception:
        pass


def _on_backtest_progress(self, msg: str):
    self.backtest_status_label.setText(str(msg))


def _normalize_backtest_run(run):
    if is_dataclass(run):
        data = asdict(run)
    elif isinstance(run, dict):
        data = dict(run)
    else:
        indicator_keys = getattr(run, "indicator_keys", [])
        if indicator_keys is None:
            indicator_keys = []
        elif not isinstance(indicator_keys, (list, tuple)):
            indicator_keys = [indicator_keys]
        data = {
            "symbol": getattr(run, "symbol", ""),
            "interval": getattr(run, "interval", ""),
            "logic": getattr(run, "logic", ""),
            "indicator_keys": list(indicator_keys),
            "trades": getattr(run, "trades", 0),
            "roi_value": getattr(run, "roi_value", 0.0),
            "roi_percent": getattr(run, "roi_percent", 0.0),
            "max_drawdown_value": getattr(run, "max_drawdown_value", 0.0),
            "max_drawdown_percent": getattr(run, "max_drawdown_percent", 0.0),
            "max_drawdown_during_value": getattr(
                run,
                "max_drawdown_during_value",
                getattr(run, "max_drawdown_value", 0.0),
            ),
            "max_drawdown_during_percent": getattr(
                run,
                "max_drawdown_during_percent",
                getattr(run, "max_drawdown_percent", 0.0),
            ),
            "max_drawdown_result_value": getattr(
                run,
                "max_drawdown_result_value",
                0.0,
            ),
            "max_drawdown_result_percent": getattr(
                run,
                "max_drawdown_result_percent",
                0.0,
            ),
            "mdd_logic": getattr(run, "mdd_logic", None),
        }
    data.setdefault("indicator_keys", [])
    keys = data.get("indicator_keys") or []
    if not isinstance(keys, (list, tuple)):
        keys = [keys]
    data["indicator_keys"] = [str(k) for k in keys if k is not None]
    try:
        data["trades"] = int(data.get("trades", 0) or 0)
    except Exception:
        data["trades"] = 0
    for key in (
        "roi_value",
        "roi_percent",
        "max_drawdown_value",
        "max_drawdown_percent",
        "max_drawdown_during_value",
        "max_drawdown_during_percent",
        "max_drawdown_result_value",
        "max_drawdown_result_percent",
    ):
        try:
            data[key] = float(data.get(key, 0.0) or 0.0)
        except Exception:
            data[key] = 0.0
    for pct_key in ("position_pct",):
        try:
            data[pct_key] = float(data.get(pct_key, 0.0) or 0.0)
        except Exception:
            data[pct_key] = 0.0
    for lev_key in ("leverage",):
        try:
            data[lev_key] = float(data.get(lev_key, 0.0) or 0.0)
        except Exception:
            data[lev_key] = 0.0
    for bool_key in ("stop_loss_enabled",):
        data[bool_key] = bool(data.get(bool_key, False))
    for str_key in (
        "symbol",
        "interval",
        "logic",
        "stop_loss_mode",
        "stop_loss_scope",
        "margin_mode",
        "position_mode",
        "assets_mode",
        "account_mode",
    ):
        val = data.get(str_key)
        data[str_key] = str(val or "").strip()
    mdd_logic_val = str(data.get("mdd_logic", "") or "").lower()
    if mdd_logic_val not in MDD_LOGIC_OPTIONS:
        mdd_logic_val = MDD_LOGIC_DEFAULT
    data["mdd_logic"] = mdd_logic_val
    data["mdd_logic_display"] = _MDD_LOGIC_LABELS.get(
        mdd_logic_val,
        mdd_logic_val.replace("_", " ").title(),
    )
    loop_raw = data.get("loop_interval_override")
    if loop_raw is None:
        if isinstance(run, dict):
            loop_raw = run.get("loop_interval_override")
        else:
            loop_raw = getattr(run, "loop_interval_override", None)
    if loop_raw is None:
        strategy_controls = data.get("strategy_controls")
        if isinstance(strategy_controls, dict):
            loop_raw = strategy_controls.get("loop_interval_override")
    loop_normalized = _normalize_loop_override(loop_raw)
    data["loop_interval_override"] = loop_normalized or ""
    start_iso, start_display = _normalize_datetime_pair(data.get("start"))
    if not start_iso and hasattr(run, "start"):
        start_iso, start_display = _normalize_datetime_pair(getattr(run, "start"))
    data["start"] = start_iso
    data["start_display"] = start_display or "-"
    end_iso, end_display = _normalize_datetime_pair(data.get("end"))
    if not end_iso and hasattr(run, "end"):
        end_iso, end_display = _normalize_datetime_pair(getattr(run, "end"))
    data["end"] = end_iso
    data["end_display"] = end_display or "-"
    pos_pct_fraction = data.get("position_pct", 0.0)
    try:
        pos_pct_fraction = float(pos_pct_fraction or 0.0)
    except Exception:
        pos_pct_fraction = 0.0
    data["position_pct"] = pos_pct_fraction
    data["position_pct_display"] = f"{max(pos_pct_fraction, 0.0) * 100.0:.2f}%"
    stop_enabled = data.get("stop_loss_enabled", False)
    stop_mode = data.get("stop_loss_mode", "")
    stop_usdt = data.get("stop_loss_usdt", 0.0)
    stop_percent = data.get("stop_loss_percent", 0.0)
    stop_scope = data.get("stop_loss_scope", "")
    try:
        stop_usdt = float(stop_usdt or 0.0)
    except Exception:
        stop_usdt = 0.0
    try:
        stop_percent = float(stop_percent or 0.0)
    except Exception:
        stop_percent = 0.0
    data["stop_loss_usdt"] = stop_usdt
    data["stop_loss_percent"] = stop_percent
    if stop_enabled:
        parts = []
        if stop_mode:
            parts.append(stop_mode)
        if stop_scope:
            parts.append(stop_scope)
        if stop_usdt > 0.0:
            parts.append(f"{stop_usdt:.2f} USDT")
        if stop_percent > 0.0:
            parts.append(f"{stop_percent:.2f}%")
        data["stop_loss_display"] = "Enabled" + (
            f" ({', '.join(parts)})" if parts else ""
        )
    else:
        data["stop_loss_display"] = "Disabled"
    if not data.get("margin_mode"):
        data["margin_mode"] = ""
    if not data.get("position_mode"):
        data["position_mode"] = ""
    if not data.get("assets_mode"):
        data["assets_mode"] = ""
    if not data.get("account_mode"):
        data["account_mode"] = ""
    data["leverage_display"] = f"{data.get('leverage', 0.0):.2f}x"
    max_dd_during_pct = data.get(
        "max_drawdown_during_percent",
        data.get("max_drawdown_percent", 0.0),
    )
    try:
        max_dd_during_pct = float(max_dd_during_pct or 0.0)
    except Exception:
        max_dd_during_pct = 0.0
    max_dd_during_val = data.get(
        "max_drawdown_during_value",
        data.get("max_drawdown_value", 0.0),
    )
    try:
        max_dd_during_val = float(max_dd_during_val or 0.0)
    except Exception:
        max_dd_during_val = 0.0
    max_dd_result_pct = data.get("max_drawdown_result_percent", 0.0)
    try:
        max_dd_result_pct = float(max_dd_result_pct or 0.0)
    except Exception:
        max_dd_result_pct = 0.0
    max_dd_result_val = data.get("max_drawdown_result_value", 0.0)
    try:
        max_dd_result_val = float(max_dd_result_val or 0.0)
    except Exception:
        max_dd_result_val = 0.0
    data["max_drawdown_percent"] = max_dd_during_pct
    data["max_drawdown_value"] = max_dd_during_val
    data["max_drawdown_during_percent"] = max_dd_during_pct
    data["max_drawdown_during_value"] = max_dd_during_val
    data["max_drawdown_result_percent"] = max_dd_result_pct
    data["max_drawdown_result_value"] = max_dd_result_val
    if max_dd_during_pct > 0.0:
        data["max_drawdown_during_display"] = f"{-abs(max_dd_during_pct):.2f}%"
    else:
        data["max_drawdown_during_display"] = "0.00%"
    if max_dd_during_val > 0.0:
        data["max_drawdown_during_value_display"] = (
            f"{-abs(max_dd_during_val):.2f} USDT"
        )
    else:
        data["max_drawdown_during_value_display"] = "0.00 USDT"
    if max_dd_result_pct > 0.0:
        data["max_drawdown_result_display"] = f"{-abs(max_dd_result_pct):.2f}%"
    else:
        data["max_drawdown_result_display"] = "0.00%"
    if max_dd_result_val > 0.0:
        data["max_drawdown_result_value_display"] = (
            f"{-abs(max_dd_result_val):.2f} USDT"
        )
    else:
        data["max_drawdown_result_value_display"] = "0.00 USDT"
    data["symbol"] = str(data.get("symbol") or "")
    data["interval"] = str(data.get("interval") or "")
    data["logic"] = str(data.get("logic") or "")
    return data


def _on_backtest_finished(self, result: dict, error: object):
    self.backtest_run_btn.setEnabled(True)
    try:
        self.backtest_stop_btn.setEnabled(False)
    except Exception:
        pass
    worker = getattr(self, "backtest_worker", None)
    if worker and worker.isRunning():
        worker.wait(100)
    self.backtest_worker = None
    if error:
        err_text = str(error) if error is not None else ""
        if isinstance(error, RuntimeError) and "backtest_cancelled" in err_text.lower():
            self.backtest_status_label.setText("Backtest cancelled.")
            return
        msg = f"Backtest failed: {error}"
        self.backtest_status_label.setText(msg)
        self.log(msg)
        return
    runs_raw = result.get("runs", []) if isinstance(result, dict) else []
    errors = result.get("errors", []) if isinstance(result, dict) else []
    run_dicts = [self._normalize_backtest_run(r) for r in (runs_raw or [])]
    default_loop_override = _normalize_loop_override(
        self.backtest_config.get("loop_interval_override")
    )
    for rd in run_dicts:
        if not rd.get("loop_interval_override"):
            rd["loop_interval_override"] = default_loop_override or ""
    self.backtest_results = run_dicts
    expected_runs = getattr(self, "_backtest_expected_runs", []) or []
    for idx, rd in enumerate(run_dicts):
        if idx < len(expected_runs):
            sym, iv, inds = expected_runs[idx]
            if not rd.get("symbol") and sym:
                rd["symbol"] = sym
            if not rd.get("interval") and iv:
                rd["interval"] = iv
            if (not rd.get("indicator_keys")) and inds:
                rd["indicator_keys"] = list(inds)
    try:
        self.log(f"Backtest returned {len(run_dicts)} run(s).")
        for idx, rd in enumerate(run_dicts):
            self.log(f"Backtest run[{idx}]: {rd}")
    except Exception:
        pass
    self._populate_backtest_results_table(run_dicts)
    summary_parts = []
    if run_dicts:
        summary_parts.append(f"{len(run_dicts)} run(s) completed")
        total_roi = sum(r.get("roi_value", 0.0) for r in run_dicts)
        summary_parts.append(f"Total ROI: {total_roi:+.2f} USDT")
        avg_roi_pct = sum(r.get("roi_percent", 0.0) for r in run_dicts) / max(
            len(run_dicts),
            1,
        )
        summary_parts.append(f"Avg ROI %: {avg_roi_pct:+.2f}%")
    if errors:
        summary_parts.append(f"{len(errors)} error(s)")
        for err in errors:
            sym = err.get("symbol")
            interval = err.get("interval")
            self.log(f"Backtest error for {sym}@{interval}: {err.get('error')}")
    if not summary_parts:
        summary_parts.append("No results generated.")
    self.backtest_status_label.setText(" | ".join(summary_parts))


def _populate_backtest_results_table(self, runs):
    try:
        rows_data = list(runs or [])
        try:
            self.backtest_results_table.setSortingEnabled(False)
        except Exception:
            pass
        try:
            self.backtest_results_table.clearContents()
        except Exception:
            pass
        self.backtest_results_table.setRowCount(len(rows_data))
        for row, run in enumerate(rows_data):
            try:
                data = self._normalize_backtest_run(run)
                symbol = data.get("symbol") or "-"
                interval = data.get("interval") or "-"
                logic = data.get("logic") or "-"
                indicator_keys = data.get("indicator_keys") or []
                trades = _safe_float(data.get("trades", 0.0), 0.0)
                roi_value = _safe_float(data.get("roi_value", 0.0), 0.0)
                roi_percent = _safe_float(data.get("roi_percent", 0.0), 0.0)
                start_display = data.get("start_display") or "-"
                end_display = data.get("end_display") or "-"
                pos_pct_display = data.get("position_pct_display") or "0.00%"
                stop_loss_display = data.get("stop_loss_display") or "Disabled"
                margin_mode = data.get("margin_mode") or "-"
                position_mode = data.get("position_mode") or "-"
                assets_mode = data.get("assets_mode") or "-"
                account_mode = data.get("account_mode") or "-"
                leverage_display = (
                    data.get("leverage_display")
                    or f"{data.get('leverage', 0.0):.2f}x"
                )
                max_drawdown_during_percent = _safe_float(
                    data.get(
                        "max_drawdown_during_percent",
                        data.get("max_drawdown_percent", 0.0),
                    ),
                    0.0,
                )
                max_drawdown_during_value = _safe_float(
                    data.get(
                        "max_drawdown_during_value",
                        data.get("max_drawdown_value", 0.0),
                    ),
                    0.0,
                )
                max_drawdown_result_percent = _safe_float(
                    data.get("max_drawdown_result_percent", 0.0),
                    0.0,
                )
                max_drawdown_result_value = _safe_float(
                    data.get("max_drawdown_result_value", 0.0),
                    0.0,
                )

                indicators_display = ", ".join(
                    INDICATOR_DISPLAY_NAMES.get(k, k) for k in indicator_keys
                ) or "-"
                item_symbol = QtWidgets.QTableWidgetItem(symbol or "-")
                try:
                    item_symbol.setData(QtCore.Qt.ItemDataRole.UserRole, dict(data))
                except Exception:
                    pass
                self.backtest_results_table.setItem(row, 0, item_symbol)
                self.backtest_results_table.setItem(
                    row,
                    1,
                    QtWidgets.QTableWidgetItem(interval or "-"),
                )
                self.backtest_results_table.setItem(
                    row,
                    2,
                    QtWidgets.QTableWidgetItem(logic or "-"),
                )
                self.backtest_results_table.setItem(
                    row,
                    3,
                    QtWidgets.QTableWidgetItem(indicators_display),
                )
                trades_display = _safe_int(trades, 0)
                trades_item = _NumericItem(str(trades_display), trades_display)
                self.backtest_results_table.setItem(row, 4, trades_item)
                loop_display = data.get("loop_interval_override") or "-"
                self.backtest_results_table.setItem(
                    row,
                    5,
                    QtWidgets.QTableWidgetItem(loop_display),
                )
                self.backtest_results_table.setItem(
                    row,
                    6,
                    QtWidgets.QTableWidgetItem(start_display or "-"),
                )
                self.backtest_results_table.setItem(
                    row,
                    7,
                    QtWidgets.QTableWidgetItem(end_display or "-"),
                )
                self.backtest_results_table.setItem(
                    row,
                    8,
                    QtWidgets.QTableWidgetItem(pos_pct_display),
                )
                self.backtest_results_table.setItem(
                    row,
                    9,
                    QtWidgets.QTableWidgetItem(stop_loss_display),
                )
                self.backtest_results_table.setItem(
                    row,
                    10,
                    QtWidgets.QTableWidgetItem(margin_mode or "-"),
                )
                self.backtest_results_table.setItem(
                    row,
                    11,
                    QtWidgets.QTableWidgetItem(position_mode or "-"),
                )
                self.backtest_results_table.setItem(
                    row,
                    12,
                    QtWidgets.QTableWidgetItem(assets_mode or "-"),
                )
                self.backtest_results_table.setItem(
                    row,
                    13,
                    QtWidgets.QTableWidgetItem(account_mode or "-"),
                )
                self.backtest_results_table.setItem(
                    row,
                    14,
                    QtWidgets.QTableWidgetItem(leverage_display),
                )
                roi_value_item = _NumericItem(f"{roi_value:+.2f}", roi_value)
                self.backtest_results_table.setItem(row, 15, roi_value_item)
                roi_percent_item = _NumericItem(f"{roi_percent:+.2f}%", roi_percent)
                self.backtest_results_table.setItem(row, 16, roi_percent_item)
                if max_drawdown_during_value > 0.0:
                    dd_during_value_for_sort = -abs(max_drawdown_during_value)
                    dd_during_value_text = f"{dd_during_value_for_sort:.2f} USDT"
                else:
                    dd_during_value_for_sort = 0.0
                    dd_during_value_text = "0.00 USDT"
                dd_during_value_item = _NumericItem(
                    dd_during_value_text,
                    dd_during_value_for_sort,
                )
                if max_drawdown_during_percent > 0.0:
                    dd_during_value_item.setToolTip(
                        f"Peak-to-trough drop while open: {max_drawdown_during_percent:.2f}%"
                    )
                self.backtest_results_table.setItem(row, 17, dd_during_value_item)
                if max_drawdown_during_percent > 0.0:
                    dd_during_for_sort = -abs(max_drawdown_during_percent)
                    dd_during_text = f"{dd_during_for_sort:.2f}%"
                else:
                    dd_during_for_sort = 0.0
                    dd_during_text = "0.00%"
                dd_during_item = _NumericItem(dd_during_text, dd_during_for_sort)
                if max_drawdown_during_value > 0.0:
                    dd_during_item.setToolTip(
                        f"Peak-to-trough drop while open: {max_drawdown_during_value:.2f} USDT"
                    )
                self.backtest_results_table.setItem(row, 18, dd_during_item)
                if max_drawdown_result_value > 0.0:
                    dd_result_value_for_sort = -abs(max_drawdown_result_value)
                    dd_result_value_text = f"{dd_result_value_for_sort:.2f} USDT"
                else:
                    dd_result_value_for_sort = 0.0
                    dd_result_value_text = "0.00 USDT"
                dd_result_value_item = _NumericItem(
                    dd_result_value_text,
                    dd_result_value_for_sort,
                )
                if max_drawdown_result_percent > 0.0:
                    dd_result_value_item.setToolTip(
                        f"Max loss on closed position: {max_drawdown_result_percent:.2f}%"
                    )
                self.backtest_results_table.setItem(row, 19, dd_result_value_item)
                if max_drawdown_result_percent > 0.0:
                    dd_result_for_sort = -abs(max_drawdown_result_percent)
                    dd_result_text = f"{dd_result_for_sort:.2f}%"
                else:
                    dd_result_for_sort = 0.0
                    dd_result_text = "0.00%"
                dd_result_item = _NumericItem(dd_result_text, dd_result_for_sort)
                if max_drawdown_result_value > 0.0:
                    dd_result_item.setToolTip(
                        f"Max loss on closed position: {max_drawdown_result_value:.2f} USDT"
                    )
                self.backtest_results_table.setItem(row, 20, dd_result_item)
            except Exception as row_exc:
                self.log(f"Backtest table row {row} error: {row_exc}")
                err_item = QtWidgets.QTableWidgetItem(f"Error: {row_exc}")
                err_item.setForeground(QtGui.QBrush(QtGui.QColor("red")))
                self.backtest_results_table.setItem(row, 0, err_item)
                for col in range(1, self.backtest_results_table.columnCount()):
                    self.backtest_results_table.setItem(
                        row,
                        col,
                        QtWidgets.QTableWidgetItem("-"),
                    )
                continue
        self.backtest_results_table.resizeRowsToContents()
    except Exception as exc:
        self.log(f"Backtest results table error: {exc}")
    finally:
        try:
            self.backtest_results_table.setSortingEnabled(True)
        except Exception:
            pass


def bind_main_window_backtest_results_runtime(
    main_window_cls,
    *,
    mdd_logic_labels: dict[str, str],
    normalize_loop_override,
) -> None:
    global _MDD_LOGIC_LABELS
    global _normalize_loop_override

    _MDD_LOGIC_LABELS = dict(mdd_logic_labels or {})
    if callable(normalize_loop_override):
        _normalize_loop_override = normalize_loop_override

    main_window_cls._select_backtest_scan_best = _select_backtest_scan_best
    main_window_cls._select_backtest_scan_row = _select_backtest_scan_row
    main_window_cls._apply_backtest_scan_best = _apply_backtest_scan_best
    main_window_cls._on_backtest_scan_finished = _on_backtest_scan_finished
    main_window_cls._stop_backtest = _stop_backtest
    main_window_cls._on_backtest_progress = _on_backtest_progress
    main_window_cls._normalize_backtest_run = staticmethod(_normalize_backtest_run)
    main_window_cls._on_backtest_finished = _on_backtest_finished
    main_window_cls._populate_backtest_results_table = _populate_backtest_results_table
