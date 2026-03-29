from __future__ import annotations

import ast
from pathlib import Path
import unittest


APP_ROOT = Path("Languages/Python/app")

_BANNED_EXACT_IMPORTS = {
    "app.preamble",
    "app.workers",
    "app.close_all",
    "app.gui.main_window",
}

_BANNED_PREFIXES = (
    "app.gui.shared.main_window_",
    "app.gui.trade.main_window_",
    "app.gui.code.main_window_",
    "app.gui.backtest.main_window_backtest_",
    "app.gui.chart.main_window_chart_",
    "app.gui.dashboard.main_window_dashboard_",
    "app.gui.positions.main_window_positions",
    "app.gui.runtime.account.main_window_",
    "app.gui.runtime.service.main_window_",
    "app.gui.runtime.ui.main_window_",
    "app.gui.runtime.window.main_window_",
    "app.gui.runtime.composition.main_window_",
    "app.gui.runtime.strategy.main_window_",
)


def _module_name_for(path: Path) -> str:
    rel_parts = path.relative_to(APP_ROOT.parent).with_suffix("").parts
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


def _is_banned_import(target: str) -> bool:
    if target in _BANNED_EXACT_IMPORTS:
        return True
    if any(target.startswith(f"{name}.") for name in _BANNED_EXACT_IMPORTS):
        return True
    return any(target.startswith(prefix) for prefix in _BANNED_PREFIXES)


class LegacyRuntimeImportTests(unittest.TestCase):
    def test_python_app_avoids_legacy_runtime_imports(self):
        violations: list[str] = []
        for path in sorted(APP_ROOT.rglob("*.py")):
            for lineno, target in _iter_import_targets(path):
                if _is_banned_import(target):
                    violations.append(f"{path}:{lineno}: {target}")
        self.assertEqual(
            [],
            violations,
            "Legacy compatibility imports remain in app code:\n" + "\n".join(violations),
        )
