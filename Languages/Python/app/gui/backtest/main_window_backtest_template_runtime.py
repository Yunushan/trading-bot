from __future__ import annotations

import copy

from PyQt6 import QtCore, QtWidgets

_MDD_LOGIC_OPTIONS = ()
_MDD_LOGIC_DEFAULT = "overall"
_BACKTEST_TEMPLATE_DEFINITIONS = {}
_BACKTEST_TEMPLATE_DEFAULT = {}
_INDICATOR_DISPLAY_NAMES = {}
_SIDE_LABELS = {}
_ParamDialog = None
_normalize_connector_backend = lambda value: value  # type: ignore


def _get_selected_mdd_logic(self) -> str:
    try:
        combo = getattr(self, "backtest_mdd_combo", None)
        if combo is not None and combo.count():
            value = combo.currentData(QtCore.Qt.ItemDataRole.UserRole)
            if value in _MDD_LOGIC_OPTIONS:
                return str(value)
    except Exception:
        pass
    value = str(self.backtest_config.get("mdd_logic", _MDD_LOGIC_DEFAULT) or "").lower()
    return value if value in _MDD_LOGIC_OPTIONS else _MDD_LOGIC_DEFAULT


def _set_backtest_mdd_selection(
    self,
    logic: str | None,
    *,
    update_config: bool = False,
) -> str:
    logic_norm = str(logic or _MDD_LOGIC_DEFAULT).lower()
    if logic_norm not in _MDD_LOGIC_OPTIONS:
        logic_norm = _MDD_LOGIC_DEFAULT
    try:
        combo = getattr(self, "backtest_mdd_combo", None)
        if combo is not None and combo.count():
            with QtCore.QSignalBlocker(combo):
                idx = combo.findData(logic_norm)
                if idx < 0:
                    idx = 0
                combo.setCurrentIndex(idx)
                data = combo.itemData(
                    combo.currentIndex(),
                    QtCore.Qt.ItemDataRole.UserRole,
                )
                if data in _MDD_LOGIC_OPTIONS:
                    logic_norm = str(data)
    except Exception:
        pass
    if update_config:
        self._update_backtest_config("mdd_logic", logic_norm)
    return logic_norm


def _on_backtest_mdd_logic_changed(self, _index: int = -1):
    try:
        logic = self._get_selected_mdd_logic()
        self._update_backtest_config("mdd_logic", logic)
    except Exception:
        pass


def _get_selected_template_key(self) -> str | None:
    try:
        combo = getattr(self, "backtest_template_combo", None)
        if combo is not None and combo.count():
            value = combo.currentData(QtCore.Qt.ItemDataRole.UserRole)
            if value in _BACKTEST_TEMPLATE_DEFINITIONS:
                return value
    except Exception:
        pass
    template_cfg = self.backtest_config.get("template", {})
    name = template_cfg.get("name")
    return name if name in _BACKTEST_TEMPLATE_DEFINITIONS else None


def _select_backtest_template(
    self,
    key: str | None,
    *,
    update_config: bool = False,
) -> str | None:
    try:
        combo = getattr(self, "backtest_template_combo", None)
        if combo is None or combo.count() == 0:
            return None
        target = key if key in _BACKTEST_TEMPLATE_DEFINITIONS else None
        if target is None and _BACKTEST_TEMPLATE_DEFINITIONS:
            target = next(iter(_BACKTEST_TEMPLATE_DEFINITIONS))
        selected = target
        with QtCore.QSignalBlocker(combo):
            idx = combo.findData(target)
            if idx < 0:
                idx = 0 if combo.count() else -1
            if idx >= 0:
                combo.setCurrentIndex(idx)
                selected = combo.itemData(idx)
    except Exception:
        selected = target
    if update_config and selected:
        template_cfg = self.backtest_config.setdefault(
            "template",
            copy.deepcopy(_BACKTEST_TEMPLATE_DEFAULT),
        )
        template_cfg["name"] = selected
        self.config.setdefault("backtest", {})["template"] = copy.deepcopy(template_cfg)
    return selected


def _on_backtest_template_enabled(self, checked: bool):
    try:
        template_cfg = self.backtest_config.setdefault(
            "template",
            copy.deepcopy(_BACKTEST_TEMPLATE_DEFAULT),
        )
        template_cfg["enabled"] = bool(checked)
        selected = self._get_selected_template_key()
        if checked:
            selected = self._select_backtest_template(
                template_cfg.get("name") or selected,
                update_config=False,
            )
            if selected:
                template_cfg["name"] = selected
        self.config.setdefault("backtest", {})["template"] = copy.deepcopy(template_cfg)
        combo = getattr(self, "backtest_template_combo", None)
        if combo is not None:
            combo.setEnabled(bool(checked) and combo.count() > 0)
        if checked:
            self._apply_backtest_template(template_cfg.get("name"))
        else:
            self._backtest_pending_symbol_selection = None
    except Exception:
        pass


def _on_backtest_template_selected(self, _index: int = -1):
    try:
        key = self._get_selected_template_key()
        if not key:
            return
        template_cfg = self.backtest_config.setdefault(
            "template",
            copy.deepcopy(_BACKTEST_TEMPLATE_DEFAULT),
        )
        template_cfg["name"] = key
        self.config.setdefault("backtest", {})["template"] = copy.deepcopy(template_cfg)
        if template_cfg.get("enabled"):
            self._apply_backtest_template(key)
    except Exception:
        pass


def _apply_backtest_template(self, template_key: str | None) -> None:
    if not template_key or template_key not in _BACKTEST_TEMPLATE_DEFINITIONS:
        return
    template = _BACKTEST_TEMPLATE_DEFINITIONS.get(template_key)
    if not isinstance(template, dict):
        return
    try:
        template_cfg = self.backtest_config.setdefault(
            "template",
            copy.deepcopy(_BACKTEST_TEMPLATE_DEFAULT),
        )
        template_cfg["name"] = template_key
        self.config.setdefault("backtest", {})["template"] = copy.deepcopy(template_cfg)
        symbol_selection_rule = template.get("symbol_selection")
        if isinstance(symbol_selection_rule, dict):
            source_changed = False
            desired_source = symbol_selection_rule.get("source")
            if desired_source:
                idx_source = self.backtest_symbol_source_combo.findText(
                    desired_source,
                    QtCore.Qt.MatchFlag.MatchFixedString,
                )
                if idx_source < 0:
                    idx_source = self.backtest_symbol_source_combo.findText(desired_source)
                if (
                    idx_source >= 0
                    and self.backtest_symbol_source_combo.currentIndex() != idx_source
                ):
                    self.backtest_symbol_source_combo.setCurrentIndex(idx_source)
                    source_changed = True
            self._backtest_pending_symbol_selection = dict(symbol_selection_rule)
            applied = False
            if not source_changed:
                applied = self._apply_backtest_symbol_selection_rule(symbol_selection_rule)
            if applied:
                self._backtest_pending_symbol_selection = None
            else:
                worker = getattr(self, "_backtest_symbol_worker", None)
                needs_refresh = not source_changed
                try:
                    if worker is not None and worker.isRunning():
                        needs_refresh = False
                except Exception:
                    pass
                if needs_refresh:
                    try:
                        self._refresh_backtest_symbols()
                    except Exception:
                        pass
        else:
            self._backtest_pending_symbol_selection = None

        intervals = template.get("intervals")
        if intervals:
            existing = {
                self.backtest_interval_list.item(i).text()
                for i in range(self.backtest_interval_list.count())
            }
            missing = [iv for iv in intervals if iv not in existing]
            if missing:
                with QtCore.QSignalBlocker(self.backtest_interval_list):
                    for iv in missing:
                        self.backtest_interval_list.addItem(QtWidgets.QListWidgetItem(iv))
            self._set_backtest_interval_selection(intervals)

        logic_value = str(template.get("logic") or "").upper()
        if logic_value:
            with QtCore.QSignalBlocker(self.backtest_logic_combo):
                idx_logic = self.backtest_logic_combo.findText(
                    logic_value,
                    QtCore.Qt.MatchFlag.MatchFixedString,
                )
                if idx_logic < 0:
                    idx_logic = self.backtest_logic_combo.findText(logic_value)
                if idx_logic >= 0:
                    self.backtest_logic_combo.setCurrentIndex(idx_logic)
            self._update_backtest_config("logic", logic_value)

        pct_value = float(
            template.get(
                "position_pct",
                self.backtest_config.get("position_pct", 2.0),
            )
        )
        with QtCore.QSignalBlocker(self.backtest_pospct_spin):
            self.backtest_pospct_spin.setValue(pct_value)
        self._update_backtest_config("position_pct", float(pct_value))

        side_value = str(template.get("side") or "BOTH").upper()
        side_label = _SIDE_LABELS.get(side_value, side_value.title())
        with QtCore.QSignalBlocker(self.backtest_side_combo):
            idx_side = self.backtest_side_combo.findText(
                side_label,
                QtCore.Qt.MatchFlag.MatchFixedString,
            )
            if idx_side < 0:
                idx_side = self.backtest_side_combo.findText(side_label)
            if idx_side >= 0:
                self.backtest_side_combo.setCurrentIndex(idx_side)
        self._update_backtest_config("side", side_label)

        stop_loss_template = template.get("stop_loss")
        if isinstance(stop_loss_template, dict):
            updates = {
                "enabled": bool(stop_loss_template.get("enabled", True)),
                "mode": stop_loss_template.get("mode", "percent"),
                "percent": float(stop_loss_template.get("percent", 0.0) or 0.0),
                "usdt": float(stop_loss_template.get("usdt", 0.0) or 0.0),
                "scope": stop_loss_template.get("scope", "per_trade"),
            }
            self._backtest_stop_loss_update(**updates)
            self._update_backtest_stop_loss_widgets()

        date_range = template.get("date_range")
        if isinstance(date_range, dict):
            now_dt = QtCore.QDateTime.currentDateTime()
            start_dt = QtCore.QDateTime(now_dt)
            months = int(date_range.get("months", 0) or 0)
            days = int(date_range.get("days", 0) or 0)
            if months:
                start_dt = start_dt.addMonths(-months)
            if days:
                start_dt = start_dt.addDays(-days)
            with QtCore.QSignalBlocker(self.backtest_end_edit):
                self.backtest_end_edit.setDateTime(now_dt)
            with QtCore.QSignalBlocker(self.backtest_start_edit):
                self.backtest_start_edit.setDateTime(start_dt)
            self._backtest_dates_changed()

        indicators_template = template.get("indicators", {})
        if isinstance(indicators_template, dict):
            indicators_cfg = self.backtest_config.setdefault("indicators", {})
            cfg_parent = self.config.setdefault("backtest", {}).setdefault("indicators", {})
            for key, (cb, _btn) in self.backtest_indicator_widgets.items():
                params = indicators_cfg.setdefault(key, {})
                target_params = indicators_template.get(key)
                enabled = bool(target_params)
                params["enabled"] = enabled
                if enabled and isinstance(target_params, dict):
                    params.update(
                        {k: v for k, v in target_params.items() if k != "enabled"}
                    )
                cb.blockSignals(True)
                cb.setChecked(enabled)
                cb.blockSignals(False)
                cfg_parent[key] = copy.deepcopy(params)
            for key, target_params in indicators_template.items():
                if key in self.backtest_indicator_widgets:
                    continue
                if not isinstance(target_params, dict):
                    continue
                params = indicators_cfg.setdefault(key, {})
                params.update(
                    {k: v for k, v in target_params.items() if k != "enabled"}
                )
                params["enabled"] = bool(target_params.get("enabled", True))
                cfg_parent[key] = copy.deepcopy(params)

        margin_mode = str(template.get("margin_mode") or "")
        if margin_mode:
            with QtCore.QSignalBlocker(self.backtest_margin_mode_combo):
                idx_margin = self.backtest_margin_mode_combo.findText(
                    margin_mode,
                    QtCore.Qt.MatchFlag.MatchFixedString,
                )
                if idx_margin < 0:
                    idx_margin = self.backtest_margin_mode_combo.findText(margin_mode)
                if idx_margin >= 0:
                    self.backtest_margin_mode_combo.setCurrentIndex(idx_margin)
            self._update_backtest_config("margin_mode", margin_mode)

        position_mode = str(template.get("position_mode") or "")
        if position_mode:
            with QtCore.QSignalBlocker(self.backtest_position_mode_combo):
                idx_position = self.backtest_position_mode_combo.findText(
                    position_mode,
                    QtCore.Qt.MatchFlag.MatchFixedString,
                )
                if idx_position < 0:
                    idx_position = self.backtest_position_mode_combo.findText(position_mode)
                if idx_position >= 0:
                    self.backtest_position_mode_combo.setCurrentIndex(idx_position)
            self._update_backtest_config("position_mode", position_mode)

        assets_mode = str(template.get("assets_mode") or "")
        if assets_mode:
            normalized_assets = self._normalize_assets_mode(assets_mode)
            with QtCore.QSignalBlocker(self.backtest_assets_mode_combo):
                idx_assets = self.backtest_assets_mode_combo.findData(normalized_assets)
                if idx_assets < 0:
                    idx_assets = 0
                self.backtest_assets_mode_combo.setCurrentIndex(idx_assets)
            self._update_backtest_config("assets_mode", normalized_assets)

        account_mode = str(template.get("account_mode") or "")
        if account_mode:
            normalized_account = self._normalize_account_mode(account_mode)
            with QtCore.QSignalBlocker(self.backtest_account_mode_combo):
                idx_account = self.backtest_account_mode_combo.findData(normalized_account)
                if idx_account < 0:
                    idx_account = 0
                self.backtest_account_mode_combo.setCurrentIndex(idx_account)
            self._update_backtest_config("account_mode", normalized_account)

        leverage_value = int(
            template.get("leverage", self.backtest_config.get("leverage", 5) or 1)
        )
        with QtCore.QSignalBlocker(self.backtest_leverage_spin):
            self.backtest_leverage_spin.setValue(leverage_value)
        self._update_backtest_config("leverage", leverage_value)

        connector_backend = template.get("connector_backend")
        if connector_backend:
            normalized_connector = _normalize_connector_backend(connector_backend)
            combo = getattr(self, "backtest_connector_combo", None)
            if combo is not None:
                idx_conn = combo.findData(normalized_connector)
                if idx_conn < 0:
                    idx_conn = combo.findText(
                        normalized_connector,
                        QtCore.Qt.MatchFlag.MatchFixedString,
                    )
                if idx_conn < 0:
                    idx_conn = combo.findText(normalized_connector)
                if idx_conn >= 0:
                    with QtCore.QSignalBlocker(combo):
                        combo.setCurrentIndex(idx_conn)
            self.backtest_config["connector_backend"] = normalized_connector
            self.config.setdefault("backtest", {})["connector_backend"] = normalized_connector

        template_mdd = template.get("mdd_logic")
        if template_mdd:
            self._set_backtest_mdd_selection(template_mdd, update_config=True)

        loop_override_value = template.get("loop_interval_override")
        if loop_override_value is not None:
            normalized_loop = self._normalize_loop_override(loop_override_value)
            if hasattr(self, "backtest_loop_combo"):
                self._set_loop_combo_value(self.backtest_loop_combo, normalized_loop)
            self._update_backtest_config("loop_interval_override", normalized_loop or "")
    except Exception:
        pass


def _update_backtest_config(self, key, value):
    try:
        if key == "side":
            value = self._canonical_side_from_text(value)
        if key == "assets_mode":
            value = self._normalize_assets_mode(value)
        if key == "account_mode":
            value = self._normalize_account_mode(value)
        self.backtest_config[key] = value
        cfg = self.config.setdefault("backtest", {})
        cfg[key] = value
    except Exception:
        pass


def _backtest_toggle_indicator(self, key: str, checked: bool):
    try:
        indicators = self.backtest_config.setdefault("indicators", {})
        params = indicators.setdefault(key, {})
        params["enabled"] = bool(checked)
        cfg = self.config.setdefault("backtest", {}).setdefault("indicators", {})
        cfg[key] = copy.deepcopy(params)
    except Exception:
        pass


def _open_backtest_params(self, key: str):
    try:
        params = self.backtest_config.setdefault("indicators", {}).setdefault(key, {})
        dlg = _ParamDialog(
            key,
            params,
            self,
            display_name=_INDICATOR_DISPLAY_NAMES.get(key, key),
        )
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            updates = dlg.get_params()
            params.update(updates)
            cfg = self.config.setdefault("backtest", {}).setdefault("indicators", {})
            cfg[key] = copy.deepcopy(params)
    except Exception:
        pass


def bind_main_window_backtest_template_runtime(
    main_window_cls,
    *,
    mdd_logic_options,
    mdd_logic_default,
    backtest_template_definitions,
    backtest_template_default,
    indicator_display_names,
    side_labels,
    normalize_connector_backend,
    param_dialog_cls,
) -> None:
    global _MDD_LOGIC_OPTIONS
    global _MDD_LOGIC_DEFAULT
    global _BACKTEST_TEMPLATE_DEFINITIONS
    global _BACKTEST_TEMPLATE_DEFAULT
    global _INDICATOR_DISPLAY_NAMES
    global _SIDE_LABELS
    global _normalize_connector_backend
    global _ParamDialog

    _MDD_LOGIC_OPTIONS = tuple(mdd_logic_options or ())
    _MDD_LOGIC_DEFAULT = str(mdd_logic_default or "overall")
    _BACKTEST_TEMPLATE_DEFINITIONS = dict(backtest_template_definitions or {})
    _BACKTEST_TEMPLATE_DEFAULT = dict(backtest_template_default or {})
    _INDICATOR_DISPLAY_NAMES = dict(indicator_display_names or {})
    _SIDE_LABELS = dict(side_labels or {})
    if callable(normalize_connector_backend):
        _normalize_connector_backend = normalize_connector_backend
    _ParamDialog = param_dialog_cls

    main_window_cls._get_selected_mdd_logic = _get_selected_mdd_logic
    main_window_cls._set_backtest_mdd_selection = _set_backtest_mdd_selection
    main_window_cls._on_backtest_mdd_logic_changed = _on_backtest_mdd_logic_changed
    main_window_cls._get_selected_template_key = _get_selected_template_key
    main_window_cls._select_backtest_template = _select_backtest_template
    main_window_cls._on_backtest_template_enabled = _on_backtest_template_enabled
    main_window_cls._on_backtest_template_selected = _on_backtest_template_selected
    main_window_cls._apply_backtest_template = _apply_backtest_template
    main_window_cls._update_backtest_config = _update_backtest_config
    main_window_cls._backtest_toggle_indicator = _backtest_toggle_indicator
    main_window_cls._open_backtest_params = _open_backtest_params
