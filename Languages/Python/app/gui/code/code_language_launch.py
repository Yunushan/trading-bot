from __future__ import annotations

import concurrent.futures
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from PyQt6 import QtCore, QtGui, QtWidgets

from ..shared.app_icon import load_app_icon

_LANGUAGE_SWITCH_DISPLAY_NAME = str(os.environ.get("BOT_TASKBAR_DISPLAY_NAME") or "Trading Bot").strip() or "Trading Bot"


def _language_switch_logo_pixmap() -> QtGui.QPixmap | None:
    try:
        icon = load_app_icon()
    except Exception:
        icon = QtGui.QIcon()
    if icon.isNull():
        return None
    for size in (72, 96, 128):
        try:
            pixmap = icon.pixmap(size, size)
        except Exception:
            continue
        if pixmap is not None and not pixmap.isNull():
            return pixmap
    return None


class LanguageSwitchSplash:
    def __init__(self, status_text: str = "Loading...") -> None:
        self._widget: QtWidgets.QWidget | None = None
        self._spinner_angle = 0
        self._status_text = str(status_text or "Loading...")
        self._logo_pixmap = _language_switch_logo_pixmap()
        self._timer: QtCore.QTimer | None = None

        try:
            screen = QtGui.QGuiApplication.primaryScreen()
            screen_geo = screen.geometry() if screen else QtCore.QRect(0, 0, 1920, 1080)

            class _Widget(QtWidgets.QWidget):
                def paintEvent(inner_self, event):  # noqa: N802, ANN001
                    Q_UNUSED = event
                    splash_ref = getattr(inner_self, "_splash_ref", None)
                    if splash_ref is None:
                        return
                    painter = None
                    try:
                        painter = QtGui.QPainter(inner_self)
                        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

                        width = inner_self.width()
                        height = inner_self.height()
                        panel_rect = QtCore.QRectF(0, 0, width, height)
                        panel_path = QtGui.QPainterPath()
                        panel_path.addRoundedRect(panel_rect, 24, 24)
                        painter.setClipPath(panel_path)

                        bg_grad = QtGui.QLinearGradient(0, 0, 0, height)
                        bg_grad.setColorAt(0.0, QtGui.QColor(16, 22, 32, 245))
                        bg_grad.setColorAt(1.0, QtGui.QColor(10, 14, 22, 250))
                        painter.fillRect(inner_self.rect(), bg_grad)

                        painter.setClipping(False)
                        border_pen = QtGui.QPen(QtGui.QColor(56, 189, 248, 80))
                        border_pen.setWidthF(1.5)
                        painter.setPen(border_pen)
                        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                        painter.drawRoundedRect(QtCore.QRectF(0.75, 0.75, width - 1.5, height - 1.5), 24, 24)

                        accent_rect = QtCore.QRectF(40, 0, width - 80, 3)
                        accent_grad = QtGui.QLinearGradient(40, 0, width - 40, 0)
                        accent_grad.setColorAt(0.0, QtGui.QColor(56, 189, 248, 0))
                        accent_grad.setColorAt(0.3, QtGui.QColor(56, 189, 248, 180))
                        accent_grad.setColorAt(0.5, QtGui.QColor(52, 211, 153, 200))
                        accent_grad.setColorAt(0.7, QtGui.QColor(56, 189, 248, 180))
                        accent_grad.setColorAt(1.0, QtGui.QColor(56, 189, 248, 0))
                        painter.setPen(QtCore.Qt.PenStyle.NoPen)
                        painter.setBrush(accent_grad)
                        painter.drawRoundedRect(accent_rect, 1.5, 1.5)

                        cursor_y = 40
                        logo = splash_ref._logo_pixmap
                        if logo is not None and not logo.isNull():
                            scaled = logo.scaled(
                                72,
                                72,
                                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                                QtCore.Qt.TransformationMode.SmoothTransformation,
                            )
                            painter.drawPixmap((width - scaled.width()) // 2, cursor_y, scaled)
                            cursor_y += 88
                        else:
                            cursor_y += 20

                        title_font = QtGui.QFont("Segoe UI", 18, QtGui.QFont.Weight.Bold)
                        painter.setFont(title_font)
                        painter.setPen(QtGui.QColor(230, 237, 243))
                        painter.drawText(
                            QtCore.QRectF(0, cursor_y, width, 30),
                            QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignTop,
                            _LANGUAGE_SWITCH_DISPLAY_NAME,
                        )
                        cursor_y += 36

                        painter.setFont(QtGui.QFont("Segoe UI", 11))
                        painter.setPen(QtGui.QColor(148, 163, 184))
                        painter.drawText(
                            QtCore.QRectF(0, cursor_y, width, 22),
                            QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignTop,
                            splash_ref._status_text,
                        )
                        cursor_y += 34

                        spinner_rect = QtCore.QRectF((width - 44) // 2, cursor_y, 44, 44)
                        track_pen = QtGui.QPen(QtGui.QColor(148, 163, 184, 40))
                        track_pen.setWidthF(3.0)
                        track_pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
                        painter.setPen(track_pen)
                        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                        painter.drawEllipse(spinner_rect)

                        arc_path = QtGui.QPainterPath()
                        arc_path.arcMoveTo(spinner_rect, splash_ref._spinner_angle)
                        arc_path.arcTo(spinner_rect, splash_ref._spinner_angle, 100)
                        arc_pen = QtGui.QPen(QtGui.QColor(56, 189, 248))
                        arc_pen.setWidthF(3.0)
                        arc_pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
                        painter.setPen(arc_pen)
                        painter.drawPath(arc_path)

                        arc_path2 = QtGui.QPainterPath()
                        angle2 = (splash_ref._spinner_angle + 180) % 360
                        arc_path2.arcMoveTo(spinner_rect, angle2)
                        arc_path2.arcTo(spinner_rect, angle2, 60)
                        arc_pen2 = QtGui.QPen(QtGui.QColor(52, 211, 153, 180))
                        arc_pen2.setWidthF(3.0)
                        arc_pen2.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
                        painter.setPen(arc_pen2)
                        painter.drawPath(arc_path2)
                    except Exception:
                        pass
                    finally:
                        if painter is not None:
                            try:
                                painter.end()
                            except Exception:
                                pass

            widget = _Widget(
                None,
                QtCore.Qt.WindowType.FramelessWindowHint
                | QtCore.Qt.WindowType.WindowStaysOnTopHint
                | QtCore.Qt.WindowType.Tool
                | QtCore.Qt.WindowType.WindowDoesNotAcceptFocus
                | QtCore.Qt.WindowType.NoDropShadowWindowHint,
            )
            widget.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
            widget.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            widget.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            widget.setFixedSize(420, 320)
            widget.move(
                screen_geo.x() + (screen_geo.width() - 420) // 2,
                screen_geo.y() + (screen_geo.height() - 320) // 2,
            )
            widget._splash_ref = self  # type: ignore[attr-defined]
            self._widget = widget
            widget.show()
            widget.raise_()
            widget.activateWindow()
            QtWidgets.QApplication.processEvents()

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
        self._status_text = str(text or "Loading...")
        if self._widget is not None:
            try:
                self._widget.update()
                QtWidgets.QApplication.processEvents()
            except Exception:
                pass

    def raise_window(self) -> None:
        if self._widget is None:
            return
        try:
            self._widget.show()
            self._widget.raise_()
            self._widget.activateWindow()
            QtWidgets.QApplication.processEvents()
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


def create_launch_progress_dialog(status_text: str, parent: QtWidgets.QWidget | None = None) -> LanguageSwitchSplash | None:
    Q_UNUSED = parent
    try:
        splash = LanguageSwitchSplash(status_text)
        splash.raise_window()
        return splash
    except Exception:
        return None


def detach_launch_progress_dialog(dialog: LanguageSwitchSplash | None) -> None:
    if dialog is None:
        return
    try:
        dialog.raise_window()
    except Exception:
        pass


def hide_window_for_handoff(
    window,
    progress_dialog: LanguageSwitchSplash | None,
    *,
    active_attr: str,
    hidden_attr: str,
) -> bool:
    detach_launch_progress_dialog(progress_dialog)
    hidden = False
    try:
        setattr(window, active_attr, True)
        window.hide()
        hidden = not bool(window.isVisible())
    except Exception:
        hidden = False
    finally:
        try:
            setattr(window, active_attr, False)
        except Exception:
            pass
    try:
        setattr(window, hidden_attr, bool(hidden))
    except Exception:
        pass
    return bool(hidden)


def restore_window_after_handoff(window, *, hidden_attr: str) -> None:
    try:
        hidden_for_handoff = bool(getattr(window, hidden_attr, False))
    except Exception:
        hidden_for_handoff = False
    if not hidden_for_handoff:
        return
    try:
        setattr(window, hidden_attr, False)
    except Exception:
        pass
    try:
        state = window.windowState()
    except Exception:
        state = QtCore.Qt.WindowState.WindowNoState
    try:
        if state & QtCore.Qt.WindowState.WindowMaximized:
            window.showMaximized()
        else:
            window.show()
    except Exception:
        try:
            window.showMaximized()
        except Exception:
            pass
    try:
        window.raise_()
        window.activateWindow()
    except Exception:
        pass


def shutdown_python_after_handoff(window, *, hidden_attr: str) -> None:
    try:
        setattr(window, hidden_attr, False)
    except Exception:
        pass
    try:
        window._force_close = True
    except Exception:
        pass
    try:
        QtWidgets.QWidget.close(window)
        return
    except Exception:
        pass
    try:
        app = QtWidgets.QApplication.instance()
        if app is not None:
            setattr(app, "_exiting", True)
            arm_hard_exit = getattr(app, "_bot_arm_hard_exit", None)
            if callable(arm_hard_exit):
                arm_hard_exit()
            app.quit()
    except Exception:
        pass


def update_launch_progress(dialog: LanguageSwitchSplash | None, text: str) -> None:
    if dialog is None:
        return
    try:
        dialog.set_status(str(text or "Working..."))
    except Exception:
        pass


def is_qt_runtime_path(path_value: str | None) -> bool:
    value = str(path_value or "").strip().strip('"').strip("'")
    if not value:
        return False
    low = value.lower().replace("/", "\\")
    if "site-packages\\pyqt6\\qt6\\bin" in low:
        return True
    if "\\qt\\" in low and low.endswith("\\bin"):
        return True
    return False


def compose_cpp_launch_path(qt_bins: list[Path], base_path: str | None) -> str:
    preferred: list[str] = []
    preferred_norm: set[str] = set()
    for path in qt_bins:
        try:
            resolved = str(path.resolve())
        except Exception:
            resolved = str(path)
        normalized = os.path.normcase(os.path.normpath(resolved))
        if normalized in preferred_norm:
            continue
        preferred_norm.add(normalized)
        preferred.append(resolved)

    merged: list[str] = list(preferred)
    seen: set[str] = set(preferred_norm)
    for token in str(base_path or "").split(os.pathsep):
        part = str(token or "").strip()
        if not part:
            continue
        normalized = os.path.normcase(os.path.normpath(part))
        if normalized in seen:
            continue
        if is_qt_runtime_path(part) and normalized not in preferred_norm:
            continue
        seen.add(normalized)
        merged.append(part)
    return os.pathsep.join(merged)


def find_windeployqt_for_cpp(qt_bins: list[Path] | None = None) -> Path | None:
    names = ["windeployqt"]
    if sys.platform == "win32":
        names.insert(0, "windeployqt.exe")

    for candidate in qt_bins or []:
        for name in names:
            path = candidate / name
            try:
                if path.is_file():
                    return path.resolve()
            except Exception:
                continue

    for name in names:
        found = shutil.which(name)
        if not found:
            continue
        try:
            return Path(found).resolve()
        except Exception:
            return Path(found)
    return None


def cpp_runtime_stamp_path(exe_path: Path) -> Path:
    return exe_path.parent / ".tb_cpp_runtime.stamp"


def cpp_runtime_bundle_missing(exe_path: Path) -> bool:
    required_dlls = ("Qt6Core.dll", "Qt6Gui.dll", "Qt6Widgets.dll", "Qt6Network.dll")
    for dll_name in required_dlls:
        try:
            if not (exe_path.parent / dll_name).is_file():
                return True
        except Exception:
            return True
    if sys.platform == "win32":
        try:
            if not (exe_path.parent / "platforms" / "qwindows.dll").is_file():
                return True
        except Exception:
            return True
    return False


def prepare_cpp_launch_env(
    exe_path: Path,
    qt_bins: list[Path],
    base_env: dict[str, str] | None = None,
) -> dict[str, str]:
    env = dict(base_env or os.environ.copy())
    for key in (
        "QT_PLUGIN_PATH",
        "QT_QPA_PLATFORM_PLUGIN_PATH",
        "QML_IMPORT_PATH",
        "QML2_IMPORT_PATH",
        "QT_QPA_FONTDIR",
        "QT_QPA_PLATFORMTHEME",
    ):
        env.pop(key, None)

    launch_bins: list[Path] = [exe_path.parent]
    launch_bins.extend(qt_bins or [])
    env["PATH"] = compose_cpp_launch_path(launch_bins, env.get("PATH", ""))
    env["TB_CPP_LAUNCH_PATH"] = os.pathsep.join(str(path) for path in launch_bins if str(path).strip())

    plugin_root = exe_path.parent
    platform_plugins = plugin_root / "platforms"
    if platform_plugins.is_dir():
        env["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(platform_plugins)
    if plugin_root.is_dir():
        env["QT_PLUGIN_PATH"] = str(plugin_root)
    return env


def deploy_cpp_runtime_bundle(
    exe_path: Path,
    *,
    qt_bins: list[Path] | None = None,
    force: bool = False,
) -> tuple[bool, str]:
    if sys.platform != "win32":
        return True, ""
    if exe_path is None or not exe_path.is_file():
        return False, "C++ executable does not exist."

    stamp_path = cpp_runtime_stamp_path(exe_path)
    if not force:
        try:
            stamp_fresh = stamp_path.is_file() and stamp_path.stat().st_mtime >= exe_path.stat().st_mtime
        except Exception:
            stamp_fresh = False
        if stamp_fresh and not cpp_runtime_bundle_missing(exe_path):
            return True, "already-deployed"

    windeployqt = find_windeployqt_for_cpp(qt_bins)
    if windeployqt is None:
        return False, "windeployqt was not found."

    deploy_env = os.environ.copy()
    deploy_env["PATH"] = compose_cpp_launch_path(qt_bins or [], deploy_env.get("PATH", ""))
    deploy_cmd = [
        str(windeployqt),
        "--compiler-runtime",
        "--no-translations",
        "--force",
        str(exe_path),
    ]
    ok, output = run_command_capture_hidden(deploy_cmd, cwd=exe_path.parent, env=deploy_env)
    if ok:
        try:
            stamp_path.write_text(str(time.time()), encoding="utf-8")
        except Exception:
            pass
    return ok, output


def format_windows_exit_code(returncode: int | None) -> str:
    try:
        value = int(returncode or 0)
    except Exception:
        return str(returncode)
    if value < 0:
        value = (value + (1 << 32)) & 0xFFFFFFFF
    return f"{value} (0x{value:08X})"


def run_command_capture_hidden(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> tuple[bool, str]:
    run_kwargs: dict[str, object] = {
        "capture_output": True,
        "text": True,
    }
    if cwd is not None:
        run_kwargs["cwd"] = str(cwd)
    if env is not None:
        run_kwargs["env"] = env
    if sys.platform == "win32":
        run_kwargs["creationflags"] = 0x08000000
    try:
        result = subprocess.run(command, check=True, **run_kwargs)
        output = ((result.stdout or "") + (result.stderr or "")).strip()
        return True, output
    except FileNotFoundError:
        return False, f"Command not found: {command[0]}"
    except subprocess.CalledProcessError as exc:
        output = ((exc.stdout or "") + (exc.stderr or "")).strip()
        return False, output
    except Exception as exc:
        return False, str(exc)


def run_callable_with_ui_pump(
    fn,
    *args,
    poll_interval_s: float = 0.05,
    **kwargs,
):
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(fn, *args, **kwargs)
        while not future.done():
            try:
                QtWidgets.QApplication.processEvents()
            except Exception:
                pass
            time.sleep(max(0.01, float(poll_interval_s)))
        return future.result()
