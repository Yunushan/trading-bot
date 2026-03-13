from __future__ import annotations

import copy
import traceback

from PyQt6 import QtCore

_DBG_BACKTEST_DASHBOARD = False
_normalize_indicator_values = lambda value: []  # type: ignore
_normalize_stop_loss_dict = lambda value: value  # type: ignore


def _backtest_add_selected_to_dashboard(self, rows: list[int] | None = None):
    try:
        def _dbg(msg: str) -> None:
            if not _DBG_BACKTEST_DASHBOARD:
                return
            try:
                self.log(f"[Backtest->Dashboard] {msg}")
            except Exception:
                pass

        if isinstance(rows, bool):
            _dbg(f"Received rows bool={rows}; normalizing to None")
            rows = None
        table = getattr(self, "backtest_results_table", None)
        raw_results = getattr(self, "backtest_results", [])
        _dbg(f"Raw results type={type(raw_results).__name__}")
        if isinstance(raw_results, list):
            results = list(raw_results)
        elif isinstance(raw_results, tuple):
            results = list(raw_results)
        elif isinstance(raw_results, dict):
            results = [dict(raw_results)]
        elif raw_results in (None, False, True):
            results = []
        else:
            results = [raw_results]
        normalized_results = []
        for entry in results:
            try:
                normalized_results.append(self._normalize_backtest_run(entry))
            except Exception:
                try:
                    dict_candidate = dict(entry)
                    normalized_results.append(self._normalize_backtest_run(dict_candidate))
                except Exception:
                    _dbg(f"Dropping non-normalizable entry type={type(entry).__name__}")
                    continue
        results = normalized_results
        _dbg(f"Normalized results count={len(results)}")
        try:
            self.backtest_results = list(results)
        except Exception:
            pass
        if table is None or not results:
            try:
                self.backtest_status_label.setText("No backtest results available to import.")
            except Exception:
                pass
            _dbg("No results or table; aborting.")
            return
        if rows is None:
            selection = table.selectionModel()
            if selection is None:
                _dbg("Selection model missing; aborting.")
                return
            target_rows = sorted({index.row() for index in selection.selectedRows()})
            if not target_rows:
                try:
                    self.backtest_status_label.setText("Select one or more backtest rows to add.")
                except Exception:
                    pass
                _dbg("No rows selected via UI.")
                return
        else:
            target_rows = sorted({int(r) for r in rows if isinstance(r, int)})
            if not target_rows:
                try:
                    self.backtest_status_label.setText("No backtest rows available to add.")
                except Exception:
                    pass
                _dbg("Row indices arg empty after filtering.")
                return
        _dbg(f"Target row count={len(target_rows)}")
        runtime_pairs = self._override_config_list("runtime")
        if not isinstance(runtime_pairs, list):
            try:
                runtime_pairs = list(runtime_pairs)
            except TypeError:
                runtime_pairs = []
            try:
                ctx_runtime = self._override_ctx("runtime")
                cfg_key_runtime = ctx_runtime.get("config_key")
                if cfg_key_runtime:
                    self.config[cfg_key_runtime] = runtime_pairs
            except Exception:
                pass
        _dbg(
            f"Existing runtime pairs before cleanup: type={type(runtime_pairs).__name__}, "
            f"len={len(runtime_pairs or [])}"
        )
        existing = {}
        clean_runtime_pairs: list[dict] = []
        for entry in runtime_pairs or []:
            if not isinstance(entry, dict):
                _dbg(f"Skipping non-dict runtime entry type={type(entry).__name__}")
                continue
            sym = str((entry or {}).get("symbol") or "").strip().upper()
            iv = str((entry or {}).get("interval") or "").strip()
            indicators = _normalize_indicator_values((entry or {}).get("indicators"))
            lev_existing = None
            controls_existing = entry.get("strategy_controls")
            if isinstance(controls_existing, dict):
                lev_existing = controls_existing.get("leverage")
            if lev_existing is None:
                lev_existing = entry.get("leverage")
            try:
                if lev_existing is not None:
                    lev_existing = max(1, int(float(lev_existing)))
            except Exception:
                lev_existing = None
            key = (sym, iv, tuple(indicators), lev_existing)
            existing[key] = entry
            clean_runtime_pairs.append(entry)
        if runtime_pairs is not None:
            try:
                runtime_pairs.clear()
                runtime_pairs.extend(clean_runtime_pairs)
            except Exception:
                pass
        row_count = table.rowCount()

        def _row_payload(row_idx: int) -> dict:
            payload = None
            try:
                item = table.item(row_idx, 0)
            except Exception:
                item = None
            if item is not None:
                try:
                    payload = item.data(QtCore.Qt.ItemDataRole.UserRole)
                except Exception:
                    payload = None
            if isinstance(payload, dict):
                return dict(payload)
            if 0 <= row_idx < len(results):
                return dict(results[row_idx])
            return {}

        added_count = 0
        for row_idx in target_rows:
            if row_idx < 0 or row_idx >= row_count:
                _dbg(f"Row {row_idx} out of bounds (table rows={row_count})")
                continue
            data = self._normalize_backtest_run(_row_payload(row_idx))
            _dbg(f"Row {row_idx} normalized data: {data}")
            sym = str(data.get("symbol") or "").strip().upper()
            iv = str(data.get("interval") or "").strip()
            if not sym or not iv:
                _dbg(f"Row {row_idx} missing sym/interval")
                continue
            indicators_clean = _normalize_indicator_values(data.get("indicator_keys"))

            controls_snapshot = self._collect_strategy_controls("backtest")
            controls_to_apply = None
            stop_cfg = None
            loop_override_value = None
            leverage_for_key = None

            if controls_snapshot:
                _dbg(f"Row {row_idx} using live controls snapshot")
                controls_to_apply = copy.deepcopy(controls_snapshot)
                stop_cfg = controls_to_apply.get("stop_loss")
                loop_override_value = self._normalize_loop_override(
                    controls_to_apply.get("loop_interval_override")
                )
                leverage_for_key = controls_to_apply.get("leverage")
            else:
                stored_controls = data.get("strategy_controls")
                if isinstance(stored_controls, dict):
                    _dbg(f"Row {row_idx} using stored controls from result")
                    controls_to_apply = copy.deepcopy(stored_controls)
                    stop_cfg = controls_to_apply.get("stop_loss")
                    loop_override_value = self._normalize_loop_override(
                        controls_to_apply.get("loop_interval_override")
                    )
                    leverage_for_key = controls_to_apply.get("leverage")

            if leverage_for_key is None:
                leverage_for_key = data.get("leverage")
            try:
                if leverage_for_key is not None:
                    leverage_for_key = max(1, int(float(leverage_for_key)))
            except Exception:
                leverage_for_key = None

            key = (sym, iv, tuple(indicators_clean), leverage_for_key)
            if key in existing:
                _dbg(f"Row {row_idx} already exists; skipping")
                continue

            entry = {"symbol": sym, "interval": iv}
            if indicators_clean:
                entry["indicators"] = list(indicators_clean)
            base_loop_value = self._normalize_loop_override(data.get("loop_interval_override"))
            if base_loop_value:
                entry["loop_interval_override"] = base_loop_value
            if loop_override_value:
                entry["loop_interval_override"] = loop_override_value
            if controls_to_apply:
                entry["strategy_controls"] = controls_to_apply
            if isinstance(stop_cfg, dict):
                stop_cfg = _normalize_stop_loss_dict(stop_cfg)
                entry["stop_loss"] = stop_cfg
                if isinstance(controls_to_apply, dict):
                    controls_to_apply["stop_loss"] = stop_cfg
            else:
                data_stop_cfg = data.get("stop_loss")
                if isinstance(data_stop_cfg, dict):
                    stop_cfg_norm = _normalize_stop_loss_dict(data_stop_cfg)
                    entry["stop_loss"] = stop_cfg_norm
                    if isinstance(controls_to_apply, dict):
                        controls_to_apply.setdefault("stop_loss", stop_cfg_norm)
            if leverage_for_key is not None:
                entry["leverage"] = leverage_for_key

            runtime_pairs.append(entry)
            existing[key] = entry
            added_count += 1
            _dbg(
                f"Row {row_idx} appended: indicators={indicators_clean}, "
                f"leverage={leverage_for_key}, has_controls={'strategy_controls' in entry}"
            )
        if added_count:
            _dbg(f"Completed: appended {added_count} entries.")
        else:
            try:
                self.backtest_status_label.setText(
                    "Selected results already exist in dashboard overrides."
                )
            except Exception:
                pass
            _dbg("No new entries were added (duplicates?).")
    except Exception as exc:
        try:
            self.backtest_status_label.setText(f"Add to dashboard failed: {exc}")
        except Exception:
            pass
        try:
            if _DBG_BACKTEST_DASHBOARD:
                tb = traceback.format_exc()
                self.log(f"[Backtest->Dashboard] error: {exc}\n{tb}")
            else:
                self.log(f"Add backtest results to dashboard error: {exc}")
        except Exception:
            pass


def _backtest_add_all_to_dashboard(self):
    try:
        table = getattr(self, "backtest_results_table", None)
        if table is None:
            try:
                self.backtest_status_label.setText("No backtest results table available.")
            except Exception:
                pass
            return
        all_rows = list(range(table.rowCount()))
        if not all_rows:
            try:
                self.backtest_status_label.setText("No backtest rows available to add.")
            except Exception:
                pass
            return
        self._backtest_add_selected_to_dashboard(rows=all_rows)
    except Exception as exc:
        try:
            self.backtest_status_label.setText(f"Add all failed: {exc}")
        except Exception:
            pass
        try:
            self.log(f"Add all backtest results to dashboard error: {exc}")
        except Exception:
            pass


def bind_main_window_backtest_bridge_runtime(
    main_window_cls,
    *,
    dbg_backtest_dashboard: bool = False,
    normalize_indicator_values=None,
    normalize_stop_loss_dict=None,
) -> None:
    global _DBG_BACKTEST_DASHBOARD
    global _normalize_indicator_values
    global _normalize_stop_loss_dict

    _DBG_BACKTEST_DASHBOARD = bool(dbg_backtest_dashboard)
    if callable(normalize_indicator_values):
        _normalize_indicator_values = normalize_indicator_values
    if callable(normalize_stop_loss_dict):
        _normalize_stop_loss_dict = normalize_stop_loss_dict

    main_window_cls._backtest_add_selected_to_dashboard = _backtest_add_selected_to_dashboard
    main_window_cls._backtest_add_all_to_dashboard = _backtest_add_all_to_dashboard
