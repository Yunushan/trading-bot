# Hardening Articles

This file maps the 18 hardening articles to repository evidence. It does not claim live trading, full native runtime parity, signed releases, or every third-party connector is production-approved. Those claims require external evidence artifacts and remain gated.

Article 1 - Live trading safety: Python live safety settings, Python order-risk tests, and Rust order guard helpers enforce explicit live acknowledgement, real credentials, leverage/position/session caps, order audit availability, connector health, symbol filters, and typed order intent validation.

Article 2 - Backtest optimizer architecture: optimizer limits, large-run confirmation, result table caps, service-backed execution, and optimizer tests protect the GUI from unbounded synchronous brute force while still allowing large research batches.

Article 3 - Risky exception handling regression gate: `tools/audit_risky_patterns.py` and `tools/risky_patterns_baseline.json` prevent broad-exception and silent-pass regressions from growing.

Article 4 - Python test coverage gate: Python tests run with coverage for `app` and `trading_core` and a configured fail-under threshold.

Article 5 - Static analysis gate: Ruff and mypy are configured and run in CI against the Python workspace.

Article 6 - Rust behavioral tests: Rust core behavioral tests are part of the local verifier and CI Rust smoke path.

Article 7 - Native C++ smoke coverage: `tools/check_native_cpp.py` configures, builds, and runs native order-safety and service-API contract CTest targets.

Article 8 - Cross-language parity source of truth: generated parity contracts keep Python as the canonical source for C++ and Rust contract surfaces.

Article 9 - Rust GUI scope boundary: Tauri is the only user-selectable Rust desktop shell and remains a Python Service API client; native Rust trading execution is still disabled until explicitly promoted.

Article 10 - Release artifact discipline: generated executables, build directories, caches, and distribution folders are ignored and covered by workspace hygiene tools.

Article 11 - Dependency version and upgrade safety: dependency metadata checks, Python version support checks, and reproducible bootstrap documentation guard upgrades.

Article 12 - Connector support evidence gates: non-primary connectors remain evidence-gated until deterministic tests and sandbox/testnet or approved live-paper artifacts exist.

Article 13 - Secret handling and redaction: Python, C++, and Rust redaction surfaces cover API keys, bearer tokens, terminal output, connector diagnostics, config persistence, and LLM responses.

Article 14 - LLM advisory-only boundary: LLM integrations are advisory-only and cannot own strategy, risk, take-profit, stop-loss, or order execution.

Article 15 - Observability and diagnostics: runtime diagnostics, operational preflight freshness, heartbeat evidence, and redacted diagnostic helpers make failures visible.

Article 16 - GUI responsiveness and async workers: scanner/backtest work is service/thread backed, and client contracts keep long work outside direct UI blocking paths.

Article 17 - Packaging and installer evidence: release smoke, release asset checks, and release documentation define required artifacts and platform validation before publishing.

Article 18 - Operator runbook: operator and operational preflight runbooks document setup, safety gates, execution ownership, failure recovery, and supported operating procedures.

Run `python tools/check_hardening_articles.py` before claiming these articles are still covered.
