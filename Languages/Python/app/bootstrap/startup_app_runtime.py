from __future__ import annotations

import sys


def _optional_qt_call(callback, *args) -> bool:
    try:
        callback(*args)
    except (AttributeError, RuntimeError, TypeError):
        return False
    return True


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
        _optional_qt_call(
            QtCore.QCoreApplication.setAttribute,
            QtCore.Qt.ApplicationAttribute.AA_DontCreateNativeWidgetSiblings,
            True,
        )
        if env_flag("BOT_FORCE_SOFTWARE_OPENGL"):
            _optional_qt_call(
                QtCore.QCoreApplication.setAttribute,
                QtCore.Qt.ApplicationAttribute.AA_UseSoftwareOpenGL,
                True,
            )

    app = QApplication(sys.argv)
    app.setApplicationName(app_display_name)
    app.setApplicationDisplayName(app_display_name)
    app._exiting = False  # type: ignore[attr-defined]
    bind_background_process_exit(
        app,
        uninstall_startup_window_suppression=uninstall_startup_window_suppression,
        uninstall_cbt_startup_window_suppression=uninstall_cbt_startup_window_suppression,
    )
    _optional_qt_call(QtGui.QGuiApplication.setDesktopFileName, app_user_model_id)
    if sys.platform == "win32":
        _optional_qt_call(app.setQuitOnLastWindowClosed, False)
    return app


def _load_application_icon(*, QtGui, app, env_flag, force_app_icon: bool):
    from app.gui.shared.app_icon import find_primary_icon_file, load_app_icon

    icon = QtGui.QIcon()
    disable_app_icon = env_flag("BOT_DISABLE_APP_ICON") and not force_app_icon
    if not disable_app_icon:
        try:
            icon = load_app_icon()
        except (OSError, RuntimeError, TypeError):
            icon = QtGui.QIcon()
    if (force_app_icon or not disable_app_icon) and icon.isNull():
        try:
            fallback_path = find_primary_icon_file()
        except OSError:
            fallback_path = None
        if fallback_path and fallback_path.is_file():
            icon = QtGui.QIcon(str(fallback_path))
    if not icon.isNull():
        _optional_qt_call(app.setWindowIcon, icon)
        _optional_qt_call(QtGui.QGuiApplication.setWindowIcon, icon)
    return icon, disable_app_icon
