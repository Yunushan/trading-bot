from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

try:
    from PyQt6 import QtWidgets as _QtWidgets  # noqa: F401

    PYQT_AVAILABLE = True
    PYQT_UNAVAILABLE_REASON = ""
except Exception as exc:
    PYQT_AVAILABLE = False
    PYQT_UNAVAILABLE_REASON = str(exc)

if PYQT_AVAILABLE:
    from app.config import build_default_config
    from app.gui.shared import config_runtime
    from app.service.config_store import write_service_config_file


@unittest.skipUnless(PYQT_AVAILABLE, f"PyQt6 unavailable: {PYQT_UNAVAILABLE_REASON}")
class GuiConfigPersistenceTests(unittest.TestCase):
    def test_save_config_writes_service_wrapper_and_strips_inline_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            export_path = Path(tmp) / "desktop-export.json"
            config = build_default_config()
            config.update(
                {
                    "api_key": "exchange-key",
                    "api_secret": "exchange-secret",
                    "llm_api_key": "llm-secret",
                }
            )

            class _SaveDialog:
                AcceptMode = config_runtime.QtWidgets.QFileDialog.AcceptMode

                def __init__(self, _owner):
                    pass

                def setAcceptMode(self, _mode):
                    pass

                def setNameFilter(self, _name_filter):
                    pass

                def setDefaultSuffix(self, _suffix):
                    pass

                def exec(self):
                    return config_runtime.QtWidgets.QDialog.DialogCode.Accepted

                def selectedFiles(self):
                    return [str(export_path)]

            class _Window:
                def __init__(self):
                    self.config = config
                    self.logs: list[str] = []

                def log(self, message):
                    self.logs.append(str(message))

            window = _Window()
            with mock.patch.object(config_runtime.QtWidgets, "QFileDialog", _SaveDialog):
                config_runtime.save_config(window)

            payload = json.loads(export_path.read_text(encoding="utf-8"))
            self.assertEqual("trading-bot-service-config", payload["kind"])
            self.assertTrue(payload["contains_secrets"])
            self.assertFalse(payload["inline_secrets_persisted"])
            self.assertIn("api_key", payload["secret_fields"])
            self.assertIn("api_secret", payload["secret_fields"])
            self.assertIn("llm_api_key", payload["secret_fields"])
            self.assertEqual("", payload["config"]["api_key"])
            self.assertEqual("", payload["config"]["api_secret"])
            self.assertEqual("", payload["config"]["llm_api_key"])
            self.assertTrue(any("secret values stripped" in item for item in window.logs))

    def test_load_config_accepts_wrapped_service_config_exports(self):
        with tempfile.TemporaryDirectory() as tmp:
            export_path = Path(tmp) / "desktop-export.json"
            config = build_default_config()
            config.update({"symbols": ["ETHUSDT"], "intervals": ["15m"], "theme": "Blue"})
            write_service_config_file(config, export_path, allow_unsafe_path=True)

            class _LoadDialog:
                @staticmethod
                def getOpenFileName(*_args, **_kwargs):
                    return str(export_path), "JSON Files (*.json)"

            class _Window:
                def __init__(self):
                    self.config = build_default_config()
                    self.backtest_config: dict[str, object] = {}
                    self.chart_enabled = False
                    self.logs: list[str] = []
                    self.refreshed: list[str] = []
                    self.service_syncs = 0

                def _refresh_symbol_interval_pairs(self, kind):
                    self.refreshed.append(str(kind))

                def _sync_language_exchange_lists_from_config(self):
                    pass

                def _sync_service_config_snapshot(self):
                    self.service_syncs += 1

                def log(self, message):
                    self.logs.append(str(message))

            window = _Window()
            with (
                mock.patch.object(config_runtime.QtWidgets, "QFileDialog", _LoadDialog),
                mock.patch.object(config_runtime, "_LANGUAGE_PATHS", {"Python": PYTHON_ROOT}),
                mock.patch.object(config_runtime, "_EXCHANGE_PATHS", {"Binance": PYTHON_ROOT}),
            ):
                config_runtime.load_config(window)

            self.assertEqual(["ETHUSDT"], window.config["symbols"])
            self.assertEqual(["15m"], window.config["intervals"])
            self.assertEqual("Blue", window.config["theme"])
            self.assertEqual(["runtime", "backtest"], window.refreshed)
            self.assertEqual(1, window.service_syncs)
            self.assertTrue(any("Loaded config" in item for item in window.logs))


if __name__ == "__main__":
    unittest.main()
