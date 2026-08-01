from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
TOOL_PATH = REPO_ROOT / "tools" / "check_critical_coverage.py"


def _load_tool_module():
    spec = importlib.util.spec_from_file_location("check_critical_coverage", TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CriticalCoverageGateTests(unittest.TestCase):
    def test_current_python_coverage_meets_critical_package_minimums(self):
        module = _load_tool_module()

        report = module.build_coverage_report(REPO_ROOT / "Languages" / "Python" / "coverage.xml")

        self.assertTrue(report["ok"])
        self.assertEqual(set(module.CRITICAL_PACKAGE_MINIMUMS), set(report["packages"]))

    def test_missing_or_undercovered_package_fails_the_gate(self):
        module = _load_tool_module()
        xml = """<coverage><packages>
        <package name=\"core.strategy\" line-rate=\"0.74\" />
        <package name=\"core.positions\" line-rate=\"0.60\" />
        <package name=\"integrations.exchanges.binance.orders\" line-rate=\"0.70\" />
        <package name=\"service.runners\" line-rate=\"0.80\" />
        </packages></coverage>"""
        with tempfile.TemporaryDirectory() as directory:
            coverage_file = Path(directory) / "coverage.xml"
            coverage_file.write_text(xml, encoding="utf-8")

            report = module.build_coverage_report(coverage_file)

        self.assertFalse(report["ok"])
        packages = report["packages"]
        self.assertFalse(packages["core.strategy"]["ok"])
        self.assertFalse(packages["settings"]["ok"])
