import sys
import unittest
from pathlib import Path


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


from app.platform import windows_taskbar
from app.platform import windows_taskbar_metadata_runtime as taskbar_metadata_runtime
from app.platform import windows_taskbar_shortcut_runtime as taskbar_shortcut_runtime


class WindowsTaskbarSplitSmokeTest(unittest.TestCase):
    def test_windows_taskbar_facade_matches_split_modules(self):
        self.assertIs(windows_taskbar.ensure_app_user_model_id, taskbar_metadata_runtime.ensure_app_user_model_id)
        self.assertIs(windows_taskbar.apply_taskbar_metadata, taskbar_metadata_runtime.apply_taskbar_metadata)
        self.assertIs(windows_taskbar.ensure_taskbar_visible, taskbar_metadata_runtime.ensure_taskbar_visible)
        self.assertIs(windows_taskbar.build_relaunch_command, taskbar_metadata_runtime.build_relaunch_command)
        self.assertIs(windows_taskbar.ensure_start_menu_shortcut, taskbar_shortcut_runtime.ensure_start_menu_shortcut)
        self.assertIs(
            windows_taskbar._apply_shortcut_property_store,
            taskbar_shortcut_runtime._apply_shortcut_property_store,
        )


if __name__ == "__main__":
    unittest.main()
