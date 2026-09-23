# Production readiness reassessment — 2026-09-23

## Verdict and scope

**65/100 for unattended real-money production: NO-GO.** This is a dated engineering judgment using the [2026-09-17 audit rubric](PRODUCTION_READINESS_AUDIT.md), not a probability of avoiding loss, a profitability estimate, or authorization to trade or deploy. Launch blockers override the total. The earlier **58/100** score remains the historical baseline.

- Reviewed clean code commit: `7cf7f7d46db7aa0715722b866e90d455fe602514` on `codex/production-readiness-20260923`.
- Local declared-runtime source gate: `tools/verify_all.py --skip-promotion-evidence --json` returned `ok=true`. It evaluated 41 checks; only the nonblocking workspace-hygiene observation reported ignored build/cache files. The external Rust evidence-import check was explicitly skipped. Python tests: **1,901 passed, 2 Windows symlink skips**, **54.01% coverage** against a 46% floor. Service, web, mobile, Rust, Tauri, C++, parity, deployment-contract, lint, type and source-compile checks passed. The local temporary JSON report has SHA-256 `071df5347cc5b5ef90053cc2e171c4b2c3c6724e424171f01f60ca26e31f399a`; it is not retained production evidence.
- The strict clean-commit check `tools/check_operational_readiness.py --require-evidence --require-current-commit --require-clean-source --json` returned `schema_ok=true`, `current_source_tree_clean=true`, `promotion_ready=false`. All four required artifacts were missing: sustained service runtime, production SLO window, service-config backup/restore, and incident-audit continuity. Its local temporary report has SHA-256 `7e4cf7f9b9ed08e3d971028c9181311be9b93a809fcf7406654223ffdcc6cb05`.
- Public repository reads on 2026-09-23 still showed `main protected=false`, no effective branch rules or repository rulesets, and `production` with no protection rules and administrator bypass enabled. Administrator-only settings, including native secret-scanning and push protection, were not verified. See the [governance proposal](PRODUCTION_GOVERNANCE_PROPOSAL.md).

## Scorecard

| Dimension | 2026-09-17 | 2026-09-23 | Evidence and remaining deduction |
| --- | ---: | ---: | --- |
| Trading correctness and risk protection | 12/20 | **14/20** | Offline regressions now reject ccxt protected-field collisions and stale/replayed/invalid live candles before new exposure. Account-wide limits and crash-independent position protection remain absent. |
| Security and credential boundaries | 9/15 | **11/15** | Host-owned LLM provider/credential/destination controls, HTTPS-or-loopback policy, bounded LLM transport, and an enforced redacted Git-history secret scan passed local tests. No deployment-host or penetration-test assurance. |
| State, recovery and execution ownership | 8/15 | **8/15** | Ledger transactions remain path-specific and API-key-bound. Two independent paths accepted synthetic intents; no authoritative account owner fence, durable aggregate risk state or physical host-loss proof. |
| Automated verification and CI | 12/15 | **13/15** | The current local source gate passed across languages and raised measured line coverage to 54.01%. Main is still unprotected; critical coverage, typing and operational integration still have gaps. |
| Deployment and release integrity | 4/10 | **6/10** | Probe output/identity/read-only regressions and an offline exact-digest publisher/verifier contract passed. No actual attested release image, registry-retention proof, protected release-tag drill or cluster deployment evidence. |
| Operations and production evidence | 4/10 | **4/10** | The strict clean-commit promotion check failed on four missing required artifacts. No genuine sustained SLO, paging, recovery or account reconciliation window was supplied. |
| Architecture and maintainability | 6/10 | **6/10** | Python contracts remain canonical; trading is still desktop-owned, the standalone service is heartbeat-only, and long-history ledger capacity is unmeasured. |
| Product scope, operator QA and support | 3/5 | **3/5** | No signed candidate acceptance packet, named release owners or chosen first-release trading/account/host scope. |
| **Total** | **58/100** | **65/100** | **NO-GO for unattended real-money production.** |

The seven-point increase credits reproduced and tested behavior plus the complete local source gate. It does not credit task labels, documentation volume, or green checks as operational proof. The highest-priority remaining work is account identity and single-owner fencing (PRD-008), durable aggregate risk/kill state (PRD-009), exchange-resident or independently verified position protection (PRD-010), recovery fault proof (PRD-011), and the external governance/release/operations evidence in PRD-001/007/015/016/022. The read-only observer still produced only one of four unseeded trading-freshness samples. [The implementation plan](PRODUCTION_IMPLEMENTATION_PLAN.md) is the canonical task-status register.
