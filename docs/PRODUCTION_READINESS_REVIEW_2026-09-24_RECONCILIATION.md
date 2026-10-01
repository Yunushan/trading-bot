# Production readiness reassessment — 2026-09-24 Spot reconciliation checkpoint

## Verdict and tested revision

**72/100 for the selected first target (Python desktop + Binance Spot on one host): NO-GO for live trading.** This reassessment applies to code commit `c9571f994653d1c622b6f1d90b06652f017bbf9a` on `codex/prd009-futures-snapshot-guard`. It is not a profitability estimate, loss probability, or authorization to trade or deploy.

This checkpoint adds a bounded machine-verified query for unresolved local Live Spot order intents. The command reads the signed account UID, selects that UID's existing local ledger and requests the status of each unresolved client order ID through fixed read-only GET endpoints. It serializes against the same-user local execution-owner lock, keeps an intent unresolved on an API or validation error, and never rearms the owner. It does not reconcile all balances, positions, open orders, other keys, users or hosts.

## Verification evidence

- The clean-commit command `.\.venv\Scripts\python.exe tools/verify_all.py --skip-promotion-evidence --json` returned exit 0 and `ok=true`: **1,945 Python tests passed, 2 skipped, 54.41% total coverage**. Python mypy passed all 30 configured source files; Ruff, source compilation, critical coverage floors, service/web/mobile, Rust (**313 tests**), Tauri and native C++ (**4/4 tests**) passed.
- The external Rust evidence-import audit was explicitly skipped because it requires clean-commit external runtime and release evidence. Workspace hygiene remains an advisory due to ignored Rust build/cache paths; no cleanup was run.
- The strict command `tools/check_operational_readiness.py --require-evidence --require-current-commit --require-clean-source --json` returned exit 1 with `schema_ok=true`, `current_source_tree_clean=true` and `promotion_ready=false`. Four required artifacts are absent: `service-api-sustained-runtime`, `production-service-slo-window`, `service-config-backup-restore` and `incident-audit-continuity`. Policy SHA-256: `89fd34b17ac695febf98fd9e72ed21aa606cd5fbc7345244d85ea1e4ca47b02c`.
- The transport and CLI use mocked HTTP responses in tests. No exchange API call, production credential, live order, deployment, repository setting or remote branch was changed. The local commit was not pushed.

## Scorecard

| Dimension | Previous 71/100 review | This checkpoint | Evidence and remaining deduction |
| --- | ---: | ---: | --- |
| Trading correctness and risk protection | 15/20 | **15/20** | Operator-approved budgets, durable account-wide risk and restart-safe kill state are still missing. |
| Security and credential boundaries | 11/15 | **11/15** | Account-wide fencing, key inventory/revocation and independent review remain open. |
| State, recovery and execution ownership | 11/15 | **12/15** | Exact unresolved Spot order-status queries now bind to signed UID and client order ID, refuse an active local owner, and preserve unresolved state on errors. Full account reconciliation, anti-rollback and cross-user/host/executor fencing remain open. |
| Automated verification and CI | 14/15 | **14/15** | The clean full source gate passes; candidate CI and external promotion evidence remain outstanding. |
| Deployment and release integrity | 6/10 | **6/10** | No attested release artifact, protected candidate workflow or deployed rollback proof is supplied. |
| Operations and production evidence | 4/10 | **4/10** | The four required sustained runtime, SLO, restore and incident/audit artifacts remain absent. |
| Architecture and maintainability | 6/10 | **6/10** | Python remains canonical; full account recovery, ledger scale and broader executor fencing remain open. |
| Product scope, operator QA and support | 4/5 | **4/5** | The target is selected, but its named account, machine, operator, risk policy and signed acceptance remain absent. |
| **Total** | **71/100** | **72/100** | **NO-GO for live trading.** |

The one-point increase credits the tested, fail-closed exact-order reconciliation slice. It does not credit live account recovery, the ignored-build advisory, the skipped Rust evidence importer, or any production evidence. The preceding [71/100 source-gate review](PRODUCTION_READINESS_REVIEW_2026-09-24_SOURCE_GATE.md) and earlier reviews remain historical for their tested revisions.

## Remaining launch blockers

- PRD-008 still needs full account reconciliation, restored-state anti-rollback, verified key/UID pairing during rotation, and controls for external users, hosts, bots and API keys.
- PRD-009 still needs operator-selected risk limits and reset authority, durable account-wide accounting, restart-safe kill state and audited external-position reconciliation.
- PRD-010/011 still need independent protection and end-to-end fault/recovery proof.
- The four operational artifacts, candidate CI, repository governance, named incident owners and signed risk acceptance remain open. Green source CI and quick local drills do not supply the missing production windows.

See the [implementation plan](PRODUCTION_IMPLEMENTATION_PLAN.md) for task status and the [handoff](PRODUCTION_HANDOFF.md) for the next action. The 2026-09-17 audit remains unchanged as the historical baseline.
