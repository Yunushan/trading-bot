"""
Deprecated compatibility service entrypoint.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    _PYTHON_ROOT = Path(__file__).resolve().parents[2]
    if str(_PYTHON_ROOT) not in sys.path:
        sys.path.insert(0, str(_PYTHON_ROOT))
    from app.entrypoint_contract import SERVICE_ENTRYPOINT_CONTRACT
    from app.service.product_main import main as product_main
else:
    from ..entrypoint_contract import SERVICE_ENTRYPOINT_CONTRACT
    from .product_main import main as product_main

IS_DEPRECATED_COMPATIBILITY_ENTRYPOINT = True
COMPATIBILITY_NOTICE = SERVICE_ENTRYPOINT_CONTRACT.compatibility_notice()


def main(argv: list[str] | None = None) -> int:
    return int(product_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
