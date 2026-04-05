# Trading Bot Desktop App

Canonical product launcher for the PyQt desktop application.

The actual desktop implementation still lives in `Languages/Python/` while the
repo finishes its product-first layout migration. This folder is the stable
top-level app boundary for desktop packaging and operator-facing launch docs.

## Run

From the repository root with the Python environment already activated:

```bash
python apps/desktop-pyqt/main.py
```

Deprecated compatibility launchers still work:

```bash
cd Languages/Python
python main.py
```
