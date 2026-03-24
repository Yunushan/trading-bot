from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path

from PyQt6 import QtCore, QtWidgets

_NORMALIZE_STOP_LOSS_DICT: Callable[[object], dict] | None = None
_QT_CHARTS_AVAILABLE = False
_TRADINGVIEW_SUPPORTED: Callable[[], bool] | None = None
_LANGUAGE_PATHS: dict = {}
_EXCHANGE_PATHS: dict = {}
_FOREX_BROKER_PATHS: dict = {}
_LEAD_TRADER_OPTIONS: list[tuple[str, str]] = []


def _normalize_stop_loss(value):
    func = _NORMALIZE_STOP_LOSS_DICT
    if callable(func):
        return func(value)
    return value


def _tradingview_supported_flag() -> bool:
    func = _TRADINGVIEW_SUPPORTED
    if not callable(func):
        return False
    try:
        return bool(func())
    except Exception:
        return False


def _default_lead_trader_profile() -> str:
    if _LEAD_TRADER_OPTIONS:
        try:
            return str(_LEAD_TRADER_OPTIONS[0][1])
        except Exception:
            pass
    return ""


def _load_app_state_file(path: Path) -> dict:
    try:
        if path.is_file():
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _save_app_state_file(path: Path, data: dict) -> None:
    try:
        if not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    except Exception:
        pass


def save_config(self):
    try:
        dlg = QtWidgets.QFileDialog(self)
        dlg.setAcceptMode(QtWidgets.QFileDialog.AcceptMode.AcceptSave)
        dlg.setNameFilter("JSON Files (*.json)")
        dlg.setDefaultSuffix("json")
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            fn = dlg.selectedFiles()[0]
            with open(fn, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            self.log(f"Saved config to {fn}")
    except Exception as e:
        try:
            self.log(f"Save config error: {e}")
        except Exception:
            pass


def load_config(self):
    try:
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Load Config", "", "JSON Files (*.json)")
        if not fn:
            return
        with open(fn, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if isinstance(cfg, dict):
            self.config.update(cfg)
        self.config["stop_loss"] = _normalize_stop_loss(self.config.get("stop_loss"))
        backtest_cfg = self.config.get("backtest", {})
        if not isinstance(backtest_cfg, dict):
            backtest_cfg = {}
        backtest_cfg = copy.deepcopy(backtest_cfg)
        backtest_cfg["stop_loss"] = _normalize_stop_loss(backtest_cfg.get("stop_loss"))
        self.config["backtest"] = backtest_cfg
        self.backtest_config.update(copy.deepcopy(backtest_cfg))
        chart_cfg = self.config.get("chart")
        if not isinstance(chart_cfg, dict):
            chart_cfg = {}
        self.config["chart"] = chart_cfg
        self.chart_config = chart_cfg
        if getattr(self, "chart_enabled", False):
            self.chart_config.setdefault("auto_follow", True)
            self.chart_auto_follow = bool(self.chart_config.get("auto_follow", True))
            default_view_mode = "tradingview" if _tradingview_supported_flag() else "original"
            self.chart_config.setdefault("view_mode", default_view_mode)
            self._restore_chart_controls_from_config()
            current_market_text = self.chart_market_combo.currentText() if hasattr(self, "chart_market_combo") else "Futures"
            self._chart_needs_render = True
            self._on_chart_market_changed(current_market_text)
            if self.chart_auto_follow:
                self._apply_dashboard_selection_to_chart(load=True)
            elif _QT_CHARTS_AVAILABLE:
                try:
                    if self._is_chart_visible() or self._chart_pending_initial_load:
                        self.load_chart(auto=True)
                except Exception:
                    pass
        self.config.setdefault("runtime_symbol_interval_pairs", [])
        self.config.setdefault("backtest_symbol_interval_pairs", [])
        self.backtest_config.setdefault(
            "backtest_symbol_interval_pairs",
            list(self.config.get("backtest_symbol_interval_pairs", [])),
        )
        self._refresh_symbol_interval_pairs("runtime")
        self._refresh_symbol_interval_pairs("backtest")
        self.config.setdefault("code_language", next(iter(_LANGUAGE_PATHS)))
        self.config.setdefault("selected_exchange", next(iter(_EXCHANGE_PATHS)))
        if _FOREX_BROKER_PATHS:
            self.config.setdefault("selected_forex_broker", next(iter(_FOREX_BROKER_PATHS)))
        else:
            self.config.setdefault("selected_forex_broker", None)
        self._sync_language_exchange_lists_from_config()
        try:
            self._sync_service_config_snapshot()
        except Exception:
            pass
        self.log(f"Loaded config from {fn}")
        try:
            self.leverage_spin.setValue(int(self.config.get("leverage", self.leverage_spin.value())))
            self.margin_mode_combo.setCurrentText(self.config.get("margin_mode", self.margin_mode_combo.currentText()))
            self.position_mode_combo.setCurrentText(
                self.config.get("position_mode", self.position_mode_combo.currentText())
            )
            assets_mode_loaded = self._normalize_assets_mode(
                self.config.get("assets_mode", self.assets_mode_combo.currentData())
            )
            idx_assets_loaded = self.assets_mode_combo.findData(assets_mode_loaded)
            if idx_assets_loaded is not None and idx_assets_loaded >= 0:
                with QtCore.QSignalBlocker(self.assets_mode_combo):
                    self.assets_mode_combo.setCurrentIndex(idx_assets_loaded)
            account_mode_loaded = self._normalize_account_mode(
                self.config.get("account_mode", self.account_mode_combo.currentData())
            )
            idx_account_loaded = self.account_mode_combo.findData(account_mode_loaded)
            if idx_account_loaded is not None and idx_account_loaded >= 0:
                with QtCore.QSignalBlocker(self.account_mode_combo):
                    self.account_mode_combo.setCurrentIndex(idx_account_loaded)
            self.tif_combo.setCurrentText(self.config.get("tif", self.tif_combo.currentText()))
            self.gtd_minutes_spin.setValue(int(self.config.get("gtd_minutes", self.gtd_minutes_spin.value())))
            backtest_assets_mode_loaded = self._normalize_assets_mode(
                self.backtest_config.get("assets_mode", self.backtest_assets_mode_combo.currentData())
            )
            idx_backtest_assets = self.backtest_assets_mode_combo.findData(backtest_assets_mode_loaded)
            if idx_backtest_assets is not None and idx_backtest_assets >= 0:
                with QtCore.QSignalBlocker(self.backtest_assets_mode_combo):
                    self.backtest_assets_mode_combo.setCurrentIndex(idx_backtest_assets)
            backtest_account_mode_loaded = self._normalize_account_mode(
                self.backtest_config.get("account_mode", self.backtest_account_mode_combo.currentData())
            )
            idx_backtest_account = self.backtest_account_mode_combo.findData(backtest_account_mode_loaded)
            if idx_backtest_account is not None and idx_backtest_account >= 0:
                with QtCore.QSignalBlocker(self.backtest_account_mode_combo):
                    self.backtest_account_mode_combo.setCurrentIndex(idx_backtest_account)
            self._apply_runtime_account_mode_constraints(account_mode_loaded)
            self._apply_backtest_account_mode_constraints(backtest_account_mode_loaded)
            loop_loaded = self._normalize_loop_override(self.config.get("loop_interval_override"))
            if not loop_loaded:
                loop_loaded = "1m"
            self._set_loop_combo_value(getattr(self, "loop_combo", None), loop_loaded)
            self.config["loop_interval_override"] = loop_loaded or ""
            backtest_loop_loaded = self._normalize_loop_override(self.backtest_config.get("loop_interval_override"))
            self._set_loop_combo_value(getattr(self, "backtest_loop_combo", None), backtest_loop_loaded)
            self.backtest_config["loop_interval_override"] = backtest_loop_loaded or ""
            self.config.setdefault("backtest", {})["loop_interval_override"] = backtest_loop_loaded or ""
            lead_enabled_loaded = bool(self.config.get("lead_trader_enabled", False))
            if hasattr(self, "lead_trader_enable_cb") and self.lead_trader_enable_cb is not None:
                with QtCore.QSignalBlocker(self.lead_trader_enable_cb):
                    self.lead_trader_enable_cb.setChecked(lead_enabled_loaded)
            lead_profile_loaded = self.config.get("lead_trader_profile") or _default_lead_trader_profile()
            if hasattr(self, "lead_trader_combo") and self.lead_trader_combo is not None:
                idx_lead_loaded = self.lead_trader_combo.findData(lead_profile_loaded)
                if idx_lead_loaded < 0:
                    idx_lead_loaded = 0
                with QtCore.QSignalBlocker(self.lead_trader_combo):
                    self.lead_trader_combo.setCurrentIndex(idx_lead_loaded)
                self.config["lead_trader_profile"] = str(
                    self.lead_trader_combo.itemData(self.lead_trader_combo.currentIndex())
                )
            self._apply_lead_trader_state(lead_enabled_loaded)
            runtime_backend = self._runtime_connector_backend(suppress_refresh=True)
            if hasattr(self, "connector_combo") and self.connector_combo is not None:
                idx_runtime_connector = self.connector_combo.findData(runtime_backend)
                if idx_runtime_connector is not None and idx_runtime_connector >= 0:
                    with QtCore.QSignalBlocker(self.connector_combo):
                        self.connector_combo.setCurrentIndex(idx_runtime_connector)
            backtest_backend = self._backtest_connector_backend()
            if hasattr(self, "backtest_connector_combo") and self.backtest_connector_combo is not None:
                idx_backtest_connector = self.backtest_connector_combo.findData(backtest_backend)
                if idx_backtest_connector is not None and idx_backtest_connector >= 0:
                    with QtCore.QSignalBlocker(self.backtest_connector_combo):
                        self.backtest_connector_combo.setCurrentIndex(idx_backtest_connector)
            self._update_runtime_stop_loss_widgets()
            self._update_backtest_stop_loss_widgets()
            self._update_connector_labels()
        except Exception:
            pass
    except Exception as e:
        try:
            self.log(f"Load config error: {e}")
        except Exception:
            pass


def _snapshot_auth_state(self) -> dict:
    """Capture auth/mode state on the UI thread to avoid cross-thread UI access in workers."""
    try:
        api_key = self.api_key_edit.text().strip()
    except Exception:
        api_key = ""
    try:
        api_secret = self.api_secret_edit.text().strip()
    except Exception:
        api_secret = ""
    try:
        mode = self.mode_combo.currentText()
    except Exception:
        mode = "Live"
    try:
        account_type = self.account_combo.currentText()
    except Exception:
        account_type = "Futures"
    try:
        leverage_val = int(self.leverage_spin.value() or 1)
    except Exception:
        leverage_val = 1
    try:
        margin_mode = self.margin_mode_combo.currentText() or "Isolated"
    except Exception:
        margin_mode = "Isolated"
    return {
        "api_key": api_key,
        "api_secret": api_secret,
        "mode": mode,
        "account_type": account_type,
        "default_leverage": leverage_val,
        "default_margin_mode": margin_mode,
    }


def _build_wrapper_from_values(self, auth: dict):
    return self._create_binance_wrapper(
        api_key=auth.get("api_key", ""),
        api_secret=auth.get("api_secret", ""),
        mode=auth.get("mode", "Live"),
        account_type=auth.get("account_type", "Futures"),
        default_leverage=int(auth.get("default_leverage", 1) or 1),
        default_margin_mode=auth.get("default_margin_mode", "Isolated") or "Isolated",
    )


def _build_wrapper_from_ui(self):
    """Always build a fresh wrapper using current UI values (mode, account, creds)."""
    return _build_wrapper_from_values(self, _snapshot_auth_state(self))


def bind_main_window_config(
    main_window_cls,
    *,
    normalize_stop_loss_dict,
    qt_charts_available: bool,
    tradingview_supported,
    language_paths: dict,
    exchange_paths: dict,
    forex_broker_paths: dict,
    lead_trader_options,
) -> None:
    global _NORMALIZE_STOP_LOSS_DICT
    global _QT_CHARTS_AVAILABLE
    global _TRADINGVIEW_SUPPORTED
    global _LANGUAGE_PATHS
    global _EXCHANGE_PATHS
    global _FOREX_BROKER_PATHS
    global _LEAD_TRADER_OPTIONS

    _NORMALIZE_STOP_LOSS_DICT = normalize_stop_loss_dict
    _QT_CHARTS_AVAILABLE = bool(qt_charts_available)
    _TRADINGVIEW_SUPPORTED = tradingview_supported
    _LANGUAGE_PATHS = dict(language_paths or {})
    _EXCHANGE_PATHS = dict(exchange_paths or {})
    _FOREX_BROKER_PATHS = dict(forex_broker_paths or {})
    _LEAD_TRADER_OPTIONS = list(lead_trader_options or [])

    main_window_cls.save_config = save_config
    main_window_cls.load_config = load_config
    main_window_cls._snapshot_auth_state = _snapshot_auth_state
    main_window_cls._build_wrapper_from_values = _build_wrapper_from_values
    main_window_cls._build_wrapper_from_ui = _build_wrapper_from_ui
