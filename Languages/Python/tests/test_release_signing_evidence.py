from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
import zipfile


REPO_ROOT = Path(__file__).resolve().parents[3]
WRITER_PATH = REPO_ROOT / "tools" / "write_release_signing_evidence.py"
CHECKER_PATH = REPO_ROOT / "tools" / "check_release_signing_evidence.py"

WRITER_SPEC = importlib.util.spec_from_file_location("write_release_signing_evidence", WRITER_PATH)
assert WRITER_SPEC and WRITER_SPEC.loader
writer = importlib.util.module_from_spec(WRITER_SPEC)
sys.modules["write_release_signing_evidence"] = writer
WRITER_SPEC.loader.exec_module(writer)

CHECKER_SPEC = importlib.util.spec_from_file_location("check_release_signing_evidence", CHECKER_PATH)
assert CHECKER_SPEC and CHECKER_SPEC.loader
checker = importlib.util.module_from_spec(CHECKER_SPEC)
sys.modules["check_release_signing_evidence"] = checker
CHECKER_SPEC.loader.exec_module(checker)


class ReleaseSigningEvidenceTests(unittest.TestCase):
    def _write_files(self, root: Path, names: list[str]) -> list[Path]:
        paths = []
        for index, name in enumerate(names):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"signed-{index}".encode())
            paths.append(path)
        return paths

    def _write_zip(self, path: Path, members: dict[str, bytes]) -> Path:
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, payload in members.items():
                archive.writestr(name, payload)
        return path

    def _windows_fixture(self, root: Path, target_id: str) -> tuple[list[Path], list[Path]]:
        assets = self._write_files(
            root,
            [
                f"Trading-Bot-Python-{target_id}-1.2.3.exe",
                f"Trading-Bot-Rust-{target_id}-1.2.3.exe",
                f"Trading-Bot-Rust-tauri-{target_id}-1.2.3.exe",
            ],
        )
        cpp_target = self._write_files(
            root / f"build-{target_id}",
            ["Trading-Bot-C++.exe"],
        )[0]
        cpp_asset = self._write_zip(
            root / f"Trading-Bot-C++-{target_id}-1.2.3.zip",
            {"Trading-Bot-C++/Trading-Bot-C++.exe": cpp_target.read_bytes()},
        )
        return [*assets, cpp_asset], [*assets, cpp_target]

    def test_windows_evidence_binds_all_required_asset_families(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets, signature_targets = self._windows_fixture(root, "windows-x64")
            evidence = writer.build_evidence(
                platform_name="windows",
                target_id="windows-x64",
                source_revision="a" * 40,
                assets=assets,
                signature_targets=signature_targets,
            )
            evidence_path = root / "release-signing-windows-x64.json"
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

            issues = checker.validate_evidence(
                evidence,
                evidence_path=evidence_path,
                asset_dir=root,
                expected_revision="a" * 40,
            )

        self.assertEqual([], issues)
        self.assertFalse(evidence["notarization"]["required"])
        self.assertTrue(evidence["signing"]["secure_timestamp"])

    def test_macos_evidence_requires_accepted_notary_logs_and_stapled_app(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            signature_targets = self._write_files(
                root / "signed",
                [
                    "Trading-Bot-Python",
                    "trading-bot-rust",
                    "trading-bot-tauri-desktop",
                    "Trading-Bot-C++",
                ],
            )
            asset_names = [
                "Trading-Bot-Python-macos-15-arm64-1.2.3.zip",
                "Trading-Bot-Rust-macos-15-arm64-1.2.3.zip",
                "Trading-Bot-Rust-tauri-macos-15-arm64-1.2.3.zip",
                "Trading-Bot-C++-macos-15-arm64-1.2.3.zip",
            ]
            assets = [
                self._write_zip(
                    root / asset_name,
                    {f"payload/{asset_name.removesuffix('.zip')}": target.read_bytes()},
                )
                for asset_name, target in zip(asset_names, signature_targets, strict=True)
            ]
            app_archive = self._write_zip(
                root / ".notary-cpp-macos-15-arm64.zip",
                {
                    "Trading-Bot-C++/Trading-Bot-C++.app/Contents/MacOS/Trading-Bot-C++": signature_targets[
                        -1
                    ].read_bytes()
                },
            )
            notarized_archives = [app_archive, *assets[:3]]
            receipts = []
            logs = []
            for index in range(4):
                receipt = root / f"receipt-{index}.json"
                receipt.write_text(
                    json.dumps({"id": f"12345678-1234-1234-1234-{index:012d}", "status": "Accepted"}),
                    encoding="utf-8",
                )
                log = root / f"log-{index}.json"
                log.write_text(
                    json.dumps({"issues": None if index == 0 else []}),
                    encoding="utf-8",
                )
                receipts.append(receipt)
                logs.append(log)

            evidence = writer.build_evidence(
                platform_name="macos",
                target_id="macos-15-arm64",
                source_revision="b" * 40,
                assets=assets,
                signature_targets=signature_targets,
                notary_receipts=receipts,
                notary_logs=logs,
                notarized_archives=notarized_archives,
                cpp_app_stapled=True,
            )
            evidence_path = root / "release-signing-macos-15-arm64.json"
            issues = checker.validate_evidence(
                evidence,
                evidence_path=evidence_path,
                asset_dir=root,
                expected_revision="b" * 40,
            )

        self.assertEqual([], issues)
        self.assertTrue(evidence["notarization"]["all_submissions_accepted"])
        self.assertEqual(4, len(evidence["notarization"]["submissions"]))

    def test_checker_rejects_hash_tampering_and_secret_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets, signature_targets = self._windows_fixture(root, "windows-arm64")
            evidence = writer.build_evidence(
                platform_name="windows",
                target_id="windows-arm64",
                source_revision="c" * 40,
                assets=assets,
                signature_targets=signature_targets,
            )
            evidence["certificate_password"] = "must-not-appear"
            assets[0].write_bytes(b"tampered")

            issues = checker.validate_evidence(
                evidence,
                evidence_path=root / "evidence.json",
                asset_dir=root,
            )

        self.assertTrue(any("forbidden secret-bearing field" in issue for issue in issues))
        self.assertTrue(any("hash mismatch" in issue for issue in issues))

    def test_checker_rejects_signature_hash_not_present_in_published_zip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets, signature_targets = self._windows_fixture(root, "windows-x64")
            assets[-1] = self._write_zip(
                assets[-1],
                {"Trading-Bot-C++/Trading-Bot-C++.exe": b"different-unsigned-payload"},
            )
            evidence = writer.build_evidence(
                platform_name="windows",
                target_id="windows-x64",
                source_revision="d" * 40,
                assets=assets,
                signature_targets=signature_targets,
            )
            evidence_path = root / "release-signing-windows-x64.json"

            issues = checker.validate_evidence(
                evidence,
                evidence_path=evidence_path,
                asset_dir=root,
            )

        self.assertTrue(any("signed cpp binary hash is not present" in issue for issue in issues))

    def test_complete_windows_publication_set_requires_both_unique_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence_paths = []
            for target_id in ("windows-x64", "windows-arm64"):
                assets, signature_targets = self._windows_fixture(root, target_id)
                evidence = writer.build_evidence(
                    platform_name="windows",
                    target_id=target_id,
                    source_revision="e" * 40,
                    assets=assets,
                    signature_targets=signature_targets,
                )
                evidence_path = root / f"release-signing-{target_id}.json"
                evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
                evidence_paths.append(evidence_path)

            report = checker.audit_paths(
                evidence_paths,
                asset_dir=root,
                expected_revision="e" * 40,
                required_platform="windows",
            )

        self.assertTrue(report["ok"])
        self.assertEqual([], report["issues"])


if __name__ == "__main__":
    unittest.main()
