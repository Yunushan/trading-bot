# Start here: production-readiness work

This file makes the work resumable in a new chat **without the old conversation**. Use the same repository checkout, or carry these versioned documents to another machine. They are ordinary local files; until committed/pushed they are available only where these working-tree changes exist.

## Current checkpoint

- Audit date: **2026-09-17**.
- Audited source: `e574dae633d2186b8af4af1013076ff91f778bb9` on `main`.
- Latest tested clean code commit: `1578938331fdd04a6cbdd7eb66ac194916cf2cf1` on `codex/prd009-futures-snapshot-guard`, starting from merged `main` commit `3618e4c09ab2732ffe58f4c8ca5de5bbe3a3c5a0`. Check `git rev-parse HEAD` and `git status` for later documentation commits.
- Current dated score: **71/100 for the selected first target (Python desktop + Binance Spot on one host); NO-GO for live trading** at code commit `1578938331fdd04a6cbdd7eb66ac194916cf2cf1`. The preceding 2026-09-24 checkpoints assign **70/100** at `a2918725da4d8b459616b8e1d25eff5456c2b583`, **69/100** at `c6765952f1541b7b80e8158534557971819d24f3` and **67/100** at `317ac2ca98580f13def7111901c9fe980906c61c`; earlier reviews assign **66/100** at `3dc13908b39f6af759cd7c431e2be095366683d7`, **65/100** at `7cf7f7d46db7aa0715722b866e90d455fe602514`, and the 2026-09-17 historical baseline **58/100**. None is a profitability estimate or authorization to trade/deploy.
- Delivered: deep audit, verification ledger, prioritized implementation backlog, this handoff, repository navigation pointers.
- Product fixes delivered offline: **PRD-002–006, PRD-018 and PRD-023**. **PRD-007–009, PRD-019 and PRD-020** have bounded implementations in progress. PRD-009 now rejects malformed Futures stop snapshots, but its durable account-wide risk ledger and restart-safe kill state are still open. PRD-008 now supports offline Live Spot history migration and key rotation with explicit rearm; machine-verified reconciliation, anti-rollback and broader fencing remain open. No live orders, deployments, remote settings or production credentials changed. Documentation and offline tests do not close external production evidence requirements.
- Previous implementation checkpoint: **PRD-002 DONE** in commit `6335304f593ae70383c2b454f6e0c707f20e29d5`; it hardens the host-owned LLM provider, credential-reference, destination and public-network-consent boundary.
- Previous implementation checkpoint: **PRD-003 DONE** in commit `206fa48a07c8e774faebb51d1470d84e37547058`; it enforces HTTPS or explicit loopback HTTP for LLM inference/discovery and rejects unsafe endpoint syntax before network calls.
- Earlier implementation checkpoint: **PRD-004 DONE** in commit `01a24cf8c6a2f831f357d1ddc5f445c32bc17b04`; it rejects ccxt protected-order parameter collisions before exchange construction or order submission.
- Earlier implementation checkpoint: **PRD-005 DONE** in commit `1d7779bcad5d055594d660dcb76e4fa6c95c7d59`; it carries exchange event/receipt metadata, rejects stale/replayed/invalid live candles before new exposure and preserves source event timestamps through strategy orders.
- Earlier implementation checkpoint: **PRD-006 DONE** in commit `5b1908987ccefe0995887d6a76f1cd5948c00303`; it confines deployment probe evidence to the canonical artifact directory, verifies the expected `/readyz` commit across observations, and requires server `read_only=true` in the protected workflow.
- Prior clean-commit 2026-09-23 source checkpoint: an exact-digest read-only image publisher/verifier, bounded advisory LLM transport, an enforced redacted Git-history secret scan, a next-bar-open backtest mode and corrected support docs are implemented. The full source gate passed with **1,901 Python tests, 2 skips and 54.01% coverage**, plus service/web/mobile/Rust/Tauri/C++ checks. One advisory workspace-hygiene check observed ignored build/cache files. The external promotion evidence-import check was explicitly skipped; no real image was published or deployed.
- Latest PRD-008 increment: offline migration moves resolved v1/v2 history to the UID-scoped path, preserves original bytes as backup, disarms before publication, and resumes only from matching recovery state. Offline rotation preserves intents/store ID, rejects unresolved intents/active owner, records fingerprints and requires explicit rearm. Focused checks passed **38 tests, 1 environment-dependent skip, 3 process-dependent tests deselected and 46 subtests**; Ruff and mypy passed. The full repository gate was not rerun after this increment. See the [70/100 reassessment](PRODUCTION_READINESS_REVIEW_2026-09-24_PRD008.md) and its earlier 69/67 checkpoints.
- The full current-revision source gate on code commit `15789383` passed: **1,937 Python tests, 2 Windows symlink skips, 54.35% coverage**, with the configured source, lint/type, service/web/mobile, Rust, Tauri and native C++ checks green. The external Rust evidence import was explicitly skipped; workspace hygiene reported only ignored build/cache paths. See the [71/100 source-gate reassessment](PRODUCTION_READINESS_REVIEW_2026-09-24_SOURCE_GATE.md).
- The strict operational evidence check on clean code revision `1578938331fdd04a6cbdd7eb66ac194916cf2cf1` returned `schema_ok=true`, `current_source_tree_clean=true`, `promotion_ready=false`. It exited 1 because four artifacts are missing: sustained service runtime, production SLO window, service-config backup/restore and incident-audit continuity. Policy SHA-256: `89fd34b17ac695febf98fd9e72ed21aa606cd5fbc7345244d85ea1e4ca47b02c`. The check must pass on any proposed release candidate.
- Remaining immediate blockers: the selected product boundary is Python desktop + Binance Spot on one host, but the account, host identity, operator, risk limits and acceptance are unnamed. PRD-008 still lacks exchange-side fencing, machine-verified reconciliation, restored-state anti-rollback and control of other OS users/hosts/executors. PRD-009 still needs operator-selected budgets and reset authority. The earlier public GitHub REST read observed unprotected `main` and `production`; it was not rechecked here. The unseeded observer still has only **1 of 4** required trading-freshness samples. PRD-020 lacks calibrated market costs, full causality/provenance and holdout/live replay. Six Rust dependency exceptions expire **2026-10-10** and need named owners.
- Canonical evidence/findings: [PRODUCTION_READINESS_AUDIT.md](PRODUCTION_READINESS_AUDIT.md).
- Current dated score and evidence: [PRODUCTION_READINESS_REVIEW_2026-09-24_SOURCE_GATE.md](PRODUCTION_READINESS_REVIEW_2026-09-24_SOURCE_GATE.md). The preceding [70/100 PRD-008 review](PRODUCTION_READINESS_REVIEW_2026-09-24_PRD008.md), [67/100 review](PRODUCTION_READINESS_REVIEW_2026-09-24.md), [2026-09-23 follow-up](PRODUCTION_READINESS_REVIEW_2026-09-23_FOLLOWUP.md) and [prior review](PRODUCTION_READINESS_REVIEW_2026-09-23.md) remain historical evidence for their own code commits.
- Canonical task statuses/acceptance criteria/work log: [PRODUCTION_IMPLEMENTATION_PLAN.md](PRODUCTION_IMPLEMENTATION_PLAN.md).

## First actions for a new agent

1. Read root `AGENTS.md`, then this file, the audit verdict/findings and the implementation plan. Do not rely on memory of an earlier chat.
2. Run `git status --short --branch` and `git rev-parse HEAD`. Preserve unrelated changes. Compare current code with the audited SHA; findings and remote statuses may have changed.
3. Read the task register and latest work-log entry. Reproduce the selected defect offline before fixing it; never assume it remains unfixed.
4. Recommended next task: continue **PRD-008** with restored-state anti-rollback and machine-verified reconciliation design for the selected one-host target. **PRD-009 is IN_PROGRESS:** the malformed-snapshot guard is implemented, but operator-selected limits, durable account-wide accounting, restart-safe kill state and audited reset still need work. PRD-007 needs an authorized real publisher run; PRD-001 needs reviewer/settings decisions; genuine active-trading observations remain open.
5. Follow the chosen task's dependencies and acceptance criteria. Finish a coherent patch with regression tests. Do not weaken safety/tests, hand-edit generated parity, make speculative broad rewrites, or promote unsupported targets.
6. Update the task register/work log and this checkpoint with the actual tests, SHA/PR, remaining blockers and next task before ending the turn. Keep the historical audit baseline intact; add dated reassessments.

## Ready-to-paste prompt

```text
Continue this repository's production-readiness implementation.
Read AGENTS.md, docs/PRODUCTION_HANDOFF.md,
docs/PRODUCTION_READINESS_AUDIT.md and docs/PRODUCTION_IMPLEMENTATION_PLAN.md.
Inspect current git state and the latest work log; preserve unrelated changes.
Continue the next ready high-priority task (current recommendation PRD-008),
inspect the bounded Live Spot owner implementation and its remaining acceptance
gaps, add regression tests for the next coherent slice and run the appropriate gates.
Do not place orders, deploy, change live risk limits, expose secrets, or change
GitHub settings without the necessary explicit authorization.
Update the task register and handoff with evidence and the next action.
Do not claim production readiness from green CI or documentation alone. Use the
71/100 target-limited NO-GO reassessment, retain the preceding 70/100,
69/100 and 67/100, prior 66/100 and 65/100 clean-commit reviews and preserve the 58/100
historical audit.
```

To request planning only, replace “Continue” with “Review and propose changes for”. To choose a task, replace `PRD-008` with its task ID.

## Known environment/evidence caveats

- The latest Python 3.14 full source gate is on code commit `15789383`; it returned `ok=true` with **1,937 passed, 2 skipped, 54.35% coverage**. Lazy package exports remove exchange SDK startup from offline admin tools, and worker tests defer unrelated mock/service imports; the original subprocess regressions now pass. The strict clean-source check on the same code commit confirms all four operational evidence artifacts are still missing. The external Rust evidence importer was skipped. See the latest plan work log and dated reviews for exact evidence.
- On 2026-09-23, a fresh public GitHub REST recheck reported `main protected=false`, no repository rulesets, `production protection_rules=[]` and `can_admins_bypass=true`; administrator-only settings were unavailable and no settings changed. [The governance proposal](PRODUCTION_GOVERNANCE_PROPOSAL.md) is ready for operator review. Recheck remote state before acting.
- Required local production evidence was missing. Genuine rolling 30-day telemetry, release signing/QA, actual alert delivery, account recovery and deployment inputs cannot be fabricated by an agent.
- Python owns trading behavior; native C++/Rust/mobile are not automatically promoted by source parity. Read-only Kubernetes replicas are not trading HA.
