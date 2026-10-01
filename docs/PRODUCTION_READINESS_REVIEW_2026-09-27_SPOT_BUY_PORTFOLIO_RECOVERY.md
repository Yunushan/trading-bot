# Production readiness reassessment — Spot BUY portfolio recovery

## Verdict and tested revision

**78/100 for the selected first target (Python desktop + Binance Spot on one host): NO-GO for live trading.** The reviewed code commit is `3b8400d1` on `codex/prd009-futures-snapshot-guard`.

The new recovery path applies exact terminal Spot market BUY fills to the desktop's durable allocation snapshot. It reconciles Binance trade rows against the exact order totals, accounts for commissions charged in the base asset or USDT, and stores a stable fill signature before resolving the intent. This covers both a primary `FILLED` acknowledgement followed by a desktop persistence failure and restart recovery from an unresolved intent, for USDT-quoted BUYs only. Unsupported fills remain blocked. One point is added for the verified fee-aware position accounting path; this does not establish production acceptance.

## Change and verification evidence

- Added `recover-spot-market-fills`, an explicit Live Spot administration action. It verifies the signed account identity, rechecks each exact unresolved order, loads bounded `myTrades` pages by symbol/order ID and fetches the symbol's base/quote metadata. Binance documents the order-trade endpoint and the response fields used for this proof in its [Spot REST API](https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md?plain=1).
- Recovery supports terminal Spot `MARKET` BUYs quoted in USDT. It subtracts base-asset commission from received inventory and adds USDT commission to cost. It verifies executed quantity and cumulative quote quantity against every exact order trade, then atomically and idempotently writes the Live desktop snapshot. The order intent is marked reconciled only after the on-disk allocation contains the same client order ID, net quantity and proof signature.
- Normal primary `FILLED` BUY acknowledgements use the same commission-aware proof. The GUI persists its allocation snapshot before recording the portfolio proof; a failed write or missing proof leaves the positive-fill intent unresolved and blocks another live entry.
- SELL fills, non-USDT quote pairs, third-asset commissions, incomplete/contradictory trade history and malformed snapshots remain unresolved. Recovery does not place or cancel orders, rearm the owner, reconcile all account balances or fills, or fence other keys/users/hosts/executors. Stop-loss protection and the broader exchange fault matrix remain open.
- Focused offline command: `.venv\\Scripts\\python.exe -m pytest Languages/Python/tests/test_order_acknowledgement_identity.py Languages/Python/tests/test_spot_fill_recovery_runtime.py Languages/Python/tests/test_allocation_persistence.py Languages/Python/tests/test_spot_user_data_admin_runtime.py Languages/Python/tests/test_spot_reconciliation_admin.py Languages/Python/tests/test_order_intent_reconciliation_safety.py Languages/Python/tests/test_order_intent_transactions.py Languages/Python/tests/test_open_trade_signal_behavior.py Languages/Python/tests/test_spot_execution_owner.py Languages/Python/tests/test_spot_owner_gui_lifecycle.py -q --no-cov` — **97 passed, 199 subtests passed**.
- The full `.venv\\Scripts\\python.exe tools/verify_all.py --skip-promotion-evidence --json` gate returned `ok=true`: **1,973 Python tests passed, 2 Windows symlink skips, 54.78% coverage**; Ruff, mypy across 30 files, service/API, web/mobile, Rust (**313 tests**), Tauri and native C++ (**4/4**) passed. Critical Python execution coverage floors passed. The risky-pattern audit matched its baseline at 2,964 broad exceptions and 750 silent-pass findings. Workspace hygiene reported ignored Rust build/cache directories as an advisory. The Rust live-smoke preflight attempted no network request; external Rust evidence import was explicitly skipped because it requires clean-commit operational evidence.
- Local restore and incident/audit continuity drills in the source gate passed using synthetic credentials and read-only local service state. They are not deployed runtime evidence or a rolling production SLO. Source-bound artifacts must be regenerated after the final documentation commit, then the strict operational readiness gate must be rerun.
- No live Binance request, production credential, order, deployment, repository setting or remote branch changed.

## Scorecard

| Dimension | Previous checkpoint | This checkpoint | Evidence and remaining deduction |
| --- | ---: | ---: | --- |
| Trading correctness and risk protection | 16/20 | **17/20** | Exact fee-aware accounting now imports supported positive BUY fills. Exchange-resident protection, SELL recovery, other quote/fee assets, approved risk budgets and durable kill state remain open. |
| Security and credential boundaries | 11/15 | **11/15** | Account-wide fencing, key inventory/revocation, other-user/host controls and independent security review remain open. |
| State, recovery and execution ownership | 14/15 | **14/15** | Supported BUY fill proof is durable and idempotent; SELL and other unsupported fills still block. Restored-state anti-rollback and broader executor fencing remain open. |
| Automated verification and CI | 14/15 | **14/15** | Full source verification and quality floors pass; candidate CI and external promotion evidence remain outstanding. |
| Deployment and release integrity | 6/10 | **6/10** | No attested release artifact, protected candidate workflow or deployed rollback proof is supplied. |
| Operations and production evidence | 6/10 | **6/10** | Local drills pass, but deployed HTTPS runtime and genuine rolling 30-day production SLO evidence remain missing. |
| Architecture and maintainability | 6/10 | **6/10** | Python remains canonical; exchange-resident Spot protection, complete fill lifecycle and broader fencing remain open. |
| Product scope, operator QA and support | 4/5 | **4/5** | The target is selected, but account, machine, operator, approved risk policy and signed acceptance remain unnamed. |
| **Total** | **77/100** | **78/100** | **NO-GO for live trading.** |

## Remaining blockers

- PRD-010 still needs exchange-resident, fill-linked Spot protection with verified partial-fill, acknowledgement, restart, reconnect and manual-exchange-change behavior.
- PRD-008/011 still need supported SELL-fill recovery and broader fee/quote-asset handling, restored-state anti-rollback, full account-to-portfolio reconciliation and stronger fencing.
- PRD-009 still needs operator-selected risk limits, durable account-wide accounting, restart-safe kill state and audited reset authority.
- The strict operational gate needs a real deployed HTTPS runtime probe and genuine rolling 30-day production telemetry. Release signing/QA, candidate CI, named incident ownership and signed risk acceptance also remain open.

The preceding [77/100 Spot fill recovery visibility review](PRODUCTION_READINESS_REVIEW_2026-09-27_SPOT_FILL_RECOVERY.md) remains historical evidence for code commit `0fa604dd`.
