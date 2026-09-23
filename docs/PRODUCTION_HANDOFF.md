# Start here: production-readiness work

This file makes the work resumable in a new chat **without the old conversation**. Use the same repository checkout, or carry these versioned documents to another machine. They are ordinary local files; until committed/pushed they are available only where these working-tree changes exist.

## Current checkpoint

- Audit date: **2026-09-17**.
- Audited source: `e574dae633d2186b8af4af1013076ff91f778bb9` on `main`.
- Latest pre-change source: `8700725f4e76a49bd195d6d2ba99e3ff3c792b67` on `main`; the 2026-09-23 implementation is on `codex/production-readiness-20260923`. Check `git rev-parse HEAD` for its current commit.
- Score: **58/100 for unattended real-money production; NO-GO**. This is not a profitability score or a score for every possible deployment scope.
- Delivered: deep audit, verification ledger, prioritized implementation backlog, this handoff, repository navigation pointers.
- Product fixes delivered offline: **PRD-002–006, PRD-018 and PRD-023**. **PRD-007, PRD-019 and PRD-020** have bounded implementations in progress. No live orders, deployments, remote settings or credentials changed. Documentation and offline tests do not close external production evidence requirements.
- Previous implementation checkpoint: **PRD-002 DONE** in commit `6335304f593ae70383c2b454f6e0c707f20e29d5`; it hardens the host-owned LLM provider, credential-reference, destination and public-network-consent boundary.
- Previous implementation checkpoint: **PRD-003 DONE** in commit `206fa48a07c8e774faebb51d1470d84e37547058`; it enforces HTTPS or explicit loopback HTTP for LLM inference/discovery and rejects unsafe endpoint syntax before network calls.
- Latest implementation checkpoint: **PRD-004 DONE** in commit `01a24cf8c6a2f831f357d1ddc5f445c32bc17b04`; it rejects ccxt protected-order parameter collisions before exchange construction or order submission. The baseline score has not been re-scored.
- Latest implementation checkpoint: **PRD-005 DONE** in commit `1d7779bcad5d055594d660dcb76e4fa6c95c7d59`; it carries exchange event/receipt metadata, rejects stale/replayed/invalid live candles before new exposure and preserves source event timestamps through strategy orders. The baseline score has not been re-scored.
- Latest implementation checkpoint: **PRD-006 DONE** in commit `5b1908987ccefe0995887d6a76f1cd5948c00303`; it confines deployment probe evidence to the canonical artifact directory, verifies the expected `/readyz` commit across observations, and requires server `read_only=true` in the protected workflow. The baseline score has not been re-scored.
- 2026-09-23 source checkpoint: an exact-digest read-only image publisher/verifier, bounded advisory LLM transport, an enforced redacted Git-history secret scan, a next-bar-open backtest mode and corrected support docs are implemented. The full source gate passed with **1,901 Python tests, 2 skips and 54.01% coverage**, plus service/web/mobile/Rust/Tauri/C++ checks. One advisory workspace-hygiene check observed ignored build/cache files. The external promotion evidence-import check was explicitly skipped; no real image was published or deployed.
- Remaining immediate blockers: `main` and the `production` environment lack observed enforcement; no independent reviewer/release approvers or approved account/host/risk policy is recorded. The read-only observer yields only **1 of 4** required unseeded trading-freshness samples. Two distinct ledger paths can each accept a synthetic intent, so PRD-008 account-wide execution ownership is open. Six reviewed Rust dependency exceptions expire **2026-10-10** and need named owners.
- Canonical evidence/findings: [PRODUCTION_READINESS_AUDIT.md](PRODUCTION_READINESS_AUDIT.md).
- Canonical task statuses/acceptance criteria/work log: [PRODUCTION_IMPLEMENTATION_PLAN.md](PRODUCTION_IMPLEMENTATION_PLAN.md).

## First actions for a new agent

1. Read root `AGENTS.md`, then this file, the audit verdict/findings and the implementation plan. Do not rely on memory of an earlier chat.
2. Run `git status --short --branch` and `git rev-parse HEAD`. Preserve unrelated changes. Compare current code with the audited SHA; findings and remote statuses may have changed.
3. Read the task register and latest work-log entry. Reproduce the selected defect offline before fixing it; never assume it remains unfixed.
4. Recommended next task: **PRD-008 (account identity and single execution owner)** with an offline fail-closed owner contract first; obtain the operator's initial scope/account/host decision before claiming live enforcement. PRD-007 needs an authorized real publisher run and PRD-001 needs reviewer/settings decisions. The unseeded-observer data contract remains open.
5. Follow the chosen task's dependencies and acceptance criteria. Finish a coherent patch with regression tests. Do not weaken safety/tests, hand-edit generated parity, make speculative broad rewrites, or promote unsupported targets.
6. Update the task register/work log and this checkpoint with the actual tests, SHA/PR, remaining blockers and next task before ending the turn. Keep the historical audit baseline intact; add dated reassessments.

## Ready-to-paste prompt

```text
Continue this repository's production-readiness implementation.
Read AGENTS.md, docs/PRODUCTION_HANDOFF.md,
docs/PRODUCTION_READINESS_AUDIT.md and docs/PRODUCTION_IMPLEMENTATION_PLAN.md.
Inspect current git state and the latest work log; preserve unrelated changes.
Implement the next ready high-priority task (current recommendation PRD-008),
reproduce the issue, add regression tests and run the appropriate gates.
Do not place orders, deploy, change live risk limits, expose secrets, or change
GitHub settings without the necessary explicit authorization.
Update the task register and handoff with evidence and the next action.
Do not claim production readiness from green CI or documentation alone. Keep the
58/100 unattended-production baseline until a fresh dated evidence review.
```

To request planning only, replace “Implement” with “Review and propose changes for”. To choose a task, replace `PRD-007` with its task ID.

## Known environment/evidence caveats

- The 2026-09-23 source gate ran locally under the declared Python 3.14 environment; see the latest plan work log for exact command, counts, report hash and explicit external-evidence skip. The earlier audit's 1,851 passes and 53.52% coverage remain historical.
- On 2026-09-23, public GitHub reads again reported `main` unprotected, no effective branch rules or repository rulesets, and no protection rules on `production`; administrator-only settings were unavailable. [The governance proposal](PRODUCTION_GOVERNANCE_PROPOSAL.md) is ready for operator review. Recheck remote state before acting.
- Required local production evidence was missing. Genuine rolling 30-day telemetry, release signing/QA, actual alert delivery, account recovery and deployment inputs cannot be fabricated by an agent.
- Python owns trading behavior; native C++/Rust/mobile are not automatically promoted by source parity. Read-only Kubernetes replicas are not trading HA.
