from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path

from app.bootstrap.runtime_directory import create_private_runtime_directory


class RuntimeDirectorySecurityTests(unittest.TestCase):
    def test_runtime_directories_are_private_unique_and_cleaned_up(self):
        first = create_private_runtime_directory()
        second = create_private_runtime_directory()
        first_path = Path(first.name)
        second_path = Path(second.name)
        try:
            self.assertNotEqual(first_path, second_path)
            self.assertTrue(first_path.is_dir())
            self.assertTrue(second_path.is_dir())
            self.assertEqual(Path(tempfile.gettempdir()), first_path.parent)
            self.assertTrue(first_path.name.startswith("trading-bot-qt-runtime-"))
            if os.name == "posix":
                mode = stat.S_IMODE(first_path.stat(follow_symlinks=False).st_mode)
                self.assertEqual(stat.S_IRWXU, mode)
        finally:
            first.cleanup()
            second.cleanup()

        self.assertFalse(first_path.exists())
        self.assertFalse(second_path.exists())

    def test_bootstrap_retains_secure_directory_for_process_lifetime(self):
        runtime_env = (
            Path(__file__).resolve().parents[1] / "app" / "bootstrap" / "runtime_env.py"
        ).read_text(encoding="utf-8")

        self.assertIn("create_private_runtime_directory()", runtime_env)
        self.assertIn('os.environ["XDG_RUNTIME_DIR"] = _QT_RUNTIME_TEMP_DIR.name', runtime_env)
        self.assertNotIn('"/tmp/qt-runtime-root"', runtime_env)
        self.assertNotIn('tmp_runtime = "/tmp"', runtime_env)


if __name__ == "__main__":
    unittest.main()
