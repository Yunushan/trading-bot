from __future__ import annotations

import copy
import traceback

from PyQt6 import QtCore

from app.backtester import BacktestEngine, BacktestRequest, IndicatorDefinition

_DBG_BACKTEST_RUN = False
_SYMBOL_FETCH_TOP_N = 200
_normalize_stop_loss_dict = lambda value: value  # type: ignore
_BacktestWorker = None


def _run_backtest(self):
    def dbg(msg: str) -> None:
        if not _DBG_BACKTEST_RUN:
            return
        try:
            self.log(f"[Backtest] {msg}")
        except Exception:
            print(f"[Backtest] {msg}", flush=True)

    try:
        scan_worker = getattr(self, "backtest_scan_worker", None)
        if scan_worker is not None and scan_worker.isRunning():
            self.backtest_status_label.setText(
                "Scan in progress; stop it before starting a backtest."
            )
            dbg("Scan worker running; aborting backtest request.")
            return
        if self.backtest_worker and self.backtest_worker.isRunning():
            self.backtest_status_label.setText("Backtest already running...")
            dbg("Existing worker already running; aborting request.")
            return

        dbg("Preparing parameter overrides.")
        self._backtest_expected_runs = []

        ctx_backtest = self._override_ctx("backtest")
        pair_table = ctx_backtest.get("table") if ctx_backtest else None
        pair_overrides_from_ui: list[dict] = []
        if pair_table is not None:
            try:
                rows = sorted({idx.row() for idx in pair_table.selectionModel().selectedRows()})
            except Exception:
                rows = []
            if rows:
                dbg(f"Processing {len(rows)} selected override rows.")
                for row in rows:
                    try:
                        sym_item = pair_table.item(row, 0)
                        entry_data = sym_item.data(QtCore.Qt.ItemDataRole.UserRole)
                        if isinstance(entry_data, dict):
                            pair_overrides_from_ui.append(entry_data)
                    except Exception:
                        continue
            else:
                dbg("No rows selected in override table; using all entries from config.")
                all_pairs_from_config = (
                    self.config.get("backtest_symbol_interval_pairs", []) or []
                )
                for entry in all_pairs_from_config:
                    if isinstance(entry, dict):
                        pair_overrides_from_ui.append(entry)
        else:
            dbg("No override table found.")

        pairs_override_for_request: list[dict] | None = None
        if pair_overrides_from_ui:
            pairs_override_for_request = []
            seen_keys = set()
            for entry in pair_overrides_from_ui:
                sym = str(entry.get("symbol") or "").strip().upper()
                iv = str(entry.get("interval") or "").strip()
                if not (sym and iv):
                    continue
                key = (sym, iv)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                pairs_override_for_request.append(entry)
            dbg(
                f"Prepared {len(pairs_override_for_request)} unique overrides for the backtest request."
            )

        symbols = [s for s in (self.backtest_config.get("symbols") or []) if s]
        intervals = [iv for iv in (self.backtest_config.get("intervals") or []) if iv]
        if pairs_override_for_request:
            symbol_order: list[str] = []
            interval_order: list[str] = []
            for entry in pairs_override_for_request:
                sym = str(entry.get("symbol") or "")
                iv = str(entry.get("interval") or "")
                if sym not in symbol_order:
                    symbol_order.append(sym)
                if iv not in interval_order:
                    interval_order.append(iv)
            if not symbol_order or not interval_order:
                self.backtest_status_label.setText(
                    "Symbol/Interval overrides list is empty."
                )
                dbg("Overrides empty after filtering.")
                return
            symbols = symbol_order
            intervals = interval_order
        if not symbols:
            self.backtest_status_label.setText("Select at least one symbol.")
            dbg("Missing symbols.")
            return
        if not intervals:
            self.backtest_status_label.setText("Select at least one interval.")
            dbg("Missing intervals.")
            return

        dbg(f"Symbols={symbols}, intervals={intervals}")

        self.backtest_config["symbols"] = list(symbols)
        self.backtest_config["intervals"] = list(intervals)
        cfg_bt = self.config.setdefault("backtest", {})
        cfg_bt["symbols"] = list(symbols)
        cfg_bt["intervals"] = list(intervals)

        indicators_cfg = self.backtest_config.get("indicators", {}) or {}
        indicators: list[IndicatorDefinition] = []
        for key, params in indicators_cfg.items():
            if not params or not params.get("enabled"):
                continue
            clean_params = copy.deepcopy(params)
            clean_params.pop("enabled", None)
            indicators.append(IndicatorDefinition(key=key, params=clean_params))
        if not indicators:
            self.backtest_status_label.setText(
                "Enable at least one indicator to backtest."
            )
            dbg("No indicators enabled.")
            return

        start_qdt = self.backtest_start_edit.dateTime()
        end_qdt = self.backtest_end_edit.dateTime()
        if start_qdt > end_qdt:
            self.backtest_status_label.setText(
                "Start date/time must be before end date/time."
            )
            dbg("Invalid date range (start > end).")
            return

        start_dt = start_qdt.toPyDateTime()
        end_dt = end_qdt.toPyDateTime()
        if start_dt >= end_dt:
            self.backtest_status_label.setText(
                "Backtest range must span a positive duration."
            )
            dbg("Invalid date range (duration <= 0).")
            return

        capital = float(self.backtest_capital_spin.value())
        if capital <= 0.0:
            self.backtest_status_label.setText("Margin capital must be positive.")
            dbg("Capital <= 0.")
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
        dbg(
            f"Logic={logic}, capital={capital}, pos%={position_pct}, "
            f"side={side_value}, loop={self.backtest_config.get('loop_interval_override')}"
        )

        indicator_keys_order = [ind.key for ind in indicators]
        combos_sequence = (
            [(entry["symbol"], entry["interval"]) for entry in pairs_override_for_request]
            if pairs_override_for_request
            else [(sym, iv) for sym in symbols for iv in intervals]
        )
        expected_runs = []
        if logic == "SEPARATE":
            for sym, iv in combos_sequence:
                for ind in indicators:
                    expected_runs.append((sym, iv, [ind.key]))
        else:
            expected_indicator_list = list(indicator_keys_order)
            for sym, iv in combos_sequence:
                expected_runs.append((sym, iv, list(expected_indicator_list)))
        self._backtest_expected_runs = expected_runs
        self._backtest_dates_changed()
        dbg(f"Prepared {len(expected_runs)} expected run entries.")

        symbol_source = (self.backtest_symbol_source_combo.currentText() or "Futures").strip()
        self._update_backtest_config("symbol_source", symbol_source)
        account_type = "Spot" if symbol_source.lower().startswith("spot") else "Futures"

        api_key = self.api_key_edit.text().strip()
        api_secret = self.api_secret_edit.text().strip()
        mode = self.mode_combo.currentText()

        stop_cfg = _normalize_stop_loss_dict(self.backtest_config.get("stop_loss"))
        self.backtest_config["stop_loss"] = stop_cfg
        self.config.setdefault("backtest", {})["stop_loss"] = copy.deepcopy(stop_cfg)

        mdd_logic_value = self._get_selected_mdd_logic()

        request = BacktestRequest(
            symbols=symbols,
            intervals=intervals,
            indicators=indicators,
            logic=logic,
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
            pair_overrides=pairs_override_for_request,
        )
        dbg(
            f"BacktestRequest prepared: symbols={len(symbols)}, intervals={len(intervals)}, indicators={len(indicators)}"
        )

        signature = (mode, api_key, api_secret)
        wrapper_entry = self._backtest_wrappers.get(account_type)
        wrapper = None
        if (
            isinstance(wrapper_entry, dict)
            and wrapper_entry.get("signature") == signature
        ):
            wrapper = wrapper_entry.get("wrapper")
            dbg("Reusing cached Binance wrapper.")
        if wrapper is None:
            try:
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
                dbg("Created new Binance wrapper instance.")
            except Exception as exc:
                msg = f"Unable to initialize Binance wrapper: {exc}"
                self.backtest_status_label.setText(msg)
                self.log(msg)
                return
        else:
            try:
                wrapper.account_type = account_type
            except Exception:
                pass

        try:
            wrapper.indicator_source = self.ind_source_combo.currentText()
        except Exception:
            pass

        engine = BacktestEngine(wrapper)
        self.backtest_worker = _BacktestWorker(engine, request, self)
        self.backtest_worker.progress.connect(self._on_backtest_progress)
        self.backtest_worker.finished.connect(self._on_backtest_finished)
        self.backtest_results_table.setRowCount(0)
        self.backtest_status_label.setText("Running backtest...")
        self.backtest_run_btn.setEnabled(False)
        try:
            self.backtest_stop_btn.setEnabled(True)
        except Exception:
            pass
        try:
            self.backtest_stop_btn.setEnabled(True)
        except Exception:
            pass
        dbg("Dispatching worker thread.")
        self.backtest_worker.start()
    except Exception as exc:
        tb = traceback.format_exc()
        try:
            self.backtest_status_label.setText(f"Backtest failed: {exc}")
            self.log(f"[Backtest] error: {exc}\n{tb}")
        except Exception:
            print(tb, flush=True)


def _run_backtest_scan(self):
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
        if not symbols_all:
            self.backtest_status_label.setText(
                "No symbols loaded. Click Refresh Symbols first."
            )
            return
        try:
            top_n = int(self.backtest_scan_top_spin.value())
        except Exception:
            top_n = int(
                self.backtest_config.get("scan_top_n", _SYMBOL_FETCH_TOP_N)
                or _SYMBOL_FETCH_TOP_N
            )
        if top_n <= 0:
            self.backtest_status_label.setText("Scan Top N must be at least 1.")
            return
        if len(symbols_all) < top_n:
            self.backtest_status_label.setText(
                f"Only {len(symbols_all)} symbols loaded; lower Scan Top N or refresh."
            )
            return
        symbols = symbols_all[:top_n]

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

        indicator_keys_order = [ind.key for ind in indicators]
        expected_runs = []
        if logic == "SEPARATE":
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

        stop_cfg = _normalize_stop_loss_dict(self.backtest_config.get("stop_loss"))
        self.backtest_config["stop_loss"] = stop_cfg
        self.config.setdefault("backtest", {})["stop_loss"] = copy.deepcopy(stop_cfg)

        mdd_logic_value = self._get_selected_mdd_logic()
        request = BacktestRequest(
            symbols=symbols,
            intervals=intervals,
            indicators=indicators,
            logic=logic,
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

        engine = BacktestEngine(wrapper)
        self.backtest_scan_worker = _BacktestWorker(engine, request, self)
        self.backtest_scan_worker.progress.connect(self._on_backtest_progress)
        self.backtest_scan_worker.finished.connect(self._on_backtest_scan_finished)
        self.backtest_results_table.setRowCount(0)
        self.backtest_status_label.setText(f"Scanning top {len(symbols)} symbols...")
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
        self.backtest_scan_worker.start()
    except Exception as exc:
        tb = traceback.format_exc()
        try:
            self.backtest_status_label.setText(f"Scan failed: {exc}")
            self.log(f"[Backtest Scan] error: {exc}\n{tb}")
        except Exception:
            print(tb, flush=True)


def bind_main_window_backtest_execution_runtime(
    main_window_cls,
    *,
    dbg_backtest_run: bool,
    symbol_fetch_top_n: int,
    normalize_stop_loss_dict,
    backtest_worker_cls,
) -> None:
    global _DBG_BACKTEST_RUN
    global _SYMBOL_FETCH_TOP_N
    global _normalize_stop_loss_dict
    global _BacktestWorker

    _DBG_BACKTEST_RUN = bool(dbg_backtest_run)
    _SYMBOL_FETCH_TOP_N = max(1, int(symbol_fetch_top_n))
    if callable(normalize_stop_loss_dict):
        _normalize_stop_loss_dict = normalize_stop_loss_dict
    _BacktestWorker = backtest_worker_cls

    main_window_cls._run_backtest = _run_backtest
    main_window_cls._run_backtest_scan = _run_backtest_scan
