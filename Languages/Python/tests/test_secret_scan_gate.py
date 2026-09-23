from __future__ import annotations

import contextlib
import importlib.util
import io
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tools" / "check_secret_scan.py"
SPEC = importlib.util.spec_from_file_location("check_secret_scan", SCRIPT)
assert SPEC and SPEC.loader
scan = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scan)


class SecretScanGateTests(unittest.TestCase):
    def test_scanner_gets_full_history_and_all_output_is_captured(self) -> None:
        marker = "synthetic-secret-that-must-never-be-printed"
        fake = subprocess.CompletedProcess([], scan.LEAK_EXIT_CODE, marker, marker)
        with patch.object(scan.subprocess, "run", return_value=fake) as run:
            self.assertEqual(scan.LEAK_EXIT_CODE, scan._scan(ROOT, "gitleaks"))
        args, kwargs = run.call_args
        self.assertIn("--log-opts=--all", args[0])
        self.assertIn("--redact=100", args[0])
        self.assertTrue(kwargs["capture_output"])
        self.assertEqual(ROOT, kwargs["cwd"])

    def test_leak_or_scanner_error_is_fail_closed_without_echoing_output(self) -> None:
        marker = "synthetic-secret-that-must-never-be-printed"
        for scanner_status in (scan.LEAK_EXIT_CODE, 2):
            with self.subTest(scanner_status=scanner_status):
                out, err = io.StringIO(), io.StringIO()
                with patch.object(scan, "_scan", return_value=scanner_status):
                    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                        status = scan.main(["--source", str(ROOT)])
                self.assertEqual(1, status)
                self.assertNotIn(marker, out.getvalue() + err.getvalue())
                self.assertNotIn("Fingerprint", out.getvalue() + err.getvalue())

    def test_scanner_exception_fails_closed_without_exception_text(self) -> None:
        marker = "synthetic-secret-that-must-never-be-printed"
        out, err = io.StringIO(), io.StringIO()
        with patch.object(scan, "_scan", side_effect=RuntimeError(marker)):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                status = scan.main(["--source", str(ROOT)])
        self.assertEqual(1, status)
        self.assertNotIn(marker, out.getvalue() + err.getvalue())

    def test_ci_enforces_history_and_synthetic_regression_for_every_pr(self) -> None:
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        job = workflow.split("  secret-scan:", 1)[1].split("  workflow-lint:", 1)[0]
        self.assertIn("name: Secret Scan", job)
        self.assertIn("fetch-depth: 0", job)
        self.assertIn("gitleaks/v8@v8.30.1", job)
        self.assertIn("check_secret_scan.py --self-test", job)
        self.assertIn("check_secret_scan.py --source .", job)
        self.assertNotIn("continue-on-error", job)
        self.assertIn("pull_request:", workflow)

    def test_historical_exceptions_are_exact_fingerprints(self) -> None:
        lines = (ROOT / ".gitleaksignore").read_text(encoding="utf-8").splitlines()
        fingerprints = [line for line in lines if line and not line.startswith("#")]
        self.assertEqual(11, len(fingerprints))
        self.assertEqual(len(fingerprints), len(set(fingerprints)))
        for fingerprint in fingerprints:
            commit, path, rule, line = fingerprint.rsplit(":", 3)
            self.assertEqual(40, len(commit))
            self.assertTrue(path)
            self.assertEqual("generic-api-key", rule)
            self.assertTrue(line.isdecimal())


if __name__ == "__main__":
    unittest.main()
