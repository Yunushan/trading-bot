from __future__ import annotations

import os
import threading
import time

from PyQt6 import QtCore

from . import code_language_runtime

_CPP_AUTO_SETUP_DEFAULT_COOLDOWN_SEC = 300.0


def _runtime():
    from . import dependency_versions_runtime as runtime

    return runtime


def _cpp_auto_setup_enabled() -> bool:
    raw_value = str(os.environ.get("TB_CPP_AUTO_SETUP", "1") or "1").strip().lower()
    return raw_value not in {"0", "false", "no", "off"}


def _cpp_auto_setup_cooldown_seconds() -> float:
    raw_value = str(os.environ.get("TB_CPP_AUTO_SETUP_COOLDOWN_SEC", "") or "").strip()
    if not raw_value:
        return _CPP_AUTO_SETUP_DEFAULT_COOLDOWN_SEC
    try:
        return max(0.0, float(raw_value))
    except Exception:
        return _CPP_AUTO_SETUP_DEFAULT_COOLDOWN_SEC


def _tail_text(value: str | None, *, max_lines: int = 20, max_chars: int = 4000) -> str:
    text = str(value or "")
    lines = [line for line in text.splitlines() if line.strip()]
    if lines:
        text = "\n".join(lines[-max_lines:])
    text = text.strip()
    if len(text) > max_chars:
        text = text[-max_chars:]
    return text


def _cpp_auto_prepare_environment_result(
    *,
    reason: str,
    targets: list[dict[str, str]] | None = None,
    install_when_missing: bool = True,
) -> dict[str, object]:
    runtime = _runtime()
    target_list = runtime._cpp_env_dependency_targets(targets)
    missing_before = runtime._cpp_missing_dependency_labels(target_list)
    attempted = False
    install_ok = True
    install_output = ""

    if missing_before and install_when_missing and _cpp_auto_setup_enabled():
        attempted = True
        install_ok, install_output = runtime._cpp_run_dependency_installer()

    runtime._reset_cpp_dependency_caches()
    missing_after = runtime._cpp_missing_dependency_labels(target_list)

    return {
        "reason": str(reason or "").strip(),
        "attempted": attempted,
        "install_ok": bool(install_ok),
        "missing_before": list(missing_before),
        "missing_after": list(missing_after),
        "ready": not missing_after,
        "install_output": _tail_text(install_output),
    }


def _apply_cpp_auto_prepare_result(
    self,
    result: dict | None,
    *,
    refresh_versions: bool = True,
) -> None:
    runtime = _runtime()
    payload = result if isinstance(result, dict) else {}
    attempted = bool(payload.get("attempted"))
    install_ok = bool(payload.get("install_ok", True))
    ready = bool(payload.get("ready"))
    reason = str(payload.get("reason") or "").strip() or "cpp-auto-setup"
    missing_before = payload.get("missing_before") if isinstance(payload.get("missing_before"), list) else []
    missing_after = payload.get("missing_after") if isinstance(payload.get("missing_after"), list) else []
    install_output = str(payload.get("install_output") or "").strip()

    if attempted and ready:
        missing_text = ", ".join(str(item) for item in missing_before) if missing_before else "dependencies"
        self.log(f"C++ dependency auto-setup ({reason}) completed: {missing_text}")
    elif attempted and not ready:
        missing_text = ", ".join(str(item) for item in missing_after) if missing_after else "unknown"
        self.log(f"C++ dependency auto-setup ({reason}) did not complete fully. Missing: {missing_text}")
        if install_output:
            self.log(_tail_text(install_output, max_lines=12, max_chars=1800))
    elif not ready and not _cpp_auto_setup_enabled():
        missing_text = ", ".join(str(item) for item in missing_after) if missing_after else "unknown"
        self.log(f"C++ auto-setup is disabled (TB_CPP_AUTO_SETUP=0). Missing: {missing_text}")
    elif not ready and not install_ok and install_output:
        self.log(_tail_text(install_output, max_lines=12, max_chars=1800))

    if refresh_versions:
        runtime._reset_cpp_dependency_caches()
        try:
            QtCore.QTimer.singleShot(0, self._refresh_dependency_versions)
        except Exception:
            pass


def _maybe_auto_prepare_cpp_environment(
    self,
    *,
    resolved_targets: list[dict[str, str]] | None = None,
    reason: str = "code-tab",
    force: bool = False,
) -> bool:
    runtime = _runtime()
    if code_language_runtime.is_frozen_python_app():
        return False
    if not _cpp_auto_setup_enabled():
        return False

    cpp_targets = runtime._cpp_env_dependency_targets(resolved_targets)
    if not cpp_targets:
        return False

    if getattr(self, "_cpp_auto_setup_inflight", False):
        return False

    now = time.time()
    cooldown_sec = _cpp_auto_setup_cooldown_seconds()
    last_attempt = float(getattr(self, "_cpp_auto_setup_last_attempt_at", 0.0) or 0.0)
    if not force and cooldown_sec > 0.0 and now - last_attempt < cooldown_sec:
        return False

    missing_now = runtime._cpp_missing_dependency_labels(cpp_targets)
    if not missing_now:
        return False

    self._cpp_auto_setup_inflight = True
    self._cpp_auto_setup_last_attempt_at = now
    self.log(f"C++ dependencies missing ({reason}): {', '.join(missing_now)}. Starting automatic setup...")

    def _worker():
        result = _cpp_auto_prepare_environment_result(
            reason=reason,
            targets=cpp_targets,
            install_when_missing=True,
        )
        try:
            QtCore.QMetaObject.invokeMethod(
                self,
                "_on_cpp_auto_prepare_finished",
                QtCore.Qt.ConnectionType.QueuedConnection,
                QtCore.Q_ARG(object, result),
            )
        except Exception:
            self._cpp_auto_setup_inflight = False

    threading.Thread(target=_worker, daemon=True).start()
    return True
