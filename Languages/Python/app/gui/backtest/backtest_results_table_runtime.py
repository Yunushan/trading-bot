from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets

from app.config import INDICATOR_DISPLAY_NAMES
from ..shared.helper_runtime import _safe_float, _safe_int
from ..shared.ui_support import _NumericItem
from . import backtest_results_normalize_runtime


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
    default_loop_override = backtest_results_normalize_runtime._normalize_loop_override(
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
