# Production readiness reassessment — 2026-09-24 PRD-008 checkpoint

## Verdict and evidence

**70/100 for the selected first target (Python desktop + Binance Spot on one host): NO-GO for live trading.** This reassessment uses the [2026-09-17 audit rubric](PRODUCTION_READINESS_AUDIT.md) and applies only to code commit `a2918725da4d8b459616b8e1d25eff5456c2b583` on `codex/prd009-futures-snapshot-guard`. It is not a profitability estimate, loss probability or authorization to deploy. A narrower scope does not remove hard launch blockers.

- The user selected the initial target as Python desktop with Binance Spot on one host. The specific account, machine, operator, approved risk limits and signed acceptance are still not recorded.
- The PRD-008 increment adds offline Live Spot history migration and credential rotation. Migration accepts resolved v1/v2 history, locks the source and destination in stable order, preserves the old ledger as a backup, moves the old path out of service and leaves the new owner marker in `recovery_required`. An interrupted migration can resume with the same UID/environment/reference. Rotation preserves ledger/store identity, refuses unresolved intents and active owners, disarms before changing the binding, records only old/new SHA-256 fingerprints plus a reference, and requires explicit rearm. A failed rotation write leaves the owner disarmed with the old binding recoverable.
- From `Languages/Python`, the focused command `..\..\.venv\Scripts\python.exe -m pytest tests/test_spot_execution_owner.py tests/test_order_intent_provisioning.py -q --no-cov -k "not separate_process and not only_one_process_can_initialize and not admin_is_packaged_and_module_and_source_entrypoints_share_behavior"` reported **38 passed, 1 skipped, 3 deselected, 46 subtests passed**. The skip is the existing symlink test because this Windows host lacks the privilege (`WinError 1314`). The three process-dependent tests were deselected; the prior full gate recorded child-interpreter startup failures with `_overlapped` `WinError 10106` on this host.
- Ruff passed on the changed implementation and test files. The configured mypy check passed with no issues in **30 source files**. `git diff --check` passed.
- The complete repository gate was not rerun for this increment. The previous run on `317ac2ca98580f13def7111901c9fe980906c61c` reported **1,925 passed, 2 skipped, 3 failed** in process-spawn cases; see the preceding [2026-09-24 review](PRODUCTION_READINESS_REVIEW_2026-09-24.md). That result is not presented as a green gate for this revision.
- Strict promotion check on clean revision `d361c74ebbc4bb68add823c77107864915e5ea8d` returned exit 1 with `schema_ok=true`, `current_source_tree_clean=true` and `promotion_ready=false`. All four required artifacts are absent: `service-api-sustained-runtime`, `production-service-slo-window`, `service-config-backup-restore` and `incident-audit-continuity`. Policy SHA-256: `89fd34b17ac695febf98fd9e72ed21aa606cd5fbc7345244d85ea1e4ca47b02c`.
- The rotation command is deliberately offline. It records human attestation and does not verify that the supplied UID and new API key refer to the same Binance account. The live runtime separately verifies the signed UID and credential binding before owner acquisition. No real credential, exchange request, order, deployment or repository setting was used or changed.

## Scorecard

| Dimension | Previous 2026-09-24 review | This checkpoint | Evidence and remaining deduction |
| --- | ---: | ---: | --- |
| Trading correctness and risk protection | 15/20 | **15/20** | The malformed Futures snapshot guard remains. Operator-approved budgets, durable account-wide risk and restart-safe kill state are still missing. |
| Security and credential boundaries | 11/15 | **11/15** | Rotation stores only fingerprints and preserves the ledger. Account-wide fencing, key inventory/revocation and independent review remain open. |
| State, recovery and execution ownership | 9/15 | **11/15** | Local history migration, rotation and failure recovery are tested. Exchange-side fencing, machine-verified reconciliation and anti-rollback proof remain open. |
| Automated verification and CI | 13/15 | **13/15** | Focused tests, Ruff and mypy passed; the full current-revision gate and candidate CI remain outstanding. |
| Deployment and release integrity | 6/10 | **6/10** | No attested release artifact, protected candidate workflow or deployed rollback proof is supplied. |
| Operations and production evidence | 4/10 | **4/10** | Sustained SLO, alert delivery, restore and account-reconciliation evidence remain outstanding. |
| Architecture and maintainability | 6/10 | **6/10** | Python remains canonical. Ledger migration/scale and broader executor fencing are open. |
| Product scope, operator QA and support | 3/5 | **4/5** | Platform, exchange and one-host target are now selected. The named account, machine, operator, risk policy and signed acceptance remain absent. |
| **Total** | **67/100** | **70/100** | **NO-GO for live trading.** |

The three points since the 67/100 review credit a tested history-preserving rotation/recovery path, a tested legacy-history migration path and an explicit first-target boundary. The additional point since the intermediate 69/100 checkpoint credits migration. None is production sign-off. Earlier 69, 67, 66, 65 and historical 58 reviews remain evidence for their own revisions.

## Hard blockers

- PRD-008 remains in progress. The OS lock only coordinates processes under one OS profile on one host; it does not fence another host, OS user, native runtime, external bot or still-valid Binance key. Migration and rotation do not machine-verify exchange reconciliation or the new key's account identity; restored-state anti-rollback proof is still absent.
- PRD-009 still needs operator-selected limits and reset authority, durable shared accounting, restart-safe kill state, external-position reconciliation and audited reset.
- PRD-010/011 still need independent position-protection and end-to-end fault/recovery proof.
- The strict check on clean revision `d361c74ebbc4bb68add823c77107864915e5ea8d` confirms four missing operational evidence artifacts: `service-api-sustained-runtime`, `production-service-slo-window`, `service-config-backup-restore`, and `incident-audit-continuity`.
- Repository governance, independent reviewers, named incident owners and signed risk acceptance remain open. The earlier public GitHub governance observation was not rechecked in this checkpoint.

See the [implementation plan](PRODUCTION_IMPLEMENTATION_PLAN.md) for the task record and the [handoff](PRODUCTION_HANDOFF.md) for the next action. The [previous same-day review](PRODUCTION_READINESS_REVIEW_2026-09-24.md) remains a historical checkpoint for its earlier source revision.
