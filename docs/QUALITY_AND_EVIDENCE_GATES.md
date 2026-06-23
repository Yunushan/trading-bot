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
promotion readiness with the complete missing release-platform target list,
Python lint/type/contracts/tests, web and mobile client tests, Rust workspace
checks, Tauri UI behavior, native C++ build/tests, and diff whitespace. The CI
workflow runs on `main`, pull requests targeting `main`, and pushed
`codex/**` verification branches so branch work can collect remote check
evidence before a PR exists.

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
  contract hash. `tools/check_native_cpp.py` also runs this source-sync audit
  before any CMake configure/build/test work, so stale Python-owned generated
  contracts block the native C++ health gate even when the local C++ toolchain
  is otherwise available.
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
  `tools/check_rust_native_evidence_workflows.py --json` structurally checks
  the main CI Rust evidence gate plus the manual live-smoke, release-platform
  target, release-evidence, and promotion-audit workflows, so CI/import/readiness
  wiring cannot silently drift away from the same promotion rules.
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
  the commit-bound importer command operators must use before promotion. For
  release-platform evidence, the row also carries the bounded
  `missing_platform_evidence_plan` with per-target promotion-grade validation
  commands, so the final audit runbook still shows how to collect and validate
  missing OS/browser targets. The release row also reports total release
  evidence target count plus platform/browser present, passed, and missing
  splits, so a partial lab result cannot hide which target family remains
  unproven. The
  `current_commit_clean_source_evidence` promotion requirement repeats the
  actionable dirty/untracked source issues, so a failed checklist row is enough
  to see what must be committed, removed, or imported before evidence collection.
  Operators can write the same promotion requirements, clean-source scope,
  artifact collection rows, commands, safety flags, and next actions to a
  Markdown runbook with
  `tools/audit_rust_native_runtime_readiness.py --json --write-evidence-plan artifacts/rust-native-runtime-evidence-plan.md`;
  pass `--release-missing-limit 0` when the runbook must list every remaining
  release-platform target instead of the default bounded sample.
  Local browser probe batches include a matching batch validation command that
  repeats `--target-filter` for every locally generated browser target and
  still requires current-commit, clean-source evidence.
  Use that exported plan while collecting current-commit runtime evidence. CI
  writes and uploads the same complete-target runbook with
  `--release-missing-limit 0` as the `rust-native-runtime-evidence-plan`
  artifact for the checked source revision.
  Live market-data, signed account-read, and release-platform rows include
  explicit `missing_prerequisites` values for dirty source state, missing
  operator confirmation switches, missing Binance credentials, missing release
  tags, missing or invalid platform evidence, and generated-evidence write-guard
  blockers, so a `ready_to_collect: false` row always names the next concrete
  prerequisite.
  Each evidence row in that plan includes the exact `required_runtime_ids` and
  an import command with matching `--require-runtime-id` flags, so a partial
  artifact bundle cannot be accidentally treated as the required live or release
  proof.
  The manual live-smoke and release-evidence workflows also upload post-run
  plan artifacts with `always()` after checkout/tooling reaches the plan step.
  Those workflow runbooks use `--release-missing-limit 0`, so operators can see
  every remaining release-platform target and promotion blocker even when a
  subset evidence collection attempt fails before validation finishes.
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
  `release_platform`. The Rust `--native-live-market-smoke` and
  `--native-live-smoke` commands refuse to start network clients unless the
  source tree is clean under the same promotion evidence exclusions, so dirty
  checkouts cannot generate invalid live-smoke promotion artifacts. Use
  `tools/check_rust_native_live_smoke_preflight.py --json`
  to continuously verify the Rust live-smoke preflight remains
  read-only, redacted, artifact-free, and explicit about credential and
  confirmation prerequisite booleans plus `source_tree_clean` before any operator supplies real
  credentials. The same checker rejects preflight output whose
  `python_source_contract_hash` does not match the current Python
  source-of-truth contract, so stale Rust builds cannot satisfy the preflight
  gate. Public market-data evidence may be collected separately with
  `TRADING_BOT_RUST_MARKET_SMOKE=1 cargo run -p trading-bot-rust -- --native-live-market-smoke`;
  signed account evidence still requires the credential-gated
  `--native-live-smoke` command. Operators can also run the manual
  `.github/workflows/rust-native-live-smoke.yml` workflow after configuring
  `BINANCE_API_KEY` and `BINANCE_API_SECRET` repository secrets; the workflow
  runs the same preflight, executes the read-only signed account smoke, validates
  `rust-native-live-market-data-smoke.json` and
  `rust-native-live-account-read-smoke.json`, uploads them as artifacts, and
  uploads a post-smoke `rust-native-live-smoke-evidence-plan` runbook artifact
  on both successful and failed smoke attempts once the plan step can run. That
  post-smoke runbook uses `--release-missing-limit 0` so a failed signed smoke
  attempt still names every remaining release-platform target and dispatch
  command.
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
  with runner labels, required workflow inputs, probe commands, promotion-grade
  `target_validation_command` values, and `gh workflow run` examples; pass
  `--missing-limit 0` when an operator needs the complete missing-target plan.
  It also reports `source_tree_clean`; a dirty source tree blocks both preflight
  success and the final aggregate writer before any network request or artifact
  write. It also includes `local_browser_batch_plan`, which lists the current
  host's built-in Chrome/Edge browser targets, whether a local browser-contract
  tool is available, whether `npm` is available, the runnable target subset, an
  `unavailable_reason` when local collection is not currently possible, the
  batch collection command, and the per-target validation commands when such
  local browser evidence can be collected. If `npm` is not on `PATH`, operators
  can set `TB_BROWSER_NODE_EXECUTABLE=<path-to-existing-node-executable>` to use
  the checked-in direct Node browser-contract harness; preflight rejects missing
  or non-executable paths instead of treating the env var as evidence.
  It also distinguishes present files from usable evidence
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
  step can run. That post-release runbook uses `--release-missing-limit 0` so a
  failed aggregate attempt still names every remaining target and dispatch
  command.
  Downloaded Actions ZIPs or artifact folders can be imported locally with
  `tools/import_rust_native_evidence_artifacts.py`; the importer validates
  runtime artifacts against `docs/rust-native-runtime-evidence.json` and
  platform artifacts against `docs/release-platform-test-matrix.json` before
  copying anything, and previews by default unless `--apply` is passed. Use
  `--require-current-commit --require-clean-source` and the matching
  `--require-runtime-id` flags when importing evidence for runtime promotion,
  so stale, dirty-source, or partial runtime/release-platform artifact bundles
  are rejected before they enter the canonical evidence directory. The
  promotion-mode importer also checks release-platform target JSON for the
  current git commit, `source_tree_clean: true`, the current Python
  source-contract hash, `runtime_ready_claimed: false`, and
  `secrets_redacted: true`. The clean-source promotion check ignores
  only the canonical evidence artifact directories
  `artifacts/rust-native-runtime-evidence/` and `release-platform-evidence/`;
  tracked or untracked code, workflow, documentation, tool, or manifest changes
  outside those directories still block promotion evidence validation. Runtime
  and release-platform evidence JSON/ZIP/download artifacts are ignored
  generated outputs, not source files. Do not hand-edit or commit stale evidence
  to satisfy promotion; regenerate/import it from the candidate commit instead.
  `tools/verify_all.py` also checks that generated evidence artifacts are not
  tracked as source, dry-runs the importer over existing local evidence
  directories with `--require-current-commit --require-clean-source`, and CI
  runs the same strict audits. If ignored local evidence files were produced
  from a dirty or older checkout, that import audit is supposed to fail; clean
  the generated evidence directories or import fresh artifacts from the
  candidate commit before treating the local verification result as promotion
  evidence. Source-control, workflow-contract, or importer regressions fail the
  normal local and remote gates.
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
  that OS/browser target. The aggregate release evidence writer also requires
  every per-target JSON to match the current git commit, have
  `source_tree_clean: true`, carry the current Python source-contract hash, keep
  `runtime_ready_claimed: false`, and mark `secrets_redacted: true`; stale or
  hand-carried target evidence cannot be aggregated into promotion evidence.
  The aggregate writer also refuses to write when the current checkout is dirty,
  so `source_tree_clean: false` aggregate release evidence is not produced for
  promotion.
  Operators can validate one target artifact while collecting evidence with
  `tools/check_release_platform_matrix.py --require-evidence --require-current-commit --require-clean-source --target-filter <target-id>`.
  Those flags make target-level validation enforce the same current-commit,
  clean-source, Python source-contract, runtime-ready, and redaction binding
  before aggregation or import.
  The manual `release-platform-real-tests.yml` workflow exposes
  `desktop_smoke_command` and `browser_test_command` inputs so external labs can
  pass the real release binary or override browser command for the selected
  target. For supported Chromium-family browser targets, the probe can run
  `npm --prefix apps/web-dashboard run test:browser -- --browser=chrome` or
  `npm --prefix apps/web-dashboard run test:browser -- --browser=edge`
  automatically when `npm` and the matching browser are available. When `npm` is
  unavailable, set `TB_BROWSER_NODE_EXECUTABLE=<path-to-existing-node-executable>` to run
  `node apps/web-dashboard/tests/browser-contract.test.mjs --browser=chrome` or
  `node apps/web-dashboard/tests/browser-contract.test.mjs --browser=edge`
  directly with the same checked-in harness. Other browser targets need an
  external lab command that proves the declared browser. Local operators can run
  `tools/run_release_platform_probe.py --list-local-browser-targets` to see the
  matching host/browser targets and
  `tools/run_release_platform_probe.py --local-browser-targets --require-clean-source --output-dir release-platform-evidence`
  to collect only those partial browser artifacts before validating each target.
  The collection command refuses dirty source trees because promotion evidence
  must be bound to the current clean commit. Use
  `tools/check_rust_native_local_recovery_evidence.py --json` to generate and
  validate deterministic local recovery evidence in an isolated artifact
  directory. Use
  `tools/audit_rust_native_runtime_readiness.py --json` for normal CI/local
  consistency checks; it reports per-artifact status, remaining evidence IDs,
  authoritative native source-sync status, Python runtime-readiness source
  flags, redacted live-smoke prerequisites, release evidence prerequisites,
  release platform preflight coverage counts, invalid/unknown evidence counts,
  a bounded `missing_platform_evidence_plan`, Markdown evidence plan export
  support, and next actions. The canonical `tools/verify_all.py` and CI runbook
  paths pass `--release-missing-limit 0` so full verification reports every
  missing release-platform target. Use
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
