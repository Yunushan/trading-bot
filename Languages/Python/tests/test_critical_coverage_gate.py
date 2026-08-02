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
    def test_ci_runs_coverage_gate_after_python_suite(self):
        workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )

        test_command = "python tools/run_python_tests.py --runner pytest"
        coverage_command = (
            "python ../../tools/check_critical_coverage.py --coverage-file coverage.xml"
        )

        self.assertIn(test_command, workflow)
        self.assertIn(coverage_command, workflow)
        self.assertLess(workflow.index(test_command), workflow.index(coverage_command))

    def test_critical_package_minimums_accept_threshold_fixture(self):
        module = _load_tool_module()

        package_rows = "\n".join(
            f'<package name="{name}" line-rate="{minimum}" />'
            for name, minimum in module.CRITICAL_PACKAGE_MINIMUMS.items()
        )
        xml = f"<coverage><packages>{package_rows}</packages></coverage>"

        with tempfile.TemporaryDirectory() as directory:
            coverage_file = Path(directory) / "coverage.xml"
            coverage_file.write_text(xml, encoding="utf-8")
            report = module.build_coverage_report(coverage_file)

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

    def test_malformed_package_rate_returns_a_failed_report(self):
        module = _load_tool_module()
        xml = '<coverage><packages><package name="core.strategy" line-rate="not-a-rate" /></packages></coverage>'

        with tempfile.TemporaryDirectory() as directory:
            coverage_file = Path(directory) / "coverage.xml"
            coverage_file.write_text(xml, encoding="utf-8")

            report = module.build_coverage_report(coverage_file)

        self.assertFalse(report["ok"])
        self.assertIn("invalid package line-rate", report["error"])
        self.assertEqual({}, report["packages"])

    def test_non_finite_or_out_of_range_package_rates_fail_closed(self):
        module = _load_tool_module()

        for invalid_rate in ("nan", "inf", "-inf", "-0.01", "1.01"):
            with self.subTest(invalid_rate=invalid_rate):
                xml = (
                    "<coverage><packages>"
                    f'<package name="core.strategy" line-rate="{invalid_rate}" />'
                    "</packages></coverage>"
                )
                with tempfile.TemporaryDirectory() as directory:
                    coverage_file = Path(directory) / "coverage.xml"
                    coverage_file.write_text(xml, encoding="utf-8")

                    report = module.build_coverage_report(coverage_file)

                self.assertFalse(report["ok"])
                self.assertIn("invalid package line-rate", report["error"])
                self.assertEqual({}, report["packages"])
