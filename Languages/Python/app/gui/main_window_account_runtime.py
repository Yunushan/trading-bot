from __future__ import annotations

from PyQt6 import QtCore

from app.binance_wrapper import BinanceWrapper

_CONNECTOR_OPTIONS = ()
_DEFAULT_CONNECTOR_BACKEND = ""
_FUTURES_CONNECTOR_KEYS = frozenset()
_SPOT_CONNECTOR_KEYS = frozenset()
_SIDE_LABELS = {}
_normalize_connector_backend = lambda value: value  # type: ignore
_recommended_connector_for_key = lambda account_key: account_key  # type: ignore
_refresh_dependency_usage_labels = lambda window: None  # type: ignore


def _normalize_assets_mode(value):
    text = str(value or "").strip().lower()
    if "multi" in text:
        return "Multi-Assets"
    return "Single-Asset"


def _normalize_account_mode(value):
    text = str(value or "").strip().lower()
    if "portfolio" in text:
        return "Portfolio Margin"
    return "Classic Trading"


def _update_leverage_enabled(self):
    """Disable leverage control when Spot is selected."""
    try:
        acct = str(self.config.get("account_type") or "")
        is_futures = acct.strip().upper().startswith("FUT")
    except Exception:
        is_futures = True
    try:
        spin = getattr(self, "leverage_spin", None)
        if spin is not None:
            if not is_futures:
                spin.setValue(1)
            spin.setEnabled(is_futures)
    except Exception:
        pass
    futures_only_widgets = []
    try:
        futures_only_widgets.extend(
            [
                getattr(self, "margin_mode_combo", None),
                getattr(self, "position_mode_combo", None),
                getattr(self, "assets_mode_combo", None),
                getattr(self, "account_mode_combo", None),
                getattr(self, "allow_opposite_checkbox", None),
                getattr(self, "cb_add_only", None),
                getattr(self, "lead_trader_enable_cb", None),
                getattr(self, "lead_trader_combo", None),
            ]
        )
    except Exception:
        pass
    for widget in futures_only_widgets:
        try:
            if widget is None:
                continue
            widget.setEnabled(is_futures)
        except Exception:
            pass
    try:
        side_combo = getattr(self, "side_combo", None)
        if side_combo is not None:
            if not is_futures:
                label_buy = _SIDE_LABELS["BUY"]
                idx_buy = side_combo.findText(label_buy)
                if idx_buy >= 0:
                    blocker = None
                    try:
                        blocker = QtCore.QSignalBlocker(side_combo)
                    except Exception:
                        blocker = None
                    side_combo.setCurrentIndex(idx_buy)
                    if blocker is not None:
                        del blocker
                side_combo.setEnabled(False)
            else:
                side_combo.setEnabled(True)
    except Exception:
        pass


def _rebuild_connector_combo_for_account(
    self,
    account_key: str,
    *,
    force_default: bool = False,
    current_backend: str | None = None,
) -> str:
    """Ensure the connector dropdown matches the selected account type."""
    allowed = _FUTURES_CONNECTOR_KEYS if account_key == "FUTURES" else _SPOT_CONNECTOR_KEYS
    recommended = _recommended_connector_for_key(account_key)
    target = _normalize_connector_backend(current_backend or self.config.get("connector_backend"))
    if force_default or target not in allowed:
        target = recommended
    combo = getattr(self, "connector_combo", None)
    chosen = target
    if combo is not None:
        try:
            blocker = QtCore.QSignalBlocker(combo)
        except Exception:
            blocker = None
        combo.clear()
        for label, value in _CONNECTOR_OPTIONS:
            if value in allowed:
                combo.addItem(label, value)
        if combo.count():
            idx = combo.findData(target)
            if idx < 0:
                idx = combo.findData(recommended)
            if idx < 0:
                idx = 0
            combo.setCurrentIndex(max(0, idx))
            try:
                chosen = _normalize_connector_backend(combo.itemData(combo.currentIndex()))
            except Exception:
                chosen = target
        if blocker is not None:
            del blocker
    self.config["connector_backend"] = chosen
    return chosen


def _ensure_runtime_connector_for_account(
    self,
    account_type: str,
    *,
    force_default: bool = False,
    suppress_refresh: bool = False,
) -> str:
    account_key = "FUTURES" if str(account_type or "Futures").upper().startswith("FUT") else "SPOT"
    current_backend = _normalize_connector_backend(self.config.get("connector_backend"))
    chosen = self._rebuild_connector_combo_for_account(
        account_key,
        force_default=force_default,
        current_backend=current_backend,
    )
    if not suppress_refresh:
        self._update_connector_labels()
    return self.config.get("connector_backend", chosen)


def _runtime_connector_backend(self, *, suppress_refresh: bool = False) -> str:
    account_type = str(self.config.get("account_type", "Futures") or "Futures")
    return self._ensure_runtime_connector_for_account(
        account_type,
        force_default=False,
        suppress_refresh=suppress_refresh,
    )


def _backtest_connector_backend(self) -> str:
    source_text = ""
    if hasattr(self, "backtest_symbol_source_combo") and self.backtest_symbol_source_combo is not None:
        try:
            source_text = self.backtest_symbol_source_combo.currentText()
        except Exception:
            source_text = ""
    source_key = "SPOT" if str(source_text or "Futures").strip().lower().startswith("spot") else "FUTURES"
    allowed = _FUTURES_CONNECTOR_KEYS if source_key == "FUTURES" else _SPOT_CONNECTOR_KEYS
    recommended = _recommended_connector_for_key(source_key)
    backend = _normalize_connector_backend(self.backtest_config.get("connector_backend"))
    if backend not in allowed:
        backend = recommended
    self.backtest_config["connector_backend"] = backend
    self.config.setdefault("backtest", {})["connector_backend"] = backend
    return backend


def _create_binance_wrapper(
    self,
    *,
    api_key: str,
    api_secret: str,
    mode: str,
    account_type: str,
    connector_backend: str | None = None,
    **kwargs,
) -> BinanceWrapper:
    backend = connector_backend or self._runtime_connector_backend(suppress_refresh=True)
    return BinanceWrapper(
        api_key,
        api_secret,
        mode=mode,
        account_type=account_type,
        connector_backend=backend,
        **kwargs,
    )


def _invalidate_shared_binance(self, reason: str | None = None):
    try:
        existing = getattr(self, "shared_binance", None)
    except Exception:
        existing = None
    if existing is not None:
        try:
            self.shared_binance = None
        except Exception:
            self.__dict__["shared_binance"] = None
    try:
        self._shared_binance_invalidated_reason = reason
    except Exception:
        pass
    try:
        if getattr(self, "balance_label", None):
            self.balance_label.setText("N/A")
    except Exception:
        pass
    try:
        self._update_positions_balance_labels(None, None)
    except Exception:
        pass


def _on_api_credentials_changed(self):
    self._invalidate_shared_binance("credentials_changed")
    self._reconfigure_positions_worker()


def _on_mode_changed(self, value: str):
    try:
        self.config["mode"] = str(value or self.mode_combo.currentText() or "Live")
    except Exception:
        pass
    self._invalidate_shared_binance("mode_changed")
    self._reconfigure_positions_worker()


def _connector_label_text(self, backend: str) -> str:
    backend = _normalize_connector_backend(backend)
    for label, value in _CONNECTOR_OPTIONS:
        if value == backend:
            return label
    return backend.title()


def _update_connector_labels(self):
    try:
        self._refresh_symbol_interval_pairs("runtime")
    except Exception:
        pass
    try:
        self._refresh_symbol_interval_pairs("backtest")
    except Exception:
        pass
    try:
        _refresh_dependency_usage_labels(self)
    except Exception:
        pass


def _on_account_type_changed(self, value):
    account_text = str(value or "").strip()
    try:
        if not account_text and hasattr(self, "account_combo"):
            account_text = str(self.account_combo.currentText() or "Futures").strip()
    except Exception:
        account_text = "Futures"
    if not account_text:
        account_text = "Futures"
    normalized = "Futures" if account_text.lower().startswith("fut") else "Spot"
    self.config["account_type"] = normalized
    self._invalidate_shared_binance("account_type_changed")
    self._ensure_runtime_connector_for_account(normalized, force_default=False)
    self._update_leverage_enabled()
    desired_spot = "Binance spot"
    desired_futures = "Binance futures"
    try:
        combo = getattr(self, "ind_source_combo", None)
        if combo is not None:
            current_source = (combo.currentText() or "").strip()
            lowered = current_source.lower()
            target_source = current_source
            if normalized == "Spot" and "futures" in lowered:
                target_source = desired_spot
            elif normalized == "Futures" and ("spot" in lowered and "futures" not in lowered):
                target_source = desired_futures
            if target_source and target_source != current_source:
                blocker = None
                try:
                    blocker = QtCore.QSignalBlocker(combo)
                except Exception:
                    blocker = None
                combo.setCurrentText(target_source)
                if blocker is not None:
                    del blocker
            self.config["indicator_source"] = combo.currentText()
            if hasattr(self, "shared_binance") and self.shared_binance is not None:
                try:
                    self.shared_binance.indicator_source = combo.currentText()
                except Exception:
                    pass
    except Exception:
        pass


def _refresh_backtest_connector_options(
    self,
    symbol_source: str | None = None,
    *,
    force_default: bool = False,
) -> None:
    if not hasattr(self, "backtest_connector_combo") or self.backtest_connector_combo is None:
        return
    source_text = symbol_source or ""
    if (
        not source_text
        and hasattr(self, "backtest_symbol_source_combo")
        and self.backtest_symbol_source_combo is not None
    ):
        try:
            source_text = self.backtest_symbol_source_combo.currentText()
        except Exception:
            source_text = ""
    source_key = "SPOT" if str(source_text or "Futures").strip().lower().startswith("spot") else "FUTURES"
    allowed = _FUTURES_CONNECTOR_KEYS if source_key == "FUTURES" else _SPOT_CONNECTOR_KEYS
    recommended = _recommended_connector_for_key(source_key)
    current_backend = _normalize_connector_backend(self.backtest_config.get("connector_backend"))
    if force_default or current_backend not in allowed:
        current_backend = recommended
    blocker = None
    try:
        blocker = QtCore.QSignalBlocker(self.backtest_connector_combo)
    except Exception:
        blocker = None
    self.backtest_connector_combo.clear()
    for label, value in _CONNECTOR_OPTIONS:
        if value in allowed:
            self.backtest_connector_combo.addItem(label, value)
    idx = self.backtest_connector_combo.findData(current_backend)
    if idx < 0:
        idx = self.backtest_connector_combo.findData(recommended)
    if idx < 0 and self.backtest_connector_combo.count():
        idx = 0
    if idx >= 0 and self.backtest_connector_combo.count():
        self.backtest_connector_combo.setCurrentIndex(idx)
        current_backend = _normalize_connector_backend(self.backtest_connector_combo.currentData())
    if blocker is not None:
        del blocker
    self.backtest_config["connector_backend"] = current_backend
    self.config.setdefault("backtest", {})["connector_backend"] = current_backend
    self._update_backtest_config("connector_backend", current_backend)
    self._update_connector_labels()
    try:
        self._reconfigure_positions_worker()
    except Exception:
        pass
    if getattr(self, "_ui_initialized", False):
        try:
            self.refresh_symbols()
        except Exception:
            pass


def _on_runtime_connector_changed(self, *_args):
    try:
        data = None
        if hasattr(self, "connector_combo") and self.connector_combo is not None:
            data = self.connector_combo.currentData()
            if data is None:
                data = self.connector_combo.currentText()
        backend = _normalize_connector_backend(data)
    except Exception:
        backend = _DEFAULT_CONNECTOR_BACKEND
    self.config["connector_backend"] = backend
    self._update_connector_labels()
    try:
        self._reconfigure_positions_worker()
    except Exception:
        pass


def _on_backtest_connector_changed(self, *_args):
    try:
        data = None
        if hasattr(self, "backtest_connector_combo") and self.backtest_connector_combo is not None:
            data = self.backtest_connector_combo.currentData()
            if data is None:
                data = self.backtest_connector_combo.currentText()
        backend = _normalize_connector_backend(data)
    except Exception:
        backend = _DEFAULT_CONNECTOR_BACKEND
    self.backtest_config["connector_backend"] = backend
    self.config.setdefault("backtest", {})["connector_backend"] = backend
    self._update_connector_labels()


def bind_main_window_account_runtime(
    MainWindow,
    *,
    connector_options,
    default_connector_backend,
    futures_connector_keys,
    spot_connector_keys,
    side_labels,
    normalize_connector_backend,
    recommended_connector_for_key,
    refresh_dependency_usage_labels,
):
    global _CONNECTOR_OPTIONS
    global _DEFAULT_CONNECTOR_BACKEND
    global _FUTURES_CONNECTOR_KEYS
    global _SPOT_CONNECTOR_KEYS
    global _SIDE_LABELS
    global _normalize_connector_backend
    global _recommended_connector_for_key
    global _refresh_dependency_usage_labels

    _CONNECTOR_OPTIONS = tuple(connector_options)
    _DEFAULT_CONNECTOR_BACKEND = default_connector_backend
    _FUTURES_CONNECTOR_KEYS = frozenset(futures_connector_keys)
    _SPOT_CONNECTOR_KEYS = frozenset(spot_connector_keys)
    _SIDE_LABELS = dict(side_labels)
    _normalize_connector_backend = normalize_connector_backend
    _recommended_connector_for_key = recommended_connector_for_key
    _refresh_dependency_usage_labels = refresh_dependency_usage_labels

    MainWindow._normalize_assets_mode = staticmethod(_normalize_assets_mode)
    MainWindow._normalize_account_mode = staticmethod(_normalize_account_mode)
    MainWindow._update_leverage_enabled = _update_leverage_enabled
    MainWindow._rebuild_connector_combo_for_account = _rebuild_connector_combo_for_account
    MainWindow._ensure_runtime_connector_for_account = _ensure_runtime_connector_for_account
    MainWindow._runtime_connector_backend = _runtime_connector_backend
    MainWindow._backtest_connector_backend = _backtest_connector_backend
    MainWindow._create_binance_wrapper = _create_binance_wrapper
    MainWindow._invalidate_shared_binance = _invalidate_shared_binance
    MainWindow._on_api_credentials_changed = _on_api_credentials_changed
    MainWindow._on_mode_changed = _on_mode_changed
    MainWindow._connector_label_text = _connector_label_text
    MainWindow._update_connector_labels = _update_connector_labels
    MainWindow._on_account_type_changed = _on_account_type_changed
    MainWindow._refresh_backtest_connector_options = _refresh_backtest_connector_options
    MainWindow._on_runtime_connector_changed = _on_runtime_connector_changed
    MainWindow._on_backtest_connector_changed = _on_backtest_connector_changed
