from PyQt6 import QtCore, QtGui, QtWidgets
from pathlib import Path

from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import pyqtSignal
import re
import copy, threading
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone

from ..config import DEFAULT_CONFIG, INDICATOR_DISPLAY_NAMES
from ..binance_wrapper import BinanceWrapper, normalize_margin_ratio
from ..backtester import BacktestEngine, BacktestRequest, IndicatorDefinition
from ..strategy import StrategyEngine
from ..workers import StopWorker, StartWorker, CallWorker

BINANCE_SUPPORTED_INTERVALS = {
    "1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1mo"
}

BACKTEST_INTERVAL_ORDER = ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w"]




class _PositionsWorker(QtCore.QObject):
    positions_ready = QtCore.pyqtSignal(list, str)  # rows, account_type
    error = QtCore.pyqtSignal(str)

    def __init__(self, api_key:str, api_secret:str, mode:str, account_type:str, parent=None):
        super().__init__(parent)
        self._api_key = api_key
        self._api_secret = api_secret
        self._mode = mode
        self._acct = account_type
        self._symbols = None  # optional filter set
        self._busy = False
        self._timer = None
        self._wrapper = None
        self._last_err_ts = 0
        self._enabled = True
        self._interval_ms = 5000

    @QtCore.pyqtSlot(int)
    def start_with_interval(self, interval_ms: int):
        try:
            self._enabled = True
            self._interval_ms = int(max(200, int(interval_ms)))
            if self._timer is not None:
                try:
                    self._timer.stop()
                    self._timer.deleteLater()
                except Exception:
                    pass
            self._timer = QtCore.QTimer(self)
            self._timer.setInterval(self._interval_ms)
            self._timer.timeout.connect(self._tick)
            self._timer.start()
            # immediate tick
            try:
                self._tick()
            except Exception:
                pass
        except Exception:
            pass

    @QtCore.pyqtSlot()
    def stop_timer(self):
        try:
            self._enabled = False
            if self._timer is not None:
                try:
                    self._timer.stop()
                    self._timer.deleteLater()
                except Exception:
                    pass
            self._timer = None
        except Exception:
            pass

    @QtCore.pyqtSlot(int)
    def set_interval(self, interval_ms: int):
        try:
            self._interval_ms = int(max(200, int(interval_ms)))
            if self._timer is not None:
                self._timer.setInterval(self._interval_ms)
        except Exception:
            pass

    def configure(self, api_key=None, api_secret=None, mode=None, account_type=None, symbols=None):
        if api_key is not None: self._api_key = api_key
        if api_secret is not None: self._api_secret = api_secret
        if mode is not None: self._mode = mode
        if account_type is not None: self._acct = account_type
        self._symbols = set(symbols) if symbols else None
        # force wrapper rebuild on next tick
        self._wrapper = None

    def _ensure_wrapper(self):
        if self._wrapper is None:
            try:
                self._wrapper = BinanceWrapper(
                    self._api_key or "",
                    self._api_secret or "",
                    mode=self._mode or "Live",
                    account_type=self._acct or "Futures",
                )
            except Exception:
                self._wrapper = None

    def _compute_futures_metrics(self, p:dict):
        try:
            amt = float(p.get('positionAmt') or 0.0)
            mark = float(p.get('markPrice') or 0.0)
            lev = int(float(p.get('leverage') or 0.0)) or 0
            pnl = float(p.get('unRealizedProfit') or 0.0)
            notional = float(p.get('notional') or 0.0)
            if notional == 0.0 and mark and amt:
                notional = abs(amt) * mark
            size_usdt = abs(notional)
            iso_wallet = float(p.get('isolatedWallet') or 0.0)
            margin = iso_wallet
            if margin <= 0.0:
                margin = float(p.get('initialMargin') or 0.0)
            if margin <= 0.0 and lev > 0:
                margin = size_usdt / lev
            roi = (pnl / margin * 100.0) if margin > 0 else 0.0
            pnl_roi_str = f"{pnl:+.2f} USDT ({roi:+.2f}%)"

            # Prefer Binance-provided marginRatio when available, otherwise approximate.
            ratio = normalize_margin_ratio(p.get('marginRatio'))
            if ratio <= 0.0:
                # Margin Ratio (isolated) ~= (maintMargin + unrealizedLoss) / isolatedWallet
                try:
                    mm = float(p.get('maintMargin') or p.get('maintenanceMargin') or 0.0)
                except Exception:
                    mm = 0.0
                unrealized_loss = abs(pnl) if pnl < 0 else 0.0
                margin_balance = iso_wallet + (pnl if pnl > 0 else 0.0)
                denom = margin_balance if margin_balance > 0.0 else float(p.get('isolatedWallet') or 0.0)
                if denom > 0.0:
                    ratio = ((mm + unrealized_loss) / denom) * 100.0
            return size_usdt, margin, pnl_roi_str, ratio
        except Exception:
            return 0.0, 0.0, "-", 0.0


    def _tick(self):
        if not self._enabled:
            return
        if self._busy:
            return
        self._busy = True
        try:
            acct = str(self._acct or "FUTURES").upper()
            self._ensure_wrapper()
            if self._wrapper is None:
                return
            rows = []
            if acct == "FUTURES":
                try:
                    positions = self._wrapper.list_open_futures_positions() or []
                except Exception as e:
                    import time
                    if time.time() - self._last_err_ts > 5:
                        self._last_err_ts = time.time()
                        self.error.emit(f"Positions error: {e}")
                    return
                for p in positions:
                    try:
                        sym = str(p.get('symbol'))
                        if self._symbols and sym not in self._symbols:
                            continue
                        amt = float(p.get('positionAmt') or 0.0)
                        if abs(amt) <= 0.0:
                            continue
                        mark = float(p.get('markPrice') or 0.0)
                        value = abs(amt) * mark if mark else 0.0
                        side_key = 'L' if amt > 0 else 'S'
                        size_usdt, margin_usdt, pnl_roi, margin_ratio = self._compute_futures_metrics(p)
                        rows.append({
                            'symbol': sym,
                            'qty': abs(amt),
                            'mark': mark,
                            'value': value,
                            'size_usdt': size_usdt,
                            'margin_usdt': margin_usdt,
                            'margin_ratio': margin_ratio,
                            'pnl_roi': pnl_roi,
                            'side_key': side_key,
                        })
                    except Exception:
                        pass
            else:
                # SPOT
                try:
                    balances = self._wrapper.get_balances() or []
                except Exception as e:
                    self.error.emit(f"Spot balances error: {e}")
                    return
                base = "USDT"
                for b in balances:
                    try:
                        asset = b.get("asset")
                        free = float(b.get("free") or 0.0)
                        locked = float(b.get("locked") or 0.0)
                        total = free + locked
                        if asset in (base, None) or total <= 0:
                            continue
                        sym = f"{asset}{base}"
                        if self._symbols and sym not in self._symbols:
                            continue
                        last = float(self._wrapper.get_last_price(sym) or 0.0)
                        value = total * last
                        rows.append({
                            'symbol': sym,
                            'qty': total,
                            'mark': last,
                            'value': value,
                            'size_usdt': 0.0,
                            'margin_usdt': 0.0,
                            'pnl_roi': "-",
                            'side_key': 'SPOT',
                        })
                    except Exception:
                        pass
            self.positions_ready.emit(rows, acct)
        finally:
            self._busy = False


class _BacktestWorker(QtCore.QThread):
    progress = QtCore.pyqtSignal(str)
    finished = QtCore.pyqtSignal(dict, object)

    def __init__(self, engine: BacktestEngine, request: BacktestRequest, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.request = request
        self._stop_requested = False

    def request_stop(self):
        self._stop_requested = True

    def run(self):
        try:
            result = self.engine.run(self.request, progress=self.progress.emit,
                                     should_stop=lambda: bool(self._stop_requested))
            self.finished.emit(result, None)
        except Exception as exc:
            self.finished.emit({}, exc)
from ..position_guard import IntervalPositionGuard
from .param_dialog import ParamDialog

class MainWindow(QtWidgets.QWidget):
    log_signal = pyqtSignal(str)
    trade_signal = pyqtSignal(dict)

    # thread-safe control signals for positions worker
    req_pos_start = QtCore.pyqtSignal(int)
    req_pos_stop = QtCore.pyqtSignal()
    req_pos_set_interval = QtCore.pyqtSignal(int)

    LIGHT_THEME = """
    QWidget { background-color: #FFFFFF; color: #000000; font-family: Arial; }
    QGroupBox { border: 1px solid #C0C0C0; margin-top: 6px; }
    QPushButton { background-color: #F0F0F0; border: 1px solid #B0B0B0; padding: 6px; }
    QTextEdit { background-color: #FFFFFF; color: #000000; }
    QLineEdit { background-color: #FFFFFF; color: #000000; }
    QComboBox { background-color: #FFFFFF; color: #000000; }
    QListWidget { background-color: #FFFFFF; color: #000000; }
    QLabel { color: #000000; }
    """

    DARK_THEME = """
    QWidget { background-color: #121212; color: #E0E0E0; font-family: Arial; }
    QGroupBox { border: 1px solid #333; margin-top: 6px; }
    QPushButton { background-color: #1E1E1E; border: 1px solid #333; padding: 6px; }
    QTextEdit { background-color: #0E0E0E; color: #E0E0E0; }
    QLineEdit { background-color: #1E1E1E; color: #E0E0E0; }
    QComboBox { background-color: #1E1E1E; color: #E0E0E0; }
    QListWidget { background-color: #0E0E0E; color: #E0E0E0; }
    QLabel { color: #E0E0E0; }
    """

    def __init__(self):
        super().__init__()
        self.guard = IntervalPositionGuard(stale_ttl_sec=180)
        self.config = copy.deepcopy(DEFAULT_CONFIG)
        self.config.setdefault('theme', 'Dark')
        self.config.setdefault('close_on_exit', False)
        self.strategy_threads = {}
        self.shared_binance = None
        self.stop_worker = None
        self.indicator_widgets = {}
        self.traded_symbols = set()
        self._indicator_runtime_controls = []
        self._runtime_lock_widgets = []
        self.backtest_indicator_widgets = {}
        self.backtest_results = []
        self.backtest_worker = None
        self._backtest_symbol_worker = None
        self.backtest_symbols_all = []
        self._backtest_wrappers = {}
        self.backtest_config = copy.deepcopy(self.config.get("backtest", {}))
        if not self.backtest_config:
            self.backtest_config = copy.deepcopy(DEFAULT_CONFIG.get("backtest", {}))
        else:
            self.backtest_config = copy.deepcopy(self.backtest_config)
        if not self.backtest_config.get("indicators"):
            self.backtest_config["indicators"] = copy.deepcopy(DEFAULT_CONFIG["backtest"]["indicators"])
        default_backtest = DEFAULT_CONFIG.get("backtest", {}) or {}
        self.backtest_config.setdefault("symbol_source", default_backtest.get("symbol_source", "Futures"))
        self.backtest_config.setdefault("capital", float(default_backtest.get("capital", 1000.0)))
        self.backtest_config.setdefault("logic", default_backtest.get("logic", "AND"))
        self.backtest_config.setdefault("start_date", default_backtest.get("start_date"))
        self.backtest_config.setdefault("end_date", default_backtest.get("end_date"))
        self.backtest_config.setdefault("symbols", list(default_backtest.get("symbols", [])))
        self.backtest_config.setdefault("intervals", list(default_backtest.get("intervals", [])))
        self.backtest_config.setdefault("position_pct", float(default_backtest.get("position_pct", 2.0)))
        self.backtest_config.setdefault("side", default_backtest.get("side", "BOTH"))
        self.backtest_config.setdefault("margin_mode", default_backtest.get("margin_mode", "Isolated"))
        self.backtest_config.setdefault("position_mode", default_backtest.get("position_mode", "Hedge"))
        self.backtest_config.setdefault("assets_mode", default_backtest.get("assets_mode", "Single-Asset"))
        self.backtest_config.setdefault("leverage", int(default_backtest.get("leverage", 5)))
        self.backtest_config.setdefault("backtest_symbol_interval_pairs", list(self.config.get("backtest_symbol_interval_pairs", [])))
        self._backtest_futures_widgets = []
        self.config.setdefault("runtime_symbol_interval_pairs", [])
        self.config.setdefault("backtest_symbol_interval_pairs", [])
        self.symbol_interval_table = None
        self.pair_add_btn = None
        self.pair_remove_btn = None
        self.pair_clear_btn = None
        self.backtest_run_btn = None
        self.backtest_stop_btn = None
        self.override_contexts = {}
        self.bot_status_label_tab1 = None
        self.bot_status_label_tab2 = None
        self._bot_active = False
        self.init_ui()
        self.log_signal.connect(self._buffer_log)
        self.trade_signal.connect(self._on_trade_signal)

    def _set_runtime_controls_enabled(self, enabled: bool):
        try:
            widgets = getattr(self, "_runtime_lock_widgets", [])
            for widget in widgets:
                if widget is None:
                    continue
                widget.setEnabled(enabled)
        except Exception:
            pass

    def _override_ctx(self, kind: str) -> dict:
        return getattr(self, "override_contexts", {}).get(kind, {})

    def _override_config_list(self, kind: str) -> list:
        ctx = self._override_ctx(kind)
        cfg_key = ctx.get("config_key")
        if not cfg_key:
            return []
        lst = self.config.setdefault(cfg_key, [])
        if kind == "backtest":
            try:
                self.backtest_config[cfg_key] = list(lst)
            except Exception:
                pass
        return lst

    def _refresh_symbol_interval_pairs(self, kind: str = "runtime"):
        ctx = self._override_ctx(kind)
        table = ctx.get("table")
        if table is None:
            return
        pairs_cfg = self._override_config_list(kind) or []
        table.setRowCount(0)
        seen = set()
        cleaned = []
        for entry in pairs_cfg:
            sym = str((entry or {}).get('symbol') or '').strip().upper()
            iv = str((entry or {}).get('interval') or '').strip()
            if not sym or not iv:
                continue
            key = (sym, iv)
            if key in seen:
                continue
            seen.add(key)
            cleaned.append({'symbol': sym, 'interval': iv})
            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, 0, QtWidgets.QTableWidgetItem(sym))
            table.setItem(row, 1, QtWidgets.QTableWidgetItem(iv))
        cfg_key = ctx.get("config_key")
        if cfg_key:
            self.config[cfg_key] = cleaned
            if kind == "backtest":
                try:
                    self.backtest_config[cfg_key] = list(cleaned)
                except Exception:
                    pass

    def _add_selected_symbol_interval_pairs(self, kind: str = "runtime"):
        ctx = self._override_ctx(kind)
        symbol_list = ctx.get("symbol_list")
        interval_list = ctx.get("interval_list")
        if symbol_list is None or interval_list is None:
            return
        try:
            symbols = []
            for i in range(symbol_list.count()):
                item = symbol_list.item(i)
                if item and item.isSelected():
                    symbols.append(item.text().strip().upper())
            intervals = []
            for i in range(interval_list.count()):
                item = interval_list.item(i)
                if item and item.isSelected():
                    intervals.append(item.text().strip())
            if not symbols or not intervals:
                return
            pairs_cfg = self._override_config_list(kind)
            existing = {(str(p.get('symbol') or '').strip().upper(), str(p.get('interval') or '').strip()) for p in pairs_cfg}
            changed = False
            for sym in symbols:
                if not sym:
                    continue
                for iv in intervals:
                    if not iv:
                        continue
                    key = (sym, iv)
                    if key in existing:
                        continue
                    pairs_cfg.append({'symbol': sym, 'interval': iv})
                    existing.add(key)
                    changed = True
            if changed:
                self._refresh_symbol_interval_pairs(kind)
            for widget in (symbol_list, interval_list):
                try:
                    for i in range(widget.count()):
                        item = widget.item(i)
                        if item:
                            item.setSelected(False)
                except Exception:
                    pass
        except Exception:
            pass

    def _remove_selected_symbol_interval_pairs(self, kind: str = "runtime"):
        ctx = self._override_ctx(kind)
        table = ctx.get("table")
        if table is None:
            return
        try:
            rows = sorted({idx.row() for idx in table.selectionModel().selectedRows()}, reverse=True)
            if not rows:
                return
            pairs_cfg = self._override_config_list(kind)
            updated = []
            remove_set = set()
            for row in rows:
                sym_item = table.item(row, 0)
                iv_item = table.item(row, 1)
                sym = sym_item.text().strip().upper() if sym_item else ''
                iv = iv_item.text().strip() if iv_item else ''
                if sym and iv:
                    remove_set.add((sym, iv))
            for entry in pairs_cfg:
                sym = str(entry.get('symbol') or '').strip().upper()
                iv = str(entry.get('interval') or '').strip()
                if (sym, iv) in remove_set:
                    continue
                updated.append({'symbol': sym, 'interval': iv})
            cfg_key = ctx.get("config_key")
            if cfg_key:
                self.config[cfg_key] = updated
                if kind == "backtest":
                    try:
                        self.backtest_config[cfg_key] = list(updated)
                    except Exception:
                        pass
            self._refresh_symbol_interval_pairs(kind)
        except Exception:
            pass

    def _clear_symbol_interval_pairs(self, kind: str = "runtime"):
        ctx = self._override_ctx(kind)
        cfg_key = ctx.get("config_key")
        if not cfg_key:
            return
        try:
            self.config[cfg_key] = []
            if kind == "backtest":
                try:
                    self.backtest_config[cfg_key] = []
                except Exception:
                    pass
            self._refresh_symbol_interval_pairs(kind)
        except Exception:
            pass

    def _create_override_group(self, kind: str, symbol_list, interval_list) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox("Symbol / Interval Overrides")
        layout = QtWidgets.QVBoxLayout(group)
        table = QtWidgets.QTableWidget(0, 2)
        table.setHorizontalHeaderLabels(["Symbol", "Interval"])
        table.horizontalHeader().setStretchLastSection(True)
        try:
            table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        except Exception:
            table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QtWidgets.QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        layout.addWidget(table)

        btn_layout = QtWidgets.QHBoxLayout()
        add_btn = QtWidgets.QPushButton("Add Selected")
        add_btn.clicked.connect(lambda _, k=kind: self._add_selected_symbol_interval_pairs(k))
        btn_layout.addWidget(add_btn)
        remove_btn = QtWidgets.QPushButton("Remove Selected")
        remove_btn.clicked.connect(lambda _, k=kind: self._remove_selected_symbol_interval_pairs(k))
        btn_layout.addWidget(remove_btn)
        clear_btn = QtWidgets.QPushButton("Clear All")
        clear_btn.clicked.connect(lambda _, k=kind: self._clear_symbol_interval_pairs(k))
        btn_layout.addWidget(clear_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        config_key = "runtime_symbol_interval_pairs" if kind == "runtime" else "backtest_symbol_interval_pairs"
        self.override_contexts[kind] = {
            "table": table,
            "symbol_list": symbol_list,
            "interval_list": interval_list,
            "config_key": config_key,
            "add_btn": add_btn,
            "remove_btn": remove_btn,
            "clear_btn": clear_btn,
        }
        if kind == "runtime":
            self.symbol_interval_table = table
            self.pair_add_btn = add_btn
            self.pair_remove_btn = remove_btn
            self.pair_clear_btn = clear_btn
        lock_widgets = getattr(self, '_runtime_lock_widgets', None)
        if isinstance(lock_widgets, list):
            for widget in (table, add_btn, remove_btn, clear_btn):
                if widget and widget not in lock_widgets:
                    lock_widgets.append(widget)
        self._refresh_symbol_interval_pairs(kind)
        return group

    def _on_indicator_toggled(self, key: str, checked: bool):
        try:
            indicators = self.config.setdefault('indicators', {})
            params = indicators.setdefault(key, {})
            params['enabled'] = bool(checked)
        except Exception:
            pass

    def _update_bot_status(self, active=None):
        try:
            if active is not None:
                self._bot_active = bool(active)
            text = "Bot Status: ON" if getattr(self, '_bot_active', False) else "Bot Status: OFF"
            color = "#3FB950" if self._bot_active else "#F97068"
            for label in (getattr(self, 'bot_status_label_tab1', None), getattr(self, 'bot_status_label_tab2', None)):
                if label is None:
                    continue
                label.setText(text)
                label.setStyleSheet(f"font-weight: bold; color: {color};")
        except Exception:
            pass

    def _has_active_engines(self):
        try:
            engines = getattr(self, 'strategy_engines', {}) or {}
        except Exception:
            return False
        for eng in engines.values():
            try:
                if hasattr(eng, 'is_alive'):
                    if eng.is_alive():
                        return True
                else:
                    thread = getattr(eng, '_thread', None)
                    if thread and getattr(thread, 'is_alive', lambda: False)():
                        return True
            except Exception:
                continue
        return False

    def _sync_runtime_state(self):
        active = self._has_active_engines()
        if active:
            self._set_runtime_controls_enabled(False)
        else:
            self._set_runtime_controls_enabled(True)
        try:
            btn = getattr(self, 'refresh_balance_btn', None)
            if btn is not None:
                btn.setEnabled(True)
        except Exception:
            pass
        try:
            start_btn = getattr(self, 'start_btn', None)
            stop_btn = getattr(self, 'stop_btn', None)
            if start_btn is not None:
                start_btn.setEnabled(not active)
            if stop_btn is not None:
                stop_btn.setEnabled(active)
        except Exception:
            pass
        self._update_bot_status(active)
        return active

    @staticmethod
    def _coerce_qdate(value):
        if isinstance(value, QtCore.QDate):
            return value
        if isinstance(value, datetime):
            return QtCore.QDate(value.year, value.month, value.day)
        if isinstance(value, str):
            # Try common formats
            for fmt in ("yyyy-MM-dd", "yyyy/MM/dd", "dd.MM.yyyy"):
                qd = QtCore.QDate.fromString(value, fmt)
                if qd.isValid():
                    return qd
            try:
                dt = datetime.fromisoformat(value)
                return QtCore.QDate(dt.year, dt.month, dt.day)
            except Exception:
                pass
        return QtCore.QDate.currentDate()

    def _initialize_backtest_ui_defaults(self):
        fetch_triggered = False
        try:
            source = self.backtest_config.get("symbol_source") or "Futures"
            idx = self.backtest_symbol_source_combo.findText(source)
            if idx is not None and idx >= 0 and self.backtest_symbol_source_combo.currentIndex() != idx:
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
            _set_combo(self.backtest_side_combo, side_cfg)
            margin_mode_cfg = (self.backtest_config.get("margin_mode") or "Isolated")
            _set_combo(self.backtest_margin_mode_combo, margin_mode_cfg)
            position_mode_cfg = (self.backtest_config.get("position_mode") or "Hedge")
            _set_combo(self.backtest_position_mode_combo, position_mode_cfg)
            assets_mode_cfg = (self.backtest_config.get("assets_mode") or "Single-Asset")
            _set_combo(self.backtest_assets_mode_combo, assets_mode_cfg)
            leverage_cfg = int(self.backtest_config.get("leverage", 5) or 1)
            self.backtest_leverage_spin.setValue(leverage_cfg)
            today = QtCore.QDate.currentDate()
            start_cfg = self.backtest_config.get("start_date")
            end_cfg = self.backtest_config.get("end_date")
            start_qdate = self._coerce_qdate(start_cfg) if start_cfg else today.addMonths(-3)
            end_qdate = self._coerce_qdate(end_cfg) if end_cfg else today
            if not end_qdate.isValid():
                end_qdate = today
            if not start_qdate.isValid() or start_qdate > end_qdate:
                start_qdate = end_qdate.addMonths(-3)
            self.backtest_start_edit.setDate(start_qdate)
            self.backtest_end_edit.setDate(end_qdate)
        except Exception:
            pass
        self._update_backtest_futures_controls()
        if not fetch_triggered:
            self._refresh_backtest_symbols()

    def _populate_backtest_lists(self):
        try:
            if not self.backtest_symbols_all:
                fallback_ordered: list[str] = []

                def _extend_unique(seq):
                    for sym in seq or []:
                        sym_up = str(sym).strip().upper()
                        if not sym_up:
                            continue
                        if sym_up not in fallback_ordered:
                            fallback_ordered.append(sym_up)

                _extend_unique(self.backtest_config.get("symbols"))
                _extend_unique(self.config.get("symbols"))
                try:
                    if hasattr(self, "symbol_list"):
                        for i in range(self.symbol_list.count()):
                            item = self.symbol_list.item(i)
                            if item:
                                _extend_unique([item.text()])
                except Exception:
                    pass
                if not fallback_ordered:
                    fallback_ordered.append("BTCUSDT")
                self.backtest_symbols_all = list(fallback_ordered)
            self._update_backtest_symbol_list(self.backtest_symbols_all)
        except Exception:
            pass

        interval_candidates: list[str] = []

        def _extend_interval(seq):
            for iv in seq or []:
                iv_norm = str(iv).strip()
                if not iv_norm:
                    continue
                if iv_norm not in interval_candidates:
                    interval_candidates.append(iv_norm)

        _extend_interval(self.backtest_config.get("intervals"))
        try:
            if hasattr(self, "interval_list"):
                for i in range(self.interval_list.count()):
                    item = self.interval_list.item(i)
                    if item:
                        _extend_interval([item.text()])
        except Exception:
            pass
        _extend_interval(BACKTEST_INTERVAL_ORDER)
        if not interval_candidates:
            interval_candidates.append("1h")

        ordered_intervals = [iv for iv in BACKTEST_INTERVAL_ORDER if iv in interval_candidates]
        extras = [iv for iv in interval_candidates if iv not in BACKTEST_INTERVAL_ORDER]
        full_order = ordered_intervals + extras

        selected_intervals = [iv for iv in (self.backtest_config.get("intervals") or []) if iv in full_order]
        if not selected_intervals and full_order:
            selected_intervals = [full_order[0]]
        with QtCore.QSignalBlocker(self.backtest_interval_list):
            self.backtest_interval_list.clear()
            for iv in full_order:
                item = QtWidgets.QListWidgetItem(iv)
                item.setSelected(iv in selected_intervals)
                self.backtest_interval_list.addItem(item)
        self.backtest_config["intervals"] = list(selected_intervals)
        cfg = self.config.setdefault("backtest", {})
        cfg["intervals"] = list(selected_intervals)
        self._backtest_store_intervals()

    def _set_backtest_symbol_selection(self, symbols):
        symbols_upper = {str(s).upper() for s in (symbols or []) if s}
        with QtCore.QSignalBlocker(self.backtest_symbol_list):
            for i in range(self.backtest_symbol_list.count()):
                item = self.backtest_symbol_list.item(i)
                if not item:
                    continue
                item.setSelected(item.text().upper() in symbols_upper)
        self._backtest_store_symbols()

    def _set_backtest_interval_selection(self, intervals):
        intervals_norm = {str(iv) for iv in (intervals or []) if iv}
        with QtCore.QSignalBlocker(self.backtest_interval_list):
            for i in range(self.backtest_interval_list.count()):
                item = self.backtest_interval_list.item(i)
                if not item:
                    continue
                item.setSelected(item.text() in intervals_norm)
        self._backtest_store_intervals()

    def _update_backtest_symbol_list(self, candidates):
        try:
            candidates = [str(sym).upper() for sym in (candidates or []) if sym]
            unique_candidates: list[str] = []
            seen = set()
            for sym in candidates:
                if sym and sym not in seen:
                    seen.add(sym)
                    unique_candidates.append(sym)
            selected_cfg = [str(s).upper() for s in (self.backtest_config.get("symbols") or []) if s]
            selected = [s for s in selected_cfg if s in unique_candidates]
            if not unique_candidates and selected_cfg:
                unique_candidates = []
                seen.clear()
                for sym in selected_cfg:
                    if sym and sym not in seen:
                        seen.add(sym)
                        unique_candidates.append(sym)
                selected = list(unique_candidates)
            if not selected and unique_candidates:
                selected = [unique_candidates[0]]
            with QtCore.QSignalBlocker(self.backtest_symbol_list):
                self.backtest_symbol_list.clear()
                for sym in unique_candidates:
                    item = QtWidgets.QListWidgetItem(sym)
                    item.setSelected(sym in selected)
                    self.backtest_symbol_list.addItem(item)
            self.backtest_symbols_all = list(unique_candidates)
            self.backtest_config["symbols"] = list(selected)
            cfg = self.config.setdefault("backtest", {})
            cfg["symbols"] = list(selected)
            if unique_candidates and not selected and self.backtest_symbol_list.count():
                self.backtest_symbol_list.item(0).setSelected(True)
            self._backtest_store_symbols()
        except Exception:
            pass

    def _backtest_store_symbols(self):
        try:
            symbols = []
            for i in range(self.backtest_symbol_list.count()):
                item = self.backtest_symbol_list.item(i)
                if item and item.isSelected():
                    symbols.append(item.text().upper())
            self.backtest_config["symbols"] = symbols
            cfg = self.config.setdefault("backtest", {})
            cfg["symbols"] = list(symbols)
        except Exception:
            pass

    def _backtest_store_intervals(self):
        try:
            intervals = []
            for i in range(self.backtest_interval_list.count()):
                item = self.backtest_interval_list.item(i)
                if item and item.isSelected():
                    intervals.append(item.text())
            self.backtest_config["intervals"] = intervals
            cfg = self.config.setdefault("backtest", {})
            cfg["intervals"] = list(intervals)
        except Exception:
            pass

    def _update_backtest_futures_controls(self):
        try:
            source = (self.backtest_symbol_source_combo.currentText() or "Futures").strip().lower()
            is_futures = source.startswith("fut")
        except Exception:
            is_futures = True
        for widget in getattr(self, "_backtest_futures_widgets", []):
            if widget is None:
                continue
            try:
                widget.setVisible(is_futures)
                widget.setEnabled(is_futures)
            except Exception:
                pass

    def _backtest_symbol_source_changed(self, text: str):
        self._update_backtest_config("symbol_source", text)
        self._update_backtest_futures_controls()
        self._refresh_backtest_symbols()

    def _refresh_backtest_symbols(self):
        try:
            worker = getattr(self, "_backtest_symbol_worker", None)
            if worker is not None and worker.isRunning():
                return
        except Exception:
            pass
        if not hasattr(self, "backtest_refresh_symbols_btn"):
            return
        self.backtest_refresh_symbols_btn.setEnabled(False)
        self.backtest_refresh_symbols_btn.setText("Refreshing...")
        source_text = (self.backtest_symbol_source_combo.currentText() or "Futures").strip()
        source_lower = source_text.lower()
        acct = "Spot" if source_lower.startswith("spot") else "Futures"
        api_key = self.api_key_edit.text().strip()
        api_secret = self.api_secret_edit.text().strip()
        mode = self.mode_combo.currentText()

        def _do():
            wrapper = BinanceWrapper(
                api_key,
                api_secret,
                mode=mode,
                account_type=acct,
            )
            return wrapper.fetch_symbols(sort_by_volume=True)

        worker = CallWorker(_do, parent=self)
        try:
            worker.progress.connect(self.log)
        except Exception:
            pass
        worker.done.connect(lambda res, err, src=acct: self._on_backtest_symbols_ready(res, err, src))
        self._backtest_symbol_worker = worker
        try:
            self.backtest_status_label.setText(f"Refreshing {acct.upper()} symbols...")
        except Exception:
            pass
        worker.start()

    def _on_backtest_symbols_ready(self, result, error, source_label):
        try:
            self.backtest_refresh_symbols_btn.setEnabled(True)
            self.backtest_refresh_symbols_btn.setText("Refresh")
        except Exception:
            pass
        self._backtest_symbol_worker = None
        if error or not result:
            msg = f"Backtest symbol refresh failed: {error or 'no symbols returned'}"
            self.log(msg)
            try:
                self.backtest_status_label.setText(msg)
            except Exception:
                pass
            return
        symbols = [str(sym).upper() for sym in (result or []) if sym]
        self.backtest_symbols_all = symbols
        self._update_backtest_symbol_list(symbols)
        msg = f"Loaded {len(symbols)} {source_label.upper()} symbols for backtest."
        self.log(msg)
        try:
            self.backtest_status_label.setText(msg)
        except Exception:
            pass

    def _backtest_dates_changed(self):
        try:
            start_str = self.backtest_start_edit.date().toString("yyyy-MM-dd")
            end_str = self.backtest_end_edit.date().toString("yyyy-MM-dd")
            self.backtest_config["start_date"] = start_str
            self.backtest_config["end_date"] = end_str
            cfg = self.config.setdefault("backtest", {})
            cfg["start_date"] = start_str
            cfg["end_date"] = end_str
        except Exception:
            pass

    def _update_backtest_config(self, key, value):
        try:
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
            dlg = ParamDialog(key, params, self, display_name=INDICATOR_DISPLAY_NAMES.get(key, key))
            if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
                updates = dlg.get_params()
                params.update(updates)
                cfg = self.config.setdefault("backtest", {}).setdefault("indicators", {})
                cfg[key] = copy.deepcopy(params)
        except Exception:
            pass

    def _run_backtest(self):
        if self.backtest_worker and self.backtest_worker.isRunning():
            self.backtest_status_label.setText("Backtest already running...")
            return

        ctx_backtest = self._override_ctx("backtest")
        pair_table = ctx_backtest.get("table") if ctx_backtest else None
        selected_pairs = []
        if pair_table is not None:
            try:
                rows = sorted({idx.row() for idx in pair_table.selectionModel().selectedRows()})
            except Exception:
                rows = []
            if rows:
                for row in rows:
                    sym_item = pair_table.item(row, 0)
                    iv_item = pair_table.item(row, 1)
                    sym = sym_item.text().strip().upper() if sym_item else ''
                    iv = iv_item.text().strip() if iv_item else ''
                    if sym and iv:
                        selected_pairs.append((sym, iv))
        if selected_pairs:
            pairs_override_raw = selected_pairs
        else:
            pairs_override_raw = [(str((entry or {}).get('symbol') or '').strip().upper(), str((entry or {}).get('interval') or '').strip())
                                for entry in self.config.get('backtest_symbol_interval_pairs', []) or []
                                if str((entry or {}).get('symbol') or '').strip() and str((entry or {}).get('interval') or '').strip()]
        pairs_override = []
        seen_pairs = set()
        for sym, iv in pairs_override_raw:
            key = (sym, iv)
            if key in seen_pairs:
                continue
            seen_pairs.add(key)

            pairs_override.append(key)
        symbols = [s for s in (self.backtest_config.get("symbols") or []) if s]
        intervals = [iv for iv in (self.backtest_config.get("intervals") or []) if iv]
        if pairs_override:
            symbol_order = []
            interval_order = []
            for sym, iv in pairs_override:
                if sym not in symbol_order:
                    symbol_order.append(sym)
                if iv not in interval_order:
                    interval_order.append(iv)
            if not symbol_order or not interval_order:
                self.backtest_status_label.setText("Symbol/Interval overrides list is empty.")
                return
            symbols = symbol_order
            intervals = interval_order
        if not symbols:
            self.backtest_status_label.setText("Select at least one symbol.")
            return
        if not intervals:
            self.backtest_status_label.setText("Select at least one interval.")
            return

        self.backtest_config["symbols"] = list(symbols)
        self.backtest_config["intervals"] = list(intervals)
        cfg_bt = self.config.setdefault("backtest", {})
        cfg_bt["symbols"] = list(symbols)
        cfg_bt["intervals"] = list(intervals)

        indicators_cfg = self.backtest_config.get("indicators", {}) or {}
        indicators = []
        for key, params in indicators_cfg.items():
            if not params or not params.get("enabled"):
                continue
            clean_params = copy.deepcopy(params)
            clean_params.pop("enabled", None)
            indicators.append(IndicatorDefinition(key=key, params=clean_params))
        if not indicators:
            self.backtest_status_label.setText("Enable at least one indicator to backtest.")
            return

        start_qdate = self.backtest_start_edit.date()
        end_qdate = self.backtest_end_edit.date()
        if start_qdate > end_qdate:
            self.backtest_status_label.setText("Start date must be before end date.")
            return

        start_dt = datetime(start_qdate.year(), start_qdate.month(), start_qdate.day())
        end_dt = datetime(end_qdate.year(), end_qdate.month(), end_qdate.day(), 23, 59, 59)
        if start_dt >= end_dt:
            self.backtest_status_label.setText("Backtest range must span at least one day.")
            return

        capital = float(self.backtest_capital_spin.value())
        if capital <= 0.0:
            self.backtest_status_label.setText("Margin capital must be positive.")
            return

        position_pct = float(self.backtest_pospct_spin.value())
        side_value = (self.backtest_side_combo.currentText() or "BOTH").strip()
        margin_mode = (self.backtest_margin_mode_combo.currentText() or "Isolated").strip()
        position_mode = (self.backtest_position_mode_combo.currentText() or "Hedge").strip()
        assets_mode = (self.backtest_assets_mode_combo.currentText() or "Single-Asset").strip()
        leverage_value = int(self.backtest_leverage_spin.value() or 1)

        logic = (self.backtest_logic_combo.currentText() or "AND").upper()
        self._update_backtest_config("logic", logic)
        self._update_backtest_config("capital", capital)
        self._update_backtest_config("position_pct", position_pct)
        self._update_backtest_config("side", side_value)
        self._update_backtest_config("margin_mode", margin_mode)
        self._update_backtest_config("position_mode", position_mode)
        self._update_backtest_config("assets_mode", assets_mode)
        self._update_backtest_config("leverage", leverage_value)
        self._backtest_dates_changed()

        symbol_source = (self.backtest_symbol_source_combo.currentText() or "Futures").strip()
        self._update_backtest_config("symbol_source", symbol_source)
        account_type = "Spot" if symbol_source.lower().startswith("spot") else "Futures"

        api_key = self.api_key_edit.text().strip()
        api_secret = self.api_secret_edit.text().strip()
        mode = self.mode_combo.currentText()

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
            leverage=leverage_value,
            margin_mode=margin_mode,
            position_mode=position_mode,
            assets_mode=assets_mode,
            pair_overrides=pairs_override if pairs_override else None,
        )

        signature = (mode, api_key, api_secret)
        wrapper_entry = self._backtest_wrappers.get(account_type)
        wrapper = None
        if isinstance(wrapper_entry, dict) and wrapper_entry.get("signature") == signature:
            wrapper = wrapper_entry.get("wrapper")
        if wrapper is None:
            try:
                wrapper = BinanceWrapper(
                    api_key,
                    api_secret,
                    mode=mode,
                    account_type=account_type,
                )
                self._backtest_wrappers[account_type] = {"signature": signature, "wrapper": wrapper}
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
        self.backtest_worker.start()

    def _stop_backtest(self):
        try:
            worker = getattr(self, 'backtest_worker', None)
            if worker and worker.isRunning():
                if hasattr(worker, 'request_stop'):
                    worker.request_stop()
                self.backtest_status_label.setText('Stopping backtest...')
                try:
                    self.backtest_stop_btn.setEnabled(False)
                except Exception:
                    pass
                return
            self.backtest_status_label.setText('No backtest running.')
        except Exception:
            pass

    def _on_backtest_progress(self, msg: str):
        self.backtest_status_label.setText(str(msg))

    @staticmethod
    def _normalize_backtest_run(run):
        if is_dataclass(run):
            data = asdict(run)
        elif isinstance(run, dict):
            data = dict(run)
        else:
            indicator_keys = getattr(run, "indicator_keys", [])
            if indicator_keys is None:
                indicator_keys = []
            elif not isinstance(indicator_keys, (list, tuple)):
                indicator_keys = [indicator_keys]
            data = {
                "symbol": getattr(run, "symbol", ""),
                "interval": getattr(run, "interval", ""),
                "logic": getattr(run, "logic", ""),
                "indicator_keys": list(indicator_keys),
                "trades": getattr(run, "trades", 0),
                "roi_value": getattr(run, "roi_value", 0.0),
                "roi_percent": getattr(run, "roi_percent", 0.0),
            }
        data.setdefault("indicator_keys", [])
        keys = data.get("indicator_keys") or []
        if not isinstance(keys, (list, tuple)):
            keys = [keys]
        data["indicator_keys"] = [str(k) for k in keys if k is not None]
        try:
            data["trades"] = int(data.get("trades", 0) or 0)
        except Exception:
            data["trades"] = 0
        for key in ("roi_value", "roi_percent"):
            try:
                data[key] = float(data.get(key, 0.0) or 0.0)
            except Exception:
                data[key] = 0.0
        data["symbol"] = str(data.get("symbol") or "")
        data["interval"] = str(data.get("interval") or "")
        data["logic"] = str(data.get("logic") or "")
        return data

    def _on_backtest_finished(self, result: dict, error: object):
        self.backtest_run_btn.setEnabled(True)
        try:
            self.backtest_stop_btn.setEnabled(False)
        except Exception:
            pass
        worker = getattr(self, "backtest_worker", None)
        if worker and worker.isRunning():
            worker.wait(100)
        self.backtest_worker = None
        if error:
            err_text = str(error) if error is not None else ''
            if isinstance(error, RuntimeError) and 'backtest_cancelled' in err_text.lower():
                self.backtest_status_label.setText('Backtest cancelled.')
                return
            msg = f"Backtest failed: {error}"
            self.backtest_status_label.setText(msg)
            self.log(msg)
            return
        runs_raw = result.get("runs", []) if isinstance(result, dict) else []
        errors = result.get("errors", []) if isinstance(result, dict) else []
        run_dicts = [self._normalize_backtest_run(r) for r in (runs_raw or [])]
        self.backtest_results = run_dicts
        self._populate_backtest_results_table(run_dicts)
        summary_parts = []
        if run_dicts:
            summary_parts.append(f"{len(run_dicts)} run(s) completed")
            total_roi = sum(r.get("roi_value", 0.0) for r in run_dicts)
            summary_parts.append(f"Total ROI: {total_roi:+.2f} USDT")
            avg_roi_pct = sum(r.get("roi_percent", 0.0) for r in run_dicts) / max(len(run_dicts), 1)
            summary_parts.append(f"Avg ROI %: {avg_roi_pct:+.2f}%")
        if errors:
            summary_parts.append(f"{len(errors)} error(s)")
            for err in errors:
                sym = err.get("symbol")
                interval = err.get("interval")
                self.log(f"Backtest error for {sym}@{interval}: {err.get('error')}")
        if not summary_parts:
            summary_parts.append("No results generated.")
        self.backtest_status_label.setText(" | ".join(summary_parts))

    def _populate_backtest_results_table(self, runs):
        try:
            self.backtest_results_table.setRowCount(0)
            if self.backtest_results_table.isSortingEnabled():
                try:
                    self.backtest_results_table.setSortingEnabled(False)
                except Exception:
                    pass
            for run in runs or []:
                data = run if isinstance(run, dict) else self._normalize_backtest_run(run)
                symbol = data.get("symbol") or "-"
                interval = data.get("interval") or "-"
                logic = data.get("logic") or "-"
                indicator_keys = data.get("indicator_keys") or []
                trades = data.get("trades", 0)
                roi_value = data.get("roi_value", 0.0)
                roi_percent = data.get("roi_percent", 0.0)

                indicators_display = ", ".join(INDICATOR_DISPLAY_NAMES.get(k, k) for k in indicator_keys)
                row = self.backtest_results_table.rowCount()
                self.backtest_results_table.insertRow(row)
                self.backtest_results_table.setItem(row, 0, QtWidgets.QTableWidgetItem(symbol or "-"))
                self.backtest_results_table.setItem(row, 1, QtWidgets.QTableWidgetItem(interval or "-"))
                self.backtest_results_table.setItem(row, 2, QtWidgets.QTableWidgetItem(logic or "-"))
                self.backtest_results_table.setItem(row, 3, QtWidgets.QTableWidgetItem(indicators_display or "-"))
                self.backtest_results_table.setItem(row, 4, QtWidgets.QTableWidgetItem(str(trades or 0)))
                roi_value_item = QtWidgets.QTableWidgetItem(f"{roi_value:+.2f}")
                roi_value_item.setData(QtCore.Qt.ItemDataRole.UserRole, float(roi_value))
                self.backtest_results_table.setItem(row, 5, roi_value_item)
                roi_percent_item = QtWidgets.QTableWidgetItem(f"{roi_percent:+.2f}%")
                roi_percent_item.setData(QtCore.Qt.ItemDataRole.UserRole, float(roi_percent))
                self.backtest_results_table.setItem(row, 6, roi_percent_item)
        except Exception as exc:
            self.log(f"Backtest results table error: {exc}")
        finally:
            try:
                self.backtest_results_table.setSortingEnabled(True)
            except Exception:
                pass

    def init_ui(self):
        self.setWindowTitle("Binance Trading Bot")
        try:
            self.setWindowIcon(QtGui.QIcon(str(Path(__file__).resolve().parent.parent / "assets" / "binance_icon.ico")))
        except Exception:
            pass
        root_layout = QtWidgets.QVBoxLayout(self)
        self.tabs = QtWidgets.QTabWidget()
        root_layout.addWidget(self.tabs)

        # ---------------- Dashboard tab ----------------
        tab1 = QtWidgets.QWidget()
        tab1_layout = QtWidgets.QVBoxLayout(tab1)

        # Top grid
        grid = QtWidgets.QGridLayout()

        grid.addWidget(QtWidgets.QLabel("API Key:"), 0, 0)
        self.api_key_edit = QtWidgets.QLineEdit(self.config['api_key'])
        grid.addWidget(self.api_key_edit, 0, 1)

        grid.addWidget(QtWidgets.QLabel("API Secret:"), 1, 0)
        self.api_secret_edit = QtWidgets.QLineEdit(self.config['api_secret'])
        self.api_secret_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        grid.addWidget(self.api_secret_edit, 1, 1)
        self.api_key_edit.editingFinished.connect(self._reconfigure_positions_worker)
        self.api_secret_edit.editingFinished.connect(self._reconfigure_positions_worker)

        grid.addWidget(QtWidgets.QLabel("Mode:"), 0, 2)
        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItems(["Live", "Demo/Testnet"])
        self.mode_combo.setCurrentText(self.config.get('mode', 'Live'))
        grid.addWidget(self.mode_combo, 0, 3)
        self.mode_combo.currentTextChanged.connect(lambda _=None: self._reconfigure_positions_worker())

        grid.addWidget(QtWidgets.QLabel("Theme:"), 0, 4)
        self.theme_combo = QtWidgets.QComboBox()
        self.theme_combo.addItems(["Light", "Dark"])
        current_theme = self.config.get("theme") or "Dark"
        if current_theme not in ("Light", "Dark"):
            current_theme = "Dark"
        self.theme_combo.setCurrentText(current_theme)
        self.theme_combo.currentTextChanged.connect(self.apply_theme)
        grid.addWidget(self.theme_combo, 0, 5)

        self.bot_status_label_tab1 = QtWidgets.QLabel()
        self.bot_status_label_tab1.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(self.bot_status_label_tab1, 0, 6, 1, 4)

        grid.addWidget(QtWidgets.QLabel("Account Type:"), 1, 2)
        self.account_combo = QtWidgets.QComboBox()
        self.account_combo.addItems(["Spot", "Futures"])
        self.account_combo.setCurrentText(self.config.get('account_type', 'Futures'))
        grid.addWidget(self.account_combo, 1, 3)
        self.account_combo.currentTextChanged.connect(lambda _=None: self._reconfigure_positions_worker())

        grid.addWidget(QtWidgets.QLabel("Total USDT balance:"), 2, 0)
        self.balance_label = QtWidgets.QLabel("N/A")
        grid.addWidget(self.balance_label, 2, 1)
        self.pos_mode_label = QtWidgets.QLabel("Position Mode: N/A")
        grid.addWidget(self.pos_mode_label, 2, 6, 1, 2)
        self.refresh_balance_btn = QtWidgets.QPushButton("Refresh Balance")
        self.refresh_balance_btn.clicked.connect(lambda: _mw_update_balance_label(self))
        grid.addWidget(self.refresh_balance_btn, 2, 2)

        grid.addWidget(QtWidgets.QLabel("Leverage (Futures):"), 2, 3)
        self.leverage_spin = QtWidgets.QSpinBox()
        self.leverage_spin.setRange(1, 125)
        self.leverage_spin.setValue(self.config.get('leverage', 5))
        self.leverage_spin.valueChanged.connect(self.on_leverage_changed)
        grid.addWidget(self.leverage_spin, 2, 4)

        grid.addWidget(QtWidgets.QLabel("Margin Mode (Futures):"), 2, 5)
        self.margin_mode_combo = QtWidgets.QComboBox()
        self.margin_mode_combo.addItems(["Cross", "Isolated"])
        self.margin_mode_combo.setCurrentText(self.config.get('margin_mode', 'Isolated'))
        grid.addWidget(self.margin_mode_combo, 2, 6)

        grid.addWidget(QtWidgets.QLabel("Position Mode:"), 2, 7)
        self.position_mode_combo = QtWidgets.QComboBox()
        self.position_mode_combo.addItems(["One-way", "Hedge"])
        self.position_mode_combo.setCurrentText(self.config.get("position_mode", "Hedge"))
        grid.addWidget(self.position_mode_combo, 2, 8)

        grid.addWidget(QtWidgets.QLabel("Assets Mode:"), 2, 9)
        self.assets_mode_combo = QtWidgets.QComboBox()
        self.assets_mode_combo.addItems(["Single-Asset", "Multi-Assets"])
        self.assets_mode_combo.setCurrentText(self.config.get("assets_mode", "Single-Asset"))
        grid.addWidget(self.assets_mode_combo, 2, 10)

        grid.addWidget(QtWidgets.QLabel("Time-in-Force:"), 3, 2)
        self.tif_combo = QtWidgets.QComboBox()
        self.tif_combo.addItems(["GTC", "IOC", "FOK", "GTD"])
        self.tif_combo.setCurrentText(self.config.get("tif", "GTC"))
        grid.addWidget(self.tif_combo, 3, 3)
        self.gtd_minutes_spin = QtWidgets.QSpinBox()
        self.gtd_minutes_spin.setRange(1, 1440)
        self.gtd_minutes_spin.setValue(self.config.get("gtd_minutes", 30))
        self.gtd_minutes_spin.setSuffix(" min (GTD)")
        grid.addWidget(self.gtd_minutes_spin, 3, 4)
        # Show GTD minutes only when TIF == 'GTD'
        def _update_gtd_visibility(text:str):
            is_gtd = (text == 'GTD')
            self.gtd_minutes_spin.setVisible(is_gtd)
            self.gtd_minutes_spin.setEnabled(is_gtd)
        self.tif_combo.currentTextChanged.connect(_update_gtd_visibility)
        _update_gtd_visibility(self.tif_combo.currentText())

        grid.addWidget(QtWidgets.QLabel("Indicator Source:"), 3, 0)
        self.ind_source_combo = QtWidgets.QComboBox()
        self.ind_source_combo.addItems(["Binance spot","Binance futures","TradingView","Bybit"])
        self.ind_source_combo.setCurrentText(self.config.get("indicator_source", "Binance futures"))
        grid.addWidget(self.ind_source_combo, 3, 1, 1, 2)

        tab1_layout.addLayout(grid)

        # Markets & Intervals
        sym_group = QtWidgets.QGroupBox("Markets & Intervals")
        sgrid = QtWidgets.QGridLayout(sym_group)

        sgrid.addWidget(QtWidgets.QLabel("Symbols (select 1 or more):"), 0, 0)
        self.symbol_list = QtWidgets.QListWidget()
        self.symbol_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        self.symbol_list.itemSelectionChanged.connect(self._reconfigure_positions_worker)
        sgrid.addWidget(self.symbol_list, 1, 0, 4, 2)

        self.refresh_symbols_btn = QtWidgets.QPushButton("Refresh Symbols")
        self.refresh_symbols_btn.clicked.connect(self.refresh_symbols)
        sgrid.addWidget(self.refresh_symbols_btn, 5, 0, 1, 2)

        sgrid.addWidget(QtWidgets.QLabel("Intervals (select 1 or more):"), 0, 2)
        self.interval_list = QtWidgets.QListWidget()
        self.interval_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        for it in ["1m","3m","5m","15m","30m","1h","2h","4h","6h","8h","12h","1d","3d","1w"]:
            self.interval_list.addItem(QtWidgets.QListWidgetItem(it))
        sgrid.addWidget(self.interval_list, 1, 2, 3, 2)

        self.custom_interval_edit = QtWidgets.QLineEdit()
        self.custom_interval_edit.setPlaceholderText("e.g., 45s or 7m or 90m, comma-separated")
        self.add_interval_btn = QtWidgets.QPushButton("Add Custom Interval(s)")
        def _add_custom_intervals():
            txt = self.custom_interval_edit.text().strip()
            if not txt:
                return
            parts = [p.strip() for p in txt.split(",") if p.strip()]
            existing = set(self.interval_list.item(i).text() for i in range(self.interval_list.count()))
            source = (self.ind_source_combo.currentText() or '').strip().lower() if hasattr(self, 'ind_source_combo') else ''
            is_binance_source = 'binance' in source
            for p in parts:
                norm = p.strip()
                key = norm.lower()
                if is_binance_source and key not in BINANCE_SUPPORTED_INTERVALS:
                    self.log(f"Skipping unsupported Binance interval '{norm}'.")
                    continue
                if norm not in existing:
                    self.interval_list.addItem(QtWidgets.QListWidgetItem(norm))
                    existing.add(norm)
            self.custom_interval_edit.clear()
        self.add_interval_btn.clicked.connect(_add_custom_intervals)
        sgrid.addWidget(self.custom_interval_edit, 4, 2)
        sgrid.addWidget(self.add_interval_btn, 4, 3)

        tab1_layout.addWidget(sym_group)

        runtime_override_group = self._create_override_group("runtime", self.symbol_list, self.interval_list)
        tab1_layout.addWidget(runtime_override_group)

        # Strategy Controls
        strat_group = QtWidgets.QGroupBox("Strategy Controls")
        g = QtWidgets.QGridLayout(strat_group)

        g.addWidget(QtWidgets.QLabel("Side:"), 0, 0)
        self.side_combo = QtWidgets.QComboBox()
        self.side_combo.addItems(["BUY","SELL","BOTH"])
        self.side_combo.setCurrentText(self.config.get("side", "BOTH"))
        g.addWidget(self.side_combo, 0, 1)

        g.addWidget(QtWidgets.QLabel("Position % of Balance:"), 0, 2)
        self.pospct_spin = QtWidgets.QDoubleSpinBox()
        self.pospct_spin.setRange(0.01, 100.0)
        self.pospct_spin.setDecimals(2)
        # Show as percentage 0..100; config can be 0..1 or 0..100
        initial_pct = float(self.config.get("position_pct", 2.0))
        if initial_pct <= 1.0:
            initial_pct *= 100.0
        self.pospct_spin.setValue(initial_pct)
        g.addWidget(self.pospct_spin, 0, 3)

        g.addWidget(QtWidgets.QLabel("Loop Interval Override:"), 0, 4)
        self.loop_edit = QtWidgets.QLineEdit()
        self.loop_edit.setPlaceholderText("Leave empty to use candle interval; e.g., 30s")
        g.addWidget(self.loop_edit, 0, 5)

        # Add-only (One-way guard) option
        self.cb_add_only = QtWidgets.QCheckBox("Add-only in current net direction (one-way)")
        self.cb_add_only.setChecked(bool(self.config.get('add_only', False)))
        g.addWidget(self.cb_add_only, 1, 0, 1, 6)

        self.cb_close_on_exit = QtWidgets.QCheckBox("Market Close All On Window Close")
        self.cb_close_on_exit.setChecked(bool(self.config.get('close_on_exit', False)))
        self.cb_close_on_exit.stateChanged.connect(lambda state: self.config.__setitem__('close_on_exit', bool(state)))
        g.addWidget(self.cb_close_on_exit, 2, 0, 1, 6)

        tab1_layout.addWidget(strat_group)

        # Indicators
        ind_group = QtWidgets.QGroupBox("Indicators")
        il = QtWidgets.QGridLayout(ind_group)

        self._indicator_runtime_controls = []
        row = 0
        for key, params in self.config['indicators'].items():
            label = INDICATOR_DISPLAY_NAMES.get(key, key)
            cb = QtWidgets.QCheckBox(label)
            cb.setProperty('indicator_key', key)
            cb.setChecked(bool(params.get("enabled", False)))
            def make_toggle_handler(_key=key):
                def _toggle(checked):
                    self._on_indicator_toggled(_key, checked)
                return _toggle
            cb.toggled.connect(make_toggle_handler())
            btn = QtWidgets.QPushButton("Params...")
            def make_handler(_key=key, _params=params):
                def handler():
                    dlg = ParamDialog(_key, _params, self, display_name=INDICATOR_DISPLAY_NAMES.get(_key, _key))
                    if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
                        self.config['indicators'][_key].update(dlg.get_params())
                        self.indicator_widgets[_key][0].setChecked(bool(self.config['indicators'][_key].get("enabled", False)))
                return handler
            btn.clicked.connect(make_handler())
            il.addWidget(cb, row, 0)
            il.addWidget(btn, row, 1)
            self.indicator_widgets[key] = (cb, btn)
            self._indicator_runtime_controls.extend([cb, btn])
            row += 1

        tab1_layout.addWidget(ind_group)

        # Buttons
        btn_layout = QtWidgets.QHBoxLayout()
        self.start_btn = QtWidgets.QPushButton("Start")
        self.start_btn.clicked.connect(self.start_strategy)
        btn_layout.addWidget(self.start_btn)
        self.stop_btn = QtWidgets.QPushButton("Stop")
        self.stop_btn.clicked.connect(lambda checked=False: self.stop_strategy_async(close_positions=True))
        self.stop_btn.setEnabled(False)
        btn_layout.addWidget(self.stop_btn)
        self.save_btn = QtWidgets.QPushButton("Save Config")
        self.save_btn.clicked.connect(self.save_config)
        btn_layout.addWidget(self.save_btn)
        self.load_btn = QtWidgets.QPushButton("Load Config")
        self.load_btn.clicked.connect(self.load_config)
        btn_layout.addWidget(self.load_btn)
        tab1_layout.addLayout(btn_layout)

        self._runtime_lock_widgets = [
            self.api_key_edit,
            self.api_secret_edit,
            self.mode_combo,
            self.theme_combo,
            self.account_combo,
            self.leverage_spin,
            self.margin_mode_combo,
            self.position_mode_combo,
            self.assets_mode_combo,
            self.tif_combo,
            self.gtd_minutes_spin,
            self.ind_source_combo,
            self.symbol_list,
            self.refresh_symbols_btn,
            self.interval_list,
            self.custom_interval_edit,
            self.add_interval_btn,
            self.side_combo,
            self.pospct_spin,
            self.loop_edit,
            self.cb_add_only,
            self.cb_close_on_exit,
            self.start_btn,
            self.save_btn,
            self.load_btn
        ] + list(self._indicator_runtime_controls)
        self._set_runtime_controls_enabled(True)


        # Log
        self.log_edit = QtWidgets.QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        try:
            self.log_edit.document().setMaximumBlockCount(1000)
        except Exception:
            pass
        tab1_layout.addWidget(self.log_edit)

        self.tabs.addTab(tab1, "Dashboard")

        # Map symbol -> {'L': set(), 'S': set()} for intervals shown in Positions tab
        self._entry_intervals = {}
        self._entry_times = {}  # (sym, 'L'/'S') -> last trade time string
        self._entry_times_by_iv = {}
        self._open_position_records = {}
        self._closed_position_records = []


        # ---------------- Positions tab ----------------
        tab2 = QtWidgets.QWidget()
        tab2_layout = QtWidgets.QVBoxLayout(tab2)

        ctrl_layout = QtWidgets.QHBoxLayout()
        self.refresh_pos_btn = QtWidgets.QPushButton("Refresh Positions")
        self.refresh_pos_btn.clicked.connect(self.refresh_positions)
        ctrl_layout.addWidget(self.refresh_pos_btn)
        self.close_all_btn = QtWidgets.QPushButton("Market Close ALL Positions")
        self.close_all_btn.clicked.connect(self.close_all_positions_async)
        ctrl_layout.addWidget(self.close_all_btn)
        ctrl_layout.addStretch()
        self.bot_status_label_tab2 = QtWidgets.QLabel()
        self.bot_status_label_tab2.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        ctrl_layout.addWidget(self.bot_status_label_tab2)
        tab2_layout.addLayout(ctrl_layout)
        self._sync_runtime_state()

        self.pos_table = QtWidgets.QTableWidget(0, 13, tab2)
        self.pos_table.setHorizontalHeaderLabels(["Symbol","Balance/Position","Last Price (USDT)","Size (USDT)","Margin Ratio","Margin (USDT)","PNL (ROI%)","Entry TF","Side","Open Time","Close Time","Status","Close"])
        self.pos_table.horizontalHeader().setStretchLastSection(True)
        self.pos_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        try:
            self.pos_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        except Exception:
            self.pos_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        tab2_layout.addWidget(self.pos_table)

        self.tabs.addTab(tab2, "Positions")

        # Background positions worker (keeps UI thread snappy)
        self._pos_thread = QtCore.QThread(self)
        self._pos_worker = _PositionsWorker(
            self.api_key_edit.text().strip(),
            self.api_secret_edit.text().strip(),
            self.mode_combo.currentText(),
            self.account_combo.currentText(),
        )
        # Wire thread-safe control signals
        self.req_pos_start.connect(self._pos_worker.start_with_interval)
        self.req_pos_stop.connect(self._pos_worker.stop_timer)
        self.req_pos_set_interval.connect(self._pos_worker.set_interval)
        self._pos_worker.moveToThread(self._pos_thread)
        self._pos_worker.positions_ready.connect(self._on_positions_ready)
        self._pos_worker.error.connect(lambda e: self.log(f"Positions worker: {e}"))
        try:
            self._reconfigure_positions_worker()
        except Exception:
            pass
        
        self._pos_thread.start()
        # adjust worker refresh interval
        try:
            self._apply_positions_refresh_settings()
        except Exception:
            pass

        # ---------------- Backtest tab ----------------
        tab3 = QtWidgets.QWidget()
        tab3_layout = QtWidgets.QVBoxLayout(tab3)

        top_layout = QtWidgets.QHBoxLayout()

        market_group = QtWidgets.QGroupBox("Markets")
        market_layout = QtWidgets.QGridLayout(market_group)

        market_layout.addWidget(QtWidgets.QLabel("Symbol Source:"), 0, 0)
        self.backtest_symbol_source_combo = QtWidgets.QComboBox()
        self.backtest_symbol_source_combo.addItems(["Futures", "Spot"])
        self.backtest_symbol_source_combo.currentTextChanged.connect(self._backtest_symbol_source_changed)
        market_layout.addWidget(self.backtest_symbol_source_combo, 0, 1)
        self.backtest_refresh_symbols_btn = QtWidgets.QPushButton("Refresh")
        self.backtest_refresh_symbols_btn.clicked.connect(self._refresh_backtest_symbols)
        market_layout.addWidget(self.backtest_refresh_symbols_btn, 0, 2)

        market_layout.addWidget(QtWidgets.QLabel("Symbols (select 1 or more):"), 1, 0, 1, 3)
        self.backtest_symbol_list = QtWidgets.QListWidget()
        self.backtest_symbol_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        self.backtest_symbol_list.itemSelectionChanged.connect(self._backtest_store_symbols)
        market_layout.addWidget(self.backtest_symbol_list, 2, 0, 4, 3)

        market_layout.addWidget(QtWidgets.QLabel("Intervals (select 1 or more):"), 1, 3)
        self.backtest_interval_list = QtWidgets.QListWidget()
        self.backtest_interval_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        self.backtest_interval_list.itemSelectionChanged.connect(self._backtest_store_intervals)
        market_layout.addWidget(self.backtest_interval_list, 2, 3, 4, 2)
        pair_group = self._create_override_group("backtest", self.backtest_symbol_list, self.backtest_interval_list)
        market_layout.addWidget(pair_group, 6, 0, 1, 5)


        market_layout.setColumnStretch(0, 2)
        market_layout.setColumnStretch(1, 1)
        market_layout.setColumnStretch(2, 1)
        market_layout.setColumnStretch(3, 1)
        market_layout.setColumnStretch(4, 1)

        top_layout.addWidget(market_group)

        param_group = QtWidgets.QGroupBox("Backtest Parameters")
        param_form = QtWidgets.QFormLayout(param_group)

        self.backtest_start_edit = QtWidgets.QDateEdit(calendarPopup=True)
        self.backtest_start_edit.setDisplayFormat("yyyy-MM-dd")
        self.backtest_end_edit = QtWidgets.QDateEdit(calendarPopup=True)
        self.backtest_end_edit.setDisplayFormat("yyyy-MM-dd")
        self.backtest_start_edit.dateChanged.connect(self._backtest_dates_changed)
        self.backtest_end_edit.dateChanged.connect(self._backtest_dates_changed)

        param_form.addRow("Start Date:", self.backtest_start_edit)
        param_form.addRow("End Date:", self.backtest_end_edit)

        self.backtest_logic_combo = QtWidgets.QComboBox()
        self.backtest_logic_combo.addItems(["AND", "OR", "SEPARATE"])
        self.backtest_logic_combo.currentTextChanged.connect(lambda v: self._update_backtest_config("logic", v))
        param_form.addRow("Signal Logic:", self.backtest_logic_combo)

        self.backtest_capital_spin = QtWidgets.QDoubleSpinBox()
        self.backtest_capital_spin.setDecimals(2)
        self.backtest_capital_spin.setRange(1.0, 1_000_000_000.0)
        self.backtest_capital_spin.setSuffix(" USDT")
        self.backtest_capital_spin.valueChanged.connect(lambda v: self._update_backtest_config("capital", float(v)))
        param_form.addRow("Margin Capital:", self.backtest_capital_spin)

        self.backtest_pospct_spin = QtWidgets.QDoubleSpinBox()
        self.backtest_pospct_spin.setDecimals(2)
        self.backtest_pospct_spin.setRange(0.01, 100.0)
        self.backtest_pospct_spin.setSuffix(" %")
        self.backtest_pospct_spin.valueChanged.connect(lambda v: self._update_backtest_config("position_pct", float(v)))
        param_form.addRow("Position % of Balance:", self.backtest_pospct_spin)

        self.backtest_side_combo = QtWidgets.QComboBox()
        self.backtest_side_combo.addItems(["BUY", "SELL", "BOTH"])
        self.backtest_side_combo.currentTextChanged.connect(lambda v: self._update_backtest_config("side", v))
        param_form.addRow("Side:", self.backtest_side_combo)

        self.backtest_margin_mode_combo = QtWidgets.QComboBox()
        self.backtest_margin_mode_combo.addItems(["Isolated", "Cross"])
        self.backtest_margin_mode_combo.currentTextChanged.connect(lambda v: self._update_backtest_config("margin_mode", v))
        param_form.addRow("Margin Mode (Futures):", self.backtest_margin_mode_combo)

        self.backtest_position_mode_combo = QtWidgets.QComboBox()
        self.backtest_position_mode_combo.addItems(["Hedge", "One-way"])
        self.backtest_position_mode_combo.currentTextChanged.connect(lambda v: self._update_backtest_config("position_mode", v))
        param_form.addRow("Position Mode:", self.backtest_position_mode_combo)

        self.backtest_assets_mode_combo = QtWidgets.QComboBox()
        self.backtest_assets_mode_combo.addItems(["Single-Asset", "Multi-Assets"])
        self.backtest_assets_mode_combo.currentTextChanged.connect(lambda v: self._update_backtest_config("assets_mode", v))
        param_form.addRow("Assets Mode:", self.backtest_assets_mode_combo)

        self.backtest_leverage_spin = QtWidgets.QSpinBox()
        self.backtest_leverage_spin.setRange(1, 125)
        self.backtest_leverage_spin.valueChanged.connect(lambda v: self._update_backtest_config("leverage", int(v)))
        param_form.addRow("Leverage (Futures):", self.backtest_leverage_spin)

        self._backtest_futures_widgets = [
            self.backtest_margin_mode_combo,
            param_form.labelForField(self.backtest_margin_mode_combo),
            self.backtest_position_mode_combo,
            param_form.labelForField(self.backtest_position_mode_combo),
            self.backtest_assets_mode_combo,
            param_form.labelForField(self.backtest_assets_mode_combo),
            self.backtest_leverage_spin,
            param_form.labelForField(self.backtest_leverage_spin),
        ]

        top_layout.addWidget(param_group)

        indicator_group = QtWidgets.QGroupBox("Indicators")
        ind_layout = QtWidgets.QGridLayout(indicator_group)
        self.backtest_indicator_widgets.clear()
        row = 0
        for key, params in self.backtest_config.get("indicators", {}).items():
            label = INDICATOR_DISPLAY_NAMES.get(key, key)
            cb = QtWidgets.QCheckBox(label)
            cb.setProperty("indicator_key", key)
            cb.setChecked(bool(params.get("enabled", False)))
            cb.toggled.connect(lambda checked, _key=key: self._backtest_toggle_indicator(_key, checked))
            btn = QtWidgets.QPushButton("Params...")
            btn.clicked.connect(lambda _=False, _key=key: self._open_backtest_params(_key))
            ind_layout.addWidget(cb, row, 0)
            ind_layout.addWidget(btn, row, 1)
            self.backtest_indicator_widgets[key] = (cb, btn)
            row += 1
        top_layout.addWidget(indicator_group, stretch=1)

        tab3_layout.addLayout(top_layout)

        controls_layout = QtWidgets.QHBoxLayout()
        self.backtest_run_btn = QtWidgets.QPushButton("Run Backtest")
        self.backtest_run_btn.clicked.connect(self._run_backtest)
        controls_layout.addWidget(self.backtest_run_btn)
        self.backtest_stop_btn = QtWidgets.QPushButton("Stop")
        self.backtest_stop_btn.setEnabled(False)
        self.backtest_stop_btn.clicked.connect(self._stop_backtest)
        controls_layout.addWidget(self.backtest_stop_btn)
        self.backtest_status_label = QtWidgets.QLabel()
        controls_layout.addWidget(self.backtest_status_label)
        controls_layout.addStretch()
        tab3_layout.addLayout(controls_layout)
        try:
            for widget in (self.backtest_run_btn, self.backtest_stop_btn):
                if widget and widget not in self._runtime_lock_widgets:
                    self._runtime_lock_widgets.append(widget)
        except Exception:
            pass

        self.backtest_results_table = QtWidgets.QTableWidget(0, 7)
        self.backtest_results_table.setHorizontalHeaderLabels(["Symbol", "Interval", "Logic", "Indicators", "Trades", "ROI (USDT)", "ROI (%)"])
        self.backtest_results_table.horizontalHeader().setStretchLastSection(True)
        self.backtest_results_table.setSortingEnabled(True)
        try:
            self.backtest_results_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        except Exception:
            self.backtest_results_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        tab3_layout.addWidget(self.backtest_results_table)

        self.tabs.addTab(tab3, "Backtest")
        self._refresh_symbol_interval_pairs("runtime")
        self._refresh_symbol_interval_pairs("backtest")
        self._initialize_backtest_ui_defaults()


        

        self.resize(1200, 900)
        self.apply_theme(self.theme_combo.currentText())
        self._setup_log_buffer()
        try:
            self.ind_source_combo.currentTextChanged.connect(lambda v: self.config.__setitem__("indicator_source", v))
        except Exception:
            pass

    
    

def _gui_on_positions_ready(self, rows: list, acct: str):
    try:
        try:
            rows = sorted(rows, key=lambda r: (str(r.get('symbol') or ''), str(r.get('side_key') or '')))
        except Exception:
            rows = rows or []

        positions_map: dict[tuple, dict] = {}
        base_rows = rows or []
        for r in base_rows:
            try:
                sym = r.get('symbol')
                side_key = r.get('side_key') or 'SPOT'
                if not sym:
                    continue
                positions_map[(sym, side_key)] = {
                    'symbol': sym,
                    'side_key': side_key,
                    'entry_tf': r.get('entry_tf'),
                    'open_time': r.get('open_time'),
                    'close_time': '-',
                    'status': 'Active',
                    'data': dict(r),
                }
            except Exception:
                continue

        acct_upper = str(acct or '').upper()
        if acct_upper.startswith('FUT'):
            try:
                worker = getattr(self, '_pos_worker', None)
                bw = getattr(worker, '_wrapper', None) if worker else None
                if worker and bw is None:
                    try:
                        worker._ensure_wrapper()
                        bw = getattr(worker, '_wrapper', None)
                    except Exception:
                        bw = None
                if bw is None:
                    bw = getattr(self, 'shared_binance', None)
                if bw is None:
                    bw = BinanceWrapper(
                        self.api_key_edit.text().strip(),
                        self.api_secret_edit.text().strip(),
                        mode=self.mode_combo.currentText(),
                        account_type=self.account_combo.currentText(),
                    )
                raw = bw.list_open_futures_positions() or []
                syms_filter = None
                try:
                    selected = [self.symbol_list.item(i).text() for i in range(self.symbol_list.count()) if self.symbol_list.item(i).isSelected()]
                    if selected:
                        syms_filter = set(selected)
                except Exception:
                    syms_filter = None
                for p in raw:
                    try:
                        sym = str(p.get('symbol'))
                        if syms_filter and sym not in syms_filter:
                            continue
                        amt = float(p.get('positionAmt') or 0.0)
                        if abs(amt) <= 0.0:
                            continue
                        mark = float(p.get('markPrice') or 0.0)
                        value = abs(amt) * mark if mark else 0.0
                        side_key = 'L' if amt > 0 else 'S'
                        margin_usdt = float(p.get('isolatedWallet') or p.get('initialMargin') or 0.0)
                        pnl = float(p.get('unRealizedProfit') or 0.0)
                        margin_ratio = normalize_margin_ratio(p.get('marginRatio') or p.get('margin_ratio'))
                        if margin_ratio <= 0.0 and margin_usdt > 0:
                            try:
                                maint = float(p.get('maintMargin') or p.get('maintenanceMargin') or 0.0)
                            except Exception:
                                maint = 0.0
                            unrealized_loss = abs(pnl) if pnl < 0 else 0.0
                            margin_balance = margin_usdt + (pnl if pnl > 0 else 0.0)
                            denom = margin_balance if margin_balance > 0.0 else margin_usdt
                            if denom > 0.0:
                                margin_ratio = ((maint + unrealized_loss) / denom) * 100.0
                        if margin_usdt > 0:
                            pnl_roi = f"{pnl:+.2f} USDT ({(pnl / margin_usdt * 100.0):+.2f}%)"
                        else:
                            pnl_roi = f"{pnl:+.2f} USDT"
                        try:
                            update_time = int(float(p.get('updateTime') or p.get('update_time') or 0))
                        except Exception:
                            update_time = 0
                        data = {
                            'symbol': sym,
                            'qty': abs(amt),
                            'mark': mark,
                            'size_usdt': value,
                            'margin_usdt': margin_usdt,
                            'margin_ratio': margin_ratio,
                            'pnl_roi': pnl_roi,
                            'side_key': side_key,
                            'update_time': update_time,
                        }
                        rec = positions_map.get((sym, side_key))
                        if rec is None:
                            rec = {
                                'symbol': sym,
                                'side_key': side_key,
                                'entry_tf': '-',
                                'open_time': '-',
                                'close_time': '-',
                                'status': 'Active',
                            }
                        else:
                            rec = dict(rec)
                        rec['data'] = data
                        rec['status'] = 'Active'
                        rec['close_time'] = '-'
                        entry_times_map = getattr(self, '_entry_times_by_iv', {}) or {}
                        intervals = set()
                        try:
                            for (sym_key, side_key_key, iv_key), ts in entry_times_map.items():
                                if sym_key == sym and side_key_key == side_key and ts and iv_key:
                                    iv_norm = str(iv_key).strip().lower()
                                    if iv_norm:
                                        intervals.add(iv_norm)
                        except Exception:
                            pass
                        if not intervals:
                            intervals = {str(iv).strip().lower() for iv in (self._entry_intervals.get(sym, {}) or {}).get(side_key, set()) if str(iv).strip()}
                        if intervals:
                            rec['entry_tf'] = ', '.join(sorted(intervals, key=_mw_interval_sort_key))
                        else:
                            rec['entry_tf'] = '-'
                        open_times = []
                        for iv in intervals:
                            ts = entry_times_map.get((sym, side_key, iv))
                            dt_obj = self._parse_any_datetime(ts)
                            if dt_obj:
                                try:
                                    epoch = dt_obj.timestamp()
                                except Exception:
                                    epoch = None
                                if epoch is not None:
                                    open_times.append((epoch, dt_obj))
                        if not open_times:
                            base_ts = getattr(self, '_entry_times', {}).get((sym, side_key)) if hasattr(self, '_entry_times') else None
                            dt_obj = self._parse_any_datetime(base_ts)
                            if dt_obj:
                                try:
                                    epoch = dt_obj.timestamp()
                                except Exception:
                                    epoch = None
                                if epoch is not None:
                                    open_times.append((epoch, dt_obj))
                        if not open_times and data.get('update_time'):
                            dt_obj = self._parse_any_datetime(data.get('update_time'))
                            if dt_obj:
                                try:
                                    epoch = dt_obj.timestamp()
                                except Exception:
                                    epoch = None
                                if epoch is not None:
                                    open_times.append((epoch, dt_obj))
                        if open_times:
                            open_times.sort(key=lambda item: item[0])
                            rec['open_time'] = self._format_display_time(open_times[0][1])
                        positions_map[(sym, side_key)] = rec
                    except Exception:
                        continue
            except Exception:
                pass

        if not hasattr(self, '_open_position_records'):
            self._open_position_records = {}
            self._closed_position_records = []

        from datetime import datetime as _dt
        now_dt = _dt.now().astimezone()
        prev_records = getattr(self, '_open_position_records', {}) or {}
        closed_keys = set(prev_records.keys()) - set(positions_map.keys())
        if closed_keys:
            now_fmt = self._format_display_time(now_dt)
            for key in closed_keys:
                rec = prev_records.get(key)
                if not rec:
                    continue
                closed_rec = dict(rec)
                closed_rec['status'] = 'Closed'
                closed_rec['close_time'] = now_fmt
                self._closed_position_records.insert(0, closed_rec)
            if len(self._closed_position_records) > 200:
                self._closed_position_records = self._closed_position_records[:200]

        self._open_position_records = positions_map

        display_records = sorted(positions_map.values(), key=lambda d: (d['symbol'], d.get('side_key'), d.get('entry_tf'))) + self._closed_position_records

        self.pos_table.setRowCount(0)
        for rec in display_records:
            try:
                data = rec.get('data', {}) or {}
                sym = rec.get('symbol')
                side_key = rec.get('side_key')
                interval = rec.get('entry_tf') or '-'
                row = self.pos_table.rowCount()
                self.pos_table.insertRow(row)

                qty_show = float(data.get('qty') or 0.0)
                mark = float(data.get('mark') or 0.0)
                size_usdt = float(data.get('size_usdt') or (qty_show * mark))
                mr = normalize_margin_ratio(data.get('margin_ratio'))
                margin_usdt = float(data.get('margin_usdt') or 0.0)
                pnl_roi = data.get('pnl_roi')
                side_text = 'Long' if side_key == 'L' else ('Short' if side_key == 'S' else 'Spot')
                open_time = rec.get('open_time') or '-'
                close_time = rec.get('close_time') if rec.get('status') == 'Closed' else '-'
                status_txt = rec.get('status', 'Active')

                self.pos_table.setItem(row, 0, QtWidgets.QTableWidgetItem(sym))
                self.pos_table.setItem(row, 1, QtWidgets.QTableWidgetItem(f"{qty_show:.8f}"))
                self.pos_table.setItem(row, 2, QtWidgets.QTableWidgetItem(f"{mark:.8f}" if mark else '-'))
                self.pos_table.setItem(row, 3, QtWidgets.QTableWidgetItem(f"{size_usdt:.2f}"))
                self.pos_table.setItem(row, 4, QtWidgets.QTableWidgetItem(f"{mr:.2f}%" if mr > 0 else '-'))
                self.pos_table.setItem(row, 5, QtWidgets.QTableWidgetItem(f"{margin_usdt:.2f} USDT" if margin_usdt else '-'))
                self.pos_table.setItem(row, 6, QtWidgets.QTableWidgetItem(str(pnl_roi or '-')))
                self.pos_table.setItem(row, 7, QtWidgets.QTableWidgetItem(interval or '-'))
                self.pos_table.setItem(row, 8, QtWidgets.QTableWidgetItem(side_text))
                self.pos_table.setItem(row, 9, QtWidgets.QTableWidgetItem(str(open_time or '-')))
                self.pos_table.setItem(row, 10, QtWidgets.QTableWidgetItem(str(close_time or '-')))
                self.pos_table.setItem(row, 11, QtWidgets.QTableWidgetItem(status_txt))
                btn = self._make_close_btn(sym, side_key, interval, qty_show)
                if status_txt != 'Active':
                    btn.setEnabled(False)
                self.pos_table.setCellWidget(row, 12, btn)
            except Exception:
                pass
    except Exception as e:
        self.log(f"Positions render failed: {e}")
    def _make_close_btn(self, symbol: str, side_key: str | None = None, interval: str | None = None, qty: float | None = None):
        label = "Close"
        if side_key == "L":
            label = "Close Long"
        elif side_key == "S":
            label = "Close Short"
        btn = QtWidgets.QPushButton(label)
        tooltip_bits = []
        if side_key == "L":
            tooltip_bits.append("Closes the long leg")
        elif side_key == "S":
            tooltip_bits.append("Closes the short leg")
        if interval and interval not in ("-", "SPOT"):
            tooltip_bits.append(f"Interval {interval}")
        if qty and qty > 0:
            try:
                tooltip_bits.append(f"Qty ~= {qty:.6f}")
            except Exception:
                pass
        if tooltip_bits:
            btn.setToolTip(" | ".join(tooltip_bits))
        btn.setEnabled(side_key in ("L", "S"))
        interval_key = interval if interval not in ("-", "SPOT") else None
        btn.clicked.connect(lambda _, s=symbol, sk=side_key, iv=interval_key, q=qty: self._close_position_single(s, sk, iv, q))
        return btn

    def _close_position_single(self, symbol: str, side_key: str | None, interval: str | None, qty: float | None):
        if not symbol:
            return
        try:
            from ..workers import CallWorker as _CallWorker
        except Exception as exc:
            try:
                self.log(f"Close {symbol} setup error: {exc}")
            except Exception:
                pass
            return
        if side_key not in ("L", "S"):
            try:
                self.log(f"{symbol}: manual close is only available for futures legs.")
            except Exception:
                pass
            return
        if getattr(self, "shared_binance", None) is None:
            try:
                self.shared_binance = BinanceWrapper(
                    self.api_key_edit.text().strip(),
                    self.api_secret_edit.text().strip(),
                    mode=self.mode_combo.currentText(),
                    account_type=self.account_combo.currentText(),
                    default_leverage=int(self.leverage_spin.value() or 1),
                    default_margin_mode=self.margin_mode_combo.currentText() or "Isolated"
                )
            except Exception as exc:
                try:
                    self.log(f"Close {symbol} setup error: {exc}")
                except Exception:
                    pass
                return
        account = (self.account_combo.currentText() or "").upper()
        try:
            qty_val = float(qty or 0.0)
        except Exception:
            qty_val = 0.0

        def _do():
            bw = self.shared_binance
            if account.startswith("FUT"):
                if side_key in ("L", "S") and qty_val > 0:
                    try:
                        dual = bool(bw.get_futures_dual_side())
                    except Exception:
                        dual = False
                    order_side = "SELL" if side_key == "L" else "BUY"
                    pos_side = None
                    if dual:
                        pos_side = "LONG" if side_key == "L" else "SHORT"
                    return bw.close_futures_leg_exact(symbol, qty_val, side=order_side, position_side=pos_side)
                return bw.close_futures_position(symbol)
            return {"ok": False, "error": "Spot manual close via UI is not available yet"}

        def _done(res, err):
            succeeded = False
            try:
                if err:
                    self.log(f"Close {symbol} error: {err}")
                else:
                    self.log(f"Close {symbol} result: {res}")
                    succeeded = isinstance(res, dict) and res.get("ok")
                if succeeded and interval and side_key in ("L", "S"):
                    try:
                        self._entry_intervals.setdefault(symbol, {"L": set(), "S": set()}).setdefault(side_key, set()).discard(interval)
                    except Exception:
                        pass
                    try:
                        self._entry_times_by_iv.pop((symbol, side_key, interval), None)
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                self.refresh_positions(symbols=[symbol])
            except Exception:
                pass

        worker = _CallWorker(_do, parent=self)
        try:
            worker.progress.connect(self.log)
        except Exception:
            pass
        worker.done.connect(_done)
        worker.finished.connect(worker.deleteLater)

        def _cleanup():
            try:
                self._bg_workers.remove(worker)
            except Exception:
                pass

        if not hasattr(self, "_bg_workers"):
            self._bg_workers = []
        self._bg_workers.append(worker)
        worker.finished.connect(_cleanup)
        worker.start()

    def _setup_log_buffer(self):
        from collections import deque
        self._log_buf = deque(maxlen=8000)
        self._log_timer = QtCore.QTimer(self)
        self._log_timer.setInterval(200)
        self._log_timer.timeout.connect(self._flush_log_buffer)
        self._log_timer.start()

    def _buffer_log(self, msg: str):
        try:
            self._log_buf.append(msg)
        except Exception:
            pass

    def _flush_log_buffer(self):
        try:
            if not hasattr(self, '_log_buf') or not self._log_buf:
                return
            lines = []
            for _ in range(300):
                if not self._log_buf:
                    break
                lines.append(self._log_buf.popleft())
            if not lines:
                return
            from datetime import datetime as _dt
            import re as _re
            pat = _re.compile(r'^\[?(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]?\s*(.*)$')
            pat2 = _re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*(.*)$')
            formatted = []
            for raw in lines:
                line = str(raw)
                match = pat.match(line)
                if match:
                    iso_ts, rest = match.groups()
                    body = rest.strip()
                    nested = pat2.match(body)
                    if nested:
                        body = nested.group(2).strip()
                    try:
                        ts = _dt.strptime(iso_ts, "%Y-%m-%d %H:%M:%S").strftime("%d-%m-%Y %H:%M:%S")
                    except Exception:
                        ts = _dt.now().strftime("%d-%m-%Y %H:%M:%S")
                    formatted.append(f"[{ts}] {body}" if body else f"[{ts}]")
                else:
                    ts = _dt.now().strftime("%d-%m-%Y %H:%M:%S")
                    formatted.append(f"[{ts}] {line}")
            text = '\n'.join(formatted)
            try:
                self.log_edit.appendPlainText(text)
            except Exception:
                self.log_edit.append(text)
            self.log_edit.verticalScrollBar().setValue(self.log_edit.verticalScrollBar().maximum())
        except Exception:
            pass


    def trigger_positions_refresh(self):
        try:
            if hasattr(self, '_pos_worker') and self._pos_worker is not None:
                QtCore.QMetaObject.invokeMethod(self._pos_worker, "_tick", QtCore.Qt.QueuedConnection)
        except Exception:
            pass

    def _parse_any_datetime(self, value):
        from datetime import datetime as _dt
        if value is None:
            return None
        if isinstance(value, _dt):
            try:
                return value.astimezone() if value.tzinfo else value
            except Exception:
                return value
        if isinstance(value, (int, float)):
            try:
                raw = float(value)
                if raw > 1e12:
                    raw /= 1000.0
                return _dt.fromtimestamp(raw, tz=timezone.utc).astimezone()
            except Exception:
                pass
        try:
            s = str(value).strip()
        except Exception:
            return None
        if not s:
            return None
        s_norm = s.replace('/', '-')
        patterns = (
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%dT%H:%M:%S.%f',
            '%Y-%m-%dT%H:%M:%S.%fZ',
            '%d-%m-%Y %H:%M:%S',
            '%d.%m.%Y %H:%M:%S',
        )
        for fmt in patterns:
            try:
                dt = _dt.strptime(s_norm, fmt)
                if fmt.endswith('Z'):
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone() if dt.tzinfo else dt
            except Exception:
                continue
        try:
            dt = _dt.fromisoformat(s_norm.replace('Z', '+00:00'))
            return dt.astimezone() if dt.tzinfo else dt
        except Exception:
            return None

    def _format_display_time(self, value):
        dt = self._parse_any_datetime(value)
        if dt is None:
            try:
                return str(value) if value not in (None, '') else '-'
            except Exception:
                return '-'
        try:
            if getattr(dt, 'tzinfo', None):
                dt = dt.astimezone()
        except Exception:
            pass
        return dt.strftime('%d.%m.%Y %H:%M:%S')


    def _parse_pos_interval_label(self, label: str) -> int:
        # return milliseconds
        try:
            s = (label or "").strip().lower().replace(" ", "")
            if s.startswith("5second"): return 5_000
            if s.startswith("15second"): return 15_000
            if s.startswith("30second"): return 30_000
            if s.startswith("1minute"): return 60_000
            if s.startswith("3minute"): return 180_000
            if s.startswith("5minute"): return 300_000
            if s.startswith("10minute"): return 600_000
            if s.startswith("15minute"): return 900_000
            if s.startswith("30minute"): return 1_800_000
            if s.startswith("1hour"): return 3_600_000
        except Exception:
            pass
        return 5_000

    
    
    def _collect_strategy_intervals(self, symbol: str, side_key: str):
        intervals = set()
        try:
            engines = getattr(self, 'strategy_engines', {}) or {}
            sym_upper = (symbol or '').upper()
            side_key_upper = (side_key or '').upper()
            for eng in engines.values():
                cfg = getattr(eng, 'config', {}) or {}
                cfg_sym = str(cfg.get('symbol') or '').upper()
                if not cfg_sym or cfg_sym != sym_upper:
                    continue
                interval = str(cfg.get('interval') or '').strip()
                if not interval:
                    continue
                side_pref = str(cfg.get('side') or 'BOTH').upper()
                if side_pref in ('BUY', 'LONG'):
                    allowed = {'L'}
                elif side_pref in ('SELL', 'SHORT'):
                    allowed = {'S'}
                else:
                    allowed = {'L', 'S'}
                if side_key_upper in allowed:
                    intervals.add(interval)
        except Exception:
            pass
        return intervals


    def _apply_positions_refresh_settings(self):
        try:
            self.req_pos_start.emit(5000)
        except Exception:
            pass

    def apply_theme(self, name: str):
        theme = (name or '').strip().lower()
        stylesheet = self.DARK_THEME if theme.startswith('dark') else self.LIGHT_THEME
        self.setStyleSheet(stylesheet)
        try:
            self.config['theme'] = 'Dark' if theme.startswith('dark') else 'Light'
        except Exception:
            pass

    def _append_log(self, msg: str):
        ts = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        self.log_edit.append(f"[{ts}] {msg}")
        self.log_edit.verticalScrollBar().setValue(self.log_edit.verticalScrollBar().maximum())

    def log(self, msg: str):
        self.log_signal.emit(msg)

    def _trade_mux(self, evt: dict):
        try:
            # forward to guard first
            if hasattr(self, 'guard') and callable(getattr(self.guard, 'trade_hook', None)):
                self.guard.trade_hook(evt)
        except Exception:
            pass
        try:
            # then notify UI
            self.trade_signal.emit(evt)
        except Exception:
            pass

    def _on_trade_signal(self, order_info: dict):
        self.log(f"TRADE UPDATE: {order_info}")
        sym = order_info.get("symbol")
        interval = order_info.get("interval")
        side = order_info.get("side")
        position_side = order_info.get("position_side") or side
        event_type = str(order_info.get("event") or "").lower()
        status = str(order_info.get("status") or "").lower()
        ok_flag = order_info.get("ok")
        interval = order_info.get("interval")
        side_for_key = position_side or side
        side_key = "L" if str(side_for_key).upper() in ("BUY", "LONG") else "S"
        if event_type == "close_interval":
            try:
                self._entry_intervals.setdefault(sym, {"L": set(), "S": set()}).setdefault(side_key, set()).discard(interval)
            except Exception:
                pass
            try:
                self._entry_times_by_iv.pop((sym, side_key, interval), None)
            except Exception:
                pass
            if sym:
                self.traded_symbols.add(sym)
            self.update_balance_label()
            self.refresh_positions(symbols=[sym] if sym else None)
            return
        is_success = (status != "error") and (ok_flag is None or ok_flag is True)
        if sym and interval and side_for_key:
            side_key = "L" if str(side_for_key).upper() in ("BUY", "LONG") else "S"
            self._entry_intervals.setdefault(sym, {'L': set(), 'S': set()})
            if is_success:
                self._entry_intervals[sym][side_key].add(interval)
                tstr = order_info.get('time')
                if tstr:
                    self._entry_times[(sym, side_key)] = tstr
                else:
                    from datetime import datetime
                    tstr = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    self._entry_times[(sym, side_key)] = tstr
                self._entry_times_by_iv[(sym, side_key, interval)] = tstr
            else:
                # Remove any stale interval markers when an order fails.
                try:
                    self._entry_intervals[sym][side_key].discard(interval)
                    self._entry_times_by_iv.pop((sym, side_key, interval), None)
                except Exception:
                    pass
        if sym:
            self.traded_symbols.add(sym)
        self.update_balance_label()
        self.refresh_positions(symbols=[sym] if sym else None)

    # ---- actions
    


def refresh_symbols(self):
    from ..workers import CallWorker as _CallWorker
    self.refresh_symbols_btn.setEnabled(False)
    self.refresh_symbols_btn.setText("Refreshing...")
    def _do():
        tmp_wrapper = BinanceWrapper(self.api_key_edit.text().strip(), self.api_secret_edit.text().strip(),
                                     mode=self.mode_combo.currentText(),
                                     account_type=self.account_combo.currentText())
        syms = tmp_wrapper.fetch_symbols(sort_by_volume=True)
        return syms
    def _done(res, err):
        try:
            if err or not res:
                self.log(f"Failed to refresh symbols: {err or 'no symbols'}")
                return
            self.symbol_list.clear()
            self.symbol_list.addItems([s for s in res if s.endswith("USDT")])
            self.log(f"Loaded {self.symbol_list.count()} USDT-pair symbols for {self.account_combo.currentText()}.")
        finally:
            self.refresh_symbols_btn.setEnabled(True)
            self.refresh_symbols_btn.setText("Refresh Symbols")
    w = _CallWorker(_do, parent=self)
    try:
        w.progress.connect(self.log)
    except Exception:
        pass
    w.done.connect(_done)
    w.start()

def start_stop_worker(self):
    try:
        self.log("Stop requested…")
        self.stop_button.setEnabled(False)
        self.start_button.setEnabled(False)
    except Exception:
        pass
    try:
        self.stop_worker = StopWorker(self.api, account_type=self.account_type, is_futures=(self.account_type=='futures'))
        self.stop_worker.log_signal.connect(self.log)
        self.stop_worker.finished.connect(lambda: self.on_stop_done())
        self.start_stop_worker()
    except Exception as e:
        self.log(f"Failed to start stop-worker: {e!r}")
    
def apply_futures_modes(self):
    from ..workers import CallWorker as _CallWorker
    mm = self.margin_mode_combo.currentText().upper()
    pos_mode = self.position_mode_combo.currentText()
    hedge = (pos_mode.strip().lower() == 'hedge')
    assets_mode = self.assets_mode_combo.currentText()
    multi = (assets_mode.strip().lower() == 'multi-assets')
    tif = self.tif_combo.currentText()
    gtdm = int(self.gtd_minutes_spin.value())
    def _do():
        try:
            self.shared_binance.set_position_mode(hedge)
        except Exception:
            pass
        try:
            self.shared_binance.set_multi_assets_mode(multi)
        except Exception:
            pass
        return True
    def _done(res, err):
        if err:
            self.log(f"Apply futures modes error: {err}")
            return
        self.config['margin_mode'] = 'Isolated' if mm=='ISOLATED' else 'Cross'
        self.config['position_mode'] = 'Hedge' if hedge else 'One-way'
        self.config['assets_mode'] = 'Multi-Assets' if multi else 'Single-Asset'
        self.config['tif'] = tif
        self.config['gtd_minutes'] = gtdm
    w = _CallWorker(_do, parent=self)
    try:
        w.progress.connect(self.log)
    except Exception:
        pass
    w.done.connect(_done)
    w.start()

def _mw_update_balance_label(self):
    from ..workers import CallWorker as _CallWorker
    if not hasattr(self, "_bg_workers"):
        self._bg_workers = []
    def _compute():
        bw = BinanceWrapper(
            self.api_key_edit.text().strip(),
            self.api_secret_edit.text().strip(),
            mode=self.mode_combo.currentText(),
            account_type=self.account_combo.currentText(),
        )
        try: bw.indicator_source = str(self.ind_source_combo.currentText())
        except Exception: pass
        out = {"ok": True, "bal": 0.0, "acct": str(self.account_combo.currentText()).strip().upper(), "dual": None, "err": None}
        try:
            if out["acct"] == "FUTURES":
                ok, err = bw.futures_api_ok()
                if ok:
                    try: out["dual"] = bool(bw.get_futures_dual_side())
                    except Exception: out["dual"] = None
                else:
                    out["ok"] = False; out["err"] = err
            out["bal"] = float(bw.get_total_usdt_value() or 0.0)
        except Exception as e:
            out["ok"] = False; out["err"] = str(e)
        return out
    w = _CallWorker(_compute, parent=self)
    def on_done(res, err):
        try:
            if err or not res or not res.get("ok", True):
                msg = (err and str(err)) or (res and res.get("err")) or "unknown error"
                try: self.log(f"Balance refresh failed: {msg}")
                except Exception: pass
                try: self.balance_label.setText("0.0000 USDT")
                except Exception: pass
            else:
                try:
                    if res.get("acct") == "FUTURES":
                        dual = res.get("dual")
                        self.pos_mode_label.setText(f"Position Mode: {'Hedge' if (dual is True) else 'One-way' if (dual is False) else 'Unknown'}")
                    self.balance_label.setText(f"{float(res.get('bal') or 0.0):.4f} USDT")
                except Exception: pass
        finally:
            try: self.refresh_balance_btn.setEnabled(True); self.refresh_balance_btn.setText("Refresh Balance")
            except Exception: pass
    try: self.refresh_balance_btn.setEnabled(False); self.refresh_balance_btn.setText("Refreshing...")
    except Exception: pass
    try:
        w.done.connect(on_done)
        w.finished.connect(w.deleteLater)
        def _cleanup():
            try:
                self._bg_workers.remove(w)
            except Exception:
                pass
        w.finished.connect(_cleanup)
    except Exception:
        pass
    self._bg_workers.append(w)
    w.start()


def _on_leverage_changed(self, value):
    try:
        self.config['leverage'] = int(value)
    except Exception:
        pass
    try:
        if hasattr(self, 'shared_binance') and self.shared_binance:
            self.shared_binance.set_futures_leverage(int(value))
    except Exception:
        pass

try:
    MainWindow.on_leverage_changed = _on_leverage_changed
except Exception:
    pass



def start_strategy(self):
    started = 0
    try:
        # Loop Interval Override from UI (e.g., "10s", "2m", "1h", "1d", "1w"). Empty = use candle interval.
        raw_override = (self.loop_edit.text().strip() if hasattr(self, 'loop_edit') else '')
        loop_override = re.sub(r'\s+', '', raw_override.lower()) if raw_override else None
        if loop_override and not re.match(r'^\d+(s|m|h|d|w)?$', loop_override):
            self.log(f"Invalid loop interval override: {raw_override}. Use formats like '10s', '2m', '1h'. Ignoring.")
            loop_override = None

        runtime_ctx = self._override_ctx("runtime")
        pair_entries = []
        table = runtime_ctx.get("table") if runtime_ctx else None
        if table is not None:
            try:
                selected_rows = sorted({idx.row() for idx in table.selectionModel().selectedRows()})
            except Exception:
                selected_rows = []
            if selected_rows:
                for row in selected_rows:
                    sym_item = table.item(row, 0)
                    iv_item = table.item(row, 1)
                    sym = sym_item.text().strip().upper() if sym_item else ''
                    iv = iv_item.text().strip() if iv_item else ''
                    if sym and iv:
                        pair_entries.append((sym, iv))
        if not pair_entries:
            for entry in self.config.get("runtime_symbol_interval_pairs", []) or []:
                sym = str((entry or {}).get('symbol') or '').strip().upper()
                interval_val = str((entry or {}).get('interval') or '').strip()
                if sym and interval_val:
                    pair_entries.append((sym, interval_val))
        syms = [self.symbol_list.item(i).text() for i in range(self.symbol_list.count())
                if self.symbol_list.item(i).isSelected()]
        if not syms and self.symbol_list.count():
            syms = [self.symbol_list.item(i).text() for i in range(self.symbol_list.count())]

        ivs = [self.interval_list.item(i).text() for i in range(self.interval_list.count())
               if self.interval_list.item(i).isSelected()]
        if not ivs:
            ivs = ["1m"]



        if pair_entries:
            combos = pair_entries
        else:
            if not syms:
                self.log("No symbols available. Click Refresh Symbols.")
                return
            combos = []
            for sym in syms:
                for iv in ivs:
                    combos.append((sym, iv))
        # Deduplicate combos while preserving order
        unique_combos = []
        seen_combo = set()
        for sym, iv in combos:
            sym_norm = str(sym).strip().upper()
            iv_norm = str(iv).strip().lower()
            key = (sym_norm, iv_norm)
            if not sym_norm or not iv_norm:
                continue
            if key in seen_combo:
                continue
            seen_combo.add(key)
            unique_combos.append((sym_norm, iv_norm))
        combos = unique_combos
        total_jobs = len(combos)
        concurrency = StrategyEngine.concurrent_limit()
        if total_jobs > concurrency:
            self.log(f"{total_jobs} symbol/interval loops requested; limiting concurrent execution to {concurrency} to keep the UI responsive.")

        if getattr(self, "shared_binance", None) is None:
            self.shared_binance = BinanceWrapper(
                self.api_key_edit.text().strip(), self.api_secret_edit.text().strip(),
                mode=self.mode_combo.currentText(), account_type=self.account_combo.currentText(),
                default_leverage=int(self.leverage_spin.value() or 1),
                default_margin_mode=self.margin_mode_combo.currentText() or "Isolated"
            )

        if not hasattr(self, "strategy_engines"):
            self.strategy_engines = {}

        for sym, iv in combos:
            key = f"{sym}@{iv}"
            try:
                # Skip if an engine is already running for this key
                if key in self.strategy_engines and getattr(self.strategy_engines[key], "is_alive", lambda: False)():
                    self.log(f"Engine already running for {key}, skipping.")
                    continue

                cfg = copy.deepcopy(self.config)
                cfg.update({
                    "symbol": sym,
                    "interval": iv,
                    "position_pct": float(self.pospct_spin.value() or self.config.get("position_pct", 100.0)),
                    "side": self.side_combo.currentText(),
                })
                eng = StrategyEngine(self.shared_binance, cfg, log_callback=self.log,
                                     trade_callback=self._on_trade_signal,
                                     loop_interval_override=loop_override)
                eng.start()
                self.strategy_engines[key] = eng
                self.log(f"Loop start for {key}.")
                started += 1
            except Exception as e:
                self.log(f"Failed to start engine for {key}: {e}")

        if started == 0:
            self.log("No new engines started (already running?)")
    except Exception as e:
        try:
            self.log(f"Start error: {e}")
        except Exception:
            pass
    finally:
        try:
            self._sync_runtime_state()
        except Exception:
            pass


def stop_strategy_async(self, close_positions: bool = True):
    """Stop all StrategyEngine threads and then market-close ALL active positions asynchronously."""
    try:
        # 1) Stop loops
        if hasattr(self, "strategy_engines") and self.strategy_engines:
            for key, eng in list(self.strategy_engines.items()):
                try:
                    eng.stop()
                except Exception:
                    pass
            # tiny pause to let threads settle
            try:
                import time as _t; _t.sleep(0.05)
            except Exception:
                pass
            self.strategy_engines.clear()
            self.log("Stopped all strategy engines.")
        else:
            self.log("No engines to stop.")
        # 2) Then close all open positions in background (non-blocking)
        try:
            if close_positions:
                self.close_all_positions_async()
        except Exception as e:
            try: self.log(f"Failed to trigger close-all: {e}")
            except Exception: pass

    except Exception as e:
        try: self.log(f"Stop error: {e}")
        except Exception: pass
    finally:
        try:
            self._sync_runtime_state()
        except Exception:
            pass

def save_config(self):
    try:
        from PyQt6 import QtWidgets
        import json
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
        try: self.log(f"Save config error: {e}")
        except Exception: pass

def load_config(self):
    try:
        from PyQt6 import QtWidgets
        import json
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Load Config", "", "JSON Files (*.json)")
        if not fn:
            return
        with open(fn, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if isinstance(cfg, dict):
            self.config.update(cfg)
        self.config.setdefault('runtime_symbol_interval_pairs', [])
        self.config.setdefault('backtest_symbol_interval_pairs', [])
        self.backtest_config.setdefault('backtest_symbol_interval_pairs', list(self.config.get('backtest_symbol_interval_pairs', [])))
        self._refresh_symbol_interval_pairs("runtime")
        self._refresh_symbol_interval_pairs("backtest")
        self.log(f"Loaded config from {fn}")
        try:
            self.leverage_spin.setValue(int(self.config.get("leverage", self.leverage_spin.value())))
            self.margin_mode_combo.setCurrentText(self.config.get("margin_mode", self.margin_mode_combo.currentText()))
            self.position_mode_combo.setCurrentText(self.config.get("position_mode", self.position_mode_combo.currentText()))
            self.assets_mode_combo.setCurrentText(self.config.get("assets_mode", self.assets_mode_combo.currentText()))
            self.tif_combo.setCurrentText(self.config.get("tif", self.tif_combo.currentText()))
            self.gtd_minutes_spin.setValue(int(self.config.get("gtd_minutes", self.gtd_minutes_spin.value())))
        except Exception:
            pass
    except Exception as e:
        try: self.log(f"Load config error: {e}")
        except Exception: pass

try:
    MainWindow.start_strategy = start_strategy
except Exception:
    pass
try:
    MainWindow.stop_strategy_async = stop_strategy_async
except Exception:
    pass
try:
    MainWindow.save_config = save_config
    MainWindow.load_config = load_config
except Exception:
    pass

try:
    MainWindow.refresh_symbols = refresh_symbols
except Exception:
    pass

try:
    MainWindow.apply_futures_modes = apply_futures_modes
except Exception:
    pass


def refresh_positions(self, *args, **kwargs):
    """Manual refresh of positions: reconfigure worker and trigger an immediate tick."""
    try:
        try:
            self._reconfigure_positions_worker()
        except Exception:
            pass
        try:
            self.req_pos_start.emit(5000)
        except Exception:
            pass
        self.log("Positions refresh requested.")
    except Exception as e:
        try: self.log(f"Refresh positions error: {e}")
        except Exception: pass

try:
    MainWindow.refresh_positions = refresh_positions
except Exception:
    pass

def close_all_positions_async(self):
    """Close all open futures positions using reduce-only market orders in a worker."""
    try:
        from ..workers import CallWorker as _CallWorker
        if getattr(self, "shared_binance", None) is None:
            self.shared_binance = BinanceWrapper(
                self.api_key_edit.text().strip(), self.api_secret_edit.text().strip(),
                mode=self.mode_combo.currentText(), account_type=self.account_combo.currentText(),
                default_leverage=int(self.leverage_spin.value() or 1),
                default_margin_mode=self.margin_mode_combo.currentText() or "Isolated"
            )
        def _do():
            if (self.account_combo.currentText() or '').upper().startswith('FUT'):
                return self.shared_binance.close_all_futures_positions()
            else:
                return self.shared_binance.close_all_spot_positions()
        def _done(res, err):
            if err:
                self.log(f"Close-all error: {err}")
                return
            try:
                for r in (res or []):
                    if not r.get('ok'):
                        self.log(f"Close-all {r.get('symbol')}: error → {r.get('error')}")
                    else:
                        self.log(f"Close-all {r.get('symbol')}: closed={r.get('closed')}")
                n_ok = sum(1 for r in (res or []) if r.get('ok'))
                n_all = len(res or [])
                self.log(f"Close-all completed: {n_ok}/{n_all} ok.")
            except Exception:
                self.log(f"Close-all result: {res}")
        w = _CallWorker(_do, parent=self)
        try: w.progress.connect(self.log)
        except Exception: pass
        w.done.connect(_done)
        w.start()
    except Exception as e:
        try: self.log(f"Close-all setup error: {e}")
        except Exception: pass

try:
    MainWindow.close_all_positions_async = close_all_positions_async
except Exception:
    pass


def update_balance_label(self):
    """Refresh the 'Total USDT balance' label safely after an order."""
    try:
        if getattr(self, "shared_binance", None) is None:
            return
        bal = 0.0
        try:
            if (self.account_combo.currentText() or '').upper().startswith('FUT'):
                bal = float(self.shared_binance.get_futures_balance_usdt() or 0.0)
            else:
                bal = float(self.shared_binance.get_spot_balance('USDT') or 0.0)
        except Exception:
            pass
        try:
            self.balance_label.setText(f"{bal:.3f} USDT")
        except Exception:
            # Fallback: log only
            self.log(f"Balance updated: {bal:.3f} USDT")
    except Exception as e:
        try: self.log(f"Balance label update error: {e}")
        except Exception: pass

try:
    MainWindow.update_balance_label = update_balance_label
except Exception:
    pass


# --- Graceful teardown to avoid "QThread destroyed while running" and timer warnings ---
def _teardown_positions_thread(self):
    try:
        if getattr(self, "_pos_worker", None) is not None:
            try:
                # Ask the worker (in its own thread) to stop its QTimer
                self.req_pos_stop.emit()
            except Exception:
                pass
        if getattr(self, "_pos_thread", None) is not None:
            try:
                self._pos_thread.quit()
                # wait up to 2 seconds for a clean exit
                self._pos_thread.wait(2000)
            except Exception:
                pass
        self._pos_worker = None
        self._pos_thread = None
    except Exception:
        pass

def closeEvent(self, event):
    try:
        # Stop strategy loops and close positions if needed
        try:
            self.stop_strategy_async(close_positions=bool(getattr(self, "cb_close_on_exit", None) and self.cb_close_on_exit.isChecked()))
        except Exception:
            pass
        _teardown_positions_thread(self)
    finally:
        try:
            super(MainWindow, self).closeEvent(event)
        except Exception:
            # if super call fails (rare), still accept close
            try:
                event.accept()
            except Exception:
                pass

try:
    MainWindow._teardown_positions_thread = _teardown_positions_thread
    MainWindow.closeEvent = closeEvent
except Exception:
    pass


def _gui_apply_theme(self, name: str):
    theme = (name or '').strip().lower()
    stylesheet = self.DARK_THEME if theme.startswith('dark') else self.LIGHT_THEME
    self.setStyleSheet(stylesheet)
    try:
        self.config['theme'] = 'Dark' if theme.startswith('dark') else 'Light'
    except Exception:
        pass

try:
    MainWindow.apply_theme = _gui_apply_theme
except Exception:
    pass

try:
    MainWindow._on_positions_ready = _gui_on_positions_ready
except Exception:
    pass


def _gui_setup_log_buffer(self):
    from collections import deque
    self._log_buf = deque(maxlen=8000)
    self._log_timer = QtCore.QTimer(self)
    self._log_timer.setInterval(200)
    self._log_timer.timeout.connect(self._flush_log_buffer)
    self._log_timer.start()

def _gui_buffer_log(self, msg: str):
    try:
        self._log_buf.append(msg)
    except Exception:
        pass

def _mw_reconfigure_positions_worker(self):
    try:
        worker = getattr(self, '_pos_worker', None)
        if worker is None:
            return
        try:
            symbols = [self.symbol_list.item(i).text() for i in range(self.symbol_list.count()) if self.symbol_list.item(i).isSelected()]
        except Exception:
            symbols = None
        worker.configure(
            api_key=self.api_key_edit.text().strip(),
            api_secret=self.api_secret_edit.text().strip(),
            mode=self.mode_combo.currentText(),
            account_type=self.account_combo.currentText(),
            symbols=symbols or None,
        )
    except Exception:
        pass


def _mw_collect_strategy_intervals(self, symbol: str, side_key: str):
    intervals = set()
    try:
        engines = getattr(self, 'strategy_engines', {}) or {}
        sym_upper = (symbol or '').upper()
        side_key_upper = (side_key or '').upper()
        for eng in engines.values():
            cfg = getattr(eng, 'config', {}) or {}
            cfg_sym = str(cfg.get('symbol') or '').upper()
            if not cfg_sym or cfg_sym != sym_upper:
                continue
            interval = str(cfg.get('interval') or '').strip()
            if not interval:
                continue
            side_pref = str(cfg.get('side') or 'BOTH').upper()
            if side_pref in ('BUY', 'LONG'):
                allowed = {'L'}
            elif side_pref in ('SELL', 'SHORT'):
                allowed = {'S'}
            else:
                allowed = {'L', 'S'}
            if side_key_upper in allowed:
                intervals.add(interval)
    except Exception:
        pass
    return intervals


def _mw_parse_any_datetime(self, value):
    from datetime import datetime as _dt
    if value is None:
        return None
    if isinstance(value, _dt):
        try:
            return value.astimezone() if value.tzinfo else value
        except Exception:
            return value
    if isinstance(value, (int, float)):
        try:
            raw = float(value)
            if raw > 1e12:
                raw /= 1000.0
            return _dt.fromtimestamp(raw, tz=timezone.utc).astimezone()
        except Exception:
            pass
    try:
        s = str(value).strip()
    except Exception:
        return None
    if not s:
        return None
    s_norm = s.replace('/', '-')
    patterns = (
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%dT%H:%M:%S.%f',
        '%Y-%m-%dT%H:%M:%S.%fZ',
        '%d-%m-%Y %H:%M:%S',
        '%d.%m.%Y %H:%M:%S',
    )
    for fmt in patterns:
        try:
            dt = _dt.strptime(s_norm, fmt)
            if fmt.endswith('Z'):
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone() if dt.tzinfo else dt
        except Exception:
            continue
    try:
        dt = _dt.fromisoformat(s_norm.replace('Z', '+00:00'))
        return dt.astimezone() if dt.tzinfo else dt
    except Exception:
        return None


def _mw_format_display_time(self, value):
    dt = _mw_parse_any_datetime(self, value)
    if dt is None:
        try:
            return str(value) if value not in (None, '') else '-'
        except Exception:
            return '-'
    try:
        if getattr(dt, 'tzinfo', None):
            dt = dt.astimezone()
    except Exception:
        pass
    return dt.strftime('%d.%m.%Y %H:%M:%S')


def _mw_interval_sort_key(label: str):
    try:
        lbl = (label or '').strip().lower()
        if not lbl:
            return (float('inf'), '')
        import re as _re
        match = _re.match(r'(\d+(?:\.\d+)?)([smhdw]?)', lbl)
        if not match:
            return (float('inf'), lbl)
        value = float(match.group(1))
        unit = match.group(2) or 'm'
        factor = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400, 'w': 604800}.get(unit, 60)
        return (value * factor, lbl)
    except Exception:
        return (float('inf'), str(label))


def _gui_flush_log_buffer(self):
    try:
        if not hasattr(self, '_log_buf') or not self._log_buf:
            return
        lines = []
        for _ in range(300):
            if not self._log_buf:
                break
            lines.append(self._log_buf.popleft())
        if not lines:
            return
        from datetime import datetime as _dt
        import re as _re
        pat = _re.compile(r'^\[?(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]?\s*(.*)$')
        pat2 = _re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*(.*)$')
        formatted = []
        for raw in lines:
            line = str(raw)
            match = pat.match(line)
            if match:
                iso_ts, rest = match.groups()
                body = rest.strip()
                nested = pat2.match(body)
                if nested:
                    body = nested.group(2).strip()
                try:
                    ts = _dt.strptime(iso_ts, '%Y-%m-%d %H:%M:%S').strftime('%d-%m-%Y %H:%M:%S')
                except Exception:
                    ts = _dt.now().strftime('%d-%m-%Y %H:%M:%S')
                formatted.append(f"[{ts}] {body}" if body else f"[{ts}]")
            else:
                ts = _dt.now().strftime('%d-%m-%Y %H:%M:%S')
                formatted.append(f"[{ts}] {line}")
        text = '\n'.join(formatted)
        try:
            self.log_edit.appendPlainText(text)
        except Exception:
            self.log_edit.append(text)
        self.log_edit.verticalScrollBar().setValue(self.log_edit.verticalScrollBar().maximum())
    except Exception:
        pass

try:
    MainWindow._collect_strategy_intervals = _mw_collect_strategy_intervals
except Exception:
    pass

try:
    MainWindow._parse_any_datetime = _mw_parse_any_datetime
    MainWindow._format_display_time = _mw_format_display_time
except Exception:
    pass


try:
    MainWindow._setup_log_buffer = _gui_setup_log_buffer
    MainWindow._buffer_log = _gui_buffer_log
    MainWindow._flush_log_buffer = _gui_flush_log_buffer
except Exception:
    pass

try:
    MainWindow._reconfigure_positions_worker = _mw_reconfigure_positions_worker
except Exception:
    pass


def _mw_log(self, msg: str):
    try:
        self.log_signal.emit(str(msg))
    except Exception:
        pass

def _mw_trade_mux(self, evt: dict):
    try:
        guard = getattr(self, 'guard', None)
        hook = getattr(guard, 'trade_hook', None)
        if callable(hook):
            hook(evt)
    except Exception:
        pass
    try:
        self.trade_signal.emit(evt)
    except Exception:
        pass

def _mw_on_trade_signal(self, order_info: dict):
    self.log(f"TRADE UPDATE: {order_info}")
    sym = order_info.get("symbol")
    interval = order_info.get("interval")
    side = order_info.get("side")
    position_side = order_info.get("position_side") or side
    event_type = str(order_info.get("event") or "").lower()
    status = str(order_info.get("status") or "").lower()
    ok_flag = order_info.get("ok")
    interval = order_info.get("interval")
    side_for_key = position_side or side
    side_key = "L" if str(side_for_key).upper() in ("BUY", "LONG") else "S"
    if event_type == "close_interval":
        try:
            self._entry_intervals.setdefault(sym, {"L": set(), "S": set()}).setdefault(side_key, set()).discard(interval)
        except Exception:
            pass
        try:
            self._entry_times_by_iv.pop((sym, side_key, interval), None)
        except Exception:
            pass
        if sym:
            self.traded_symbols.add(sym)
        self.update_balance_label()
        self.refresh_positions(symbols=[sym] if sym else None)
        return
    is_success = (status != "error") and (ok_flag is None or ok_flag is True)
    if sym and interval and side_for_key:
        side_key = "L" if str(side_for_key).upper() in ("BUY", "LONG") else "S"
        self._entry_intervals.setdefault(sym, {'L': set(), 'S': set()})
        if is_success:
            self._entry_intervals[sym][side_key].add(interval)
            tstr = order_info.get('time')
            if tstr:
                self._entry_times[(sym, side_key)] = tstr
            else:
                from datetime import datetime
                tstr = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                self._entry_times[(sym, side_key)] = tstr
            self._entry_times_by_iv[(sym, side_key, interval)] = tstr
        else:
            try:
                self._entry_intervals[sym][side_key].discard(interval)
                self._entry_times_by_iv.pop((sym, side_key, interval), None)
            except Exception:
                pass
    if sym:
        self.traded_symbols.add(sym)
    self.update_balance_label()
    self.refresh_positions(symbols=[sym] if sym else None)

try:
    if not hasattr(MainWindow, 'log'):
        MainWindow.log = _mw_log
    if not hasattr(MainWindow, '_trade_mux'):
        MainWindow._trade_mux = _mw_trade_mux
    if not hasattr(MainWindow, '_on_trade_signal'):
        MainWindow._on_trade_signal = _mw_on_trade_signal
except Exception:
    pass