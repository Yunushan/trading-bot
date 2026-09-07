"""Offline order-intent storage administration; never contacts an exchange."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Languages/Python"))

from app.integrations.exchanges.binance.orders.order_intent_admin import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
