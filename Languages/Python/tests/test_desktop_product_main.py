import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.desktop import product_main  # noqa: E402


class DesktopProductMainTests(unittest.TestCase):
    def test_smoke_mode_bypasses_shortcut_and_gui_entrypoint(self):
        with (
            patch.object(product_main, "_run_packaged_smoke", return_value=0) as smoke,
            patch.object(product_main, "_maybe_launch_via_shell_shortcut") as shortcut,
            patch.dict(sys.modules, {"app.desktop.bootstrap": None}),
        ):
            self.assertEqual(product_main.main(["--smoke"]), 0)

        smoke.assert_called_once_with()
        shortcut.assert_not_called()

    def test_smoke_flag_is_case_insensitive_and_whitespace_tolerant(self):
        with patch.object(product_main, "_run_packaged_smoke", return_value=0) as smoke:
            self.assertEqual(product_main.main(["  --SMOKE  "]), 0)

        smoke.assert_called_once_with()

    def test_default_mode_dispatches_to_desktop_bootstrap(self):
        bootstrap = ModuleType("app.desktop.bootstrap")
        run_entrypoint = Mock(return_value=7)
        bootstrap._run_entrypoint = run_entrypoint
        with (
            patch.object(product_main, "_maybe_launch_via_shell_shortcut") as shortcut,
            patch.dict(sys.modules, {"app.desktop.bootstrap": bootstrap}),
        ):
            self.assertEqual(product_main.main([]), 7)

        shortcut.assert_called_once_with()
        run_entrypoint.assert_called_once_with()

    def test_packaged_smoke_imports_real_runtime_surface(self):
        self.assertEqual(product_main._run_packaged_smoke(), 0)


if __name__ == "__main__":
    unittest.main()
