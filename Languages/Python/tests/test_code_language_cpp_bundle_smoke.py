import sys
import unittest
from pathlib import Path


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


from app.gui.code import code_language_cpp_bundle_runtime as cpp_bundle_runtime
from app.gui.code import code_language_cpp_bundle_cache_runtime as cpp_bundle_cache_runtime
from app.gui.code import code_language_cpp_bundle_install_runtime as cpp_bundle_install_runtime
from app.gui.code import code_language_cpp_bundle_packaged_runtime as cpp_bundle_packaged_runtime
from app.gui.code import code_language_cpp_bundle_release_runtime as cpp_bundle_release_runtime


class CodeLanguageCppBundleSplitSmokeTest(unittest.TestCase):
    def test_cpp_bundle_facade_matches_split_modules(self):
        self.assertIs(cpp_bundle_runtime.reset_cpp_runtime_caches, cpp_bundle_cache_runtime.reset_cpp_runtime_caches)
        self.assertIs(cpp_bundle_runtime.cpp_cache_root, cpp_bundle_cache_runtime.cpp_cache_root)
        self.assertIs(cpp_bundle_runtime.cpp_runtime_is_cached_path, cpp_bundle_cache_runtime.cpp_runtime_is_cached_path)
        self.assertIs(cpp_bundle_runtime.read_cache_meta, cpp_bundle_cache_runtime.read_cache_meta)
        self.assertIs(cpp_bundle_runtime.cpp_packaged_runtime_exe, cpp_bundle_packaged_runtime.cpp_packaged_runtime_exe)
        self.assertIs(cpp_bundle_runtime.cpp_packaged_installed_value, cpp_bundle_packaged_runtime.cpp_packaged_installed_value)
        self.assertIs(cpp_bundle_runtime.cpp_runtime_bundle_missing, cpp_bundle_packaged_runtime.cpp_runtime_bundle_missing)
        self.assertIs(cpp_bundle_runtime.cpp_latest_release_asset_info, cpp_bundle_release_runtime.cpp_latest_release_asset_info)
        self.assertIs(cpp_bundle_runtime.download_binary_file, cpp_bundle_install_runtime.download_binary_file)
        self.assertIs(cpp_bundle_runtime.ensure_cached_cpp_bundle, cpp_bundle_install_runtime.ensure_cached_cpp_bundle)
        self.assertIs(cpp_bundle_runtime.populate_cpp_bundle_from_zip, cpp_bundle_install_runtime.populate_cpp_bundle_from_zip)


if __name__ == "__main__":
    unittest.main()
