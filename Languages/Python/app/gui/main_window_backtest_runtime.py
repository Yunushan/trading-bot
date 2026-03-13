from __future__ import annotations

from PyQt6 import QtCore

from app.backtester import BacktestEngine, BacktestRequest


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
            result = self.engine.run(
                self.request,
                progress=self.progress.emit,
                should_stop=lambda: bool(self._stop_requested),
            )
            self.finished.emit(result, None)
        except Exception as exc:
            self.finished.emit({}, exc)
