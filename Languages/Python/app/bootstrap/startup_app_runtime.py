from __future__ import annotations

import sys


def _create_qt_application(
    *,
    QApplication,
    QtCore,
    QtGui,
    env_flag,
    app_display_name: str,
    app_user_model_id: str,
    bind_background_process_exit,
    uninstall_startup_window_suppression,
    uninstall_cbt_startup_window_suppression,
):
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.ApplicationAttribute.AA_DontShowIconsInMenus, False)
    if sys.platform == "win32":
        try:
            QtCore.QCoreApplication.setAttribute(
                QtCore.Qt.ApplicationAttribute.AA_DontCreateNativeWidgetSiblings,
                True,
            )
        except Exception:
            pass
        if env_flag("BOT_FORCE_SOFTWARE_OPENGL"):
            try:
                QtCore.QCoreApplication.setAttribute(QtCore.Qt.ApplicationAttribute.AA_UseSoftwareOpenGL, True)
            except Exception:
                pass

    app = QApplication(sys.argv)
    app.setApplicationName(app_display_name)
    app.setApplicationDisplayName(app_display_name)
    app._exiting = False  # type: ignore[attr-defined]
    bind_background_process_exit(
        app,
        uninstall_startup_window_suppression=uninstall_startup_window_suppression,
        uninstall_cbt_startup_window_suppression=uninstall_cbt_startup_window_suppression,
    )
    try:
        QtGui.QGuiApplication.setDesktopFileName(app_user_model_id)
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            app.setQuitOnLastWindowClosed(False)
        except Exception:
            pass
    return app


def _load_application_icon(*, QtGui, app, env_flag, force_app_icon: bool):
    from app.gui.shared.app_icon import find_primary_icon_file, load_app_icon

    icon = QtGui.QIcon()
    disable_app_icon = env_flag("BOT_DISABLE_APP_ICON") and not force_app_icon
    if not disable_app_icon:
        try:
            icon = load_app_icon()
        except Exception:
            icon = QtGui.QIcon()
    if (force_app_icon or not disable_app_icon) and icon.isNull():
        try:
            fallback_path = find_primary_icon_file()
        except Exception:
            fallback_path = None
        if fallback_path and fallback_path.is_file():
            try:
                icon = QtGui.QIcon(str(fallback_path))
            except Exception:
                icon = QtGui.QIcon()
        if not icon.isNull():
            try:
                app.setWindowIcon(icon)
                QtGui.QGuiApplication.setWindowIcon(icon)
            except Exception:
                pass
    return icon, disable_app_icon
