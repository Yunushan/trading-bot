"""Write a deterministic, non-secret digest manifest for release artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_revision(root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "unknown"


def build_manifest(root: Path, artifacts: list[Path]) -> dict[str, object]:
    resolved_root = root.resolve()
    rows = []
    for artifact in sorted((item.resolve() for item in artifacts), key=lambda item: item.name.lower()):
        if not artifact.is_file():
            raise FileNotFoundError(f"Release artifact not found: {artifact}")
        rows.append(
            {
                "name": artifact.name,
                "sha256": _sha256(artifact),
                "size_bytes": artifact.stat().st_size,
            }
        )
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_revision": _git_revision(resolved_root),
        "artifacts": rows,
    }


def verify_manifest(manifest_path: Path, *, root: Path, require_current_revision: bool = False) -> None:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("Unsupported release manifest schema")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("Release manifest must contain at least one artifact")
    if require_current_revision and payload.get("source_revision") != _git_revision(root.resolve()):
        raise ValueError("Release manifest source revision does not match the current checkout")

    names: set[str] = set()
    for row in artifacts:
        if not isinstance(row, dict):
            raise ValueError("Release manifest artifact entry must be an object")
        name = row.get("name")
        digest = row.get("sha256")
        size = row.get("size_bytes")
        if not isinstance(name, str) or Path(name).name != name or name in names:
            raise ValueError("Release manifest contains an unsafe or duplicate artifact name")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError(f"Release manifest has an invalid SHA-256 for {name}")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise ValueError(f"Release manifest has an invalid size for {name}")
        artifact = manifest_path.parent / name
        if not artifact.is_file():
            raise FileNotFoundError(f"Release artifact listed in manifest is missing: {artifact}")
        if artifact.stat().st_size != size or _sha256(artifact) != digest:
            raise ValueError(f"Release artifact digest mismatch: {artifact}")
        names.add(name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifacts", nargs="*", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify", type=Path, help="verify an existing manifest and its sibling artifacts")
    parser.add_argument("--require-current-revision", action="store_true")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    if args.verify is not None:
        if args.artifacts or args.output is not None:
            parser.error("--verify cannot be combined with artifacts or --output")
        verify_manifest(
            args.verify,
            root=args.repo_root,
            require_current_revision=args.require_current_revision,
        )
        print(f"release manifest verified: {args.verify}")
        return 0
    if not args.artifacts or args.output is None:
        parser.error("artifacts and --output are required when writing a manifest")
    payload = build_manifest(args.repo_root, args.artifacts)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
