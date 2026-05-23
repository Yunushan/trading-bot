from __future__ import annotations

import copy
import traceback

from PyQt6 import QtCore

_DBG_BACKTEST_DASHBOARD = False


def _normalize_indicator_values(value):  # type: ignore
    return []


def _normalize_stop_loss_dict(value):  # type: ignore
    return value


def _clean_backtest_result_metadata(data: dict) -> dict:
    metadata_keys = (
        "symbol",
        "interval",
        "indicator_keys",
        "logic",
        "trades",
        "roi_value",
        "roi_percent",
        "max_drawdown_percent",
        "max_drawdown_value",
        "max_drawdown_during_percent",
        "max_drawdown_during_value",
        "max_drawdown_result_percent",
        "max_drawdown_result_value",
        "mdd_logic",
        "mdd_logic_display",
        "start",
        "start_display",
        "end",
        "end_display",
        "side",
        "capital",
        "position_pct",
        "position_pct_display",
        "position_pct_units",
        "leverage",
        "leverage_display",
        "margin_mode",
        "position_mode",
        "assets_mode",
        "account_mode",
        "stop_loss_enabled",
        "stop_loss_mode",
        "stop_loss_scope",
        "stop_loss_usdt",
        "stop_loss_percent",
        "stop_loss_display",
        "loop_interval_override",
        "connector_backend",
        "strategy_controls",
        "optimizer_rank",
        "optimizer_metric",
        "optimizer_primary_score",
        "optimizer_eligible",
        "optimizer_mode",
        "optimizer_scope",
        "optimizer_mdd_limit",
        "optimizer_min_trades",
        "optimizer_candidate_count",
        "optimizer_eligible_count",
        "optimizer_filtered_count",
        "optimizer_run_count",
        "optimizer_rejection_reason",
    )
    metadata = {
        key: copy.deepcopy(data.get(key))
        for key in metadata_keys
        if key in data and data.get(key) not in (None, "")
    }
    indicator_keys = metadata.get("indicator_keys")
    if isinstance(indicator_keys, tuple):
        metadata["indicator_keys"] = list(indicator_keys)
    metadata["source"] = "python-backtest"
    return metadata


def _coerce_optional_float(value) -> float | None:  # type: ignore
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _coerce_optional_int(value) -> int | None:  # type: ignore
    number = _coerce_optional_float(value)
    if number is None:
        return None
    try:
        return max(1, int(number))
    except Exception:
        return None


def _coerce_bool(value) -> bool:  # type: ignore
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off", "", "none", "null"}:
            return False
    return bool(value)


def _is_filtered_optimizer_result(data: dict) -> bool:
    if "optimizer_eligible" not in data:
        return False
    return not _coerce_bool(data.get("optimizer_eligible"))


def _normalize_runtime_controls(self, controls) -> dict:  # type: ignore
    if not isinstance(controls, dict) or not controls:
        return {}
    normalizer = getattr(self, "_normalize_strategy_controls", None)
    if callable(normalizer):
        try:
            normalized = normalizer("runtime", copy.deepcopy(controls))
            if isinstance(normalized, dict):
                return normalized
        except Exception:
            pass
    return copy.deepcopy(controls)


def _stop_loss_from_backtest_result(data: dict) -> dict | None:
    stop_cfg = data.get("stop_loss")
    if isinstance(stop_cfg, dict):
        return _normalize_stop_loss_dict(stop_cfg)
    has_stop_payload = any(
        key in data
        for key in (
            "stop_loss_enabled",
            "stop_loss_mode",
            "stop_loss_scope",
            "stop_loss_usdt",
            "stop_loss_percent",
        )
    )
    if not has_stop_payload:
        return None
    return _normalize_stop_loss_dict(
        {
            "enabled": _coerce_bool(data.get("stop_loss_enabled", False)),
            "mode": str(data.get("stop_loss_mode") or "usdt").strip().lower(),
            "scope": str(data.get("stop_loss_scope") or "per_trade").strip().lower(),
            "usdt": _coerce_optional_float(data.get("stop_loss_usdt")) or 0.0,
            "percent": _coerce_optional_float(data.get("stop_loss_percent")) or 0.0,
        }
    )


def _runtime_controls_from_backtest_result(self, data: dict) -> dict:
    stored_controls = data.get("strategy_controls")
    if isinstance(stored_controls, dict):
        controls = _normalize_runtime_controls(self, stored_controls)
        if controls:
            return controls

    controls: dict[str, object] = {}
    side = str(data.get("side") or "").strip().upper()
    if side:
        controls["side"] = side
    pos_pct = _coerce_optional_float(data.get("position_pct"))
    if pos_pct is not None:
        controls["position_pct"] = pos_pct
        controls["position_pct_units"] = str(
            data.get("position_pct_units") or "fraction"
        ).strip()
    leverage = _coerce_optional_int(data.get("leverage"))
    if leverage is not None:
        controls["leverage"] = leverage
    loop_override = self._normalize_loop_override(data.get("loop_interval_override"))
    if loop_override:
        controls["loop_interval_override"] = loop_override
    account_mode = str(data.get("account_mode") or "").strip()
    if account_mode:
        controls["account_mode"] = account_mode
    connector_backend = str(data.get("connector_backend") or "").strip()
    if connector_backend:
        controls["connector_backend"] = connector_backend
    stop_cfg = _stop_loss_from_backtest_result(data)
    if isinstance(stop_cfg, dict):
        controls["stop_loss"] = stop_cfg
    return _normalize_runtime_controls(self, controls)


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
        skipped_ineligible_count = 0

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
        updated_count = 0
        for row_idx in target_rows:
            if row_idx < 0 or row_idx >= row_count:
                _dbg(f"Row {row_idx} out of bounds (table rows={row_count})")
                continue
            data = self._normalize_backtest_run(_row_payload(row_idx))
            _dbg(f"Row {row_idx} normalized data: {data}")
            if _is_filtered_optimizer_result(data):
                skipped_ineligible_count += 1
                _dbg(
                    f"Row {row_idx} skipped because optimizer_eligible="
                    f"{data.get('optimizer_eligible')!r}"
                )
                continue
            sym = str(data.get("symbol") or "").strip().upper()
            iv = str(data.get("interval") or "").strip()
            if not sym or not iv:
                _dbg(f"Row {row_idx} missing sym/interval")
                continue
            indicators_clean = _normalize_indicator_values(data.get("indicator_keys"))

            controls_to_apply = _runtime_controls_from_backtest_result(self, data)
            stop_cfg = None
            loop_override_value = None
            leverage_for_key = None

            if controls_to_apply:
                _dbg(f"Row {row_idx} using stored controls from result")
                stop_cfg = controls_to_apply.get("stop_loss")
                loop_override_value = self._normalize_loop_override(
                    controls_to_apply.get("loop_interval_override")
                )
                leverage_for_key = controls_to_apply.get("leverage")
            else:
                controls_snapshot = self._collect_strategy_controls("backtest")
                if controls_snapshot:
                    _dbg(f"Row {row_idx} using live controls snapshot fallback")
                    controls_to_apply = _normalize_runtime_controls(self, controls_snapshot)
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

            backtest_metadata = _clean_backtest_result_metadata(data)
            key = (sym, iv, tuple(indicators_clean), leverage_for_key)
            if key in existing:
                existing_entry = existing[key]
                row_updated = False
                if backtest_metadata:
                    existing_entry["backtest_result"] = backtest_metadata
                    row_updated = True
                if controls_to_apply:
                    existing_entry["strategy_controls"] = controls_to_apply
                    row_updated = True
                if loop_override_value:
                    existing_entry["loop_interval_override"] = loop_override_value
                if isinstance(stop_cfg, dict):
                    stop_cfg = _normalize_stop_loss_dict(stop_cfg)
                    existing_entry["stop_loss"] = stop_cfg
                    if isinstance(controls_to_apply, dict):
                        controls_to_apply["stop_loss"] = stop_cfg
                if leverage_for_key is not None:
                    existing_entry["leverage"] = leverage_for_key
                if row_updated:
                    updated_count += 1
                _dbg(f"Row {row_idx} already exists; skipping")
                continue

            entry = {"symbol": sym, "interval": iv}
            if indicators_clean:
                entry["indicators"] = list(indicators_clean)
            if backtest_metadata:
                entry["backtest_result"] = backtest_metadata
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
            try:
                status = f"Added {added_count} backtest result(s) to dashboard overrides."
                if updated_count:
                    status += f" Updated {updated_count} existing provenance record(s)."
                if skipped_ineligible_count:
                    status += (
                        f" Skipped {skipped_ineligible_count} filtered optimizer result(s)."
                    )
                self.backtest_status_label.setText(status)
            except Exception:
                pass
        elif updated_count:
            try:
                status = (
                    f"Updated {updated_count} existing dashboard override provenance record(s)."
                )
                if skipped_ineligible_count:
                    status += (
                        f" Skipped {skipped_ineligible_count} filtered optimizer result(s)."
                    )
                self.backtest_status_label.setText(status)
            except Exception:
                pass
            _dbg(f"Updated provenance for {updated_count} existing entries.")
        elif skipped_ineligible_count:
            try:
                self.backtest_status_label.setText(
                    f"Skipped {skipped_ineligible_count} filtered optimizer result(s); "
                    "only eligible optimizer rows can be added."
                )
            except Exception:
                pass
            _dbg(f"Skipped {skipped_ineligible_count} ineligible optimizer entries.")
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
