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


def _platform_name() -> str:
    return str(platform.system() or "").strip().casefold()


def credential_store_backend() -> str:
    system = _platform_name()
    if os.name == "nt" or system == "windows":
        return "windows-credential-manager"
    if system == "darwin":
        return "macos-keychain" if shutil.which("security") else "unavailable"
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
        # The macOS security utility has no stdin value mode for generic passwords.
        # Do not log this command or its arguments: the value is intentionally transient.
        result = _run_secret_command(
            ["security", "add-generic-password", "-a", _KEYCHAIN_ACCOUNT, "-s", target, "-w", str(value), "-U"]
        )
        if result.returncode:
            raise _command_error("macOS Keychain write", result)
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
        result = _run_secret_command(["security", "find-generic-password", "-a", _KEYCHAIN_ACCOUNT, "-s", target, "-w"])
        if result.returncode:
            return ""
        return str(result.stdout or "").rstrip("\r\n")
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
        result = _run_secret_command(["security", "delete-generic-password", "-a", _KEYCHAIN_ACCOUNT, "-s", target])
        if result.returncode and "could not be found" not in str(result.stderr or "").casefold():
            raise _command_error("macOS Keychain delete", result)
        return
    if backend == "linux-secret-service":
        result = _run_secret_command(["secret-tool", "clear", "service", "trading-bot", "target", target])
        if result.returncode:
            raise _command_error("Linux Secret Service delete", result)
        return
    raise CredentialStoreUnavailable("No supported OS credential store is available on this platform.")
