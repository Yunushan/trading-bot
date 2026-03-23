from __future__ import annotations

import os
import sys
import time


class _StartupPresentationController:
    def __init__(
        self,
        *,
        app,
        QtCore,
        QtGui,
        QLabel,
        QWidget,
        env_flag,
        boot_log,
        pre_qt_window_suppressor,
        splash_screen_cls,
        close_native_startup_cover,
        native_startup_cover=None,
    ) -> None:
        self.app = app
        self.QtCore = QtCore
        self.QtGui = QtGui
        self.QLabel = QLabel
        self.QWidget = QWidget
        self._env_flag = env_flag
        self._boot_log = boot_log
        self._pre_qt_window_suppressor = pre_qt_window_suppressor
        self._SplashScreen = splash_screen_cls
        self._close_native_startup_cover = close_native_startup_cover
        self._native_startup_cover = native_startup_cover
        self._startup_masks: list = []
        self._startup_mask_hide_ms = 0
        self._splash = None
        self._startup_overlay_raise_timer = None
        self._startup_main_window_shown = False
        self._startup_user_switched_away = False
        self._startup_transition_done = False
        self._startup_transition_deadline = 0.0
        self._mask_unmask_deadline = 0.0
        self._win = None

        self._create_startup_masks()
        self._create_splash()
        if self._splash is not None or self._startup_masks:
            self._native_startup_cover = self._close_native_startup_cover(
                self._native_startup_cover,
                boot_log=self._boot_log,
            )
        self._start_overlay_raise_timer_if_needed()

    def set_status(self, text: str) -> None:
        splash = self._splash
        if splash is None:
            return
        try:
            splash.set_status(text)
        except Exception:
            pass

    def attach_main_window(self, win) -> None:  # noqa: ANN001
        self._win = win
        try:
            main_hwnd = int(win.winId())
        except Exception:
            main_hwnd = 0
        if main_hwnd:
            try:
                self._pre_qt_window_suppressor.add_known_ok_hwnd(main_hwnd)
            except Exception:
                pass

        # Once the main window is visible, release startup overlays quickly so
        # the UI becomes interactive instead of waiting several seconds for a
        # stricter exposure check.
        transition_timeout_s = 1.2 if not self._startup_masks else 4.0
        self._mask_unmask_deadline = time.monotonic() + transition_timeout_s
        self._startup_transition_deadline = time.monotonic() + transition_timeout_s
        startup_reveal_ms = self._startup_reveal_ms()
        startup_reveal_armed = bool(sys.platform == "win32" and startup_reveal_ms > 0)

        if not startup_reveal_armed:
            self._show_main_window(activate=True)
        else:
            self._boot_log("MainWindow show deferred for startup reveal")

        if startup_reveal_armed:
            self.QtCore.QTimer.singleShot(startup_reveal_ms, self._reveal_main_window)
            if self._startup_masks:
                delay_ms = max(self._startup_mask_hide_ms, startup_reveal_ms + 300)
                self.QtCore.QTimer.singleShot(delay_ms, self._try_hide_startup_mask)
        elif self._startup_masks:
            self.QtCore.QTimer.singleShot(self._startup_mask_hide_ms or 1300, self._try_hide_startup_mask)
            self.QtCore.QTimer.singleShot(0, self._finish_startup_transition)
        else:
            self.QtCore.QTimer.singleShot(0, self._finish_startup_transition)

    def _startup_reveal_ms(self) -> int:
        try:
            reveal_ms = int(os.environ.get("BOT_STARTUP_REVEAL_DELAY_MS") or 0)
        except Exception:
            reveal_ms = 0
        return max(0, min(reveal_ms, 5000))

    def _create_startup_masks(self) -> None:
        if sys.platform != "win32" or not self._env_flag("BOT_STARTUP_MASK_ENABLED"):
            return
        try:
            startup_mask_hide_ms = int(os.environ.get("BOT_STARTUP_MASK_HIDE_MS") or 500)
        except Exception:
            startup_mask_hide_ms = 500
        startup_mask_mode = str(os.environ.get("BOT_STARTUP_MASK_MODE") or "snapshot").strip().lower()
        startup_mask_scope = str(os.environ.get("BOT_STARTUP_MASK_SCOPE") or "all").strip().lower()
        startup_mask_hide_ms = max(100, min(startup_mask_hide_ms, 5000))
        self._startup_mask_hide_ms = startup_mask_hide_ms
        try:
            screens: list = []
            all_screens = list(self.QtGui.QGuiApplication.screens() or [])
            if startup_mask_scope in {"primary", "main"}:
                primary = self.QtGui.QGuiApplication.primaryScreen()
                if primary is not None:
                    screens = [primary]
            elif startup_mask_scope in {"cursor", "active"}:
                try:
                    cursor_pos = self.QtGui.QCursor.pos()
                except Exception:
                    cursor_pos = None
                chosen = self.QtGui.QGuiApplication.screenAt(cursor_pos) if cursor_pos is not None else None
                if chosen is not None:
                    screens = [chosen]
            if not screens:
                screens = all_screens
            if not screens:
                primary = self.QtGui.QGuiApplication.primaryScreen()
                if primary is not None:
                    screens = [primary]
            snapshot_count = 0
            for screen in screens:
                mask = self.QWidget(
                    None,
                    self.QtCore.Qt.WindowType.SplashScreen
                    | self.QtCore.Qt.WindowType.FramelessWindowHint
                    | self.QtCore.Qt.WindowType.WindowStaysOnTopHint
                    | self.QtCore.Qt.WindowType.NoDropShadowWindowHint,
                )
                mask.setAttribute(self.QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
                mask.setAttribute(self.QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                try:
                    mask.setWindowTitle("")
                except Exception:
                    pass
                mask.setGeometry(screen.geometry())
                mask_is_snapshot = False
                if startup_mask_mode == "snapshot":
                    try:
                        pixmap = screen.grabWindow(0)
                    except Exception:
                        pixmap = self.QtGui.QPixmap()
                    if pixmap is not None and not pixmap.isNull():
                        snapshot = self.QLabel(mask)
                        snapshot.setScaledContents(True)
                        snapshot.setPixmap(pixmap)
                        snapshot.setGeometry(mask.rect())
                        snapshot.show()
                        mask_is_snapshot = True
                        snapshot_count += 1
                if not mask_is_snapshot:
                    mask.setStyleSheet("background-color: #0d1117;")
                mask.show()
                try:
                    mask.raise_()
                except Exception:
                    pass
                self._make_mask_click_through(mask)
                try:
                    self._pre_qt_window_suppressor.add_known_ok_hwnd(int(mask.winId()))
                except Exception:
                    pass
                self._startup_masks.append(mask)
            self._process_events(50)
            mask_mode_effective = "snapshot" if snapshot_count == len(self._startup_masks) and self._startup_masks else "solid"
            self._boot_log(
                f"startup masks shown count={len(self._startup_masks)} mode={mask_mode_effective} scope={startup_mask_scope or 'all'}"
            )
        except Exception:
            self._startup_masks = []

    def _make_mask_click_through(self, mask) -> None:  # noqa: ANN001
        try:
            import ctypes
            import ctypes.wintypes as wintypes

            user32 = ctypes.windll.user32
            hwnd = wintypes.HWND(int(mask.winId()))
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x00080000
            WS_EX_TRANSPARENT = 0x00000020
            get_style = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
            set_style = getattr(user32, "SetWindowLongPtrW", None) or user32.SetWindowLongW
            exstyle = int(get_style(hwnd, GWL_EXSTYLE))
            set_style(hwnd, GWL_EXSTYLE, exstyle | WS_EX_LAYERED | WS_EX_TRANSPARENT)
        except Exception:
            pass

    def _create_splash(self) -> None:
        splash_host_widget = self._startup_masks[0] if self._startup_masks else None
        if self._env_flag("BOT_DISABLE_SPLASH"):
            return
        try:
            splash = self._SplashScreen(
                self.app,
                self.QtCore,
                self.QtGui,
                self.QWidget,
                host_widget=splash_host_widget,
            )
            self._boot_log("splash screen shown")
            if splash._widget is not None and splash_host_widget is None:
                try:
                    self._pre_qt_window_suppressor.add_known_ok_hwnd(int(splash._widget.winId()))
                except Exception:
                    pass
            if splash._widget is not None and self._startup_masks:
                try:
                    splash._widget.raise_()
                except Exception:
                    pass
                self._process_events(25)
            self._splash = splash
        except Exception:
            self._splash = None

    def _process_events(self, max_ms: int) -> None:
        try:
            self.app.processEvents(self.QtCore.QEventLoop.ProcessEventsFlag.AllEvents, max_ms)
        except Exception:
            pass

    def _startup_app_is_active(self) -> bool:
        try:
            state = self.app.applicationState()
        except Exception:
            return True
        return state == self.QtCore.Qt.ApplicationState.ApplicationActive

    def _stop_startup_overlay_raise_timer(self) -> None:
        timer = self._startup_overlay_raise_timer
        if timer is None:
            return
        try:
            timer.stop()
        except Exception:
            pass
        try:
            timer.deleteLater()
        except Exception:
            pass
        self._startup_overlay_raise_timer = None

    def _release_startup_overlays(self, *, reason: str = "", mark_user_switched: bool = False) -> None:
        if mark_user_switched:
            self._startup_user_switched_away = True
        self._stop_startup_overlay_raise_timer()
        splash = self._splash
        if splash is not None:
            try:
                splash.close()
            except Exception:
                pass
            self._splash = None
        if self._startup_masks:
            for mask in list(self._startup_masks):
                try:
                    mask.hide()
                except Exception:
                    pass
                try:
                    mask.deleteLater()
                except Exception:
                    pass
            self._startup_masks = []
        if reason:
            self._boot_log(f"startup overlays released ({reason})")

    def _raise_startup_overlays(self) -> None:
        if self._startup_main_window_shown and not self._startup_app_is_active():
            self._release_startup_overlays(reason="app-inactive", mark_user_switched=True)
            return
        for mask in list(self._startup_masks):
            try:
                mask.raise_()
            except Exception:
                pass
        splash = self._splash
        if splash is not None and getattr(splash, "_widget", None) is not None:
            try:
                splash._widget.raise_()
            except Exception:
                pass

    def _start_overlay_raise_timer_if_needed(self) -> None:
        if sys.platform != "win32" or not self._startup_masks:
            return
        try:
            timer = self.QtCore.QTimer(self.app)
            timer.setInterval(15)
            timer.timeout.connect(self._raise_startup_overlays)
            timer.start()
            self._startup_overlay_raise_timer = timer
            self._raise_startup_overlays()
        except Exception:
            self._startup_overlay_raise_timer = None

    def _show_main_window(self, *, activate: bool) -> None:
        win = self._win
        if win is None:
            return
        show_without_activating = not activate
        if show_without_activating:
            try:
                win.setAttribute(self.QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            except Exception:
                pass
        try:
            if sys.platform == "win32":
                try:
                    win.setWindowState(win.windowState() | self.QtCore.Qt.WindowState.WindowMaximized)
                except Exception:
                    pass
                try:
                    win.showMaximized()
                except Exception:
                    win.show()
            else:
                win.show()
        finally:
            if show_without_activating:
                try:
                    self.QtCore.QTimer.singleShot(
                        0,
                        lambda: win.setAttribute(self.QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, False),
                    )
                except Exception:
                    pass
        self._startup_main_window_shown = True
        self._boot_log("MainWindow shown")
        self._native_startup_cover = self._close_native_startup_cover(
            self._native_startup_cover,
            boot_log=self._boot_log,
        )

    def _main_window_ready_for_unmask(self) -> bool:
        win = self._win
        if win is None:
            return False
        try:
            if not win.isVisible():
                return False
        except Exception:
            return False
        try:
            if win.windowState() & self.QtCore.Qt.WindowState.WindowMinimized:
                return False
        except Exception:
            pass
        try:
            handle = win.windowHandle()
        except Exception:
            handle = None
        if handle is not None:
            try:
                if hasattr(handle, "isExposed") and not handle.isExposed():
                    try:
                        if self.app.activeWindow() is win:
                            return True
                    except Exception:
                        pass
                    try:
                        focus_window = self.QtGui.QGuiApplication.focusWindow()
                        if focus_window is not None and focus_window is handle:
                            return True
                    except Exception:
                        pass
                    return False
            except Exception:
                pass
        return True

    def _finish_startup_transition(self) -> None:
        if self._startup_transition_done:
            return
        if not self._main_window_ready_for_unmask() and time.monotonic() < self._startup_transition_deadline:
            self.QtCore.QTimer.singleShot(60, self._finish_startup_transition)
            return
        self._startup_transition_done = True
        self._stop_startup_overlay_raise_timer()
        try:
            self._pre_qt_window_suppressor.stop()
        except Exception:
            pass
        splash = self._splash
        if splash is not None:
            try:
                splash.close()
                self._boot_log("splash screen closed")
            except Exception:
                pass
            self._splash = None
        self._try_hide_startup_mask()

    def _try_hide_startup_mask(self) -> None:
        if not self._startup_masks:
            return
        if not self._main_window_ready_for_unmask() and time.monotonic() < self._mask_unmask_deadline:
            self.QtCore.QTimer.singleShot(80, self._try_hide_startup_mask)
            return
        for mask in list(self._startup_masks):
            try:
                mask.hide()
            except Exception:
                pass
            try:
                mask.deleteLater()
            except Exception:
                pass
        self._startup_masks = []
        self._boot_log("startup masks hidden")

    def _reveal_main_window(self) -> None:
        activate_now = (not self._startup_user_switched_away) and self._startup_app_is_active()
        win = self._win
        if win is not None:
            try:
                if not win.isVisible():
                    self._show_main_window(activate=activate_now)
            except Exception:
                pass
            try:
                if activate_now:
                    win.raise_()
                    win.activateWindow()
            except Exception:
                pass
        self._finish_startup_transition()
