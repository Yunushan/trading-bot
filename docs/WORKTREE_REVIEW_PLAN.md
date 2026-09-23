# Worktree Review Plan

For a broad working tree, review changes in slices instead of as one large
patch.

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

`tool versions` is a blocking advisory: a failure makes the wrapper fail even
though it is reported separately from required checks. `risky pattern audit`
is required and blocks success on regression or high-severity findings.
`workspace hygiene`, `worktree summary`, `client dependency locks`, and `ruff
availability` are nonblocking advisories in this wrapper. Python lint remains
a required check, so missing Ruff still blocks through that check. CI also
enforces pinned runtime versions and source hygiene on clean runners.
