# Worktree Review Plan

The current working tree is intentionally broad. Review it in slices instead of
as one large patch.

Run:

```bash
python tools/summarize_worktree_changes.py
```

Recommended review order:

1. `ci-tooling`: version pins, workflow checks, hygiene and verification tools.
2. `python-settings`: config validation and default settings.
3. `service-api`: API auth, config persistence, schemas, and runtime metadata.
4. `exchange-order-safety`: order audit, live guards, futures submit/close flows.
5. `llm`: providers, advisory boundary, local model management.
6. `web-dashboard`: browser status/config rendering and token handling.
7. `mobile-client`: thin client contract and deterministic UI logic.
8. `tests`: regression coverage for all changed surfaces.
9. `docs`: operator and architecture documentation.

Before final review, run:

```bash
python tools/verify_all.py
```

`tool versions`, `workspace hygiene`, `risky pattern audit`, and `ruff
availability` are advisory in that wrapper because they depend on the local
machine setup or provide triage counts instead of hard failure policy. CI
enforces the pinned runtime versions and source hygiene on clean runners.
