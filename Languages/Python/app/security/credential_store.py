"""Minimal OS credential-store boundary used by persisted service configuration."""

from __future__ import annotations

import ctypes
import os
import platform
import shutil
import subprocess
from ctypes import wintypes


class CredentialStoreUnavailable(RuntimeError):
    """Raised when the current platform has no supported secure credential store."""


_CRED_TYPE_GENERIC = 1
_CRED_PERSIST_LOCAL_MACHINE = 2
_KEYCHAIN_ACCOUNT = "trading-bot-service-config"
_LINUX_SECRET_LABEL = "Trading Bot service configuration"
_ERR_SEC_ITEM_NOT_FOUND = -25300


def _platform_name() -> str:
    return str(platform.system() or "").strip().casefold()


def credential_store_backend() -> str:
    system = _platform_name()
    if os.name == "nt" or system == "windows":
        return "windows-credential-manager"
    if system == "darwin":
        return "macos-keychain"
    if system == "linux":
        return "linux-secret-service" if shutil.which("secret-tool") else "unavailable"
    return "unavailable"


def _target_name(scope: str, account: str) -> str:
    return f"TradingBot/{scope}/{account}"


def _run_secret_command(command: list[str], *, input_value: str | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            input=input_value,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        raise CredentialStoreUnavailable(f"Could not run the OS credential-store command: {command[0]}") from exc


def _command_error(command: str, result: subprocess.CompletedProcess[str]) -> OSError:
    detail = str(result.stderr or result.stdout or "credential-store command failed").strip()
    return OSError(f"{command} failed with exit code {result.returncode}: {detail}")


def _windows_api():
    if os.name != "nt":
        raise CredentialStoreUnavailable("No supported OS credential store is available on this platform.")

    class _FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

    class _CREDENTIALW(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", _FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    advapi32 = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    advapi32.CredWriteW.argtypes = (ctypes.POINTER(_CREDENTIALW), wintypes.DWORD)
    advapi32.CredWriteW.restype = wintypes.BOOL
    advapi32.CredReadW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(_CREDENTIALW)))
    advapi32.CredReadW.restype = wintypes.BOOL
    advapi32.CredFree.argtypes = (ctypes.c_void_p,)
    advapi32.CredFree.restype = None
    advapi32.CredDeleteW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD)
    advapi32.CredDeleteW.restype = wintypes.BOOL
    return advapi32, _CREDENTIALW


def _macos_keychain_api():
    if _platform_name() != "darwin":
        raise CredentialStoreUnavailable("No supported OS credential store is available on this platform.")
    try:
        security = ctypes.CDLL("/System/Library/Frameworks/Security.framework/Security")
        core_foundation = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
    except OSError as exc:
        raise CredentialStoreUnavailable("The macOS Keychain framework is unavailable.") from exc

    security.SecKeychainAddGenericPassword.argtypes = (
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    )
    security.SecKeychainAddGenericPassword.restype = ctypes.c_int32
    security.SecKeychainFindGenericPassword.argtypes = (
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
    )
    security.SecKeychainFindGenericPassword.restype = ctypes.c_int32
    security.SecKeychainItemModifyAttributesAndData.argtypes = (
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
    )
    security.SecKeychainItemModifyAttributesAndData.restype = ctypes.c_int32
    security.SecKeychainItemDelete.argtypes = (ctypes.c_void_p,)
    security.SecKeychainItemDelete.restype = ctypes.c_int32
    security.SecKeychainItemFreeContent.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
    security.SecKeychainItemFreeContent.restype = ctypes.c_int32
    core_foundation.CFRelease.argtypes = (ctypes.c_void_p,)
    core_foundation.CFRelease.restype = None
    return security, core_foundation


def _macos_keychain_identity(target: str) -> tuple[bytes, bytes]:
    return target.encode("utf-8"), _KEYCHAIN_ACCOUNT.encode("utf-8")


def _macos_keychain_find(target: str):
    security, core_foundation = _macos_keychain_api()
    service, account = _macos_keychain_identity(target)
    password_size = ctypes.c_uint32()
    password_data = ctypes.c_void_p()
    item = ctypes.c_void_p()
    status = security.SecKeychainFindGenericPassword(
        None,
        len(service),
        service,
        len(account),
        account,
        ctypes.byref(password_size),
        ctypes.byref(password_data),
        ctypes.byref(item),
    )
    return security, core_foundation, status, password_size, password_data, item


def _macos_keychain_release(core_foundation, item: ctypes.c_void_p) -> None:
    if item.value:
        core_foundation.CFRelease(item)


def put_secret(*, scope: str, account: str, value: str) -> None:
    raw = str(value).encode("utf-8")
    if not raw:
        return
    backend = credential_store_backend()
    target = _target_name(scope, account)
    if backend == "windows-credential-manager":
        if len(raw) > 2560:
            raise ValueError("Credential value exceeds the Windows Credential Manager generic credential limit.")
        advapi32, credential_type = _windows_api()
        blob = (ctypes.c_byte * len(raw)).from_buffer_copy(raw)
        credential = credential_type()
        credential.Type = _CRED_TYPE_GENERIC
        credential.TargetName = target
        credential.CredentialBlobSize = len(raw)
        credential.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_byte))
        credential.Persist = _CRED_PERSIST_LOCAL_MACHINE
        credential.UserName = account
        if not advapi32.CredWriteW(ctypes.byref(credential), 0):
            raise OSError(ctypes.get_last_error(), "CredWriteW failed")
        return
    if backend == "macos-keychain":
        security, core_foundation, status, _size, password_data, item = _macos_keychain_find(target)
        try:
            if password_data.value:
                security.SecKeychainItemFreeContent(None, password_data)
            if status not in (_ERR_SEC_ITEM_NOT_FOUND, 0):
                raise OSError(status, "SecKeychainFindGenericPassword failed")
            if status == 0:
                status = security.SecKeychainItemModifyAttributesAndData(item, None, len(raw), raw)
            else:
                service, keychain_account = _macos_keychain_identity(target)
                status = security.SecKeychainAddGenericPassword(
                    None,
                    len(service),
                    service,
                    len(keychain_account),
                    keychain_account,
                    len(raw),
                    raw,
                    ctypes.byref(item),
                )
            if status:
                raise OSError(status, "macOS Keychain write failed")
        finally:
            _macos_keychain_release(core_foundation, item)
        return
    if backend == "linux-secret-service":
        result = _run_secret_command(
            ["secret-tool", "store", "--label", _LINUX_SECRET_LABEL, "service", "trading-bot", "target", target],
            input_value=str(value),
        )
        if result.returncode:
            raise _command_error("Linux Secret Service write", result)
        return
    raise CredentialStoreUnavailable("No supported OS credential store is available on this platform.")


def get_secret(*, scope: str, account: str) -> str:
    backend = credential_store_backend()
    target = _target_name(scope, account)
    if backend == "windows-credential-manager":
        advapi32, credential_type = _windows_api()
        credential_pointer = ctypes.POINTER(credential_type)()
        if not advapi32.CredReadW(target, _CRED_TYPE_GENERIC, 0, ctypes.byref(credential_pointer)):
            error = ctypes.get_last_error()
            if error == 1168:  # ERROR_NOT_FOUND
                return ""
            raise OSError(error, "CredReadW failed")
        try:
            credential = credential_pointer.contents
            if not credential.CredentialBlob or not credential.CredentialBlobSize:
                return ""
            return ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize).decode("utf-8")
        finally:
            advapi32.CredFree(credential_pointer)
    if backend == "macos-keychain":
        security, core_foundation, status, password_size, password_data, item = _macos_keychain_find(target)
        try:
            if status == _ERR_SEC_ITEM_NOT_FOUND:
                return ""
            if status:
                raise OSError(status, "SecKeychainFindGenericPassword failed")
            if not password_data.value or not password_size.value:
                return ""
            return ctypes.string_at(password_data, password_size.value).decode("utf-8")
        finally:
            if password_data.value:
                security.SecKeychainItemFreeContent(None, password_data)
            _macos_keychain_release(core_foundation, item)
    if backend == "linux-secret-service":
        result = _run_secret_command(["secret-tool", "lookup", "service", "trading-bot", "target", target])
        if result.returncode:
            return ""
        return str(result.stdout or "").rstrip("\r\n")
    raise CredentialStoreUnavailable("No supported OS credential store is available on this platform.")


def delete_secret(*, scope: str, account: str) -> None:
    backend = credential_store_backend()
    target = _target_name(scope, account)
    if backend == "windows-credential-manager":
        advapi32, _credential_type = _windows_api()
        if not advapi32.CredDeleteW(target, _CRED_TYPE_GENERIC, 0):
            error = ctypes.get_last_error()
            if error != 1168:  # ERROR_NOT_FOUND
                raise OSError(error, "CredDeleteW failed")
        return
    if backend == "macos-keychain":
        security, core_foundation, status, _size, password_data, item = _macos_keychain_find(target)
        try:
            if status == _ERR_SEC_ITEM_NOT_FOUND:
                return
            if status:
                raise OSError(status, "SecKeychainFindGenericPassword failed")
            status = security.SecKeychainItemDelete(item)
            if status:
                raise OSError(status, "SecKeychainItemDelete failed")
        finally:
            if password_data.value:
                security.SecKeychainItemFreeContent(None, password_data)
            _macos_keychain_release(core_foundation, item)
        return
    if backend == "linux-secret-service":
        result = _run_secret_command(["secret-tool", "clear", "service", "trading-bot", "target", target])
        if result.returncode:
            raise _command_error("Linux Secret Service delete", result)
        return
    raise CredentialStoreUnavailable("No supported OS credential store is available on this platform.")
