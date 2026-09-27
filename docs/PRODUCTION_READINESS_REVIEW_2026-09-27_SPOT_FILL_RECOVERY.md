# Production readiness reassessment — Spot fill recovery visibility

## Verdict and tested revision

**77/100 for the selected first target (Python desktop + Binance Spot on one host): NO-GO for live trading.** The reviewed code commit is `0fa604dde1c661383d2362d4c368a2112980120e` on `codex/prd009-futures-snapshot-guard`.

Exact reconciliation of an uncertain Spot `MARKET` intent now retains the unresolved block for every positive execution, including `FILLED`. The per-order recovery command exposes the exact order response quantities and an estimated gross average fill price. The account audit reports only how many positive fills still require portfolio reconciliation. No workflow yet imports exchange fills into the desktop's durable position allocations.

This change earns no additional score point because it extends the existing State/recovery control without closing fee-aware inventory reconciliation. The score is an engineering assurance assessment, not a profitability estimate or permission to trade or deploy.

## Change and verification evidence

- A reproduced crash-recovery gap allowed an exact query of an uncertain Spot market order to resolve a positive full fill as `accepted`. That response established exchange execution but could not establish that the desktop position allocation had been durably saved before a process crash.
- Exact reconciliation now keeps positive Spot market fills unresolved and blocks subsequent intents until a portfolio recovery workflow exists. This rule applies to full and partial fills, including canceled/expired partial orders. Confirmed zero-fill terminal results can resolve. Normal primary `FILLED` acknowledgements retain their prior behavior; the crash window between that acknowledgement and desktop position persistence remains open.
- The explicit `reconcile-spot` action displays validated order identity, side/type, original and executed quantities, Binance's cumulative quote quantity, and `gross_average_price` when those quantities are valid. It marks `portfolio_reconciliation_required` and reports failure while a positive fill remains unresolved. The account-wide audit emits only the count of positive market fills requiring portfolio reconciliation; it continues to redact symbols, client IDs, order IDs and amounts. Neither action automatically rearms the owner.
- Binance's Spot order response documents `cummulativeQuoteQty`; dividing it by executed quantity gives a gross average price. The diagnostic excludes commissions and cannot serve as net portfolio inventory. See the [Binance Spot REST API order response](https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md?plain=1).
- Focused offline checks: **37 passed, 149 subtests passed** across Spot reconciliation, acknowledgement identity and order-intent recovery tests. Full Python suite on the implementation commit: **1,960 passed, 2 skipped**, 54.49% total coverage. Ruff passed; mypy passed for 30 source files. Critical coverage floors passed: strategy 75.95%, positions 68.58%, Binance market 71.83%, Binance orders 84.22%, service runners 87.17%, and settings 94.87%. The two skips are Windows symlink privilege/environment constraints.
- A complete `verify_all.py --skip-promotion-evidence --json` run on the earlier working-tree stage of this increment returned `ok=true`, covering Python tests, Ruff, mypy, service/web/mobile, Rust (313 tests), Tauri, native C++ (4/4), and local service/recovery checks. The positive-full-fill guard was added afterward and is covered by the final 1,960-test run. The Rust external promotion-evidence importer was skipped; the verifier's read-only preflight attempted no network request. Workspace hygiene reported ignored build/cache paths.
- Local restore and incident/audit artifacts were last accepted by the strict operational gate on clean documentation commit `444a8f4308544ce701e6d2c6fd4db7fac9cb8c3c`. They are stale after this code and documentation work and must be regenerated for the final commit. The last strict gate accepted both local artifacts but remained `promotion_ready=false` because the deployed HTTPS runtime and genuine rolling 30-day SLO artifacts were missing. Policy SHA-256: `89fd34b17ac695febf98fd9e72ed21aa606cd5fbc7345244d85ea1e4ca47b02c`.
- No live Binance request, production credential, order, deployment, repository setting or remote branch changed.

## Scorecard

| Dimension | Previous checkpoint | This checkpoint | Evidence and remaining deduction |
| --- | ---: | ---: | --- |
| Trading correctness and risk protection | 16/20 | **16/20** | Exact positive fills remain blocked on recovery; exchange-resident Spot protection, primary-ack crash recovery, approved durable risk budgets and kill state remain missing. |
| Security and credential boundaries | 11/15 | **11/15** | Account-wide fencing, key inventory/revocation, other-user/host controls and independent security review remain open. |
| State, recovery and execution ownership | 14/15 | **14/15** | Exact positive Spot market fills remain unresolved and their quantities are operator-visible; fee-aware fill-to-portfolio import, anti-rollback, atomic snapshots and cross-key/host fencing remain open. |
| Automated verification and CI | 14/15 | **14/15** | Current Python verification and quality floors pass; candidate CI and current external promotion evidence remain outstanding. |
| Deployment and release integrity | 6/10 | **6/10** | No attested release artifact, protected candidate workflow or deployed rollback proof is supplied. |
| Operations and production evidence | 6/10 | **6/10** | Local recovery drills require current-source regeneration; deployed-service runtime and rolling 30-day production SLO evidence remain missing. |
| Architecture and maintainability | 6/10 | **6/10** | Python remains canonical; Spot protection lifecycle, full account recovery and broader executor fencing remain open. |
| Product scope, operator QA and support | 4/5 | **4/5** | The target is selected, but account, machine, operator, approved risk policy and signed acceptance remain unnamed. |
| **Total** | **77/100** | **77/100** | **NO-GO for live trading.** |

## Remaining blockers

- PRD-008/011 need a supported, idempotent path to apply exchange fills and commissions to durable Spot portfolio state before owner rearm. The primary `FILLED` acknowledgement crash window remains unresolved.
- PRD-010 needs exchange-resident fill-linked protection and fault/recovery proof for partial fills, acknowledgement ambiguity, restart, reconnect and manual exchange changes.
- PRD-009 needs operator-selected risk limits and reset authority, durable account-wide accounting and restart-safe kill state. PRD-008 still needs restored-state anti-rollback and controls for external users, hosts, bots and API keys.
- The strict operational gate still needs a deployed HTTPS runtime probe and genuine rolling 30-day production telemetry. Candidate CI, release governance, named incident owners and signed risk acceptance remain open.

The preceding [2026-09-27 partial-fill guard review](PRODUCTION_READINESS_REVIEW_2026-09-27_SPOT_PARTIAL_FILL_GUARD.md) remains historical evidence for code commit `c4a75e5d`.
