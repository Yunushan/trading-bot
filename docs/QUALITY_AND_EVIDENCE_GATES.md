# Quality and Evidence Gates

This project treats source-complete work and externally evidenced support as
separate states. A feature can be implemented in source, but it is not promoted
to official support until the matching evidence artifact exists.

## Local verification gate

Run the combined gate from the repository root before publishing changes:

```bash
python tools/clean_workspace_artifacts.py --apply
python tools/verify_all.py
python tools/audit_workspace_hygiene.py --json
```

`tools/verify_all.py` is the canonical local gate. It checks declared Python and
Node runtimes, workspace hygiene, client dependency locks, risky-pattern
regressions, unsupported support/parity claims, Python lint/type/contracts/tests,
web and mobile client tests, Rust workspace checks, Tauri UI behavior, native
C++ build/tests, and diff whitespace.

## 18-article completion gate

| Article | Completion rule | Evidence |
| --- | --- | --- |
| 1. Runtime versions | Python and Node match `.python-version` and `.node-version`. | `tools/check_local_tool_versions.py --json` passes. |
| 2. Workspace hygiene | Generated artifacts do not pollute source audits. | `tools/audit_workspace_hygiene.py --json` reports zero noisy artifacts after cleanup. |
| 3. Python dependency health | Python desktop, service, and dev dependencies install under the declared runtime. | `python -m pip install -e "Languages/Python[desktop,service,dev]"` completes. |
| 4. Python tests and coverage | Full Python tests pass and total coverage does not fall below the configured 38% floor. | `python -m pytest Languages/Python/tests -q` passes with `--cov-fail-under=38`. |
| 5. Python lint/type contracts | Ruff and mypy pass for the reviewed typed surface. | `tools/verify_all.py` Python lint and type checks pass. |
| 6. Service API contracts | Service schema and HTTP contract tests stay in sync with the UI/client assumptions. | `Languages/Python/tools/check_service_api_contracts.py` and service tests pass. |
| 7. Backtest optimizer guardrails | Large searches show estimated runtime, keep bounded result rows, require user confirmation for very large interactive runs, and reject invalid OHLCV/timestamp data before simulation. | Optimizer and data-quality unit tests plus UI execution helpers pass. |
| 8. Risky-pattern regression gate | Broad exception, silent pass, TODO, bare except, and disabled TLS counts cannot increase above the reviewed baseline. | `tools/audit_risky_patterns.py --baseline tools/risky_patterns_baseline.json --fail-on-regression --fail-on-high` passes. |
| 9. Web dashboard quality | Web dashboard tests pass under the declared Node runtime. | `npm test` in `apps/web-dashboard`. |
| 10. Mobile client quality | Mobile thin-client tests pass under the declared Node runtime. | `npm test` in `apps/mobile-client`. |
| 11. Rust shared-core health | Rust workspace compiles and core tests pass. | `cargo check --workspace` and `cargo test -p trading-bot-core` in `experiments/rust-shells`. |
| 12. Tauri desktop behavior | Tauri UI behavior mirrors the operational tab surface and key controls. | `node experiments/rust-shells/apps/tauri-desktop/ui/tauri-ui-behavior.test.cjs` passes. |
| 13. Native C++ health | Qt/C++ experiment configures, builds, and runs CTest. | `python tools/check_native_cpp.py --json` passes. |
| 14. CI workflow parity | GitHub Actions contains equivalent Python, support-claim, web, mobile, Rust, and native C++ gates. | `.github/workflows/ci.yml` workflow lint and the remote run pass. |
| 15. Connector promotion | Non-Binance crypto and FX/broker connectors remain evidence-gated until venue-specific dry-run/live artifacts are attached. | Connector matrix evidence files or CI artifacts for each venue. |
| 16. Live trading safety | Live trading requires explicit live confirmation, real credential checks, and order/session caps. | Safety tests plus operator runbook evidence. |
| 17. Platform promotion | FreeBSD, BSD-family, Solaris/illumos, mobile native, and unusual CPU targets remain evidence-gated until matching runner/device artifacts pass. | Release-platform matrix artifacts, self-hosted runner logs, or device test reports. |
| 18. Manual product QA | Visual desktop flows, hosted service API flows, LLM/local-model flows, and release packaging get an operator checklist before support promotion. | Dated manual QA notes linked from the release or PR. |

## Evidence rules

- Do not mark an evidence-gated target as `Supported now` only because source
  code exists.
- Attach logs or artifacts for live connector, mobile device, and unusual OS
  promotions. A local developer note without reproducible output is not enough.
- When an external check cannot run locally, keep it represented as a required
  document, CI job, or support-matrix evidence row so the gap is visible.
- Source-contract parity is not standalone product/runtime parity. Native C++
  and Rust surfaces may claim generated Python source-contract parity only; full
  standalone parity stays false until native execution ownership and external
  release/platform evidence exist.
- Clean generated build, coverage, cache, and target directories after local
  verification unless they are the artifact being reviewed.

## Manual QA checklist

Use this checklist before a release or before promoting an experimental target:

- Desktop opens with the canonical launcher and the dashboard, chart, positions,
  backtest, liquidation heatmap, service API, LLM, logs, and code-language
  surfaces are reachable.
- Backtest can run a small single-symbol test, a multi-symbol optimizer test,
  and a high-run warning/confirmation path.
- Service API can start on `127.0.0.1`, requires a token when configured, and
  keeps public endpoint controls disabled unless explicitly enabled.
- Local LLM model check/download flow clearly states where the model is stored
  and does not claim cloud OpenAI token availability without a token.
- Live/demo connector tests use testnet or dry-run mode unless the operator has
  deliberately enabled live trading and documented the account limits.
