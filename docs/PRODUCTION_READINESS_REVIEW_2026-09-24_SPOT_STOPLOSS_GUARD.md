# Production readiness reassessment — 2026-09-24 Spot stop-loss guard

## Verdict and tested revision

**74/100 for the selected first target (Python desktop + Binance Spot on one host): NO-GO for live trading.** This review applies to source revision `2070f9de` on `codex/prd009-futures-snapshot-guard`. The score is an engineering assurance assessment, not a profitability estimate, loss probability, or authorization to trade or deploy.

The new guard closes a false-assurance path: the dashboard exposed a stop-loss setting as applicable to live trades, but strategy stop management only evaluated Futures positions. Live Spot BUYs now fail before order intent creation and before exchange submission when `stop_loss.enabled` is true. The guard checks both current strategy settings and the lower-level Binance Spot order method, so a stale wrapper config cannot bypass the desktop strategy check. It leaves Spot SELL reductions available and updates the UI wording to say Futures only.

This does **not** implement exchange-resident Spot protection. If the setting is disabled, a live Spot position still has no crash-independent stop; fills, open orders, restarts and manual exchange changes are not reconciled into a protection lifecycle. This increment removes one misleading unsafe configuration and does not close PRD-010.

## Verification evidence

- Focused command `.\.venv\Scripts\python.exe -m pytest Languages/Python/tests/test_order_acknowledgement_identity.py Languages/Python/tests/test_fake_exchange_integration.py -q --no-cov` passed: **21 tests and 90 subtests**. It proves that the blocked Live Spot BUY performs no exchange request or intent creation, while Spot SELL remains available.
- `.\.venv\Scripts\ruff.exe check` passed on every changed Python source and test file.
- Full command `.\.venv\Scripts\python.exe tools/verify_all.py --skip-promotion-evidence --json` returned exit 0 and `ok=true`: **1,953 Python tests passed, 2 skipped, 54.48% coverage**; Ruff, mypy (30 files), critical coverage floors, service API contracts/tests, web/mobile, Rust (313 tests), Tauri and native C++ (4/4) passed. The external Rust evidence-import audit was skipped because it requires clean-commit external runtime/release evidence. Workspace hygiene reported ignored Rust build/cache artifacts. The Rust read-only live-smoke preflight confirmed no network request and no order submission when credentials/clean-source prerequisites were absent.
- No live Binance request, credential, order, deployment, repository setting or remote branch was used or changed.

## Scorecard

| Dimension | Previous checkpoint | This checkpoint | Evidence and remaining deduction |
| --- | ---: | ---: | --- |
| Trading correctness and risk protection | 15/20 | **16/20** | Unsupported configured Spot stop-loss now blocks Live Spot buys before side effects. Exchange-resident fill-linked protection, crash recovery, approved durable risk budgets and kill state remain missing. |
| Security and credential boundaries | 11/15 | **11/15** | Account-wide fencing, key inventory/revocation, other-user/host controls and independent security review remain open. |
| State, recovery and execution ownership | 13/15 | **13/15** | Tested single-key reconciliation remains bounded. Portfolio/fill reconciliation, anti-rollback, atomic snapshots and cross-key/host fencing remain open. |
| Automated verification and CI | 14/15 | **14/15** | The full source gate passes; candidate CI and external promotion evidence remain outstanding. |
| Deployment and release integrity | 6/10 | **6/10** | No attested release artifact, protected candidate workflow or deployed rollback proof is supplied. |
| Operations and production evidence | 4/10 | **4/10** | Sustained runtime, SLO, restore and incident/audit artifacts are still missing. |
| Architecture and maintainability | 6/10 | **6/10** | Python remains canonical; Spot protection lifecycle, full account recovery and broader executor fencing remain open. |
| Product scope, operator QA and support | 4/5 | **4/5** | The target is selected, but the account, machine, operator, approved risk policy and signed acceptance remain unnamed. |
| **Total** | **73/100** | **74/100** | **NO-GO for live trading.** |

The one-point increase credits a tested entry-time block for an enabled but unsupported Spot stop-loss. It does not credit independent protection or observed Spot recovery. The preceding [73/100 account-audit reassessment](PRODUCTION_READINESS_REVIEW_2026-09-24_ACCOUNT_AUDIT.md) remains historical for its tested revision.

## Remaining launch blockers

- PRD-010/011 still need exchange-resident, fill-linked protection and end-to-end fault/recovery proof for partial fills, ambiguous acknowledgements, restart, reconnect and manual exchange changes.
- PRD-008 needs portfolio/fill reconciliation, restored-state anti-rollback, verified key/UID pairing during rotation, and controls for external users, hosts, bots and API keys.
- PRD-009 needs operator-selected risk limits and reset authority, durable account-wide accounting, restart-safe kill state and audited external-position reconciliation.
- The four required production evidence artifacts, candidate CI, repository governance, named incident owners and signed risk acceptance remain open. Green source checks are not production sign-off.
