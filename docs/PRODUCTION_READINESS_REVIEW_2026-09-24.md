# Production readiness review — 2026-09-24

## Verdict and evidence

**67/100 for unattended real-money production: NO-GO.** This conservative reassessment uses the [2026-09-17 audit rubric](PRODUCTION_READINESS_AUDIT.md) and applies only to clean code commit `317ac2ca98580f13def7111901c9fe980906c61c` on `codex/prd009-futures-snapshot-guard`. It is not a profitability estimate, a probability of avoiding loss, or authorization to trade or deploy. Hard launch blockers override the total.

- Focused Futures stop and close-reconciliation checks passed **61 tests and 2 subtests**. Ruff passed on all changed files; the full Python type check reported no issues in 30 source files.
- `tools/verify_all.py --skip-promotion-evidence --json` ran under the declared Python 3.14 environment. It refreshed total line coverage to **54.27%** and passed every critical package coverage threshold. Service/API and deployment contracts, web/mobile, lint/type, source compilation, Rust (**313 tests**), Tauri and native C++ (**4/4 tests**) passed. The full Python suite reported **1,925 passed, 2 skipped and 3 failed**. Two admin-entrypoint subtests and one multiprocessing initialization test failed when spawned interpreters could not load Windows `_overlapped` (`WinError 10106`); the multiprocessing test then timed out. These failures reproduced in isolation. The source gate therefore returned `ok=false`; it is not recorded as green. One advisory workspace-hygiene check found ignored build/cache files, which were left untouched. The external Rust evidence import was skipped.
- Strict promotion check `tools/check_operational_readiness.py --require-evidence --require-current-commit --require-clean-source --json` on this clean commit returned exit 1: `schema_ok=true`, `current_source_tree_clean=true`, `promotion_ready=false`. It found four missing required operational artifacts: `service-api-sustained-runtime`, `production-service-slo-window`, `service-config-backup-restore`, and `incident-audit-continuity`. Policy SHA-256: `89fd34b17ac695febf98fd9e72ed21aa606cd5fbc7345244d85ea1e4ca47b02c`.
- The last repository governance observation was the 2026-09-23 public GitHub read: `main` unprotected, no repository rulesets, no production protection rules and administrator bypass enabled. It was not rechecked in this assessment. No repository settings, credentials, deployments, production evidence or live orders changed.

## Scorecard

| Dimension | 2026-09-23 follow-up | 2026-09-24 review | Evidence and remaining deduction |
| --- | ---: | ---: | --- |
| Trading correctness and risk protection | 14/20 | **15/20** | Cumulative Futures stops now reject malformed snapshots, invalid hedge-side data, non-finite totals and unusable percentage-stop margin before closing. Durable aggregate risk, restart-safe protection and realistic live fills remain open. |
| Security and credential boundaries | 11/15 | **11/15** | Existing LLM and secret-scan boundaries remain; deployment-host security and independent review are open. |
| State, recovery and execution ownership | 9/15 | **9/15** | Same-user/single-host Live Spot ownership remains bounded; account-wide/exchange-side fencing, credential rotation, durable aggregate risk and recovery proof remain open. |
| Automated verification and CI | 13/15 | **13/15** | Focused safety tests, typing and critical coverage passed. The complete local Python gate did not pass because the host could not start Windows child interpreters; candidate CI was not run. Main governance remains open. |
| Deployment and release integrity | 6/10 | **6/10** | No attested release artifact or deployed rollback proof is supplied. |
| Operations and production evidence | 4/10 | **4/10** | No genuine sustained SLO, paging, restore or account-reconciliation window. |
| Architecture and maintainability | 6/10 | **6/10** | Python remains canonical; service/runtime limits and long-history ledger capacity remain open. |
| Product scope, operator QA and support | 3/5 | **3/5** | Named first-release account, host, operator, risk policy and signed candidate acceptance remain absent. |
| **Total** | **66/100** | **67/100** | **NO-GO for unattended real-money production.** |

The one-point increase credits a tested fail-closed correction to a Futures cumulative-stop defect: malformed position rows can no longer be silently skipped to understate loss. Invalid snapshots pause new entries while leaving the existing reducing-close path available. This is a bounded stop-input guard; it does not implement the PRD-009 acceptance criteria for operator-approved limits, atomic account-wide accounting, restart-persistent kill state, external-position reconciliation or audited reset. No score credit is claimed for the incomplete full Python gate or for the strict promotion check.

## Remaining blockers

- PRD-009 still needs operator-selected exposure/loss/order budgets and reset authority, followed by durable shared accounting and restart/concurrency/reconciliation proof.
- PRD-008 account identity, credential rotation, legacy migration, anti-rollback and broader execution ownership remain open.
- PRD-010/011 still need independently verified position protection and end-to-end fault/recovery proof.
- The four current-SHA operational artifacts are absent. Sustained production observations, deployment/rollback evidence, release signing and human risk sign-off cannot be fabricated by offline code changes.
- Repository governance, named reviewer/incident ownership and the chosen release scope remain unresolved; recheck remote settings before any future release decision.

See the [implementation plan](PRODUCTION_IMPLEMENTATION_PLAN.md) for task status and the [handoff](PRODUCTION_HANDOFF.md) for the next action. Earlier dated reviews remain unchanged historical evidence.
