# Production readiness reassessment — Spot acknowledgement validation

## Verdict and tested revision

**76/100 for the selected first target (Python desktop + Binance Spot on one host): NO-GO for live trading.** The reviewed source revision is `53385f70` on `codex/prd009-futures-snapshot-guard`. The narrow acknowledgement-status validation is an additional fail-closed check, but does not supply independent production acceptance evidence; the previous 76-point score is retained. This score is an engineering assurance assessment, not a profitability estimate, loss probability, or authorization to trade or deploy.

The Spot order response boundary now accepts only known active statuses (`NEW`, `PARTIALLY_FILLED`, `FILLED`, `PENDING_NEW`, `PENDING_CANCEL`). Unknown statuses are rejected. Where a durable intent exists, the order stays unresolved and blocks a retry. This closes an inconsistent response path; Live execution already requires durable intent handling, and the broader Spot protection/recovery requirements remain open.

## Verification evidence

- Focused command covering Spot response validation, durable intent reconciliation and the fake exchange path: **23 passed, 100 subtests passed**.
- Full command `.venv\Scripts\python.exe tools/verify_all.py --skip-promotion-evidence --json` returned `ok=true` on the exact source changes later committed as `53385f70`: **1,954 Python tests passed, 2 skipped, 54.48% coverage**. Ruff, mypy (30 files), service API/contracts, web/mobile, Rust (313), Tauri and native C++ (4/4) passed. The native close suite passed in 119.24 seconds.
- The Rust external evidence import was skipped because it requires clean-commit external release/runtime evidence. The live-smoke preflight attempted no network request and submitted no orders. Workspace hygiene remained advisory for ignored build/cache paths.
- The strict operational evidence gate last accepted the two local restore/continuity artifacts on earlier clean commit `1122de9c`. The source commit `53385f70` invalidated those commit-bound files; regenerate them after the final documentation commit before running the strict gate. That gate still requires an actual sustained deployed HTTPS runtime and genuine rolling 30-day SLO telemetry.
- No live Binance request, production credential, order, deployment, repository setting or remote branch changed.

## Scorecard

| Dimension | Previous checkpoint | This checkpoint | Evidence and remaining deduction |
| --- | ---: | ---: | --- |
| Trading correctness and risk protection | 16/20 | **16/20** | Unknown Spot acknowledgement statuses fail closed and ambiguous intents block retries. Exchange-resident fill-linked protection, crash recovery, approved durable risk budgets and kill state remain missing. |
| Security and credential boundaries | 11/15 | **11/15** | Account-wide fencing, key inventory/revocation, other-user/host controls and independent security review remain open. |
| State, recovery and execution ownership | 13/15 | **13/15** | Local restore and incident/audit continuity are tested on an earlier commit. Portfolio/fill reconciliation, anti-rollback, atomic snapshots and cross-key/host fencing remain open. |
| Automated verification and CI | 14/15 | **14/15** | The full source gate passes; candidate CI and external promotion evidence remain outstanding. |
| Deployment and release integrity | 6/10 | **6/10** | No attested release artifact, protected candidate workflow or deployed rollback proof is supplied. |
| Operations and production evidence | 6/10 | **6/10** | Local restore and incident/audit artifacts passed on an earlier commit. The sustained deployed-service probe and rolling 30-day production SLO evidence remain missing. |
| Architecture and maintainability | 6/10 | **6/10** | Python remains canonical; Spot protection lifecycle, full account recovery and broader executor fencing remain open. |
| Product scope, operator QA and support | 4/5 | **4/5** | The target is selected, but the account, machine, operator, approved risk policy and signed acceptance remain unnamed. |
| **Total** | **76/100** | **76/100** | **NO-GO for live trading.** |

The preceding [recovery-evidence reassessment](PRODUCTION_READINESS_REVIEW_2026-09-24_RECOVERY_EVIDENCE.md) remains evidence for its own checkpoint. The score stays unchanged because this patch strengthens an existing fail-closed boundary but does not close a production acceptance criterion.

## Remaining blockers

- PRD-010/011 still need exchange-resident, fill-linked Spot protection and fault/recovery proof for partial fills, ambiguous acknowledgements, restart, reconnect and manual exchange changes.
- PRD-008 needs portfolio/fill reconciliation, restored-state anti-rollback, verified key/UID pairing during rotation, and controls for external users, hosts, bots and API keys. PRD-009 needs operator-selected risk limits and reset authority, durable account-wide accounting and restart-safe kill state.
- The strict gate needs the sustained deployed HTTPS service artifact and genuine rolling 30-day production telemetry. Candidate CI, repository governance, named incident owners and signed risk acceptance also remain open.
