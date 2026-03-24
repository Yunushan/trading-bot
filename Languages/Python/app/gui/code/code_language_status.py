from __future__ import annotations

from PyQt6 import QtCore

from . import code_language_runtime
from .code_language_catalog import (
    CPP_CODE_LANGUAGE_KEY,
    PYTHON_CODE_LANGUAGE_KEY,
    RUST_CODE_LANGUAGE_KEY,
)


def rust_runtime_release_line(
    config: dict | None = None,
    *,
    rust_project_version,
    rust_tool_version,
    rust_framework_title,
    rust_framework_key,
    rust_manifest_path,
) -> str:
    release_text = rust_project_version()
    rustc_version = rust_tool_version(["rustc", "--version"], cache_key="rustc")
    framework_title = rust_framework_title(config)
    framework_prefix = f"{framework_title} | " if rust_framework_key(config) else ""
    if release_text and rustc_version:
        return f"{framework_prefix}Release: {release_text} | rustc {rustc_version}"
    if release_text:
        return f"{framework_prefix}Release: {release_text}"
    if rust_manifest_path().is_file() and rustc_version:
        return f"{framework_prefix}Release: Scaffolded | rustc {rustc_version}"
    if rust_manifest_path().is_file():
        return f"{framework_prefix}Release: Scaffolded"
    return f"{framework_prefix}Release: Not initialized"


def apply_code_language_card_release_lines(self, *, release_lines: dict[str, str] | None = None) -> None:
    cards = getattr(self, "_starter_language_cards", None)
    if not isinstance(cards, dict) or not cards:
        return
    base_subtitles = getattr(self, "_starter_language_base_subtitles", None)
    if not isinstance(base_subtitles, dict):
        base_subtitles = {}

    resolved_lines = release_lines if isinstance(release_lines, dict) else {}
    for key, card in cards.items():
        if card is None:
            continue
        base_text = str(base_subtitles.get(key) or "").strip()
        release_text = str(resolved_lines.get(key) or "").strip()
        subtitle_text = base_text
        if release_text:
            subtitle_text = f"{base_text}\n{release_text}" if base_text else release_text
        try:
            card.subtitle_label.setText(subtitle_text)
        except Exception:
            pass


def refresh_code_language_card_release_labels(self, *, rust_release_line: str) -> None:
    release_lines = {
        PYTHON_CODE_LANGUAGE_KEY: code_language_runtime.python_runtime_release_line(),
        CPP_CODE_LANGUAGE_KEY: code_language_runtime.cpp_runtime_release_line(),
        RUST_CODE_LANGUAGE_KEY: str(rust_release_line or "").strip(),
    }
    apply_code_language_card_release_lines(self, release_lines=release_lines)


def _ensure_process_watchdog(self, *, timer_attr: str, callback) -> None:
    timer = getattr(self, timer_attr, None)
    if timer is None:
        try:
            timer = QtCore.QTimer(self)
            timer.setInterval(1000)
            timer.timeout.connect(callback)
            setattr(self, timer_attr, timer)
        except Exception:
            return
    try:
        if not timer.isActive():
            timer.start()
    except Exception:
        pass


def _poll_code_language_process_state(
    self,
    *,
    process_attr: str,
    active_code_language_key: str,
    language_label: str,
) -> None:
    proc = getattr(self, process_attr, None)
    if proc is None:
        return
    try:
        exit_code = proc.poll()
    except Exception:
        exit_code = 0
    if exit_code is None:
        return

    setattr(self, process_attr, None)
    switched_to_python = False
    try:
        if self.config.get("code_language") == active_code_language_key:
            self.config["code_language"] = PYTHON_CODE_LANGUAGE_KEY
            switched_to_python = True
    except Exception:
        switched_to_python = False

    if switched_to_python:
        try:
            self._refresh_code_tab_from_config()
        except Exception:
            pass
        try:
            self.log(f"{language_label} bot exited (code {exit_code}). Switched code language to Python.")
        except Exception:
            pass


def ensure_cpp_process_watchdog(self) -> None:
    return _ensure_process_watchdog(
        self,
        timer_attr="_cpp_process_watchdog_timer",
        callback=self._poll_cpp_process_state,
    )


def poll_cpp_process_state(self) -> None:
    return _poll_code_language_process_state(
        self,
        process_attr="_cpp_code_tab_process",
        active_code_language_key=CPP_CODE_LANGUAGE_KEY,
        language_label="C++",
    )


def ensure_rust_process_watchdog(self) -> None:
    return _ensure_process_watchdog(
        self,
        timer_attr="_rust_process_watchdog_timer",
        callback=self._poll_rust_process_state,
    )


def poll_rust_process_state(self) -> None:
    return _poll_code_language_process_state(
        self,
        process_attr="_rust_code_tab_process",
        active_code_language_key=RUST_CODE_LANGUAGE_KEY,
        language_label="Rust",
    )
