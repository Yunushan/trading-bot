"""Run pip-audit with the operating system's trusted certificate store."""

from __future__ import annotations

import importlib
import sys


def _enable_system_trust() -> None:
    try:
        truststore = importlib.import_module("truststore")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            'Python security dependencies are missing. Install them with: '
            'python -m pip install -e "Languages/Python[security]"'
        ) from exc
    truststore.inject_into_ssl()


def main() -> int:
    _enable_system_trust()
    audit = importlib.import_module("pip_audit._cli").audit
    result = audit()
    return 0 if result is None else int(result)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
