"""Explicit selected-account recovery of durable desktop Spot BUY work."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from PyQt6 import QtCore, QtWidgets

from app.gui.runtime.background_workers import CallWorker
from app.gui.shared import allocation_persistence
from app.gui.shared.allocation_persistence import AllocationSnapshotSession
from app.security.redaction import REDACTED_TEXT, redact_text
from app.settings.live_safety import LiveTradingSafetyError

_RECOVERY_UI_ERRORS = (
    LiveTradingSafetyError, OSError, ValueError, TypeError, AttributeError,
    KeyError, OverflowError, ArithmeticError, RuntimeError,
)


def _allocation_path() -> Path:
    return cast(Path, allocation_persistence.get_position_allocations_path(
        Path(__file__).resolve().parents[2] / "window_shell.py",
    ))


def _discover(wrapper: Any, allocation_path: Path) -> Any:
    from app.integrations.exchanges.binance.orders.spot_desktop_buy_recovery_runtime import (
        discover_spot_desktop_buy_recoveries,
    )
    return discover_spot_desktop_buy_recoveries(wrapper, allocation_path=allocation_path)


def _capture_loaded(window: Any, allocation_path: Path) -> Any:
    from app.integrations.exchanges.binance.orders.spot_desktop_buy_recovery_runtime import (
        capture_spot_desktop_buy_recovery_source,
    )
    return capture_spot_desktop_buy_recovery_source(
        window._allocation_snapshot_session, window._entry_allocations, window._open_position_records,
        allocation_path=allocation_path,
    )


def _recover(wrapper: Any, item: Any, *, allocation_path: Path, receipt: Any, handoff: Any) -> dict:
    from app.integrations.exchanges.binance.orders.spot_desktop_buy_recovery_runtime import (
        recover_spot_desktop_buy,
    )
    return cast(dict, recover_spot_desktop_buy(
        wrapper, item, allocation_path=allocation_path, expected_loaded_receipt=receipt,
        publication_handoff=handoff,
    ))


def _selected_scope(window: Any) -> tuple:
    """UI-thread capture only; credentials never appear in recovery messages."""
    auth = window._snapshot_auth_state()
    backend = window._runtime_connector_backend(suppress_refresh=True)
    return (auth.get("api_key"), auth.get("api_secret"), auth.get("mode"), auth.get("account_type"), backend)


@dataclass(frozen=True, repr=False)
class _RecoveryToken:
    window: Any = field(repr=False)
    wrapper: Any = field(repr=False)
    session: AllocationSnapshotSession = field(repr=False)
    account_generation: int
    recovery_generation: int
    session_generation: int
    allocations: dict = field(repr=False)
    records: dict = field(repr=False)
    scope: tuple = field(repr=False)

    def matches_selection(self) -> bool:
        window = self.window
        return (
            getattr(window, "shared_binance", None) is self.wrapper
            and getattr(window, "_allocation_snapshot_session", None) is self.session
            and getattr(window, "_account_observation_generation", 0) == self.account_generation
            and getattr(window, "_spot_buy_recovery_generation", 0) == self.recovery_generation
        )

    def matches_context(self) -> bool:
        return (
            self.matches_selection() and getattr(self.window, "_entry_allocations", None) is self.allocations
            and getattr(self.window, "_open_position_records", None) is self.records
        )

    @contextmanager
    def publication_handoff(self):
        """Called after paired storage locks; never read Qt or acquire storage here."""
        with self.session._mutex:
            if (
                not self.matches_context() or self.session._generation != self.session_generation
                or not self.session.matches_loaded_maps(self.allocations, self.records)
            ):
                raise LiveTradingSafetyError("Selected account or loaded allocation maps changed before recovery.")
            yield


class SpotBuyRecoveryDialog(QtWidgets.QDialog):
    def __init__(self, window: Any):
        super().__init__(window)
        self._window: Any = window
        self._worker: Any = None
        self._after_worker: Any = None
        self._discovery: Any = None
        self._token: _RecoveryToken | None = None
        self._errors: dict[str, str] = {}
        self._credential_values: set[str] = set()
        self.setWindowTitle("Spot BUY Recovery")
        self.resize(900, 360)
        layout = QtWidgets.QVBoxLayout(self)
        description = QtWidgets.QLabel(
            "Recover local portfolio records for existing Live Spot MARKET BUY fills. "
            "Stop the strategy first. Recovery does not place an order or restart trading."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        self.count_label = QtWidgets.QLabel("Durable unresolved work: not checked")
        layout.addWidget(self.count_label)
        self.table = QtWidgets.QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Client order ID", "Symbol", "Order ID", "Exchange status", "Recovery error"])
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        header = self.table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
            header.setStretchLastSection(True)
        layout.addWidget(self.table)
        self.status_label = QtWidgets.QLabel("Select Live / Spot, then discover durable work for that account.")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        buttons = QtWidgets.QHBoxLayout()
        self.discover_btn = QtWidgets.QPushButton("Discover / Recheck")
        self.discover_btn.clicked.connect(self.discover)
        buttons.addWidget(self.discover_btn)
        self.recover_btn = QtWidgets.QPushButton("Recover Selected")
        self.recover_btn.clicked.connect(self.recover_selected)
        self.recover_btn.setEnabled(False)
        buttons.addWidget(self.recover_btn)
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.close)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)
        for name, signal in (
            ("api_key_edit", "textChanged"), ("api_secret_edit", "textChanged"),
            ("mode_combo", "currentTextChanged"), ("account_combo", "currentTextChanged"),
            ("connector_combo", "currentIndexChanged"),
        ):
            getattr(getattr(window, name), signal).connect(self._invalidate_scope)
        window.installEventFilter(self)

    def eventFilter(self, watched, event):
        if watched is self._window and event.type() == QtCore.QEvent.Type.Close:
            self._invalidate_scope()
            if self._worker is not None:
                self.status_label.setText("Account recovery is running. Close the window after it finishes.")
                event.ignore()
                return True
        return super().eventFilter(watched, event)

    def _invalidate_scope(self, *_args) -> None:
        session = getattr(self._window, "_allocation_snapshot_session", None)
        if isinstance(session, AllocationSnapshotSession):
            with session._mutex:
                self._window._spot_buy_recovery_generation = getattr(self._window, "_spot_buy_recovery_generation", 0) + 1
                session.invalidate("selected account changed during Spot BUY recovery")
        else:
            self._window._spot_buy_recovery_generation = getattr(self._window, "_spot_buy_recovery_generation", 0) + 1
        self._window._spot_buy_recovery_fence = True
        self._discovery = None
        self.recover_btn.setEnabled(False)
        self.status_label.setText("Account or window changed. Discover again; new exposure remains blocked.")

    def _capture_token(self, wrapper: Any, scope: tuple) -> _RecoveryToken:
        session = getattr(self._window, "_allocation_snapshot_session", None)
        if not isinstance(session, AllocationSnapshotSession):
            raise LiveTradingSafetyError("Desktop allocation session is unavailable.")
        return _RecoveryToken(
            self._window, wrapper, session, getattr(self._window, "_account_observation_generation", 0),
            getattr(self._window, "_spot_buy_recovery_generation", 0), session._capture()[5],
            self._window._entry_allocations, self._window._open_position_records, scope,
        )

    def _current(self, token: _RecoveryToken, *, generation: int | None = None) -> bool:
        return (
            token.matches_context() and _selected_scope(self._window) == token.scope
            and token.session._capture()[5] == (token.session_generation if generation is None else generation)
        )

    def _fail(self, error: object, *, client_order_id: str | None = None) -> None:
        self._window._spot_buy_recovery_fence = True
        message = redact_text(error).replace("\n", " ")[:1200]
        for value in sorted(self._credential_values, key=len, reverse=True):
            if value:
                message = message.replace(value, REDACTED_TEXT)
        self.status_label.setText(f"Recovery blocked: {message}")
        if client_order_id is not None:
            self._errors[client_order_id] = message
            self._render_items()

    def _run(self, fn, finished) -> None:
        self.discover_btn.setEnabled(False)
        self.recover_btn.setEnabled(False)
        worker = CallWorker(fn, parent=self._window)
        self._worker = worker
        worker.done.connect(finished)
        worker.finished.connect(lambda: self._worker_finished(worker))
        # CallWorker.progress includes a traceback; expose only redacted done errors.
        worker.start()

    def _worker_finished(self, worker) -> None:
        if self._worker is not worker:
            return
        self._worker = None
        worker.deleteLater()
        self.discover_btn.setEnabled(True)
        self.recover_btn.setEnabled(
            self._discovery is not None and bool(self._discovery.items)
            and self._token is not None and self._current(self._token) and self._token.session.ready
        )
        after, self._after_worker = self._after_worker, None
        if after is not None:
            after()

    def discover(self, *_args) -> None:
        if self._worker is not None:
            return
        self._window._spot_buy_recovery_fence = True
        self._discovery = None
        try:
            scope = _selected_scope(self._window)
            self._credential_values.update(value for value in scope[:2] if isinstance(value, str) and value)
            if scope[2:4] != ("Live", "Spot"):
                raise LiveTradingSafetyError("Recovery requires the selected Live Spot account.")
            if getattr(self._window, "strategy_engines", None):
                raise LiveTradingSafetyError("Stop the strategy before recovery; restart if execution ownership remains held.")
            wrapper = getattr(self._window, "shared_binance", None)
            if wrapper is None:
                auth = self._window._snapshot_auth_state()
                wrapper = self._window._create_binance_wrapper(
                    api_key=auth["api_key"], api_secret=auth["api_secret"], mode=auth["mode"],
                    account_type=auth["account_type"], connector_backend=scope[4],
                )
                self._window.shared_binance = wrapper
            elif (wrapper.api_key, wrapper.api_secret, wrapper.mode, str(wrapper.account_type).title()) != scope[:4]:
                raise LiveTradingSafetyError("Shared exchange wrapper differs from the selected account. Refresh the account first.")
            token = self._capture_token(wrapper, scope)
            path = _allocation_path()
        except _RECOVERY_UI_ERRORS as exc:
            self._fail(exc)
            return
        self.status_label.setText("Verifying the selected account and reading durable recovery work...")

        def done(result, error):
            if error is not None:
                self._fail(error)
                return
            if not self._current(token) or result.authority.wrapper is not wrapper:
                self._fail("Selected account or allocation source changed during discovery. Discover again.")
                return
            if self._window._reload_position_allocation_snapshot("Live") is not True:
                self._fail("Verified account allocation reload failed. New exposure remains blocked.")
                return
            if not token.matches_selection() or _selected_scope(self._window) != scope:
                self._fail("Selected account changed during allocation reload. Discover again.")
                return
            try:
                self._token = self._capture_token(wrapper, scope)
                _capture_loaded(self._window, path)
            except _RECOVERY_UI_ERRORS as exc:
                self._fail(exc)
                return
            self._discovery = result
            self._render_items()
            self._window._spot_buy_recovery_fence = result.unresolved_count > 0 or result.unsupported_count > 0
            self.status_label.setText(
                "Exact recovery is available for the listed BUY fills."
                if result.items else "No eligible BUY fills. Unsupported work requires operator recovery."
                if result.unsupported_count else "No durable unresolved work for the verified account."
            )

        self._run(lambda: _discover(wrapper, path), done)

    def _render_items(self) -> None:
        if self._discovery is None:
            return
        result = self._discovery
        self.count_label.setText(
            f"Verified account: {result.authority.account_uid} ({result.authority.environment}); "
            f"durable unresolved work: {result.unresolved_count}; eligible BUY fills: {len(result.items)}; "
            f"operator recovery required: {result.unsupported_count}"
        )
        self.table.setRowCount(len(result.items))
        for row, item in enumerate(result.items):
            values = (item.client_order_id, item.symbol, str(item.order_id), item.exchange_status,
                      self._errors.get(item.client_order_id, ""))
            for column, value in enumerate(values):
                self.table.setItem(row, column, QtWidgets.QTableWidgetItem(value))
        if result.items:
            self.table.selectRow(0)

    def recover_selected(self, *_args) -> None:
        if self._worker is not None or self._discovery is None or self._token is None:
            return
        row = self.table.currentRow()
        if not 0 <= row < len(self._discovery.items):
            self._fail("Select a recovery item first.")
            return
        item = self._discovery.items[row]
        token = self._token
        self._window._spot_buy_recovery_fence = True
        try:
            if not self._current(token):
                raise LiveTradingSafetyError("Selected account or loaded allocation source changed. Discover again.")
            path = _allocation_path()
            receipt = _capture_loaded(self._window, path)
        except _RECOVERY_UI_ERRORS as exc:
            self._fail(exc, client_order_id=item.client_order_id)
            return
        self.status_label.setText(f"Recovering existing order {item.order_id}...")

        def done(result, error):
            if error is not None:
                self._fail(error, client_order_id=item.client_order_id)
                return
            if result.get("portfolio_reconciled") is not True:
                self._fail(result.get("error") or "Allocation publication is pending its durable marker; recheck to retry.",
                           client_order_id=item.client_order_id)
                return
            authority = item.authority
            if (
                not self._current(token, generation=result.get("session_generation"))
                or result.get("client_order_id") != item.client_order_id
                or (result.get("account_uid"), result.get("environment"), result.get("store_id"))
                != (authority.account_uid, authority.environment, authority.store_id)
            ):
                self._fail("Account or allocation source changed after recovery. Discover again before loading maps.",
                           client_order_id=item.client_order_id)
                return
            if self._window._reload_position_allocation_snapshot("Live") is not True:
                self._fail("Durable recovery succeeded; desktop allocation reload failed. Recheck before new exposure.",
                           client_order_id=item.client_order_id)
                return
            loaded = token.session._capture()
            if (
                not token.matches_selection() or _selected_scope(self._window) != token.scope
                or (loaded[2], loaded[3]) != result.get("allocation_receipt")
            ):
                token.session.invalidate("allocation storage changed after desktop BUY recovery")
                self._fail("Allocation storage changed after recovery. Discover again before new exposure.",
                           client_order_id=item.client_order_id)
                return
            self._errors.pop(item.client_order_id, None)
            self._discovery = None
            self._token = None
            self.status_label.setText("Portfolio recovered and reloaded. Rechecking durable unresolved work...")
            self._after_worker = self.discover

        self._run(lambda: _recover(token.wrapper, item, allocation_path=path, receipt=receipt,
                                   handoff=token.publication_handoff), done)

    def closeEvent(self, event):
        if self._worker is not None:
            self.status_label.setText("Recovery is running. Keep this view open until it completes.")
            event.ignore()
            return
        event.accept()


def open_spot_buy_recovery(window: Any) -> SpotBuyRecoveryDialog:
    dialog = getattr(window, "_spot_buy_recovery_dialog", None)
    if not isinstance(dialog, SpotBuyRecoveryDialog):
        dialog = SpotBuyRecoveryDialog(window)
        window._spot_buy_recovery_dialog = dialog
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    return dialog
