from __future__ import annotations

from pathlib import Path


def jsonl_backup_path(path: Path, index: int = 1) -> Path:
    return path.with_name(f"{path.name}.{max(1, int(index))}")


def rotate_jsonl_if_needed(
    path: Path,
    incoming_bytes: int,
    *,
    max_bytes: int | None,
    backup_count: int = 1,
) -> bool:
    if max_bytes is None or max_bytes <= 0 or backup_count < 0:
        return False
    path = Path(path).expanduser()
    try:
        current_size = path.stat().st_size
    except FileNotFoundError:
        return False
    if current_size + max(0, int(incoming_bytes or 0)) <= max_bytes:
        return False

    if backup_count == 0:
        path.unlink(missing_ok=True)
        return True

    path.parent.mkdir(parents=True, exist_ok=True)
    for index in range(int(backup_count), 0, -1):
        source = path if index == 1 else jsonl_backup_path(path, index - 1)
        target = jsonl_backup_path(path, index)
        if not source.exists():
            continue
        if target.exists():
            target.unlink()
        source.replace(target)
    return True
