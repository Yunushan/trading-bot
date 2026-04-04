from __future__ import annotations

import concurrent.futures
import copy
import json
import re
import ssl
import sys
import time
import urllib.request
from pathlib import Path

from PyQt6 import QtCore, QtWidgets

from app.integrations.exchanges.binance import _normalize_connector_choice as _normalize_connector_backend
from .code_language_catalog import (
    BASE_PROJECT_PATH as _BASE_PROJECT_PATH,
    CPP_CODE_LANGUAGE_KEY,
    CPP_DEPENDENCY_VERSION_TARGETS as _CPP_DEPENDENCY_VERSION_TARGETS,
    DEFAULT_DEPENDENCY_VERSION_TARGETS as _DEFAULT_DEPENDENCY_VERSION_TARGETS,
    EXCHANGE_PATHS,
    FOREX_BROKER_PATHS,
    LANGUAGE_PATHS,
    REQUIREMENTS_PATHS as _REQUIREMENTS_PATHS,
    RUST_CODE_LANGUAGE_KEY,
    _rust_dependency_targets_for_config,
)

_CONNECTOR_DEPENDENCY_KEYS = {
    "python-binance",
    "binance-connector",
    "ccxt",
    "binance-sdk-derivatives-trading-usds-futures",
    "binance-sdk-derivatives-trading-coin-futures",
    "binance-sdk-spot",
}

_DEPENDENCY_MODULE_ALIASES = {
    "python-binance": ("binance",),
    "binance-connector": ("binance",),
    "ccxt": ("ccxt",),
    "pyqt6": ("PyQt6",),
    "pyqt6-qt6": ("PyQt6",),
    "pyqt6-webengine": ("PyQt6.QtWebEngineWidgets", "PyQt6.QtWebEngineCore"),
    "numba": ("numba",),
    "llvmlite": ("llvmlite",),
    "numpy": ("numpy",),
    "pandas": ("pandas",),
    "requests": ("requests",),
    "binance-sdk-derivatives-trading-usds-futures": ("binance_sdk_derivatives_trading_usds_futures",),
    "binance-sdk-derivatives-trading-coin-futures": ("binance_sdk_derivatives_trading_coin_futures",),
    "binance-sdk-spot": ("binance_sdk_spot",),
}

_DEPENDENCY_USAGE_ACTIVE_COLOR = "#16a34a"
_DEPENDENCY_USAGE_PASSIVE_COLOR = "#dc2626"
_DEPENDENCY_USAGE_PENDING_COLOR = "#d97706"
_DEPENDENCY_USAGE_UNKNOWN_COLOR = "#64748b"
_DEPENDENCY_USAGE_POLL_INTERVAL_MS = 1500
_LATEST_VERSION_CACHE: dict[str, tuple[str, float]] = {}


def _runtime():
    from . import dependency_versions_runtime as runtime

    return runtime


def _normalize_dependency_key(value: str | None) -> str:
    return str(value or "").strip().lower().replace("_", "-")


def _normalize_dependency_usage_text(usage: str | None) -> str:
    text = str(usage or "").strip().lower()
    if text == "active":
        return "Active"
    if text == "passive":
        return "Passive"
    if text == "checking...":
        return "Checking..."
    if text == "unknown":
        return "Unknown"
    if not text:
        return "Passive"
    return str(usage).strip()


def _dependency_usage_color(usage_text: str) -> str:
    normalized = str(usage_text or "").strip().lower()
    if normalized == "active":
        return _DEPENDENCY_USAGE_ACTIVE_COLOR
    if normalized == "passive":
        return _DEPENDENCY_USAGE_PASSIVE_COLOR
    if normalized == "checking...":
        return _DEPENDENCY_USAGE_PENDING_COLOR
    return _DEPENDENCY_USAGE_UNKNOWN_COLOR


def _set_dependency_usage_widget(widget: QtWidgets.QLabel | None, usage: str | None) -> None:
    if widget is None:
        return
    usage_text = _normalize_dependency_usage_text(usage)
    usage_color = _dependency_usage_color(usage_text)
    widget.setText(usage_text)
    widget.setStyleSheet(f"font-size: 11px; padding: 2px 4px 4px 4px; font-weight: 600; color: {usage_color};")


def _set_dependency_usage_counter_widget(widget: QtWidgets.QLabel | None, count: int | str | None) -> None:
    if widget is None:
        return
    try:
        count_value = max(0, int(count or 0))
    except Exception:
        count_value = 0
    widget.setText(str(count_value))
    widget.setStyleSheet("font-size: 11px; padding: 2px 4px 4px 4px; font-weight: 600;")


def _make_dependency_cell_copyable(widget: QtWidgets.QLabel | None) -> None:
    if widget is None:
        return
    try:
        widget.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
    except Exception:
        pass
    try:
        widget.setCursor(QtCore.Qt.CursorShape.IBeamCursor)
    except Exception:
        pass


def _apply_dependency_usage_entry(
    self,
    label: str,
    usage: str | None,
    *,
    widgets: tuple[QtWidgets.QLabel, QtWidgets.QLabel, QtWidgets.QLabel, QtWidgets.QLabel] | None = None,
    track_change: bool = True,
) -> None:
    if not label:
        return
    labels = getattr(self, "_dep_version_labels", None)
    if widgets is None:
        if not isinstance(labels, dict):
            return
        widgets = labels.get(label)
    if not widgets:
        return
    try:
        _, _, usage_widget, counter_widget = widgets
    except Exception:
        return

    usage_text = _normalize_dependency_usage_text(usage)
    normalized_usage = usage_text.lower()

    state_map = getattr(self, "_dep_usage_last_state", None)
    if not isinstance(state_map, dict):
        state_map = {}
        self._dep_usage_last_state = state_map
    count_map = getattr(self, "_dep_usage_change_counts", None)
    if not isinstance(count_map, dict):
        count_map = {}
        self._dep_usage_change_counts = count_map

    previous_state = str(state_map.get(label) or "").strip().lower()
    if track_change and previous_state in {"active", "passive"} and normalized_usage in {"active", "passive"}:
        if previous_state != normalized_usage:
            try:
                count_map[label] = max(0, int(count_map.get(label, 0))) + 1
            except Exception:
                count_map[label] = 1
    if normalized_usage in {"active", "passive"}:
        state_map[label] = normalized_usage

    _set_dependency_usage_widget(usage_widget, usage_text)
    _set_dependency_usage_counter_widget(counter_widget, count_map.get(label, 0))


def _dependency_module_candidates(target: dict[str, str]) -> tuple[str, ...]:
    package = _normalize_dependency_key(target.get("package"))
    label = _normalize_dependency_key(target.get("label"))
    key = package or label
    alias_candidates = _DEPENDENCY_MODULE_ALIASES.get(key)
    if alias_candidates:
        return alias_candidates
    raw = str(target.get("package") or target.get("label") or "").strip()
    if not raw:
        return tuple()
    return (raw.replace("-", "_"),)


def _dependency_usage_state(
    target: dict[str, str],
    *,
    config: dict | None = None,
    loaded_modules: set[str] | None = None,
) -> str:
    runtime = _runtime()
    custom = str(target.get("custom") or "").strip().lower()
    if custom.startswith("cpp_"):
        return runtime._cpp_custom_usage_value(target)
    if custom.startswith("rust_"):
        return runtime._rust_custom_usage_value(target)

    dependency_key = _normalize_dependency_key(target.get("package") or target.get("label"))
    if dependency_key in _CONNECTOR_DEPENDENCY_KEYS:
        backend_key = _normalize_connector_backend((config or {}).get("connector_backend"))
        return "Active" if dependency_key == backend_key else "Passive"

    modules = loaded_modules if loaded_modules is not None else set(sys.modules.keys())
    for module_name in _dependency_module_candidates(target):
        name = str(module_name or "").strip()
        if not name:
            continue
        if name in modules:
            return "Active"
        prefix = f"{name}."
        if any(loaded.startswith(prefix) for loaded in modules):
            return "Active"
    return "Passive"


def _refresh_dependency_usage_labels(
    self,
    targets: list[dict[str, str]] | None = None,
    *,
    config: dict | None = None,
) -> None:
    labels = getattr(self, "_dep_version_labels", None)
    if not labels:
        return
    target_list = targets or getattr(self, "_dep_version_targets", []) or []
    if not target_list:
        return
    try:
        config_snapshot = dict((config if config is not None else self.config) or {})
    except Exception:
        config_snapshot = {}
    loaded_modules = set(sys.modules.keys())
    usage_by_label: dict[str, str] = {}
    for target in target_list:
        label = str(target.get("label") or "").strip()
        if not label:
            continue
        usage_by_label[label] = _dependency_usage_state(
            target,
            config=config_snapshot,
            loaded_modules=loaded_modules,
        )
    for label, widgets in labels.items():
        _apply_dependency_usage_entry(
            self,
            label,
            usage_by_label.get(label, "Passive"),
            widgets=widgets,
            track_change=True,
        )


def _extract_requirement_name(line: str) -> str | None:
    stripped = (line or "").strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith(("-", "--")):
        return None
    if "#" in stripped:
        stripped = stripped.split("#", 1)[0].strip()
    if not stripped:
        return None
    separators = ("==", ">=", "<=", "~=", "!=", "===", "<", ">", "@")
    name_part = stripped
    for sep in separators:
        if sep in stripped:
            name_part = stripped.split(sep, 1)[0].strip()
            break
    if "[" in name_part:
        name_part = name_part.split("[", 1)[0].strip()
    return name_part or None


def _iter_candidate_requirement_paths(config: dict | None = None) -> list[Path]:
    candidates: list[Path] = []
    seen: set[Path] = set()

    def _add(path: Path | None):
        if path is None:
            return
        try:
            resolved = Path(path).resolve()
        except Exception:
            return
        if resolved in seen:
            return
        seen.add(resolved)
        candidates.append(resolved)

    _add(_BASE_PROJECT_PATH / "requirements.txt")
    lang_rel = None
    exch_rel = None
    forex_rel = None
    try:
        if config:
            lang_rel = LANGUAGE_PATHS.get(config.get("code_language"))
            exch_rel = EXCHANGE_PATHS.get(config.get("selected_exchange"))
            forex_rel = FOREX_BROKER_PATHS.get(config.get("selected_forex_broker"))
    except Exception:
        lang_rel = exch_rel = forex_rel = None

    if lang_rel:
        _add(_BASE_PROJECT_PATH / lang_rel / "requirements.txt")
        if exch_rel:
            _add(_BASE_PROJECT_PATH / lang_rel / exch_rel / "requirements.txt")
        if forex_rel:
            _add(_BASE_PROJECT_PATH / lang_rel / forex_rel / "requirements.txt")
    if exch_rel:
        _add(_BASE_PROJECT_PATH / exch_rel / "requirements.txt")

    for legacy in _REQUIREMENTS_PATHS:
        _add(legacy)
    return candidates


def _dependency_targets_from_requirements(paths: list[Path] | None = None) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    seen: set[str] = set()
    paths_to_check = paths or _REQUIREMENTS_PATHS
    for path in paths_to_check:
        if not path.is_file():
            continue
        try:
            with path.open("r", encoding="utf-8") as fh:
                for raw_line in fh:
                    pkg_name = _extract_requirement_name(raw_line)
                    if not pkg_name or pkg_name in seen:
                        continue
                    entries.append({"label": pkg_name, "package": pkg_name})
                    seen.add(pkg_name)
        except Exception:
            continue
    if not entries:
        return copy.deepcopy(_DEFAULT_DEPENDENCY_VERSION_TARGETS)
    return entries


def _resolve_dependency_targets_for_config(config: dict | None = None) -> list[dict[str, str]]:
    language_key = ""
    try:
        language_key = str((config or {}).get("code_language") or "").strip()
    except Exception:
        language_key = ""
    if language_key == CPP_CODE_LANGUAGE_KEY:
        return copy.deepcopy(_CPP_DEPENDENCY_VERSION_TARGETS)
    if language_key == RUST_CODE_LANGUAGE_KEY:
        return _rust_dependency_targets_for_config(config)
    return _dependency_targets_from_requirements(_iter_candidate_requirement_paths(config))


def _latest_version_from_pypi(package: str, timeout: float = 8.0) -> str | None:
    if not package:
        return None
    cache_entry = _LATEST_VERSION_CACHE.get(package)
    now = time.time()
    if cache_entry and now - cache_entry[1] < 1800:
        return cache_entry[0]
    url = f"https://pypi.org/pypi/{package}/json"
    timeout_val = max(2.0, float(timeout or 8.0))
    latest = None

    try:
        import requests  # type: ignore

        resp = requests.get(url, timeout=timeout_val, headers={"User-Agent": "trading-bot-starter/1.0"})
        if resp.status_code == 200:
            payload = resp.json()
            latest = payload.get("info", {}).get("version")
    except Exception:
        pass

    if latest is None:
        try:
            import requests  # type: ignore

            resp = requests.get(
                url,
                timeout=timeout_val,
                headers={"User-Agent": "trading-bot-starter/1.0"},
                verify=False,  # noqa: S501
            )
            if resp.status_code == 200:
                payload = resp.json()
                latest = payload.get("info", {}).get("version")
        except Exception:
            pass

    if latest is None:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "trading-bot-starter/1.0"})
            ctx = ssl.create_default_context()
            try:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            except Exception:
                pass
            with urllib.request.urlopen(req, timeout=timeout_val, context=ctx) as resp:
                payload = json.load(resp)
                latest = payload.get("info", {}).get("version")
        except Exception:
            latest = None

    if latest:
        _LATEST_VERSION_CACHE[package] = (latest, now)
        return latest
    return None


def _collect_dependency_versions(
    targets: list[dict[str, str]] | None = None,
    *,
    include_latest: bool = True,
    config: dict | None = None,
) -> list[tuple[str, str, str, str]]:
    runtime = _runtime()
    versions: list[tuple[str, str, str, str]] = []
    target_list = targets or runtime.DEPENDENCY_VERSION_TARGETS
    loaded_modules = set(sys.modules.keys())

    installed_map: dict[str, str] = {}
    for target in target_list:
        label = target["label"]
        installed_version = runtime._installed_version_for_dependency_target(target)
        if installed_version:
            installed_version = runtime._normalize_installed_version_text(installed_version) or installed_version
        installed_map[label] = installed_version or "Not installed"

    latest_map: dict[str, str] = {}
    if include_latest:
        max_workers = min(6, max(1, len(target_list)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_map: dict[str, concurrent.futures.Future] = {}
            for target in target_list:
                custom = str(target.get("custom") or "").strip().lower()
                if custom.startswith("cpp_"):
                    installed_display = installed_map.get(target["label"], "Unknown")
                    latest_map[target["label"]] = runtime._cpp_custom_latest_value(target, installed_display)
                    continue
                if custom.startswith("rust_"):
                    installed_display = installed_map.get(target["label"], "Unknown")
                    latest_map[target["label"]] = runtime._rust_custom_latest_value(target, installed_display)
                    continue
                if custom == "qt":
                    latest_map[target["label"]] = installed_map.get(target["label"], "Unknown")
                    continue
                pypi_name = target.get("pypi") or target.get("package")
                if not pypi_name:
                    continue
                future_map[target["label"]] = pool.submit(_latest_version_from_pypi, pypi_name)
            for label, fut in future_map.items():
                try:
                    latest_val = fut.result(timeout=10.0)
                except Exception:
                    latest_val = None
                latest_map[label] = latest_val or "Unknown"

    for target in target_list:
        label = target["label"]
        installed_display = installed_map.get(label, "Not installed")
        latest_display = latest_map.get(label, "Not checked" if not include_latest else "Unknown")
        usage_display = _dependency_usage_state(target, config=config, loaded_modules=loaded_modules)
        versions.append((label, installed_display, latest_display, usage_display))
    return versions
