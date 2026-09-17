# Start here: production-readiness work

This file makes the work resumable in a new chat **without the old conversation**. Use the same repository checkout, or carry these versioned documents to another machine. They are ordinary local files; until committed/pushed they are available only where these working-tree changes exist.

## Current checkpoint

- Audit date: **2026-09-17**.
- Audited source: `e574dae633d2186b8af4af1013076ff91f778bb9` on `main`.
- Score: **58/100 for unattended real-money production; NO-GO**. This is not a profitability score or a score for every possible deployment scope.
- Delivered: deep audit, verification ledger, prioritized implementation backlog, this handoff, repository navigation pointers.
- Product fixes in this audit: **none**. No live orders, deployments, remote settings or credentials changed. Documentation does not close findings.
- Canonical evidence/findings: [PRODUCTION_READINESS_AUDIT.md](PRODUCTION_READINESS_AUDIT.md).
- Canonical task statuses/acceptance criteria/work log: [PRODUCTION_IMPLEMENTATION_PLAN.md](PRODUCTION_IMPLEMENTATION_PLAN.md).

## First actions for a new agent

1. Read root `AGENTS.md`, then this file, the audit verdict/findings and the implementation plan. Do not rely on memory of an earlier chat.
2. Run `git status --short --branch` and `git rev-parse HEAD`. Preserve unrelated changes. Compare current code with the audited SHA; findings and remote statuses may have changed.
3. Read the task register and latest work-log entry. Reproduce the selected defect offline before fixing it; never assume it remains unfixed.
4. Recommended next task: **PRD-002 (LLM credential/destination isolation)**. Independent parallel tasks: **PRD-004 (ccxt protected fields)** and **PRD-006 (deployment probe integration)**. PRD-005 live-data validity is also urgent. PRD-001 needs owner/settings decisions.
5. Follow the chosen task's dependencies and acceptance criteria. Finish a coherent patch with regression tests. Do not weaken safety/tests, hand-edit generated parity, make speculative broad rewrites, or promote unsupported targets.
6. Update the task register/work log and this checkpoint with the actual tests, SHA/PR, remaining blockers and next task before ending the turn. Keep the historical audit baseline intact; add dated reassessments.

## Ready-to-paste prompt

```text
Continue this repository's production-readiness implementation.
Read AGENTS.md, docs/PRODUCTION_HANDOFF.md,
docs/PRODUCTION_READINESS_AUDIT.md and docs/PRODUCTION_IMPLEMENTATION_PLAN.md.
Inspect current git state and the latest work log; preserve unrelated changes.
Implement the next ready high-priority task (initial recommendation PRD-002),
reproduce the issue, add regression tests and run the appropriate gates.
Use independent agents for bounded parallel work when useful.
Do not place orders, deploy, change live risk limits, expose secrets, or change
GitHub settings without the necessary explicit authorization.
Update the task register and handoff with evidence and the next action.
Do not claim production readiness from green CI or documentation alone.
```

To request planning only, replace “Implement” with “Review and propose changes for”. To choose a task, replace `PRD-002` with its task ID.

## Known environment/evidence caveats

- Audited local tools: Python 3.14.7, Node 26.8.2. Active Python lacked full desktop/service/dev test dependencies. Use an isolated declared-runtime environment; do not silently install into the user's global interpreter.
- Full-suite evidence was **remote**: 1,851 passed, 53.52% line coverage at the audited SHA. Targeted local suites passed 32 cases. Do not report those as a fresh run in the new chat.
- Main CI/CodeQL were green; platform run `35202563575` was still in progress at the audit snapshot. Main protection was false with zero effective branch rules. Recheck, do not treat these as live facts.
- Required local production evidence was missing. Genuine rolling 30-day telemetry, release signing/QA, actual alert delivery, account recovery and deployment inputs cannot be fabricated by an agent.
- Python owns trading behavior; native C++/Rust/mobile are not automatically promoted by source parity. Read-only Kubernetes replicas are not trading HA.
