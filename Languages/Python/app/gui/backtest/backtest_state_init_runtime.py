from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from .backtest_state_context_runtime import get_side_labels


def initialize_backtest_ui_defaults(self):
    fetch_triggered = False
    try:
        source = self.backtest_config.get("symbol_source") or "Futures"
        idx = self.backtest_symbol_source_combo.findText(source)
        if (
            idx is not None
            and idx >= 0
            and self.backtest_symbol_source_combo.currentIndex() != idx
        ):
            self.backtest_symbol_source_combo.setCurrentIndex(idx)
            fetch_triggered = True
    except Exception:
        pass
    try:
        self._populate_backtest_lists()
    except Exception:
        pass
    try:
        if self.backtest_stop_btn is not None:
            self.backtest_stop_btn.setEnabled(False)
    except Exception:
        pass
    try:
        logic = (self.backtest_config.get("logic") or "AND").upper()

        def _set_combo(combo: QtWidgets.QComboBox, value: str):
            if combo is None:
                return
            try:
                target = (value or "").strip().lower()
                for i in range(combo.count()):
                    if combo.itemText(i).strip().lower() == target:
                        combo.setCurrentIndex(i)
                        return
            except Exception:
                pass

        _set_combo(self.backtest_logic_combo, logic)
        capital = float(self.backtest_config.get("capital", 1000.0))
        self.backtest_capital_spin.setValue(capital)
        pct_cfg = float(self.backtest_config.get("position_pct", 2.0) or 0.0)
        if pct_cfg <= 1.0:
            pct_disp = pct_cfg * 100.0
            self.backtest_pospct_spin.setValue(pct_disp)
            self._update_backtest_config("position_pct", pct_disp)
        else:
            self.backtest_pospct_spin.setValue(pct_cfg)
        side_cfg = (self.backtest_config.get("side") or "BOTH").upper()
        side_labels = get_side_labels()
        side_label = side_labels.get(side_cfg, side_labels["BOTH"])
        try:
            idx_side = self.backtest_side_combo.findText(
                side_label,
                QtCore.Qt.MatchFlag.MatchFixedString,
            )
        except Exception:
            idx_side = self.backtest_side_combo.findText(side_label)
        if idx_side is not None and idx_side >= 0:
            self.backtest_side_combo.setCurrentIndex(idx_side)
        margin_mode_cfg = self.backtest_config.get("margin_mode") or "Isolated"
        _set_combo(self.backtest_margin_mode_combo, margin_mode_cfg)
        position_mode_cfg = self.backtest_config.get("position_mode") or "Hedge"
        _set_combo(self.backtest_position_mode_combo, position_mode_cfg)
        assets_mode_cfg = self._normalize_assets_mode(
            self.backtest_config.get("assets_mode")
        )
        idx_assets = self.backtest_assets_mode_combo.findData(assets_mode_cfg)
        if idx_assets is not None and idx_assets >= 0:
            with QtCore.QSignalBlocker(self.backtest_assets_mode_combo):
                self.backtest_assets_mode_combo.setCurrentIndex(idx_assets)
        account_mode_cfg = self._normalize_account_mode(
            self.backtest_config.get("account_mode")
        )
        idx_account_mode = self.backtest_account_mode_combo.findData(account_mode_cfg)
        if idx_account_mode is not None and idx_account_mode >= 0:
            with QtCore.QSignalBlocker(self.backtest_account_mode_combo):
                self.backtest_account_mode_combo.setCurrentIndex(idx_account_mode)
        leverage_cfg = int(self.backtest_config.get("leverage", 5) or 1)
        self.backtest_leverage_spin.setValue(leverage_cfg)
        loop_cfg = (
            self._normalize_loop_override(
                self.backtest_config.get("loop_interval_override")
            )
            or ""
        )
        if hasattr(self, "backtest_loop_combo"):
            self._set_loop_combo_value(self.backtest_loop_combo, loop_cfg)
        self.backtest_config["loop_interval_override"] = loop_cfg
        now_dt = QtCore.QDateTime.currentDateTime()
        start_cfg = self.backtest_config.get("start_date")
        end_cfg = self.backtest_config.get("end_date")
        end_qdt = self._coerce_qdatetime(end_cfg) if end_cfg else now_dt
        if not end_qdt.isValid():
            end_qdt = now_dt
        start_qdt = self._coerce_qdatetime(start_cfg) if start_cfg else end_qdt.addMonths(-3)
        if not start_qdt.isValid() or start_qdt > end_qdt:
            start_qdt = end_qdt.addMonths(-3)
        self.backtest_start_edit.setDateTime(start_qdt)
        self.backtest_end_edit.setDateTime(end_qdt)
    except Exception:
        pass
    try:
        self._update_backtest_stop_loss_widgets()
    except Exception:
        pass
    self._update_backtest_futures_controls()
    if not fetch_triggered:
        self._refresh_backtest_symbols()

