# Contributing

This repository is a multi-implementation trading workspace with one primary user-facing path today: the Python desktop and service code under `Languages/Python/`.

Use this document for contribution workflow, validation expectations, and change-scope rules.

## Before you start

- Read [README.md](README.md) for the current product scope and support status.
- Read [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md) before moving files or introducing new modules.
- Read [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for maintenance conventions.
- Keep changes scoped to one concern when possible. Avoid mixing packaging, refactors, and feature work in one pull request.

## Local setup

From the repository root, check the declared runtime versions and preview the
full contributor bootstrap:

```bash
python tools/bootstrap_local_dev.py --dry-run
```

Primary Python workspace:

```bash
cd Languages/Python
python -m pip install --upgrade pip
python -m pip install -e ".[desktop,service,dev]"
```

If `python` is not the declared interpreter, check the target command before
installing into it:

```powershell
python tools/check_local_tool_versions.py --strict --skip-node --python-command "python"
```

Or run the full contributor bootstrap from the repository root after Python
and Node match `.python-version` and `.node-version`:

```bash
python tools/bootstrap_local_dev.py
```

When more than one Python version is installed, target the declared interpreter
explicitly instead of relying on the active shell `python`:

```powershell
python tools/bootstrap_local_dev.py --python-command "python" --dry-run
python tools/bootstrap_local_dev.py --python-command "python"
```

Compatibility install commands still work:

```bash
pip install -r requirements.txt
pip install -r requirements.service.txt
```

Optional workspaces:

- `Languages/Rust/` for Rust shells and shared crates
- `Languages/C++/` for the native Qt preview path

## Validation

Run the checks that match the area you changed.

Python boundary checks:

```bash
cd Languages/Python
python -m ruff check --config pyproject.toml .
python tools/check_dependency_metadata.py
python -m mypy --config-file pyproject.toml
python tools/run_python_tests.py --runner pytest
python ../../tools/check_python_sources_compile.py app trading_core main.py tools
```

Release or packaging preflight from the repository root:

```bash
python tools/release_smoke.py --skip-full-tests --manual-smoke-mode fast
```

When validating with a specific Python install:

```powershell
python tools/release_smoke.py --python-command "python" --skip-full-tests --manual-smoke-mode fast
```

Rust:

```bash
cd Languages/Rust
cargo check --workspace
```

C++:

```bash
cmake -S Languages/C++ -B build/binance_cpp
cmake --build build/binance_cpp
```

If you touch docs, commands, release flow, API behavior, or public entrypoints, update the relevant documentation in the same change.

## Change rules

- Do not commit generated artifacts such as `build/`, `dist_enduser/`, `.venv/`, `target/`, or root-level executables.
- Do not commit API keys, tokens, account data, or screenshots containing secrets.
- Do not introduce new compatibility wrappers unless there is a clear deprecation plan.
- Prefer canonical import paths over legacy shim modules.
- Keep repo-root additions rare. Contributor and maintenance material should usually live in `docs/`, `.github/`, or `tools/`.
- When changing runtime behavior, add or update automated tests where practical.
- When changing public routes, payloads, or service behavior, update [docs/SERVICE_API.md](docs/SERVICE_API.md).
- When changing packaging or release expectations, update [docs/RELEASES.md](docs/RELEASES.md).
- When changing support claims, update [docs/SUPPORT_MATRIX.md](docs/SUPPORT_MATRIX.md).

## Pull requests

A good pull request for this repo should include:

- a short problem statement
- the implementation approach and affected areas
- validation commands you ran
- any follow-up work or known limits

Keep pull requests reviewable. Large structural changes are acceptable, but they should still be organized into coherent commits and a clear migration path.

## Review standard

Reviews should prioritize:

- behavior regressions
- production and operational risk
- API and packaging stability
- test coverage gaps
- structure drift that makes the repo harder to navigate

Style-only churn is low value unless it directly supports maintainability or a planned migration.

## Documentation expectations

If a change affects how contributors work, how users launch the app, or how releases are produced, update documentation in the same pull request.

At minimum, consider:

- [README.md](README.md)
- [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md)
- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)
- [docs/RELEASES.md](docs/RELEASES.md)
- [docs/SERVICE_API.md](docs/SERVICE_API.md)
