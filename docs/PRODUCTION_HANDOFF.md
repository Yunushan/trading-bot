# Start here: production-readiness work

This file makes the work resumable in a new chat **without the old conversation**. Use the same repository checkout, or carry these versioned documents to another machine. They are ordinary local files; until committed/pushed they are available only where these working-tree changes exist.

## Current checkpoint

- Audit date: **2026-09-17**.
- Audited source: `e574dae633d2186b8af4af1013076ff91f778bb9` on `main`.
- Current tested clean code commit: `3dc13908b39f6af759cd7c431e2be095366683d7` on `codex/production-readiness-20260923`, starting from `af720dfcc646b77d07cbd6d9c638dd0d07b2324c`. The source gate passed on its staged candidate and the strict evidence check ran on this clean commit. Check `git rev-parse HEAD` and `git status` for later documentation commits.
- Current dated score: **66/100 for unattended real-money production; NO-GO** at clean code commit `3dc13908b39f6af759cd7c431e2be095366683d7`. The [prior dated review](PRODUCTION_READINESS_REVIEW_2026-09-23.md) assigned **65/100 NO-GO** at `7cf7f7d46db7aa0715722b866e90d455fe602514`; the 2026-09-17 **58/100** audit is the historical baseline. None is a profitability estimate or a score for every deployment scope.
- Delivered: deep audit, verification ledger, prioritized implementation backlog, this handoff, repository navigation pointers.
- Product fixes delivered offline: **PRD-002–006, PRD-018 and PRD-023**. **PRD-007, PRD-008, PRD-019 and PRD-020** have bounded implementations in progress. No live orders, deployments, remote settings or credentials changed. Documentation and offline tests do not close external production evidence requirements.
- Previous implementation checkpoint: **PRD-002 DONE** in commit `6335304f593ae70383c2b454f6e0c707f20e29d5`; it hardens the host-owned LLM provider, credential-reference, destination and public-network-consent boundary.
- Previous implementation checkpoint: **PRD-003 DONE** in commit `206fa48a07c8e774faebb51d1470d84e37547058`; it enforces HTTPS or explicit loopback HTTP for LLM inference/discovery and rejects unsafe endpoint syntax before network calls.
- Earlier implementation checkpoint: **PRD-004 DONE** in commit `01a24cf8c6a2f831f357d1ddc5f445c32bc17b04`; it rejects ccxt protected-order parameter collisions before exchange construction or order submission.
- Earlier implementation checkpoint: **PRD-005 DONE** in commit `1d7779bcad5d055594d660dcb76e4fa6c95c7d59`; it carries exchange event/receipt metadata, rejects stale/replayed/invalid live candles before new exposure and preserves source event timestamps through strategy orders.
- Earlier implementation checkpoint: **PRD-006 DONE** in commit `5b1908987ccefe0995887d6a76f1cd5948c00303`; it confines deployment probe evidence to the canonical artifact directory, verifies the expected `/readyz` commit across observations, and requires server `read_only=true` in the protected workflow.
- Prior clean-commit 2026-09-23 source checkpoint: an exact-digest read-only image publisher/verifier, bounded advisory LLM transport, an enforced redacted Git-history secret scan, a next-bar-open backtest mode and corrected support docs are implemented. The full source gate passed with **1,901 Python tests, 2 skips and 54.01% coverage**, plus service/web/mobile/Rust/Tauri/C++ checks. One advisory workspace-hygiene check observed ignored build/cache files. The external promotion evidence-import check was explicitly skipped; no real image was published or deployed.
- Current follow-up: Live Spot has a signed UID-based fixed ledger root and retained owner lock for one OS user on one host; second wrappers/processes and restart without offline reconciliation attestation are blocked. The read-only deployment workflow selects versioned, nonpromotion `observer-smoke` service-health evidence and explicitly reports trading observations unavailable. The next-bar-open backtest validates fee/slippage inputs and adverse cost sensitivity. The staged-candidate complete source gate returned `ok=true` across **41 checks**, with **1,923 Python tests passed, 2 Windows symlink skips and 54.23% coverage**; Rust core, native C++, Tauri, service/web/mobile, lint/type and other required source checks passed. Only a nonblocking ignored-build/cache workspace advisory was false; external Rust evidence import was skipped. Two earlier combined runs exposed a Rust fixture failure, repaired before this full rerun.
- Strict operational evidence check on clean code commit `3dc13908b39f6af759cd7c431e2be095366683d7` returned `schema_ok=true`, `current_source_tree_clean=true`, `promotion_ready=false`. The four required artifacts were missing: sustained service runtime, production SLO window, service-config backup/restore and incident-audit continuity. The check exited 1 as expected; policy SHA-256 was `89fd34b17ac695febf98fd9e72ed21aa606cd5fbc7345244d85ea1e4ca47b02c`. The follow-up review document was added after that clean-source check.
- Remaining immediate blockers: a fresh public GitHub REST recheck still observed `main protected=false`, no rulesets, `production protection_rules=[]` and `can_admins_bypass=true`; no setting changed. No independent reviewer/release approvers or approved account/host/risk policy is recorded. The unseeded observer still has only **1 of 4** required trading-freshness samples; observer smoke cannot promote trading. PRD-008 lacks exchange-side fencing and control of other OS users, hosts, external bots and valid keys; legacy history migration, key rotation, machine-verified reconciliation and restored-state proof remain open. PRD-020 still lacks calibrated market costs, full causality/provenance and holdout/live replay. Six reviewed Rust dependency exceptions expire **2026-10-10** and need named owners.
- Canonical evidence/findings: [PRODUCTION_READINESS_AUDIT.md](PRODUCTION_READINESS_AUDIT.md).
- Current dated score and strict-gate result: [PRODUCTION_READINESS_REVIEW_2026-09-23_FOLLOWUP.md](PRODUCTION_READINESS_REVIEW_2026-09-23_FOLLOWUP.md). The [prior review](PRODUCTION_READINESS_REVIEW_2026-09-23.md) remains historical evidence for its own code commit.
- Canonical task statuses/acceptance criteria/work log: [PRODUCTION_IMPLEMENTATION_PLAN.md](PRODUCTION_IMPLEMENTATION_PLAN.md).

## First actions for a new agent

1. Read root `AGENTS.md`, then this file, the audit verdict/findings and the implementation plan. Do not rely on memory of an earlier chat.
2. Run `git status --short --branch` and `git rev-parse HEAD`. Preserve unrelated changes. Compare current code with the audited SHA; findings and remote statuses may have changed.
3. Read the task register and latest work-log entry. Reproduce the selected defect offline before fixing it; never assume it remains unfixed.
4. Recommended next task: finish **PRD-008** identity/recovery/rotation beyond the bounded same-user/host Live Spot gate, and obtain named operator/account/host scope decisions before claiming account-wide enforcement. An independent **PRD-009 TODO** offline candidate is to reject a malformed Futures position snapshot before calculating cumulative risk and pause new entries while preserving proven reducing closes; no fix is in place. Operator risk values, durable kill state and account-wide scope still need decisions. PRD-007 needs an authorized real publisher run and PRD-001 needs reviewer/settings decisions. The active-trading observation contract remains open.
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
66/100 dated NO-GO reassessment, retain the prior 65/100 clean-commit review
and preserve the 58/100 historical audit.
```

To request planning only, replace “Continue” with “Review and propose changes for”. To choose a task, replace `PRD-008` with its task ID.

## Known environment/evidence caveats

- The current staged-candidate source gate ran locally under the declared Python 3.14 environment and passed; the strict clean-commit promotion check on `3dc13908` returned `promotion_ready=false` because all four operational artifacts were missing. See the latest plan work log and follow-up review for exact commands and counts. The earlier clean-commit source gate at `7cf7f7d4` and the 2026-09-17 audit's 1,851 passes and 53.52% coverage remain historical.
- On 2026-09-23, a fresh public GitHub REST recheck reported `main protected=false`, no repository rulesets, `production protection_rules=[]` and `can_admins_bypass=true`; administrator-only settings were unavailable and no settings changed. [The governance proposal](PRODUCTION_GOVERNANCE_PROPOSAL.md) is ready for operator review. Recheck remote state before acting.
- Required local production evidence was missing. Genuine rolling 30-day telemetry, release signing/QA, actual alert delivery, account recovery and deployment inputs cannot be fabricated by an agent.
- Python owns trading behavior; native C++/Rust/mobile are not automatically promoted by source parity. Read-only Kubernetes replicas are not trading HA.
