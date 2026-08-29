from __future__ import annotations

import re
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.10 without tomli
    try:
        import tomli as tomllib  # type: ignore[import-not-found]
    except ModuleNotFoundError:  # pragma: no cover - minimal parser handles this deployment case
        tomllib = None  # type: ignore[assignment]


PYQT6_PACKAGE_KEYS = (
    "pyqt6",
    "pyqt6-qt6",
    "pyqt6-webengine",
    "pyqt6-webengine-qt6",
)
VersionTuple = tuple[int, int, int]

_VERSION_RE = re.compile(
    r"^\s*(\d+)\.(\d+)(?:\.(\d+))?(?:(?:[A-Za-z][A-Za-z0-9.-]*)|(?:[-+.][A-Za-z0-9.-]*))?\s*$"
)


def canonical_package_name(value: object) -> str:
    return re.sub(r"[-_.]+", "-", str(value or "").strip().lower())


def package_key(value: object) -> str | None:
    canonical = canonical_package_name(value)
    return canonical if canonical in PYQT6_PACKAGE_KEYS else None


def parse_release_version(value: object) -> VersionTuple | None:
    match = _VERSION_RE.fullmatch(str(value or ""))
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)


def _fallback_contract(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    in_contract = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("[") and line.endswith("]"):
            in_contract = line == "[tool.trading-bot.pyqt6]"
            continue
        if not in_contract or "=" not in line:
            continue
        key, raw_value = (part.strip() for part in line.split("=", 1))
        if key not in {"minimum_version", "maximum_version_exclusive", "future_target_version"}:
            continue
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            values[key] = value[1:-1].strip()
    return values


def load_contract(pyproject_path: Path | None = None) -> dict[str, str]:
    path = pyproject_path or Path(__file__).resolve().parents[3] / "pyproject.toml"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}

    if tomllib is None:
        return _fallback_contract(text)
    try:
        document = tomllib.loads(text)
    except Exception:
        return _fallback_contract(text)
    tool = document.get("tool") if isinstance(document.get("tool"), dict) else {}
    trading_bot = tool.get("trading-bot") if isinstance(tool.get("trading-bot"), dict) else {}
    contract = trading_bot.get("pyqt6") if isinstance(trading_bot.get("pyqt6"), dict) else {}
    return {
        key: str(contract.get(key) or "").strip()
        for key in ("minimum_version", "maximum_version_exclusive", "future_target_version")
    }


def reviewed_version_bounds(
    contract: dict[str, str] | None = None,
) -> tuple[VersionTuple, VersionTuple] | None:
    values = contract if contract is not None else load_contract()
    minimum = parse_release_version(values.get("minimum_version"))
    maximum = parse_release_version(values.get("maximum_version_exclusive"))
    if minimum is None or maximum is None or minimum >= maximum:
        return None
    return minimum, maximum
