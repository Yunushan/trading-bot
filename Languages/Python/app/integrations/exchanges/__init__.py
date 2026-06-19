"""
Exchange integration package.

This namespace is the new home for exchange-specific adapters that were
previously placed in the flat ``app/`` module layout.
"""

from .ccxt_diagnostics import CcxtDiagnosticsConnector

__all__ = ["CcxtDiagnosticsConnector"]
