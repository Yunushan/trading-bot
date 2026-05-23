from __future__ import annotations

from . import backtest_optimizer_runtime
from .backtest_service_execution_runtime import stop_service_backtest


def _select_backtest_scan_best(
    self,
    runs,
    mdd_limit: float,
    metric: str = "roi_percent",
    min_trades: int = 1,
):
    ranked = backtest_optimizer_runtime.rank_optimizer_runs(
        runs,
        metric=metric,
        mdd_limit=mdd_limit,
        min_trades=min_trades,
    )
    for data in ranked:
        if not data.get("optimizer_eligible"):
            continue
        symbol = str(data.get("symbol") or "").strip().upper()
        interval = str(data.get("interval") or "").strip()
        if not symbol or not interval:
            continue
        return {
            "symbol": symbol,
            "interval": interval,
            "roi_percent": float(data.get("roi_percent", 0.0) or 0.0),
            "roi_value": float(data.get("roi_value", 0.0) or 0.0),
            "max_drawdown_percent": float(data.get("max_drawdown_percent", 0.0) or 0.0),
            "trades": int(data.get("trades", 0) or 0),
            "indicator_keys": list(data.get("indicator_keys") or []),
            "mdd_logic": data.get("mdd_logic"),
            "optimizer_rank": data.get("optimizer_rank"),
            "optimizer_primary_score": data.get("optimizer_primary_score"),
        }
    return None


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
    try:
        self.backtest_run_btn.setEnabled(True)
    except Exception:
        pass
    try:
        self.backtest_stop_btn.setEnabled(False)
    except Exception:
        pass
    try:
        self.backtest_scan_btn.setEnabled(True)
    except Exception:
        pass
    try:
        self._refresh_backtest_optimizer_estimate()
    except Exception:
        pass
    if error:
        err_text = str(error) if error is not None else ""
        if isinstance(error, RuntimeError) and "backtest_cancelled" in err_text.lower():
            self.backtest_status_label.setText("Backtest scan cancelled.")
            return
        msg = f"Backtest scan failed: {error}"
        self.backtest_status_label.setText(msg)
        self.log(msg)
        return
    if not isinstance(result, dict):
        return
    runs_raw = result.get("runs", []) or []
    errors = result.get("errors", []) or []
    try:
        mdd_limit = float(getattr(self, "_backtest_scan_mdd_limit", 0.0) or 0.0)
    except Exception:
        mdd_limit = 0.0
    metric = backtest_optimizer_runtime.normalize_optimizer_metric(
        getattr(self, "_backtest_scan_optimizer_metric", None)
        or self.backtest_config.get("optimizer_metric", "roi_percent")
    )
    mode = backtest_optimizer_runtime.normalize_optimizer_mode(
        getattr(self, "_backtest_scan_optimizer_mode", None)
        or self.backtest_config.get("optimizer_mode", "current")
    )
    scope = backtest_optimizer_runtime.normalize_scan_scope(
        getattr(self, "_backtest_scan_scope", None)
        or self.backtest_config.get("scan_scope", "selected")
    )
    run_count_raw = getattr(self, "_backtest_scan_run_count", None)
    try:
        run_count = int(run_count_raw) if run_count_raw is not None else None
    except Exception:
        run_count = None
    try:
        min_trades = int(
            getattr(self, "_backtest_scan_optimizer_min_trades", None)
            if getattr(self, "_backtest_scan_optimizer_min_trades", None) is not None
            else self.backtest_config.get("optimizer_min_trades", 1)
        )
    except Exception:
        min_trades = 1
    runs_for_ranking = runs_raw
    has_engine_rank = False
    try:
        first_run = next(iter(runs_for_ranking), None)
        first_data = (
            backtest_optimizer_runtime.run_to_mapping(first_run)
            if first_run is not None
            else {}
        )
        has_engine_rank = first_data.get("optimizer_rank") is not None or first_data.get("optimizer_candidate_count") is not None
    except Exception:
        has_engine_rank = False
    if has_engine_rank:
        ranked_runs = [
            backtest_optimizer_runtime.run_to_mapping(run)
            for run in (runs_for_ranking or [])
        ]
        ranked_runs.sort(
            key=lambda row: int(row.get("optimizer_rank") or 1_000_000)
        )
    else:
        ranked_runs = backtest_optimizer_runtime.rank_optimizer_runs(
            runs_for_ranking,
            metric=metric,
            mdd_limit=mdd_limit,
            min_trades=min_trades,
            mode=mode,
            scope=scope,
            run_count=run_count,
            max_rows=backtest_optimizer_runtime.MAX_BACKTEST_OPTIMIZER_TABLE_ROWS,
        )
    if ranked_runs:
        self.backtest_results = ranked_runs
        self._populate_backtest_results_table(ranked_runs)
        try:
            self.backtest_results_table.sortItems(5)
        except Exception:
            pass
    best = self._select_backtest_scan_best(
        ranked_runs,
        mdd_limit,
        metric=metric,
        min_trades=min_trades,
    )
    first_ranked = ranked_runs[0] if ranked_runs else {}
    try:
        eligible_count = int(first_ranked.get("optimizer_eligible_count"))
    except Exception:
        eligible_count = sum(1 for run in ranked_runs if run.get("optimizer_eligible"))
    try:
        filtered_count = int(first_ranked.get("optimizer_filtered_count"))
    except Exception:
        filtered_count = max(0, int(run_count or len(ranked_runs)) - eligible_count)
    try:
        candidate_count = int(first_ranked.get("optimizer_candidate_count"))
    except Exception:
        candidate_count = int(run_count or len(ranked_runs))
    shown_count = len(ranked_runs)
    for err in errors:
        try:
            sym = err.get("symbol")
            interval = err.get("interval")
            self.log(f"Backtest scan error for {sym}@{interval}: {err.get('error')}")
        except Exception:
            pass
    if not best:
        mdd_text = f"MDD <= {mdd_limit:.2f}%" if mdd_limit > 0 else "no MDD limit"
        self.backtest_status_label.setText(
            f"Scan complete, but no runs met {mdd_text} and min trades {min_trades}; "
            f"{filtered_count} filtered. Showing {shown_count}/{candidate_count} row(s)."
        )
        return
    auto_apply = False
    if auto_apply:
        self._apply_backtest_scan_best(best)
    metric_label = backtest_optimizer_runtime.option_label(
        backtest_optimizer_runtime.OPTIMIZER_METRIC_OPTIONS,
        metric,
    )
    summary = (
        f"Scan best by {metric_label}: {best['symbol']}@{best['interval']} "
        f"ROI {best['roi_percent']:+.2f}% | MDD {best['max_drawdown_percent']:.2f}% "
        f"| trades {best['trades']} | eligible {eligible_count}, filtered {filtered_count}"
    )
    if shown_count < candidate_count:
        summary += f" | showing top {shown_count}/{candidate_count}"
    if errors:
        summary += f" | {len(errors)} error(s)"
    self.backtest_status_label.setText(summary)


def _stop_backtest(self):
    try:
        if stop_service_backtest(self):
            return
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
