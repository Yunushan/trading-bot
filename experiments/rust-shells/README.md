# Trading Bot Rust Shell Experiments

This directory is a Rust workspace for shared contracts/core logic plus the Tauri desktop shell.

It is not a single finished application. The Rust side is currently a Service API client and UI parity scaffold, not a native trading runtime. Python remains the primary end-user implementation and the only active strategy, risk, and exchange execution owner.

## Workspace layout

- `crates/contracts`: shared DTOs and contracts
- `crates/core`: shared Rust core scaffold
- `apps/tauri-desktop`: Tauri desktop shell

The shared Rust core exposes the same LLM provider catalog used by the Python
service API. The Tauri shell may mirror Python/C++ tabs, controls, route names,
and model options, but mirrored UI does not mean native trading execution. All
live strategy, risk, account, order, and exchange behavior must continue through
the Python Service API until the native Rust runtime gaps below are closed.

## Status overview

| Component | Status | Notes |
| --- | --- | --- |
| Shared contracts crate | Active foundation | Common types and workspace contracts |
| Shared core crate | Active foundation | Intended home for reusable Rust-side business logic |
| Tauri desktop shell | Operational Service API client | The only user-selectable Rust desktop shell; can manage/connect to the Python Service API, but does not own trading execution |

For this project, use `Tauri` for Rust desktop work because it is the only Rust shell with an interactive Service API client and managed local Python Service API flow.

## Native trading runtime boundary

Rust native trading execution is currently disabled. The Rust workspace is a
Service API client and tab/catalog parity layer. It must not be treated as a standalone trading engine until the native
runtime capability gaps are implemented and tested.

The C++ experiment already contains native runtime pieces that Rust does not:

- `BinanceRestClient.*`: balance, symbols, klines, ticker price, open futures
  positions, symbol filters, market/limit futures orders, and close-position
  planning rules.
- `BinanceWsClient.*`: book ticker and kline WebSocket stream scaffolding.
- `TradingBotWindow.dashboard_runtime*.cpp`: dashboard runtime lifecycle,
  polling, signal candle caches, retry windows, open-position tracking, order
  fallback helpers, and shutdown handling.
- `TradingBotWindow.positions.cpp`: live futures position/balance refresh and
  local table reconciliation.

`trading-bot-core` now has a native `BinanceRestMarketDataClient` foundation for
exchangeInfo USDT symbols, optional 24h quote-volume ordering, klines, ticker
prices, and Binance error payload handling. It also has `BinanceWebSocketClient`
for Binance book-ticker/kline stream URL construction, tungstenite connection
entry points, message parsing, and supervised stream cache/reconnect evidence
for stale-feed fail-closed planning; `BinanceSignedRestClient` for signed USDT
balance snapshots, normalized balance rows, open futures position parsing
with account-position overlays, futures position-mode get/change request
foundations, and futures margin-type/leverage/multi-assets request and parser
foundations; signed market/limit order request/result foundations
and Binance futures symbol filters; order submit guard foundations for Python's
intent, live-safety, audit, connector-health, filter, and session-cap checks;
order audit/circuit-breaker foundations for redacted JSONL events, snapshots,
incidents, threshold/window tripping, reset-block status, and rotation helpers;
risk/stop-loss close-decision foundations for normalized stop-loss settings,
per-trade, directional, cumulative, entire-account, and close-opposite planning;
a runtime-owned order engine for guarded submit, deterministic dry-run audit,
redacted audit JSONL, connector circuit incident persistence, and submit reconciliation; a
runtime-owned risk/close execution path for stop-loss close fallback and
close-opposite residual reconciliation; plus portfolio/history/allocation
reconciliation helpers and close-position planning foundations that mirror
Python/C++ one-way `reduceOnly`, hedge-mode `positionSide`, and close-all
`closePosition` fallback rules. It also has Desktop shell/tab lifecycle
contracts plus strategy runtime signal/control/provenance helpers, worker
lifecycle snapshots, custom interval kline aggregation, reconnect/backoff
decisions, kline cache staleness guards, and a deterministic stream supervisor
state machine for Python-source parity, plus a native runtime loop coordinator
that owns stream supervision snapshots, live stream event/close/error ingestion,
pause, stop, shutdown, idle transitions, hedge/one-way close planning,
account-mode reconciliation, futures-settings reconciliation for margin mode,
leverage, and assets mode before signal evaluation, a native account preflight gate, native operational preflight gate, and portfolio-aware exposure guard checks for target margin, available balance, side
caps, filter headroom, and one-way add-only reduce-only behavior without
enabling live trading. These paths support Python-source
parity validation. Before standalone native Rust trading can be enabled, Rust
still needs imported credential-gated live-smoke artifacts, live recovery
evidence with regression tests, and release evidence. The source-level guard for
this is `rust_native_trading_runtime_ready() == false` and the capability matrix
exposed by `rust_native_runtime_capabilities()`.

### Guarded native live smoke

The Rust workspace includes a read-only, credential-gated smoke command for
operators who can access Binance futures testnet or production from their own
machine. It fetches market data, account mode, multi-assets mode, USDT balance,
and open futures positions. It does not submit, modify, or cancel orders. After
a successful run, it writes `rust-native-live-market-data-smoke.json` and
`rust-native-live-account-read-smoke.json` under
`artifacts/rust-native-runtime-evidence/` unless
`RUST_NATIVE_RUNTIME_EVIDENCE_DIR` points elsewhere.

```bash
TRADING_BOT_RUST_LIVE_SMOKE=1 \
BINANCE_API_KEY=... \
BINANCE_API_SECRET=... \
BINANCE_TESTNET=true \
cargo run -p trading-bot-rust -- --native-live-smoke
```

Optional inputs:

- `BINANCE_LIVE_SMOKE_SYMBOL`, default `BTCUSDT`
- `BINANCE_LIVE_SMOKE_INTERVAL`, default `1m`
- `BINANCE_TESTNET`, default `true`

Before running the live smoke, operators can check prerequisites without
network access or secret output:

```bash
cargo run -p trading-bot-rust -- --native-live-smoke-preflight
```

The preflight prints redacted JSON with explicit prerequisite booleans, does not contact Binance,
does not write evidence, and exits non-zero until
`BINANCE_API_KEY`, `BINANCE_API_SECRET`, and `TRADING_BOT_RUST_LIVE_SMOKE=1` are
present. The local preflight checker also requires the reported
`python_source_contract_hash` to match the current Python source-of-truth
contract, so stale Rust preflight output cannot satisfy the evidence gate.

The same read-only signed account smoke can be collected in GitHub Actions with
the manual `.github/workflows/rust-native-live-smoke.yml` workflow. Configure
the repository secrets `BINANCE_API_KEY` and `BINANCE_API_SECRET`, dispatch the
workflow with the desired testnet flag, symbol, and interval, and download the
`rust-native-live-smoke-evidence` artifact. The workflow runs the preflight
first, executes `--native-live-smoke`, validates only the two live-smoke
artifacts, and uploads `rust-native-live-market-data-smoke.json` plus
`rust-native-live-account-read-smoke.json`. It also uploads
`rust-native-live-smoke-evidence-plan`, a post-smoke runbook showing remaining
promotion blockers for that source revision. The plan upload uses `always()`
and `if-no-files-found: warn`, so a failed smoke attempt still leaves the
operator runbook when checkout and Python tooling reached the plan step.

Those artifacts are valid only when they include the expected endpoint rows and
operation-level suite results. Market data evidence must prove USDT symbol,
kline, and ticker fetches. Signed account evidence must prove position mode,
multi-assets mode, USDT balance with `balances_redacted: true`, and open
position reads. It must also include redacted environment metadata with
`api_key_present: true`, `api_secret_present: true`, `signed_account_read: true`,
and `secrets_in_artifact: false`.

Market-data evidence can also be collected separately without account
credentials:

```bash
cargo run -p trading-bot-rust -- --native-live-market-smoke-preflight
TRADING_BOT_RUST_MARKET_SMOKE=1 \
BINANCE_TESTNET=true \
cargo run -p trading-bot-rust -- --native-live-market-smoke
```

That public/read-only command writes only
`rust-native-live-market-data-smoke.json`. It never submits orders and never
reads signed account state. Signed account evidence still requires the guarded
`--native-live-smoke` command above.

Local/CI verification also exercises the preflight contract with missing-env
and dummy-env runs for the signed smoke plus missing/confirmed runs for the
market-data smoke, confirms dummy secrets are not printed, and confirms no
evidence artifacts are written. It also rejects preflight output whose
`python_source_contract_hash` is stale relative to the current Python source:

```bash
python tools/check_rust_native_live_smoke_preflight.py --json
```

This smoke command is evidence plumbing only. Passing it is still not enough to
change `rust_native_trading_runtime_ready()` to `true`; the project also needs
live recovery tests and release evidence before standalone native Rust trading
can be enabled.

### Deterministic local recovery evidence

Rust can also write local regression evidence for stream recovery, order guard,
order audit, runtime order engine, and risk-close behavior without using live
credentials:

```bash
cargo run -p trading-bot-rust -- --write-local-recovery-evidence
```

This writes `rust-native-live-stream-recovery.json` and
`rust-native-order-guard-recovery.json` with
`evidence_scope: deterministic_local`. Use
`RUST_NATIVE_RUNTIME_EVIDENCE_DIR` to redirect the output during local testing.
These artifacts prove deterministic recovery regressions, but they still do not
replace live-smoke or release-platform evidence and do not change
`rust_native_trading_runtime_ready()` to `true`.

The CI/local verifier runs the same command in an isolated evidence directory
and validates only the deterministic recovery artifacts against the shared
manifest:

```bash
python tools/check_rust_native_local_recovery_evidence.py --json
```

The required evidence contract lives at
`docs/rust-native-runtime-evidence.json`. Validate the declaration with:

```bash
python tools/check_rust_native_runtime_evidence.py --schema-only
```

To validate artifacts from a temporary output directory, pass:

```bash
python tools/check_rust_native_runtime_evidence.py --require-evidence --evidence-dir <artifact-dir>
```

For promotion, also require the evidence files to match the checked-out
committed source revision and to have been generated from a clean tracked
source tree:

```bash
python tools/check_rust_native_runtime_evidence.py --require-evidence --require-current-commit --require-clean-source --evidence-dir <artifact-dir>
```

Evidence `generated_at` values must use `unix:<seconds>` format; the validator
rejects free-form timestamps.

### Release/platform evidence

The release evidence artifact is generated from real release inputs, not from a
local source build. After the Rust release assets exist on GitHub and every
release platform/browser target has a passed evidence JSON file, write the Rust
runtime release artifact with:

```bash
python tools/write_rust_native_release_evidence.py \
  --tag <tag> \
  --platform-evidence-dir release-platform-evidence \
  --preflight \
  --json
```

The preflight command does not contact GitHub and does not write artifacts. It
reports the required Rust release asset names, local platform evidence coverage,
and whether the final evidence writer has enough local inputs to be attempted.

```bash
python tools/write_rust_native_release_evidence.py \
  --tag <tag> \
  --platform-evidence-dir release-platform-evidence
```

That command writes `rust-native-release-platform-evidence.json` only when the
required Rust release assets are present and
`tools/check_release_platform_matrix.py --require-evidence
--require-current-commit --require-clean-source` would pass for the same
evidence directory. The preflight JSON's `missing_platform_evidence_plan`
includes the exact `target_validation_command` to run after each target probe.
The aggregate artifact embeds every target's passed `suite_results`; platform
targets must carry the `platform-probe.target_match.matched: true` proof in
that embedded suite list, not only a target count. It also records the
`evidence_file` and `evidence_sha256` for each source target JSON.
Each per-target evidence JSON must prove every suite declared for that target in
`docs/release-platform-test-matrix.json`. A platform probe alone is not enough
for desktop targets that also require Python service, desktop release, and
native build smoke coverage.
Each per-target JSON must also come from the same candidate source revision:
`tools/run_release_platform_probe.py` writes the git commit,
`source_tree_clean`, and Python source-contract hash, and the release evidence
writer rejects stale, dirty, or mismatched target artifacts before aggregation.
While collecting evidence target by target, validate the just-written artifact
without requiring the rest of the matrix yet:

```bash
python tools/check_release_platform_matrix.py \
  --require-evidence \
  --require-current-commit \
  --require-clean-source \
  --evidence-dir release-platform-evidence \
  --target-filter <target-id>
```

Those promotion flags make the single-target check reject stale commit,
dirty-source, mismatched Python source-contract, premature runtime-ready, or
unredacted target artifacts before they reach the aggregate release writer.

The same aggregation can be run in GitHub Actions with the manual
`.github/workflows/rust-native-release-evidence.yml` workflow. Provide the
release tag and, when the per-target evidence was produced by Actions, the run
id containing `release-platform-evidence-*` artifacts. The workflow downloads
those JSON artifacts, runs the preflight, writes and validates
`rust-native-release-platform-evidence.json`, and uploads the
`rust-native-release-platform-evidence` artifact. It also uploads
`rust-native-release-platform-evidence-plan`, a post-release runbook showing
remaining promotion blockers for that source revision. The plan upload uses
`always()` and `if-no-files-found: warn`, so a failed release-evidence attempt
still leaves the operator runbook when checkout and Python tooling reached the
plan step.

Before any standalone native Rust runtime promotion, first prove the Python-owned
C++/Rust/Tauri source catalogs are synchronized and export the current evidence
collection plan:

```bash
python tools/audit_native_source_sync.py --json
python tools/audit_rust_native_runtime_readiness.py --json --write-evidence-plan artifacts/rust-native-runtime-evidence-plan.md
```

The main CI workflow writes and uploads the same
`rust-native-runtime-evidence-plan` artifact, so operators can download a
revision-specific runbook before collecting live or release evidence. Each row
in that runbook includes `required_runtime_ids` plus an import command with the
matching `--require-runtime-id` flags; for the signed live-smoke artifact, the
plan requires both market-data and account-read evidence. For release-platform
evidence, the runbook also carries the bounded `missing_platform_evidence_plan`
with each missing target's promotion-grade `target_validation_command`.
`tools/check_rust_native_evidence_workflows.py --json` covers that main CI gate
and the manual live-smoke, release-platform target, release-evidence, and
promotion-audit workflows, so the workflow wiring is checked against the same
commit-bound importer and readiness rules as the runtime evidence validators.

After the manual live-smoke and release-evidence workflows have produced
artifacts for the same candidate commit, run the manual
`.github/workflows/rust-native-promotion-audit.yml` workflow with those two
Actions run ids. The promotion workflow downloads the artifacts under
`artifacts/rust-native-runtime-evidence/downloads/`, imports them with
`--apply --overwrite --require-current-commit --require-clean-source` plus the
three required `--require-runtime-id` flags, logs copy versus overwrite actions
with existing/incoming evidence hashes, generates deterministic local recovery
evidence for the checked commit, validates the full runtime evidence set, and runs
`tools/audit_rust_native_runtime_readiness.py --require-ready --json`. It also
uploads `rust-native-promotion-evidence-plan` and
`rust-native-runtime-promotion-evidence` artifacts for review.

Download the live-smoke and release-evidence workflow artifact ZIPs or folders,
then import them through the validator instead of copying them manually:

```bash
python tools/import_rust_native_evidence_artifacts.py <artifact.zip-or-dir> --apply --require-current-commit --require-clean-source --require-runtime-id rust-native-live-market-data-smoke --require-runtime-id rust-native-live-account-read-smoke --require-runtime-id rust-native-release-platform-evidence
```

The importer validates runtime artifacts against
`docs/rust-native-runtime-evidence.json` and release-platform target artifacts
against `docs/release-platform-test-matrix.json`. In promotion mode it rejects
stale runtime and release-platform evidence, dirty-source evidence, evidence
collected from a different commit, and evidence carrying an older Python
source-contract hash before it can enter the canonical artifact directories.
Rust evidence writers stamp `source_tree_clean` with the same clean-source
scope: untracked source/tool files outside the canonical evidence directories
make the artifact non-promotion-grade, while generated evidence files under
`artifacts/rust-native-runtime-evidence/` and `release-platform-evidence/` are
excluded from that cleanliness decision.
Those runtime and release-platform evidence JSON/ZIP/download artifacts are
ignored generated outputs; do not hand-edit or commit them as source.
The aggregate `tools/verify_all.py` command dry-runs the same strict importer
against existing local evidence directories. If old ignored evidence remains in
the workspace, that check should fail until the directories are cleaned or fresh
candidate-commit artifacts are imported.

After the required artifacts are attached under
`artifacts/rust-native-runtime-evidence/`, run:

```bash
python tools/check_rust_native_runtime_evidence.py --require-evidence --require-current-commit --require-clean-source
python tools/audit_rust_native_runtime_readiness.py --require-ready
```

The non-promotion audit is safe for CI while Rust remains guarded as not ready:

```bash
python tools/audit_rust_native_runtime_readiness.py --json
```

That audit reports per-artifact status, remaining evidence IDs, redacted
live-smoke prerequisites, release evidence prerequisites, native source-sync
status, Python runtime-readiness source flags, dirty/untracked promotion-source
paths, the structured evidence collection plan, and next actions. It fails
promotion if `Languages/Python/app/native_parity.py` disagrees with
`rust_native_trading_runtime_ready()`, so Python remains the source of truth for
the runtime-ready claim boundary. It does not print secret values.

## Python app contract parity audit

The Rust workspace exposes a Python app source-contract parity matrix through
`native_python_app_parity_domains()`. That matrix is intentionally separate from
standalone runtime/product parity: mirrored controls and generated route catalogs
are useful, but they do not mean Rust owns the Python app's trading execution
behavior or has release evidence for every platform.

Current source-level guards:

- `native_python_app_contract_parity_ready() == true`
- `cpp_entire_python_app_contract_parity_ready() == true`
- `rust_entire_python_app_contract_parity_ready() == true`

Current standalone runtime/product guards:

- `native_full_python_app_parity_ready() == false`
- `cpp_entire_python_app_parity_ready() == false`
- `rust_entire_python_app_parity_ready() == false`

The tracked domains are desktop shell/tabs, Service API contract, config
persistence, strategy runtime, exchange connectors, account/portfolio/positions,
order execution/risk, backtest engine, charts/heatmaps, logs/terminal
diagnostics, LLM advisory, and startup/packaging/platform integration.

## Build examples

From `experiments/rust-shells`:

```bash
cargo run -p trading-bot-rust
cargo run -p trading-bot-tauri-desktop
```

If `cargo` is not installed yet, install Rust with `rustup` first.

## Recommendation

Use this workspace when you want to:

- build shared Rust contracts/core incrementally
- work on the Tauri Service API client shell
- prototype a future Rust-native runtime

If you want the most complete working app today, use `Languages/Python`.
