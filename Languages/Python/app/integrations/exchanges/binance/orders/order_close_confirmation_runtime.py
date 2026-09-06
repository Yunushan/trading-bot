"""Bounded read-only resolution of a submitted futures market order, never a resubmit."""
from __future__ import annotations

import time

from app.security.redaction import redact_text
from app.settings.live_safety import LiveTradingSafetyError

from .order_intent_runtime import _intent_record, _validate_reconciliation_response, reconcile_order_intent


CLOSE_QUERY_ATTEMPTS = 3
CLOSE_QUERY_INTERVAL_SECONDS = 0.1


def confirm_market_order(self, params: dict, response: object, *, error: str = "") -> tuple[dict, bool]:
    best: dict | None = None
    query_error = ""
    mark_accepted = getattr(self, "_mark_order_intent_accepted", None)
    mark_unknown = getattr(self, "_mark_order_intent_unknown", None)
    try:
        record = _intent_record(params, market="futures", source="market-confirmation")
        state, _status, _order_id = _validate_reconciliation_response(record, response)
        if not isinstance(response, dict):
            raise ValueError("Order response must be an object")
        best = dict(response)
    except (TypeError, ValueError, LiveTradingSafetyError) as exc:
        error = error or redact_text(exc)
        if callable(mark_unknown):
            mark_unknown(params, error=error)
    else:
        if callable(mark_accepted):
            mark_accepted(params, via="primary", result=best)
        if state != "unknown":
            return best, False

    if callable(getattr(self, "_query_order_intent_exchange", None)):
        for attempt in range(CLOSE_QUERY_ATTEMPTS):
            if attempt:
                time.sleep(CLOSE_QUERY_INTERVAL_SECONDS)
            observed = reconcile_order_intent(self, params["newClientOrderId"], include_execution=True)
            candidate = observed.get("order_response")
            if observed.get("reconciled") and isinstance(candidate, dict):
                best = candidate
                if observed.get("state") != "unknown":
                    return best, True
            elif observed.get("error"):
                query_error = str(observed["error"])
    if best is not None:
        return best, False
    detail = "; ".join(part for part in (error, query_error) if part)
    raise LiveTradingSafetyError(f"Order execution remains unconfirmed; reconciliation required: {redact_text(detail)}")
