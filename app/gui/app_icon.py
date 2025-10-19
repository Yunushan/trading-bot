from __future__ import annotations

import base64
import os
import sys
from functools import lru_cache
from importlib import resources as _resources
from pathlib import Path

from PyQt6 import QtGui

_ICON_FILENAMES_WINDOWS = ("binance_icon.ico", "binance_icon.png")
_ICON_FILENAMES_UNIX = ("binance_icon.png", "binance_icon.ico")
_COMMON_FALLBACKS = ("binance_icon.svg",)

FALLBACK_ICON_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAgAAAAIACAYAAAD0eNT6AAAYPklEQVR4nO3dsY5d13XH4a1IgJVAALsAbFxEDxCA"
    "8xAs3PIV3Lh0wYdg4TKNX0FtCr4EgfRxCjcE3BEQArkQlII+GY54OXPvOWfvvdZe39c5keQ7gz3r//MQcb66u7v7"
    "pQEApfzT7A8AAIwnAACgIAEAAAUJAAAoSAAAQEECAAAKEgAAUJAAAICCBAAAFCQAAKAgAQAABQkAAChIAABAQQIA"
    "AAoSAABQkAAAgIIEAAAUJAAAoCABAAAFCQAAKEgAAEBBAgAAChIAAFCQAACAggQAABQkAACgIAEAAAUJAAAoSAAA"
    "QEECAAAKEgAAUJAAAICCBAAAFCQAAKAgAQAABQkAAChIAABAQQIAAAoSAABQkAAAgIIEAAAUJAAAoCABAAAFCQAA"
    "KEgAAEBBAgAAChIAAFCQAACAggQAABQkAACgIAEAAAUJAAAoSAAAQEECAAAKEgAAUJAAAICCBAAAFCQAAKAgAQAA"
    "BQkAAChIAABAQQIAAAoSAABQkAAAgIIEAAAUJAAAoCABAAAFCQAAKEgAAEBBAgAAChIAAFCQAACAggQAABQkAACg"
    "IAEAAAUJAAAoSAAAQEECAAAKEgAAUJAAAICCBAAAFCQAAKAgAQAABQkAAChIAABAQQIAAAoSAABQkAAAgIIEAAAU"
    "JAAAoCABAAAFCQAAKEgAAEBBAgAAChIAAFCQAACAggQAABQkAACgIAEAAAUJAAAoSAAAQEECAAAKEgAAUJAAAICC"
    "BAAAFCQAAKAgAQAABQkAAChIAABAQQIAAAoSAABQkAAAgIIEAAAUJAAAoCABAAAFCQAAKEgAAEBBAgAAChIAAFCQ"
    "AACAggQAABQkAACgIAEAAAUJAAAoSAAAQEECAAAKEgAAUJAAAICCBAAAFCQAAKAgAQAABQkAAChIAABAQQIAAAoS"
    "AABQkAAAgIIEAAAUJAAAoCABAAAFCQAAKEgAAEBBAgAAChIAAFCQAACAggQAABQkAACgIAEAAAUJAAAoSAAAQEECA"
    "AAKEgAAUJAAAICCBAAAFCQAAKAgAQAABQkAAChIAABAQQIAAAoSAABQkAAAgIIEAAAUJAAAoCABAAAFCQAAKEgAA"
    "EBBAgAAChIAAFCQAACAggQAABQkAACgoP8DyvnXGJ6q+6wAAAAASUVORK5CYII="
)


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

    try:
        exe_path = Path(sys.argv[0]).resolve()
    except Exception:
        exe_path = None
    if exe_path:
        exe_dir = exe_path.parent
        candidates.extend([
            exe_dir / "app" / "assets",
            exe_dir / "assets",
            exe_dir,
            exe_dir.parent / "assets",
        ])

    env_assets = os.getenv("BINANCE_BOT_ASSETS")
    if env_assets:
        candidates.append(Path(env_assets))

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


def _icon_from_path(path: Path) -> QtGui.QIcon:
    """Attempt to build an icon from the given path using multiple strategies."""
    icon = QtGui.QIcon(str(path))
    if not icon.isNull():
        return icon
    suffix = path.suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".bmp", ".svg"}:
        try:
            pixmap = QtGui.QPixmap(str(path))
            if not pixmap.isNull():
                icon = QtGui.QIcon(pixmap)
                if not icon.isNull():
                    return icon
        except Exception:
            pass
    return QtGui.QIcon()

def _load_from_package_resources() -> QtGui.QIcon | None:
    try:
        files = _resources.files("app.assets")
    except Exception:
        return None
    for filename in _icon_filename_candidates():
        try:
            resource = files.joinpath(filename)
        except FileNotFoundError:
            continue
        try:
            with _resources.as_file(resource) as tmp_path:
                candidate = _icon_from_path(tmp_path)
                if not candidate.isNull():
                    return candidate
        except FileNotFoundError:
            pass
        try:
            data = _resources.read_binary("app.assets", filename)
            pixmap = QtGui.QPixmap()
            if pixmap.loadFromData(data):
                icon = QtGui.QIcon(pixmap)
                if not icon.isNull():
                    return icon
        except Exception:
            continue
    return None


@lru_cache(maxsize=1)
def load_app_icon() -> QtGui.QIcon:
    """Load the Binance app icon with platform-aware fallbacks."""
    icon = _load_from_package_resources()
    if icon and not icon.isNull():
        return icon
    for directory in _candidate_directories():
        for filename in _icon_filename_candidates():
            path = directory / filename
            if not path.exists():
                continue
            candidate = _icon_from_path(path)
            if not candidate.isNull():
                return candidate
    theme_icon = QtGui.QIcon.fromTheme("binance")
    if theme_icon and not theme_icon.isNull():
        return theme_icon
    try:
        data = base64.b64decode(FALLBACK_ICON_PNG)
        pixmap = QtGui.QPixmap()
        if pixmap.loadFromData(data):
            icon = QtGui.QIcon(pixmap)
            if not icon.isNull():
                return icon
    except Exception:
        pass
    fallback_pixmap = QtGui.QPixmap(64, 64)
    fallback_pixmap.fill(QtGui.QColor("#F3BA2F"))
    painter = QtGui.QPainter(fallback_pixmap)
    try:
        painter.setPen(QtGui.QPen(QtGui.QColor("#1F1F1F"), 6))
        painter.drawEllipse(6, 6, 52, 52)
    finally:
        painter.end()
    return QtGui.QIcon(fallback_pixmap)
