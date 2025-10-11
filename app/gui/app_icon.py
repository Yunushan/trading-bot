from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

from PyQt6 import QtGui

_ICON_FILENAMES_WINDOWS = ("binance_icon.ico", "binance_icon.png")
_ICON_FILENAMES_UNIX = ("binance_icon.png", "binance_icon.ico")
_COMMON_FALLBACKS = ("binance_icon.svg",)


def _candidate_directories() -> list[Path]:
    """Return asset directories to probe, ordered by likelihood."""
    here = Path(__file__).resolve()
    app_dir = here.parent.parent
    project_dir = app_dir.parent
    candidates: list[Path] = []

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        meipass_path = Path(meipass)
        candidates.extend([
            meipass_path / "app" / "assets",
            meipass_path / "assets",
            meipass_path,
        ])

    candidates.extend([
        app_dir / "assets",
        here.parent / "assets",
        project_dir / "app" / "assets",
        project_dir / "assets",
        Path.cwd() / "app" / "assets",
        Path.cwd() / "assets",
    ])

    seen: set[Path] = set()
    ordered: list[Path] = []
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            ordered.append(candidate)
    return ordered


def _icon_filename_candidates() -> tuple[str, ...]:
    if sys.platform.startswith("win"):
        return _ICON_FILENAMES_WINDOWS + _COMMON_FALLBACKS
    return _ICON_FILENAMES_UNIX + _COMMON_FALLBACKS


@lru_cache(maxsize=1)
def load_app_icon() -> QtGui.QIcon:
    """Load the Binance app icon with platform-aware fallbacks."""
    icon = QtGui.QIcon()
    for directory in _candidate_directories():
        for filename in _icon_filename_candidates():
            path = directory / filename
            if not path.exists():
                continue
            candidate = QtGui.QIcon(str(path))
            if not candidate.isNull():
                return candidate
    theme_icon = QtGui.QIcon.fromTheme("binance")
    if theme_icon and not theme_icon.isNull():
        return theme_icon
    return icon
