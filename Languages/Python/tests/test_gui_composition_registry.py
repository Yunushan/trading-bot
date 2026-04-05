from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import QtWidgets as _QtWidgets  # noqa: F401

    PYQT_AVAILABLE = True
    PYQT_UNAVAILABLE_REASON = ""
except Exception as exc:
    PYQT_AVAILABLE = False
    PYQT_UNAVAILABLE_REASON = str(exc)

if PYQT_AVAILABLE:
    from app.gui.positions import positions_runtime
    from app.gui.runtime.composition.binding_modules import _load_binding_modules
    from app.gui.runtime.window import runtime as window_runtime
    from app.gui.shared import config_runtime


def _iter_namespace_names(namespace: SimpleNamespace, prefix: str = "modules"):
    for name, value in vars(namespace).items():
        full_name = f"{prefix}.{name}"
        yield full_name, name, value
        if isinstance(value, SimpleNamespace):
            yield from _iter_namespace_names(value, prefix=full_name)


@unittest.skipUnless(PYQT_AVAILABLE, f"PyQt6 unavailable: {PYQT_UNAVAILABLE_REASON}")
class GuiCompositionRegistryTests(unittest.TestCase):
    def test_binding_registry_uses_canonical_namespace_labels(self):
        modules = _load_binding_modules()

        leaked_labels = [
            full_name
            for full_name, name, _value in _iter_namespace_names(modules)
            if name.startswith("main_window_")
        ]

        self.assertEqual([], leaked_labels)
        self.assertFalse(hasattr(modules.shared, "main_window_config"))
        self.assertTrue(hasattr(modules.shared, "config"))
        self.assertTrue(hasattr(modules.positions, "runtime"))
        self.assertTrue(hasattr(modules.runtime.window, "runtime"))
        self.assertIs(modules.shared.config, config_runtime)
        self.assertIs(modules.positions.runtime, positions_runtime)
        self.assertIs(modules.runtime.window.runtime, window_runtime)


if __name__ == "__main__":
    unittest.main()
