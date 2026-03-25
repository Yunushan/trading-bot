"""
Backward-compatible import shim for the strategy engine.

New code should import from ``app.core.strategy``.
"""

from app.core.strategy import StrategyEngine

__all__ = ["StrategyEngine"]
