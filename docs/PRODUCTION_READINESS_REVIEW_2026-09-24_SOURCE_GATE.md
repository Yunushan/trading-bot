# Production readiness reassessment — 2026-09-24 source-gate checkpoint

## Verdict and evidence

**71/100 for the selected first target (Python desktop + Binance Spot on one host): NO-GO for live trading.** This reassessment uses the [2026-09-17 audit rubric](PRODUCTION_READINESS_AUDIT.md) and applies to code commit `1578938331fdd04a6cbdd7eb66ac194916cf2cf1` on `codex/prd009-futures-snapshot-guard`. It is not a profitability estimate, loss probability or authorization to deploy.

- The user selected Python desktop with Binance Spot on one host. The account, machine, operator, approved risk limits and signed acceptance are still unnamed.
- This code increment makes public Binance connector and order-binder exports lazy. Offline order-store administration can import the provisioning/runtime modules without loading `binance.client` and its asynchronous networking runtime. Existing public exports remain available on access.
- The provisioning regression's spawned worker no longer imports `unittest.mock` or the service API status schema, neither of which it uses. The original two-process initialization race and assertions remain intact.
- Affected suites from `Languages/Python`: `test_binance_package_split_smoke.py` and `test_order_intent_provisioning.py` — **88 passed, 1 Windows symlink-privilege skip, 127 subtests**. Ruff passed on the changed files; the repository mypy check passed with no issues in **30 source files**.
- The canonical `.\.venv\Scripts\python.exe tools/verify_all.py --skip-promotion-evidence --json` returned exit 0 with `ok=true`: **1,937 Python tests passed, 2 Windows symlink skips, 54.35% total coverage**. Critical Python package coverage floors, service/web/mobile, Ruff, mypy, Python source compilation, Rust (**313 tests**), Tauri and native C++ (**4/4 tests**) passed. The external Rust evidence-import audit was explicitly skipped. The optional workspace-hygiene check reported ignored build/cache paths; no cleanup was run.
- Strict evidence check on clean code commit `1578938331fdd04a6cbdd7eb66ac194916cf2cf1` returned exit 1 with `schema_ok=true`, `current_source_tree_clean=true` and `promotion_ready=false`. Four artifacts are missing: `service-api-sustained-runtime`, `production-service-slo-window`, `service-config-backup-restore` and `incident-audit-continuity`. Policy SHA-256: `89fd34b17ac695febf98fd9e72ed21aa606cd5fbc7345244d85ea1e4ca47b02c`.
- No live exchange request, order, production credential, deployment, repository setting or remote branch changed.

## Scorecard

| Dimension | Previous 70/100 review | This checkpoint | Evidence and remaining deduction |
| --- | ---: | ---: | --- |
| Trading correctness and risk protection | 15/20 | **15/20** | Operator-approved budgets, durable account-wide risk and restart-safe kill state are still missing. |
| Security and credential boundaries | 11/15 | **11/15** | Account-wide fencing, key inventory/revocation and independent review remain open. |
| State, recovery and execution ownership | 11/15 | **11/15** | Exchange-side fencing, machine-verified reconciliation and anti-rollback proof remain open. |
| Automated verification and CI | 13/15 | **14/15** | The full current source gate now passes; candidate CI and external promotion evidence remain outstanding. |
| Deployment and release integrity | 6/10 | **6/10** | No attested release artifact, protected candidate workflow or deployed rollback proof is supplied. |
| Operations and production evidence | 4/10 | **4/10** | Sustained SLO, alert delivery, restore and account-reconciliation evidence remain outstanding. |
| Architecture and maintainability | 6/10 | **6/10** | Python remains canonical. Ledger migration/scale and broader executor fencing are open. |
| Product scope, operator QA and support | 4/5 | **4/5** | The target is selected, but its named account, machine, operator, risk policy and signed acceptance remain absent. |
| **Total** | **70/100** | **71/100** | **NO-GO for live trading.** |

The one-point increase credits the green full current-revision source gate. It does not credit the ignored-build advisory, the explicitly skipped evidence importer, or any production evidence. The earlier [70/100 PRD-008 review](PRODUCTION_READINESS_REVIEW_2026-09-24_PRD008.md) and earlier 69/67/66/65/58 checkpoints remain historical evidence for their own revisions.

## Hard blockers

- PRD-008 remains in progress. The local owner only coordinates processes under one OS profile on one host. Exchange-side fencing, other OS users/hosts/executors, machine-verified account and order reconciliation, and restored-state anti-rollback remain open.
- PRD-009 still needs operator-selected limits and reset authority, durable shared accounting, restart-safe kill state, external-position reconciliation and audited reset.
- PRD-010/011 still need independent position-protection and end-to-end fault/recovery proof.
- The four required operational evidence artifacts remain absent. Green source verification cannot replace the sustained runtime/SLO, backup/restore or incident/audit continuity evidence.
- Candidate CI, repository governance, independent review, named incident owners and signed risk acceptance remain open.

See the [implementation plan](PRODUCTION_IMPLEMENTATION_PLAN.md) for the work log and the [handoff](PRODUCTION_HANDOFF.md) for the next action. The earlier reviews remain unchanged.
