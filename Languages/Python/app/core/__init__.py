"""
Internal trading-domain implementation namespace.

The canonical reusable package boundary now lives at ``trading_core``.
Keep ``app.core`` for the existing monolith/runtime wiring while external
consumers and new shared code migrate to the public package surface.
"""

__all__ = ["backtest", "indicators", "positions", "strategy"]
