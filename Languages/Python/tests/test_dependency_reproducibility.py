from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PYTHON_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PYTHON_ROOT.parents[1]
DEPENDENCY_METADATA_SCRIPT = PYTHON_ROOT / "tools" / "check_dependency_metadata.py"
VERIFY_ALL_SCRIPT = REPO_ROOT / "tools" / "verify_all.py"
TOOL_VERSION_SCRIPT = REPO_ROOT / "tools" / "check_local_tool_versions.py"
BOOTSTRAP_SCRIPT = REPO_ROOT / "tools" / "bootstrap_local_dev.py"
CLEAN_WORKSPACE_SCRIPT = REPO_ROOT / "tools" / "clean_workspace_artifacts.py"
RISKY_PATTERN_SCRIPT = REPO_ROOT / "tools" / "audit_risky_patterns.py"
CLIENT_LOCK_SCRIPT = REPO_ROOT / "tools" / "check_client_dependency_locks.py"
COMPILE_CHECK_SCRIPT = REPO_ROOT / "tools" / "check_python_sources_compile.py"


def _load_script_module(name: str, path: Path):
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_verify_all_module():
    return _load_script_module("verify_all", VERIFY_ALL_SCRIPT)


def _load_tool_version_module():
    return _load_script_module("check_local_tool_versions", TOOL_VERSION_SCRIPT)


def _load_bootstrap_module():
    return _load_script_module("bootstrap_local_dev", BOOTSTRAP_SCRIPT)


class DependencyReproducibilityTests(unittest.TestCase):
    def test_verify_all_includes_ci_python_quality_checks(self):
        module = _load_verify_all_module()

        check_by_name = {check.name: check for check in module._checks(REPO_ROOT, skip_slow=True)}

        self.assertIn("python lint", check_by_name)
        self.assertIn("python type check", check_by_name)
        self.assertIn("client dependency locks", check_by_name)
        self.assertFalse(check_by_name["client dependency locks"].required)
        self.assertTrue(check_by_name["tool versions"].blocks_success)
        self.assertIn("ruff", check_by_name["python lint"].command)
        self.assertIn("--no-cache", check_by_name["python lint"].command)
        self.assertIn("mypy", check_by_name["python type check"].command)
        self.assertIn("--no-incremental", check_by_name["python type check"].command)
        self.assertIn("--cache-dir", check_by_name["python type check"].command)
        self.assertIn("--python-version", check_by_name["python type check"].command)
        version_index = check_by_name["python type check"].command.index("--python-version")
        self.assertEqual(module._mypy_python_version(), check_by_name["python type check"].command[version_index + 1])

        full_checks = {check.name: check for check in module._checks(REPO_ROOT, skip_slow=False)}
        full_check_names = set(full_checks)
        self.assertIn("python tests", full_check_names)
        self.assertIn("python source compile", full_check_names)
        self.assertIn("Languages/Python/tools/run_python_tests.py", full_checks["python tests"].command)
        self.assertEqual(module.DEFAULT_CHECK_TIMEOUT_SECONDS, full_checks["python tests"].timeout_seconds)
        self.assertGreaterEqual(full_checks["python tests"].timeout_seconds, 600)
        self.assertEqual(900, full_checks["native c++ build and tests"].timeout_seconds)
        self.assertEqual("900", full_checks["native c++ build and tests"].command[-1])
        self.assertIn("Cargo can securely access", full_checks["rust workspace check"].remediation)
        self.assertIn("--locked", full_checks["rust workspace check"].command)
        self.assertIn("--locked", full_checks["rust core tests"].command)
        self.assertNotIn("compileall", " ".join(" ".join(check.command) for check in module._checks(REPO_ROOT, skip_slow=False)))

        fresh_checks = {
            check.name: check
            for check in module._checks(
                REPO_ROOT,
                skip_slow=True,
                native_cpp_build_dir=Path("build") / "fresh-native-cpp",
            )
        }
        self.assertEqual(
            ("--build-dir", str(Path("build") / "fresh-native-cpp")),
            fresh_checks["native c++ build and tests"].command[-2:],
        )

    def test_verify_all_can_explicitly_skip_external_promotion_evidence(self):
        module = _load_verify_all_module()

        default_names = {
            check.name
            for check in module._checks(REPO_ROOT, skip_slow=True)
        }
        local_names = {
            check.name
            for check in module._checks(
                REPO_ROOT,
                skip_slow=True,
                skip_promotion_evidence=True,
            )
        }

        self.assertIn("rust native evidence import audit", default_names)
        self.assertNotIn("rust native evidence import audit", local_names)
        self.assertIn("native c++ build and tests", local_names)
        self.assertIn("rust core tests", local_names)

    def test_verify_all_runtime_remediation_reports_expected_and_actual_versions(self):
        module = _load_verify_all_module()
        stdout = json.dumps(
            {
                "ok": False,
                "checks": {
                    "python": {"expected": "3.14", "actual": "3.12.9", "ok": False},
                    "node": {"expected": "24", "actual": "24.0.0", "ok": True},
                },
            }
        )
        check = module.Check("tool versions", (sys.executable,), REPO_ROOT, required=False)

        remediation = module._remediation_for(check, returncode=0, stdout=stdout, stderr="")

        self.assertIn("python expected 3.14, actual 3.12.9", remediation)

    def test_verify_all_marks_nested_json_failure_and_blocks_runtime_mismatch(self):
        module = _load_verify_all_module()
        check = module.Check("tool versions", (sys.executable,), REPO_ROOT, required=False, blocks_success=True)
        completed = module.subprocess.CompletedProcess(
            list(check.command),
            0,
            stdout=json.dumps({"ok": False, "remediations": ["fix runtime"]}),
            stderr="",
        )

        with mock.patch.object(module.subprocess, "run", return_value=completed) as run:
            result = module._run_check(check, verbose=True)

        self.assertFalse(result["ok"])
        self.assertTrue(result["blocks_success"])
        self.assertEqual(["fix runtime"], module._collect_remediations([result]))
        self.assertFalse(module._report_ok([result]))
        self.assertEqual("1", run.call_args.kwargs["env"]["PYTHONDONTWRITEBYTECODE"])

    def test_verify_all_uses_check_specific_timeout(self):
        module = _load_verify_all_module()
        check = module.Check("native c++ build and tests", (sys.executable,), REPO_ROOT, timeout_seconds=900)
        completed = module.subprocess.CompletedProcess(list(check.command), 0, stdout="", stderr="")

        with mock.patch.object(module.subprocess, "run", return_value=completed) as run:
            result = module._run_check(check, verbose=True)

        self.assertTrue(result["ok"])
        self.assertEqual(900, run.call_args.kwargs["timeout"])

    def test_verify_all_nonblocking_advisory_failure_does_not_fail_report(self):
        module = _load_verify_all_module()
        results = [
            {"name": "required", "required": True, "blocks_success": False, "ok": True},
            {"name": "advisory", "required": False, "blocks_success": False, "ok": False},
        ]

        self.assertTrue(module._report_ok(results))

    def test_verify_all_nonzero_returncode_wins_over_nested_json_ok(self):
        module = _load_verify_all_module()
        check = module.Check("python tests", (sys.executable,), REPO_ROOT)

        self.assertFalse(module._check_ok_from_output(check=check, returncode=1, stdout='{"ok": true}'))

    def test_verify_all_exposes_rust_promotion_state_separately_from_audit_health(self):
        module = _load_verify_all_module()
        check = module.Check("rust native runtime promotion audit", (sys.executable,), REPO_ROOT)
        completed = module.subprocess.CompletedProcess(
            list(check.command),
            0,
            stdout=json.dumps(
                {
                    "ok": True,
                    "promotion_ready": False,
                    "completion_claim": {"status": "denied", "can_claim": False},
                }
            ),
            stderr="",
        )

        with mock.patch.object(module.subprocess, "run", return_value=completed):
            result = module._run_check(check, verbose=False)

        self.assertTrue(result["ok"])
        self.assertFalse(result["promotion_ready"])
        self.assertEqual("denied", result["completion_claim_status"])
        self.assertFalse(result["completion_claim_can_claim"])

    def test_verify_all_downgrades_only_dirty_source_promotion_import_failure(self):
        module = _load_verify_all_module()
        check = module.Check(
            "rust native evidence import audit",
            (sys.executable,),
            REPO_ROOT,
        )
        completed = module.subprocess.CompletedProcess(
            list(check.command),
            1,
            stdout=json.dumps(
                {
                    "ok": False,
                    "require_clean_source": True,
                    "issues": [
                        "artifact.json: current tracked source tree must be clean for promotion evidence validation; dirty paths: tools/verify_all.py",
                        "platform.json: current source tree must be clean for promotion evidence import",
                    ],
                }
            ),
            stderr="",
        )

        with mock.patch.object(module.subprocess, "run", return_value=completed):
            result = module._run_check(check, verbose=True)

        self.assertFalse(result["ok"])
        self.assertFalse(result["required"])
        self.assertFalse(result["blocks_success"])
        self.assertIn("clean candidate source tree", result["advisory_reason"])
        self.assertIn("--stale-promotion-evidence --apply", result["remediation"])
        self.assertTrue(module._report_ok([result]))

    def test_verify_all_downgrades_untracked_source_promotion_import_failure(self):
        module = _load_verify_all_module()
        check = module.Check(
            "rust native evidence import audit",
            (sys.executable,),
            REPO_ROOT,
        )
        completed = module.subprocess.CompletedProcess(
            list(check.command),
            1,
            stdout=json.dumps(
                {
                    "ok": False,
                    "require_clean_source": True,
                    "issues": [
                        "artifact.json: current promotion source tree must not contain untracked "
                        "source/tool files; untracked paths: tools/Setup-Windows11ReleaseRunner.ps1"
                    ],
                }
            ),
            stderr="",
        )

        with mock.patch.object(module.subprocess, "run", return_value=completed):
            result = module._run_check(check, verbose=True)

        self.assertFalse(result["ok"])
        self.assertFalse(result["required"])
        self.assertFalse(result["blocks_success"])
        self.assertIn("clean candidate source tree", result["advisory_reason"])
        self.assertTrue(module._report_ok([result]))

    def test_verify_all_downgrades_stale_commit_promotion_import_failure(self):
        module = _load_verify_all_module()
        check = module.Check(
            "rust native evidence import audit",
            (sys.executable,),
            REPO_ROOT,
        )
        completed = module.subprocess.CompletedProcess(
            list(check.command),
            1,
            stdout=json.dumps(
                {
                    "ok": False,
                    "require_clean_source": True,
                    "require_current_commit": True,
                    "issues": [
                        "artifact.json: artifact.json commit must match current git commit abc123",
                        "artifact.json: artifact.json current source tree must be clean for promotion evidence import",
                    ],
                }
            ),
            stderr="",
        )

        with mock.patch.object(module.subprocess, "run", return_value=completed):
            result = module._run_check(check, verbose=True)

        self.assertFalse(result["ok"])
        self.assertFalse(result["required"])
        self.assertFalse(result["blocks_success"])
        self.assertIn("current-commit artifacts", result["advisory_reason"])
        self.assertIn("--stale-promotion-evidence --apply", result["remediation"])
        self.assertTrue(module._report_ok([result]))

    def test_verify_all_downgrades_stale_release_platform_promotion_import_failure(self):
        module = _load_verify_all_module()
        check = module.Check(
            "rust native evidence import audit",
            (sys.executable,),
            REPO_ROOT,
        )
        completed = module.subprocess.CompletedProcess(
            list(check.command),
            1,
            stdout=json.dumps(
                {
                    "ok": False,
                    "require_clean_source": True,
                    "require_current_commit": True,
                    "issues": [
                        "release-platform-evidence/browser-chrome-windows_11_x64.json: "
                        "release-platform-evidence/browser-chrome-windows_11_x64.json "
                        "commit must match current git commit abc123",
                        "release-platform-evidence/browser-chrome-windows_11_x64.json: "
                        "release-platform-evidence/browser-chrome-windows_11_x64.json "
                        "native_source_sync must be a non-empty object",
                    ],
                }
            ),
            stderr="",
        )

        with mock.patch.object(module.subprocess, "run", return_value=completed):
            result = module._run_check(check, verbose=True)

        self.assertFalse(result["ok"])
        self.assertFalse(result["required"])
        self.assertFalse(result["blocks_success"])
        self.assertIn("runtime/release evidence", result["advisory_reason"])
        self.assertIn("--stale-promotion-evidence --apply", result["remediation"])
        self.assertTrue(module._report_ok([result]))

    def test_verify_all_keeps_missing_source_sync_import_failure_required(self):
        module = _load_verify_all_module()
        check = module.Check(
            "rust native evidence import audit",
            (sys.executable,),
            REPO_ROOT,
        )
        completed = module.subprocess.CompletedProcess(
            list(check.command),
            1,
            stdout=json.dumps(
                {
                    "ok": False,
                    "require_clean_source": True,
                    "require_current_commit": True,
                    "require_native_source_sync_audit": True,
                    "issues": [
                        "missing required current-checkout native source sync audit artifact: "
                        "artifacts/native-source-sync/native-source-sync-audit.json"
                    ],
                }
            ),
            stderr="",
        )

        with mock.patch.object(module.subprocess, "run", return_value=completed):
            result = module._run_check(check, verbose=True)

        self.assertFalse(result["ok"])
        self.assertTrue(result["required"])
        self.assertNotIn("advisory_reason", result)
        self.assertFalse(module._report_ok([result]))

    def test_verify_all_keeps_non_dirty_import_failure_required(self):
        module = _load_verify_all_module()
        check = module.Check(
            "rust native evidence import audit",
            (sys.executable,),
            REPO_ROOT,
        )
        completed = module.subprocess.CompletedProcess(
            list(check.command),
            1,
            stdout=json.dumps(
                {
                    "ok": False,
                    "require_clean_source": True,
                    "issues": ["artifact.json has unknown runtime evidence_id: stale"],
                }
            ),
            stderr="",
        )

        with mock.patch.object(module.subprocess, "run", return_value=completed):
            result = module._run_check(check, verbose=True)

        self.assertFalse(result["ok"])
        self.assertTrue(result["required"])
        self.assertNotIn("--stale-runtime-evidence", result.get("remediation", ""))
        self.assertFalse(module._report_ok([result]))

    def test_verify_all_client_lock_remediation_names_missing_lockfile_command(self):
        module = _load_verify_all_module()
        stdout = json.dumps(
            {
                "ok": False,
                "clients": [
                    {"path": "apps/web-dashboard", "lockfile_exists": True},
                    {"path": "apps/mobile-client", "lockfile_exists": False},
                ],
            }
        )
        check = module.Check("client dependency locks", (sys.executable,), REPO_ROOT, required=False)

        remediation = module._remediation_for(check, returncode=1, stdout=stdout, stderr="")

        self.assertIn("cd apps/mobile-client && npm install --package-lock-only", remediation)

    def test_verify_all_service_dependency_remediation_handles_missing_httpx2(self):
        module = _load_verify_all_module()
        check = module.Check("service tests", (sys.executable,), REPO_ROOT, remediation="generic")

        remediation = module._remediation_for(
            check,
            returncode=1,
            stdout="You can install this with: $ pip install httpx2",
            stderr="ModuleNotFoundError: No module named 'httpx2'",
        )

        self.assertIn("python tools/bootstrap_local_dev.py --python-command", remediation)
        self.assertIn('Languages/Python[service,dev]', remediation)

    def test_verify_all_full_test_dependency_remediation_uses_full_python_surface(self):
        module = _load_verify_all_module()
        check = module.Check("python tests", (sys.executable,), REPO_ROOT, remediation="generic")

        remediation = module._remediation_for(
            check,
            returncode=1,
            stdout="[FAIL] full Python tests require optional desktop/service/dev dependencies: PyQt6",
            stderr="ModuleNotFoundError: No module named 'PyQt6'",
        )

        self.assertIn("python tools/bootstrap_local_dev.py --python-command", remediation)
        self.assertIn('Languages/Python[desktop,service,dev]', remediation)

    def test_verify_all_workspace_hygiene_remediation_handles_noisy_artifacts(self):
        module = _load_verify_all_module()
        stdout = json.dumps({"noisy_artifact_count": 3, "noisy_artifacts": [".venv/", "build/"]})
        check = module.Check("workspace hygiene", (sys.executable,), REPO_ROOT, required=False)

        remediation = module._remediation_for(check, returncode=0, stdout=stdout, stderr="")

        self.assertIn("python tools/clean_workspace_artifacts.py --apply", remediation)

    def test_verify_all_report_collects_unique_remediations(self):
        module = _load_verify_all_module()
        results = [
            {"name": "a", "returncode": 1, "remediation": "fix one"},
            {"name": "b", "returncode": 1, "remediation": "fix one"},
            {"name": "c", "returncode": 0, "remediation": "fix parsed advisory"},
            {"name": "d", "returncode": 0},
        ]

        remediations = module._collect_remediations(results)

        self.assertEqual(["fix one", "fix parsed advisory"], remediations)

    def test_dependency_metadata_check_passes(self):
        module = _load_script_module("check_dependency_metadata", DEPENDENCY_METADATA_SCRIPT)

        self.assertEqual([], module.run_checks())
        self.assertEqual(".[desktop]", module.EXPECTED_REQUIREMENT_SHIMS["requirements.txt"])
        self.assertEqual(".[service]", module.EXPECTED_REQUIREMENT_SHIMS["requirements.service.txt"])
        self.assertIn("httpx2", module.DEV_DEPENDENCY_NAMES)
        self.assertEqual("pyinstaller==6.22.0", module.PYINSTALLER_REQUIREMENT)
        self.assertEqual(
            ["pyinstaller==6.22.0"],
            module._non_comment_lines(PYTHON_ROOT / "requirements.packaging.txt"),
        )
        for path in module.PACKAGING_INSTALL_SURFACES:
            self.assertIn("requirements.packaging.txt", path.read_text(encoding="utf-8"))

    def test_repo_declares_local_runtime_tool_versions(self):
        self.assertEqual("3.14", (REPO_ROOT / ".python-version").read_text(encoding="utf-8").strip())
        self.assertEqual("26", (REPO_ROOT / ".node-version").read_text(encoding="utf-8").strip())
        launcher = (PYTHON_ROOT / "Trading-Bot-Python.bat").read_text(encoding="utf-8")
        self.assertIn("py -3.15 -c", launcher)
        self.assertIn("%LocalAppData%\\Programs\\Python\\Python315\\python.exe", launcher)
        self.assertIn("C:\\Python315\\python.exe", launcher)
        self.assertIn("sys.version_info[:2] < (3, 16)", launcher)
        self.assertIn("python-3.14.5-amd64.exe", launcher)
        docs = (REPO_ROOT / "docs" / "DEPENDENCY_REPRODUCIBILITY.md").read_text(encoding="utf-8")
        self.assertIn("python tools/check_local_tool_versions.py --strict", docs)
        self.assertIn("python tools/bootstrap_local_dev.py --dry-run", docs)

    def test_dependabot_covers_every_shipped_dependency_ecosystem(self):
        config = (REPO_ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
        blocks = re.findall(r"(?ms)^  - package-ecosystem: ([^\n]+)\n(.*?)(?=^  - package-ecosystem:|\Z)", config)
        actual = {
            (
                ecosystem.strip(),
                re.search(r'(?m)^    directory: "([^"]+)"$', body).group(1),
            )
            for ecosystem, body in blocks
        }
        self.assertEqual(
            {
                ("github-actions", "/"),
                ("pip", "/Languages/Python"),
                ("npm", "/apps/web-dashboard"),
                ("npm", "/apps/mobile-client"),
                ("cargo", "/experiments/rust-shells"),
                ("docker", "/docker"),
            },
            actual,
        )
        self.assertEqual(6, config.count("interval: weekly"))
        self.assertNotIn("open-pull-requests-limit: 0", config)
        limits = [int(value) for value in re.findall(r"open-pull-requests-limit: (\d+)", config)]
        self.assertEqual(6, len(limits))
        self.assertTrue(all(limit >= 5 for limit in limits))
        self.assertIn("    groups:\n      binance-sdk:\n        patterns:", config)
        for package in (
            "binance-sdk-derivatives-trading-usds-futures",
            "binance-sdk-derivatives-trading-coin-futures",
            "binance-sdk-spot",
        ):
            self.assertIn(f'          - "{package}"', config)

    def test_supply_chain_security_workflow_audits_python_node_rust_and_container_clients(self):
        workflow = (REPO_ROOT / ".github" / "workflows" / "supply-chain-security.yml").read_text(
            encoding="utf-8"
        )
        pull_request_trigger = workflow.split("  pull_request:", 1)[1].split("  push:", 1)[0]

        self.assertNotIn("paths:", pull_request_trigger)
        self.assertIn("python -m venv .ci-python-audit", workflow)
        self.assertIn(
            ".ci-python-audit/bin/python -m pip install --upgrade pip==26.2.1 setuptools==83.0.0 wheel",
            workflow,
        )
        self.assertIn('.ci-python-audit/bin/python -m pip install -e "./Languages/Python[service,security]"', workflow)
        self.assertNotIn("actions/checkout@v5", workflow)
        self.assertTrue(
            any(
                action in workflow
                for action in (
                    "actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd",
                    "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
                )
            )
        )
        self.assertTrue(
            any(
                action in workflow
                for action in (
                    "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1",
                    "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97",
                )
            )
        )
        self.assertTrue(
            any(
                action in workflow
                for action in (
                    "actions/setup-node@249970729cb0ef3589644e2896645e5dc5ba9c38",
                    "actions/setup-node@820762786026740c76f36085b0efc47a31fe5020",
                )
            )
        )
        self.assertIn("dtolnay/rust-toolchain@4cda84d5c5c54efe2404f9d843567869ab1699d4", workflow)
        self.assertIn(
            ".ci-python-audit/bin/python tools/run_python_security_audit.py --skip-editable --progress-spinner=off",
            workflow,
        )
        self.assertIn("npm audit --omit=dev --audit-level=high", workflow)
        self.assertIn("check_mobile_image_size_exposure.cjs", workflow)
        self.assertIn('--mitigation-report "$mitigation_file"', workflow)
        self.assertIn("apps/web-dashboard", workflow)
        self.assertIn("apps/mobile-client", workflow)
        self.assertIn("cargo install cargo-audit --version 0.22.2 --locked", workflow)
        self.assertIn("working-directory: experiments/rust-shells", workflow)
        self.assertIn(
            'audit_db="$(mktemp -d "$RUNNER_TEMP/trading-bot-rustsec-db.XXXXXX")"',
            workflow,
        )
        self.assertIn("trap 'rm -rf \"$audit_db\"' EXIT", workflow)
        self.assertIn('cargo audit --db "$audit_db" --file Cargo.lock', workflow)
        self.assertIn('--format json > "$audit_report"', workflow)
        self.assertIn("check_rust_audit_policy.py", workflow)
        self.assertIn("--policy ../../tools/rust-audit-policy.json", workflow)
        self.assertIn('if [[ "$audit_status" -gt 1 ]]', workflow)
        self.assertIn("rust-dependency-audit-report", workflow)
        self.assertIn("actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a", workflow)
        self.assertIn("container-vulnerability-audit", workflow)
        self.assertIn("docker build --pull \\", workflow)
        self.assertIn('--build-arg BUILD_COMMIT="$GITHUB_SHA"', workflow)
        self.assertIn("Verify image source revision label", workflow)
        self.assertIn("id: image-build", workflow)
        self.assertIn("if: steps.image-build.outcome == 'success'", workflow)
        self.assertIn(
            "aquasecurity/trivy-action@ed142fd0673e97e23eac54620cfb913e5ce36c25",
            workflow,
        )
        self.assertIn("image-ref: trading-bot-service:supply-chain", workflow)
        self.assertIn("severity: HIGH,CRITICAL", workflow)
        self.assertIn('exit-code: "1"', workflow)
        self.assertIn("if: always() && steps.trivy.outcome != 'skipped'", workflow)

    def test_rust_audit_policy_is_exact_time_bounded_and_excludes_fixed_advisories(self):
        policy = json.loads((REPO_ROOT / "tools" / "rust-audit-policy.json").read_text(encoding="utf-8"))
        exceptions = policy["exceptions"]

        self.assertEqual(1, policy["version"])
        self.assertEqual(7, policy["max_database_age_days"])
        self.assertEqual(45, policy["max_exception_days"])
        self.assertEqual(16, len(exceptions))
        identities = {
            (item["kind"], item["id"], item["package"], item["version"])
            for item in exceptions
        }
        self.assertEqual(len(exceptions), len(identities))
        self.assertNotIn(("unsound", "RUSTSEC-2026-0097", "rand", "0.9.2"), identities)
        self.assertNotIn(("unsound", "RUSTSEC-2024-0429", "glib", "0.18.5"), identities)
        for exception in exceptions:
            with self.subTest(advisory=exception["id"], package=exception["package"]):
                self.assertEqual("2026-08-26", exception["reviewed"])
                self.assertEqual("2026-10-10", exception["expires"])
                self.assertTrue(exception["scope"])
                self.assertTrue(exception["reason"])

        cargo_lock = (REPO_ROOT / "experiments" / "rust-shells" / "Cargo.lock").read_text(
            encoding="utf-8"
        )
        self.assertIn('name = "rand"\nversion = "0.9.3"', cargo_lock)
        self.assertNotIn('name = "rand"\nversion = "0.9.2"', cargo_lock)

        rust_manifest = (REPO_ROOT / "experiments" / "rust-shells" / "Cargo.toml").read_text(
            encoding="utf-8"
        )
        self.assertIn('glib = { path = "../../vendor/glib-0.18.5" }', rust_manifest)
        glib_lock_entry = cargo_lock.split('name = "glib"\n', 1)[1].split("\n\n", 1)[0]
        self.assertNotIn("source =", glib_lock_entry)
        self.assertNotIn("checksum =", glib_lock_entry)

        glib_source = (
            REPO_ROOT / "vendor" / "glib-0.18.5" / "src" / "variant_iter.rs"
        ).read_text(encoding="utf-8")
        self.assertIn("let mut p: *mut libc::c_char", glib_source)
        self.assertIn("&mut p", glib_source)
        self.assertNotIn("let p: *mut libc::c_char", glib_source)
        patch_notes = (REPO_ROOT / "vendor" / "glib-0.18.5" / "PATCH.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("05dff0ee696f9bcd8617cd48c4b812d046d440cb", patch_notes)
        self.assertIn("233daaf6e83ae6a12a52055f568f9d7cf4671dabb78ff9560ab6da230ce00ee5", patch_notes)

    def test_mobile_production_lockfile_uses_patched_image_size_fork(self):
        policy = json.loads((REPO_ROOT / "tools" / "node-audit-policy.json").read_text(encoding="utf-8"))
        mobile_root = REPO_ROOT / "apps" / "mobile-client"
        mobile_package = json.loads((mobile_root / "package.json").read_text(encoding="utf-8"))
        lockfile = json.loads((mobile_root / "package-lock.json").read_text(encoding="utf-8"))

        self.assertEqual([], policy["projects"]["apps/mobile-client"]["exceptions"])
        self.assertEqual("npm:image-size-next@1.2.2", mobile_package["overrides"]["image-size"])
        resolved = [
            (package_path, metadata)
            for package_path, metadata in lockfile["packages"].items()
            if package_path.endswith("/node_modules/image-size")
        ]
        self.assertEqual(1, len(resolved))
        package_path, metadata = resolved[0]
        self.assertEqual(
            "node_modules/@react-native/community-cli-plugin/node_modules/image-size",
            package_path,
        )
        self.assertEqual("image-size-next", metadata["name"])
        self.assertEqual("1.2.2", metadata["version"])
        self.assertEqual(
            "sha512-Pd3CJ2+Ifk2H2jWikkoz2BSZgnuF3Qsea4gQmj2gtiOtYpGWBl7elj8EXnFMiY5PaYNruTTLD0hQ0UWK7pz9xA==",
            metadata["integrity"],
        )
        self.assertIn("check_mobile_image_size_exposure.cjs", mobile_package["scripts"]["test"])

    def test_mobile_production_lockfile_overrides_brace_expansion_security_fix(self):
        mobile_root = REPO_ROOT / "apps" / "mobile-client"
        package = json.loads((mobile_root / "package.json").read_text(encoding="utf-8"))
        lockfile = json.loads((mobile_root / "package-lock.json").read_text(encoding="utf-8"))

        for parent in ("react-native", "rimraf", "test-exclude"):
            self.assertEqual("1.1.16", package["overrides"][parent]["brace-expansion"])

        resolved_versions = {
            metadata["version"]
            for package_path, metadata in lockfile["packages"].items()
            if package_path.endswith("/brace-expansion")
        }
        self.assertTrue(resolved_versions)
        self.assertIn("5.0.9", resolved_versions)
        self.assertNotIn("5.0.8", resolved_versions)
        self.assertTrue(resolved_versions <= {"1.1.16", "5.0.9"})

    def test_mobile_production_lockfile_overrides_js_yaml_security_fix(self):
        mobile_root = REPO_ROOT / "apps" / "mobile-client"
        package = json.loads((mobile_root / "package.json").read_text(encoding="utf-8"))
        lockfile = json.loads((mobile_root / "package-lock.json").read_text(encoding="utf-8"))

        self.assertEqual("4.3.1", package["overrides"]["@expo/xcpretty"]["js-yaml"])
        self.assertEqual("4.3.1", lockfile["packages"]["node_modules/js-yaml"]["version"])

    def test_codeql_workflow_scans_python_javascript_and_native_languages_with_pinned_actions(self):
        workflow = (REPO_ROOT / ".github" / "workflows" / "codeql.yml").read_text(encoding="utf-8")
        pull_request_trigger = workflow.split("  pull_request:", 1)[1].split("  schedule:", 1)[0]

        self.assertNotIn("paths:", pull_request_trigger)
        self.assertIn("security-events: write", workflow)
        self.assertIn("- language: python", workflow)
        self.assertIn("- language: javascript-typescript", workflow)
        self.assertIn("- language: c-cpp", workflow)
        self.assertIn("- language: rust", workflow)
        self.assertIn("build-mode: ${{ matrix.build-mode }}", workflow)
        self.assertIn("config-file: ./.github/codeql-config.yml", workflow)
        self.assertEqual(4, workflow.count("build-mode: none"))
        codeql_config = (REPO_ROOT / ".github" / "codeql-config.yml").read_text(encoding="utf-8")
        self.assertIn("paths-ignore:", codeql_config)
        self.assertIn("vendor/glib-0.18.5/**", codeql_config)
        for action_name in ("init", "analyze"):
            self.assertRegex(
                workflow,
                rf"(?m)^\s*uses:\s*github/codeql-action/{action_name}@[0-9a-f]{{40}}(?:\s+#.*)?$",
            )

    def test_rust_live_evidence_commands_use_the_workspace_lockfile(self):
        workflow = (REPO_ROOT / ".github" / "workflows" / "rust-native-live-smoke.yml").read_text(
            encoding="utf-8"
        )
        preflight = (REPO_ROOT / "tools" / "check_rust_native_live_smoke_preflight.py").read_text(
            encoding="utf-8"
        )
        recovery = (REPO_ROOT / "tools" / "check_rust_native_local_recovery_evidence.py").read_text(
            encoding="utf-8"
        )
        rust_main = (REPO_ROOT / "experiments" / "rust-shells" / "src" / "main.rs").read_text(
            encoding="utf-8"
        )
        readme = (REPO_ROOT / "experiments" / "rust-shells" / "README.md").read_text(encoding="utf-8")
        quality_gates = (REPO_ROOT / "docs" / "QUALITY_AND_EVIDENCE_GATES.md").read_text(
            encoding="utf-8"
        )
        startup_packaging = (
            REPO_ROOT / "experiments" / "rust-shells" / "crates" / "core" / "src" / "startup_packaging.rs"
        ).read_text(encoding="utf-8")

        for content in (workflow, preflight, recovery, rust_main, readme, quality_gates):
            self.assertIn("cargo run --locked -p trading-bot-rust", content)
            self.assertNotIn("cargo run -p trading-bot-rust", content)
        self.assertIn("cargo run --locked -p trading-bot-tauri-desktop", readme)
        self.assertIn("cargo check --workspace --locked", quality_gates)
        self.assertIn("cargo test --locked -p trading-bot-core", quality_gates)
        self.assertIn("cargo build --workspace --locked", startup_packaging)

    def test_quality_gate_coverage_documentation_matches_pytest_configuration(self):
        pytest_config = (PYTHON_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        quality_gates = (REPO_ROOT / "docs" / "QUALITY_AND_EVIDENCE_GATES.md").read_text(
            encoding="utf-8"
        )

        configured_floor = re.search(r"--cov-fail-under=(\d+)", pytest_config)
        self.assertIsNotNone(configured_floor)
        assert configured_floor is not None
        self.assertIn(f"configured {configured_floor.group(1)}% floor", quality_gates)
        self.assertIn(f"--cov-fail-under={configured_floor.group(1)}", quality_gates)

    def test_posix_webengine_sandbox_workaround_is_root_only(self):
        runtime_env = (PYTHON_ROOT / "app" / "bootstrap" / "runtime_env.py").read_text(encoding="utf-8")

        posix_start = runtime_env.index('if os.name == "posix":')
        windows_start = runtime_env.index('if os.name == "nt":')
        posix_setup = runtime_env[posix_start:windows_start]
        root_setup_start = posix_setup.index("if is_root:")
        no_sandbox_start = posix_setup.index('"--no-sandbox"')
        self.assertLess(root_setup_start, no_sandbox_start)
        self.assertIn('os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")', posix_setup)
        self.assertIn('os.environ.setdefault("QTWEBENGINE_USE_SANDBOX", "0")', posix_setup)

        windows_setup = runtime_env[windows_start:]
        self.assertIn('BOT_WEBENGINE_DISABLE_SANDBOX', windows_setup)
        self.assertIn('windows_flags.append("--no-sandbox")', windows_setup)
        self.assertIn('os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "0")', windows_setup)
        self.assertIn('os.environ.setdefault("QTWEBENGINE_USE_SANDBOX", "1")', windows_setup)

    def test_all_workflow_actions_are_pinned_to_immutable_commits(self):
        action_pin_pattern = r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)?@[0-9a-f]{40}$"
        for workflow_path in sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml")):
            workflow = workflow_path.read_text(encoding="utf-8")
            references = re.findall(r"(?m)^\s*uses:\s*([^\s#]+)", workflow)
            self.assertTrue(references, workflow_path)
            for reference in references:
                with self.subTest(workflow=workflow_path.name, reference=reference):
                    if reference.startswith("./.github/actions/"):
                        action_dir = (REPO_ROOT / reference[2:]).resolve()
                        allowed_root = (REPO_ROOT / ".github" / "actions").resolve()
                        self.assertTrue(action_dir.is_relative_to(allowed_root), reference)
                        action_manifest = action_dir / "action.yml"
                        self.assertTrue(action_manifest.is_file(), action_manifest)
                        action_references = re.findall(
                            r"(?m)^\s*uses:\s*([^\s#]+)",
                            action_manifest.read_text(encoding="utf-8"),
                        )
                        self.assertTrue(action_references, action_manifest)
                        for action_reference in action_references:
                            self.assertRegex(action_reference, action_pin_pattern)
                    else:
                        self.assertRegex(reference, action_pin_pattern)

    def test_runtime_tool_version_remediations_are_actionable(self):
        module = _load_tool_version_module()

        python_fix = module._runtime_remediation("python", "3.14", "3.12.9")
        node_fix = module._runtime_remediation("node", "26", "20.10.0")

        self.assertIn("Python 3.14", python_fix)
        self.assertIn("python tools/bootstrap_local_dev.py --python-command", python_fix)
        self.assertIn('Languages/Python[desktop,service,dev]', python_fix)
        self.assertIn("Node.js 26", node_fix)
        self.assertIn("OpenJS.NodeJS --exact", node_fix)
        self.assertNotIn("OpenJS.NodeJS.LTS", node_fix)
        self.assertEqual("", module._runtime_remediation("node", "26", "26.1.0"))

    def test_local_dev_bootstrap_plan_installs_python_surface_and_clients(self):
        module = _load_bootstrap_module()

        steps = module.build_bootstrap_steps(
            python_executable="python",
            npm_executable="npm",
            include_python_deps=True,
            include_client_deps=True,
        )
        commands = [" ".join(step.command) for step in steps]

        self.assertTrue(any("pip install --upgrade pip" in command for command in commands))
        self.assertTrue(any("Languages/Python[desktop,service,dev]" in command for command in commands))
        self.assertTrue(any(step.cwd == REPO_ROOT / "apps" / "web-dashboard" for step in steps))
        self.assertTrue(any(step.cwd == REPO_ROOT / "apps" / "mobile-client" for step in steps))

    def test_local_dev_bootstrap_can_scope_to_python_only(self):
        module = _load_bootstrap_module()

        steps = module.build_bootstrap_steps(
            python_executable="python",
            npm_executable="npm",
            include_python_deps=True,
            include_client_deps=False,
        )

        self.assertEqual(2, len(steps))
        self.assertTrue(all("npm" not in step.command for step in steps))

    def test_local_dev_bootstrap_docs_are_discoverable(self):
        docs = {
            "root README": (REPO_ROOT / "README.md").read_text(encoding="utf-8"),
            "contributing": (REPO_ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8"),
            "dependency docs": (REPO_ROOT / "docs" / "DEPENDENCY_REPRODUCIBILITY.md").read_text(encoding="utf-8"),
            "operator runbook": (REPO_ROOT / "docs" / "OPERATOR_RUNBOOK.md").read_text(encoding="utf-8"),
        }

        for docs_text in docs.values():
            self.assertIn("python tools/bootstrap_local_dev.py --dry-run", docs_text)

    def test_contributing_native_workspace_commands_use_existing_paths(self):
        contributing = (REPO_ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")

        self.assertIn("experiments/rust-shells/", contributing)
        self.assertIn("cd experiments/rust-shells", contributing)
        self.assertIn("experiments/native-cpp/", contributing)
        self.assertIn("cmake -S experiments/native-cpp -B build/binance_cpp", contributing)
        self.assertNotIn("Languages/Rust", contributing)
        self.assertNotIn("Languages/C++", contributing)

    def test_runtime_tool_version_checker_reports_expected_shape(self):
        module = _load_tool_version_module()

        payload = module.build_tool_version_report(skip_node=True)
        self.assertIn("ok", payload)
        self.assertIn("remediations", payload)
        self.assertEqual({"python"}, set(payload["checks"]))
        self.assertEqual("3.14", payload["checks"]["python"]["expected"])

    def test_runtime_tool_version_checker_can_probe_selected_python_command(self):
        module = _load_tool_version_module()
        completed = module.subprocess.CompletedProcess(
            ["python"],
            0,
            stdout="3.14.5\n",
            stderr="",
        )

        with mock.patch.object(module.subprocess, "run", return_value=completed):
            payload = module.build_tool_version_report(skip_node=True, python_command=("python",))

        self.assertTrue(payload["checks"]["python"]["ok"])
        self.assertEqual("3.14.5", payload["checks"]["python"]["actual"])
        self.assertEqual("python", payload["checks"]["python"]["command"])

    def test_runtime_tool_version_checker_accepts_supported_compatibility_python(self):
        module = _load_tool_version_module()
        completed = module.subprocess.CompletedProcess(
            ["python"],
            0,
            stdout="3.15.0\n",
            stderr="",
        )

        with mock.patch.object(module.subprocess, "run", return_value=completed):
            payload = module.build_tool_version_report(
                skip_node=True,
                python_command=("python",),
                allow_supported_python=True,
            )

        self.assertTrue(payload["checks"]["python"]["ok"])
        self.assertTrue(payload["checks"]["python"]["supported_compatibility_target"])

    def test_runtime_tool_version_checker_cli_can_enable_supported_compatibility_python(self):
        module = _load_tool_version_module()

        with mock.patch.object(
            module,
            "build_tool_version_report",
            return_value={"ok": True, "checks": {}, "remediations": []},
        ) as report:
            self.assertEqual(
                0,
                module.main(
                    [
                        "--json",
                        "--skip-node",
                        "--python-command",
                        "python",
                        "--allow-supported-python",
                    ]
                ),
            )

        report.assert_called_once_with(
            skip_python=False,
            skip_node=True,
            python_command=("python",),
            allow_supported_python=True,
        )

    def test_runtime_tool_version_checker_cli_accepts_selected_python_command(self):
        module = _load_tool_version_module()

        with mock.patch.object(
            module,
            "build_tool_version_report",
            return_value={"ok": True, "checks": {}, "remediations": []},
        ) as report:
            self.assertEqual(0, module.main(["--json", "--skip-node", "--python-command", "python"]))

        report.assert_called_once_with(skip_python=False, skip_node=True, python_command=("python",))

    def test_local_dev_bootstrap_accepts_explicit_python_command(self):
        module = _load_bootstrap_module()

        steps = module.build_bootstrap_steps(
            python_command=("python",),
            npm_executable="npm",
            include_python_deps=True,
            include_client_deps=False,
        )
        commands = [" ".join(step.command) for step in steps]

        self.assertTrue(all(command.startswith("python ") for command in commands))
        self.assertEqual(("python",), module._split_command("python"))

    def test_local_dev_bootstrap_checks_selected_python_command(self):
        module = _load_bootstrap_module()

        with mock.patch.object(module, "build_tool_version_report", return_value={"remediations": []}) as report:
            remediations = module.runtime_remediations(
                include_python_deps=True,
                include_client_deps=False,
                python_command=("python",),
            )

        self.assertEqual([], remediations)
        report.assert_called_once_with(skip_python=False, skip_node=True, python_command=("python",))

    def test_workspace_cleanup_tool_dry_run_reports_expected_shape(self):
        module = _load_script_module("clean_workspace_artifacts", CLEAN_WORKSPACE_SCRIPT)

        with mock.patch.object(
            module,
            "_ignored_paths",
            return_value=[
                ".vcpkg/",
                "Languages/Python/app/__pycache__/",
                "Languages/Python/.pytest_cache/",
                "Languages/Python/trading_bot_python.egg-info/",
                ".coverage",
                ".vscode/",
                "README.md",
            ],
        ), mock.patch.object(module, "_explicit_generated_artifacts", return_value=[]):
            payload = module.clean_workspace_artifacts(apply=False)
        self.assertFalse(payload["applied"])
        self.assertEqual(5, payload["planned_count"])
        self.assertEqual(
            [
                ".vcpkg/",
                "Languages/Python/app/__pycache__/",
                "Languages/Python/.pytest_cache/",
                "Languages/Python/trading_bot_python.egg-info/",
                ".coverage",
            ],
            payload["planned"],
        )
        self.assertIn("removed_count", payload)

    def test_workspace_cleanup_tool_removes_readonly_generated_cache_files(self):
        module = _load_script_module("clean_workspace_artifacts", CLEAN_WORKSPACE_SCRIPT)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cache_dir = root / ".vcpkg" / ".git" / "objects"
            cache_dir.mkdir(parents=True)
            readonly_file = cache_dir / "object"
            readonly_file.write_text("generated cache", encoding="utf-8")
            os.chmod(readonly_file, 0o444)

            with (
                mock.patch.object(module, "_repo_root", return_value=root),
                mock.patch.object(module, "_ignored_paths", return_value=[".vcpkg/"]),
            ):
                payload = module.clean_workspace_artifacts(apply=True)

            self.assertEqual([".vcpkg/"], payload["removed"])
            self.assertFalse((root / ".vcpkg").exists())

    def test_workspace_cleanup_tool_tolerates_paths_removed_during_apply(self):
        module = _load_script_module("clean_workspace_artifacts", CLEAN_WORKSPACE_SCRIPT)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cache_dir = root / ".ruff_cache"
            cache_dir.mkdir()

            with (
                mock.patch.object(module, "_repo_root", return_value=root),
                mock.patch.object(module, "_ignored_paths", return_value=[".ruff_cache/"]),
                mock.patch.object(module.shutil, "rmtree", side_effect=FileNotFoundError("already gone")),
            ):
                payload = module.clean_workspace_artifacts(apply=True)

            self.assertEqual([], payload["removed"])
            self.assertEqual([{"path": ".ruff_cache/", "reason": "already removed"}], payload["skipped"])

    def test_workspace_cleanup_retry_ignores_disappearing_children(self):
        module = _load_script_module("clean_workspace_artifacts", CLEAN_WORKSPACE_SCRIPT)
        retry = mock.Mock(side_effect=FileNotFoundError("already gone"))
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_path = str(Path(temp_dir) / ".ruff_cache" / ".gitignore")

            module._make_writable_and_retry(retry, missing_path, None)

        retry.assert_not_called()

    def test_workspace_cleanup_tool_expands_collapsed_native_source_sync_artifacts(self):
        module = _load_script_module("clean_workspace_artifacts", CLEAN_WORKSPACE_SCRIPT)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audit_path = root / "artifacts" / "native-source-sync" / "native-source-sync-audit.json"
            audit_path.parent.mkdir(parents=True)
            audit_path.write_text('{"ok": true}', encoding="utf-8")
            nested_plan_path = (
                root
                / "artifacts"
                / "rust-native-runtime-evidence"
                / "rust-native-runtime-evidence-plan.md"
            )
            nested_plan_path.parent.mkdir(parents=True)
            nested_plan_path.write_text("# Rust native runtime evidence plan\n", encoding="utf-8")
            legacy_plan_path = root / "artifacts" / "rust-native-runtime-evidence-plan.md"
            legacy_plan_path.write_text("# Rust native runtime evidence plan\n", encoding="utf-8")

            with (
                mock.patch.object(module, "_repo_root", return_value=root),
                mock.patch.object(module, "_ignored_paths", return_value=["artifacts/"]),
            ):
                dry_run = module.clean_workspace_artifacts(apply=False)

            expected_paths = [
                "artifacts/native-source-sync/native-source-sync-audit.json",
                "artifacts/rust-native-runtime-evidence-plan.md",
                "artifacts/rust-native-runtime-evidence/rust-native-runtime-evidence-plan.md",
            ]
            self.assertEqual(expected_paths, dry_run["planned"])
            self.assertEqual(3, dry_run["planned_count"])

            with (
                mock.patch.object(module, "_repo_root", return_value=root),
                mock.patch.object(module, "_ignored_paths", return_value=["artifacts/"]),
            ):
                payload = module.clean_workspace_artifacts(apply=True)

            self.assertEqual(expected_paths, payload["removed"])
            self.assertFalse(audit_path.exists())
            self.assertFalse(nested_plan_path.exists())
            self.assertFalse(legacy_plan_path.exists())
            self.assertTrue((root / "artifacts").exists())

    def test_workspace_cleanup_removes_nested_release_platform_download_artifacts(self):
        module = _load_script_module("clean_workspace_artifacts", CLEAN_WORKSPACE_SCRIPT)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            download_dir = (
                root
                / "release-platform-evidence"
                / "release-platform-evidence-browser-chrome-ubuntu_24_04_x64"
            )
            download_dir.mkdir(parents=True)
            downloaded_json = download_dir / "browser-chrome-ubuntu_24_04_x64.json"
            downloaded_json.write_text('{"status": "passed"}\n', encoding="utf-8")

            with (
                mock.patch.object(module, "_repo_root", return_value=root),
                mock.patch.object(module, "_ignored_paths", return_value=[]),
            ):
                dry_run = module.clean_workspace_artifacts(apply=False)
                payload = module.clean_workspace_artifacts(apply=True)

            expected_path = (
                "release-platform-evidence/"
                "release-platform-evidence-browser-chrome-ubuntu_24_04_x64"
            )
            self.assertEqual([expected_path], dry_run["planned"])
            self.assertEqual([expected_path], payload["removed"])
            self.assertFalse(download_dir.exists())
            self.assertFalse(downloaded_json.exists())
            self.assertTrue((root / "release-platform-evidence").exists())

    def test_workspace_cleanup_removes_nested_rust_runtime_download_artifacts(self):
        module = _load_script_module("clean_workspace_artifacts", CLEAN_WORKSPACE_SCRIPT)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            download_dir = (
                root
                / "artifacts"
                / "rust-native-runtime-evidence"
                / "downloads"
                / "run-123"
            )
            download_dir.mkdir(parents=True)
            downloaded_json = download_dir / "rust-native-live-market-data-smoke.json"
            downloaded_json.write_text('{"status": "passed"}\n', encoding="utf-8")

            with (
                mock.patch.object(module, "_repo_root", return_value=root),
                mock.patch.object(module, "_ignored_paths", return_value=[]),
            ):
                dry_run = module.clean_workspace_artifacts(apply=False)
                payload = module.clean_workspace_artifacts(apply=True)

            expected_path = "artifacts/rust-native-runtime-evidence/downloads"
            self.assertEqual([expected_path], dry_run["planned"])
            self.assertEqual([expected_path], payload["removed"])
            self.assertFalse(download_dir.exists())
            self.assertFalse(downloaded_json.exists())
            self.assertTrue((root / "artifacts" / "rust-native-runtime-evidence").exists())

    def test_workspace_cleanup_tool_can_opt_in_to_stale_rust_runtime_evidence(self):
        module = _load_script_module("clean_workspace_artifacts", CLEAN_WORKSPACE_SCRIPT)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evidence_dir = root / "artifacts" / "rust-native-runtime-evidence"
            evidence_dir.mkdir(parents=True)
            release_evidence_dir = root / "release-platform-evidence"
            release_evidence_dir.mkdir()
            stale_path = evidence_dir / "rust-native-live-market-data-smoke.json"
            current_path = evidence_dir / "rust-native-live-stream-recovery.json"
            unknown_path = evidence_dir / "custom-runtime-evidence.json"
            stale_release_path = release_evidence_dir / "browser-chrome-windows_11_x64.json"
            current_release_path = release_evidence_dir / "browser-edge-windows_11_x64.json"
            current_hash = "b" * 64
            stale_path.write_text(
                json.dumps(
                    {
                        "evidence_id": "rust-native-live-market-data-smoke",
                        "commit": "old-commit",
                        "python_source_contract_hash": "a" * 64,
                    }
                ),
                encoding="utf-8",
            )
            current_path.write_text(
                json.dumps(
                    {
                        "evidence_id": "rust-native-live-stream-recovery",
                        "commit": "current-commit",
                        "python_source_contract_hash": current_hash,
                    }
                ),
                encoding="utf-8",
            )
            unknown_path.write_text(
                json.dumps(
                    {
                        "evidence_id": "custom-runtime-evidence",
                        "commit": "old-commit",
                        "python_source_contract_hash": "a" * 64,
                    }
                ),
                encoding="utf-8",
            )
            stale_release_path.write_text(
                json.dumps(
                    {
                        "target_id": "browser-chrome-windows_11_x64",
                        "commit": "old-commit",
                        "source_tree_clean": False,
                        "python_source_contract_hash": "a" * 64,
                    }
                ),
                encoding="utf-8",
            )
            current_release_path.write_text(
                json.dumps(
                    {
                        "target_id": "browser-edge-windows_11_x64",
                        "commit": "current-commit",
                        "source_tree_clean": True,
                        "python_source_contract_hash": current_hash,
                        "native_source_sync": {"contract_hash": current_hash},
                        "runtime_ready_claimed": False,
                    }
                ),
                encoding="utf-8",
            )

            with (
                mock.patch.object(module, "_repo_root", return_value=root),
                mock.patch.object(module, "_ignored_paths", return_value=["artifacts/", "release-platform-evidence/"]),
                mock.patch.object(module, "_current_runtime_evidence_binding", return_value=("current-commit", current_hash)),
            ):
                default_dry_run = module.clean_workspace_artifacts(apply=False)
                stale_dry_run = module.clean_workspace_artifacts(
                    apply=False,
                    include_stale_runtime_evidence=True,
                )
                payload = module.clean_workspace_artifacts(
                    apply=True,
                    include_stale_runtime_evidence=True,
                )

            expected_path = "artifacts/rust-native-runtime-evidence/rust-native-live-market-data-smoke.json"
            expected_release_path = "release-platform-evidence/browser-chrome-windows_11_x64.json"
            self.assertNotIn(expected_path, default_dry_run["planned"])
            self.assertNotIn(expected_release_path, default_dry_run["planned"])
            self.assertEqual([expected_path, expected_release_path], stale_dry_run["planned"])
            self.assertEqual([expected_path, expected_release_path], payload["removed"])
            self.assertFalse(stale_path.exists())
            self.assertFalse(stale_release_path.exists())
            self.assertTrue(current_path.exists())
            self.assertTrue(current_release_path.exists())
            self.assertTrue(unknown_path.exists())

    def test_workspace_cleanup_can_opt_in_to_stale_operational_readiness_evidence(self):
        module = _load_script_module("clean_workspace_artifacts", CLEAN_WORKSPACE_SCRIPT)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evidence_dir = root / "artifacts" / "operational-readiness"
            evidence_dir.mkdir(parents=True)
            stale_path = evidence_dir / "service-config-backup-restore.json"
            current_path = evidence_dir / "incident-audit-continuity.json"
            unknown_path = evidence_dir / "local-not-in-policy.json"
            current_hash = "b" * 64
            stale_path.write_text(
                json.dumps(
                    {
                        "evidence_id": "service-config-backup-restore",
                        "commit": "old-commit",
                        "policy_sha256": "a" * 64,
                        "promotion_eligible": False,
                        "source_tree_clean": False,
                        "status": "pass",
                    }
                ),
                encoding="utf-8",
            )
            current_path.write_text(
                json.dumps(
                    {
                        "evidence_id": "incident-audit-continuity",
                        "commit": "current-commit",
                        "policy_sha256": current_hash,
                        "promotion_eligible": True,
                        "source_tree_clean": True,
                        "status": "pass",
                    }
                ),
                encoding="utf-8",
            )
            unknown_path.write_text("{}", encoding="utf-8")

            with (
                mock.patch.object(module, "_repo_root", return_value=root),
                mock.patch.object(
                    module,
                    "_ignored_paths",
                    return_value=["artifacts/operational-readiness/"],
                ),
                mock.patch.object(
                    module,
                    "_current_operational_readiness_binding",
                    return_value=("current-commit", current_hash, True),
                ),
                mock.patch.object(
                    module,
                    "_operational_readiness_required_filenames",
                    return_value={
                        "service-config-backup-restore.json",
                        "incident-audit-continuity.json",
                    },
                ),
            ):
                default_dry_run = module.clean_workspace_artifacts(apply=False)
                stale_dry_run = module.clean_workspace_artifacts(
                    apply=False,
                    include_stale_runtime_evidence=True,
                )
                payload = module.clean_workspace_artifacts(
                    apply=True,
                    include_stale_runtime_evidence=True,
                )

            expected_path = "artifacts/operational-readiness/service-config-backup-restore.json"
            self.assertNotIn(expected_path, default_dry_run["planned"])
            self.assertEqual([expected_path], stale_dry_run["planned"])
            self.assertEqual([expected_path], payload["removed"])
            self.assertFalse(stale_path.exists())
            self.assertTrue(current_path.exists())
            self.assertTrue(unknown_path.exists())

    def test_workspace_hygiene_classifier_includes_generated_caches_not_editor_settings(self):
        module = _load_script_module("audit_workspace_hygiene", REPO_ROOT / "tools" / "audit_workspace_hygiene.py")

        noisy_paths = [
            ".ruff_cache/",
            "Languages/Python/.mypy_cache/",
            "Languages/Python/app/__pycache__/",
            "Languages/Python/trading_core/__pycache__/strategy.cpython-312.pyc",
            "Languages/Python/trading_bot_python.egg-info/",
            ".coverage",
            "coverage.xml",
            "aqtinstall.log",
            "artifacts/native-source-sync/native-source-sync-audit.json",
        ]
        for path in noisy_paths:
            with self.subTest(path=path):
                self.assertTrue(module.is_noisy_ignored_path(path))

        self.assertFalse(module.is_noisy_ignored_path(".vscode/settings.json"))
        self.assertFalse(module.is_noisy_ignored_path("Languages/Python/.vscode/settings.json"))

    def test_workspace_hygiene_summary_reports_not_ok_when_noisy_artifacts_exist(self):
        module = _load_script_module("audit_workspace_hygiene", REPO_ROOT / "tools" / "audit_workspace_hygiene.py")

        def fake_git_lines(*args: str):
            if args == ("status", "--ignored", "--short"):
                return ["!! .ruff_cache/", "!! .vscode/settings.json"]
            if args == ("ls-files",):
                return ["README.md"]
            return []

        with mock.patch.object(module, "_git_lines", side_effect=fake_git_lines):
            payload = module.ignored_artifact_summary()

        self.assertFalse(payload["ok"])
        self.assertEqual(1, payload["noisy_artifact_count"])
        self.assertEqual([".ruff_cache/"], payload["noisy_artifacts"])

    def test_workspace_hygiene_summary_rejects_tracked_generated_files(self):
        module = _load_script_module("audit_workspace_hygiene_tracked", REPO_ROOT / "tools" / "audit_workspace_hygiene.py")

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            generated = root / "coverage.json"
            generated.write_text("{}", encoding="utf-8")

            def fake_git_lines(*args: str):
                if args == ("status", "--ignored", "--short"):
                    return []
                if args == ("ls-files",):
                    return ["coverage.json"]
                return []

            with (
                mock.patch.object(module, "_repo_root", return_value=root),
                mock.patch.object(module, "_git_lines", side_effect=fake_git_lines),
            ):
                payload = module.ignored_artifact_summary()

        self.assertFalse(payload["ok"])
        self.assertEqual(1, payload["tracked_generated_artifact_count"])
        self.assertEqual(["coverage.json"], payload["tracked_generated_artifacts"])
        self.assertEqual(["coverage.json"], payload["noisy_artifacts"])

    def test_risky_pattern_audit_summary_reports_hotspots_without_full_finding_dump(self):
        module = _load_script_module("audit_risky_patterns", RISKY_PATTERN_SCRIPT)

        payload = module._summary_report(module.audit_risky_patterns())
        self.assertIn("finding_count", payload)
        self.assertIn("severity_counts", payload)
        self.assertIn("top_paths", payload)
        self.assertNotIn("findings", payload)
        self.assertNotIn("todo_marker", payload.get("counts", {}))

    def test_client_dependency_lock_checker_reports_client_lock_state(self):
        module = _load_script_module("check_client_dependency_locks", CLIENT_LOCK_SCRIPT)

        payload = module.check_client_dependency_locks(REPO_ROOT)
        self.assertIn("clients", payload)
        self.assertIn("errors", payload)
        self.assertTrue(any(item["path"] == "apps/mobile-client" for item in payload["clients"]))
        if not (REPO_ROOT / "apps" / "mobile-client" / "package-lock.json").is_file():
            self.assertIn("apps/mobile-client/package-lock.json is missing", payload["errors"])
        else:
            self.assertEqual([], payload["errors"])

    def test_client_packages_declare_node_engine_and_package_manager(self):
        for path in (
            REPO_ROOT / "apps" / "web-dashboard" / "package.json",
            REPO_ROOT / "apps" / "mobile-client" / "package.json",
        ):
            with self.subTest(path=path):
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual("npm@11.6.2", payload["packageManager"])
                self.assertEqual(">=26 <27", payload["engines"]["node"])

        self.assertTrue((REPO_ROOT / "apps" / "web-dashboard" / "package-lock.json").is_file())

    def test_python_source_compile_check_runs_without_writing_bytecode(self):
        module = _load_script_module("check_python_sources_compile", COMPILE_CHECK_SCRIPT)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_dir = root / "pkg"
            source_dir.mkdir()
            source_file = source_dir / "module.py"
            source_file.write_text("VALUE = 1\n", encoding="utf-8")

            payload = module.check_python_sources_compile(["pkg"], root=root)

            self.assertTrue(payload["ok"])
            self.assertEqual(1, payload["checked_count"])
            self.assertFalse((source_dir / "__pycache__").exists())

    def test_python_source_compile_check_reports_syntax_errors(self):
        module = _load_script_module("check_python_sources_compile", COMPILE_CHECK_SCRIPT)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_file = root / "broken.py"
            source_file.write_text("def broken(:\n    pass\n", encoding="utf-8")

            payload = module.check_python_sources_compile(["broken.py"], root=root)

            self.assertFalse(payload["ok"])
            self.assertEqual(1, len(payload["errors"]))
            self.assertEqual("broken.py", payload["errors"][0]["path"])


if __name__ == "__main__":
    unittest.main()
