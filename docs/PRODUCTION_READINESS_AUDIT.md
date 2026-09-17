# Production readiness audit — 2026-09-17

## Verdict

**58/100 for an unattended real-money product. Not approved for unattended live deployment.**

The project has a substantial, tested engineering foundation, particularly the Python Binance order-intent/reconciliation path. It is not merely a prototype. However, confirmed integration/security defects, gaps in crash-independent risk protection, and unverified operational evidence prevent production sign-off. Green CI is necessary but insufficient.

This is an engineering assessment, not a probability of avoiding losses, a profitability score, a penetration-test certificate, or regulatory approval. No live orders, account requests, deployments, credential changes, or repository-setting changes were made during this audit. Only audit/plan/handoff documentation was changed.

**Start/continue work:** [handoff](PRODUCTION_HANDOFF.md) → [implementation plan](PRODUCTION_IMPLEMENTATION_PLAN.md). The plan is the authoritative task-status register; this audit preserves the baseline findings.

## Scope, provenance, and limits

- Repository: `Yunushan/trading-bot`.
- Audited clean source: `e574dae633d2186b8af4af1013076ff91f778bb9` (`main`).
- Evidence snapshot: **2026-09-17 09:09 UTC** (12:09 Europe/Istanbul). Recheck remote state before acting; this is not a live dashboard.
- Primary target assessed: canonical Python runtime, Binance execution, desktop-hosted or write-enabled Service API, and enabled LLM/connector surfaces, operated unattended with real funds.
- Hosted read-only observer, supervised demo/testnet, unattended trading, and multi-host execution are different release scopes. The score must not be transferred between them.
- Native C++/Rust, mobile, unusual OS targets, and additional brokers remain separately evidence-gated. Their mere existence is neither proof of production support nor a requirement to ship a narrower Python/Binance product.
- Method: independent trading, security, operations/release reviews; source/test/call-path inspection; safe synthetic reproductions; local offline checks; current GitHub CI logs and public branch metadata.
- This was a deep risk-focused audit, not an exhaustive line-by-line review of every file or every venue. No production telemetry, real account reconciliation, physical power-loss test, operator paging test, or signed-release installation was performed.
- Evidence levels below: **R** = reproduced offline; **S** = source-inspected behavior/gap; **E** = external assurance missing or unverified; **L** = documented scope limitation. Missing evidence in this checkout does not prove it exists nowhere else.

## Scorecard

Points reflect demonstrated assurance within the stated target. Approximate anchors: 0% absent/unsafe; 25% documented only; 50% meaningful implementation with material gaps; 75% tested with bounded remaining gaps; 100% implementation and operational evidence complete for a deliberately bounded scope. Intermediate points are reviewer judgment, not an automated test statistic. A launch blocker overrides the total.

| Dimension | Earned / weight | Basis for credit and deductions |
| --- | ---: | --- |
| Trading correctness and risk protection | 12 / 20 | Durable Binance intents, validated acknowledgements, partial-fill/reconciliation tests; ccxt collision, live-data validation gap, loop-dependent stops and limited capital policy. |
| Security and credential boundaries | 9 / 15 | Auth/TLS/read-only/redaction foundations; remote LLM credential routing and cleartext endpoint gaps; assurance not a pentest. |
| State, recovery and execution ownership | 8 / 15 | Atomic local ledger and crash/concurrency tests; account-wide fencing, credential rotation, durable budgets and real host-loss recovery not proven. |
| Automated verification and CI | 12 / 15 | 1,851 passing Python tests, broad language/platform jobs, critical coverage gate; integration blind spots, 53.52% overall line coverage, narrow typing, unprotected main. |
| Deployment and release integrity | 4 / 10 | Hardened read-only template and signing policy; reproduced output/identity/topology probe defects, digest provenance gap, release evidence unverified. |
| Operations and production evidence | 4 / 10 | SLO/DR/incident policies and tools exist; required local production artifacts absent, real paging/capacity/account recovery unverified. |
| Architecture and maintainability | 6 / 10 | Python ownership and contracts clear; trading remains desktop-owned, facade extraction incomplete, large exception baseline. |
| Product scope, operator QA and support | 3 / 5 | Explicit evidence-gated catalogs/runbooks; no current scoped production acceptance packet, broad surfaces multiply verification cost. |
| **Total** | **58 / 100** | **Useful beta foundation; unattended production gate remains closed.** |

Do not add points merely for implementing a task or increasing line counts. Re-score from fresh evidence using this same rubric and retain the previous dated assessment.

## What is already strong

1. Python is the canonical trading implementation; LLMs are advisory, not execution authorities. Generated C++/Rust/Tauri contracts have source-sync checks.
2. Binance order storage uses local transaction locks, unique temporary writes, flush/fsync and atomic publication. Uncertain submissions block follow-on submissions; acknowledgements require identity validation; market submission avoids blind POST retries.
3. Tests cover partial fills, reconciliation ambiguity, concurrent ledger updates, interrupted writes, provisioning and shutdown safety. These are meaningful safety tests, not just imports.
4. Non-loopback API exposure requires strong token/TLS handling; constant-time token comparison, request bounds, stream/write limits, read-only middleware and security headers exist. Browser tokens are memory-only in the implementation.
5. Credential-store integration, redaction, LLM context minimization/output policy, advanced-request protected fields and redirect refusal exist. No direct LLM-to-order execution path was found in inspected call sites.
6. Actions are SHA-pinned; Python/Node/Rust/container audits, release signing policies, immutable base images, support matrices and operational evidence rules are present.

## Confirmed defects and priority control gaps

Priority here is engineering severity: P1 = high-priority pre-production issue; P2 = hardening/assurance work. Exploitability depends on the stated preconditions. Implementation phases and exact acceptance criteria are in the linked plan.

### F01 — P1 / R: ccxt advanced parameters can reverse explicit safety intent

`Languages/Python/app/integrations/exchanges/ccxt_diagnostics.py:248–252` uses `setdefault()` for `clientOrderId` and `reduceOnly`; line 280 forwards that dictionary to `create_order()`.

Safe dry-run observation: `reduce_only=True`, `client_order_id='expected-id'`, and `params={'reduceOnly': False, 'clientOrderId': 'different-id'}` produced `{'reduceOnly': False, 'clientOrderId': 'different-id'}`. No exchange client/network/order was used. Production uses the same request dictionary. A risk-reducing intent must not silently become an exposure-increasing order.

Fix: reject protected-field conflicts before client construction, including venue aliases. Assert zero submission calls for rejected inputs. Existing `test_exchange_support_capabilities.py` tests authorization/dry-run behavior but missed this conflict. **Task PRD-004.**

### F02 — P1 / R + S: remote LLM configuration can redirect host credentials

The remote protected-field set at `app/service/config_store.py:47` protects inline `llm_api_key`, but not `llm_api_key_env`, provider, base URL or network-consent fields. `app/service/api/app.py:1088` uses that guard; `app/integrations/llm/providers.py:1208` accepts the reference; `clients.py:27` resolves it from the process environment and request construction attaches it.

A synthetic-only request-builder reproduction showed that the guard accepts an arbitrary fabricated environment-variable name and the resulting request includes its fabricated value as authorization to a selected fictitious endpoint. This is not a demonstrated unauthenticated exploit or full HTTP integration attack. It requires a valid token on a **write-enabled** service. Correct read-only middleware blocks the configuration mutation/prompt POST (`api/app.py:577`). The risk contradicts the intended host-owned credential boundary, even though the token already carries operator privileges.

Fix: host-owned approved credential-reference/destination bindings, consistently enforced for `/config`, `/llm/config`, terminal routes, inference and discovery. Keep model fields editable. **Task PRD-002.**

### F03 — P1 / R + S: LLM inference/discovery permit non-loopback HTTP

`app/settings/validation.py:1021` validates the URL as text. `app/integrations/llm/clients.py:356–384` checks network category, not encrypted transport; line 735 posts directly. `discovery.py:257–270` directly performs discovery GETs. A fabricated `http://example.invalid/v1` was accepted by the real request builder with a fake credential attached.

Default cloud URLs are HTTPS; exposure requires unsafe configuration. Public-network consent does not encrypt traffic. Host-configured HTTP discovery can matter even on a read-only API. Reuse the existing `app/security/network_url.py:25` boundary (already used by local-model operations), retaining explicitly allowed loopback HTTP, redirect refusal and custom/local public-network opt-in. **Task PRD-003.**

### F04 — P1 / R: deployment probe output path fails after rollout

`.github/workflows/deploy-production-readonly.yml:188` places `PROBE_OUTPUT` in `${{ runner.temp }}`, passes it at line 204, and uploads it at line 214. `tools/run_service_sustained_probe.py:228–259` permits outputs only beneath repository `artifacts/operational-readiness/`. Calling the real resolver with an outside-root path raises `ValueError`.

The workflow reaches this failure **after** `kubectl apply`/rollout (line 166): cluster changes can succeed while verification/evidence fails. Existing five workflow string-presence tests all pass. Repair the integration, not the path-confinement safeguard. **Task PRD-006.**

### F05 — P1 / R: deployment quick probe does not enforce server identity/read-only state

The workflow's identity step selects `--profile quick`. `tools/run_service_sustained_probe.py:537–554` only adds identity matching to success for the sustained profile; corresponding suite rows are likewise sustained-only at lines 602–617. It does not validate the server's read-only state.

A fake remote transport returning healthy/fresh data, the wrong commit (`f` repeated 40 times), and server `read_only=false` still yielded `ok=true`, `issues=[]`, and report `read_only=true`. That report field describes a GET-only probe, **not server enforcement**. No network was used. Add explicit expected-commit/read-only requirements or a dedicated deployment smoke, while preserving local quick-test semantics. **Task PRD-006.**

### F06 — P1 / S: immutable container digest is not trusted build provenance

Deployment lines 117–132 compare a pulled digest and producer-controlled OCI source-revision label. They do not verify that the exact digest was built by the approved repository/workflow and passed its scan. Supply-chain workflow lines 176–178/231 build and scan a separate local image; that does not establish identity of an operator-supplied deployment digest. Human approval helps but is not cryptographic provenance.

Require trusted build attestation plus scan/SBOM evidence bound to the same digest, SHA and freshness policy **before** Kubernetes mutation. Desktop signing is not container provenance. **Task PRD-007.**

### F07 — P1 / S: live market data needs an event-time/quality gate

`app/integrations/exchanges/binance/market/market_data.py:224–245` builds raw frames, coerces invalid values to NaN and timestamps cache receipt. `app/core/strategy/runtime/strategy_runtime.py:327–336` generates signals and stamps local current time. `app/core/strategy/orders/operational_snapshot.py:14–18` checks connector/account/portfolio freshness, not candle event time.

In the inspected path, a successful but old or malformed candle response is not rejected by an interval-aware live-data contract before signals. This is source-inspected, **not reproduced order placement**. Other rate-limit guards can block orders; do not infer that every cached response is tradable. Distinguish live versus historical data and exposure-increasing versus risk-reducing actions. **Task PRD-005.**

### F08 — P1 / E: main branch has no enforced protection in the observed public metadata

Read-only GitHub API snapshot: `/branches/main` returned `protected=false`; `/rules/branches/main` returned zero effective rules. CI passes, but the observed main settings do not enforce review/required checks against direct pushes. Environment protection, tag rules, native secret scanning and signing credentials were **not** established by this query.

Verify administrator-visible settings and configure agreed review/check/direct-push/bypass rules through a separately authorized change. Do not rename or enable checks without observing their real contexts. **Task PRD-001.**

## Unattended-operation and architecture limitations

### F09 — P1 / L + S: local loops are not crash-independent protection

Stop loss defaults disabled (`app/settings/risk.py:55`); enabled stops depend on local market state and price (`core/strategy/runtime/strategy_cycle_runtime.py:25`, `strategy_cycle_risk_stop_runtime.py:39`) before submitting a close. No automatic exchange-resident protective-stop installation/reconciliation lifecycle was found in the canonical route.

That is not a claim that software stops violate their documented contract. It is a host/process/network-failure limitation. Unattended promotion needs acknowledged exchange-side protection where supported, or a separately reviewed independent protection model. **Task PRD-010.**

### F10 — P1 / L: ledger lock and session budget are not account-wide control

Intent paths follow the audit path, binding is API-key-based, and locks serialize one file (`orders/order_intent_runtime.py:55,79`, `order_intent_store.py:68`). The runbook explicitly disclaims cross-path/cross-host account fencing and automated credential rotation (`docs/OPERATOR_RUNBOOK.md:70–75,180–184`). A second key or path for one account is not proven to share ownership.

`order_submit_guard_runtime.py:72–76,237–251` keeps a wrapper-local session-attempt counter. It correctly implements a session budget, not durable account/day loss or aggregate exposure control. Defaults (20x leverage, 10% position percentage, 100 attempts) are configurable—not an audited production capital policy. Never change live risk values without an operator decision. **Tasks PRD-008, PRD-009, PRD-011.**

### F11 — P1/P2 / L + S: headless API is not headless trading; state growth unmeasured

`app/service/runners/local_executor.py:2–5,22–23` explicitly says it does not execute strategies/market loops/orders. `app/service/product_main.py:401` directs trading to desktop-hosted mode. `trading_core/strategy.py:5`, `positions.py:5`, `backtest.py:5` re-export `app.core` implementations; extraction is a boundary, not a completed independent engine.

The Kubernetes deployment is a replicated read-only observer, not trading HA (`deploy/kubernetes/production-readonly/README.md:5–9`). Shipping cloud trading requires an explicit executor project; supervised desktop operation does not require an unnecessary rewrite.

The intent store reads/serializes full JSON history and scans intents (`order_intent_runtime.py:95,185`, `order_intent_store.py:20,121`). No long-history latency evidence was inspected. Benchmark before selecting a database migration; deleting deduplication history is not an acceptable optimization. **Tasks PRD-012, PRD-021.**

### F12 — P2 / S: research simulation needs an explicit execution model

Backtest OHLCV validation, fees/slippage, bounded optimizer work and cancellation are real strengths. However, simulation consumes signal index `idx` and enters at that bar's close (`core/backtest/engine_simulation_runtime.py:302,314,431`); same-bar reversal is explicitly tested (`tests/test_backtest_behavior.py:576`). This is a modeling assumption, not proof of a coding look-ahead bug across all indicators.

Before using results to justify capital allocation, document causal signal availability/fill timing, gap/intrabar assumptions, funding/spread/latency/liquidity effects where applicable, data provenance and holdout/walk-forward evaluation. No empirical profitable-strategy claim was verified. **Task PRD-020.**

### F13 — P2 / S: maintainability and security hardening remain

- Risky-pattern audit passes its non-regression baseline, but reports **2,952 broad-exception + 748 silent-pass matches**. These are heuristic matches, not 3,700 confirmed bugs. Prioritize money-path silent failure and observability, not mechanical removal.
- Mypy passed **30 selected source files**; `follow_imports=skip` is not whole-runtime strict typing.
- LLM context defaults can leave model-window budgeting unbounded (`integrations/llm/providers.py:1214`, `clients.py:54`); response bodies are buffered before parsing (`clients.py:735,761`). Add absolute byte/time/concurrency caps independent of configurable model options.
- Seven scoped Rust unmaintained/yanked exceptions expire **2026-10-10** (`tools/rust-audit-policy.json`). They are not seven proven exploitable vulnerabilities. Node policy has no exceptions. Verify current advisory results again for the candidate.
- No dedicated secret-scanning workflow/hook was found in inspected files; GitHub-native scanning/push-protection settings remain unverified.
- Documentation drift: web/API docs mention session-storage tokens though implementation is memory-only; worktree guide understates blocking checks; coverage prose overstates per-descendant enforcement. The actual checker aggregates each configured subtree; it does not enforce a separate threshold on every descendant.

**Tasks PRD-017, PRD-018, PRD-019, PRD-023.**

### F14 — P1 / R + S: production observer topology and probe freshness contract disagree

The real, unseeded standalone service's operational preflight produced only **1 of 4** valid freshness samples in an offline reproduction: execution/account/portfolio timestamps were missing. `tools/run_service_sustained_probe.py:471–494` requires all four. Its local quick path instead seeds synthetic connector/execution/account/portfolio snapshots at lines 367–385, so that local pass does not exercise the deployed topology.

Read-only API mode disables its local executor (`app/service/api/app.py:291–296`); the checked-in Kubernetes topology has no live snapshot-ingestion path and denies egress. This is an integration mismatch, not an observed production outage. Fixing the output path and identity checks alone will not establish a workable production probe.

Define the observer's actual data source/capabilities and a matching versioned health/evidence contract. Test the real unseeded read-only service. Never inject fake production observations or make absent trading data count as fresh: either supply genuine observations through an approved design or explicitly report that capability as unavailable and do not claim trading-monitor freshness. Active-trading freshness requirements must remain strict. **Tasks PRD-006, PRD-015, PRD-022.**

## Operational evidence: not yet a production sign-off

Before audit documents changed the clean checkout, the strict operational command returned `schema_ok=true`, `current_source_tree_clean=true`, **`promotion_ready=false`**. These required local artifacts were missing:

| Required artifact | What must be demonstrated |
| --- | --- |
| `service-api-sustained-runtime.json` | Actual HTTPS deployment, ≥1,800 seconds and ≥18,000 read-only requests, current policy/SHA/freshness. |
| `production-service-slo-window.json` | Genuine rolling 30-day telemetry: availability ≥99.9%, error ratio ≤0.1%, read p95 ≤500ms, operational age ≤120s. |
| `service-config-backup-restore.json` | Recovery objectives met with genuine restore/restart evidence. |
| `incident-audit-continuity.json` | Incident/order-audit continuity and recovery evidence. |

Exact policy: [operational readiness policy](operational-readiness-policy.json). A local quick probe, generated sample telemetry or schema pass cannot satisfy these. Current-SHA/clean-source/freshness restrictions matter: choose and freeze a candidate before collecting commit-bound evidence. A 30-day observation cannot be compressed into a coding session.

Signing-policy validation passes but reports external credentials unknown and signing evidence uncollected. Older `docs/release-qa/v1.0.40.md` is scoped prerelease evidence, not sign-off for this SHA. Actual production TLS, cluster/CNI topology, paging delivery, workload capacity, credential rotation, full account recovery and release install/upgrade/rollback remain to be established. **Tasks PRD-013–016 and PRD-022.**

## Verification ledger

### Remote evidence inspected

| Evidence | Observed result |
| --- | --- |
| [Main CI run 35201147819](https://github.com/Yunushan/trading-bot/actions/runs/35201147819) | Completed success at audited SHA; 24 jobs returned, all successful. |
| [Python Quality job](https://github.com/Yunushan/trading-bot/actions/runs/35201147819/job/105136023323) | **1,851 passed, 1 warning**; **53.52% total line coverage**; selected-file mypy success. Logs also contain temporary-source coverage parse warnings; no failure inferred. |
| [CodeQL 35201147956](https://github.com/Yunushan/trading-bot/actions/runs/35201147956) | Completed success at audited SHA. Not a penetration test. |
| [Supply Chain Security 35201083345](https://github.com/Yunushan/trading-bot/actions/runs/35201083345) | Success on preceding SHA `d004f421ee6cd935968769031d7e72b95312d726`; no same-SHA run observed because push path filtering excluded the final actions-only change. Do not label it a same-SHA scan. |
| [Release Platform Real Tests 35202563575](https://github.com/Yunushan/trading-bot/actions/runs/35202563575) | **In progress** at snapshot. Not counted as passed. Another same-SHA platform run was skipped. |
| CI artifacts | Native-source-sync audit and Rust runtime-evidence plan listed. Their presence is not actual Rust runtime promotion or production telemetry. |

Observed critical line coverage from the Python job:

| Configured subtree (including descendants) | Actual | Required floor |
| --- | ---: | ---: |
| `core.strategy` | 75.54% | 75% |
| `core.positions` | 68.58% | 60% |
| `integrations.exchanges.binance.market` | 69.44% | 65% |
| `integrations.exchanges.binance.orders` | 84.38% | 70% |
| `service.runners` | 87.22% | 80% |
| `settings` | 94.91% | 85% |

### Local checks and reproductions

- Python 3.14.7 / Node 26.8.2: declared-version check passed; strict client-lock metadata check passed.
- Risky-pattern non-regression/high-severity check passed with the counts above.
- `test_production_deployment_workflow.py`: 5 passed; `test_production_deployment.py`: 9 passed; `test_order_intent_store_portability.py`: 1 passed; `test_network_url_security.py`: 5 passed; `test_critical_coverage_gate.py`: 12 passed. **32 offline unittest cases passed** in these targeted suites.
- Web render/preflight, token-storage/stream, and service-contract scripts passed. Mobile service-contract/app-logic and Node audit-policy self-test passed. Tauri UI behavior script passed. This was not the full installed mobile test command or a physical-device test.
- Deployment template and signing-policy source checks passed. Strict operational evidence check failed as described above.
- Safe reproductions confirmed ccxt parameter collisions, synthetic LLM guard/transport construction, probe output-path rejection, wrong-identity quick-probe success and the unseeded observer freshness mismatch. These observations are not committed regression tests yet.
- Full **local** Python suite was not run: active interpreter lacks PyQt6, FastAPI, httpx2, pytest, requests and uvicorn; some attempted trading imports also lacked `binance`. Remote CI supplies the full-suite result, not an invented local pass. No global packages were installed.
- Temporary-directory tests initially hit sandbox access errors; targeted suites above passed when rerun outside that restriction. Those environmental errors are not product defects. Other blocked agent checks were not credited as passes.

## Launch decision

1. Keep unattended real-money promotion closed. Do not equate start/lifecycle success with running trading execution or protective-order acknowledgement.
2. First narrow release candidate: Python/Binance, one identified execution owner, explicitly supervised operation; remote read-only observation initially. This is a **recommended scope**, not permission to start trading or an assertion that it is already signed off.
3. Repair confirmed defects; establish risk/ownership/protection invariants and exact build provenance; gather real recovery/telemetry/operator evidence for the chosen scope.
4. Expand connectors/platforms or enable multi-host execution only through separate evidence-backed gates. Native source parity and observer replicas never substitute for trading-runtime correctness.

This assessment must be refreshed after implementation, branch-policy changes and candidate evidence collection. Documentation completion alone does not change the score or close any product finding.
