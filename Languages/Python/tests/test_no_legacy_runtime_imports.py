from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path
import unittest


PYTHON_ROOT = Path("Languages/Python")


def _load_import_policy():
    if str(PYTHON_ROOT) not in sys.path:
        sys.path.insert(0, str(PYTHON_ROOT))
    from tools import import_policy

    return import_policy


_IMPORT_POLICY = _load_import_policy()
POLICY_SCAN_ROOTS = _IMPORT_POLICY.POLICY_SCAN_ROOTS
is_deprecated_import = _IMPORT_POLICY.is_deprecated_import
replacement_for_legacy_import = _IMPORT_POLICY.replacement_for_legacy_import


APP_ROOT = PYTHON_ROOT / "app"


def _iter_python_files(root: Path):
    if root.is_file():
        yield root
        return
    yield from sorted(root.rglob("*.py"))


def _module_name_for(path: Path) -> str:
    rel_parts = path.relative_to(PYTHON_ROOT).with_suffix("").parts
    return ".".join(rel_parts)


def _resolve_relative(module_name: str, level: int, name: str | None) -> str:
    parts = module_name.split(".")
    if level > len(parts):
        return name or ""
    base_parts = parts[:-level]
    if name:
        base_parts.extend(name.split("."))
    return ".".join(base_parts)


def _iter_import_targets(path: Path) -> list[tuple[int, str]]:
    module_name = _module_name_for(path)
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    targets: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                targets.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_relative(module_name, node.level, node.module)
            if base:
                targets.append((node.lineno, base))
                for alias in node.names:
                    if alias.name != "*":
                        targets.append((node.lineno, f"{base}.{alias.name}"))
    return targets


class LegacyRuntimeImportTests(unittest.TestCase):
    def test_python_workspace_avoids_legacy_runtime_imports(self):
        violations: list[str] = []
        for root in POLICY_SCAN_ROOTS:
            for path in _iter_python_files(PYTHON_ROOT / root):
                for lineno, target in _iter_import_targets(path):
                    replacement = replacement_for_legacy_import(target)
                    if replacement:
                        violations.append(f"{path}:{lineno}: {target} -> use {replacement}")
        self.assertEqual(
            [],
            violations,
            "Legacy compatibility imports remain in the Python workspace:\n" + "\n".join(violations),
        )

    def test_deprecated_import_registry_covers_backward_compatible_shims(self):
        uncovered: list[str] = []
        for path in sorted(APP_ROOT.rglob("*.py")):
            text = path.read_text(encoding="utf-8-sig")
            if "Backward-compatible import shim" not in text:
                continue
            module_name = _module_name_for(path)
            if not is_deprecated_import(module_name):
                uncovered.append(module_name)
        self.assertEqual(
            [],
            uncovered,
            "Backward-compatible shim modules are missing from tools.import_policy:\n" + "\n".join(uncovered),
        )

    def test_removed_flat_bootstrap_and_worker_shims_raise_import_error(self):
        removed_modules = [
            "app.preamble",
            "app.workers",
        ]

        for module_name in removed_modules:
            with self.subTest(module_name=module_name):
                with self.assertRaises(ModuleNotFoundError):
                    importlib.import_module(module_name)
