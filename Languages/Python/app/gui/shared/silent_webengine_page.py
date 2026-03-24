from __future__ import annotations

try:
    from PyQt6.QtWebEngineCore import QWebEnginePage
except Exception:  # pragma: no cover - environment without WebEngine
    QWebEnginePage = None  # type: ignore[assignment]


if QWebEnginePage is not None:
    class SilentWebEnginePage(QWebEnginePage):
        """Suppress modal JavaScript dialogs from embedded web views."""

        def javaScriptAlert(self, securityOrigin, msg) -> None:  # noqa: N802, ANN001
            return None

        def javaScriptConfirm(self, securityOrigin, msg) -> bool:  # noqa: N802, ANN001
            # Allow unload/confirm flows to continue silently instead of flashing
            # a modal Chromium dialog when the user changes tabs.
            return True

        def javaScriptPrompt(self, securityOrigin, msg, defaultValue):  # noqa: N802, ANN001
            return False, defaultValue
else:
    SilentWebEnginePage = None  # type: ignore[assignment]
