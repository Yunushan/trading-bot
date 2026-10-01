"""Keep the lazy Python-owned Binance exports in both frozen desktop graphs."""

import ast
import importlib.util
import re
import shlex
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PYTHON_ROOT = REPO_ROOT / "Languages" / "Python"
PACKAGE = "app.integrations.exchanges.binance"
PACKAGE_ROOT = PYTHON_ROOT / "app" / "integrations" / "exchanges" / "binance"


def _lazy_module_targets() -> set[str]:
    targets = {f"{PACKAGE}.wrapper"}
    tree = ast.parse((PACKAGE_ROOT / "orders" / "__init__.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "_EXPORT_MODULES" for target in node.targets
        ):
            exports = ast.literal_eval(node.value)
            targets.update(importlib.util.resolve_name(module, f"{PACKAGE}.orders") for module in exports.values())
            return targets
    raise AssertionError("Lazy order export catalog was not found")


class LazyBinancePackagingTests(unittest.TestCase):
    def test_both_builds_collect_owned_lazy_modules_unconditionally(self):
        targets = _lazy_module_targets()
        self.assertIn(f"{PACKAGE}.orders.spot_opo_execution_runtime", targets)
        for filename in ("build_exe.ps1", "build_binary.sh"):
            with self.subTest(filename=filename):
                script = (PYTHON_ROOT / "tools" / filename).read_text(encoding="utf-8")
                if filename.endswith(".ps1"):
                    block = re.search(r"\$pyInstallerArgs = @\((.*?)\n  \)", script, re.DOTALL)
                    self.assertIsNotNone(block)
                    tokens = re.findall(r'"([^"\n]+)"', block.group(1))
                else:
                    block = re.search(r"pyinstaller_args=\((.*?)\n\)", script, re.DOTALL)
                    self.assertIsNotNone(block)
                    tokens = shlex.split(block.group(1), comments=True)
                collected = [tokens[index + 1] for index, token in enumerate(tokens[:-1]) if token == "--collect-submodules"]
                self.assertEqual(collected, [PACKAGE])
                for target in targets:
                    self.assertTrue(target.startswith(collected[0] + "."), target)

    @unittest.skipUnless(importlib.util.find_spec("PyInstaller"), "PyInstaller is a packaging dependency")
    def test_real_pyinstaller_collection_covers_current_dynamic_exports(self):
        from PyInstaller.utils.hooks import collect_submodules

        collected = set(collect_submodules(PACKAGE, on_error="raise"))
        missing = _lazy_module_targets() - collected
        self.assertEqual(missing, set(), f"Frozen graph omits lazy exports: {sorted(missing)}")


if __name__ == "__main__":
    unittest.main()
