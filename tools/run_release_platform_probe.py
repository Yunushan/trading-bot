#!/usr/bin/env python3
"""Run release-platform smoke probes and write a real evidence artifact."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

try:
    from audit_native_source_sync import audit_native_source_sync
    from check_generated_evidence_source_control import generated_evidence_write_guard
    from check_release_platform_matrix import (
        DEFAULT_MATRIX_PATH,
        PROMOTION_SOURCE_TREE_IGNORED_PATHS,
    )
    from check_release_platform_matrix import _load_json, _validate_matrix
    from release_browser_contract_commands import (
        browser_contract_command_args,
        browser_contract_missing_command_message,
    )
    from release_browser_contract_commands import browser_host_from_observed_platform
    from release_browser_contract_commands import (
        builtin_browser_contract_targets_for_host,
    )
except ModuleNotFoundError:  # pragma: no cover - exercised when imported as tools.*
    from tools.audit_native_source_sync import audit_native_source_sync
    from tools.check_generated_evidence_source_control import (
        generated_evidence_write_guard,
    )
    from tools.check_release_platform_matrix import (
        DEFAULT_MATRIX_PATH,
        PROMOTION_SOURCE_TREE_IGNORED_PATHS,
    )
    from tools.check_release_platform_matrix import _load_json, _validate_matrix
    from tools.release_browser_contract_commands import (
        browser_contract_command_args,
        browser_contract_missing_command_message,
    )
    from tools.release_browser_contract_commands import (
        browser_host_from_observed_platform,
    )
    from tools.release_browser_contract_commands import (
        builtin_browser_contract_targets_for_host,
    )

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = REPO_ROOT / "Languages" / "Python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.native_parity import native_python_source_contract_hash  # noqa: E402


DEFAULT_DESKTOP_RELEASE_SMOKE_COMMAND = (
    sys.executable,
    "tools/check_native_cpp.py",
    "--config",
    "Release",
    "--timeout",
    "600",
)


def _repo_root() -> Path:
    return REPO_ROOT


def _current_git_commit() -> str:
    try:
        output = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_repo_root(),
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown-local-commit"
    return output.stdout.strip() or "unknown-local-commit"


def _source_tree_status_command(untracked_files: str) -> list[str]:
    command = [
        "git",
        "status",
        "--porcelain",
        f"--untracked-files={untracked_files}",
        "--",
        ".",
    ]
    command.extend(f":(exclude){path}" for path in PROMOTION_SOURCE_TREE_IGNORED_PATHS)
    return command


def _source_tree_status_clean(untracked_files: str) -> bool:
    try:
        output = subprocess.run(
            _source_tree_status_command(untracked_files),
            cwd=_repo_root(),
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return not output.stdout.strip()


def _source_tree_clean() -> bool:
    return _source_tree_status_clean("no") and _source_tree_status_clean("all")


def _native_source_sync_binding() -> dict[str, object]:
    return {
        "required": True,
        "audit_artifact": "native-source-sync-audit",
        "audit_path": "artifacts/native-source-sync/native-source-sync-audit.json",
        "python_source_of_truth": "Languages/Python/app/native_parity.py",
        "contract_hash": native_python_source_contract_hash(),
        "surface_contract_required": True,
    }


def _native_source_sync_guard() -> dict[str, Any]:
    audit = audit_native_source_sync()
    surface_contract = audit.get("surface_contract")
    surface_contract_ok = (
        isinstance(surface_contract, dict) and surface_contract.get("ok") is True
    )
    surface_contract_issues = (
        [
            str(issue)
            for issue in surface_contract.get("issues", [])
            if str(issue).strip()
        ]
        if isinstance(surface_contract, dict)
        else ["native source sync surface_contract is missing"]
    )
    audit_issues = [
        str(issue) for issue in audit.get("issues", []) if str(issue).strip()
    ]
    issues = [*audit_issues]
    if not surface_contract_ok:
        issues.extend(surface_contract_issues)
    return {
        "ok": bool(audit.get("ok")) and surface_contract_ok,
        "audit_artifact": "native-source-sync-audit",
        "audit_path": "artifacts/native-source-sync/native-source-sync-audit.json",
        "python_source_of_truth": "Languages/Python/app/native_parity.py",
        "contract_hash": audit.get("contract_hash"),
        "surface_contract_ok": surface_contract_ok,
        "generated_artifact_count": len(audit.get("generated", []) or []),
        "consumer_surface_count": len(audit.get("consumers", []) or []),
        "issues": issues,
    }


def _find_target(target_id: str, matrix_path: Path) -> dict[str, Any]:
    matrix = _load_json(matrix_path)
    platform_targets, browser_targets, issues = _validate_matrix(matrix)
    if issues:
        raise RuntimeError("matrix is invalid: " + "; ".join(issues))
    for target in platform_targets + browser_targets:
        if target["id"] == target_id:
            return target
    raise RuntimeError(f"unknown target id: {target_id}")


def _matrix_targets(
    matrix_path: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    matrix = _load_json(matrix_path)
    platform_targets, browser_targets, issues = _validate_matrix(matrix)
    if issues:
        raise RuntimeError("matrix is invalid: " + "; ".join(issues))
    return platform_targets, browser_targets


def _run_command(
    name: str,
    command: list[str],
    *,
    cwd: Path,
    timeout: int = 240,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    started = time.time()
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "name": name,
            "status": "failed",
            "command": command,
            "duration_seconds": round(time.time() - started, 3),
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
        }
    return {
        "name": name,
        "status": "passed" if result.returncode == 0 else "failed",
        "command": command,
        "duration_seconds": round(time.time() - started, 3),
        "returncode": result.returncode,
        "stdout": "\n".join(result.stdout.strip().splitlines()[-40:]),
        "stderr": "\n".join(result.stderr.strip().splitlines()[-40:]),
    }


def _rust_release_binary(root: Path, name: str) -> Path:
    suffix = ".exe" if sys.platform == "win32" else ""
    return (
        root / "experiments" / "rust-shells" / "target" / "release" / f"{name}{suffix}"
    )


def _rust_native_build_smoke(
    cargo: str,
    target: dict[str, Any],
    *,
    root: Path,
) -> dict[str, Any]:
    started = time.time()
    steps: list[dict[str, Any]] = []
    commands = (
        (
            "rust-workspace-tests",
            [
                cargo,
                "test",
                "--manifest-path",
                "experiments/rust-shells/Cargo.toml",
                "--locked",
                "--workspace",
            ],
        ),
        (
            "rust-release-build",
            [
                cargo,
                "build",
                "--manifest-path",
                "experiments/rust-shells/Cargo.toml",
                "--locked",
                "--release",
                "--package",
                "trading-bot-rust",
                "--package",
                "trading-bot-tauri-desktop",
            ],
        ),
    )
    for name, command in commands:
        result = _run_command(name, command, cwd=root, timeout=1800)
        steps.append(result)
        if result.get("status") != "passed":
            return {
                "name": "native-build-smoke",
                "status": "failed",
                "duration_seconds": round(time.time() - started, 3),
                "stderr": f"{name} failed",
                "steps": steps,
            }

    target_id = str(target.get("id") or "unknown-target")
    package_evidence = (
        root
        / "build"
        / "release-platform-evidence"
        / f"rust-package-smoke-{target_id}.json"
    )
    package_command = [
        sys.executable,
        "tools/write_rust_package_smoke_evidence.py",
        "--rust-cli",
        str(_rust_release_binary(root, "trading-bot-rust")),
        "--tauri-desktop",
        str(_rust_release_binary(root, "trading-bot-tauri-desktop")),
        "--output",
        str(package_evidence),
        "--source-revision",
        _current_git_commit(),
        "--platform",
        str(target.get("family") or platform.system()),
        "--architecture",
        str(target.get("architecture") or platform.machine()),
        "--require-clean-source",
    ]
    package_result = _run_command(
        "rust-package-smoke",
        package_command,
        cwd=root,
        timeout=180,
    )
    steps.append(package_result)
    return {
        "name": "native-build-smoke",
        "status": "passed" if package_result.get("status") == "passed" else "failed",
        "duration_seconds": round(time.time() - started, 3),
        "stderr": ""
        if package_result.get("status") == "passed"
        else "rust-package-smoke failed",
        "package_evidence": str(package_evidence),
        "steps": steps,
    }


def _shell_command_from_env(name: str) -> list[str] | None:
    raw = str(os.environ.get(name) or "").strip()
    if not raw:
        return None
    if sys.platform == "win32":
        return ["cmd", "/c", raw]
    return ["sh", "-lc", raw]


def _os_release() -> dict[str, str]:
    os_release = Path("/etc/os-release")
    if not os_release.is_file():
        return {}
    parsed: dict[str, str] = {}
    try:
        lines = os_release.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {}
    for line in lines:
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        parsed[key.strip()] = value.strip().strip('"')
    return parsed


def _observed_platform() -> dict[str, Any]:
    os_release = _os_release()
    return {
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "normalized_architecture": _normalize_architecture(platform.machine()),
        "processor": platform.processor(),
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "os_release_id": os_release.get("ID", ""),
        "os_release_id_like": os_release.get("ID_LIKE", ""),
        "os_release_version_id": os_release.get("VERSION_ID", ""),
        "macos_version": platform.mac_ver()[0],
    }


def _current_browser_host(observed: dict[str, Any] | None = None) -> str:
    return browser_host_from_observed_platform(dict(observed or _observed_platform()))


def _local_browser_targets(matrix_path: Path) -> list[dict[str, Any]]:
    _platform_targets, browser_targets = _matrix_targets(matrix_path)
    host = _current_browser_host()
    npm = shutil.which("npm.cmd" if sys.platform == "win32" else "npm")
    if not host or not npm:
        return []
    return [
        target
        for target in builtin_browser_contract_targets_for_host(browser_targets, host)
        if browser_contract_command_args(target, npm_executable=npm) is not None
    ]


def _normalize_architecture(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    if normalized in {"amd64", "x86_64", "x64"}:
        return "x64"
    if normalized in {"arm64", "aarch64"}:
        return "arm64"
    if normalized in {"x86", "i386", "i686"}:
        return "x86"
    if normalized.startswith("armv7") or normalized.startswith("armv6"):
        return "arm32"
    return normalized


def _expected_architecture(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"x64", "x86", "arm32", "arm64"}:
        return normalized
    if normalized.startswith("x86_64"):
        return "x64"
    if "arm64" in normalized:
        return "arm64"
    return _normalize_architecture(normalized)


def _linux_distribution_matches(
    family: str, version: str, observed: dict[str, Any]
) -> bool:
    distro_id = str(observed.get("os_release_id") or "").lower()
    distro_like = str(observed.get("os_release_id_like") or "").lower()
    version_id = str(observed.get("os_release_version_id") or "")
    if family == "ubuntu":
        return distro_id == "ubuntu" and version_id.startswith(version)
    if family == "rhel":
        distro_tokens = {distro_id, *distro_like.split()}
        return (
            bool({"rhel", "fedora"} & distro_tokens)
            and version_id.split(".", 1)[0] == version
        )
    return False


def _platform_match_issues(
    target: dict[str, Any], observed: dict[str, Any]
) -> list[str]:
    family = str(target.get("family") or "").lower()
    version = str(target.get("version") or "")
    expected_arch = _expected_architecture(str(target.get("architecture") or ""))
    observed_arch = str(observed.get("normalized_architecture") or "")
    system = str(observed.get("system") or "")
    issues: list[str] = []

    if expected_arch and observed_arch != expected_arch:
        issues.append(
            f"architecture mismatch: expected {expected_arch}, observed {observed_arch or 'unknown'}"
        )

    if family == "windows":
        if system != "Windows":
            issues.append(
                f"system mismatch: expected Windows, observed {system or 'unknown'}"
            )
        if str(observed.get("release") or "") != version:
            issues.append(
                f"Windows release mismatch: expected {version}, observed {observed.get('release') or 'unknown'}"
            )
    elif family == "macos":
        if system != "Darwin":
            issues.append(
                f"system mismatch: expected Darwin/macOS, observed {system or 'unknown'}"
            )
        macos_major = str(observed.get("macos_version") or "").split(".", 1)[0]
        if macos_major != version:
            issues.append(
                f"macOS major version mismatch: expected {version}, observed {macos_major or 'unknown'}"
            )
    elif family in {"ubuntu", "rhel"}:
        if system != "Linux":
            issues.append(
                f"system mismatch: expected Linux, observed {system or 'unknown'}"
            )
        elif not _linux_distribution_matches(family, version, observed):
            issues.append(
                "Linux distribution mismatch: expected "
                f"{family} {version}, observed "
                f"{observed.get('os_release_id') or 'unknown'} "
                f"{observed.get('os_release_version_id') or 'unknown'}"
            )
    elif family in {"freebsd", "openbsd", "netbsd"}:
        expected_system = family.capitalize()
        if system.lower() != family:
            issues.append(
                f"system mismatch: expected {expected_system}, observed {system or 'unknown'}"
            )
    elif family == "android":
        if system not in {"Android", "Linux"}:
            issues.append(
                f"system mismatch: expected Android runtime, observed {system or 'unknown'}"
            )
        android_root_present = bool(
            os.environ.get("ANDROID_ROOT") or os.environ.get("ANDROID_DATA")
        )
        if (
            not android_root_present
            and str(observed.get("os_release_id") or "").lower() != "android"
        ):
            issues.append(
                "Android runtime marker missing: ANDROID_ROOT/ANDROID_DATA or os-release ID android required"
            )
    elif family == "ios":
        if system not in {"iOS", "Darwin"}:
            issues.append(
                f"system mismatch: expected iOS runtime, observed {system or 'unknown'}"
            )
        if not (os.environ.get("SIMULATOR_UDID") or os.environ.get("IOS_DEVICE_NAME")):
            issues.append(
                "iOS runtime marker missing: SIMULATOR_UDID or IOS_DEVICE_NAME required"
            )
    else:
        issues.append(
            f"unsupported platform family for target matching: {family or 'unknown'}"
        )
    return issues


def _platform_probe_result(target: dict[str, Any]) -> dict[str, Any]:
    observed = _observed_platform()
    issues = _platform_match_issues(target, observed)
    return {
        "name": "platform-probe",
        "status": "passed" if not issues else "failed",
        "observed": observed,
        "target_match": {
            "matched": not issues,
            "expected": {
                "family": target.get("family"),
                "version": target.get("version"),
                "architecture": target.get("architecture"),
                "normalized_architecture": _expected_architecture(
                    str(target.get("architecture") or "")
                ),
            },
            "issues": issues,
        },
    }


def _suite_results(target: dict[str, Any], *, root: Path) -> list[dict[str, Any]]:
    suites = [str(item) for item in target.get("test_suites", [])]
    results: list[dict[str, Any]] = []

    if "platform-probe" in suites:
        results.append(_platform_probe_result(target))

    if "python-service-contract" in suites:
        results.append(
            _run_command(
                "python-service-contract",
                [
                    sys.executable,
                    "tools/check_python_sources_compile.py",
                    "apps/service-api/main.py",
                    "Languages/Python/app/service",
                    "Languages/Python/app/settings",
                    "Languages/Python/trading_core",
                ],
                cwd=root,
            )
        )
        results.append(
            _run_command(
                "python-service-healthcheck",
                [sys.executable, "apps/service-api/main.py", "--healthcheck"],
                cwd=root,
            )
        )

    if "desktop-release-smoke" in suites:
        command = _shell_command_from_env("TB_RELEASE_DESKTOP_SMOKE_COMMAND") or list(
            DEFAULT_DESKTOP_RELEASE_SMOKE_COMMAND
        )
        results.append(
            _run_command("desktop-release-smoke", command, cwd=root, timeout=900)
        )

    if "native-build-smoke" in suites:
        cargo = shutil.which("cargo")
        if cargo:
            workspace_check = _run_command(
                "rust-workspace-check",
                [
                    cargo,
                    "check",
                    "--manifest-path",
                    "experiments/rust-shells/Cargo.toml",
                    "--locked",
                    "--workspace",
                ],
                cwd=root,
                timeout=900,
            )
            results.append(workspace_check)
            if workspace_check.get("status") == "passed":
                results.append(_rust_native_build_smoke(cargo, target, root=root))
            else:
                results.append(
                    {
                        "name": "native-build-smoke",
                        "status": "failed",
                        "stderr": "rust-workspace-check failed",
                        "steps": [],
                    }
                )
        else:
            results.append(
                {
                    "name": "native-build-smoke",
                    "status": "failed",
                    "stderr": "cargo is not on PATH",
                }
            )

    if "mobile-client-contract" in suites:
        npm = shutil.which("npm.cmd" if sys.platform == "win32" else "npm")
        if npm:
            results.append(
                _run_command(
                    "mobile-client-contract",
                    [npm, "test"],
                    cwd=root / "apps" / "mobile-client",
                )
            )
        else:
            results.append(
                {
                    "name": "mobile-client-contract",
                    "status": "failed",
                    "stderr": "npm is not on PATH",
                }
            )

    if "browser-contract" in suites:
        command = _shell_command_from_env("TB_BROWSER_TEST_COMMAND")
        if command is None:
            npm = shutil.which("npm.cmd" if sys.platform == "win32" else "npm")
            if npm:
                command = browser_contract_command_args(target, npm_executable=npm)
        if command is None:
            results.append(
                {
                    "name": "browser-contract",
                    "status": "failed",
                    "stderr": browser_contract_missing_command_message(target),
                }
            )
        else:
            results.append(
                _run_command("browser-contract", command, cwd=root, timeout=900)
            )

    return results


def _run_probe(target: dict[str, Any], *, output: Path, root: Path) -> dict[str, Any]:
    output = output if output.is_absolute() else root / output
    source_control_write_guard = generated_evidence_write_guard(
        [output],
        root=root,
        require_generated_destinations=True,
    )
    if not source_control_write_guard["ok"]:
        return {
            "ok": False,
            "target_id": str(target.get("id") or ""),
            "output": str(output),
            "source_control_write_guard": source_control_write_guard,
            "issues": [str(issue) for issue in source_control_write_guard["issues"]],
        }

    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    suite_results = _suite_results(target, root=root)
    ok = bool(suite_results) and all(
        item.get("status") == "passed" for item in suite_results
    )
    payload = {
        "target_id": str(target.get("id") or ""),
        "status": "passed" if ok else "failed",
        "started_at": started,
        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "commit": _current_git_commit(),
        "source_tree_clean": _source_tree_clean(),
        "python_source_contract_hash": native_python_source_contract_hash(),
        "native_source_sync": _native_source_sync_binding(),
        "runtime_ready_claimed": False,
        "secrets_redacted": True,
        "target": target,
        "suite_results": suite_results,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    failed_suites = [
        {
            key: item[key]
            for key in ("name", "status", "returncode", "stderr", "stdout")
            if key in item
        }
        for item in suite_results
        if item.get("status") != "passed"
    ]
    return {
        "ok": ok,
        "target_id": payload["target_id"],
        "output": str(output),
        "source_control_write_guard": source_control_write_guard,
        "failed_suites": failed_suites,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target-id", help="Target id from tools/check_release_platform_matrix.py."
    )
    parser.add_argument(
        "--matrix",
        default=str(DEFAULT_MATRIX_PATH),
        help="Path to release platform matrix JSON.",
    )
    parser.add_argument(
        "--output", help="Evidence JSON path to write for a single --target-id run."
    )
    parser.add_argument(
        "--output-dir",
        default="release-platform-evidence",
        help="Directory for --local-browser-targets evidence JSON files.",
    )
    parser.add_argument(
        "--list-local-browser-targets",
        action="store_true",
        help="Print browser target ids that match this host and have checked-in contract commands.",
    )
    parser.add_argument(
        "--local-browser-targets",
        action="store_true",
        help="Run all browser targets that match this host and have checked-in contract commands.",
    )
    parser.add_argument(
        "--require-clean-source",
        action="store_true",
        help="Refuse to write evidence unless the source tree is clean for promotion validation.",
    )
    parser.add_argument(
        "--require-native-source-sync",
        action="store_true",
        help="Refuse to write evidence unless the Python-owned native source-sync audit passes.",
    )
    args = parser.parse_args(argv)

    root = _repo_root()
    matrix_path = Path(args.matrix)

    if args.list_local_browser_targets:
        targets = _local_browser_targets(matrix_path)
        payload = {
            "ok": True,
            "host": _current_browser_host(),
            "target_ids": [str(target["id"]) for target in targets],
            "count": len(targets),
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    if args.require_clean_source and not _source_tree_clean():
        payload = {
            "ok": False,
            "source_tree_clean": False,
            "issues": [
                "source tree must be clean when --require-clean-source is used; "
                "commit or remove source changes before collecting promotion evidence"
            ],
        }
        if args.local_browser_targets:
            payload["host"] = _current_browser_host()
        if args.target_id:
            payload["target_id"] = args.target_id
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 1

    if args.require_native_source_sync:
        native_source_sync_guard = _native_source_sync_guard()
        if not native_source_sync_guard["ok"]:
            payload = {
                "ok": False,
                "source_tree_clean": _source_tree_clean(),
                "native_source_sync_guard": native_source_sync_guard,
                "issues": [
                    "native source sync audit must pass when --require-native-source-sync is used; "
                    "regenerate C++/Rust/Tauri parity artifacts from Languages/Python/app/native_parity.py "
                    "before collecting promotion evidence",
                    *[str(issue) for issue in native_source_sync_guard["issues"]],
                ],
            }
            if args.local_browser_targets:
                payload["host"] = _current_browser_host()
            if args.target_id:
                payload["target_id"] = args.target_id
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 1

    if args.local_browser_targets:
        targets = _local_browser_targets(matrix_path)
        output_dir = Path(args.output_dir)
        results = [
            _run_probe(target, output=output_dir / f"{target['id']}.json", root=root)
            for target in targets
        ]
        ok = bool(results) and all(bool(result.get("ok")) for result in results)
        print(
            json.dumps(
                {
                    "ok": ok,
                    "host": _current_browser_host(),
                    "count": len(results),
                    "outputs": results,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if ok else 1

    if not args.target_id or not args.output:
        parser.error(
            "--target-id and --output are required unless listing or running local browser targets"
        )

    target = _find_target(args.target_id, matrix_path)
    result = _run_probe(target, output=Path(args.output), root=root)
    print(json.dumps(result, indent=2, sort_keys=True))
    ok = bool(result["ok"])
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
