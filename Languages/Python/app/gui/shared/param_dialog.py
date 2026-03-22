from PyQt6 import QtWidgets, QtCore

class ParamDialog(QtWidgets.QDialog):
    def __init__(self, key, original_params: dict, parent=None, display_name=None):
        super().__init__(parent)
        title = display_name or key
        self.setWindowTitle(f"Params: {title}")
        self._key = key
        # Copy without mutating original
        self._params = dict(original_params)
        lay = QtWidgets.QFormLayout(self)

        # Build only param editors (no "Enabled" here; it's controlled in Indicators panel)
        self.widgets = {}
        for k, v in self._params.items():
            if k == "enabled":
                continue
            e = QtWidgets.QLineEdit(str(v) if v is not None else "")
            e.setPlaceholderText("None")
            lay.addRow(k, e)
            self.widgets[k] = e

        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok |
            QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addRow(btns)

    def get_params(self) -> dict:
        out = {}
        for k, e in self.widgets.items():
            txt = e.text().strip()
            if txt == "" or txt.lower() == "none":
                out[k] = None
                continue
            try:
                if '.' in txt:
                    out[k] = float(txt)
                else:
                    out[k] = int(txt)
            except Exception:
                out[k] = txt
        return out
