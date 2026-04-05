"""
Canonical service API product launcher.

This wrapper exposes the repository-level service app boundary under ``apps/``
and delegates into the canonical importable package entrypoint.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON_WORKSPACE_DIR = REPO_ROOT / "Languages" / "Python"
CANONICAL_PRODUCT_MODULE = "app.service.product_main"


def _ensure_python_workspace_on_path() -> None:
    for candidate in (REPO_ROOT, PYTHON_WORKSPACE_DIR):
        candidate_str = str(candidate)
        if candidate_str not in sys.path:
            sys.path.insert(0, candidate_str)


def main(argv: list[str] | None = None) -> int:
    _ensure_python_workspace_on_path()
    from app.service.product_main import main as service_main

    return int(service_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
