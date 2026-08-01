from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
