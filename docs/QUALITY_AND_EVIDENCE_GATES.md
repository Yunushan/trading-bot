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
regressions, unsupported support/parity claims, Rust native runtime evidence
declarations, Python-owned C++/Rust source synchronization, Rust native runtime
promotion readiness, Python lint/type/contracts/tests, web and mobile client
tests, Rust workspace checks, Tauri UI behavior, native C++ build/tests, and
diff whitespace.

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
- Python remains the source of truth for shared C++/Rust contract catalogs.
  `tools/audit_native_source_sync.py --json` must pass in local/CI verification;
  if it fails, regenerate the native contracts with
  `python Languages/Python/tools/generate_native_parity_contracts.py`. The audit
  reports expected and actual SHA-256 values for each generated Rust, C++, and
  Tauri artifact and verifies that each artifact embeds the current Python
  contract hash.
- Rust native runtime promotion is controlled by
  `docs/rust-native-runtime-evidence.json` and
  `tools/check_rust_native_runtime_evidence.py`. The schema check belongs in
  local/CI verification; `--require-evidence --require-current-commit --require-clean-source`
  is the promotion gate and requires passed live-smoke, recovery, and
  release-platform artifacts from the same committed source revision being
  promoted, generated from a clean tracked source tree, and carrying the current
  Python source-contract hash. The readiness audit also
  emits a machine-readable `promotion_requirements` checklist; Rust is not
  runtime-complete unless every required checklist row passes. The manifest
  `policy.runtime_ready_flag` may represent either the current unpromoted
  `rust_native_trading_runtime_ready() == false` state or a future promoted
  `rust_native_trading_runtime_ready() == true` state, but the readiness audit
  requires that manifest policy, Rust source guard, Python native parity
  `rust_standalone_runtime_ready` source flag, Tauri display text, current
  commit evidence, and all runtime artifacts agree.
  The promotion flow is intentionally commit-bound: create a candidate source
  commit where the Rust guard, manifest policy, and desktop text agree; run the
  evidence workflows from that exact commit; import the downloaded artifacts with
  `tools/import_rust_native_evidence_artifacts.py --apply --require-current-commit --require-clean-source`
  plus `--require-runtime-id` for `rust-native-live-market-data-smoke`,
  `rust-native-live-account-read-smoke`, and
  `rust-native-release-platform-evidence`;
  then run `tools/audit_rust_native_runtime_readiness.py --require-ready --json`.
  The audit emits a `promotion_model` object with the current phase, failed
  requirement ids, command hints, and the exact evidence directories ignored for
  tracked source cleanliness. When the tracked source tree is dirty, the audit
  also reports `current_source_tree_dirty_paths` so promotion blockers are
  actionable instead of just a boolean failure. The audit also reports
  `current_source_tree_untracked_paths`; untracked source or tool files outside
  the canonical evidence directories block strict promotion because operators
  must collect evidence from the exact committed source revision. Reusing
  evidence from an older commit or an older Python source contract must fail.
  The same audit also emits an `evidence_collection_plan` row for every required
  Rust runtime artifact. Each row names the expected artifact path, whether the
  artifact already passed, whether prerequisites allow collecting it now, the
  local preflight command, the local collection command, the matching manual
  GitHub workflow command, required environment/input values, safety flags, and
  the commit-bound importer command operators must use before promotion. The
  `current_commit_clean_source_evidence` promotion requirement repeats the
  actionable dirty/untracked source issues, so a failed checklist row is enough
  to see what must be committed, removed, or imported before evidence collection.
  Operators can write the same promotion requirements, clean-source scope,
  artifact collection rows, commands, safety flags, and next actions to a
  Markdown runbook with
  `tools/audit_rust_native_runtime_readiness.py --json --write-evidence-plan artifacts/rust-native-runtime-evidence-plan.md`;
  use that exported plan while collecting current-commit runtime evidence. CI
  writes and uploads the same runbook as the
  `rust-native-runtime-evidence-plan` artifact for the checked source revision.
  Each evidence row in that plan includes the exact `required_runtime_ids` and
  an import command with matching `--require-runtime-id` flags, so a partial
  artifact bundle cannot be accidentally treated as the required live or release
  proof.
  The manual live-smoke and release-evidence workflows also upload post-run
  plan artifacts with `always()` after checkout/tooling reaches the plan step,
  so operators can see the remaining promotion blockers even when a subset
  evidence collection attempt fails before validation finishes.
  After the live-smoke and release-evidence workflow artifacts exist for the
  candidate commit, operators can run
  `.github/workflows/rust-native-promotion-audit.yml` with those two Actions run
  ids. That workflow downloads the external evidence under the ignored runtime
  evidence directory, imports it with
  `--apply --overwrite --require-current-commit --require-clean-source` and
  the three required runtime evidence IDs, and logs the importer's JSON report
  so reviewers can see copy versus overwrite actions plus existing/incoming
  evidence hashes,
  regenerates deterministic local recovery evidence for the checked commit,
  validates the complete evidence set, and runs
  `tools/audit_rust_native_runtime_readiness.py --require-ready --json`. It
  uploads `rust-native-promotion-evidence-plan` even on failure so the final
  promotion blocker list remains attached to the attempted promotion run.
  Runtime evidence artifacts must use machine-readable `generated_at` values in
  `unix:<seconds>` format.
  Deterministic local recovery artifacts may use
  `evidence_scope: deterministic_local`, but
  live-smoke artifacts must remain scoped to `live_testnet` or
  `live_production`, and release artifacts must be scoped to
  `release_platform`. Use `tools/check_rust_native_live_smoke_preflight.py --json`
  to continuously verify the Rust live-smoke preflight remains
  read-only, redacted, artifact-free, and explicit about credential and
  confirmation prerequisite booleans before any operator supplies real
  credentials. Public market-data evidence may be collected separately with
  `TRADING_BOT_RUST_MARKET_SMOKE=1 cargo run -p trading-bot-rust -- --native-live-market-smoke`;
  signed account evidence still requires the credential-gated
  `--native-live-smoke` command. Operators can also run the manual
  `.github/workflows/rust-native-live-smoke.yml` workflow after configuring
  `BINANCE_API_KEY` and `BINANCE_API_SECRET` repository secrets; the workflow
  runs the same preflight, executes the read-only signed account smoke, validates
  `rust-native-live-market-data-smoke.json` and
  `rust-native-live-account-read-smoke.json`, uploads them as artifacts, and
  uploads a post-smoke `rust-native-live-smoke-evidence-plan` runbook artifact
  on both successful and failed smoke attempts once the plan step can run.
  Live-smoke artifacts must include both endpoint rows and operation-level
  suite rows: market data evidence must prove symbols, klines, and ticker price
  fetches; signed account evidence must prove position mode, multi-assets mode,
  USDT balance with `balances_redacted: true`, open positions were read, and
  redacted environment metadata shows `api_key_present: true`,
  `api_secret_present: true`, `signed_account_read: true`, and
  `secrets_in_artifact: false`.
  Use
  `tools/write_rust_native_release_evidence.py --preflight --json` to inspect
  local release-platform evidence coverage without network access or artifact
  writes. The preflight JSON includes a bounded `missing_platform_evidence_plan`
  with runner labels, required workflow inputs, probe commands, and `gh workflow
  run` examples; pass `--missing-limit 0` when an operator needs the complete
  missing-target plan. It also distinguishes present files from usable evidence
  with `passed_platform_evidence_count`, `invalid_platform_evidence_count`, and
  `unknown_platform_evidence_count`; only passed evidence can contribute to
  release promotion. Use `tools/write_rust_native_release_evidence.py` to create the Rust
  release artifact from real GitHub Rust release assets and passed
  release-platform evidence. Operators can also run the manual
  `.github/workflows/rust-native-release-evidence.yml` workflow with a release
  tag and a platform-evidence Actions run id; it downloads
  `release-platform-evidence-*` artifacts, runs the preflight, writes
  `rust-native-release-platform-evidence.json`, validates only that release
  evidence artifact, uploads it as `rust-native-release-platform-evidence`, and
  uploads a post-release `rust-native-release-platform-evidence-plan` runbook
  artifact on both successful and failed release-evidence attempts once the plan
  step can run.
  Downloaded Actions ZIPs or artifact folders can be imported locally with
  `tools/import_rust_native_evidence_artifacts.py`; the importer validates
  runtime artifacts against `docs/rust-native-runtime-evidence.json` and
  platform artifacts against `docs/release-platform-test-matrix.json` before
  copying anything, and previews by default unless `--apply` is passed. Use
  `--require-current-commit --require-clean-source` and the matching
  `--require-runtime-id` flags when importing evidence for runtime promotion,
  so stale, dirty-source, or partial artifact bundles are rejected before they
  enter the canonical evidence directory. The clean-source promotion check ignores
  only the canonical evidence artifact directories
  `artifacts/rust-native-runtime-evidence/` and `release-platform-evidence/`;
  tracked or untracked code, workflow, documentation, tool, or manifest changes
  outside those directories still block promotion evidence validation. Runtime
  and release-platform evidence JSON/ZIP/download artifacts are ignored
  generated outputs, not source files. Do not hand-edit or commit stale evidence
  to satisfy promotion; regenerate/import it from the candidate commit instead.
  `tools/verify_all.py` also checks that generated evidence artifacts are not
  tracked as source, dry-runs the importer over existing local evidence
  directories, and CI runs the same audits, so source-control or importer
  regressions fail the normal local and remote gates.
  The aggregate release evidence artifact must embed each target's passed
  `suite_results` rows, including `platform-probe.target_match.matched: true`
  for platform targets, plus `evidence_file` and `evidence_sha256` for each
  source target JSON. Promotion cannot rely on a target count without the suite
  proof and file digest that produced it.
  Platform evidence produced by
  `tools/run_release_platform_probe.py` must include a passed `platform-probe`
  result with `target_match.matched: true`; `tools/check_release_platform_matrix.py
  --require-evidence` rejects artifacts collected on the wrong OS, version, or
  architecture. It also rejects target evidence that omits any suite declared
  for that target in `docs/release-platform-test-matrix.json`, so a target is
  not promotion-ready unless its JSON proves every required matrix suite for
  that OS/browser target. Operators can validate one target artifact while
  collecting evidence with
  `tools/check_release_platform_matrix.py --require-evidence --target-filter <target-id>`.
  The manual `release-platform-real-tests.yml` workflow exposes
  `desktop_smoke_command` and `browser_test_command` inputs so external labs can
  pass the real release binary or browser command for the selected target. Use
  `tools/check_rust_native_local_recovery_evidence.py --json` to generate and
  validate deterministic local recovery evidence in an isolated artifact
  directory. Use
  `tools/audit_rust_native_runtime_readiness.py --json` for normal CI/local
  consistency checks; it reports per-artifact status, remaining evidence IDs,
  authoritative native source-sync status, Python runtime-readiness source
  flags, redacted live-smoke prerequisites, release evidence prerequisites,
  release platform preflight coverage counts, invalid/unknown evidence counts,
  a bounded `missing_platform_evidence_plan`, Markdown evidence plan export
  support, and next actions. Use
  `--require-ready` only when intentionally promoting standalone Rust native
  trading after all evidence artifacts exist.
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
