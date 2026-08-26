#!/usr/bin/env python3
"""Render an immutable, commit-bound read-only Kubernetes deployment."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from check_production_deployment import (
    COMMIT_PATTERN,
    COMMIT_SENTINEL,
    DEFAULT_MANIFEST_PATH,
    DNS_LABEL_PATTERN,
    IMAGE_DIGEST_PATTERN,
    IMAGE_SENTINEL,
    REPO_ROOT,
    load_manifest,
    validate_manifest,
)


def _replace(value: Any, replacements: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {key: _replace(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace(item, replacements) for item in value]
    if isinstance(value, str):
        rendered = value
        for old, new in replacements.items():
            rendered = rendered.replace(old, new)
        return rendered
    return value


def render_manifest(
    *,
    image: str,
    build_commit: str,
    token_secret_name: str = "trading-bot-service-api",
    template_path: Path | None = None,
) -> dict[str, Any]:
    normalized_image = str(image or "").strip().lower()
    normalized_commit = str(build_commit or "").strip().lower()
    normalized_secret_name = str(token_secret_name or "").strip().lower()
    if not IMAGE_DIGEST_PATTERN.fullmatch(
        normalized_image
    ) or normalized_image.endswith("0" * 64):
        raise ValueError(
            "--image must be an immutable image reference ending in @sha256:<64 lowercase hex characters>"
        )
    if normalized_image == IMAGE_SENTINEL:
        raise ValueError("--image must not use the non-routable template sentinel")
    if (
        not COMMIT_PATTERN.fullmatch(normalized_commit)
        or normalized_commit == COMMIT_SENTINEL
    ):
        raise ValueError(
            "--build-commit must be a non-placeholder 40-character lowercase Git commit"
        )
    if not DNS_LABEL_PATTERN.fullmatch(normalized_secret_name):
        raise ValueError(
            "--token-secret-name must be a valid lowercase Kubernetes DNS label"
        )

    payload = load_manifest(template_path or (REPO_ROOT / DEFAULT_MANIFEST_PATH))
    rendered = _replace(
        payload,
        {
            IMAGE_SENTINEL: normalized_image,
            COMMIT_SENTINEL: normalized_commit,
            "trading-bot-service-api": normalized_secret_name,
        },
    )
    report = validate_manifest(rendered, require_rendered=True)
    if not report["ok"]:
        raise ValueError(
            "Rendered manifest failed closed: " + "; ".join(report["issues"])
        )
    return rendered


def write_manifest(path: Path, payload: dict[str, Any]) -> None:
    resolved = path.resolve()
    template = (REPO_ROOT / DEFAULT_MANIFEST_PATH).resolve()
    if resolved == template:
        raise ValueError("Refusing to overwrite the checked-in deployment template")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{resolved.name}.", dir=resolved.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.replace(resolved)
    except (OSError, TypeError, ValueError):
        temporary_path.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--build-commit", required=True)
    parser.add_argument("--token-secret-name", default="trading-bot-service-api")
    parser.add_argument(
        "--template", type=Path, default=REPO_ROOT / DEFAULT_MANIFEST_PATH
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        payload = render_manifest(
            image=args.image,
            build_commit=args.build_commit,
            token_secret_name=args.token_secret_name,
            template_path=args.template,
        )
        write_manifest(args.output, payload)
    except (OSError, ValueError) as exc:
        if args.json:
            print(
                json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True)
            )
        else:
            print(f"Production deployment render failed: {exc}")
        return 1
    report = {
        "ok": True,
        "output": str(args.output.resolve()),
        "image": str(args.image).strip().lower(),
        "build_commit": str(args.build_commit).strip().lower(),
        "scope": "stateless-read-only-service-api",
    }
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"Rendered production deployment: {report['output']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
