from PyQt6.QtCore import QThread, pyqtSignal
import traceback
import copy
from .close_all import close_all_futures_positions

class StopWorker(QThread):
    """Stops running strategy threads and (optionally) closes positions without freezing the UI."""
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(str)
    finished_ok = pyqtSignal(bool)

    def __init__(self, strategy_threads: dict, binance_wrapper, close_only: bool=False):
        super().__init__()
        self.strategy_threads = strategy_threads or {}
        self.binance_wrapper = binance_wrapper
        self.close_only = bool(close_only)

    def _stop_threads(self) -> bool:
        try:
            if self.close_only:
                return True
            threads = self.strategy_threads or {}
            for key, t in list(threads.items()):
                try:
                    if hasattr(t, "stop"): t.stop()
                except Exception: pass
            for key, t in list(threads.items()):
                try:
                    if hasattr(t, "join"): t.join(timeout=2.0)
                except Exception: pass
            try: threads.clear()
            except Exception: pass
            self.log_signal.emit("All strategy loops signaled to stop.")
            return True
        except Exception as e:
            self.log_signal.emit(f"_stop_threads error: {e}\n{traceback.format_exc()}")
            return False

    def _close_futures(self) -> bool:
        try:
            self.progress_signal.emit("Closing all FUTURES positions...")
            results = close_all_futures_positions(self.binance_wrapper)
            ok = sum(1 for r in (results or []) if r.get("ok"))
            fail = sum(1 for r in (results or []) if not r.get("ok"))
            for r in (results or []):
                if not r.get('ok'):
                    self.log_signal.emit(f"Close fail: {r.get('symbol')} -> {r.get('error')} | params={r.get('params')}")
            self.log_signal.emit(f"Futures close-all completed: {ok} successful, {fail} failed.")
            return fail == 0
        except Exception as e:
            self.log_signal.emit(f"Futures close-all error: {e}\n{traceback.format_exc()}")
            return False

    def _close_spot(self) -> bool:
        try:
            self.progress_signal.emit("Closing all SPOT positions into USDT...")
            bw = self.binance_wrapper
            results = []
            if hasattr(bw, "close_all_spot_positions"):
                results = bw.close_all_spot_positions()
            ok = sum(1 for r in (results or []) if isinstance(r, dict) and r.get("ok"))
            fail = sum(1 for r in (results or []) if isinstance(r, dict) and not r.get("ok"))
            self.log_signal.emit(f"Spot close-all completed: {ok} successful, {fail} failed.")
            return fail == 0
        except Exception as e:
            self.log_signal.emit(f"Spot close-all error: {e}\n{traceback.format_exc()}")
            return False

    def run(self):
        ok = True
        try:
            self.progress_signal.emit("Stopping strategy loops..." if not self.close_only else "Close-only mode...")
            ok = ok and self._stop_threads()
            if self.binance_wrapper:
                acct = str(getattr(self.binance_wrapper, "account_type", "")).upper()
                if acct == "FUTURES":
                    ok = ok and self._close_futures()
                elif acct == "SPOT":
                    ok = ok and self._close_spot()
                else:
                    self.log_signal.emit(f"Unknown account type for close-all: {acct}")
            self.progress_signal.emit("Stop completed." if not self.close_only else "Close-only completed.")
        except Exception as e:
            ok = False
            self.log_signal.emit(f"Error during stop: {e}\n{traceback.format_exc()}")
        finally:
            self.finished_ok.emit(bool(ok))


class StartWorker(QThread):
    """Starts strategy engines without blocking the UI."""
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(str)
    engine_started = pyqtSignal(str, object)  # key, engine
    finished_ok = pyqtSignal(bool)

    def __init__(self, guard, binance_wrapper, jobs: list, base_config: dict, existing_keys: set[str] | None = None, delay_ms: int = 80, trade_callback=None):
        super().__init__()
        self.guard = guard
        self.bw = binance_wrapper
        self.jobs = jobs or []
        self.cfg = base_config or {}
        self.existing = set(existing_keys or set())
        self.delay_ms = max(0, int(delay_ms))
        self.trade_cb = trade_callback

    def _start_one(self, job):
        try:
            from .strategy import StrategyEngine
            cfg = copy.deepcopy(self.cfg)
            cfg['symbol'] = job['symbol']
            cfg['interval'] = job['interval']
            engine = StrategyEngine(self.bw, cfg,
                                    log_callback=lambda m: self.log_signal.emit(m), trade_callback=self.trade_cb,
                                    can_open_callback=(getattr(self.guard, 'can_open', None)))
            engine.set_guard(self.guard)
            engine.start()
            key = f"{job['symbol']}@{job['interval']}"
            self.engine_started.emit(key, engine)
            return True
        except Exception as e:
            self.log_signal.emit(f"Start failed for {job}: {e}\n{traceback.format_exc()}")
            return False

    def run(self):
        ok = True
        try:
            try:
                self.progress_signal.emit("Reconciling with exchange...")
                try:
                    if hasattr(self.guard, 'attach_wrapper'): self.guard.attach_wrapper(self.bw)
                    if hasattr(self.guard, 'reset'): self.guard.reset()
                    if hasattr(self.guard, 'reconcile_with_exchange'): self.guard.reconcile_with_exchange(self.bw, self.jobs, account_type=getattr(self.bw,'account_type','FUTURES'))
                except Exception as _e:
                    self.log_signal.emit(f"Guard prep error: {_e}")
                if hasattr(self.guard, "reset"): self.guard.reset()
                if hasattr(self.guard, "reconcile_with_exchange"):
                    self.guard.reconcile_with_exchange(self.bw, self.jobs, account_type=getattr(self.bw, 'account_type', 'Futures'))
            except Exception as e:
                self.log_signal.emit(f"Guard reconcile error: {e}\n{traceback.format_exc()}" )

            # Stagger starts a bit to avoid CPU spikes
            for job in self.jobs:
                key = f"{job['symbol']}@{job['interval']}"
                if key in self.existing:
                    continue
                ok = self._start_one(job) and ok
                if self.delay_ms:
                    self.msleep(self.delay_ms)
            self.progress_signal.emit("Strategy started.")
        except Exception as e:
            ok = False
            self.log_signal.emit(f"Error during start: {e}\n{traceback.format_exc()}" )
        finally:
            self.finished_ok.emit(bool(ok))

class CallWorker(QThread):
    done = pyqtSignal(object, object)
    progress = pyqtSignal(str)
    def __init__(self, fn, *args, parent=None, **kwargs):
        super().__init__(parent)
        self._fn, self._args, self._kwargs = fn, args, kwargs
    def run(self):
        try:
            res = self._fn(*self._args, **self._kwargs)
            self.done.emit(res, None)
        except Exception as e:
            try:
                import traceback
                self.progress.emit(f"Async error: {e}\n{traceback.format_exc()}")
            except Exception:
                pass
            self.done.emit(None, e)
