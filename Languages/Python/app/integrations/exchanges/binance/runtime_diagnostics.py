from __future__ import annotations

import logging

from app.security.redaction import redact_text

LOGGER = logging.getLogger(__name__)


def report_runtime_fallback(
    owner: object,
    message: str,
    error: BaseException | None = None,
    *,
    level: str = "warning",
) -> str:
    """Report a recoverable Binance runtime failure without leaking credentials."""
    safe_message = redact_text(message)
    if error is None:
        detail = safe_message
    else:
        detail = f"{safe_message}: {type(error).__name__}: {redact_text(error)}"

    wrapper_level = "warn" if level == "warning" else level
    try:
        wrapper_logger = getattr(owner, "_log", None)
    except Exception:
        wrapper_logger = None
        LOGGER.warning("Could not inspect Binance wrapper logger", exc_info=True)

    if callable(wrapper_logger):
        try:
            wrapper_logger(detail, lvl=wrapper_level)
            return detail
        except Exception:
            LOGGER.warning("Binance wrapper logger failed while reporting: %s", detail, exc_info=True)

    log_level = getattr(logging, str(level).upper(), logging.WARNING)
    LOGGER.log(log_level, "%s", detail)
    return detail
