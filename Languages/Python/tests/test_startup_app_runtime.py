# ruff: noqa: E402

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


from app.bootstrap import startup_app_runtime


class _App:
    def __init__(self):
        self.name = None
        self.display_name = None
        self.quit_on_last_window_closed = None
        self.window_icons = []

    def setApplicationName(self, value):
        self.name = value

    def setApplicationDisplayName(self, value):
        self.display_name = value

    def setQuitOnLastWindowClosed(self, value):
        self.quit_on_last_window_closed = value

    def setWindowIcon(self, icon):
        self.window_icons.append(icon)


class _Icon:
    def __init__(self, path=None, *, is_null=False):
        self.path = path
        self._is_null = is_null

    def isNull(self):
        return self._is_null


class StartupApplicationRuntimeTests(unittest.TestCase):
    def test_optional_qt_call_only_suppresses_optional_api_failures(self):
        for error in (AttributeError, RuntimeError, TypeError):
            with self.subTest(error=error.__name__):
                self.assertFalse(startup_app_runtime._optional_qt_call(lambda: (_ for _ in ()).throw(error())))

        calls = []
        self.assertTrue(startup_app_runtime._optional_qt_call(calls.append, "ok"))
        self.assertEqual(["ok"], calls)

    def test_create_application_configures_windows_qt_flags_and_exit_binding(self):
        attributes = []
        desktop_file_names = []
        app = _App()
        qt_core = SimpleNamespace(
            QCoreApplication=SimpleNamespace(setAttribute=lambda *args: attributes.append(args)),
            Qt=SimpleNamespace(
                ApplicationAttribute=SimpleNamespace(
                    AA_DontShowIconsInMenus="menus",
                    AA_DontCreateNativeWidgetSiblings="native-siblings",
                    AA_UseSoftwareOpenGL="software-opengl",
                )
            ),
        )
        qt_gui = SimpleNamespace(
            QGuiApplication=SimpleNamespace(setDesktopFileName=desktop_file_names.append)
        )
        bindings = []

        with mock.patch.object(startup_app_runtime.sys, "platform", "win32"):
            result = startup_app_runtime._create_qt_application(
                QApplication=lambda _argv: app,
                QtCore=qt_core,
                QtGui=qt_gui,
                env_flag=lambda name: name == "BOT_FORCE_SOFTWARE_OPENGL",
                app_display_name="Trading Bot",
                app_user_model_id="com.tradingbot.desktop",
                bind_background_process_exit=lambda bound_app, **kwargs: bindings.append((bound_app, kwargs)),
                uninstall_startup_window_suppression="uninstall-window",
                uninstall_cbt_startup_window_suppression="uninstall-cbt",
            )

        self.assertIs(app, result)
        self.assertEqual("Trading Bot", app.name)
        self.assertEqual("Trading Bot", app.display_name)
        self.assertFalse(app._exiting)
        self.assertFalse(app.quit_on_last_window_closed)
        self.assertEqual(["com.tradingbot.desktop"], desktop_file_names)
        self.assertEqual(
            [
                ("menus", False),
                ("native-siblings", True),
                ("software-opengl", True),
            ],
            attributes,
        )
        self.assertEqual(
            [
                (
                    app,
                    {
                        "uninstall_startup_window_suppression": "uninstall-window",
                        "uninstall_cbt_startup_window_suppression": "uninstall-cbt",
                    },
                )
            ],
            bindings,
        )

    def test_load_icon_keeps_startup_alive_when_optional_icon_apis_fail(self):
        icon = _Icon(is_null=False)
        app = _App()
        app.setWindowIcon = mock.Mock(side_effect=RuntimeError("window icon unavailable"))
        qt_gui = SimpleNamespace(
            QIcon=lambda *args: _Icon(*args),
            QGuiApplication=SimpleNamespace(setWindowIcon=mock.Mock(side_effect=RuntimeError("global icon unavailable"))),
        )

        with (
            mock.patch("app.gui.shared.app_icon.load_app_icon", return_value=icon),
            mock.patch("app.gui.shared.app_icon.find_primary_icon_file", return_value=None),
        ):
            loaded_icon, disabled = startup_app_runtime._load_application_icon(
                QtGui=qt_gui,
                app=app,
                env_flag=lambda _name: False,
                force_app_icon=False,
            )

        self.assertIs(icon, loaded_icon)
        self.assertFalse(disabled)
        app.setWindowIcon.assert_called_once_with(icon)
        qt_gui.QGuiApplication.setWindowIcon.assert_called_once_with(icon)


if __name__ == "__main__":
    unittest.main()
