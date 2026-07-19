import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import write_rust_package_smoke_evidence as package_evidence


class RustPackageSmokeEvidenceTests(unittest.TestCase):
    def _source_sync(self) -> dict[str, object]:
        contract_hash = package_evidence.native_python_source_contract_hash()
        return {
            "ok": True,
            "contract_hash": contract_hash,
            "issues": [],
            "generated": [{"ok": True}],
            "consumers": [{"ok": True}, {"ok": True}],
            "surface_contract": {"ok": True, "issues": []},
        }

    def _completed(self, marker: str) -> subprocess.CompletedProcess[str]:
        contract_hash = package_evidence.native_python_source_contract_hash()
        return subprocess.CompletedProcess(
            ["binary", "--smoke"],
            0,
            stdout=f"{marker} (contract {contract_hash}, native trading disabled).\n",
            stderr="",
        )

    def test_build_evidence_runs_and_hashes_both_required_binaries(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rust_cli = root / "trading-bot-rust"
            tauri = root / "trading-bot-tauri-desktop"
            rust_cli.write_bytes(b"rust-cli-fixture")
            tauri.write_bytes(b"tauri-fixture")

            with (
                patch.object(package_evidence, "audit_native_source_sync", return_value=self._source_sync()),
                patch.object(package_evidence, "_source_tree_clean", return_value=True),
                patch.object(
                    package_evidence.subprocess,
                    "run",
                    side_effect=[
                        self._completed("Trading Bot Rust packaged smoke passed"),
                        self._completed("Trading Bot Tauri packaged smoke passed"),
                    ],
                ),
            ):
                evidence = package_evidence.build_evidence(
                    rust_cli=rust_cli,
                    tauri_desktop=tauri,
                    source_revision="a" * 40,
                    system="Windows",
                    architecture="AMD64",
                    timeout=5,
                    require_clean_source=True,
                )

        self.assertEqual("passed", evidence["status"])
        self.assertEqual("windows", evidence["platform"]["system"])
        self.assertEqual("x64", evidence["platform"]["architecture"])
        self.assertFalse(evidence["runtime_ready_claimed"])
        self.assertEqual(["rust_cli", "tauri_desktop"], [row["role"] for row in evidence["binaries"]])
        self.assertEqual(hashlib.sha256(b"rust-cli-fixture").hexdigest(), evidence["binaries"][0]["sha256"])
        self.assertEqual(hashlib.sha256(b"tauri-fixture").hexdigest(), evidence["binaries"][1]["sha256"])

    def test_smoke_rejects_nonzero_stderr_and_missing_markers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            binary = Path(temp_dir) / "trading-bot-rust"
            binary.write_bytes(b"fixture")
            contract_hash = package_evidence.native_python_source_contract_hash()
            cases = (
                subprocess.CompletedProcess([str(binary)], 3, stdout="", stderr="failed"),
                subprocess.CompletedProcess([str(binary)], 0, stdout="ok", stderr="warning"),
                subprocess.CompletedProcess([str(binary)], 0, stdout="unrelated", stderr=""),
            )
            for completed in cases:
                with self.subTest(returncode=completed.returncode, stderr=completed.stderr):
                    with patch.object(package_evidence.subprocess, "run", return_value=completed):
                        with self.assertRaises(package_evidence.EvidenceError):
                            package_evidence._run_packaged_smoke(
                                role="rust_cli",
                                binary=binary,
                                contract_hash=contract_hash,
                                runtime_ready=False,
                                timeout=5,
                            )

    def test_strict_evidence_refuses_dirty_source_before_running_binaries(self):
        with (
            patch.object(package_evidence, "_source_tree_clean", return_value=False),
            patch.object(package_evidence, "audit_native_source_sync") as source_sync,
            patch.object(package_evidence.subprocess, "run") as run,
        ):
            with self.assertRaisesRegex(package_evidence.EvidenceError, "source tree"):
                package_evidence.build_evidence(
                    rust_cli=Path("missing-rust"),
                    tauri_desktop=Path("missing-tauri"),
                    source_revision="b" * 40,
                    system="linux",
                    architecture="x86_64",
                    timeout=5,
                    require_clean_source=True,
                )
        source_sync.assert_not_called()
        run.assert_not_called()

    def test_source_clean_guard_checks_tracked_source_and_excludes_release_outputs(self):
        completed = subprocess.CompletedProcess(
            ["git", "status"],
            0,
            stdout="",
            stderr="",
        )
        with patch.object(package_evidence.subprocess, "run", return_value=completed) as run:
            self.assertTrue(package_evidence._source_tree_clean())

        command = run.call_args.args[0]
        self.assertIn("--untracked-files=no", command)
        self.assertIn(":(exclude)release", command)

    def test_main_does_not_write_partial_evidence_on_smoke_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "evidence.json"
            with patch.object(
                package_evidence,
                "build_evidence",
                side_effect=package_evidence.EvidenceError("smoke failed"),
            ):
                return_code = package_evidence.main(
                    [
                        "--rust-cli",
                        str(root / "rust"),
                        "--tauri-desktop",
                        str(root / "tauri"),
                        "--output",
                        str(output),
                        "--json",
                    ]
                )
            self.assertEqual(1, return_code)
            self.assertFalse(output.exists())

    def test_main_writes_machine_readable_evidence_after_success(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "evidence.json"
            payload = {
                "schema": package_evidence.EVIDENCE_SCHEMA,
                "status": "passed",
                "binaries": [],
            }
            with patch.object(package_evidence, "build_evidence", return_value=payload):
                return_code = package_evidence.main(
                    [
                        "--rust-cli",
                        "rust",
                        "--tauri-desktop",
                        "tauri",
                        "--output",
                        str(output),
                        "--json",
                    ]
                )
            self.assertEqual(0, return_code)
            self.assertEqual(payload, json.loads(output.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
