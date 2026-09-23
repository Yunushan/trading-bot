# Production implementation plan

**Baseline:** 2026-09-17, `e574dae633d2186b8af4af1013076ff91f778bb9`, **58/100**, unattended production **NO-GO**. See [audit/evidence](PRODUCTION_READINESS_AUDIT.md) and [new-chat handoff](PRODUCTION_HANDOFF.md).

This is the canonical task-status register. It does not authorize deployments, live/testnet orders, new cloud spending, production secrets, repository settings, or risk-limit changes. Those actions require the applicable user/operator authorization. Ordinary implementation and offline tests can proceed when the user asks to implement the plan. The baseline audit did not implement fixes; later implementation checkpoints are recorded below.

## How to use the plan

1. Read `AGENTS.md`, the handoff and relevant audit findings. Inspect current SHA, branch, dirty paths and any newer evidence; do not assume this baseline is still current.
2. Choose one ready task or a small cohesive batch. Confirm its reproducer before changing code. Preserve unrelated changes and the Python source-of-truth boundary.
3. Add failing regression tests, implement the invariant, run focused tests plus appropriate canonical verification. Keep fault injection offline with synthetic credentials and fake exchange/HTTP clients.
4. Record status, actual assignee, changed files, commands/results, remaining risks and commit/PR in this file's work log. A `DONE` task needs acceptance evidence, not a reassuring summary.
5. Update the handoff's next task and blockers. Re-score only from a new dated evidence review; never increment the score automatically.

Statuses: `TODO`, `IN_PROGRESS`, `BLOCKED_EXTERNAL`, `DONE`, `DEFERRED_SCOPE`. Items remain **TODO** unless marked otherwise in the register and work log. Role labels are proposed owners, not assigned people. Dependency `—` means offline work can start now; external prerequisites still apply before a release. Effort: S roughly 0.5–2 engineering days, M 3–5, L 1–2 weeks, XL design/spikes and multiple increments. Estimates exclude reviews, hardware/venue access and observation windows; they are not delivery promises.

## Recommended release path and gates

| Gate | Scope | Exit conditions |
| --- | --- | --- |
| G0 — trustworthy baseline | Source + offline tests | PRD-001 decisions/enforcement recorded; PRD-002–007 fixed for enabled surfaces; candidate CI/security green; no unresolved high-severity scope-relevant defects. |
| G1 — supervised evaluation | Python/Binance on one registered execution host; remote read-only observer | Named operator/account/scope; ownership and durable risk policy; stale-data rejection; ambiguous-order/crash/restart tests; observed paper/testnet lifecycle with explicit authorization; rollback and kill procedure tested. |
| G2 — bounded production pilot | Same deliberately narrow scope | Protective-order/independent-protection proof, trading recovery, signed/provenance-bound release, deployed alerts/restore/capacity evidence, genuine policy-compliant operational artifacts; security review and human risk sign-off. |
| G3 — unattended/general release | Only individually approved targets | All relevant launch blockers closed, current strict promotion gates pass, independent review, explicit support matrix, incident ownership. Recommended reviewed score ≥85/100 **and** all hard gates; score alone never permits release. |
| Separate expansion | Headless trading, additional venues/platforms, native runtime, multi-host | Separate architecture/ownership and per-target evidence. Not prerequisites for a deliberately scoped desktop/Binance release. |

Do not claim G1–G3 is already achieved. G2/G3 operational policy includes a real 30-day window; freeze the candidate and align evidence refresh with exact-SHA requirements. Do not manufacture evidence, relax age/current-SHA rules, or describe a quick probe as endurance testing.

## Task register

The initial offline parallel lanes are security (002→003→018), trading (004 and 005, then 008–011), and deployment (006→007). Coordinate shared files/tests and serialize commits. Ownership, funding limits, production environments and release scope need explicit operator decisions.

| ID | Priority / status | Proposed owner | Effort | Dependencies | Deliverable |
| --- | --- | --- | --- | --- | --- |
| PRD-001 | P1 / BLOCKED_EXTERNAL | Maintainer + release lead | S | — | Scope decision and enforced main/release governance |
| PRD-002 | P1 / DONE | Security + API | M | — | Host-owned LLM credential/destination boundary |
| PRD-003 | P1 / DONE | Security + LLM | S–M | 002 design | Uniform LLM HTTPS/loopback URL policy |
| PRD-004 | P1 / DONE | Exchange runtime | S | — | ccxt protected-order parameter validation |
| PRD-005 | P1 / DONE | Strategy + market data | M | — | Live event-time and OHLCV quality gate |
| PRD-006 | P1 / DONE | Release tooling | M | — | Executable deployment smoke contracts |
| PRD-007 | P1 / IN_PROGRESS | Release + security | M–L | 006 | Exact-digest trusted build/scan provenance; offline workflow/verifier implemented, real publish pending |
| PRD-008 | P1 / TODO | Runtime + operator | L | 001 scope | Account identity and single-owner/fencing contract |
| PRD-009 | P1 / TODO | Risk runtime + operator | L | 008 identity | Durable aggregate risk and kill state |
| PRD-010 | P1 / TODO | Exchange + risk runtime | L–XL | 004,005,008,009 | Crash-independent position protection |
| PRD-011 | P1 / TODO | Runtime QA | L | 005,008,009,010 | Fault-injection and account recovery proof |
| PRD-012 | P2 / DEFERRED_SCOPE | Architecture | XL | 001 decision,008–011 | Headless trading extraction, only if chosen |
| PRD-013 | P1 / TODO | Operations + runtime | M | 005,009 | Deployed alerts, dashboards and runbooks |
| PRD-014 | P1 / TODO | Operations + runtime | M–L | 008,009,011 | Restore/continuity + trading DR evidence |
| PRD-015 | P1 / BLOCKED_EXTERNAL | Operations | ≥30 calendar days | 006,007,013,014,022 | Genuine sustained/SLO production evidence |
| PRD-016 | P1 / BLOCKED_EXTERNAL | Release QA + operator | L | G0,011,014 | Exact-candidate signed release acceptance |
| PRD-017 | P2 / TODO | QA + domain owners | L, incremental | 002–006 regressions | Risk-based coverage, typing and error handling |
| PRD-018 | P2 / DONE | Security + LLM | M | 002,003 | Absolute LLM byte/time/concurrency bounds, verified offline |
| PRD-019 | P2 / IN_PROGRESS | Security + build | M | — | Threat model, secret scanning, dependency evidence |
| PRD-020 | P2 / IN_PROGRESS | Research + runtime | L | 005 data contract | Causal/reproducible backtest validation |
| PRD-021 | P2 / TODO | Persistence + performance | M benchmark; L if migration | 008,009 | Long-history ledger capacity proof |
| PRD-022 | P1 / BLOCKED_EXTERNAL | Operations | M + soak | 006,007,013,016 | Real read-only deployment/rollback/capacity proof |
| PRD-023 | P2 / DONE | Documentation + QA | S | — | Correct stale docs and operating scope, verified offline |
| PRD-024 | P3 / DEFERRED_SCOPE | Connector/platform owners | Per target | G2,001 expansion decision | Evidence-backed expansion only |

Priority is not permission or a CVSS score. External tasks can be prepared with code/tests now, but cannot be closed without their listed real inputs. PRD-019's exception review has a concrete **2026-10-10 expiry**; schedule it before then even while larger work continues.

## Work packages and acceptance tests

### PRD-001 — choose the first product and enforce its release boundary

- Decide and record one initial account/venue, market mode, execution host/OS, operator, remote read/write scope, uptime expectation and supported client surfaces. Proposed baseline: Python/Binance + supervised single-host execution + read-only remote observation. No default live capital limits are selected by this plan.
- Read actual repository settings. With authorization, protect `main` and release tags; require appropriate observed CI/security contexts and review, block force pushes/deletion/direct bypass as agreed. Record administrator bypass/emergency policy, environment approvers and a tested rollback/revert procedure. Account for workflow path filters so required checks do not remain permanently pending.
- Acceptance: sanitized settings export/screenshots/API evidence; a test PR demonstrates failed required checks prevent merge; normal green reviewed PR remains mergeable. Assign named owners to the external tasks.
- Sources: audit F08; `.github/workflows/ci.yml`, `supply-chain-security.yml`, `finalize-release.yml`; external GitHub settings. No code change alone closes this item.

### PRD-002 — bind host secrets to permitted LLM destinations

- Change `app/service/config_store.py`, API mutation/terminal paths and `app/integrations/llm/{providers,clients,discovery}.py` so untrusted remote configuration cannot select arbitrary process environment names or redirect an existing key. Define provider/credential/endpoint bindings at the host administration boundary; prevent indirect bypass via generic config patches or later provider switches.
- Preserve editable/discovered/historical model IDs, provider API styles and safe option pass-through. Avoid a blanket model allowlist as a substitute for credential isolation.
- Acceptance: synthetic env secret plus attacker-chosen fake HTTPS endpoint is rejected before request; reject leaves effective/persisted config unchanged. Test `/config`, `/llm/config`, terminal commands, prompt and discovery paths; trusted host setup and ordinary model edits still work; read-only mutations remain denied.
- Tests: `test_service_config_runtime.py`, `test_service_api_http_contract.py`, `test_llm_clients_privacy.py`, `test_llm_model_discovery.py`; LLM cross-surface gate in AGENTS.md. Audit F02.

### PRD-003 — enforce encrypted LLM transport everywhere

- Centralize inference/discovery URL validation using the owned `app/security/network_url.py` policy. Require HTTPS except explicit loopback HTTP. Reject URL credentials, malformed authority, control characters and fragments. Retain redirect refusal and local/custom public-network consent.
- Acceptance: invalid destinations fail before mocked POST/GET for every API style; loopback Ollama/LM Studio and approved HTTPS work; endpoint edits cannot bypass PRD-002. Check equivalent C++/Rust/Tauri surfaces through Python-owned parity generation and targeted tests, not hand edits of generated files.
- Tests: privacy, redirect, discovery, local-model and URL-security suites; settings/catalog/serialization/output/redaction/native gates. Audit F03.

### PRD-004 — prevent ccxt order-parameter collisions

- In `app/integrations/exchanges/ccxt_diagnostics.py`, define protected order fields and venue-specific aliases; reject conflicts with explicit order arguments. Use broker `_order_validation.py` patterns where appropriate. Invalid input must fail before exchange-client construction.
- Acceptance: conflicting `reduceOnly` in both directions, conflicting client IDs, malformed mappings and aliases fail with **zero** `create_order()` calls; valid dry-run and injected-client requests preserve exact intent. Do not silently broaden ccxt live support.
- Tests: `test_exchange_support_capabilities.py` plus new parameterized collision cases. Audit F01.

### PRD-005 — make source-data validity part of live order permission

- Add an interval-aware live-data validation result carrying exchange event time, receipt time, clock skew, source, closed/open-bar semantics, monotonic/unique index, gap policy and finite OHLCV validation. Wire the result through strategy signals and the exposure-increasing order guard. Never refresh stale source data by assigning a new local signal timestamp.
- Keep historical backtest retrieval distinct. Specify how risk-reducing/manual emergency exits obtain reliable execution information without unnecessarily trapping existing exposure.
- Acceptance: stale-but-successful REST, stale/replayed/out-of-order websocket data, duplicates, future clocks, reconnect gaps, NaN/invalid OHLC and negative volume block new exposure and surface actionable reasons. Fresh recovery restores permission only after validation; valid historical backtests still run.
- Paths: `binance/market/market_data.py`, `core/strategy/runtime/strategy_runtime.py`, `core/strategy/orders/operational_snapshot.py`. Tests: market-data, operational-preflight and order-risk guard suites. Audit F07.

### PRD-006 — repair and integration-test deployment verification

- Use one allowed canonical evidence path in workflow generation, probe and upload. Validate it before applying Kubernetes changes; preserve output confinement.
- Add a dedicated deployment-smoke mode or explicit expected-SHA/read-only contract. Verify authoritative remote build identity and effective read-only configuration, including mixed replicas; distinguish probe safety from server mode. Never infer server state from a client-side `read_only=true` field.
- Resolve the actual observer topology's freshness contract: its unseeded standalone service lacks three required trading timestamps, while local quick tests seed all four. Define declared capabilities and genuine snapshot acquisition, or explicitly mark unsupported trading observation unavailable in a versioned topology-specific contract. Do not manufacture samples or relax active-trading freshness checks.
- Acceptance: exercise real argument parsing/path resolver/writer using workflow-equivalent arguments and fake HTTP/kubectl. Wrong/missing/mixed commit, writable server, bad origin/redirect, stale data and invalid output path fail. The positive path writes an artifact at the uploaded path. Precondition failures produce zero apply calls; post-apply failures produce an explicit failed verification result and actionable recovery instruction.
- Also test the actual unseeded standalone read-only service, not only mocked/seeded snapshots; prove that its declared scope and strict promotion policy agree and missing required observations fail.
- Paths: `.github/workflows/deploy-production-readonly.yml`, `tools/run_service_sustained_probe.py`, `test_production_deployment_workflow.py`, probe tests. Audit F04/F05/F14. Do not deploy as part of an offline fix.

### PRD-007 — deploy only the trusted scanned container

- Build/publish the candidate once under an approved workflow; attest source/build identity and retain SBOM/scan evidence for its exact immutable digest. Before credentials/mutation, deployment verifies issuer, repository/workflow/ref, digest, commit, scan policy and freshness.
- Acceptance: correctly labeled but unattested image rejected; wrong SHA/digest/workflow identity, missing/stale/failed scan rejected; valid evidence accepted. Integration tests assert no Kubernetes mutation on failure. Document registry retention and rebuild/revocation rules.
- Paths: deployment and supply-chain workflows, container tooling and deployment README. External inputs: registry/publishing trust and authorized credentials. Audit F06.

### PRD-008 — establish account identity and a single execution owner

- First define an enforceable single-host/single-owner scope. Bind state to authoritative account identity rather than only API-key fingerprint; inventory externally running bots/keys. Review credential rotation/migration without losing history.
- If multi-host execution is in scope, design fencing that prevents a stale owner from increasing exposure; a file lock or advisory lease alone is not adequate proof. Do not add active-active trading just because observer replicas exist.
- Acceptance: two processes, distinct ledger paths, two credentials for one account, owner loss/reacquisition, old restored state and credential rotation cannot produce competing authorized owners. Reacquisition requires account/order reconciliation. Document how off-system/manual trading is detected and handled.
- Paths: order-intent runtime/store/provisioning, desktop start lifecycle, service control plane and operator runbook. Operator/account decisions required; offline design/tests may precede them. Audit F10.

### PRD-009 — persist aggregate risk and kill state

- Agree explicit account-wide gross/net exposure, position/concentration limits, realized+unrealized loss policy, order-rate/session budgets, stale-equity policy and authorized resets. Values are operator decisions, not invented by the agent.
- Implement atomic shared accounting across engines, fills and restarts; reconcile external positions/open orders. Distinguish a submission-attempt budget from loss/notional limits. Preserve safe risk-reducing exits when entry budgets are exhausted.
- Acceptance: concurrency, partial/rejected/ambiguous orders, restarts, wrapper replacement, rollover/clock skew, stale equity, external positions and two keys cannot silently reset/bypass limits. Kill state survives restart; reset is explicit and audited.
- Paths: `order_submit_guard_runtime.py`, `app/settings/{live_safety,risk}.py`, strategy risk/position state. Audit F10.

### PRD-010 — make protection survive the execution process

- Design exchange-resident protection for supported market/account modes (or obtain an independently reviewed alternative). Install/verify fill-linked protective orders; handle partial fills, hedge legs, replacement, cancellations and acknowledgement ambiguity. Define the unsafe interval between entry and confirmed protection and a deterministic containment response.
- Acceptance: entry-fill/process-kill, lost protection acknowledgement, rejected stop, partial entry, reconnect, exchange/manual changes and restart do not falsely report protection. Protective orders cannot increase exposure or close the wrong leg. Operator-visible protection state comes from reconciled evidence.
- Paths: Binance orders/positions, strategy stop runtimes, risk settings, reconciliation tests. Venue lifecycle evidence needs explicit sandbox/testnet authorization later; no production-funds test is implied. Audit F09.

### PRD-011 — prove end-to-end trading recovery invariants

- Build a deterministic fake-venue fault harness around the real money path. Cover timeout after exchange acceptance, duplicate/reordered messages, partial fills, auth/rate-limit errors, disk-full/permission/corruption, restart, shutdown, network partition and simultaneous engines. Avoid replacing critical logic with mocks that bypass guards.
- Acceptance: at most one logical order per intent; uncertain exposure blocks new entry; inventory matches validated fills; no false close/protection; kill/ownership state retained; urgent exits have bounded behavior; all unresolved cases are operator-visible. Separate local process-kill proof from physical host/power-loss proof.
- Extend existing intent transaction/reconciliation, market entry/close and shutdown tests. Retain seeds, failure timelines and artifacts. External drills link to PRD-014. Audit F09/F10.

### PRD-012 — optional headless execution extraction

- **Deferred until scope chosen.** If cloud/headless trading is required, extract an owned deterministic executor independent of widgets/Qt event-loop state; expose typed market/risk/order/persistence interfaces. Keep desktop as an adapter to the same implementation. Do not reimplement strategy semantics in Rust/C++.
- Acceptance: representative strategies execute against fake venue with no PyQt/GUI imports; desktop/headless parity, lifecycle, cancellation, reconciliation, protection and restart tests pass. API lifecycle metadata truthfully distinguishes intent/heartbeat/backtest/trading.
- Paths: `app/service/runners`, `app/desktop/service_bridge*`, `app/gui/runtime/strategy`, `app/core`, `trading_core`. Audit F11. Not a prerequisite for deliberately scoped supervised desktop operation.

### PRD-013 — make faults actionable to a real operator

- Instrument order ambiguity, ownership loss, missing protection, market-data age, risk/kill state, reconciliation lag, failed auth, queue/stream saturation, storage errors and clock skew. Bound/redact labels and logs; correlate intent/order IDs without exposing account secrets.
- Acceptance: unit-tested alert rules plus authorized staging fault drills result in actual page delivery, acknowledgement/escalation and recovery verification. Missing telemetry itself alerts. Record named primary/backup owners and response actions. Dashboard availability does not imply strategy health.
- Paths: service metrics, deployment monitoring, operational snapshot, operator/preflight runbooks. External inputs: monitoring/paging service and on-call owners. Audit F07/F13 and operational evidence section.

### PRD-014 — restore both configuration and trading state safely

- Define encrypted backup/retention/restore access for configuration, ledger/risk/ownership state and audit history. Keep credentials out of exported evidence. Exercise an isolated restore with credentials disabled, then reconcile before re-enabling any execution.
- Acceptance: meet policy RTO/RPO for config/process/audit and separately defined trading-account objectives; prove no duplicated entry after restored snapshot, preserved unresolved intents/kill state, key-rotation procedure and operator reconciliation. Record genuine continuity/recovery artifacts tied to the candidate.
- Paths: recovery/continuity tools, order store, runbook, `operational-readiness-policy.json`. Source tests alone do not close real DR proof. Audit F10 and operational evidence section.

### PRD-015 — collect the actual production observation window

- External blockers: approved HTTPS read-only environment, candidate SHA/image, secure service-token injection, monitoring export, named owner, clean source and time. Start the real observation window only after relevant fixes/candidate selection; keep telemetry origin and digest provenance.
- Prerequisite: PRD-006/F14 must establish a truthful topology/capability-specific observation contract. A policy change needs explicit review/versioning and preservation of active-trading safeguards; missing required trading observations cannot be labeled fresh to unblock promotion.
- Acceptance: sustained ≥1,800s/18,000 requests plus genuine rolling 30-day SLO data, recovery and continuity artifacts; all meet exact policy thresholds/age/SHA rules. Run `python tools/check_operational_readiness.py --require-evidence --require-current-commit --require-clean-source --json` successfully from the approved candidate with imported artifacts.
- Never hand-author `passed:true`, reuse sample telemetry, mark a local quick probe production-ready, or weaken policy to shorten the wait. If a candidate changes, explicitly reassess/recollect invalidated evidence. Audit operational evidence section.

### PRD-016 — assemble a release acceptance packet

- External inputs: chosen supported OS/browser targets, real signing/notarization access, QA devices, approved test accounts, release owner. Verify exact candidate binaries/image rather than unrelated previous release assets.
- Acceptance: install/start/upgrade/rollback, credential entry/rotation, stop/close recovery, API/client auth, stale-data/error UX, accessibility/basic usability and optional LLM flows checked on declared targets; hashes/signatures/notarization/provenance verified; no unverified target labeled supported. Obtain operator/security approval and retain links to artifacts.
- Use existing release matrix/finalizer/evidence tooling. Hosted-only prerelease QA does not become full release sign-off. No unsigned fallback for required signed targets. Audit release evidence limits.
- This package covers **pre-deployment** artifact/installer/staging acceptance. The current production workflow additionally requires a protected semantic-version tag and published stable release: establish the authorized, explicitly scoped release before PRD-022. Publishing that artifact does not approve unattended trading; post-deployment operational acceptance and G2/G3 sign-off still depend on PRD-015/022. Record these as distinct decisions, avoiding a circular dependency on already having deployed production.

### PRD-017 — improve assurance where a missed branch can cost money

- First add regressions for F01–F07; replace presence-only workflow checks with executed contracts. Publish retained coverage XML/JSON and per-file critical hot spots with the tested SHA; explain temporary-source warnings.
- Add branch/fault/invariant tests for validation, persistence, stale data and risk/protection decisions; use mutation testing on bounded pure guards if useful. Raise floors incrementally only after real coverage exists; do not lower existing gates.
- Expand typed interfaces at money-path boundaries beyond the current 30-file set. Reduce selected broad-exception/silent-pass handlers by giving failures explicit safe states and telemetry; do not delete defensive catches indiscriminately.
- Acceptance: each high-priority fix has a pre-fix failing test; policy aggregation semantics documented honestly; coverage does not fall; injected faults exercise the blocking behavior, not only a string or returned status. Audit F13/verification ledger.

### PRD-018 — bound LLM resource consumption

- Add hard request/context/response byte limits, connect/read/total deadlines and concurrent-call limits independent of model-specific tokens. Stream/bound responses before full JSON allocation where appropriate; release capacity on cancellation/error. Keep redaction before transport.
- Acceptance: oversized prompt/context/JSON/body, slow response, never-ending stream, concurrent callers and cancellation remain bounded; redacted actionable errors returned; allowed future model option tokens remain valid. No direct execution permissions added.
- Paths: LLM clients/discovery/providers, API handlers, privacy/network tests. Audit F13.

### PRD-019 — close security-assurance and dependency drift gaps

- Document single-operator versus multi-user trust boundaries, token issuance/rotation/revocation, host-only credential references, endpoint trust, release trust and incident handling. Do not claim shared bearer token supplies role-based authorization.
- Verify native secret-scanning/push-protection settings or add an enforced equivalent PR/history scan with redacted results. Never paste found secrets into the task log; coordinate rotation outside committed docs.
- Review/remove the seven Rust exceptions before **2026-10-10**, including upstream/vendor-patch provenance. Fresh Python/Node/Rust/container results must match candidate scope. Assess hash-locked Python deployment/build constraints and remaining ranged dependencies so clean builds can be reproduced.
- Acceptance: threat review recorded, fake-secret regression detected, no unreviewed high/critical findings under policy, exact remaining exceptions with owner/expiry and rationale, two clean candidate builds have explainable dependency manifests. No blanket audit ignores.
- Paths: SECURITY.md, workflows, `tools/*audit*policy*`, Python packaging, Cargo/npm locks. Audit F13.

### PRD-020 — validate research-to-live assumptions

- Specify when each signal becomes knowable and the earliest executable fill. Make same-close/next-bar assumptions explicit; model gaps/intrabar order ambiguity, fees/slippage and market-specific funding/spread/latency/liquidity where needed. Version dataset hashes, time zones, symbol metadata and configuration/seeds.
- Acceptance: synthetic causality tests cannot consume future observations; conservative gap/stop/fill cases and cost sensitivity are reproducible; holdout/walk-forward and overfitting controls are recorded before using an optimized strategy for capital allocation. Compare intended live signals with offline replay. Profit is not an acceptance criterion for software correctness and no profit guarantee is implied.
- Paths: backtest data/signal/simulation/optimizer modules, `test_backtest_behavior.py`, strategy replay tests. Audit F12.

### PRD-021 — benchmark long-lived state before redesigning it

- Exercise 10k/100k+ realistic intent histories, unresolved records, concurrent reads/writes, slow/full disk and urgent close/reconciliation. Define p95/p99/disk-growth budgets with the operator; record hardware/configuration.
- Acceptance: measured bounds meet the selected workload; otherwise implement a separately reviewed transactional indexed journal/snapshot migration. Preserve dedup IDs, unresolved intents, identity binding, atomic migration and audit continuity. Never delete history just to pass a benchmark.
- Paths: order-intent runtime/store/provisioning and capacity tooling. Audit F11.

### PRD-022 — prove the read-only topology on its actual infrastructure

- External inputs: authorized cluster, registry digest/provenance, PRD-016 pre-deployment acceptance with protected semantic-version tag/published scoped stable release, TLS origin, CNI/network policies, secret management, monitoring and capacity envelope. Verify ingress/auth, non-root/read-only filesystem, egress denial, service-account isolation, anti-affinity/PDB/HPA and resource limits on the actual platform.
- Acceptance: exact build/read-only identity confirmed across replicas; load/SSE-client soak meets budget; pod/node loss and rollout/rollback behave as documented; failed verification triggers an operator response; rollback returns to an explicitly trusted previous digest without widening permissions. Produce genuine deployment/capacity evidence.
- Do not run trade execution in these replicas or claim trading HA. Paths: `deploy/kubernetes/production-readonly`, deployment/capacity tools/workflow. Audit F04–F06/F11.
- Exercise the actual unseeded observer and its agreed data-source/capability contract (F14), including absent observations and disconnected upstreams. No synthetic production timestamps or silent substitution of observer availability for trading-data freshness.

### PRD-023 — align documentation with actual contracts

- Correct memory-only versus session-storage token descriptions, worktree-guide blocking/advisory descriptions and critical-coverage subtree-versus-descendant wording. Repair `check_critical_coverage.py` remediation pointing to nonexistent root `tools/run_python_tests.py`; real runner is `Languages/Python/tools/run_python_tests.py`.
- Acceptance: documented commands/paths exist and their help executes; auth/storage wording matches tests; supported/scaffold/evidence-gated distinctions and single-host/read-only/headless limitations are consistent. Keep this audit historical; append outcomes rather than erasing unfavorable baseline evidence.
- Paths: web README, SERVICE_API, WORKTREE_REVIEW_PLAN, QUALITY_AND_EVIDENCE_GATES, coverage tool. This is planned follow-up, not a runtime change in the audit turn.

### PRD-024 — expand only after the narrow product is supportable

- Separate backlog per connector, desktop target, native runtime and mobile platform. Bring each live order route up to the chosen risk/idempotency/reconciliation/protection standard before venue lifecycle evidence. Preserve Python contract ownership.
- Acceptance: current clean candidate, capability-complete artifact and approved sandbox/testnet order lifecycle with cleanup/redaction for each venue; actual device/OS/installer evidence for each target; Rust standalone guard stays false until its own strict promotion gate passes. Unchosen targets remain explicitly evidence-gated, not silently removed or promoted.

## Verification and evidence recording

For documentation-only changes, validate local links, task IDs/dependencies and `git diff --check`; do not pretend that rerunning source CI creates production evidence. For implementation use repository instructions and the relevant existing runners:

```powershell
# Read-only baseline checks (repository root)
git status --short --branch
git rev-parse HEAD
python tools/check_local_tool_versions.py --json
python Languages/Python/tools/run_python_tests.py --check-deps

# Focused tests, after installing the declared dev dependencies in an isolated environment
# Use the actual task's test files; --no-cov is for this focused diagnostic run only.
python -m pytest Languages/Python/tests/test_exchange_support_capabilities.py --no-cov -q

# Canonical full source verification; missing prerequisites are not passes
python tools/verify_all.py
git diff --check

# External promotion gate, only after legitimate candidate evidence is imported
python tools/check_operational_readiness.py --require-evidence --require-current-commit --require-clean-source --json
```

The canonical runner handles full-suite coverage; focused `--no-cov` never replaces that gate. LLM changes additionally require catalog/config/request/context/output/model-discovery/parity/Rust/C++/Tauri checks per AGENTS.md. Generated parity changes come from Python and its generator. Do not run workspace cleanup blindly; inspect and preserve user artifacts/changes.

Evidence records must identify: task ID; source SHA; clean/dirty state; environment/tool versions; exact command; result/counts; artifact URL/hash; redaction status; reviewer; limitations. Do not commit tokens, account identifiers, private telemetry, or generated promotion artifacts in violation of repository policy. Store approved generated evidence in canonical ignored directories and durable external artifact storage; link sanitized metadata here.

## Work log and checkpoint

### 2026-09-17 — audit/plan created

- Source baseline: `e574dae633d2186b8af4af1013076ff91f778bb9`.
- Completed work: risk-focused audit, safe reproductions, verified current CI/logs, 32 targeted local offline unittest passes, web/mobile/Tauri checks, documentation/handoff creation.
- Product fixes completed: **none in this audit task**. All statuses above intentionally remain open/deferred/external.
- Next recommended implementation: **PRD-002**, alongside independent **PRD-004** and **PRD-006** if parallel work is available; begin PRD-001 operator decisions. PRD-005 follows immediately in the trading lane.
- External inputs not supplied: production release scope/owners/risk policy, account/host ownership proof, repository-setting authorization, deployment registry/cluster/TLS/telemetry, signing/QA evidence. Do not invent them.

### 2026-09-17 — PRD-002 implementation checkpoint

- Status: **DONE** (offline implementation; production promotion remains out of scope).
- Assignee and scope: Codex implementation checkpoint; Python service/API/remote-terminal mutation boundary, regression coverage, service documentation and generated parity artifacts.
- Starting SHA and state: `0e7cc787f70d730866a84cd84cd7ca7a4d057e4b`, clean before this change; no unrelated paths were modified.
- Failure reproduced: the F02 synthetic audit showed that a remote caller could select an arbitrary LLM environment-variable name and endpoint. Remote `/config`, `/llm/config` and terminal mutations now reject provider, credential-reference, destination and public-network-consent fields before persistence; model and validated advisory options remain editable.
- Files and behavior changed: `app/service/config_store.py` protects `llm_api_key_env`, `llm_base_url`, `llm_allow_public_network` and `llm_provider`; API error guidance and `docs/SERVICE_API.md` describe the host-owned boundary; HTTP/terminal regression tests cover rejection plus allowed model/options; native/C++/Tauri parity contracts were regenerated from the Python source of truth.
- Tests and exact outcomes:
  - `.\.venv\Scripts\python.exe -m pytest Languages/Python/tests/test_service_api_http_contract.py Languages/Python/tests/test_service_config_runtime.py Languages/Python/tests/test_service_client_integration.py Languages/Python/tests/test_llm_clients_privacy.py -p no:cacheprovider --no-cov -q` — **73 passed, 1 skipped** (host symlink capability), 1 dependency warning.
  - `.\.venv\Scripts\python.exe -m pytest Languages/Python/tests/test_llm_model_discovery.py Languages/Python/tests/test_llm_local_models.py Languages/Python/tests/test_llm_redirect_safety.py Languages/Python/tests/test_native_option_parity.py Languages/Python/tests/test_native_generated_parity_contract.py Languages/Python/tests/test_native_full_parity_contract.py Languages/Python/tests/test_service_api_host_contract.py -p no:cacheprovider --no-cov -q` — **95 passed, 341 subtests passed**.
  - `.\.venv\Scripts\python.exe -m ruff check Languages/Python/app/service/config_store.py Languages/Python/app/service/api/app.py Languages/Python/tests/test_service_api_http_contract.py` — **all checks passed**; `git diff --check` passed; parity generator reported `changed=True`.
- Commit: `6335304f593ae70383c2b454f6e0c707f20e29d5` (`Harden remote LLM configuration boundaries`). No PR or push was created.
- Acceptance items still open: host-approved provider/endpoint binding must be configured and verified on the eventual execution host; HTTPS/loopback URL enforcement is PRD-003; no live request, deployment or production secret was used. Re-run the complete canonical gate before any score change.
- External blockers / decisions needed: initial product scope, repository governance, deployment/provenance inputs and operational evidence remain unchanged from the audit.
- Next ready task: **PRD-003** (uniform LLM HTTPS/loopback URL policy), with independent **PRD-004** and **PRD-006** still ready.
- Score change: **not assessed**; the dated baseline remains 58/100 until a fresh evidence review.

### 2026-09-17 — PRD-003 implementation checkpoint

- Status: **DONE** (offline implementation; production promotion remains out of scope).
- Assignee and scope: Codex implementation checkpoint; shared URL policy, LLM inference/discovery transport, local-model helper reuse and regression coverage.
- Starting SHA and state: `b3617649a62218619e0a3750264ba0ccfdf12391`, clean before this change; no unrelated paths were modified.
- Failure reproduced: the F03 audit identified that LLM inference and model discovery used direct `requests` calls without the shared HTTPS/loopback URL validator, so public HTTP custom endpoints could pass when network consent was enabled. Invalid endpoint text could reach the request layer.
- Files and behavior changed: `app/security/network_url.py` now exposes the shared loopback/public-network policy and rejects control characters, credentials, fragments and malformed authorities; inference and discovery validate base URLs before POST/GET and retain explicit public-network consent; local-model validation uses the public shared loopback helper. New tests cover every provider API style, invalid destinations before network calls, loopback HTTP, private addresses and approved HTTPS.
- Tests and exact outcomes:
  - `.\.venv\Scripts\python.exe -m pytest Languages/Python/tests/test_network_url_security.py Languages/Python/tests/test_llm_url_security.py Languages/Python/tests/test_llm_clients_privacy.py Languages/Python/tests/test_llm_model_discovery.py Languages/Python/tests/test_llm_redirect_safety.py Languages/Python/tests/test_llm_local_models.py -p no:cacheprovider --no-cov -q` — **49 passed, 196 subtests passed**.
  - `.\.venv\Scripts\python.exe -m pytest Languages/Python/tests/test_service_api_http_contract.py Languages/Python/tests/test_service_client_integration.py Languages/Python/tests/test_service_config_runtime.py -p no:cacheprovider --no-cov -q` — **58 passed, 1 skipped** (host symlink capability), 57 subtests and 1 dependency warning.
  - `.\.venv\Scripts\python.exe -m ruff check Languages/Python/app/security/network_url.py Languages/Python/app/integrations/llm/clients.py Languages/Python/app/integrations/llm/discovery.py Languages/Python/app/integrations/llm/local_models.py Languages/Python/tests/test_network_url_security.py Languages/Python/tests/test_llm_url_security.py` — **all checks passed**; `git diff --check` passed; parity generator reported `changed=False`.
- Commit: `206fa48a07c8e774faebb51d1470d84e37547058` (`Enforce secure LLM endpoint transport`). No PR or push was created.
- Acceptance items still open: real-host certificate/egress behavior and deployment evidence remain external; no live request or production secret was used. Re-run the complete canonical gate before any score change.
- External blockers / decisions needed: initial product scope, repository governance, deployment/provenance inputs and operational evidence remain unchanged from the audit.
- Next ready task: **PRD-004** (ccxt protected-order parameter validation), with **PRD-006** deployment smoke integration still ready.
- Score change: **not assessed**; the dated baseline remains 58/100 until a fresh evidence review.

### 2026-09-17 — PRD-004 implementation checkpoint

- Status: **DONE** (offline implementation; production promotion remains out of scope).
- Assignee and scope: Codex implementation checkpoint; ccxt order-parameter boundary, exchange-support regression coverage and dry-run/live preflight behavior.
- Starting SHA and state: `9752f7bb20dc6b9d788310e5f32a9afd0509eb1e`, clean before this change; no unrelated paths were modified.
- Failure reproduced: the F01 audit showed that `submit_order` used `setdefault` for `clientOrderId` and `reduceOnly`, silently allowing conflicting aliases in `params` to override validated explicit intent. Non-mapping params were also ignored instead of failing closed.
- Files and behavior changed: `app/integrations/exchanges/ccxt_diagnostics.py` now rejects protected top-level and nested parameter aliases for symbol/type/side/amount/price/client ID/reduce-only, rejects malformed `params` before exchange construction and preserves only additive exchange options; explicit validated arguments populate canonical ccxt fields. Regression tests prove zero exchange-factory/order calls on collisions and preserve valid additive parameters.
- Tests and exact outcomes:
  - `.\.venv\Scripts\python.exe -m pytest Languages/Python/tests/test_exchange_support_capabilities.py -p no:cacheprovider --no-cov -q` — **31 passed, 150 subtests passed**.
  - `.\.venv\Scripts\python.exe -m ruff check Languages/Python/app/integrations/exchanges/ccxt_diagnostics.py Languages/Python/tests/test_exchange_support_capabilities.py` — **all checks passed**; `git diff --check` passed; parity generator reported `changed=False`.
- Commit: `01a24cf8c6a2f831f357d1ddc5f445c32bc17b04` (`Reject ccxt protected order parameter collisions`). No PR or push was created.
- Acceptance items still open: venue-specific live semantics and real exchange evidence remain external; no live order or production credential was used. Re-run the complete canonical gate before any score change.
- External blockers / decisions needed: initial product scope, repository governance, deployment/provenance inputs and operational evidence remain unchanged from the audit.
- Next ready task: **PRD-005** (live event-time and OHLCV quality gate), with **PRD-006** deployment smoke integration still ready.
- Score change: **not assessed**; the dated baseline remains 58/100 until a fresh evidence review.

### 2026-09-17 — PRD-005 implementation checkpoint

- Status: **DONE** (offline implementation; production promotion remains out of scope).
- Assignee and scope: Codex implementation checkpoint; Binance live OHLCV provenance/quality, WebSocket ordering, strategy signal timestamps, operational order preflight and regression coverage.
- Starting SHA and state: `44fa8c838762587b9fdaddf28cee464e5116302f`, clean before this change; no unrelated paths were modified.
- Failure reproduced: the F07 audit showed that successful but stale or malformed live candles could reach signal generation, while signals were stamped with local `time.time()` rather than source event time. Cached/replayed data could therefore appear fresh at the order boundary.
- Files and behavior changed: `binance/market/data_quality.py` now validates interval cadence, unique/monotonic indexes, gap policy, finite/positive OHLCV relationships, exchange event time, receipt time, clock skew, freshness and closed-bar status. `market_data.py` carries quality metadata through cache/fallback paths; `ws_runtime.py` rejects replayed/out-of-order/invalid candles without refreshing receipt time; strategy state and order candidates carry source quality and source event timestamps. Live cycles and exposure-increasing futures submissions fail closed with actionable reasons; `reduce_only` exits remain available. Historical range retrieval is unchanged.
- Tests and exact outcomes:
  - `.\.venv\Scripts\python.exe -m pytest Languages/Python/tests/test_live_market_data_quality.py Languages/Python/tests/test_binance_market_data_runtime.py Languages/Python/tests/test_binance_ws_runtime.py Languages/Python/tests/test_strategy_cycle_runtime.py Languages/Python/tests/test_strategy_runtime_safety.py Languages/Python/tests/test_strategy_runtime_behavior.py Languages/Python/tests/test_position_guard_behavior.py Languages/Python/tests/test_operational_order_snapshot.py -p no:cacheprovider --no-cov -q` — **132 passed, 165 subtests passed**.
  - `.\.venv\Scripts\python.exe -m ruff check Languages/Python/app/integrations/exchanges/binance/market/data_quality.py Languages/Python/app/integrations/exchanges/binance/market/market_data.py Languages/Python/app/integrations/exchanges/binance/transport/ws_runtime.py Languages/Python/app/integrations/exchanges/binance/wrapper.py Languages/Python/app/core/strategy/runtime/strategy_runtime.py Languages/Python/app/core/strategy/runtime/strategy_cycle_runtime.py Languages/Python/app/core/strategy/orders/operational_snapshot.py Languages/Python/app/core/strategy/orders/strategy_signal_order_submit_runtime.py Languages/Python/app/core/strategy/orders/strategy_signal_order_prepare_runtime.py Languages/Python/app/core/strategy/orders/strategy_signal_order_execute_runtime.py Languages/Python/tests/test_live_market_data_quality.py` — **all checks passed**; `git diff --check` passed; parity generator reported `changed=False`.
- Commit: `1d7779bcad5d055594d660dcb76e4fa6c95c7d59` (`Gate live orders on source market data quality`). No PR or push was created.
- Acceptance items still open: live exchange clock/stream behavior, reconnect recovery in the deployed topology, and genuine production telemetry remain external; no live order or production credential was used. Re-run the complete canonical gate and a fresh evidence review before any score change.
- External blockers / decisions needed: initial product scope, repository governance, deployment/provenance inputs and operational evidence remain unchanged from the audit.
- Next ready task: **PRD-006** (deployment smoke integration), with **PRD-007** following after its evidence path is verified.
- Score change: **not assessed**; the dated baseline remains 58/100 until a fresh evidence review.

### 2026-09-17 — PRD-006 implementation checkpoint

- Status: **DONE** (offline implementation; production promotion remains out of scope).
- Assignee and scope: Codex implementation checkpoint; deployment probe path confinement, expected deployment SHA/read-only verification, workflow integration and regression coverage.
- Starting SHA and state: `05b42bd2d03cc533ef14004478e0ab1f9445f44f`, clean before this change; no unrelated paths were modified.
- Failure reproduced: the F04/F05 audit found that the workflow wrote its probe output outside the probe's permitted evidence directory and ran a quick probe that could report success for a wrong build or writable server. The probe now accepts a full expected deployment SHA, verifies every observed `/readyz` identity, and can require server `read_only=true`; the workflow writes and uploads the canonical ignored artifact path.
- Files and behavior changed: `tools/run_service_sustained_probe.py` adds the expected-commit/read-only contract and explicit server-verification fields; `.github/workflows/deploy-production-readonly.yml` passes the deployment SHA/read-only requirement and uses `artifacts/operational-readiness/`; deployment/readiness tests cover positive and negative remote identity cases and workflow wiring; the deployment README documents the distinction between client probe safety and server mode.
- Tests and exact outcomes:
  - `.\.venv\Scripts\python.exe -m pytest --no-cov Languages/Python/tests/test_operational_readiness.py Languages/Python/tests/test_production_deployment_workflow.py Languages/Python/tests/test_production_deployment.py -q` — **43 passed, 1 warning, 112 subtests passed** (warning is the existing Starlette/AnyIO deprecation).
  - `.\.venv\Scripts\ruff.exe check --select E4,E7,E9,F tools/run_service_sustained_probe.py Languages/Python/tests/test_operational_readiness.py Languages/Python/tests/test_production_deployment_workflow.py` — **all checks passed**; `git diff --check` passed.
  - `.\.venv\Scripts\python.exe tools/check_production_deployment.py --json` — template manifest policy check **passed with no issues**.
  - `.\.venv\Scripts\python.exe tools/run_service_sustained_probe.py --profile quick --cycles 1 --minimum-requests 6 --json` — local diagnostic **passed** (6 GETs, four seeded local snapshots, no errors); `promotion_eligible=false` as required.
  - `.\.venv\Scripts\python.exe tools/run_service_sustained_probe.py --profile quick --cycles 1 --minimum-requests 6 --output artifacts/operational-readiness/prd006-path-verification.json --json` — workflow-equivalent writer created the canonical artifact path successfully; the temporary ignored artifact was removed after verification.
- Commit: `5b1908987ccefe0995887d6a76f1cd5948c00303` (`Harden production deployment probe verification`). No PR, push, cluster mutation or production credential was used.
- Acceptance items still open: the actual unseeded standalone observer still lacks three trading freshness observations and needs a versioned topology/capability contract or genuine approved ingestion; real HTTPS/TLS, mixed-replica rollout/rollback, registry attestation/scan provenance, cluster policy and capacity evidence remain external. The strict active-trading freshness gate was not weakened.
- External blockers / decisions needed: initial product scope, repository governance, trusted image provenance, authorized cluster/TLS/monitoring/token inputs, operator ownership and genuine observation/recovery windows remain unchanged. PRD-007 is the next code/design task; PRD-015/022 remain evidence-gated.
- Next ready task: **PRD-007** (exact-digest trusted build/scan provenance), followed by the operator-dependent ownership/risk/protection tasks.
- Score change: **not assessed**; the dated baseline remains **58/100, unattended production NO-GO** until a fresh evidence review.

### 2026-09-23 — offline production-readiness implementation checkpoint

- Starting source: `8700725f4e76a49bd195d6d2ba99e3ff3c792b67` on a clean `main`; work was isolated on `codex/production-readiness-20260923`. The prior 2026-09-17 audit SHA and score remain historical evidence, not this branch's score.
- **PRD-007 IN_PROGRESS:** added a protected-tag, published-release GHCR publisher that builds once, scans the pulled image ID, produces an SPDX SBOM and signs build, SBOM and passing-scan attestations for one immutable digest. The deployment workflow verifies signer, repository, ref, commit, digest, same run, hosted runner and freshness before loading Kubernetes credentials. Offline negative/positive provenance and no-mutation tests pass. No protected tag, real image, attestation, registry retention proof or cluster deployment was produced, so the task is not closed.
- **PRD-018 DONE offline:** inference and model discovery now bound request/context/response bytes, connect/read/total time and concurrent network workers. A blocked call returns at its wall deadline while retaining its worker slot until I/O exits. Cyclic/oversized JSON and slow/never-ending streams fail safely; provider option tokens remain editable and LLM output remains advisory.
- **PRD-019 IN_PROGRESS:** an unconditional `Secret Scan` pull-request job scans fetched Git history with redacted findings and a removed synthetic-token regression. The full local history scan passed. The Rust lockfile moved yanked `chacha20` 0.10.1 to 0.10.2; fresh RustSec review found zero vulnerabilities and six remaining reviewed unmaintained warnings, all expiring 2026-10-10. `SECURITY.md` records trust boundaries. Named exception owners, two clean candidate-build manifests, fresh Python/Node/container candidate findings and administrator verification of repository settings remain open.
- **PRD-020 IN_PROGRESS:** `next_bar_open` executes prior-close signals at the following open and marks a still-open terminal position without inventing a closing fill; an invalid terminal close fails closed. The historical `same_close_legacy` default is explicit and carried through Service API, checkpoints, C++ and Tauri requests using Python-owned generated parity. Indicator causality, gaps/intrabar ambiguity, market costs, dataset provenance, holdout/walk-forward and live replay remain open.
- **PRD-023 DONE offline:** corrected browser token lifetime, control-plane and coverage wording, and executable remediation paths. A fresh unseeded, read-only service regression observed only **1 valid trading freshness sample of 4**, confirming F14 remains open; no synthetic freshness was substituted.
- **PRD-001/008 evidence:** [the governance proposal](PRODUCTION_GOVERNANCE_PROPOSAL.md) records the unprotected `main` and `production` environment observations, the missing repository ruleset, and concrete settings drills; no remote setting changed. An offline PRD-008 reproduction found two independently provisioned ledger paths can each accept an intent with the same synthetic key. The path lock is transaction serialization, not an account execution lease. Authoritative account identity, owner fencing, key rotation and reconciliation remain unresolved.
- Verification on the changed tree: `.\.venv\Scripts\python.exe tools/verify_all.py --skip-promotion-evidence --json` passed the repository source gate (**41 checks evaluated; 1 advisory workspace-hygiene nonpass**, 1 external Rust evidence-import check explicitly skipped). The Python suite reported **1,901 passed, 2 Windows symlink skips, 54.01% coverage** against the 46% floor. Service, web, mobile, Rust, Tauri, native C++, deployment, parity, lint, type, coverage and source-compile checks passed. Report SHA-256: `071df5347cc5b5ef90053cc2e171c4b2c3c6724e424171f01f60ca26e31f399a` (local temporary JSON, not durable production evidence). Focused PRD-019 checks also passed: 67 Python cases/165 subtests, 313 Rust core tests, actionlint, full-history Gitleaks and synthetic history regression. The first full run had three contract failures; these were fixed and the stated result is the complete rerun.
- Commit: `7cf7f7d46db7aa0715722b866e90d455fe602514`. The pinned Gitleaks v8.30.1 full-history scan also passed after this commit. The strict operational gate then verified this commit was clean and its schema valid, but reported `promotion_ready=false` because all four required operational evidence artifacts were missing; see the [dated reassessment](PRODUCTION_READINESS_REVIEW_2026-09-23.md).
- No live orders, credentials, repository settings, image publication or cluster mutation occurred. Next: choose the initial operating scope and named owners, implement PRD-008/009/010 safety contracts, execute an authorized PRD-007 release attestation path, and resolve the F14 observer data contract and remaining PRD-020 research controls.
- Score change: the [2026-09-23 evidence review](PRODUCTION_READINESS_REVIEW_2026-09-23.md) assigns **65/100 for unattended real-money production, NO-GO**. The 2026-09-17 **58/100** audit remains the historical baseline; green source verification alone is not sign-off.

### Template for the next implementation checkpoint

```text
Date / task ID / status:
Assignee and scope:
Starting SHA and pre-existing changes:
Failure reproduced:
Files and behavior changed:
Tests / exact outcomes:
Commit or PR / artifact references:
Acceptance items still open:
External blockers / decisions needed:
Next ready task:
Score change: not assessed, or link a new dated evidence review.
```
