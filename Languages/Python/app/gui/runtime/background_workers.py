from PyQt6.QtCore import QThread, pyqtSignal


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
