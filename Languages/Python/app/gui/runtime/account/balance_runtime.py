from __future__ import annotations

import math
import os
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from PyQt6 import QtCore

from app.security.redaction import redact_text
from app.service.schemas.observation import observation_scope

_NORMALIZE_CONNECTOR_BACKEND = None


def _record_balance_runtime_exception(self, context: str, exc: BaseException) -> None:  # noqa: ANN001
    message = redact_text(exc).replace("\n", " ")
    entry = f"balance runtime suppressed exception context={context} error={type(exc).__name__}: {message}"
    fallback_needed = True
    try:
        logger = getattr(self, "_chart_debug_log", None)
        if callable(logger):
            logger(entry)
            fallback_needed = False
    except Exception:
        fallback_needed = True
    if not fallback_needed:
        return
    try:
        log_dir = Path(os.environ.get("TEMP") or os.environ.get("TMP") or os.getcwd())
        timestamp = datetime.now().isoformat(timespec="seconds")
        with (log_dir / "binance_chart_debug.log").open("a", encoding="utf-8") as handle:
            handle.write(f"{timestamp} {entry}\n")
    except Exception:
        return


def _normalize_connector_backend_safe(value) -> str | None:
    func = _NORMALIZE_CONNECTOR_BACKEND
    if not callable(func):
        return None
    try:
        return func(value)
    except Exception:
        return None


def _balance_request_scope(self) -> tuple:
    config = getattr(self, "config", {})
    connector = getattr(self, "connector_combo", None)
    connector_value = None
    if connector is not None:
        connector_value = connector.currentData()
        if connector_value is None:
            connector_value = connector.currentText()
    # Credential-bearing identity stays in memory and must never be logged.
    return (
        observation_scope(config if isinstance(config, dict) else {}),
        getattr(self, "_service_observation_generation", 0),
        getattr(self, "_account_observation_generation", 0),
        self.api_key_edit.text().strip(), self.api_secret_edit.text().strip(),
        self.mode_combo.currentText(), self.account_combo.currentText(), connector_value,
    )


def _balance_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError(f"Balance {field} is unavailable or invalid")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"Balance {field} is unavailable or invalid") from exc
    if not math.isfinite(number) or number < 0.0:
        raise ValueError(f"Balance {field} must be finite and non-negative")
    return number


def _invalidate_balance_observation(self, *, clear_values: bool = False) -> None:
    snapshot = getattr(self, "_positions_balance_snapshot", None)
    self._positions_balance_snapshot = (
        {**snapshot, "observed_at": ""} if isinstance(snapshot, dict) and not clear_values else {}
    )
    self._update_positions_balance_labels(None, None)


def bind_main_window_balance_runtime(
    main_window_cls,
    *,
    normalize_connector_backend=None,
) -> None:
    global _NORMALIZE_CONNECTOR_BACKEND

    _NORMALIZE_CONNECTOR_BACKEND = normalize_connector_backend
    main_window_cls.update_balance_label = update_balance_label


def update_balance_label(self):
    """Refresh the 'Total USDT balance' label safely after an order."""
    from app.gui.runtime.background_workers import CallWorker as _CallWorker

    btn = getattr(self, "refresh_balance_btn", None)
    old_btn_text = btn.text() if btn else None
    refresh_token = time.monotonic()
    try:
        self._balance_refresh_token = refresh_token
    except Exception as exc:
        _record_balance_runtime_exception(self, "set_balance_refresh_token", exc)
    if btn:
        try:
            btn.setEnabled(False)
            btn.setText("Refreshing...")
        except Exception as exc:
            _record_balance_runtime_exception(self, "balance_refresh_button_start", exc)
    try:
        if getattr(self, "balance_label", None):
            self.balance_label.setText("Refreshing...")
    except Exception as exc:
        _record_balance_runtime_exception(self, "balance_label_refreshing", exc)

    try:
        api_key = (self.api_key_edit.text() or "").strip()
        api_secret = (self.api_secret_edit.text() or "").strip()
    except Exception as exc:
        _record_balance_runtime_exception(self, "read_api_credentials", exc)
        api_key = ""
        api_secret = ""
    try:
        mode_value = getattr(self.mode_combo, "currentText", lambda: "Live")()
    except Exception as exc:
        _record_balance_runtime_exception(self, "read_mode_value", exc)
        mode_value = "Live"
    try:
        account_value = getattr(self.account_combo, "currentText", lambda: "Futures")()
    except Exception as exc:
        _record_balance_runtime_exception(self, "read_account_value", exc)
        account_value = "Futures"
    try:
        default_leverage = int(self.leverage_spin.value() or 1)
    except Exception as exc:
        _record_balance_runtime_exception(self, "read_default_leverage", exc)
        default_leverage = 1
    try:
        default_margin_mode = self.margin_mode_combo.currentText() or "Isolated"
    except Exception as exc:
        _record_balance_runtime_exception(self, "read_default_margin_mode", exc)
        default_margin_mode = "Isolated"
    try:
        connector_raw = None
        if hasattr(self, "connector_combo") and self.connector_combo is not None:
            connector_raw = self.connector_combo.currentData()
            if connector_raw is None:
                connector_raw = self.connector_combo.currentText()
        connector_backend = _normalize_connector_backend_safe(connector_raw)
    except Exception as exc:
        _record_balance_runtime_exception(self, "read_connector_backend", exc)
        connector_backend = None

    if not api_key or not api_secret:
        if getattr(self, "balance_label", None):
            self.balance_label.setText("API credentials missing")
        _invalidate_balance_observation(self, clear_values=True)
        try:
            self._balance_refresh_token = None
        except Exception as exc:
            _record_balance_runtime_exception(self, "clear_missing_credentials_refresh_token", exc)
        if btn:
            try:
                btn.setEnabled(True)
                if old_btn_text is not None:
                    btn.setText(old_btn_text)
            except Exception as exc:
                _record_balance_runtime_exception(self, "missing_credentials_button_restore", exc)
        return

    try:
        request_scope = _balance_request_scope(self)
    except Exception as exc:
        _record_balance_runtime_exception(self, "capture_balance_request_scope", exc)
        self._balance_refresh_token = None
        _invalidate_balance_observation(self, clear_values=True)
        if btn:
            btn.setEnabled(True)
            if old_btn_text is not None:
                btn.setText(old_btn_text)
        return

    wrapper_holder: dict[str, object | None] = {"wrapper": None}

    def _do():
        wrapper = getattr(self, "shared_binance", None)
        try:
            needs_rebuild = True
            if wrapper is not None:
                try:
                    needs_rebuild = (
                        str(getattr(wrapper, "api_key", "") or "") != api_key
                        or str(getattr(wrapper, "api_secret", "") or "") != api_secret
                        or str(getattr(wrapper, "mode", "") or "") != str(mode_value or "")
                        or str(getattr(wrapper, "account_type", "") or "").upper()
                        != str(account_value or "").strip().upper()
                        or (
                            connector_backend is not None
                            and str(getattr(wrapper, "_connector_backend", "") or "")
                            != str(connector_backend or "")
                        )
                    )
                except Exception as exc:
                    needs_rebuild = True
                    _record_balance_runtime_exception(self, "compare_existing_wrapper", exc)
            if wrapper is None or needs_rebuild:
                wrapper = self._create_binance_wrapper(
                    api_key=api_key,
                    api_secret=api_secret,
                    mode=mode_value,
                    account_type=account_value,
                    connector_backend=connector_backend,
                    default_leverage=default_leverage,
                    default_margin_mode=default_margin_mode,
                )
            try:
                wrapper_holder["wrapper"] = wrapper
            except Exception as exc:
                _record_balance_runtime_exception(self, "store_balance_wrapper_holder", exc)
            total_balance_value = None
            available_balance_value = None
            bal = 0.0
            acct_upper = str(account_value or "").upper()
            observed_at = datetime.now(timezone.utc).isoformat()
            if acct_upper == "FUTURES":
                snap = wrapper.get_futures_balance_snapshot(force_refresh=True)
                if not isinstance(snap, dict):
                    raise RuntimeError(f"Unexpected futures balance snapshot type: {type(snap).__name__}")
                total_balance_value = _balance_number(snap.get("total", snap.get("wallet")), "total")
                available_balance_value = _balance_number(snap.get("available"), "available")
                if "wallet" in snap:
                    _balance_number(snap["wallet"], "wallet")
                bal = available_balance_value if available_balance_value > 0.0 else total_balance_value
            elif acct_upper == "SPOT":
                bal = _balance_number(wrapper.get_spot_balance("USDT"), "available")
                total_balance_value = _balance_number(wrapper.get_total_usdt_value(force_refresh=True), "total")
                available_balance_value = bal
            else:
                raise ValueError("Balance account type is unsupported")
            if available_balance_value > total_balance_value:
                raise ValueError("Available balance exceeds total balance")
            return {
                "total": total_balance_value, "available": available_balance_value,
                "bal": bal, "wrapper": wrapper, "observed_at": observed_at,
            }
        except Exception as exc:
            return {"error": redact_text(exc), "wrapper": wrapper}

    def _done(res, err):
        if getattr(self, "_balance_refresh_token", None) != refresh_token:
            return
        try:
            scope_matches = _balance_request_scope(self) == request_scope
        except Exception:
            scope_matches = False
        try:
            self._balance_refresh_token = None
        except Exception as exc:
            _record_balance_runtime_exception(self, "done_clear_balance_refresh_token", exc)
        try:
            if getattr(self, "_balance_refresh_worker", None) is worker:
                self._balance_refresh_worker = None
        except Exception as exc:
            _record_balance_runtime_exception(self, "done_clear_balance_worker", exc)
        if not scope_matches:
            _invalidate_balance_observation(self, clear_values=True)
            if btn:
                btn.setEnabled(True)
                if old_btn_text is not None:
                    btn.setText(old_btn_text)
            return
        total_balance_value = None
        available_balance_value = None
        err_msg = None
        if err:
            err_msg = str(err)
        elif isinstance(res, dict) and res.get("error"):
            err_msg = str(res.get("error"))
        if err_msg or not res:
            try:
                wrapper_obj = wrapper_holder.get("wrapper")
                if wrapper_obj is not None:
                    self.shared_binance = wrapper_obj
            except Exception as exc:
                _record_balance_runtime_exception(self, "error_store_shared_wrapper", exc)
            try:
                self.log(f"Balance error: {err_msg or 'unknown error'}")
            except Exception as exc:
                _record_balance_runtime_exception(self, "log_balance_error", exc)
            try:
                if getattr(self, "balance_label", None):
                    msg = str(err_msg or "unknown error").replace("\n", " ").strip()
                    try:
                        self.balance_label.setToolTip(msg)
                    except Exception as exc:
                        _record_balance_runtime_exception(self, "balance_error_tooltip", exc)
                    label_text = None
                    try:
                        m = re.search(r"\bcode=([-]?[0-9]+)\b", msg)
                        code_val = int(m.group(1)) if m else None
                    except Exception as exc:
                        _record_balance_runtime_exception(self, "parse_balance_error_code", exc)
                        code_val = None
                    if code_val in (-2014, -2015):
                        mode_txt = str(mode_value or "").lower()
                        is_test = ("test" in mode_txt) or ("demo" in mode_txt) or ("sandbox" in mode_txt)
                        acct_txt = str(account_value or "").upper()
                        if acct_txt.startswith("FUT") and is_test:
                            if ("Spot Testnet keys" in msg) or ("accepted on Spot Testnet" in msg):
                                label_text = (
                                    f"Wrong API key for Futures Testnet (code {code_val}). "
                                    "Use FUTURES Testnet keys."
                                )
                            elif ("rejected by both Spot/Futures Testnet" in msg) or (
                                "rejected by both Spot and Futures Testnet" in msg
                            ):
                                label_text = (
                                    f"API key rejected by Testnet (code {code_val}). "
                                    "Check permissions/IP."
                                )
                            else:
                                label_text = (
                                    f"Futures Testnet key rejected (code {code_val}). "
                                    "Check permissions/IP: testnet.binancefuture.com (see Log)."
                                )
                                try:
                                    now_ts = float(time.time())
                                    last_ts = float(getattr(self, "_last_auth_help_ts", 0.0) or 0.0)
                                    if (now_ts - last_ts) > 60.0:
                                        self._last_auth_help_ts = now_ts
                                        self.log("Futures Testnet auth error (-2015/-2014). Checklist:")
                                        self.log(
                                            "1) Use FUTURES Testnet keys from https://testnet.binancefuture.com (not Spot Testnet / live)."
                                        )
                                        self.log(
                                            "2) In API Key settings enable Futures + Reading; disable IP restriction or whitelist your IP."
                                        )
                                        self.log(
                                            "3) If using VPN, your public IP changes; whitelist the current one."
                                        )
                                        try:
                                            ip = None
                                            with urllib.request.urlopen("https://api.ipify.org", timeout=5) as resp:
                                                ip = (resp.read(64) or b"").decode("utf-8", "ignore").strip()
                                            if ip and re.match(r"^[0-9]{1,3}(\.[0-9]{1,3}){3}$", ip):
                                                self.log(f"Detected public IP: {ip}")
                                        except Exception as exc:
                                            _record_balance_runtime_exception(self, "public_ip_lookup", exc)
                                except Exception as exc:
                                    _record_balance_runtime_exception(self, "write_futures_auth_help", exc)
                        elif is_test:
                            label_text = (
                                f"Testnet key rejected (code {code_val}). "
                                "Spot keys: testnet.binance.vision (see Log)."
                            )
                        else:
                            label_text = f"API key rejected (code {code_val}). Check permissions/IP (see Log)."
                    if label_text is None:
                        short = msg if len(msg) <= 120 else (msg[:117] + "...")
                        label_text = f"Balance error: {short}"
                    self.balance_label.setText(label_text)
            except Exception as exc:
                _record_balance_runtime_exception(self, "apply_balance_error_label", exc)
            _invalidate_balance_observation(self)
        else:
            total_balance_value = res.get("total")
            available_balance_value = res.get("available")
            bal = res.get("bal", 0.0)
            try:
                wrapper_obj = res.get("wrapper")
                if wrapper_obj is not None:
                    self.shared_binance = wrapper_obj
            except Exception as exc:
                _record_balance_runtime_exception(self, "success_store_shared_wrapper", exc)
            try:
                if getattr(self, "balance_label", None):
                    try:
                        self.balance_label.setToolTip("")
                    except Exception as exc:
                        _record_balance_runtime_exception(self, "clear_balance_tooltip", exc)
                    total_txt = f"{(total_balance_value if total_balance_value is not None else bal):.3f}"
                    avail_txt = f"{(available_balance_value if available_balance_value is not None else bal):.3f}"
                    if abs(float(total_txt) - float(avail_txt)) > 1e-6:
                        self.balance_label.setText(f"Total {total_txt} USDT | Available {avail_txt} USDT")
                    else:
                        self.balance_label.setText(f"{total_txt} USDT")
            except Exception as exc:
                _record_balance_runtime_exception(self, "apply_balance_success_label", exc)
            try:
                self._update_positions_balance_labels(
                    total_balance_value, available_balance_value, observed_at=str(res.get("observed_at") or ""),
                )
            except Exception as exc:
                _record_balance_runtime_exception(self, "update_positions_balance_success", exc)
        if btn:
            try:
                btn.setEnabled(True)
                if old_btn_text is not None:
                    btn.setText(old_btn_text)
            except Exception as exc:
                _record_balance_runtime_exception(self, "done_button_restore", exc)

    worker = _CallWorker(_do, parent=self)
    try:
        self._balance_refresh_worker = worker
    except Exception as exc:
        _record_balance_runtime_exception(self, "store_balance_worker", exc)
    try:
        worker.progress.connect(self.log)
    except Exception as exc:
        _record_balance_runtime_exception(self, "connect_balance_progress", exc)
    worker.done.connect(_done)
    worker.start()

    def _watchdog(expected_token: float):
        if getattr(self, "_balance_refresh_token", None) != expected_token:
            return
        try:
            running = bool(worker.isRunning())
        except Exception as exc:
            _record_balance_runtime_exception(self, "balance_watchdog_worker_running", exc)
            running = False
        if not running:
            return
        try:
            self._balance_refresh_token = None
        except Exception as exc:
            _record_balance_runtime_exception(self, "watchdog_clear_balance_refresh_token", exc)
        try:
            self._balance_refresh_worker = None
        except Exception as exc:
            _record_balance_runtime_exception(self, "watchdog_clear_balance_worker", exc)
        try:
            self.log("Balance refresh timed out; please check testnet connectivity/credentials and try again.")
        except Exception as exc:
            _record_balance_runtime_exception(self, "watchdog_log_timeout", exc)
        try:
            if getattr(self, "balance_label", None):
                self.balance_label.setText("Balance timeout")
        except Exception as exc:
            _record_balance_runtime_exception(self, "watchdog_balance_timeout_label", exc)
        try:
            try:
                scope_matches = _balance_request_scope(self) == request_scope
            except Exception:
                scope_matches = False
            _invalidate_balance_observation(self, clear_values=not scope_matches)
        except Exception as exc:
            _record_balance_runtime_exception(self, "watchdog_update_positions_balance", exc)
        if btn:
            try:
                btn.setEnabled(True)
                if old_btn_text is not None:
                    btn.setText(old_btn_text)
            except Exception as exc:
                _record_balance_runtime_exception(self, "watchdog_button_restore", exc)

    QtCore.QTimer.singleShot(120000, lambda t=refresh_token: _watchdog(t))
