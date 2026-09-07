"""Keep LLM data and local model operations on the explicitly approved endpoint."""

from __future__ import annotations

from typing import Any


class LLMRedirectError(ValueError):
    """A redirect is not permission to contact another endpoint."""


def reject_llm_redirect(response: Any) -> None:
    if 300 <= response.status_code < 400:
        try:
            response.close()
        finally:
            # Do not echo Location or the response body: either may contain secrets.
            raise LLMRedirectError(
                f"LLM HTTP redirect ({response.status_code}) refused; configure the final approved endpoint URL."
            )
