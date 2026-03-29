from __future__ import annotations

from dataclasses import asdict, is_dataclass


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
            data = item.data(0x0100) or {}
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
