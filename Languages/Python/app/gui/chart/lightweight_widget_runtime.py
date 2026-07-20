from __future__ import annotations

import html as _html
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from PyQt6 import QtCore, QtGui, QtWidgets

from ..shared.silent_webengine_page import SilentWebEnginePage
from . import lightweight_widget_assets

try:
    from PyQt6.QtWebEngineCore import QWebEnginePage
    from PyQt6.QtWebEngineWidgets import QWebEngineView
except Exception as exc:  # pragma: no cover - environment without WebEngine
    QWebEngineView = None  # type: ignore[assignment]
    QWebEnginePage = None  # type: ignore[assignment]
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


_DEFAULT_UA = os.environ.get(
    "BOT_WEBENGINE_UA",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
)


def _resolve_log_path() -> Path:
    override = str(os.environ.get("BOT_CHART_DEBUG_LOG", "") or "").strip()
    if override:
        return Path(override)
    return (Path(os.getenv("TEMP") or ".").resolve() / "binance_chart_debug.log")


_LOG_PATH = _resolve_log_path()
_HAND_CURSOR_SHAPES = {
    QtCore.Qt.CursorShape.PointingHandCursor,
    QtCore.Qt.CursorShape.OpenHandCursor,
    QtCore.Qt.CursorShape.ClosedHandCursor,
}
_WEBENGINE_VIEW_BASE = QWebEngineView if QWebEngineView is not None else QtWidgets.QWidget


def _log_chart_event(message: str) -> None:
    try:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        ts = "unknown-time"
    try:
        with open(_LOG_PATH, "a", encoding="utf-8", errors="ignore") as fh:
            fh.write(f"[{ts}] {message}\n")
    except Exception:
        return


def _log_lightweight_exception(context: str, exc: BaseException) -> None:
    message = str(exc).replace("\n", " ")
    _log_chart_event(f"LightweightChartWidget suppressed exception context={context} error={type(exc).__name__}: {message}")


def _clear_hand_override_cursor() -> None:
    try:
        override = QtGui.QGuiApplication.overrideCursor()
    except Exception:
        return
    while override is not None:
        try:
            if override.shape() not in _HAND_CURSOR_SHAPES:
                return
            QtGui.QGuiApplication.restoreOverrideCursor()
            override = QtGui.QGuiApplication.overrideCursor()
        except Exception:
            return


def _refresh_host_window_protection(widget) -> None:
    try:
        host_window = widget.window()
    except Exception:
        host_window = None
    if host_window is None:
        return
    try:
        start_guard = getattr(host_window, "_start_webengine_close_guard", None)
        if callable(start_guard):
            start_guard()
    except Exception as exc:
        _log_lightweight_exception("refresh_host_window_protection", exc)


class LightweightChartWidget(_WEBENGINE_VIEW_BASE):  # type: ignore[misc]
    """
    QWebEngine wrapper around TradingView Lightweight Charts.
    """

    ready = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        if QWebEngineView is None:  # pragma: no cover - defensive
            raise RuntimeError(f"QtWebEngine is unavailable: {_IMPORT_ERROR}")
        super().__init__(parent)
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.NoContextMenu)
        try:
            self.setMouseTracking(True)
        except Exception as exc:
            _log_lightweight_exception("set_mouse_tracking", exc)
        try:
            if QWebEnginePage is not None:
                self.setPage(_DebugWebEnginePage(self))
        except Exception as exc:
            _log_lightweight_exception("install_debug_webengine_page", exc)
        try:
            self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        except Exception as exc:
            _log_lightweight_exception("set_scrollbar_policy", exc)
        try:
            settings = self.settings()
            settings.setAttribute(settings.WebAttribute.LocalStorageEnabled, True)
            settings.setAttribute(settings.WebAttribute.JavascriptEnabled, True)
            settings.setAttribute(settings.WebAttribute.Accelerated2dCanvasEnabled, True)
            settings.setAttribute(settings.WebAttribute.WebGLEnabled, True)
            settings.setAttribute(settings.WebAttribute.HyperlinkAuditingEnabled, False)
            local_remote = getattr(settings.WebAttribute, "LocalContentCanAccessRemoteUrls", None)
            if local_remote is not None:
                settings.setAttribute(local_remote, True)
            local_file = getattr(settings.WebAttribute, "LocalContentCanAccessFileUrls", None)
            if local_file is not None:
                settings.setAttribute(local_file, True)
            settings.setAttribute(settings.WebAttribute.JavascriptCanOpenWindows, False)
            settings.setAttribute(settings.WebAttribute.JavascriptCanCloseWindows, False)
        except Exception as exc:
            _log_lightweight_exception("configure_webengine_settings", exc)
        try:
            profile = self.page().profile()
            profile.setHttpUserAgent(_DEFAULT_UA)
        except Exception as exc:
            _log_lightweight_exception("set_http_user_agent", exc)
        self._rendered = False
        self._page_ready = False
        self._pending_payload: dict | None = None
        try:
            self.loadFinished.connect(self._on_load_finished)
        except Exception as exc:
            _log_lightweight_exception("connect_load_finished", exc)
        try:
            self.loadStarted.connect(self._on_load_started)
        except Exception as exc:
            _log_lightweight_exception("connect_load_started", exc)
        try:
            page = self.page()
            if hasattr(page, "renderProcessTerminated"):
                page.renderProcessTerminated.connect(self._on_render_process_terminated)
        except Exception as exc:
            _log_lightweight_exception("connect_render_process_terminated", exc)
        _log_chart_event("LightweightChartWidget init")
        self._html_path = lightweight_widget_assets._resolve_lightweight_html_path()

    def set_chart_data(self, payload: dict) -> None:
        if not payload:
            return
        if not self._rendered:
            self._pending_payload = payload
            self._render(payload)
            return
        self._pending_payload = payload
        if self._page_ready:
            self._apply_payload(payload)

    def show_message(self, message: str, color: str = "#d1d4dc") -> None:
        safe_msg = _html.escape(str(message or ""))
        safe_color = _html.escape(str(color or "#d1d4dc"))
        html = f"""<!DOCTYPE html>
<html><head><meta charset='utf-8'><style>
html, body {{ margin:0; padding:0; width:100%; height:100%; background-color:#0b0e11; }}
.msg {{ display:flex; width:100%; height:100%; align-items:center; justify-content:center;
        color:{safe_color}; font-family:-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
</style></head><body><div class='msg'>{safe_msg}</div></body></html>"""
        self._rendered = False
        self._page_ready = False
        self._pending_payload = None
        self.setHtml(html, QtCore.QUrl("about:blank"))

    def createWindow(self, _type):  # noqa: N802
        return None

    def event(self, event):
        try:
            if event.type() in {
                QtCore.QEvent.Type.CursorChange,
                QtCore.QEvent.Type.MouseMove,
                QtCore.QEvent.Type.Leave,
                QtCore.QEvent.Type.FocusOut,
                QtCore.QEvent.Type.Hide,
            }:
                _clear_hand_override_cursor()
                shape = self.cursor().shape()
                if shape in _HAND_CURSOR_SHAPES:
                    self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
        except Exception as exc:
            _log_lightweight_exception("event_cursor_cleanup", exc)
        return super().event(event)

    def _render(self, payload: dict | None = None) -> None:
        if self._rendered:
            return
        self._rendered = True
        html = lightweight_widget_assets._build_lightweight_chart_html(payload, _log_chart_event)
        html_path = getattr(self, "_html_path", None)
        if isinstance(html_path, Path):
            try:
                html_path.write_text(html, encoding="utf-8", errors="ignore")
                self._page_ready = False
                self.load(QtCore.QUrl.fromLocalFile(str(html_path)))
                _log_chart_event(f"LightweightChartWidget loadHtmlFile path={html_path}")
                return
            except Exception as exc:
                _log_chart_event(f"LightweightChartWidget loadHtmlFile failed: {exc}")
        self.setHtml(html, lightweight_widget_assets._BASE_URL)

    def _on_load_started(self) -> None:
        try:
            _log_chart_event("LightweightChartWidget loadStarted")
        except Exception as exc:
            _log_lightweight_exception("load_started_log", exc)

    def _on_load_finished(self, ok: bool) -> None:
        self._page_ready = bool(ok)
        try:
            _log_chart_event(f"LightweightChartWidget loadFinished ok={int(bool(ok))}")
        except Exception as exc:
            _log_lightweight_exception("load_finished_log", exc)
        if not self._page_ready:
            return
        _refresh_host_window_protection(self)
        pending = self._pending_payload
        if pending:
            self._apply_payload(pending)
        try:
            self.ready.emit()
        except Exception as exc:
            _log_lightweight_exception("ready_signal_emit", exc)

    def _on_render_process_terminated(self, *_args) -> None:
        try:
            _log_chart_event(f"LightweightChartWidget renderProcessTerminated args={_args}")
        except Exception as exc:
            _log_lightweight_exception("render_process_terminated_log", exc)
        try:
            self.show_message("Lightweight chart crashed. Try disabling WebEngine charts.", color="#f75467")
        except Exception as exc:
            _log_lightweight_exception("render_process_terminated_message", exc)

    def _apply_payload(self, payload: dict) -> None:
        if not payload or not self._page_ready:
            return
        try:
            payload_json = json.dumps(payload, ensure_ascii=True)
        except Exception:
            return
        try:
            _log_chart_event(
                "LightweightChartWidget apply_payload "
                f"candles={len(payload.get('candles') or [])} "
                f"overlays={len(payload.get('overlays') or [])} "
                f"panes={len(payload.get('panes') or [])}"
            )
        except Exception as exc:
            _log_lightweight_exception("apply_payload_log", exc)
        try:
            self.page().runJavaScript(f"window.__lw_apply_payload({payload_json});")
        except Exception as exc:
            _log_lightweight_exception("apply_payload_javascript", exc)


_DebugWebEnginePageBase = SilentWebEnginePage if SilentWebEnginePage is not None else QWebEnginePage


if _DebugWebEnginePageBase is not None:
    class _DebugWebEnginePage(_DebugWebEnginePageBase):  # pragma: no cover - logging only
        def javaScriptConsoleMessage(self, level, message, line_number, source_id):
            try:
                _log_chart_event(
                    f"Lightweight JS console level={int(level)} line={int(line_number)} source={source_id} msg={message}"
                )
            except Exception as exc:
                _log_lightweight_exception("javascript_console_log", exc)
            try:
                super().javaScriptConsoleMessage(level, message, line_number, source_id)
            except Exception as exc:
                _log_lightweight_exception("javascript_console_super", exc)
