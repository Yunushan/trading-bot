from __future__ import annotations

import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
CHECKER_PATH = REPO_ROOT / "tools" / "summarize_trivy_report.py"
SPEC = importlib.util.spec_from_file_location("summarize_trivy_report", CHECKER_PATH)
assert SPEC and SPEC.loader
trivy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(trivy)


class TrivyReportSummaryTests(unittest.TestCase):
    def test_summarizes_uppercase_trivy_schema_and_orders_by_severity(self) -> None:
        payload = [
            {
                "Target": "service",
                "Vulnerabilities": [
                    {
                        "VulnerabilityID": "CVE-2",
                        "PkgName": "second",
                        "InstalledVersion": "1.0",
                        "FixedVersion": "1.1",
                        "Severity": "HIGH",
                    },
                    {
                        "VulnerabilityID": "CVE-1",
                        "PkgName": "first",
                        "InstalledVersion": "2.0",
                        "FixedVersion": "",
                        "Severity": "CRITICAL",
                    },
                ],
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trivy.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            counts, findings = trivy.summarize_report(path)

        self.assertEqual(1, counts["CRITICAL"])
        self.assertEqual(1, counts["HIGH"])
        self.assertEqual(["CVE-1", "CVE-2"], [finding["id"] for finding in findings])
        self.assertEqual("not available", findings[0]["fixed"])

    def test_supports_lowercase_results_schema(self) -> None:
        payload = {
            "results": [
                {
                    "target": "runtime",
                    "vulnerabilities": [
                        {
                            "vulnerability_id": "CVE-3",
                            "pkg_name": "runtime-package",
                            "installed_version": "3.0",
                            "fixed_version": "3.1",
                            "severity": "medium",
                        }
                    ],
                }
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trivy.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            counts, findings = trivy.summarize_report(path)

        self.assertEqual(1, counts["MEDIUM"])
        self.assertEqual("runtime", findings[0]["target"])

    def test_allows_null_vulnerabilities_for_clean_results(self) -> None:
        payload = {"Results": [{"Target": "runtime", "Vulnerabilities": None}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trivy.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            counts, findings = trivy.summarize_report(path)

        self.assertEqual({}, counts)
        self.assertEqual([], findings)

    def test_allows_omitted_vulnerabilities_for_clean_results(self) -> None:
        payload = {"Results": [{"Target": "runtime"}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trivy.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            counts, findings = trivy.summarize_report(path)

        self.assertEqual({}, counts)
        self.assertEqual([], findings)

    def test_rejects_unknown_severity_instead_of_counting_it_as_unknown(self) -> None:
        payload = {
            "Results": [
                {
                    "Target": "runtime",
                    "Vulnerabilities": [
                        {
                            "VulnerabilityID": "CVE-4",
                            "PkgName": "runtime-package",
                            "Severity": "severe",
                        }
                    ],
                }
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trivy.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(trivy.TrivyReportFormatError):
                trivy.summarize_report(path)

    def test_rejects_malformed_vulnerability_records(self) -> None:
        payload = {"Results": [{"Target": "runtime", "Vulnerabilities": ["not an object"]}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trivy.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(trivy.TrivyReportFormatError):
                trivy.summarize_report(path)

    def test_cli_reports_invalid_schema_and_fails_closed(self) -> None:
        payload = {"Results": [{"Target": "runtime", "Vulnerabilities": "invalid"}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trivy.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = trivy.main([str(path)])

        self.assertEqual(1, exit_code)
        self.assertIn("Invalid Trivy report", output.getvalue())


if __name__ == "__main__":
    unittest.main()
