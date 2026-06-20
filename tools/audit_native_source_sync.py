from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = REPO_ROOT / "Languages" / "Python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.native_parity import native_python_source_contract_hash  # noqa: E402
from tools.generate_native_parity_contracts import (  # noqa: E402
    CPP_OUTPUT,
    RUST_OUTPUT,
    TAURI_BROWSER_OUTPUT,
    render_cpp_header,
    render_rust_module,
    render_tauri_browser_contract,
)


@dataclass(frozen=True, slots=True)
class GeneratedArtifact:
    name: str
    path: Path
    expected: str


@dataclass(frozen=True, slots=True)
class ConsumerRequirement:
    name: str
    path: Path
    required_text: tuple[str, ...]


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _generated_artifacts() -> tuple[GeneratedArtifact, ...]:
    return (
        GeneratedArtifact("rust_core_generated_contract", RUST_OUTPUT, render_rust_module()),
        GeneratedArtifact("cpp_generated_contract", CPP_OUTPUT, render_cpp_header()),
        GeneratedArtifact("tauri_browser_generated_contract", TAURI_BROWSER_OUTPUT, render_tauri_browser_contract()),
    )


def _consumer_requirements() -> tuple[ConsumerRequirement, ...]:
    return (
        ConsumerRequirement(
            "rust_core_consumes_generated_contract",
            REPO_ROOT / "experiments" / "rust-shells" / "crates" / "core" / "src" / "lib.rs",
            (
                "pub mod generated_python_parity",
                "generated_python_parity::PYTHON_SOURCE_CONTRACT_HASH",
                "generated_python_parity::PYTHON_PARITY_DOMAINS",
                "generated_python_parity::PYTHON_SERVICE_ROUTES",
                "generated_python_parity::PYTHON_SERVICE_ROUTE_SCHEMAS",
                "generated_python_parity::PYTHON_INDICATOR_CATALOG",
                "generated_python_parity::PYTHON_LLM_PROVIDERS",
                "generated_python_parity::PYTHON_CONNECTOR_OPTIONS",
                "generated_python_parity::PYTHON_BACKTEST_INTERVALS",
            ),
        ),
        ConsumerRequirement(
            "cpp_support_consumes_generated_contract",
            REPO_ROOT / "experiments" / "native-cpp" / "src" / "TradingBotWindowSupport.cpp",
            (
                '#include "generated/PythonParityContract.h"',
                "PythonParityContract::kPythonSourceContractHash",
                "PythonParityContract::kPythonParityDomains",
                "PythonParityContract::kPythonServiceRoutes",
                "PythonParityContract::kPythonServiceRouteSchemas",
                "PythonParityContract::kPythonIndicatorCatalog",
                "PythonParityContract::kPythonLlmProviders",
                "PythonParityContract::kPythonConnectorOptions",
                "PythonParityContract::kPythonBacktestIntervals",
            ),
        ),
        ConsumerRequirement(
            "cpp_support_exposes_generated_contract",
            REPO_ROOT / "experiments" / "native-cpp" / "src" / "TradingBotWindowSupport.h",
            (
                "pythonSourceParityContractHash",
                "pythonSourceParityDomainTitle",
                "pythonSourceServiceRoutePath",
                "pythonSourceServiceRouteMethods",
                "pythonSourceIndicatorKeys",
                "pythonSourceLlmProviderKeys",
                "pythonSourceConnectorKeys",
                "pythonSourceBacktestIntervals",
            ),
        ),
        ConsumerRequirement(
            "tauri_browser_consumes_generated_contract",
            REPO_ROOT / "experiments" / "rust-shells" / "apps" / "tauri-desktop" / "ui" / "index.html",
            (
                'src="generated-python-parity.js"',
                "window.PythonParityContract",
                "pythonParityContract.indicatorCatalog",
                "pythonParityContract.llmProviders",
                "pythonParityContract.connectorOptions",
                "pythonParityContract.backtestIntervals",
                "pythonParityContract.serviceRoutePaths",
            ),
        ),
    )


def _check_generated_artifact(artifact: GeneratedArtifact) -> dict[str, object]:
    report: dict[str, object] = {
        "name": artifact.name,
        "path": _rel(artifact.path),
        "ok": True,
        "expected_bytes": len(artifact.expected.encode("utf-8")),
        "actual_bytes": None,
        "issue": "",
    }
    if not artifact.path.exists():
        report["ok"] = False
        report["issue"] = "missing generated artifact"
        return report

    actual = _read(artifact.path)
    report["actual_bytes"] = len(actual.encode("utf-8"))
    if actual != artifact.expected:
        report["ok"] = False
        report["issue"] = (
            "generated artifact is stale; run "
            "python Languages/Python/tools/generate_native_parity_contracts.py"
        )
    return report


def _check_consumer(requirement: ConsumerRequirement) -> dict[str, object]:
    report: dict[str, object] = {
        "name": requirement.name,
        "path": _rel(requirement.path),
        "ok": True,
        "missing_text": [],
    }
    if not requirement.path.exists():
        report["ok"] = False
        report["missing_text"] = ["consumer file is missing"]
        return report

    text = _read(requirement.path)
    missing = [needle for needle in requirement.required_text if needle not in text]
    report["missing_text"] = missing
    report["ok"] = not missing
    return report


def audit_native_source_sync() -> dict[str, object]:
    generated = [_check_generated_artifact(artifact) for artifact in _generated_artifacts()]
    consumers = [_check_consumer(requirement) for requirement in _consumer_requirements()]
    issues = [
        f"{item['path']}: {item.get('issue') or 'missing consumer wiring'}"
        for item in [*generated, *consumers]
        if not bool(item["ok"])
    ]
    return {
        "ok": not issues,
        "contract_hash": native_python_source_contract_hash(),
        "source": "Languages/Python/app/native_parity.py",
        "generated": generated,
        "consumers": consumers,
        "issues": issues,
        "remediation": "python Languages/Python/tools/generate_native_parity_contracts.py",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Python-owned native C++/Rust source synchronization.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)
    report = audit_native_source_sync()

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif report["ok"]:
        print(f"Native source sync ok: Python contract {report['contract_hash']}")
    else:
        print("Native source sync failed:")
        for issue in report["issues"]:
            print(f"- {issue}")
        print(f"remediation: {report['remediation']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
