"""Focused service test manifest and documentation helpers."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ServiceTestEntry:
    module: str
    description: str


SERVICE_TESTS = (
    ServiceTestEntry(
        "tests.test_service_api_http_contract",
        "HTTP route contracts, auth behavior, SSE auth, and runtime/dashboard responses",
    ),
    ServiceTestEntry(
        "tests.test_service_schema_contracts",
        "service response schema builders, payload normalization, and secret redaction contracts",
    ),
    ServiceTestEntry(
        "tests.test_service_config_runtime",
        "service config validation and durable config persistence",
    ),
    ServiceTestEntry(
        "tests.test_service_operational_runtime",
        "operational health snapshots, connector incidents, JSONL rotation, and redaction",
    ),
    ServiceTestEntry(
        "tests.test_service_lifecycle_runtime",
        "lifecycle control, control-plane descriptors, runtime samples, and live preflight gates",
    ),
    ServiceTestEntry(
        "tests.test_service_client_integration",
        "desktop service client selection and service terminal/LLM commands",
    ),
    ServiceTestEntry(
        "tests.test_service_background_host_integration",
        "embedded background host and background-hosted backtest API flows",
    ),
)

SERVICE_TEST_MODULES = tuple(entry.module for entry in SERVICE_TESTS)

INTENTIONALLY_EXCLUDED_SERVICE_TEST_MODULES = (
    "tests.test_service_test_runner",
)

SERVICE_TEST_DOC_PATHS = (
    "docs/SERVICE_API.md",
    "apps/service-api/README.md",
    "Languages/Python/tools/README.md",
)

FOCUSED_SERVICE_TEST_MAP_HEADING = "Focused service test map:"


def render_markdown_table(entries: Sequence[ServiceTestEntry] = SERVICE_TESTS) -> str:
    rows = ["| Module | Use when checking |", "| --- | --- |"]
    rows.extend(f"| `{entry.module}` | {entry.description} |" for entry in entries)
    return "\n".join(rows)


def render_markdown_section(entries: Sequence[ServiceTestEntry] = SERVICE_TESTS) -> str:
    return f"{FOCUSED_SERVICE_TEST_MAP_HEADING}\n\n{render_markdown_table(entries)}"


def discover_service_test_modules(python_root: Path) -> tuple[str, ...]:
    tests_dir = python_root / "tests"
    return tuple(f"tests.{path.stem}" for path in sorted(tests_dir.glob("test_service_*.py")))


def module_list_errors(python_root: Path, discovered_modules: Iterable[str] | None = None) -> list[str]:
    discovered = set(discovered_modules if discovered_modules is not None else discover_service_test_modules(python_root))
    listed = set(SERVICE_TEST_MODULES)
    excluded = set(INTENTIONALLY_EXCLUDED_SERVICE_TEST_MODULES)

    errors: list[str] = []
    unclassified = sorted(discovered - listed - excluded)
    stale_listed = sorted((listed | excluded) - discovered)
    if unclassified:
        errors.append(
            "service test files missing from SERVICE_TEST_MODULES or "
            f"INTENTIONALLY_EXCLUDED_SERVICE_TEST_MODULES: {', '.join(unclassified)}"
        )
    if stale_listed:
        errors.append(f"service test modules listed without matching files: {', '.join(stale_listed)}")
    return errors


def docs_table_errors(repo_root: Path, relative_paths: Sequence[str] = SERVICE_TEST_DOC_PATHS) -> list[str]:
    expected = render_markdown_section()
    errors: list[str] = []
    for relative_path in relative_paths:
        path = repo_root / relative_path
        if not path.is_file():
            errors.append(f"{relative_path} is missing")
            continue
        if expected not in path.read_text(encoding="utf-8"):
            errors.append(f"{relative_path} focused service test map does not match tools/service_test_manifest.py")
    return errors
