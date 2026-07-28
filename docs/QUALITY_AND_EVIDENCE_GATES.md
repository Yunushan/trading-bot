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
| 4. Python tests and coverage | Full Python tests pass and total coverage does not fall below the configured 40% floor. | `python -m pytest Languages/Python/tests -q` passes with `--cov-fail-under=40`. |
| 5. Python lint/type contracts | Ruff and mypy pass for the reviewed typed surface. | `tools/verify_all.py` Python lint and type checks pass. |
| 6. Service API contracts | Service schema and HTTP contract tests stay in sync with the UI/client assumptions. | `Languages/Python/tools/check_service_api_contracts.py` and service tests pass. |
| 7. Backtest optimizer guardrails | Large searches show estimated runtime, keep bounded result rows, require user confirmation for very large interactive runs, and reject invalid OHLCV/timestamp data before simulation. | Optimizer and data-quality unit tests plus UI execution helpers pass. |
| 8. Risky-pattern regression gate | Broad exception, silent pass, TODO, bare except, and disabled TLS counts cannot increase above the reviewed baseline. | `tools/audit_risky_patterns.py --baseline tools/risky_patterns_baseline.json --fail-on-regression --fail-on-high` passes. |
| 9. Web dashboard quality | Web dashboard tests pass under the declared Node runtime. | `npm test` in `apps/web-dashboard`. |
| 10. Mobile client quality | Mobile thin-client tests pass under the declared Node runtime. | `npm test` in `apps/mobile-client`. |
| 11. Rust shared-core health | Rust workspace compiles and core tests pass. | `cargo check --workspace --locked` and `cargo test --locked -p trading-bot-core` in `experiments/rust-shells`. |
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
  contract hash. CI and the native evidence workflows write the same report to
  `artifacts/native-source-sync/native-source-sync-audit.json` and upload it as
  `native-source-sync-audit`, so reviewers can download the proof instead of
  relying only on console logs.
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
  `tools/import_rust_native_evidence_artifacts.py <artifact.zip-or-dir> artifacts/native-source-sync --apply --require-current-commit --require-clean-source --require-native-source-sync-audit`
  plus `--require-runtime-id` for `rust-native-live-market-data-smoke`,
  `rust-native-live-account-read-smoke`, and
  `rust-native-release-platform-evidence`;
  then run `tools/audit_rust_native_runtime_readiness.py --require-ready --json`.
  `tools/check_rust_native_evidence_workflows.py --json` structurally checks
  the main CI Rust evidence gate plus the manual live-smoke, release-platform
  target, release-evidence, and promotion-audit workflows, so CI/import/readiness
  wiring cannot silently drift away from the same promotion rules. The
  live-smoke, release-platform target, release-evidence, and promotion-audit
  workflows must also run
  `tools/audit_native_source_sync.py --json --output artifacts/native-source-sync/native-source-sync-audit.json`
  before collecting or importing runtime promotion evidence, then upload the
  `native-source-sync-audit` artifact. This keeps every evidence-producing path
  bound to the current Python-owned native contract with durable JSON proof.
  The audit emits a `source_sync_claim` object for the narrower Python-owned
  native contract surface. `source_sync_claim.can_claim` is true only when
  `source_sync_claim.surface_contract_ok` is true, the
  `required_generated_artifact_names` exactly match the
  `actual_generated_artifact_names`, the `required_consumer_surface_names`
  exactly match the `actual_consumer_surface_names`, and the
  Rust source markers are present, `tools/audit_native_source_sync.py --json`
  proves generated C++/Rust/Tauri artifacts match the current Python source
  contract hash, the native C++ dashboard/backtest/chart/positions/account
  symbol surfaces, C++ chart-heatmap, exchange-connector, and strategy-runtime
  option-normalization support modules, C++ config-persistence choice validation,
  Rust strategy-runtime side/account/assets, signal, and stop-loss option
  normalization, Rust config-persistence choice validation,
  C++ Service API route callers, Rust catalog consumers, and Tauri Service API
  route callers still read those generated catalogs and route contracts, and
  the audit can extract literal C++/Tauri Service API route calls and reject
  route names that are absent from the Python Service API contract, and
  `Languages/Python/app/native_parity.py` still approves both C++ and Rust
  contract parity. This claim is intentionally separate from runtime
  completion; source synchronization does not prove standalone trading execution
  readiness.
  The audit emits a `promotion_model` object with the current phase, failed
  requirement ids, command hints, and the exact evidence directories ignored for
  tracked source cleanliness. It also emits an explicit `completion_claim`
  object on every run. `completion_claim.can_claim` is true only when the strict
  promotion requirements pass; otherwise it is `denied` with failed requirement
  ids, remaining evidence ids, and denied reasons, so a non-strict audit with
  `ok: true` cannot be mistaken for Rust runtime completion. When the tracked
  source tree is dirty, the audit also reports `current_source_tree_dirty_paths`
  so promotion blockers are actionable instead of just a boolean failure. The audit also reports
  `current_source_tree_untracked_paths`; untracked source or tool files outside
  the canonical evidence directories (`artifacts/rust-native-runtime-evidence/`,
  `artifacts/native-source-sync/`, and `release-platform-evidence/`) block
  strict promotion because operators must collect evidence from the exact
  committed source revision. Reusing
  evidence from an older commit or an older Python source contract must fail.
  The audit `next_actions` list mirrors failed promotion requirements, including
  native contract regeneration, Python/manifest policy alignment, clean candidate
  source preparation, evidence collection/import, and the final runtime-ready
  source-guard promotion step. The companion `promotion_next_action_plan` field
  carries the same work as structured JSON rows with stable action ids,
  requirement ids, evidence ids, commands, workflow hints, dependency ids,
  `ready_to_run`, `blocked_by`, and details for automation. Evidence-collection
  actions embed compact `evidence_rows` snapshots with the preflight command,
  collection command, import command, validation command, required environment,
  safety flags, `workflow_source_sync_audit`, the source-sync JSON artifact
  location, and release-platform target counts needed to run the action without
  parsing prose.
  Evidence collection actions that are blocked by dirty or untracked source
  paths list `create_clean_candidate_source_revision` in
  `depends_on_action_ids`, so automation can order source cleanup before
  collecting commit-bound runtime evidence.
  The `completion_claim.missing_inputs` object aggregates the remaining
  evidence prerequisites, required environment variables, required operator
  inputs, and release-platform target counts, so the top-level runtime
  completion claim names the external inputs still needed without requiring
  consumers to parse every evidence row. For live-smoke evidence it also carries
  the workflow inputs, expected artifact filenames, uploaded artifact names, and
  required secret names; for release-platform evidence it carries dispatch
  command counts, bounded command target ids, truncation flags, manual-input
  target counts, and the expected `release-platform-evidence-<target_id>`
  artifact naming pattern. It also mirrors the final promotion-audit workflow
  name, `live_smoke_run_id` and `release_evidence_run_id` inputs,
  `rust-native-promotion-evidence-plan` artifact name, and required runtime
  evidence IDs so automation does not need to parse shell command strings.
  The same audit also emits an `evidence_collection_plan` row for every required
  Rust runtime artifact. Each row names the expected artifact path, whether the
  artifact already passed, whether prerequisites allow collecting it now, the
  local preflight command, the local collection command, the matching manual
  GitHub workflow command, required environment/input values, safety flags, and
  the commit-bound importer command operators must use before promotion. Live
  smoke rows also include `missing_prerequisites`, so missing clean-source,
  confirmation-variable, credential, or generated-evidence write-guard blockers
  are visible in the plan before an operator attempts collection. They also
  expose `github_workflow_inputs` for `binance_testnet`, `symbol`, and
  `interval`, expected live-smoke artifact filenames, the uploaded artifact
  names, and the required repository secret names before an operator dispatches
  `.github/workflows/rust-native-live-smoke.yml`. For
  release-platform evidence, the row also carries the bounded
  `missing_platform_evidence_plan` with per-target promotion-grade validation
  commands plus `workflow_dispatch_batch_plan`, a machine-readable batch of
  `release-platform-real-tests.yml` dispatch commands and manual-input
  placeholders for the missing OS/browser targets. The
  `current_commit_clean_source_evidence` promotion requirement repeats the
  actionable dirty/untracked source issues, so a failed checklist row is enough
  to see what must be committed, removed, or imported before evidence collection.
  Operators can write the same promotion requirements, clean-source scope,
  artifact collection rows, commands, safety flags, and next actions to a
  Markdown runbook with
  `tools/audit_rust_native_runtime_readiness.py --json --write-evidence-plan artifacts/rust-native-runtime-evidence-plan.md`;
  use `--release-missing-limit 0` with that audit command when the generated
  plan must include every missing release-platform target command.
  use that exported plan while collecting current-commit runtime evidence. CI
  writes and uploads the same runbook as the
  `rust-native-runtime-evidence-plan` artifact for the checked source revision.
  Each evidence row in that plan includes the exact `required_runtime_ids` and
  an import command with matching `--require-runtime-id` flags, so a partial
  artifact bundle cannot be accidentally treated as the required live or release
  proof. The live-smoke rows also print the structured workflow inputs,
  expected artifacts, workflow artifact names, and required secret names in the
  Markdown runbook.
  The manual live-smoke and release-evidence workflows also upload post-run
  plan artifacts with `always()` after checkout/tooling reaches the plan step,
  so operators can see the remaining promotion blockers even when a subset
  evidence collection attempt fails before validation finishes.
  After the live-smoke and release-evidence workflow artifacts exist for the
  candidate commit, operators can run
  `.github/workflows/rust-native-promotion-audit.yml` with those two Actions run
  ids. The audit model exposes those ids as structured
  `github_promotion_audit_workflow_inputs` fields and names the
  `rust-native-promotion-evidence-plan` artifact before dispatch. It also
  exposes `github_promotion_audit_source_sync_audit`, proving the promotion
  workflow must run `tools/audit_native_source_sync.py --json --output artifacts/native-source-sync/native-source-sync-audit.json`
  and upload `native-source-sync-audit` before importing external runtime
  artifacts. That workflow
  downloads the external evidence under the ignored runtime
  evidence directory, imports it with
  `artifacts/native-source-sync`, `--apply --overwrite`,
  `--require-current-commit`, `--require-clean-source`,
  `--require-native-source-sync-audit`, and the three externally downloaded
  runtime evidence IDs (`rust-native-live-market-data-smoke`,
  `rust-native-live-account-read-smoke`, and
  `rust-native-release-platform-evidence`), and logs the importer's JSON
  report so reviewers can see copy versus overwrite actions plus
  existing/incoming evidence hashes. It then regenerates the two deterministic
  local recovery evidence IDs for the checked commit, validates all five
  required runtime evidence IDs, and runs
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
  confirmation prerequisite booleans plus `commit` and `source_tree_clean`
  before any operator supplies real credentials. The same checker rejects
  preflight output whose `commit` or `python_source_contract_hash` does not
  match the current source revision and Python source-of-truth contract, so
  stale Rust builds cannot satisfy the preflight gate. Public market-data
  evidence may be collected separately with
  `TRADING_BOT_RUST_MARKET_SMOKE=1 cargo run --locked -p trading-bot-rust -- --native-live-market-smoke`;
  signed account evidence still requires the credential-gated
  `--native-live-smoke` command. Operators can also run the manual
  `.github/workflows/rust-native-live-smoke.yml` workflow after configuring
  `BINANCE_API_KEY` and `BINANCE_API_SECRET` repository secrets; the workflow
  runs the native source-sync audit and the same preflight, executes the
  read-only signed account smoke, validates the Rust preflight with
  `tools/check_rust_native_live_smoke_preflight.py --json --timeout 180`,
  validates `rust-native-live-market-data-smoke.json` and
  `rust-native-live-account-read-smoke.json`, uploads them as artifacts, and
  uploads a post-smoke `rust-native-live-smoke-evidence-plan` runbook artifact
  on both successful and failed smoke attempts once the plan step can run.
  Live-smoke artifacts must include both endpoint rows and operation-level
  suite rows: market data evidence must prove symbols, klines, ticker price
  fetches, an observed `wss://` Binance kline event, and a positive recorded
  WebSocket timeout before the native read-only market cycle is accepted;
  signed account evidence must prove position mode, multi-assets mode,
  USDT balance with `balances_redacted: true`, open positions were read, and
  redacted environment metadata shows `api_key_present: true`,
  `api_secret_present: true`, `signed_account_read: true`, and
  `secrets_in_artifact: false`.
  Use
  `tools/write_rust_native_release_evidence.py --preflight --json` to inspect
  local release-platform evidence coverage without network access or artifact
  writes. The preflight JSON includes a bounded `missing_platform_evidence_plan`
  with runner labels, required workflow inputs, probe commands, promotion-grade
  `target_validation_command` values, and `gh workflow run` examples. It also
  includes `workflow_dispatch_batch_plan`, which turns the missing target list
  into focused recovery commands for `.github/workflows/release-platform-real-tests.yml`
  and exposes `complete_matrix_dispatch` for the preferred one-run
  `target_id: all` collection path,
  keeps target ids, command counts, and structured workflow inputs
  machine-readable, and lists targets that need manual workflow inputs such as a
  real desktop smoke command or external browser-lab command. The Markdown
  runbook prints only the bounded `command_target_ids` by default while
  `missing_platform_evidence_all` remains the complete missing target-id list for
  automation, and `release_evidence_target_count` is the total number of
  required platform plus browser evidence targets behind the missing-count
  denominator; pass `--missing-limit 0` when an operator needs the complete
  missing-target plan with commands.
  It also reports `source_tree_clean` and `native_source_sync_guard`; a dirty
  source tree or failed native source-sync audit blocks both preflight success
  and the final aggregate writer before any network request or artifact write.
  It also includes `local_browser_batch_plan`, which lists the current host's
  built-in Chrome/Edge browser targets, the batch collection command, and the
  per-target validation commands when such local browser evidence can be
  collected.
  It also distinguishes present files from usable evidence
  with `passed_platform_evidence_count`, `invalid_platform_evidence_count`, and
  `unknown_platform_evidence_count`; only passed evidence can contribute to
  release promotion. Use `tools/write_rust_native_release_evidence.py` to create the Rust
  release artifact from real GitHub Rust release assets and passed
  release-platform evidence. The manual
  `.github/workflows/release-platform-real-tests.yml` workflow defaults to
  `target_id: all`, expands the checked-in 12-target release matrix into its
  declared runners, and validates the combined
  `release-platform-evidence-*` artifacts in the same run. A specific canonical
  target id is for focused recovery only; `runner_labels_json` can override the
  runner only for that one target. Each matrix job uploads
  `native-source-sync-audit` before its `release-platform-evidence-<target_id>`
  artifact. Windows 11 x64 evidence requires a self-hosted runner carrying
  `self-hosted`, `windows`, `x64`, `tb-release-platform`, and
  `windows-11-x64`; GitHub's `windows-2025` image is Windows Server and is not
  accepted as Windows 11 evidence. Ubuntu 24.04 x64 and macOS 15 arm64 use
  their matching GitHub-hosted runner labels. Configure the Windows runner with
  `pwsh -File tools/Setup-Windows11ReleaseRunner.ps1 -RepositoryUrl https://github.com/<owner>/<repo> -RegistrationToken <short-lived-token> -InstallService`;
  the helper validates the host, uses only the required custom labels, and
  refuses to overwrite an existing runner directory. Operators can also run the
  manual `.github/workflows/rust-native-release-evidence.yml` workflow with a
  release tag and a platform-evidence Actions run id; it downloads
  `release-platform-evidence-*` artifacts after the native source-sync audit
  passes and uploads `native-source-sync-audit`, runs the preflight, writes
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
  `artifacts/native-source-sync`, `--require-native-source-sync-audit`,
  `--require-current-commit --require-clean-source`, and the matching
  `--require-runtime-id` flags when importing evidence for runtime promotion,
  so missing parity-audit proof, stale, dirty-source, or partial
  runtime/release-platform artifact bundles are rejected before they enter the
  canonical evidence directory. In promotion mode, the source-sync audit must be
  the current checkout's canonical
  `artifacts/native-source-sync/native-source-sync-audit.json`; an audit bundled
  inside a downloaded runtime or release artifact ZIP is not accepted as proof of
  current source parity. Every runtime evidence JSON must also carry a
  `native_source_sync` object that points at that canonical audit, names
  `Languages/Python/app/native_parity.py` as the source of truth, embeds the
  current Python contract hash, and requires the surface contract proof. The
  promotion-mode importer also checks release-platform target JSON for the
  current git commit, `source_tree_clean: true`, the current Python
  source-contract hash, `runtime_ready_claimed: false`, and
  `secrets_redacted: true`. The clean-source promotion check ignores
  only the canonical evidence artifact directories
  `artifacts/rust-native-runtime-evidence/`, `artifacts/native-source-sync/`,
  and `release-platform-evidence/`; tracked or untracked code, workflow,
  documentation, tool, or manifest changes outside those directories still block
  promotion evidence validation. Runtime, source-sync audit, and release-platform
  evidence JSON/ZIP/download artifacts are ignored generated outputs, not source
  files. Do not hand-edit or commit stale evidence to satisfy promotion;
  regenerate/import it from the candidate commit instead. To remove stale local
  Rust runtime evidence without deleting current matching evidence, run
  `python tools/clean_workspace_artifacts.py --stale-runtime-evidence --apply`.
  `tools/verify_all.py` also checks that generated evidence artifacts are not
  tracked as source, writes the current checkout's canonical native source-sync
  audit, dry-runs the importer over existing local evidence directories plus
  `artifacts/native-source-sync` with `--require-current-commit`,
  `--require-clean-source`, and `--require-native-source-sync-audit`, and CI
  runs the same strict audits. In a dirty local development checkout,
  `verify_all.py` reports the importer result as a non-blocking promotion-only
  advisory when every importer issue is a dirty-source or stale current-commit
  promotion precondition; any importer schema, source-control, workflow-contract,
  missing current-checkout native source-sync audit, partial bundle, or
  unsupported-artifact regression remains a required failure. Clean stale local
  Rust runtime evidence with
  `python tools/clean_workspace_artifacts.py --stale-runtime-evidence --apply`
  or import fresh artifacts from the clean candidate commit before treating any
  local verification result as promotion evidence.
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
  The aggregate writer also refuses to write when the current checkout is dirty
  or the Python-owned native source-sync audit fails, so `source_tree_clean:
  false` or source-desynchronized aggregate release evidence is not produced for
  promotion.
  Operators can validate one target artifact while collecting evidence with
  `tools/check_release_platform_matrix.py --require-evidence --require-current-commit --require-clean-source --target-filter <target-id>`.
  Those flags make target-level validation enforce the same current-commit,
  clean-source, Python source-contract, runtime-ready, and redaction binding
  before aggregation or import.
  The manual `release-platform-real-tests.yml` workflow defaults to
  `target_id: all`; `desktop_smoke_command` remains available only as an
  override; otherwise the
  probe builds the native C++ Release target and runs its documented `--smoke`
  command. The release workflow provisions Qt 6.10.3 with WebEngine and
  WebSockets on the matching platform runner, then provisions the pinned
  Playwright browser channels for Chrome, Edge, and Firefox;
  `browser_test_command` remains available only as an explicit override. For
  supported browser targets, the probe can run
  `npm --prefix apps/web-dashboard run test:browser -- --browser=chrome`,
  `npm --prefix apps/web-dashboard run test:browser -- --browser=edge`, or
  `npm --prefix apps/web-dashboard run test:browser -- --browser=firefox`.
  Firefox is executed with the pinned Playwright runtime; first run
  `npx --prefix apps/web-dashboard playwright install firefox` after `npm ci`.
  automatically when `npm` and the matching browser are available. Local
  operators can run
  `tools/run_release_platform_probe.py --list-local-browser-targets` to see the
  matching host/browser targets and
  `tools/run_release_platform_probe.py --local-browser-targets --require-clean-source --require-native-source-sync --output-dir release-platform-evidence`
  to collect only those partial browser artifacts before validating each target.
  The collection command refuses dirty source trees and failed native source-sync
  audits because promotion evidence must be bound to the current clean,
  Python-synchronized commit. Per-target promotion validation also rejects stale
  or missing `native_source_sync` target bindings before aggregation. The
  aggregate release writer and promotion importer enforce that same full binding
  shape, including the canonical audit artifact/path, Python source-of-truth
  path, current contract hash, and surface-contract requirement flag. Use
  `tools/check_rust_native_local_recovery_evidence.py --json` to generate and
  validate deterministic local recovery evidence in an isolated artifact
  directory for local regression checks. For promotion collection, run
  `tools/check_rust_native_local_recovery_evidence.py --evidence-dir artifacts/rust-native-runtime-evidence --require-clean-source --require-native-source-sync --json`.
  The readiness audit marks those local recovery rows ready for promotion
  collection only when the checkout is the clean candidate source revision and
  the Python-owned C++/Rust/Tauri native source-sync audit passes; dirty local
  runs are useful regression checks but are not promotion-ready evidence. Use
  `tools/audit_rust_native_runtime_readiness.py --json` for normal CI/local
  consistency checks; it reports per-artifact status, remaining evidence IDs,
  authoritative native source-sync status, Python runtime-readiness source
  flags, redacted live-smoke prerequisites, live-smoke workflow inputs and
  expected artifact names, release evidence prerequisites,
  release platform preflight coverage counts, invalid/unknown evidence counts,
  a bounded `missing_platform_evidence_plan`, `workflow_dispatch_batch_plan`,
  Markdown evidence plan export support, and next actions. Use
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
