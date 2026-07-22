# ruff: noqa: E402
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


from app.platform import windows_taskbar
from app.platform import windows_taskbar_metadata_runtime as taskbar_metadata_runtime
from app.platform import windows_taskbar_shortcut_runtime as taskbar_shortcut_runtime
from app.platform import windows_taskbar_shared_runtime as taskbar_shared_runtime


class WindowsTaskbarSplitSmokeTest(unittest.TestCase):
    @staticmethod
    def _property_store_shared(
        *,
        hwnd: int = 0,
        commit_result: int = 0,
        property_error: BaseException | None = None,
    ):
        calls: dict[str, object] = {"properties": [], "commit_count": 0, "release_count": 0}

        def commit(_store):
            calls["commit_count"] = int(calls["commit_count"]) + 1
            return commit_result

        def release(_store):
            calls["release_count"] = int(calls["release_count"]) + 1
            return 0

        store = SimpleNamespace(
            contents=SimpleNamespace(
                lpVtbl=SimpleNamespace(contents=SimpleNamespace(Commit=commit, Release=release))
            )
        )
        ctypes = SimpleNamespace(
            POINTER=lambda _type: lambda: store,
            byref=lambda value: value,
            c_wchar_p=lambda value: value,
        )
        shell32 = SimpleNamespace(
            SHGetPropertyStoreForWindow=lambda *_args: 0,
            SHGetPropertyStoreFromParsingName=lambda *_args: 0,
        )

        def set_prop_string(_store, key, value):
            if property_error is not None:
                raise property_error
            calls["properties"].append((key, value))

        shared = SimpleNamespace(
            ctypes=ctypes,
            wintypes=SimpleNamespace(HWND=int),
            IPropertyStore=object,
            _SetWindowAppUserModelID=lambda *_args: 0,
            _shell32=shell32,
            IID_IPropertyStore="IPropertyStore",
            PKEY_AppUserModel_ID="app_id",
            PKEY_RelaunchCommand="relaunch_command",
            PKEY_RelaunchDisplayNameResource="display_name",
            PKEY_RelaunchIconResource="icon_path",
            get_hwnd=lambda _window: hwnd,
            co_initialize_once=lambda: True,
            set_prop_string=set_prop_string,
        )
        return shared, calls

    @staticmethod
    def _shortcut_com_shared(*, save_result: int = 0):
        calls: dict[str, object] = {
            "properties": [],
            "commit_count": 0,
            "link_release_count": 0,
            "store_release_count": 0,
            "persist_release_count": 0,
        }

        def setter(*_args):
            return 0

        def query_interface(*_args):
            return 0

        def link_release(_link):
            calls["link_release_count"] = int(calls["link_release_count"]) + 1
            return 0

        def store_commit(_store):
            calls["commit_count"] = int(calls["commit_count"]) + 1
            return 0

        def store_release(_store):
            calls["store_release_count"] = int(calls["store_release_count"]) + 1
            return 0

        def persist_save(*_args):
            return save_result

        def persist_release(_persist):
            calls["persist_release_count"] = int(calls["persist_release_count"]) + 1
            return 0

        link = SimpleNamespace(
            contents=SimpleNamespace(
                lpVtbl=SimpleNamespace(
                    contents=SimpleNamespace(
                        SetPath=setter,
                        SetArguments=setter,
                        SetWorkingDirectory=setter,
                        SetIconLocation=setter,
                        SetDescription=setter,
                        QueryInterface=query_interface,
                        Release=link_release,
                    )
                )
            )
        )
        store = SimpleNamespace(
            contents=SimpleNamespace(
                lpVtbl=SimpleNamespace(contents=SimpleNamespace(Commit=store_commit, Release=store_release))
            )
        )
        persist = SimpleNamespace(
            contents=SimpleNamespace(
                lpVtbl=SimpleNamespace(contents=SimpleNamespace(Save=persist_save, Release=persist_release))
            )
        )
        pointers = iter((link, store, persist))
        ctypes = SimpleNamespace(
            c_void_p=lambda: next(pointers),
            byref=lambda value: value,
            cast=lambda value, _pointer_type: value,
            POINTER=lambda value: value,
        )

        def set_prop_string(_store, key, value):
            calls["properties"].append((key, value))

        shared = SimpleNamespace(
            ctypes=ctypes,
            _ole32=SimpleNamespace(CoCreateInstance=lambda *_args: 0),
            CLSID_ShellLink="CLSID_ShellLink",
            CLSCTX_INPROC_SERVER=1,
            IID_IShellLinkW="IID_IShellLinkW",
            IID_IPropertyStore="IID_IPropertyStore",
            IID_IPersistFile="IID_IPersistFile",
            IShellLinkW=object,
            IPropertyStore=object,
            IPersistFile=object,
            PKEY_AppUserModel_ID="app_id",
            PKEY_RelaunchDisplayNameResource="display_name",
            PKEY_RelaunchIconResource="icon_path",
            PKEY_RelaunchCommand="relaunch_command",
            co_initialize_once=lambda: True,
            set_prop_string=set_prop_string,
        )
        return shared, calls

    def test_windows_taskbar_facade_matches_split_modules(self):
        self.assertIs(windows_taskbar.ensure_app_user_model_id, taskbar_metadata_runtime.ensure_app_user_model_id)
        self.assertIs(windows_taskbar.apply_taskbar_metadata, taskbar_metadata_runtime.apply_taskbar_metadata)
        self.assertIs(windows_taskbar.ensure_taskbar_visible, taskbar_metadata_runtime.ensure_taskbar_visible)
        self.assertIs(windows_taskbar.build_relaunch_command, taskbar_metadata_runtime.build_relaunch_command)
        self.assertIs(windows_taskbar.ensure_start_menu_shortcut, taskbar_shortcut_runtime.ensure_start_menu_shortcut)
        self.assertIs(
            windows_taskbar._apply_shortcut_property_store,
            taskbar_shortcut_runtime._apply_shortcut_property_store,
        )

    def test_get_hwnd_prefers_effective_handle_then_falls_back_through_qt_handles(self):
        class _EffectiveWindow:
            def effectiveWinId(self):
                return 101

        class _WinIdWindow:
            def effectiveWinId(self):
                raise RuntimeError("effective handle unavailable")

            def winId(self):
                return 202

        class _WindowHandle:
            def winId(self):
                return 303

        class _WindowHandleWindow:
            def effectiveWinId(self):
                raise RuntimeError("effective handle unavailable")

            def winId(self):
                raise RuntimeError("window handle unavailable")

            def windowHandle(self):
                return _WindowHandle()

        with mock.patch.object(taskbar_shared_runtime.sys, "platform", "win32"):
            self.assertEqual(101, taskbar_shared_runtime.get_hwnd(_EffectiveWindow()))
            self.assertEqual(202, taskbar_shared_runtime.get_hwnd(_WinIdWindow()))
            self.assertEqual(303, taskbar_shared_runtime.get_hwnd(_WindowHandleWindow()))

    def test_co_initialize_once_accepts_success_and_changed_mode_results(self):
        calls: list[object] = []

        def initialize_success(value):
            calls.append(value)
            return 0

        with (
            mock.patch.object(taskbar_shared_runtime.sys, "platform", "win32"),
            mock.patch.object(taskbar_shared_runtime, "_COM_INITIALISED", False),
            mock.patch.object(taskbar_shared_runtime, "_ole32", SimpleNamespace(CoInitialize=initialize_success)),
        ):
            self.assertTrue(taskbar_shared_runtime.co_initialize_once())
            self.assertTrue(taskbar_shared_runtime.co_initialize_once())
        self.assertEqual([None], calls)

        with (
            mock.patch.object(taskbar_shared_runtime.sys, "platform", "win32"),
            mock.patch.object(taskbar_shared_runtime, "_COM_INITIALISED", False),
            mock.patch.object(
                taskbar_shared_runtime,
                "_ole32",
                SimpleNamespace(CoInitialize=lambda _value: 0x80010106),
            ),
        ):
            self.assertTrue(taskbar_shared_runtime.co_initialize_once())

    def test_relaunch_arguments_use_module_entrypoint_for_source_main(self):
        script = PYTHON_ROOT / "main.py"
        with (
            mock.patch.object(taskbar_metadata_runtime.sys, "platform", "win32"),
            mock.patch.object(taskbar_metadata_runtime.sys, "frozen", False, create=True),
        ):
            self.assertEqual(
                ["-m", "app.desktop.bootstrap.main"],
                taskbar_metadata_runtime.resolve_relaunch_arguments(script),
            )

    def test_relaunch_arguments_keep_nonstandard_source_script_path(self):
        script = Path("C:/tools/custom-launch.py")
        with (
            mock.patch.object(taskbar_metadata_runtime.sys, "platform", "win32"),
            mock.patch.object(taskbar_metadata_runtime.sys, "frozen", False, create=True),
        ):
            self.assertEqual([str(script.resolve())], taskbar_metadata_runtime.resolve_relaunch_arguments(script))

    def test_relaunch_executable_prefers_pythonw_for_source_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            python = root / "python.exe"
            pythonw = root / "pythonw.exe"
            python.touch()
            pythonw.touch()
            with (
                mock.patch.object(taskbar_metadata_runtime.sys, "platform", "win32"),
                mock.patch.object(taskbar_metadata_runtime.sys, "frozen", False, create=True),
                mock.patch.object(taskbar_metadata_runtime.sys, "executable", str(python)),
                mock.patch.object(taskbar_metadata_runtime.sys, "_base_executable", None, create=True),
            ):
                self.assertEqual(pythonw.resolve(), taskbar_metadata_runtime.resolve_relaunch_executable())

    def test_relaunch_executable_uses_frozen_executable_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            executable = Path(tmp) / "Trading-Bot-Python.exe"
            executable.touch()
            with (
                mock.patch.object(taskbar_metadata_runtime.sys, "platform", "win32"),
                mock.patch.object(taskbar_metadata_runtime.sys, "frozen", True, create=True),
                mock.patch.object(taskbar_metadata_runtime.sys, "executable", str(executable)),
                mock.patch.object(taskbar_metadata_runtime.sys, "_base_executable", None, create=True),
            ):
                self.assertEqual(executable.resolve(), taskbar_metadata_runtime.resolve_relaunch_executable())

    def test_build_relaunch_command_requires_existing_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            executable = Path(tmp) / "Trading Bot.exe"
            executable.touch()
            with (
                mock.patch.object(taskbar_metadata_runtime.sys, "platform", "win32"),
                mock.patch.object(taskbar_metadata_runtime, "resolve_relaunch_executable", return_value=executable),
                mock.patch.object(
                    taskbar_metadata_runtime,
                    "resolve_relaunch_arguments",
                    return_value=["-m", "app.desktop.bootstrap.main"],
                ),
            ):
                command = taskbar_metadata_runtime.build_relaunch_command()
            self.assertEqual(
                f'"{executable}" -m app.desktop.bootstrap.main',
                command,
            )

    def test_taskbar_metadata_and_visibility_fail_safely_without_a_window_handle(self):
        with (
            mock.patch.object(taskbar_metadata_runtime.sys, "platform", "win32"),
            mock.patch.object(taskbar_metadata_runtime.shared, "get_hwnd", return_value=0),
        ):
            self.assertFalse(taskbar_metadata_runtime.apply_taskbar_metadata(object(), app_id="com.tradingbot.desktop"))
            self.assertFalse(taskbar_metadata_runtime.ensure_taskbar_visible(object()))

    def test_taskbar_metadata_writes_all_relaunch_properties_and_releases_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            icon = Path(tmp) / "Trading Bot.ico"
            icon.touch()
            shared, calls = self._property_store_shared(hwnd=42)
            with (
                mock.patch.object(taskbar_metadata_runtime.sys, "platform", "win32"),
                mock.patch.object(taskbar_metadata_runtime, "shared", shared),
                mock.patch.object(taskbar_metadata_runtime, "ensure_app_user_model_id") as ensure_app_id,
            ):
                self.assertTrue(
                    taskbar_metadata_runtime.apply_taskbar_metadata(
                        object(),
                        app_id="com.tradingbot.desktop",
                        display_name="Trading Bot",
                        icon_path=icon,
                        relaunch_command='"Trading Bot.exe" -m app.desktop.bootstrap.main',
                    )
                )

            ensure_app_id.assert_called_once_with("com.tradingbot.desktop")
            self.assertEqual(1, calls["commit_count"])
            self.assertEqual(1, calls["release_count"])
            self.assertEqual(
                [
                    ("app_id", "com.tradingbot.desktop"),
                    ("relaunch_command", '"Trading Bot.exe" -m app.desktop.bootstrap.main'),
                    ("display_name", "Trading Bot"),
                    ("icon_path", f"{icon.resolve()},0"),
                ],
                calls["properties"],
            )

    def test_taskbar_metadata_reports_property_and_commit_failures_after_releasing_store(self):
        for shared, calls in (
            self._property_store_shared(hwnd=42, property_error=OSError("SetValue failed")),
            self._property_store_shared(hwnd=42, commit_result=-1),
        ):
            with (
                self.subTest(commit_result=calls["commit_count"]),
                mock.patch.object(taskbar_metadata_runtime.sys, "platform", "win32"),
                mock.patch.object(taskbar_metadata_runtime, "shared", shared),
                mock.patch.object(taskbar_metadata_runtime, "ensure_app_user_model_id"),
            ):
                self.assertFalse(
                    taskbar_metadata_runtime.apply_taskbar_metadata(
                        object(),
                        app_id="com.tradingbot.desktop",
                    )
                )
            self.assertEqual(1, calls["release_count"])

    def test_shortcut_creation_and_property_store_fail_safely_without_com(self):
        with tempfile.TemporaryDirectory() as tmp:
            shortcut = Path(tmp) / "Trading Bot.lnk"
            with (
                mock.patch.object(taskbar_shortcut_runtime.sys, "platform", "win32"),
                mock.patch.dict("os.environ", {"APPDATA": tmp}, clear=False),
                mock.patch.object(taskbar_shortcut_runtime.shared, "co_initialize_once", return_value=False),
            ):
                self.assertIsNone(
                    taskbar_shortcut_runtime.ensure_start_menu_shortcut(
                        app_id="com.tradingbot.desktop",
                        display_name="Trading Bot",
                        target_path=Path(tmp) / "Trading Bot.exe",
                    )
                )
                self.assertFalse(
                    taskbar_shortcut_runtime._apply_shortcut_property_store(
                        shortcut,
                        app_id="com.tradingbot.desktop",
                        display_name="Trading Bot",
                        icon_path=None,
                    )
                )

    def test_shortcut_property_store_writes_relaunch_properties_and_releases_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            shortcut = Path(tmp) / "Trading Bot.lnk"
            icon = Path(tmp) / "Trading Bot.ico"
            shortcut.touch()
            icon.touch()
            shared, calls = self._property_store_shared()
            with (
                mock.patch.object(taskbar_shortcut_runtime.sys, "platform", "win32"),
                mock.patch.object(taskbar_shortcut_runtime, "shared", shared),
            ):
                self.assertTrue(
                    taskbar_shortcut_runtime._apply_shortcut_property_store(
                        shortcut,
                        app_id="com.tradingbot.desktop",
                        display_name="Trading Bot",
                        icon_path=icon,
                        relaunch_command='"Trading Bot.exe" -m app.desktop.bootstrap.main',
                    )
                )

            self.assertEqual(1, calls["commit_count"])
            self.assertEqual(1, calls["release_count"])
            self.assertEqual(
                [
                    ("app_id", "com.tradingbot.desktop"),
                    ("display_name", "Trading Bot"),
                    ("icon_path", f"{icon.resolve()},0"),
                    ("relaunch_command", '"Trading Bot.exe" -m app.desktop.bootstrap.main'),
                ],
                calls["properties"],
            )

    def test_shortcut_property_store_reports_commit_failure_after_releasing_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            shortcut = Path(tmp) / "Trading Bot.lnk"
            shortcut.touch()
            shared, calls = self._property_store_shared(commit_result=-1)
            with (
                mock.patch.object(taskbar_shortcut_runtime.sys, "platform", "win32"),
                mock.patch.object(taskbar_shortcut_runtime, "shared", shared),
            ):
                self.assertFalse(
                    taskbar_shortcut_runtime._apply_shortcut_property_store(
                        shortcut,
                        app_id="com.tradingbot.desktop",
                        display_name="Trading Bot",
                        icon_path=None,
                    )
                )

            self.assertEqual(1, calls["commit_count"])
            self.assertEqual(1, calls["release_count"])

    def test_shortcut_creation_returns_path_only_after_metadata_and_save_succeed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "Trading Bot.exe"
            target.touch()
            shared, calls = self._shortcut_com_shared()
            with (
                mock.patch.object(taskbar_shortcut_runtime.sys, "platform", "win32"),
                mock.patch.dict("os.environ", {"APPDATA": tmp}, clear=False),
                mock.patch.object(taskbar_shortcut_runtime, "shared", shared),
                mock.patch.object(taskbar_shortcut_runtime, "_apply_shortcut_property_store", return_value=True),
            ):
                shortcut = taskbar_shortcut_runtime.ensure_start_menu_shortcut(
                    app_id="com.tradingbot.desktop",
                    display_name="Trading Bot",
                    target_path=target,
                    relaunch_command='"Trading Bot.exe" -m app.desktop.bootstrap.main',
                )

            self.assertEqual(
                root / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Trading Bot.lnk",
                shortcut,
            )
            self.assertEqual(1, calls["commit_count"])
            self.assertEqual(1, calls["link_release_count"])
            self.assertEqual(1, calls["store_release_count"])
            self.assertEqual(1, calls["persist_release_count"])

    def test_shortcut_creation_reports_persist_failure_after_releasing_com_objects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "Trading Bot.exe"
            target.touch()
            shared, calls = self._shortcut_com_shared(save_result=-1)
            with (
                mock.patch.object(taskbar_shortcut_runtime.sys, "platform", "win32"),
                mock.patch.dict("os.environ", {"APPDATA": tmp}, clear=False),
                mock.patch.object(taskbar_shortcut_runtime, "shared", shared),
                mock.patch.object(taskbar_shortcut_runtime, "_apply_shortcut_property_store") as apply_properties,
            ):
                self.assertIsNone(
                    taskbar_shortcut_runtime.ensure_start_menu_shortcut(
                        app_id="com.tradingbot.desktop",
                        display_name="Trading Bot",
                        target_path=target,
                    )
                )

            apply_properties.assert_not_called()
            self.assertEqual(1, calls["link_release_count"])
            self.assertEqual(1, calls["store_release_count"])
            self.assertEqual(1, calls["persist_release_count"])


if __name__ == "__main__":
    unittest.main()
