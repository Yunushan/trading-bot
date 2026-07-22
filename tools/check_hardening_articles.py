from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Evidence:
    path: str
    contains: tuple[str, ...] = ()
    absent: tuple[str, ...] = ()
    regex: str | None = None
    min_value_regex: tuple[str, int] | None = None


@dataclass(frozen=True)
class Article:
    article_id: int
    title: str
    evidence: tuple[Evidence, ...]


HARDENING_ARTICLES: tuple[Article, ...] = (
    Article(
        1,
        "Live trading safety",
        (
            Evidence("Languages/Python/app/settings/live_safety.py", ("LIVE_TRADING_ACKNOWLEDGEMENT",)),
            Evidence(
                "Languages/Python/tests/test_settings_defaults.py",
                ("test_live_trading_requires_explicit_confirmation_and_credentials", "LIVE_TRADING_ACKNOWLEDGEMENT"),
            ),
            Evidence("experiments/rust-shells/crates/core/src/order_guard.rs", ("guard_live_order_submit",)),
        ),
    ),
    Article(
        2,
        "Backtest optimizer architecture",
        (
            Evidence(
                "Languages/Python/app/core/backtest/optimizer_limits_runtime.py",
                ("MAX_BACKTEST_OPTIMIZER_RUNS", "MAX_BACKTEST_OPTIMIZER_TABLE_ROWS"),
                min_value_regex=(r"MAX_BACKTEST_OPTIMIZER_RUNS\s*=\s*([0-9_]+)", 100_000_000_000),
            ),
            Evidence(
                "Languages/Python/app/gui/backtest/backtest_execution_scan_runtime.py",
                ("confirm_large_backtest_optimizer_run", "optimizer_result_limit"),
            ),
            Evidence("Languages/Python/tests/test_backtest_optimizer_runtime.py", ("optimizer",)),
        ),
    ),
    Article(
        3,
        "Risky exception handling regression gate",
        (
            Evidence("tools/audit_risky_patterns.py", ("--fail-on-regression", "--fail-on-high")),
            Evidence("tools/risky_patterns_baseline.json"),
            Evidence(".github/workflows/ci.yml", ("audit_risky_patterns.py", "--fail-on-regression")),
        ),
    ),
    Article(
        4,
        "Python test coverage gate",
        (
            Evidence(
                "Languages/Python/pyproject.toml",
                ("--cov=app", "--cov=trading_core", "--cov-fail-under"),
                min_value_regex=(r"--cov-fail-under=(\d+)", 38),
            ),
            Evidence("Languages/Python/tools/run_python_tests.py", ("pytest", "run_pytest_suite")),
        ),
    ),
    Article(
        5,
        "Static analysis gate",
        (
            Evidence("Languages/Python/pyproject.toml", ("[tool.ruff.lint]", "[tool.mypy]", "check_untyped_defs")),
            Evidence(".github/workflows/ci.yml", ("python -m ruff check", "python -m mypy")),
        ),
    ),
    Article(
        6,
        "Rust behavioral tests",
        (
            Evidence("tools/verify_all.py", ("cargo", "test", "trading-bot-core")),
            Evidence(".github/workflows/ci.yml", ("cargo test --locked -p trading-bot-core",)),
            Evidence(
                "tools/check_rust_native_local_recovery_evidence.py",
                (
                    "--write-local-recovery-evidence",
                    "rust-native-live-stream-recovery",
                    "rust-native-order-guard-recovery",
                ),
            ),
            Evidence("experiments/rust-shells/crates/core/src/runtime_control.rs", ("#[cfg(test)]",)),
        ),
    ),
    Article(
        7,
        "Native C++ smoke coverage",
        (
            Evidence("tools/check_native_cpp.py", ("native_order_safety_tests", "native_service_api_contract_tests")),
            Evidence("experiments/native-cpp/CMakeLists.txt", ("native_order_safety_tests", "native_service_api_contract_tests")),
            Evidence(".github/workflows/ci.yml", ("Native C++ Smoke", "check_native_cpp.py")),
        ),
    ),
    Article(
        8,
        "Cross-language parity source of truth",
        (
            Evidence("Languages/Python/tools/generate_native_parity_contracts.py"),
            Evidence(
                "tools/audit_native_source_sync.py",
                ("render_rust_module", "render_cpp_header", "render_tauri_browser_contract"),
            ),
            Evidence("Languages/Python/tests/test_native_generated_parity_contract.py", ("generated", "parity")),
            Evidence("experiments/rust-shells/crates/core/src/generated_python_parity.rs", ("PYTHON_SOURCE_CONTRACT_HASH",)),
        ),
    ),
    Article(
        9,
        "Rust GUI scope boundary",
        (
            Evidence(
                "Languages/Python/app/gui/code/code_language_catalog.py",
                ("RUST_FRAMEWORK_OPTIONS", "Tauri"),
                ("Slint", "egui", "Iced", "Dioxus Desktop"),
            ),
            Evidence(
                "experiments/rust-shells/apps/tauri-desktop/ui/index.html",
                ("Rust desktop framework", "Tauri is the only user-selectable Rust desktop shell"),
                ("Slint", "egui", "Iced", "Dioxus Desktop"),
            ),
            Evidence(
                "experiments/rust-shells/crates/core/src/lib.rs",
                ("supported_frameworks", "rust_shell_framework_parity", "only user-selectable Rust desktop shell"),
                ("Slint", "egui", "Iced", "Dioxus Desktop"),
            ),
            Evidence(
                "experiments/rust-shells/README.md",
                ("Tauri desktop shell", "only user-selectable Rust desktop shell"),
                ("Slint", "egui", "Iced", "Dioxus Desktop"),
            ),
        ),
    ),
    Article(
        10,
        "Release artifact discipline",
        (
            Evidence(".gitignore", ("/Trading-Bot-*.exe", "build/", "dist/")),
            Evidence("tools/audit_workspace_hygiene.py", ("noisy_artifact_count",)),
            Evidence("tools/clean_workspace_artifacts.py", ("planned", "removed")),
        ),
    ),
    Article(
        11,
        "Dependency version and upgrade safety",
        (
            Evidence("Languages/Python/tools/check_dependency_metadata.py"),
            Evidence("tools/check_python_version_support.py", ("3.10", "3.14")),
            Evidence("docs/DEPENDENCY_REPRODUCIBILITY.md", ("bootstrap_local_dev.py",)),
        ),
    ),
    Article(
        12,
        "Connector support evidence gates",
        (
            Evidence("docs/connector-support-matrix.json", ("evidence_required", "official-live-evidence")),
            Evidence("tools/check_connector_support_matrix.py", ("evidence_required",)),
            Evidence("Languages/Python/tests/test_exchange_support_capabilities.py", ("evidence",)),
        ),
    ),
    Article(
        13,
        "Secret handling and redaction",
        (
            Evidence("Languages/Python/app/security/redaction.py", ("redact",)),
            Evidence("Languages/Python/tests/test_secret_redaction.py", ("api_key", "redacted")),
            Evidence("experiments/native-cpp/tests/NativeOrderSafetyTests.cpp", ("<redacted>",)),
        ),
    ),
    Article(
        14,
        "LLM advisory-only boundary",
        (
            Evidence("docs/ARCHITECTURE_BOUNDARIES.md", ("LLM integrations must stay advisory",)),
            Evidence("Languages/Python/tests/test_llm_clients_privacy.py", ("advisory",)),
            Evidence("experiments/rust-shells/crates/core/src/llm_advisory.rs", ("LLM_EXECUTION_BOUNDARY", "can_execute_orders")),
        ),
    ),
    Article(
        15,
        "Observability and diagnostics",
        (
            Evidence("Languages/Python/tests/test_runtime_exception_diagnostic_helpers.py", ("diagnostic",)),
            Evidence("experiments/rust-shells/crates/core/src/diagnostics.rs", ("Diagnostic",)),
            Evidence("docs/OPERATIONAL_PREFLIGHT_RUNBOOK.md", ("freshness", "heartbeat")),
        ),
    ),
    Article(
        16,
        "GUI responsiveness and async workers",
        (
            Evidence(
                "Languages/Python/app/gui/backtest/backtest_service_execution_runtime.py",
                ("_schedule_service_backtest_poll", "QTimer.singleShot"),
            ),
            Evidence("Languages/Python/tests/test_backtest_service_execution_runtime.py", ("service", "backtest")),
            Evidence("apps/web-dashboard/tests/service-contract.test.mjs", ("service",)),
        ),
    ),
    Article(
        17,
        "Packaging and installer evidence",
        (
            Evidence("tools/release_smoke.py", ("dry-run", "manual-smoke-mode")),
            Evidence("tools/check_release_assets.py", ("ExpectedAsset", "Trading-Bot-Python")),
            Evidence("docs/RELEASES.md", ("release", "asset")),
        ),
    ),
    Article(
        18,
        "Operator runbook",
        (
            Evidence("docs/OPERATOR_RUNBOOK.md", ("Operator Runbook",)),
            Evidence("docs/OPERATIONAL_PREFLIGHT_RUNBOOK.md", ("Start", "order")),
            Evidence("docs/HARDENING_ARTICLES.md", ("Article 1", "Article 18")),
        ),
    ),
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def _check_evidence(root: Path, evidence: Evidence) -> dict[str, object]:
    path = root / evidence.path
    result: dict[str, object] = {"path": evidence.path, "ok": True, "findings": []}
    findings: list[str] = []
    if not path.exists():
        findings.append("missing file")
        result["ok"] = False
        result["findings"] = findings
        return result
    text = _read_text(path)
    for needle in evidence.contains:
        if needle not in text:
            findings.append(f"missing required text: {needle!r}")
    for needle in evidence.absent:
        if needle in text:
            findings.append(f"forbidden text present: {needle!r}")
    if evidence.regex and re.search(evidence.regex, text, flags=re.MULTILINE) is None:
        findings.append(f"missing required pattern: {evidence.regex}")
    if evidence.min_value_regex:
        pattern, expected_minimum = evidence.min_value_regex
        match = re.search(pattern, text, flags=re.MULTILINE)
        if match is None:
            findings.append(f"missing numeric pattern: {pattern}")
        else:
            actual = int(match.group(1).replace("_", ""))
            if actual < expected_minimum:
                findings.append(f"value {actual} is below required minimum {expected_minimum}")
    result["ok"] = not findings
    result["findings"] = findings
    return result


def check_hardening_articles(root: Path | None = None) -> dict[str, object]:
    repo_root = root or _repo_root()
    article_reports: list[dict[str, object]] = []
    for article in HARDENING_ARTICLES:
        evidence_reports = [_check_evidence(repo_root, item) for item in article.evidence]
        article_reports.append(
            {
                "article": article.article_id,
                "title": article.title,
                "ok": all(bool(item["ok"]) for item in evidence_reports),
                "evidence": evidence_reports,
            }
        )
    return {
        "ok": all(bool(item["ok"]) for item in article_reports),
        "article_count": len(article_reports),
        "articles": article_reports,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify the 18 hardening articles have enforceable evidence.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)
    report = check_hardening_articles()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"Hardening articles: {report['article_count']} checked")
        for article in report["articles"]:
            status = "ok" if article["ok"] else "failed"
            print(f"- Article {article['article']}: {article['title']} - {status}")
            if not article["ok"]:
                for evidence in article["evidence"]:
                    if evidence["ok"]:
                        continue
                    print(f"  - {evidence['path']}: {', '.join(evidence['findings'])}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
