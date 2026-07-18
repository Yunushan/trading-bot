from __future__ import annotations

import importlib.util
import types
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[3]
AUDIT_RUNNER = REPO_ROOT / "tools" / "run_python_security_audit.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("run_python_security_audit", AUDIT_RUNNER)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PythonSecurityAuditTests(unittest.TestCase):
    def test_enables_truststore_before_loading_audit_client(self):
        module = _load_runner()
        fake_truststore = types.SimpleNamespace(inject_into_ssl=mock.Mock())

        with mock.patch.object(module.importlib, "import_module", return_value=fake_truststore) as importer:
            module._enable_system_trust()

        importer.assert_called_once_with("truststore")
        fake_truststore.inject_into_ssl.assert_called_once_with()

    def test_missing_security_extra_has_actionable_install_command(self):
        module = _load_runner()

        with mock.patch.object(module.importlib, "import_module", side_effect=ModuleNotFoundError):
            with self.assertRaisesRegex(RuntimeError, r"Languages/Python\[security\]"):
                module._enable_system_trust()


if __name__ == "__main__":
    unittest.main()
