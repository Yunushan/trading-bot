# Project Structure

This repository is a multi-implementation trading-bot workspace. The intent is to keep source code stable and predictable while allowing local build outputs to stay disposable.

## Stable source directories

- `Languages/Python/`: primary end-user desktop app
- `Languages/C++/`: native Qt desktop implementation
- `Languages/Rust/`: Rust workspace with multiple desktop shells and shared crates
- `assets/`: shared icons and branding assets
- `tools/`: repo-level maintenance scripts
- `docs/`: repository and development documentation

## Generated or local-only directories

These are workspace artifacts, not canonical source:

- `build/`
- `dist/`
- `dist_enduser/`
- `.venv/`
- root-level `Trading-Bot-*.exe`

They are ignored by Git and should be treated as disposable.

## Current organization guidance

The repository is intentionally language-first today, but feature code inside each implementation should be grouped by domain where possible.

Preferred direction:

- Python GUI already has feature subpackages at `Languages/Python/app/gui/positions/`, `Languages/Python/app/gui/backtest/`, `Languages/Python/app/gui/chart/`, `Languages/Python/app/gui/code/`, `Languages/Python/app/gui/dashboard/`, `Languages/Python/app/gui/trade/`, `Languages/Python/app/gui/shared/`, and `Languages/Python/app/gui/runtime/`
- Python GUI code should trend toward feature folders such as `dashboard/`, `chart/`, `positions/`, `backtest/`, `code/`, `trade/`, `shared/`, and `runtime/`
- C++ source should trend toward `dashboard/`, `positions/`, `runtime/`, `chart/`, `backtest/`, and `net/`
- Long-form maintenance or contributor guidance should live in `docs/`, not the root README

## What should stay small at the repo root

The root should remain focused on:

- project identity
- quick-start documentation
- shared assets
- top-level tooling

If a file is mainly for contributors, maintenance, or release procedure, prefer `docs/` or `tools/`.
