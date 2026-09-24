# Production readiness reassessment — 2026-09-24 account audit

## Verdict and tested revision

**73/100 for the selected first target (Python desktop + Binance Spot on one host): NO-GO for live trading.** This reassessment applies to source commit `e603b66286e4d8d36f834cbc18939484584a59f2` on `codex/prd009-futures-snapshot-guard`. It is an engineering assurance score, not a profitability estimate, loss probability, or authorization to trade or deploy.

This increment adds a read-only `reconcile-spot-account` audit alongside the existing exact unresolved-order query. It verifies the signed account UID again, validates the account balance response without printing asset names or amounts, queries all account-wide open orders, and compares their symbol/client-order-ID identities with the UID-scoped local ledger. Unknown open orders, missing locally expected open orders, status conflicts, malformed account data, and unresolved intents fail the command. It never rearms the owner.

The exchange calls are sequential, not atomic. Balance values are checked for schema and valid nonnegative finite amounts, but are not compared with a strategy-owned portfolio or fills. The audit covers one API key and cannot detect activity hidden behind other valid keys, OS users, hosts, bots or Binance products. It does not provide exchange-side fencing or restored-state anti-rollback.

## Verification evidence

- The complete command `.\\.venv\\Scripts\\python.exe tools/verify_all.py --skip-promotion-evidence --json` returned exit 0 and `ok=true` on the implementation worktree containing the exact source files committed at `e603b662`. It reported **1,950 Python tests passed, 2 skipped, 54.47% total coverage**. Ruff, mypy across 30 configured files, source compilation, critical coverage floors, service API contracts/tests, web/mobile checks, Rust (313 tests), Tauri and native C++ (4/4) passed.
- The external Rust evidence-import audit was explicitly skipped because it requires clean-commit external runtime and release evidence. Workspace hygiene remains an advisory due to ignored Rust build/cache paths; no cleanup was run.
- The 13 focused Spot transport/CLI tests and 11 subtests passed. All Binance HTTP responses were mocked. No real account request, credential, order, deployment, repository setting or remote branch was used or changed.
- The strict operational evidence check must be rerun on this checkpoint after the plan and handoff are committed; the last clean-source check on the prior revision found four missing required artifacts.

## Scorecard

| Dimension | Previous 72/100 review | This checkpoint | Evidence and remaining deduction |
| --- | ---: | ---: | --- |
| Trading correctness and risk protection | 15/20 | **15/20** | Operator-approved risk budgets, durable account-wide risk, restart-safe kill state and independent position protection remain missing. |
| Security and credential boundaries | 11/15 | **11/15** | Account-wide fencing, key inventory/revocation, other-user/host controls and independent security review remain open. |
| State, recovery and execution ownership | 12/15 | **13/15** | Tested single-key open-order comparison and non-disclosing balance validation add recovery coverage. Portfolio/fill reconciliation, an atomic view, anti-rollback, cross-key/host fencing and real account recovery proof remain open. |
| Automated verification and CI | 14/15 | **14/15** | The complete source gate passes. Candidate CI and external promotion evidence remain outstanding. |
| Deployment and release integrity | 6/10 | **6/10** | No attested release artifact, protected candidate workflow or deployed rollback proof is supplied. |
| Operations and production evidence | 4/10 | **4/10** | Sustained runtime, SLO, restore and incident/audit artifacts are still missing. |
| Architecture and maintainability | 6/10 | **6/10** | Python remains canonical; full account recovery, ledger scale and broader executor fencing remain open. |
| Product scope, operator QA and support | 4/5 | **4/5** | The target is selected, but the account, machine, operator, approved risk policy and signed acceptance remain unnamed. |
| **Total** | **72/100** | **73/100** | **NO-GO for live trading.** |

The one-point increase credits the tested all-symbol open-order comparison and balance-payload validation. It does not credit a live account audit, a portfolio balance reconciliation, fills, other keys or users, or production evidence. The preceding [72/100 reconciliation review](PRODUCTION_READINESS_REVIEW_2026-09-24_RECONCILIATION.md) and earlier reviews remain historical for their tested source revisions.

## Remaining launch blockers

- PRD-008 needs portfolio/fill reconciliation, restored-state anti-rollback, verified key/UID pairing during rotation, and controls for external users, hosts, bots and API keys.
- PRD-009 needs operator-selected risk limits and reset authority, durable account-wide accounting, restart-safe kill state and audited external-position reconciliation.
- PRD-010/011 need independent protection and end-to-end fault/recovery proof.
- Current strict-gate evidence, candidate CI, repository governance, named incident owners and signed risk acceptance remain open. Green source CI and a read-only code path do not supply production sign-off.

See the [implementation plan](PRODUCTION_IMPLEMENTATION_PLAN.md) for task status and the [handoff](PRODUCTION_HANDOFF.md) for the next action. The 2026-09-17 audit remains unchanged as the historical baseline.
