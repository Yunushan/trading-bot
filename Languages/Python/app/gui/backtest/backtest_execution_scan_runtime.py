from __future__ import annotations

import copy
import traceback

from app.core.backtest import BacktestEngine, BacktestRequest, IndicatorDefinition

from . import backtest_optimizer_runtime
from .backtest_execution_context_runtime import (
    get_backtest_worker_cls,
    get_symbol_fetch_top_n,
    normalize_backtest_stop_loss_dict,
)


def _selected_backtest_symbol_values(self) -> list[str]:
    values = [str(item or "").strip().upper() for item in (self.backtest_config.get("symbols") or []) if str(item or "").strip()]
    if values:
        return values
    symbol_list = getattr(self, "backtest_symbol_list", None)
    if symbol_list is None:
        return []
    try:
        return [str(item.text() or "").strip().upper() for item in symbol_list.selectedItems() if str(item.text() or "").strip()]
    except Exception:
        return []


def run_backtest_scan(self):
    try:
        if self.backtest_worker and self.backtest_worker.isRunning():
            self.backtest_status_label.setText(
                "Backtest running; stop it before scanning."
            )
            return
        scan_worker = getattr(self, "backtest_scan_worker", None)
        if scan_worker is not None and scan_worker.isRunning():
            self.backtest_status_label.setText("Scan already running...")
            return

        symbols_all = list(self.backtest_symbols_all or [])
        scope_value = getattr(self, "backtest_scan_scope_combo", None)
        if scope_value is not None:
            scan_scope = backtest_optimizer_runtime.normalize_scan_scope(scope_value.currentData())
        else:
            scan_scope = backtest_optimizer_runtime.normalize_scan_scope(
                self.backtest_config.get("scan_scope", "selected")
            )
        self._update_backtest_config("scan_scope", scan_scope)

        if scan_scope != "selected" and not symbols_all:
            self.backtest_status_label.setText(
                "No symbols loaded. Click Refresh Symbols first."
            )
            return
        try:
            top_n = int(self.backtest_scan_top_spin.value())
        except Exception:
            top_n = int(
                self.backtest_config.get("scan_top_n", get_symbol_fetch_top_n())
                or get_symbol_fetch_top_n()
            )
        if top_n <= 0:
            self.backtest_status_label.setText("Scan Top N must be at least 1.")
            return
        if scan_scope == "top_n" and len(symbols_all) < top_n:
            self.backtest_status_label.setText(
                f"Only {len(symbols_all)} symbols loaded; lower Scan Top N or refresh."
            )
            return
        selected_symbols = _selected_backtest_symbol_values(self)
        symbols = backtest_optimizer_runtime.resolve_scan_symbols(
            symbols_all=symbols_all,
            selected_symbols=selected_symbols,
            scope=scan_scope,
            top_n=top_n,
        )
        if not symbols:
            if scan_scope == "selected":
                self.backtest_status_label.setText(
                    "Select at least one Backtest symbol or change optimizer scope."
                )
            else:
                self.backtest_status_label.setText("No symbols available for optimizer scan.")
            return

        intervals = [iv for iv in (self.backtest_config.get("intervals") or []) if iv]
        if not intervals:
            self.backtest_status_label.setText(
                "Select at least one interval to scan."
            )
            return

        indicators_cfg = self.backtest_config.get("indicators", {}) or {}
        indicators: list[IndicatorDefinition] = []
        for key, params in indicators_cfg.items():
            if not params or not params.get("enabled"):
                continue
            clean_params = copy.deepcopy(params)
            clean_params.pop("enabled", None)
            indicators.append(IndicatorDefinition(key=key, params=clean_params))
        if not indicators:
            self.backtest_status_label.setText("Enable at least one indicator to scan.")
            return

        start_qdt = self.backtest_start_edit.dateTime()
        end_qdt = self.backtest_end_edit.dateTime()
        if start_qdt > end_qdt:
            self.backtest_status_label.setText(
                "Start date/time must be before end date/time."
            )
            return
        start_dt = start_qdt.toPyDateTime()
        end_dt = end_qdt.toPyDateTime()
        if start_dt >= end_dt:
            self.backtest_status_label.setText(
                "Backtest range must span a positive duration."
            )
            return

        capital = float(self.backtest_capital_spin.value())
        if capital <= 0.0:
            self.backtest_status_label.setText("Margin capital must be positive.")
            return

        position_pct = float(self.backtest_pospct_spin.value())
        position_pct_units = "percent"
        side_value = self._canonical_side_from_text(self.backtest_side_combo.currentText())
        margin_mode = (self.backtest_margin_mode_combo.currentText() or "Isolated").strip()
        position_mode = (
            self.backtest_position_mode_combo.currentText() or "Hedge"
        ).strip()
        assets_mode = self._normalize_assets_mode(
            self.backtest_assets_mode_combo.currentData()
            or self.backtest_assets_mode_combo.currentText()
        )
        account_mode = self._normalize_account_mode(
            self.backtest_account_mode_combo.currentData()
            or self.backtest_account_mode_combo.currentText()
        )
        leverage_value = int(self.backtest_leverage_spin.value() or 1)

        logic = (self.backtest_logic_combo.currentText() or "AND").upper()
        self._update_backtest_config("logic", logic)
        self._update_backtest_config("capital", capital)
        self._update_backtest_config("position_pct", position_pct)
        self._update_backtest_config("position_pct_units", position_pct_units)
        self._update_backtest_config("side", side_value)
        self._update_backtest_config("margin_mode", margin_mode)
        self._update_backtest_config("position_mode", position_mode)
        self._update_backtest_config("assets_mode", assets_mode)
        self._update_backtest_config("account_mode", account_mode)
        self._update_backtest_config("leverage", leverage_value)

        optimizer_mode_combo = getattr(self, "backtest_optimizer_mode_combo", None)
        optimizer_metric_combo = getattr(self, "backtest_optimizer_metric_combo", None)
        optimizer_mode = backtest_optimizer_runtime.normalize_optimizer_mode(
            optimizer_mode_combo.currentData()
            if optimizer_mode_combo is not None
            else self.backtest_config.get("optimizer_mode", "current")
        )
        optimizer_metric = backtest_optimizer_runtime.normalize_optimizer_metric(
            optimizer_metric_combo.currentData()
            if optimizer_metric_combo is not None
            else self.backtest_config.get("optimizer_metric", "roi_percent")
        )
        try:
            optimizer_combo_size = int(self.backtest_optimizer_combo_size_spin.value())
        except Exception:
            optimizer_combo_size = int(self.backtest_config.get("optimizer_combo_size", 2) or 2)
        try:
            optimizer_min_trades = int(self.backtest_optimizer_min_trades_spin.value())
        except Exception:
            optimizer_min_trades = int(self.backtest_config.get("optimizer_min_trades", 1) or 1)
        optimizer_combo_size = max(1, min(5, optimizer_combo_size))
        optimizer_min_trades = max(0, optimizer_min_trades)
        self._update_backtest_config("optimizer_mode", optimizer_mode)
        self._update_backtest_config("optimizer_metric", optimizer_metric)
        self._update_backtest_config("optimizer_combo_size", optimizer_combo_size)
        self._update_backtest_config("optimizer_min_trades", optimizer_min_trades)

        indicator_keys_order = [ind.key for ind in indicators]
        indicator_groups = backtest_optimizer_runtime.build_indicator_key_groups(
            indicator_keys_order,
            mode=optimizer_mode,
            combo_size=optimizer_combo_size,
        )
        if optimizer_mode != "current" and not indicator_groups:
            self.backtest_status_label.setText(
                "Optimizer mode needs more enabled indicators for the selected combination type."
            )
            return
        run_count = backtest_optimizer_runtime.estimate_scan_run_count(
            symbols=symbols,
            intervals=intervals,
            indicator_count=len(indicators),
            indicator_groups=indicator_groups,
            mode=optimizer_mode,
            logic=logic,
        )
        if run_count > backtest_optimizer_runtime.MAX_BACKTEST_OPTIMIZER_RUNS:
            self.backtest_status_label.setText(
                f"Optimizer would create {run_count} runs; reduce symbols, intervals, or combination size "
                f"(limit {backtest_optimizer_runtime.MAX_BACKTEST_OPTIMIZER_RUNS})."
            )
            return

        pair_overrides = None
        request_logic = logic
        if optimizer_mode != "current":
            pair_overrides = backtest_optimizer_runtime.build_pair_overrides(
                symbols=symbols,
                intervals=intervals,
                indicator_groups=indicator_groups,
            )
            if logic == "SEPARATE" and any(len(group) > 1 for group in indicator_groups):
                request_logic = "AND"

        expected_runs = []
        if pair_overrides:
            for override in pair_overrides:
                expected_runs.append((override.symbol, override.interval, list(override.indicators or [])))
        elif logic == "SEPARATE":
            for sym in symbols:
                for iv in intervals:
                    for ind in indicators:
                        expected_runs.append((sym, iv, [ind.key]))
        else:
            for sym in symbols:
                for iv in intervals:
                    expected_runs.append((sym, iv, list(indicator_keys_order)))
        self._backtest_expected_runs = expected_runs
        self._backtest_dates_changed()

        symbol_source = (self.backtest_symbol_source_combo.currentText() or "Futures").strip()
        self._update_backtest_config("symbol_source", symbol_source)
        account_type = "Spot" if symbol_source.lower().startswith("spot") else "Futures"

        api_key = self.api_key_edit.text().strip()
        api_secret = self.api_secret_edit.text().strip()
        mode = self.mode_combo.currentText()

        stop_cfg = normalize_backtest_stop_loss_dict(self.backtest_config.get("stop_loss"))
        self.backtest_config["stop_loss"] = stop_cfg
        self.config.setdefault("backtest", {})["stop_loss"] = copy.deepcopy(stop_cfg)

        mdd_logic_value = self._get_selected_mdd_logic()
        request = BacktestRequest(
            symbols=symbols,
            intervals=intervals,
            indicators=indicators,
            logic=request_logic,
            symbol_source=symbol_source,
            start=start_dt,
            end=end_dt,
            capital=capital,
            side=side_value,
            position_pct=position_pct,
            position_pct_units=position_pct_units,
            leverage=leverage_value,
            margin_mode=margin_mode,
            position_mode=position_mode,
            assets_mode=assets_mode,
            account_mode=account_mode,
            mdd_logic=mdd_logic_value,
            stop_loss_enabled=bool(stop_cfg.get("enabled")),
            stop_loss_mode=str(stop_cfg.get("mode") or "usdt"),
            stop_loss_usdt=float(stop_cfg.get("usdt", 0.0) or 0.0),
            stop_loss_percent=float(stop_cfg.get("percent", 0.0) or 0.0),
            stop_loss_scope=str(stop_cfg.get("scope") or "per_trade"),
            pair_overrides=pair_overrides,
        )

        signature = (mode, api_key, api_secret)
        wrapper_entry = self._backtest_wrappers.get(account_type)
        wrapper = None
        if (
            isinstance(wrapper_entry, dict)
            and wrapper_entry.get("signature") == signature
        ):
            wrapper = wrapper_entry.get("wrapper")
        if wrapper is None:
            wrapper = self._create_binance_wrapper(
                api_key=api_key,
                api_secret=api_secret,
                mode=mode,
                account_type=account_type,
                connector_backend=self._backtest_connector_backend(),
            )
            self._backtest_wrappers[account_type] = {
                "signature": signature,
                "wrapper": wrapper,
            }
        else:
            try:
                wrapper.account_type = account_type
            except Exception:
                pass

        try:
            wrapper.indicator_source = self.ind_source_combo.currentText()
        except Exception:
            pass

        worker_cls = get_backtest_worker_cls()
        if worker_cls is None:
            raise RuntimeError("Backtest worker is not configured")
        engine = BacktestEngine(wrapper)
        self.backtest_scan_worker = worker_cls(engine, request, self)
        self.backtest_scan_worker.progress.connect(self._on_backtest_progress)
        self.backtest_scan_worker.finished.connect(self._on_backtest_scan_finished)
        self.backtest_results_table.setRowCount(0)
        scope_label = backtest_optimizer_runtime.option_label(
            backtest_optimizer_runtime.SCAN_SCOPE_OPTIONS,
            scan_scope,
        )
        mode_label = backtest_optimizer_runtime.option_label(
            backtest_optimizer_runtime.OPTIMIZER_MODE_OPTIONS,
            optimizer_mode,
        )
        self.backtest_status_label.setText(
            f"Running optimizer: {run_count} run(s), {scope_label}, {mode_label}..."
        )
        self.backtest_run_btn.setEnabled(False)
        try:
            self.backtest_scan_btn.setEnabled(False)
        except Exception:
            pass
        try:
            self.backtest_stop_btn.setEnabled(True)
        except Exception:
            pass
        try:
            self._backtest_scan_mdd_limit = float(self.backtest_scan_mdd_spin.value())
        except Exception:
            self._backtest_scan_mdd_limit = float(
                self.backtest_config.get("scan_mdd_limit", 10.0) or 10.0
            )
        self._backtest_scan_optimizer_metric = optimizer_metric
        self._backtest_scan_optimizer_min_trades = optimizer_min_trades
        self._backtest_scan_optimizer_mode = optimizer_mode
        self.backtest_scan_worker.start()
    except Exception as exc:
        tb = traceback.format_exc()
        try:
            self.backtest_status_label.setText(f"Scan failed: {exc}")
            self.log(f"[Backtest Scan] error: {exc}\n{tb}")
        except Exception:
            print(tb, flush=True)


__all__ = ["run_backtest_scan"]
