from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import pyqtSignal
from pathlib import Path
import copy
import re
from datetime import datetime, timezone

from ..config import DEFAULT_CONFIG
from ..binance_wrapper import BinanceWrapper
from ..strategy import StrategyEngine
from ..workers import StopWorker, StartWorker, CallWorker



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
            margin = float(p.get('isolatedWallet') or 0.0)
            if margin <= 0.0:
                margin = float(p.get('initialMargin') or 0.0)
            if margin <= 0.0 and lev > 0:
                margin = size_usdt / lev
            roi = (pnl / margin * 100.0) if margin > 0 else 0.0
            pnl_roi_str = f"{pnl:+.2f} USDT ({roi:+.2f}%)"
            return size_usdt, margin, pnl_roi_str
        except Exception:
            return 0.0, 0.0, "-"


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
                        size_usdt, margin_usdt, pnl_roi = self._compute_futures_metrics(p)
                        rows.append({
                            'symbol': sym,
                            'qty': abs(amt),
                            'mark': mark,
                            'value': value,
                            'size_usdt': size_usdt,
                            'margin_usdt': margin_usdt,
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
        self._closed_positions_history = []
        self._closed_history_limit = 300
        self._active_snapshots = {}
        self._prev_active_keys = set()
        self.guard = IntervalPositionGuard(stale_ttl_sec=180)
        self.config = copy.deepcopy(DEFAULT_CONFIG)
        self.strategy_threads = {}
        self.shared_binance = None
        self.stop_worker = None
        self.indicator_widgets = {}
        self.traded_symbols = set()
        self.init_ui()
        self.log_signal.connect(self._buffer_log)
        self.trade_signal.connect(self._on_trade_signal)

    def init_ui(self):
        self.setWindowTitle("Binance Trading Bot")
        try:
            asset_dir = Path(__file__).resolve().parent.parent / "assets"
            icon = QtGui.QIcon(str(asset_dir / "binance_icon.ico"))
            if icon.isNull():
                icon = QtGui.QIcon(str(asset_dir / "binance_icon.png"))
            if not icon.isNull():
                self.setWindowIcon(icon)
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

        grid.addWidget(QtWidgets.QLabel("Mode:"), 0, 2)
        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItems(["Live", "Demo/Testnet"])
        self.mode_combo.setCurrentText(self.config.get('mode', 'Live'))
        grid.addWidget(self.mode_combo, 0, 3)

        grid.addWidget(QtWidgets.QLabel("Theme:"), 0, 4)
        self.theme_combo = QtWidgets.QComboBox()
        self.theme_combo.addItems(["Light", "Dark"])
        self.theme_combo.setCurrentText("Dark")
        self.theme_combo.currentTextChanged.connect(self.apply_theme)
        grid.addWidget(self.theme_combo, 0, 5)

        grid.addWidget(QtWidgets.QLabel("Account Type:"), 1, 2)
        self.account_combo = QtWidgets.QComboBox()
        self.account_combo.addItems(["Spot", "Futures"])
        self.account_combo.setCurrentText(self.config.get('account_type', 'Futures'))
        grid.addWidget(self.account_combo, 1, 3)

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
        sgrid.addWidget(self.symbol_list, 1, 0, 4, 2)

        self.refresh_symbols_btn = QtWidgets.QPushButton("Refresh Symbols")
        self.refresh_symbols_btn.clicked.connect(self.refresh_symbols)
        sgrid.addWidget(self.refresh_symbols_btn, 5, 0, 1, 2)

        sgrid.addWidget(QtWidgets.QLabel("Intervals (select 1 or more):"), 0, 2)
        self.interval_list = QtWidgets.QListWidget()
        self.interval_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        for it in ["1s","1m","3m","5m","15m","30m","1h","2h","4h","6h","8h","12h","1d","3d","1w"]:
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
            for p in parts:
                if p not in existing:
                    self.interval_list.addItem(QtWidgets.QListWidgetItem(p))
            self.custom_interval_edit.clear()
        self.add_interval_btn.clicked.connect(_add_custom_intervals)
        sgrid.addWidget(self.custom_interval_edit, 4, 2)
        sgrid.addWidget(self.add_interval_btn, 4, 3)

        tab1_layout.addWidget(sym_group)

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

        tab1_layout.addWidget(strat_group)

        # Indicators
        ind_group = QtWidgets.QGroupBox("Indicators")
        il = QtWidgets.QGridLayout(ind_group)

        row = 0
        for key, params in self.config['indicators'].items():
            cb = QtWidgets.QCheckBox(key)
            cb.setChecked(bool(params.get("enabled", False)))
            btn = QtWidgets.QPushButton("Params...")
            def make_handler(_key=key, _params=params):
                def handler():
                    dlg = ParamDialog(_key, _params, self)
                    if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
                        self.config['indicators'][_key].update(dlg.get_params())
                        self.indicator_widgets[_key][0].setChecked(bool(self.config['indicators'][_key].get("enabled", False)))
                return handler
            btn.clicked.connect(make_handler())
            il.addWidget(cb, row, 0)
            il.addWidget(btn, row, 1)
            self.indicator_widgets[key] = (cb, btn)
            row += 1

        tab1_layout.addWidget(ind_group)

        # Buttons
        btn_layout = QtWidgets.QHBoxLayout()
        self.start_btn = QtWidgets.QPushButton("Start")
        self.start_btn.clicked.connect(self.start_strategy)
        btn_layout.addWidget(self.start_btn)
        self.stop_btn = QtWidgets.QPushButton("Stop")
        self.stop_btn.clicked.connect(self.stop_strategy_async)
        self.stop_btn.setEnabled(False)
        btn_layout.addWidget(self.stop_btn)
        self.save_btn = QtWidgets.QPushButton("Save Config")
        self.save_btn.clicked.connect(self.save_config)
        btn_layout.addWidget(self.save_btn)
        self.load_btn = QtWidgets.QPushButton("Load Config")
        self.load_btn.clicked.connect(self.load_config)
        btn_layout.addWidget(self.load_btn)
        tab1_layout.addLayout(btn_layout)

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


        # ---------------- Positions tab ----------------
        tab2 = QtWidgets.QWidget()
        tab2_layout = QtWidgets.QVBoxLayout(tab2)

        ctrl_layout = QtWidgets.QHBoxLayout()
        self.refresh_pos_btn = QtWidgets.QPushButton("Refresh Positions")
        top_row = QtWidgets.QHBoxLayout()
        top_row.addWidget(self.refresh_pos_btn, 1)
        tab2_layout.addLayout(top_row)
        self.refresh_pos_btn.clicked.connect(self.refresh_positions)
        ctrl_layout.addWidget(self.refresh_pos_btn)
        self.close_all_btn = QtWidgets.QPushButton("Market Close ALL Positions")
        self.close_all_btn.clicked.connect(self.close_all_positions_async)
        ctrl_layout.addWidget(self.close_all_btn)
        tab2_layout.addLayout(ctrl_layout)

        self.pos_table = QtWidgets.QTableWidget(0, 12, tab2)
        self.pos_table.setHorizontalHeaderLabels([
            "Symbol",
            "Balance/Position",
            "Last Price (USDT)",
            "Size (USDT)",
            "Margin Ratio",
            "Margin (USDT)",
            "PNL (ROI%)",
            "Entry TF",
            "Side",
            "Time",
            "Status",
            "Close",
        ])
        header = self.pos_table.horizontalHeader()
        header.setStretchLastSection(True)
        self.pos_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.pos_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        self.pos_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.pos_table.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.pos_table.verticalHeader().setVisible(False)
        tab2_layout.addWidget(self.pos_table)

        closed_label = QtWidgets.QLabel("Closed Positions (session)")
        closed_label.setStyleSheet("font-weight: bold;")
        tab2_layout.addWidget(closed_label)

        self.closed_pos_table = QtWidgets.QTableWidget(0, 9, tab2)
        self.closed_pos_table.setHorizontalHeaderLabels([
            "Symbol",
            "Side",
            "Interval",
            "Qty",
            "Size (USDT)",
            "Margin (USDT)",
            "PNL (ROI%)",
            "Entry Time",
            "Exit Time",
        ])
        self.closed_pos_table.horizontalHeader().setStretchLastSection(True)
        self.closed_pos_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        tab2_layout.addWidget(self.closed_pos_table)
        try:
            self._refresh_closed_history_table()
        except Exception:
            pass

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
        
        self._pos_thread.start()
        # adjust worker refresh interval
        try:
            self._apply_positions_refresh_settings()
        except Exception:
            pass


        

        self.resize(1200, 900)
        self.apply_theme(self.theme_combo.currentText())
        self._setup_log_buffer()
        try:
            self.ind_source_combo.currentTextChanged.connect(lambda v: self.config.__setitem__("indicator_source", v))
        except Exception:
            pass

    
    
    def _on_positions_ready(self, rows: list, acct: str):
        try:
            rows = rows or []

                except Exception:
                    continue
        except Exception as e:
            self.log(f"Positions render failed: {e}")
    def _refresh_closed_history_table(self):
        try:
            table = getattr(self, 'closed_pos_table', None)
            history = getattr(self, '_closed_positions_history', [])
            if table is None:
                return
            table.setRowCount(0)
            for entry in reversed(history):
                try:
                    row = table.rowCount()
                    table.insertRow(row)
                    symbol = entry.get('symbol') or '-'
                    side_txt = entry.get('side_text') or '-'
                    interval = entry.get('interval') if entry.get('interval') not in (None, '') else '-'
                    qty = float(entry.get('qty') or 0.0)
                    size_val = float(entry.get('size_usdt') or 0.0)
                    margin_val = float(entry.get('margin_usdt') or 0.0)
                    pnl = entry.get('pnl_roi') or '-'
                    entry_time = entry.get('entry_time') or '-'
                    exit_time = entry.get('exit_time') or '-'
                    table.setItem(row, 0, QtWidgets.QTableWidgetItem(symbol))
                    table.setItem(row, 1, QtWidgets.QTableWidgetItem(side_txt))
                    table.setItem(row, 2, QtWidgets.QTableWidgetItem(str(interval)))
                    table.setItem(row, 3, QtWidgets.QTableWidgetItem(f"{qty:.8f}"))
                    table.setItem(row, 4, QtWidgets.QTableWidgetItem(f"{size_val:.2f}"))
                    table.setItem(row, 5, QtWidgets.QTableWidgetItem(f"{margin_val:.2f}"))
                    table.setItem(row, 6, QtWidgets.QTableWidgetItem(str(pnl)))
                    table.setItem(row, 7, QtWidgets.QTableWidgetItem(str(entry_time)))
                    table.setItem(row, 8, QtWidgets.QTableWidgetItem(str(exit_time)))
                except Exception:
                    continue
        except Exception:
            pass

    def _record_closed_position(self, payload: dict):
        try:
            if not payload or not payload.get('symbol'):
                return
            entry = dict(payload)
            history = getattr(self, '_closed_positions_history', None)
            if history is None:
                self._closed_positions_history = []
                history = self._closed_positions_history
            side_key = str(entry.get('side_key') or '').upper()
            if side_key in ('L', 'LONG', 'BUY'):
                entry['side_key'] = 'L'
                entry['side_text'] = 'Long'
            elif side_key in ('S', 'SHORT', 'SELL'):
                entry['side_key'] = 'S'
                entry['side_text'] = 'Short'
            else:
                entry['side_text'] = entry.get('side_text') or '-'
            entry['interval'] = entry.get('interval') if entry.get('interval') not in (None, '') else '-'
            try:
                entry['qty'] = abs(float(entry.get('qty') or 0.0))
            except Exception:
                entry['qty'] = 0.0
            try:
                entry['size_usdt'] = float(entry.get('size_usdt') or 0.0)
            except Exception:
                entry['size_usdt'] = 0.0
            try:
                entry['margin_usdt'] = float(entry.get('margin_usdt') or 0.0)
            except Exception:
                entry['margin_usdt'] = 0.0
            if not entry.get('exit_time'):
                from datetime import datetime
                entry['exit_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            history.append(entry)
            limit = getattr(self, '_closed_history_limit', 0) or 0
            if limit and len(history) > limit:
                del history[:-limit]
            self._refresh_closed_history_table()
        except Exception:
            pass

    def _make_close_btn(self, symbol: str, side_key=None):
        btn = QtWidgets.QPushButton("Close")
        try:
            btn.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        except Exception:
            pass
        btn.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        btn.setProperty("symbol", symbol)
        btn.setProperty("side_key", side_key or "")
        btn.clicked.connect(lambda _, s=symbol, sk=side_key, b=btn: self._close_position_async(s, sk, b))
        return btn

    def _ensure_shared_binance(self):
        try:
            bw = getattr(self, "shared_binance", None)
            if bw is None:
                bw = BinanceWrapper(
                    self.api_key_edit.text().strip(),
                    self.api_secret_edit.text().strip(),
                    mode=self.mode_combo.currentText(),
                    account_type=self.account_combo.currentText(),
                    default_leverage=int(self.leverage_spin.value() or 1),
                    default_margin_mode=self.margin_mode_combo.currentText() or "Isolated",
                )
                self.shared_binance = bw
            return bw
        except Exception as e:
            try:
                self.log(f"Binance client init error: {e}")
            except Exception:
                pass
            self.shared_binance = None
            return None

    def _close_position_async(self, symbol: str, side_key=None, button=None):
        sym = (symbol or "").strip().upper()
        if not sym:
            return

        try:
            if button is not None:
                button.setEnabled(False)
                button.setText("Closing…")
        except Exception:
            pass

        bw = self._ensure_shared_binance()
        if bw is None:
            try:
                if button is not None:
                    button.setEnabled(True)
                    button.setText("Close")
            except Exception:
                pass
            return

        account = (self.account_combo.currentText() or "").upper()

        def _do():
            if account.startswith("FUT"):
                return bw.close_futures_position(sym)
            return {"ok": False, "error": f"Per-symbol close not supported for {account}"}

        def _done(res, err):
            try:
                if button is not None:
                    button.setEnabled(True)
                    button.setText("Close")
            except Exception:
                pass

            if err:
                self.log(f"Close {sym} error: {err}")
            else:
                result = res or {}
                if isinstance(result, dict) and result.get("ok"):
                    closed = result.get("closed")
                    msg = f"Close {sym} ok"
                    if closed is not None:
                        msg += f" (closed={closed})"
                    self.log(msg + ".")
                elif isinstance(result, dict):
                    errs = result.get("errors") or result.get("error")
                    self.log(f"Close {sym} failed: {errs}")
                else:
                    self.log(f"Close {sym} result: {result}")
            try:
                self.trigger_positions_refresh()
            except Exception:
                pass

        worker = CallWorker(_do, parent=self)
        try:
            worker.progress.connect(self.log)
        except Exception:
            pass
        worker.done.connect(_done)
        if not hasattr(self, "_bg_workers"):
            self._bg_workers = []
        self._bg_workers.append(worker)

        def _cleanup():
            try:
                self._bg_workers.remove(worker)
            except Exception:
                pass

        worker.finished.connect(_cleanup)
        worker.start()
    def _reconfigure_positions_worker(self):
        try:
            if not hasattr(self, '_pos_worker') or self._pos_worker is None:
                return
            syms = [self.symbol_list.item(i).text() for i in range(self.symbol_list.count())] if self.symbol_list.count() else None
            self._pos_worker.configure(
                api_key=self.api_key_edit.text().strip(),
                api_secret=self.api_secret_edit.text().strip(),
                mode=self.mode_combo.currentText(),
                account_type=self.account_combo.currentText(),
                symbols=syms
            )
            self._apply_positions_refresh_settings()
        except Exception:
            pass

    # --------- buffered logging (prevents UI stalls) ---------
    def _setup_log_buffer(self):
        from collections import deque
        self._log_buf = deque(maxlen=8000)
        self._log_timer = QtCore.QTimer(self)
        self._log_timer.setInterval(200)  # flush every 200ms
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
            # Limit per-flush batch to 300 lines to avoid UI jank
            for _ in range(300):
                if not self._log_buf:
                    break
                lines.append(self._log_buf.popleft())
            if not lines:
                return
            ts = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
            # join with timestamps per line to keep format similar
            text = "\n".join(f"[{ts}] {m}" for m in lines)
            try:
                self.log_edit.appendPlainText(text)
            except Exception:
                # fallback if widget type changed
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

    
    
    def _apply_positions_refresh_settings(self):
        try:
            self.req_pos_start.emit(5000)
        except Exception:
            pass

    def apply_theme(self, name: str):
        self.setStyleSheet(self.DARK_THEME if name.lower().startswith("dark") else self.LIGHT_THEME)

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
        if sym and interval and side:
            side_key = 'L' if str(side).upper() in ('BUY','LONG') else 'S'
            self._entry_intervals.setdefault(sym, {'L': set(), 'S': set()})
            self._entry_intervals[sym][side_key].add(interval)
            tstr = order_info.get('time')
            if tstr:
                self._entry_times[(sym, side_key)] = tstr
            else:
                from datetime import datetime
                tstr = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                self._entry_times[(sym, side_key)] = tstr
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
    try:
        # Loop Interval Override from UI (e.g., "10s", "2m", "1h", "1d", "1w"). Empty = use candle interval.
        raw_override = (self.loop_edit.text().strip() if hasattr(self, 'loop_edit') else '')
        loop_override = re.sub(r'\s+', '', raw_override.lower()) if raw_override else None
        if loop_override and not re.match(r'^\d+(s|m|h|d|w)?$', loop_override):
            self.log(f"Invalid loop interval override: {raw_override}. Use formats like '10s', '2m', '1h'. Ignoring.")
            loop_override = None

        syms = [self.symbol_list.item(i).text() for i in range(self.symbol_list.count())
                if self.symbol_list.item(i).isSelected()]
        if not syms and self.symbol_list.count():
            syms = [self.symbol_list.item(i).text() for i in range(self.symbol_list.count())]

        ivs = [self.interval_list.item(i).text() for i in range(self.interval_list.count())
               if self.interval_list.item(i).isSelected()]
        if not ivs:
            ivs = ["1m"]

        if not syms:
            self.log("No symbols available. Click Refresh Symbols.")
            return

        if getattr(self, "shared_binance", None) is None:
            self.shared_binance = BinanceWrapper(
                self.api_key_edit.text().strip(), self.api_secret_edit.text().strip(),
                mode=self.mode_combo.currentText(), account_type=self.account_combo.currentText(),
                default_leverage=int(self.leverage_spin.value() or 1),
                default_margin_mode=self.margin_mode_combo.currentText() or "Isolated"
            )

        if not hasattr(self, "strategy_engines"):
            self.strategy_engines = {}

        started = 0
        for sym in syms:
            for iv in ivs:
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
        try:
            self.start_btn.setEnabled(False); self.stop_btn.setEnabled(True)
        except Exception:
            pass
    except Exception as e:
        try:
            self.log(f"Start error: {e}")
        except Exception:
            pass


def stop_strategy_async(self):
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
        try:
            self.start_btn.setEnabled(True); self.stop_btn.setEnabled(False)
        except Exception:
            pass

        # 2) Then close all open positions in background (non-blocking)
        try:
            self.close_all_positions_async()
        except Exception as e:
            try: self.log(f"Failed to trigger close-all: {e}")
            except Exception: pass

    except Exception as e:
        try: self.log(f"Stop error: {e}")
        except Exception: pass

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
                try:
                    self.trigger_positions_refresh()
                except Exception:
                    pass
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
                try:
                    self.trigger_positions_refresh()
                except Exception:
                    pass
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
            self.balance_label.setText(f"Total USDT balance: {bal:.3f} USDT")
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
            self.stop_strategy_async()
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
