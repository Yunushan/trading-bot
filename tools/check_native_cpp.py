from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _display_command(command: list[str]) -> str:
    return " ".join(command)


def _run_step(name: str, command: list[str], *, cwd: Path, timeout: int) -> dict[str, object]:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "name": name,
            "command": _display_command(command),
            "ok": False,
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
        }
    return {
        "name": name,
        "command": _display_command(command),
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def _default_build_dir(root: Path) -> Path:
    return root / "build" / "binance_cpp_sync_check"


def _cmake_generator_args() -> list[str]:
    if sys.platform != "win32":
        return []
    return []


def check_native_cpp(
    *,
    build_dir: Path,
    config: str,
    require_webengine: bool,
    enable_qt_deploy_script: bool | None,
    qt_version: str | None,
    timeout: int,
) -> dict[str, object]:
    root = _repo_root()
    cmake = shutil.which("cmake")
    ctest = shutil.which("ctest")
    if not cmake:
        return {
            "ok": False,
            "build_dir": str(build_dir),
            "steps": [],
            "remediation": "Install CMake before running native C++ checks.",
        }
    if not ctest:
        return {
            "ok": False,
            "build_dir": str(build_dir),
            "steps": [],
            "remediation": "Install CTest/CMake before running native C++ checks.",
        }

    configure = [
        cmake,
        "-S",
        str(root / "experiments" / "native-cpp"),
        "-B",
        str(build_dir),
        f"-DTB_REQUIRE_QT_WEBENGINE={'ON' if require_webengine else 'OFF'}",
        *_cmake_generator_args(),
    ]
    if qt_version:
        configure.append(f"-DTB_QT_VERSION={qt_version}")
    if enable_qt_deploy_script is not None:
        configure.append(f"-DTB_ENABLE_QT_DEPLOY_SCRIPT={'ON' if enable_qt_deploy_script else 'OFF'}")
    if sys.platform != "win32":
        configure.append("-DCMAKE_BUILD_TYPE=Debug")
    build = [cmake, "--build", str(build_dir), "--config", config, "--parallel"]
    tests = [ctest, "--test-dir", str(build_dir), "-C", config, "--output-on-failure"]

    steps = [
        _run_step("configure", configure, cwd=root, timeout=timeout),
        _run_step("build", build, cwd=root, timeout=timeout),
        _run_step("test", tests, cwd=root, timeout=timeout),
    ]
    ok = all(bool(step.get("ok")) for step in steps)
    report: dict[str, object] = {
        "ok": ok,
        "build_dir": str(build_dir),
        "config": config,
        "enable_qt_deploy_script": enable_qt_deploy_script,
        "require_webengine": require_webengine,
        "qt_version": qt_version or "",
        "steps": steps,
    }
    if not ok:
        report["remediation"] = (
            "Install Qt 6.10.x, CMake, a C++ compiler, and vcpkg dependencies; "
            "or for Linux package-manager smoke builds rerun with "
            "--no-require-webengine --no-enable-qt-deploy-script --qt-version 6.4.0."
        )
    return report


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    parser = argparse.ArgumentParser(description="Configure, build, and test the native Qt/C++ experiment.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--build-dir", default=str(_default_build_dir(root)), help="CMake build directory.")
    parser.add_argument("--config", default="Debug", help="CMake build configuration.")
    parser.add_argument(
        "--no-require-webengine",
        action="store_true",
        help="Allow CI smoke builds without Qt WebEngine.",
    )
    parser.add_argument(
        "--qt-version",
        default="",
        help="Override the CMake TB_QT_VERSION minimum for system-Qt smoke builds.",
    )
    parser.add_argument(
        "--enable-qt-deploy-script",
        dest="enable_qt_deploy_script",
        action="store_true",
        default=None,
        help="Force Qt deployment script generation on.",
    )
    parser.add_argument(
        "--no-enable-qt-deploy-script",
        dest="enable_qt_deploy_script",
        action="store_false",
        help="Force Qt deployment script generation off for package-manager smoke builds.",
    )
    parser.add_argument("--timeout", type=int, default=300, help="Timeout per step in seconds.")
    args = parser.parse_args(argv)

    report = check_native_cpp(
        build_dir=Path(args.build_dir),
        config=str(args.config or "Debug"),
        require_webengine=not args.no_require_webengine,
        enable_qt_deploy_script=args.enable_qt_deploy_script,
        qt_version=str(args.qt_version or "").strip() or None,
        timeout=max(30, int(args.timeout or 300)),
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"native C++ check: {'ok' if report['ok'] else 'failed'}")
        for step in report["steps"]:
            status = "ok" if step["ok"] else "failed"
            print(f"- {step['name']}: {status}")
            if step.get("stdout"):
                print(str(step["stdout"]).splitlines()[-1])
            if step.get("stderr"):
                print(str(step["stderr"]).splitlines()[-1])
        if report.get("remediation"):
            print(f"remediation: {report['remediation']}")
    return 0 if bool(report["ok"]) else 1


if __name__ == "__main__":
    os.environ.setdefault("CMAKE_BUILD_PARALLEL_LEVEL", str(os.cpu_count() or 2))
    raise SystemExit(main())
