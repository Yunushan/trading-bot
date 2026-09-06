from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
TOOL_PATH = REPO_ROOT / "tools" / "check_critical_coverage.py"


def _load_tool_module():
    spec = importlib.util.spec_from_file_location("check_critical_coverage", TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _coverage_xml(rows):
    root = ET.Element("coverage")
    packages = ET.SubElement(root, "packages")
    for name, covered, total in rows:
        package = ET.SubElement(
            packages, "package", name=name, attrib={"line-rate": str(covered / total if total else 1)}
        )
        classes = ET.SubElement(package, "classes")
        source = ET.SubElement(classes, "class", name="runtime.py", filename=name.replace(".", "/") + "/runtime.py")
        lines = ET.SubElement(source, "lines")
        for number in range(1, total + 1):
            ET.SubElement(lines, "line", number=str(number), hits=str(int(number <= covered)))
    return ET.tostring(root, encoding="unicode")


class CriticalCoverageGateTests(unittest.TestCase):
    def test_covered_parent_cannot_hide_undercovered_descendants(self):
        module = _load_tool_module()
        rows = [(name, 100, 100) for name in module.CRITICAL_PACKAGE_MINIMUMS]
        rows.append(("core.strategy.orders", 0, 900))
        with tempfile.TemporaryDirectory() as directory:
            coverage_file = Path(directory) / "coverage.xml"
            coverage_file.write_text(_coverage_xml(rows), encoding="utf-8")
            report = module.build_coverage_report(coverage_file)

        self.assertFalse(report["ok"])
        self.assertAlmostEqual(report["packages"]["core.strategy"]["actual"], 0.1)

    def test_ci_runs_coverage_gate_after_python_suite(self):
        workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

        test_command = "python tools/run_python_tests.py --runner pytest"
        coverage_command = "python ../../tools/check_critical_coverage.py --coverage-file coverage.xml"

        self.assertIn(test_command, workflow)
        self.assertIn(coverage_command, workflow)
        self.assertLess(workflow.index(test_command), workflow.index(coverage_command))

    def test_critical_package_minimums_accept_threshold_fixture(self):
        module = _load_tool_module()

        rows = [(name, round(minimum * 100), 100) for name, minimum in module.CRITICAL_PACKAGE_MINIMUMS.items()]

        with tempfile.TemporaryDirectory() as directory:
            coverage_file = Path(directory) / "coverage.xml"
            coverage_file.write_text(_coverage_xml(rows), encoding="utf-8")
            report = module.build_coverage_report(coverage_file)

        self.assertTrue(report["ok"])
        self.assertEqual(set(module.CRITICAL_PACKAGE_MINIMUMS), set(report["packages"]))
        for name, minimum in module.CRITICAL_PACKAGE_MINIMUMS.items():
            self.assertEqual(minimum, report["packages"][name]["actual"])
            self.assertEqual(100, report["packages"][name]["total_lines"])

    def test_missing_or_undercovered_package_fails_the_gate(self):
        module = _load_tool_module()
        xml = _coverage_xml(
            [
                ("core.strategy", 74, 100),
                ("core.positions", 60, 100),
                ("integrations.exchanges.binance.orders", 70, 100),
                ("service.runners", 80, 100),
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            coverage_file = Path(directory) / "coverage.xml"
            coverage_file.write_text(xml, encoding="utf-8")

            report = module.build_coverage_report(coverage_file)

        self.assertFalse(report["ok"])
        packages = report["packages"]
        self.assertFalse(packages["core.strategy"]["ok"])
        self.assertFalse(packages["settings"]["ok"])
        self.assertIsNone(packages["settings"]["actual"])

    def test_descendant_only_scope_is_counted_and_similar_prefix_is_excluded(self):
        module = _load_tool_module()
        rows = [(name, 100, 100) for name in module.CRITICAL_PACKAGE_MINIMUMS if name != "core.strategy"]
        rows.extend(
            [
                ("core.strategy.orders.submit", 75, 100),
                ("core.strategy_extra", 0, 900),
                ("unrelated.core.strategy", 0, 900),
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "coverage.xml"
            path.write_text(_coverage_xml(rows), encoding="utf-8")
            report = module.build_coverage_report(path)
        self.assertTrue(report["ok"])
        strategy = report["packages"]["core.strategy"]
        self.assertEqual(0.75, strategy["actual"])
        self.assertEqual(["core.strategy.orders.submit"], strategy["included_packages"])
        self.assertEqual(75, strategy["covered_lines"])
        self.assertEqual(100, strategy["total_lines"])

    def test_summary_rate_and_method_lines_cannot_inflate_coverage(self):
        module = _load_tool_module()
        root = ET.fromstring(_coverage_xml([("core.strategy", 74, 100)]))
        package = root.find("./packages/package")
        package.set("line-rate", "1.0")
        source = package.find("./classes/class")
        method = ET.SubElement(ET.SubElement(source, "methods"), "method")
        lines = ET.SubElement(method, "lines")
        for number in range(1, 101):
            ET.SubElement(lines, "line", number=str(number), hits="10")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "coverage.xml"
            path.write_text(ET.tostring(root, encoding="unicode"), encoding="utf-8")
            report = module.build_coverage_report(path)
        self.assertEqual(0.74, report["packages"]["core.strategy"]["actual"])
        self.assertEqual(100, report["packages"]["core.strategy"]["total_lines"])
        self.assertFalse(report["ok"])

    def test_empty_scope_and_summary_only_xml_cannot_pass(self):
        module = _load_tool_module()
        for xml in (
            _coverage_xml([(name, 0, 0) for name in module.CRITICAL_PACKAGE_MINIMUMS]),
            '<coverage><packages><package name="core.strategy" line-rate="1" /></packages></coverage>',
            "<not-coverage />",
            "<coverage>",
        ):
            with self.subTest(xml=xml[:100]), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "coverage.xml"
                path.write_text(xml, encoding="utf-8")
                self.assertFalse(module.build_coverage_report(path)["ok"])

    def test_invalid_and_duplicate_line_evidence_fails_closed(self):
        module = _load_tool_module()
        baseline = ET.fromstring(_coverage_xml([("core.strategy", 75, 100)]))
        variants = []
        for attribute, values in (("number", ("", "0", "-1", "1.5", "nan")), ("hits", ("", "-1", "0.5", "inf"))):
            for value in values:
                root = copy.deepcopy(baseline)
                root.find("./packages/package/classes/class/lines/line").set(attribute, value)
                variants.append((f"{attribute}={value}", root))
        for kind in ("line", "class", "package", "missing-lines", "missing-filename"):
            root = copy.deepcopy(baseline)
            if kind in ("missing-lines", "missing-filename"):
                source = root.find("./packages/package/classes/class")
                if kind == "missing-lines":
                    source.remove(source.find("lines"))
                else:
                    source.attrib.pop("filename")
            else:
                parent_path = {
                    "line": "./packages/package/classes/class/lines",
                    "class": "./packages/package/classes",
                    "package": "./packages",
                }[kind]
                parent = root.find(parent_path)
                parent.append(copy.deepcopy(parent.find(kind)))
            variants.append((kind, root))
        for label, root in variants:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "coverage.xml"
                path.write_text(ET.tostring(root, encoding="unicode"), encoding="utf-8")
                report = module.build_coverage_report(path)
                self.assertFalse(report["ok"])
                self.assertIn("invalid coverage line evidence", report["error"])

    def test_cli_reports_subtree_counts_and_returns_failure(self):
        module = _load_tool_module()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "coverage.xml"
            path.write_text(_coverage_xml([("core.strategy", 74, 100)]), encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = module.main(["--coverage-file", str(path)])
        self.assertEqual(1, status)
        self.assertIn("core.strategy (including descendants): 74.00% [74/100 lines]", output.getvalue())

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

    def test_missing_coverage_report_has_regeneration_remediation(self):
        module = _load_tool_module()

        with tempfile.TemporaryDirectory() as directory:
            coverage_file = Path(directory) / "missing-coverage.xml"
            report = module.build_coverage_report(coverage_file)

        self.assertFalse(report["ok"])
        self.assertIn("coverage report not found", report["error"])
        self.assertIn("tools/run_python_tests.py --runner pytest", report["error"])
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
