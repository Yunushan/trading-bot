# Production readiness reassessment — unresolved Spot market orders

## Verdict and tested revision

**77/100 for the selected first target (Python desktop + Binance Spot on one host): NO-GO for live trading.** The reviewed source revision is `c4a75e5d` on `codex/prd009-futures-snapshot-guard`. Spot market orders whose acknowledgements remain in flight stay unresolved. An exact query also leaves a canceled/expired market order unresolved when any quantity was executed, since the partial Spot position is not yet reconciled into portfolio state. A terminal result with confirmed zero execution may resolve. Fill-linked Spot protection, full portfolio recovery and production acceptance remain open. This score is an engineering assurance assessment, not a profitability estimate, loss probability, or authorization to trade or deploy.

## Change and verification evidence

- Spot `MARKET` intents require execution confirmation. Primary `NEW` and `PARTIALLY_FILLED` acknowledgements remain unresolved and block another intent. Exact reconciliation of a canceled/expired market order with positive executed quantity keeps it unresolved; terminal zero-execution results can resolve. Legacy accepted-but-partial market entries also remain unresolved. Reconciliation validates identity and execution fields. Spot `LIMIT` pending behavior retains its prior semantics.
- Focused offline Spot order, reconciliation and fake-exchange coverage: **35 tests, 148 subtests passed**. A regression first reproduced that an exact terminal partial fill had previously cleared the unresolved state.
- Full Python suite on the exact code commit: **1,958 passed, 2 skipped**, 54.48% coverage. Ruff passed across the Python tree; mypy passed for 30 source files; all critical package coverage floors passed. The two skips are Windows symlink privilege/environment constraints.
- A full cross-language gate on the prior `53385f70` code state passed Python (1,954 tests), Ruff, mypy, service/web/mobile, Rust (313), Tauri and native C++ (4/4). The changes from that gate to `c4a75e5d` are confined to Python execution and tests. The external Rust evidence importer was skipped in the earlier gate; this reassessment does not claim it ran on `c4a75e5d`.
- The strict operational gate on clean documentation commit `a722b032` accepted the regenerated local restore and incident/audit artifacts (`schema_ok=true`, `current_source_tree_clean=true`); it remained `promotion_ready=false` because the sustained deployed HTTPS runtime and genuine rolling 30-day production SLO artifacts are absent. Those local artifacts become stale after this review is updated and must be regenerated after the final documentation commit, followed by the strict `--require-evidence --require-current-commit --require-clean-source` gate. Policy SHA-256: `89fd34b17ac695febf98fd9e72ed21aa606cd5fbc7345244d85ea1e4ca47b02c`.
- No live Binance request, production credential, order, deployment, repository setting or remote branch changed.

## Scorecard

| Dimension | Previous checkpoint | This checkpoint | Evidence and remaining deduction |
| --- | ---: | ---: | --- |
| Trading correctness and risk protection | 16/20 | **16/20** | Uncertain Spot market exposure blocks retries, but exchange-resident fill-linked protection, crash recovery, approved durable risk budgets and kill state remain missing. |
| Security and credential boundaries | 11/15 | **11/15** | Account-wide fencing, key inventory/revocation, other-user/host controls and independent security review remain open. |
| State, recovery and execution ownership | 13/15 | **14/15** | In-flight and terminal partial Spot market intents remain blocked; confirmed zero-fill terminal results resolve. Full portfolio/fill reconciliation, anti-rollback, atomic snapshots and cross-key/host fencing remain open. |
| Automated verification and CI | 14/15 | **14/15** | Full Python verification passes; candidate CI and current external promotion evidence remain outstanding. |
| Deployment and release integrity | 6/10 | **6/10** | No attested release artifact, protected candidate workflow or deployed rollback proof is supplied. |
| Operations and production evidence | 6/10 | **6/10** | The two local continuity artifacts need current-source regeneration. Sustained deployed-service runtime and rolling 30-day production SLO evidence remain missing. |
| Architecture and maintainability | 6/10 | **6/10** | Python remains canonical; Spot protection lifecycle, full account recovery and broader executor fencing remain open. |
| Product scope, operator QA and support | 4/5 | **4/5** | The target is selected, but account, machine, operator, approved risk policy and signed acceptance remain unnamed. |
| **Total** | **76/100** | **77/100** | **NO-GO for live trading.** |

## Remaining blockers

- PRD-010/011 need exchange-resident, fill-linked Spot protection and fault/recovery proof for partial fills, ambiguous acknowledgements, restart, reconnect and manual exchange changes. Positive terminal partial fills remain safely blocked, but the runtime still needs an operator-usable path to reconcile those exchange fills into strategy-owned portfolio state before rearming.
- PRD-008 needs full portfolio/fill reconciliation, restored-state anti-rollback, verified key/UID pairing during rotation, and controls for external users, hosts, bots and API keys. PRD-009 needs operator-selected risk limits and reset authority, durable account-wide accounting and restart-safe kill state.
- The strict gate still requires a deployed HTTPS runtime probe and genuine rolling 30-day production telemetry. Candidate CI, release governance, named incident owners and signed risk acceptance remain open.

The preceding [2026-09-24 Spot acknowledgement reassessment](PRODUCTION_READINESS_REVIEW_2026-09-24_SPOT_ACK_VALIDATION.md) remains historical evidence for its tested revision.
