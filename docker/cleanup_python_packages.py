"""Remove vulnerable Python distributions inherited from the base image."""

from __future__ import annotations

import shutil
import site
from pathlib import Path


TARGETS = {
    "setuptools-70.3.0": ("setuptools", "pkg_resources"),
    "msgpack-1.1.2": ("msgpack", "_msgpack"),
}
SCAN_ROOTS = (Path("/usr"), Path("/opt"))


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def _metadata_target(path: Path) -> str | None:
    name = path.name.lower()
    for target in TARGETS:
        if name.startswith(target) and name.endswith((".dist-info", ".egg-info")):
            return target
    return None


def main() -> None:
    roots = {Path(path) for path in site.getsitepackages()}
    roots.update(root for root in SCAN_ROOTS if root.exists())
    metadata = [
        path
        for root in roots
        for path in root.rglob("*")
        if path.is_dir() and _metadata_target(path) is not None
    ]

    removed: list[str] = []
    for metadata_path in sorted(set(metadata), key=lambda path: len(path.parts), reverse=True):
        target = _metadata_target(metadata_path)
        if target is None:
            continue
        parent = metadata_path.parent
        _remove(metadata_path)
        removed.append(str(metadata_path))

        # Do not remove package code from a directory that also contains a
        # newer distribution copied into the runtime venv.
        newer_metadata = any(
            sibling.is_dir()
            and sibling != metadata_path
            and sibling.name.lower().startswith(target.split("-", 1)[0] + "-")
            and sibling.name.lower().endswith((".dist-info", ".egg-info"))
            for sibling in parent.iterdir()
        )
        if not newer_metadata:
            for package_name in TARGETS[target]:
                package_path = parent / package_name
                if package_path.exists() or package_path.is_symlink():
                    _remove(package_path)
                    removed.append(str(package_path))

    remaining = [
        path
        for root in roots
        for path in root.rglob("*")
        if path.is_dir() and _metadata_target(path) is not None
    ]
    if remaining:
        raise RuntimeError(f"vulnerable Python metadata remains: {remaining}")

    print(f"Removed {len(removed)} vulnerable base-layer Python paths.")
    Path(__file__).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
