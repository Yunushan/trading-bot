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


def _run_step(
    name: str,
    command: list[str],
    *,
    cwd: Path,
    timeout: int,
    env: dict[str, str] | None = None,
) -> dict[str, object]:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
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


def _tail_output(value: object, *, lines: int = 80) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return "\n".join(text.splitlines()[-lines:])


def _default_build_dir(root: Path) -> Path:
    return root / "build" / "binance_cpp_sync_check"


def _cmake_generator_args() -> list[str]:
    if sys.platform != "win32":
        return []
    return []


def _cmake_build_parallel_args() -> list[str]:
    # MSVC can contend on a target PDB during cold Qt smoke builds.
    return ["--parallel", "1"] if sys.platform == "win32" else ["--parallel"]


def _desktop_executable_path(build_dir: Path, config: str) -> Path:
    if sys.platform == "win32":
        return build_dir / config / "Trading-Bot-C++.exe"
    return build_dir / "Trading-Bot-C++"


def _cmake_cache_value(build_dir: Path, key: str) -> str:
    cache_path = build_dir / "CMakeCache.txt"
    try:
        lines = cache_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    prefix = f"{key}:"
    for line in lines:
        if not line.startswith(prefix):
            continue
        _, _, value = line.partition("=")
        return value.strip()
    return ""


def _qt_bin_from_cmake_cache(build_dir: Path) -> Path | None:
    qt6_dir = _cmake_cache_value(build_dir, "Qt6_DIR")
    if not qt6_dir:
        return None
    qt6_path = Path(qt6_dir)
    try:
        qt_root = qt6_path.parents[2]
    except IndexError:
        return None
    qt_bin = qt_root / "bin"
    return qt_bin if qt_bin.is_dir() else None


def _desktop_smoke_env(build_dir: Path, config: str) -> dict[str, str]:
    env = os.environ.copy()
    paths: list[str] = []
    executable_dir = _desktop_executable_path(build_dir, config).parent
    if executable_dir.is_dir():
        paths.append(str(executable_dir))
    qt_bin = _qt_bin_from_cmake_cache(build_dir)
    if qt_bin is not None:
        paths.append(str(qt_bin))
    if paths:
        env["PATH"] = os.pathsep.join([*paths, env.get("PATH", "")])
    # QApplication needs a display backend even though --smoke never shows a window.
    # Hosted Linux/macOS release runners are headless, so prefer Qt's offscreen plugin.
    if sys.platform != "win32":
        env.setdefault("QT_QPA_PLATFORM", "offscreen")
    return env


def check_native_cpp(
    *,
    build_dir: Path,
    config: str,
    require_webengine: bool,
    enable_qt_deploy_script: bool | None,
    smoke_targets_only: bool,
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
        # Single-config generators honor CMAKE_BUILD_TYPE at configure time.
        configure.append(f"-DCMAKE_BUILD_TYPE={config}")
    tests = [ctest, "--test-dir", str(build_dir), "-C", config, "--output-on-failure"]

    steps = [_run_step("configure", configure, cwd=root, timeout=timeout)]
    if smoke_targets_only:
        for target in ("native_order_safety_tests", "native_service_api_contract_tests"):
            steps.append(
                _run_step(
                    f"build {target}",
                    [cmake, "--build", str(build_dir), "--config", config, "--target", target, *_cmake_build_parallel_args()],
                    cwd=root,
                    timeout=timeout,
                )
            )
    else:
        steps.append(
            _run_step(
                "build",
                [cmake, "--build", str(build_dir), "--config", config, *_cmake_build_parallel_args()],
                cwd=root,
                timeout=timeout,
            )
        )
        steps.append(
            _run_step(
                "desktop release smoke",
                [str(_desktop_executable_path(build_dir, config)), "--smoke"],
                cwd=root,
                timeout=min(timeout, 60),
                env=_desktop_smoke_env(build_dir, config),
            )
        )
    steps.append(_run_step("test", tests, cwd=root, timeout=timeout))
    ok = all(bool(step.get("ok")) for step in steps)
    report: dict[str, object] = {
        "ok": ok,
        "build_dir": str(build_dir),
        "config": config,
        "enable_qt_deploy_script": enable_qt_deploy_script,
        "require_webengine": require_webengine,
        "smoke_targets_only": smoke_targets_only,
        "qt_version": qt_version or "",
        "steps": steps,
    }
    if not ok:
        report["remediation"] = (
            "Install Qt 6.10.x, CMake, a C++ compiler, and vcpkg dependencies; "
            "or for Linux package-manager smoke builds rerun with "
            "--no-require-webengine --no-enable-qt-deploy-script --smoke-targets-only --qt-version 6.4.0."
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
    parser.add_argument(
        "--smoke-targets-only",
        action="store_true",
        help="Build only native smoke test targets instead of the full GUI executable.",
    )
    parser.add_argument("--timeout", type=int, default=300, help="Timeout per step in seconds.")
    args = parser.parse_args(argv)

    report = check_native_cpp(
        build_dir=Path(args.build_dir),
        config=str(args.config or "Debug"),
        require_webengine=not args.no_require_webengine,
        enable_qt_deploy_script=args.enable_qt_deploy_script,
        smoke_targets_only=bool(args.smoke_targets_only),
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
            output_lines = 1 if step["ok"] else 80
            stdout_tail = _tail_output(step.get("stdout"), lines=output_lines)
            stderr_tail = _tail_output(step.get("stderr"), lines=output_lines)
            if stdout_tail:
                print(stdout_tail)
            if stderr_tail:
                print(stderr_tail)
        if report.get("remediation"):
            print(f"remediation: {report['remediation']}")
    return 0 if bool(report["ok"]) else 1


if __name__ == "__main__":
    # `/FS` is also set by the CMake project, but keeping the orchestration
    # serial on Windows avoids target-PDB contention in generated Qt builds.
    if sys.platform == "win32":
        os.environ["CMAKE_BUILD_PARALLEL_LEVEL"] = "1"
    else:
        os.environ.setdefault("CMAKE_BUILD_PARALLEL_LEVEL", str(os.cpu_count() or 2))
    raise SystemExit(main())
