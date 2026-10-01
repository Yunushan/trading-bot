# Production readiness reassessment — 2026-09-24 recovery evidence

## Verdict and tested revisions

**76/100 for the selected first target (Python desktop + Binance Spot on one host): NO-GO for live trading.** The source code remains at `2070f9de` on `codex/prd009-futures-snapshot-guard`. Fresh local operational evidence was generated and validated against clean documentation commit `b9d63363de765dc5e1cedeca7eb263e08aadb600`; subsequent documentation-only changes require the artifacts to be regenerated against the new clean commit. The score is an engineering assurance assessment, not a profitability estimate, loss probability, or authorization to trade or deploy.

This reassessment keeps the 74/100 Spot entry guard and adds two policy-accepted local recovery artifacts. The backup/restore drill forced a service child-process exit, corrupted and restored synthetic config, then verified read-only recovery and authorization. The incident/audit drill exercised rotation, restart readback, corruption tolerance, secret redaction and order-audit continuity without submitting orders.

These local drills do not demonstrate a deployed production service or production SLO telemetry. The stop-loss guard still does not implement exchange-resident protection. Live Spot remains NO-GO.

## Verification evidence

- `tools/run_operational_recovery_drill.py --output artifacts/operational-readiness/service-config-backup-restore.json --json` passed on the clean evidence commit above. It reported `promotion_eligible=true`, `source_tree_clean=true`, `read_only=true`, `order_submission_attempted=false`, RTO **3.226382 seconds**, and RPO **2.745413 seconds**. The child service verified config equality, authentication and read-only lifecycle scope before and after a forced process exit.
- `tools/run_incident_audit_continuity_drill.py --output artifacts/operational-readiness/incident-audit-continuity.json --json` passed on the same commit. It reported `promotion_eligible=true`, `source_tree_clean=true`, `read_only=true`, `order_submission_attempted=false`, RTO **0.003593 seconds**, and RPO **0.013260 seconds**. Secret-redaction and order-audit continuity checks passed.
- The strict gate `tools/check_operational_readiness.py --require-evidence --require-current-commit --require-clean-source --json` accepted both artifacts with `schema_ok=true` and `current_source_tree_clean=true`. It remained `promotion_ready=false` because `service-api-sustained-runtime` and `production-service-slo-window` were missing. Policy SHA-256: `89fd34b17ac695febf98fd9e72ed21aa606cd5fbc7345244d85ea1e4ca47b02c`.
- The full source gate remains the result recorded in the [74/100 Spot guard review](PRODUCTION_READINESS_REVIEW_2026-09-24_SPOT_STOPLOSS_GUARD.md): **1,953 Python tests passed, 2 skipped, 54.48% coverage**; configured lint/type, service/web/mobile, Rust, Tauri and native C++ checks passed. The external Rust evidence import was skipped, and ignored build/cache paths remained a workspace advisory.
- The evidence JSON files live in the ignored `artifacts/operational-readiness/` directory. Regenerate them after any candidate commit change before rerunning the strict gate. They used synthetic test data; no live exchange request, production credential, order, deployment or repository setting was used or changed.

## Scorecard

| Dimension | Previous checkpoint | This checkpoint | Evidence and remaining deduction |
| --- | ---: | ---: | --- |
| Trading correctness and risk protection | 16/20 | **16/20** | Unsupported configured Spot stop-loss blocks Live Spot buys before side effects. Exchange-resident fill-linked protection, approved durable risk budgets and kill state remain missing. |
| Security and credential boundaries | 11/15 | **11/15** | Account-wide fencing, key inventory/revocation, other-user/host controls and independent security review remain open. |
| State, recovery and execution ownership | 13/15 | **13/15** | Local restore and incident/audit continuity are tested. Portfolio/fill reconciliation, anti-rollback, atomic snapshots and cross-key/host fencing remain open. |
| Automated verification and CI | 14/15 | **14/15** | The full source gate passes; candidate CI and external promotion evidence remain outstanding. |
| Deployment and release integrity | 6/10 | **6/10** | No attested release artifact, protected candidate workflow or deployed rollback proof is supplied. |
| Operations and production evidence | 4/10 | **6/10** | Policy-accepted local restore and incident/audit artifacts now exist. The sustained deployed-service probe and rolling 30-day production SLO evidence remain missing. |
| Architecture and maintainability | 6/10 | **6/10** | Python remains canonical; Spot protection lifecycle, full account recovery and broader executor fencing remain open. |
| Product scope, operator QA and support | 4/5 | **4/5** | The target is selected, but the account, machine, operator, approved risk policy and signed acceptance remain unnamed. |
| **Total** | **74/100** | **76/100** | **NO-GO for live trading.** |

The two-point increase credits the two fresh policy artifacts, not production uptime or 30-day telemetry. The preceding [74/100 review](PRODUCTION_READINESS_REVIEW_2026-09-24_SPOT_STOPLOSS_GUARD.md) and earlier reassessments remain historical for their respective checkpoints.

## Remaining blockers

- The strict gate still needs a deployed HTTPS endpoint for at least 30 minutes and 18,000 read-only requests with deployed-commit identity, read-only mode, and fresh operational snapshots.
- It also needs a credential-free source export of genuine rolling 30-day production telemetry for the current deployed commit; synthetic data and local quick probes do not qualify.
- PRD-010/011 need exchange-resident, fill-linked Spot protection and fault/recovery proof for partial fills, ambiguous acknowledgements, restart, reconnect and manual exchange changes.
- PRD-008 needs portfolio/fill reconciliation, restored-state anti-rollback, verified key/UID pairing during rotation, and controls for external users, hosts, bots and API keys. PRD-009 needs operator-selected risk limits and reset authority, durable account-wide accounting and restart-safe kill state.
