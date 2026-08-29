#!/usr/bin/env python3
"""Allow release publishers to mutate only a missing or prerelease candidate."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping
from typing import Any

import check_release_assets


def validate_publication_state(
    payload: Mapping[str, Any] | None,
    *,
    tag: str,
) -> list[str]:
    """Return defects that would make candidate publication unsafe."""

    if payload is None:
        return []
    issues: list[str] = []
    if str(payload.get("tag_name") or "").strip() != tag:
        issues.append("existing release tag_name does not match the requested tag")
    if payload.get("draft") is not False:
        issues.append("existing release must be published, not draft")
    if payload.get("prerelease") is not True:
        issues.append(
            "existing release is already stable; a platform publisher must not demote it"
        )
    return issues


def main(argv: list[str] | None = None) -> int:
    default_owner, default_repo = check_release_assets._resolve_default_repo()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--owner", default=default_owner)
    parser.add_argument("--repo", default=default_repo)
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args(argv)
    token = (
        str(os.environ.get("GITHUB_TOKEN") or "").strip()
        or str(os.environ.get("GH_TOKEN") or "").strip()
        or None
    )

    try:
        payload = check_release_assets._fetch_release(
            args.tag,
            owner=str(args.owner).strip(),
            repo=str(args.repo).strip(),
            timeout=args.timeout,
            token=token,
        )
    except check_release_assets.GitHubApiError as error:
        if error.status == 404:
            payload = None
        else:
            print(f"release publication state check failed: {error}", file=sys.stderr)
            return 1
    except RuntimeError as error:
        print(f"release publication state check failed: {error}", file=sys.stderr)
        return 1

    issues = validate_publication_state(payload, tag=args.tag)
    if issues:
        print("release publication state: rejected", file=sys.stderr)
        for issue in issues:
            print(f"- {issue}", file=sys.stderr)
        return 1
    state = "missing candidate" if payload is None else "mutable prerelease candidate"
    print(f"release publication state: approved ({state})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
