from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets

from ..chart.chart_embed import (
    _DEFAULT_WEB_UA,
    _configure_tradingview_webengine_env,
    _native_chart_host_prewarm_enabled,
    _webengine_embed_unavailable_reason,
)


class _LazyWebEmbed(QtWidgets.QWidget):
    def __init__(self, url: str, parent=None) -> None:
        super().__init__(parent)
        self._url = str(url or "").strip()
        self._view = None
        self._loaded_once = False
        self._native_primed = False
        self._cursor_filter_installed = False

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._stack = QtWidgets.QStackedWidget()
        layout.addWidget(self._stack)

        self._fallback_label = QtWidgets.QLabel("Loading web view...")
        self._fallback_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._fallback_label.setWordWrap(True)
        self._stack.addWidget(self._fallback_label)

    def prime_native_host(self) -> None:
        if self._native_primed:
            return
        if not _native_chart_host_prewarm_enabled():
            return
        self._native_primed = True
        for widget in (self, self._stack):
            try:
                widget.setAttribute(QtCore.Qt.WidgetAttribute.WA_NativeWindow, True)
            except Exception:
                pass
            try:
                widget.winId()
            except Exception:
                pass

    def showEvent(self, event: QtGui.QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        self.prime_native_host()
        if self._loaded_once:
            return
        self._loaded_once = True
        self._ensure_view()

    def set_url(self, url: str) -> None:
        url = str(url or "").strip()
        if not url:
            return
        self._url = url
        if self._view is not None:
            try:
                self._view.load(QtCore.QUrl(self._url))
            except Exception:
                pass

    def reload(self) -> None:
        if self._view is None:
            return
        try:
            self._view.reload()
        except Exception:
            pass

    def _set_fallback_text(self, text: str) -> None:
        self._fallback_label.setText(text)
        try:
            self._stack.setCurrentWidget(self._fallback_label)
        except Exception:
            pass

    def _ensure_view(self) -> None:
        reason = _webengine_embed_unavailable_reason()
        if reason:
            self._set_fallback_text(f"{reason}\n\nUse 'Open in Browser' to view the heatmap.")
            return
        self.prime_native_host()
        try:
            host_window = self.window()
            start_guard = getattr(host_window, "_start_webengine_close_guard", None)
            if callable(start_guard):
                start_guard()
        except Exception:
            pass
        try:
            _configure_tradingview_webengine_env()
        except Exception:
            pass
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
        except Exception as exc:
            self._set_fallback_text(f"QtWebEngine unavailable: {exc}")
            return

        view = QWebEngineView(self)
        self._configure_view(view)
        self._view = view
        self._stack.insertWidget(0, view)
        self._stack.setCurrentWidget(view)
        try:
            view.installEventFilter(self)
            self._cursor_filter_installed = True
        except Exception:
            self._cursor_filter_installed = False
        if self._url:
            try:
                view.load(QtCore.QUrl(self._url))
            except Exception:
                pass

    def _configure_view(self, view) -> None:
        try:
            view.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.NoContextMenu)
        except Exception:
            pass
        try:
            settings = view.settings()
            settings.setAttribute(settings.WebAttribute.LocalStorageEnabled, True)
            settings.setAttribute(settings.WebAttribute.JavascriptCanOpenWindows, False)
            settings.setAttribute(settings.WebAttribute.JavascriptCanCloseWindows, False)
            settings.setAttribute(settings.WebAttribute.HyperlinkAuditingEnabled, False)
            if hasattr(settings.WebAttribute, "Accelerated2dCanvasEnabled"):
                settings.setAttribute(settings.WebAttribute.Accelerated2dCanvasEnabled, True)
            if hasattr(settings.WebAttribute, "WebGLEnabled"):
                settings.setAttribute(settings.WebAttribute.WebGLEnabled, True)
        except Exception:
            pass
        try:
            profile = view.page().profile()
            profile.setHttpUserAgent(_DEFAULT_WEB_UA)
        except Exception:
            pass

    def eventFilter(self, obj, event):  # noqa: N802
        if obj is getattr(self, "_view", None):
            try:
                if event.type() == QtCore.QEvent.Type.CursorChange:
                    shape = self._view.cursor().shape()
                    if shape in {
                        QtCore.Qt.CursorShape.PointingHandCursor,
                        QtCore.Qt.CursorShape.OpenHandCursor,
                        QtCore.Qt.CursorShape.ClosedHandCursor,
                    }:
                        self._view.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
            except Exception:
                pass
        return super().eventFilter(obj, event)
