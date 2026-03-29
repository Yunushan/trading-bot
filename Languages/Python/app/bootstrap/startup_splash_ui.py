from __future__ import annotations

import math
import os
import sys
from pathlib import Path

from .startup_ui_shared import APP_DISPLAY_NAME, _PROJECT_ROOT


def _resolve_splash_logo_pixmap(QtGui):  # noqa: N803
    candidates: list[Path] = []
    env_logo = str(os.environ.get("BOT_SPLASH_LOGO") or os.environ.get("BINANCE_BOT_SPLASH") or "").strip()
    if env_logo:
        candidates.append(Path(env_logo).expanduser())

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        meipass_path = Path(meipass)
        candidates.extend(
            [
                meipass_path / "assets" / "crypto_forex_logo.png",
                meipass_path / "assets" / "crypto_forex_logo.ico",
                meipass_path / "crypto_forex_logo.png",
                meipass_path / "crypto_forex_logo.ico",
            ]
        )

    try:
        exe_dir = Path(sys.executable).resolve().parent
    except Exception:
        exe_dir = None
    if exe_dir is not None:
        candidates.extend(
            [
                exe_dir / "assets" / "crypto_forex_logo.png",
                exe_dir / "assets" / "crypto_forex_logo.ico",
                exe_dir / "crypto_forex_logo.png",
                exe_dir / "crypto_forex_logo.ico",
            ]
        )

    root_assets = _PROJECT_ROOT / "assets"
    candidates.extend(
        [
            root_assets / "crypto_forex_logo.png",
            root_assets / "crypto_forex_logo.ico",
        ]
    )

    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if not candidate.is_file():
            continue
        try:
            pixmap = QtGui.QPixmap(str(candidate))
            if pixmap is not None and not pixmap.isNull():
                return pixmap
        except Exception:
            pass
        try:
            icon = QtGui.QIcon(str(candidate))
            if icon is not None and not icon.isNull():
                pixmap = icon.pixmap(96, 96)
                if pixmap is not None and not pixmap.isNull():
                    return pixmap
        except Exception:
            pass
    return None


class _SplashScreen:
    def __init__(self, app, QtCore, QtGui, QWidget, *, host_widget=None):  # noqa: N803
        self._app = app
        self._QtCore = QtCore
        self._QtGui = QtGui
        self._widget = None
        self._spinner_angle = 0
        self._status_text = "Loading…"
        self._logo_pixmap = None
        self._timer = None
        try:
            self._logo_pixmap = _resolve_splash_logo_pixmap(QtGui)
            if self._logo_pixmap is not None and self._logo_pixmap.isNull():
                self._logo_pixmap = None
        except Exception:
            self._logo_pixmap = None
        try:
            splash_w, splash_h = 420, 320
            splash_topmost = str(os.environ.get("BOT_STARTUP_SPLASH_TOPMOST", "") or "").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
            if host_widget is not None:
                try:
                    host_rect = host_widget.rect()
                except Exception:
                    host_rect = QtCore.QRect(0, 0, 1920, 1080)
                splash = _SplashWidget(host_widget)
            else:
                screen = QtGui.QGuiApplication.primaryScreen()
                screen_geo = screen.geometry() if screen else QtCore.QRect(0, 0, 1920, 1080)
                splash_flags = (
                    QtCore.Qt.WindowType.SplashScreen
                    | QtCore.Qt.WindowType.FramelessWindowHint
                    | QtCore.Qt.WindowType.NoDropShadowWindowHint
                )
                if splash_topmost:
                    splash_flags |= QtCore.Qt.WindowType.WindowStaysOnTopHint
                splash = _SplashWidget(None, splash_flags)
            splash.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            splash.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            try:
                splash.setWindowTitle("")
            except Exception:
                pass
            splash.setFixedSize(splash_w, splash_h)
            try:
                rounded_path = QtGui.QPainterPath()
                rounded_path.addRoundedRect(QtCore.QRectF(0, 0, splash_w, splash_h), 24, 24)
                splash.setMask(QtGui.QRegion(rounded_path.toFillPolygon().toPolygon()))
            except Exception:
                pass
            if host_widget is not None:
                x = (host_widget.rect().width() - splash_w) // 2
                y = (host_widget.rect().height() - splash_h) // 2
                splash.move(max(0, x), max(0, y))
            else:
                x = screen_geo.x() + (screen_geo.width() - splash_w) // 2
                y = screen_geo.y() + (screen_geo.height() - splash_h) // 2
                splash.move(x, y)
            splash._splash_ref = self
            self._widget = splash
            splash.show()
            try:
                splash.raise_()
            except Exception:
                pass
            app.processEvents(QtCore.QEventLoop.ProcessEventsFlag.AllEvents, 30)
            if sys.platform == "win32" and host_widget is None:
                try:
                    import ctypes
                    import ctypes.wintypes as wintypes

                    user32 = ctypes.windll.user32
                    hwnd = wintypes.HWND(int(splash.winId()))
                    GWL_EXSTYLE = -20
                    WS_EX_LAYERED = 0x00080000
                    WS_EX_TRANSPARENT = 0x00000020
                    get_style = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
                    set_style = getattr(user32, "SetWindowLongPtrW", None) or user32.SetWindowLongW
                    exstyle = int(get_style(hwnd, GWL_EXSTYLE))
                    set_style(hwnd, GWL_EXSTYLE, exstyle | WS_EX_LAYERED | WS_EX_TRANSPARENT)
                except Exception:
                    pass
            timer = QtCore.QTimer()
            timer.setInterval(40)
            timer.timeout.connect(self._tick)
            timer.start()
            self._timer = timer
        except Exception:
            self._widget = None

    def _tick(self) -> None:
        self._spinner_angle = (self._spinner_angle + 8) % 360
        if self._widget is not None:
            try:
                self._widget.update()
            except Exception:
                pass

    def set_status(self, text: str) -> None:
        self._status_text = text
        if self._widget is not None:
            try:
                self._widget.update()
                self._app.processEvents(self._QtCore.QEventLoop.ProcessEventsFlag.AllEvents, 20)
            except Exception:
                pass

    def close(self) -> None:
        if self._timer is not None:
            try:
                self._timer.stop()
            except Exception:
                pass
            self._timer = None
        if self._widget is not None:
            try:
                self._widget.hide()
                self._widget.deleteLater()
            except Exception:
                pass
            self._widget = None


class _SplashWidget:
    pass


def _make_splash_widget_class(QWidget, QtCore, QtGui):  # noqa: N803
    class SplashWidget(QWidget):
        def paintEvent(self, event):  # noqa: N802
            splash_ref = getattr(self, "_splash_ref", None)
            if splash_ref is None:
                return
            try:
                painter = QtGui.QPainter(self)
                painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
                w, h = self.width(), self.height()
                panel_rect = QtCore.QRectF(0, 0, w, h)
                panel_path = QtGui.QPainterPath()
                panel_path.addRoundedRect(panel_rect, 24, 24)
                painter.fillPath(panel_path, QtGui.QColor(16, 20, 27, 235))
                border_pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 22))
                border_pen.setWidthF(1.0)
                painter.setPen(border_pen)
                painter.drawPath(panel_path)
                title = APP_DISPLAY_NAME
                subtitle = splash_ref._status_text or "Loading…"
                y = 34
                if splash_ref._logo_pixmap is not None:
                    logo = splash_ref._logo_pixmap.scaled(
                        84,
                        84,
                        QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                        QtCore.Qt.TransformationMode.SmoothTransformation,
                    )
                    logo_x = (w - logo.width()) // 2
                    painter.drawPixmap(logo_x, y, logo)
                    y += logo.height() + 20
                painter.setPen(QtGui.QColor("#f8fafc"))
                title_font = QtGui.QFont("Segoe UI", 18)
                title_font.setWeight(QtGui.QFont.Weight.DemiBold)
                painter.setFont(title_font)
                painter.drawText(
                    QtCore.QRectF(24, y, w - 48, 32),
                    int(QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignVCenter),
                    title,
                )
                y += 40
                painter.setPen(QtGui.QColor("#94a3b8"))
                body_font = QtGui.QFont("Segoe UI", 10)
                painter.setFont(body_font)
                painter.drawText(
                    QtCore.QRectF(24, y, w - 48, 24),
                    int(QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignVCenter),
                    subtitle,
                )
                spinner_y = h - 74
                spinner_x = w // 2
                radius = 14
                for i in range(12):
                    alpha = int(25 + (230 * ((i + 1) / 12.0)))
                    color = QtGui.QColor(59, 130, 246, alpha)
                    painter.setPen(QtCore.Qt.PenStyle.NoPen)
                    painter.setBrush(color)
                    angle = math.radians((splash_ref._spinner_angle + i * 30) % 360)
                    dx = math.cos(angle) * radius
                    dy = math.sin(angle) * radius
                    painter.drawEllipse(QtCore.QPointF(spinner_x + dx, spinner_y + dy), 3.0, 3.0)
            except Exception:
                pass

    global _SplashWidget
    _SplashWidget = SplashWidget
    return SplashWidget
