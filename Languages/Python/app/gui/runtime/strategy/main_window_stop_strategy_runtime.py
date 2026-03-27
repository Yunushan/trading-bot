from __future__ import annotations

import time


def stop_strategy_sync(
    self,
    close_positions: bool = True,
    auth: dict | None = None,
    *,
    strategy_engine_cls=None,
) -> dict:
    """Synchronous helper to stop engines and optionally close all positions."""
    result: dict = {"ok": True}
    try:
        try:
            self._service_request_stop(
                close_positions=close_positions,
                source="desktop-stop",
            )
        except Exception:
            pass
        try:
            self._is_stopping_engines = True
        except Exception:
            pass
        try:
            if strategy_engine_cls is not None:
                strategy_engine_cls.pause_trading()
        except Exception:
            pass
        try:
            guard_obj = getattr(self, "guard", None)
            if guard_obj and hasattr(guard_obj, "pause_new"):
                guard_obj.pause_new()
        except Exception:
            pass
        engines = {}
        if hasattr(self, "strategy_engines") and isinstance(self.strategy_engines, dict):
            engines = dict(self.strategy_engines)

        if engines:
            self._is_stopping_engines = True
            stop_deadline = time.time() + 2.5
            for _, eng in engines.items():
                try:
                    if hasattr(eng, "stop"):
                        eng.stop()
                except Exception:
                    pass
            for _, eng in engines.items():
                try:
                    remaining = max(0.0, stop_deadline - time.time())
                    if remaining <= 0.0:
                        break
                    eng.join(timeout=min(0.25, remaining))
                except Exception:
                    continue
            still_alive: list[str] = []
            for key, eng in engines.items():
                try:
                    alive = bool(getattr(eng, "is_alive", lambda: False)())
                except Exception:
                    alive = False
                if alive:
                    still_alive.append(str(key))
            try:
                self.strategy_engines.clear()
            except Exception:
                pass
            try:
                self._engine_indicator_map.clear()
            except Exception:
                pass
            if still_alive:
                self.log(
                    f"Signaled loops to stop but {len(still_alive)} engine(s) are still shutting down: {', '.join(still_alive)}"
                )
            else:
                self.log("Stopped all strategy engines.")
        else:
            self.log("No engines to stop.")

        close_result = None
        if close_positions:
            try:
                if auth is None:
                    auth = self._snapshot_auth_state()
                fast_close = False
                try:
                    mode_txt = str(auth.get("mode") or "").lower()
                    fast_close = any(tag in mode_txt for tag in ("demo", "test", "sandbox"))
                except Exception:
                    fast_close = False
                self.shared_binance = self._build_wrapper_from_values(auth)
                try:
                    acct_text = str(auth.get("account_type") or "").upper()
                    if acct_text.startswith("FUT") and self.shared_binance is not None:
                        cancel_res = self.shared_binance.cancel_all_open_futures_orders()
                        result["cancel_open_orders_result"] = cancel_res
                except Exception as cancel_exc:
                    self.log(f"Cancel open orders failed: {cancel_exc}")
                close_result = self._close_all_positions_blocking(auth=auth, fast=fast_close)
                try:
                    acct_text = str(auth.get("account_type") or "").upper()
                    if acct_text.startswith("FUT") and self.shared_binance is not None:
                        cancel_res = self.shared_binance.cancel_all_open_futures_orders()
                        result["cancel_open_orders_after_close"] = cancel_res
                except Exception:
                    pass
            except Exception as exc:
                result["ok"] = False
                result["error"] = str(exc)
                self.log(f"Failed to trigger close-all: {exc}")
            result["close_all_result"] = close_result
    except Exception as exc:
        result["ok"] = False
        result["error"] = str(exc)
        try:
            self.log(f"Stop error: {exc}")
        except Exception:
            pass
    finally:
        try:
            self._is_stopping_engines = False
        except Exception:
            pass
        result["_sync_runtime_state"] = True
    return result


def stop_strategy_async(
    self,
    close_positions: bool = False,
    blocking: bool = False,
    *,
    stop_strategy_sync_fn=None,
):
    """Stop all StrategyEngine threads without auto-closing positions unless explicitly requested."""
    auth_snapshot = self._snapshot_auth_state() if close_positions else None

    def _process_stop_result(res):
        if not isinstance(res, dict):
            return res
        if not res.get("ok", True):
            try:
                self.log(f"Stop warning: {res.get('error')}")
            except Exception:
                pass
        close_details = res.get("close_all_result", None)
        if close_details is not None:
            try:
                self._handle_close_all_result(close_details)
            except Exception:
                pass
        if res.get("_sync_runtime_state"):
            try:
                self._sync_runtime_state()
            except Exception:
                pass
        return res

    if not callable(stop_strategy_sync_fn):
        return _process_stop_result({"ok": False, "error": "Stop strategy helper is not configured."})

    if blocking:
        return _process_stop_result(
            stop_strategy_sync_fn(close_positions=close_positions, auth=auth_snapshot)
        )

    try:
        from ....workers import CallWorker as _CallWorker
    except Exception:
        return _process_stop_result(
            stop_strategy_sync_fn(close_positions=close_positions, auth=auth_snapshot)
        )

    def _do():
        return stop_strategy_sync_fn(close_positions=close_positions, auth=auth_snapshot)

    def _done(res, err):
        if err:
            try:
                self.log(f"Stop error: {err}")
            except Exception:
                pass
            return
        _process_stop_result(res)

    worker = _CallWorker(_do, parent=self)
    try:
        worker.progress.connect(self.log)
    except Exception:
        pass
    worker.done.connect(_done)
    worker.finished.connect(worker.deleteLater)

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
