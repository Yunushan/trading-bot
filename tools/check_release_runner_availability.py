#!/usr/bin/env python3
"""Fail fast when a release matrix needs an unavailable self-hosted runner."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    from check_release_platform_matrix import DEFAULT_MATRIX_PATH, _load_json, _validate_matrix
except ModuleNotFoundError:  # pragma: no cover - exercised when imported as tools.*
    from tools.check_release_platform_matrix import (
        DEFAULT_MATRIX_PATH,
        _load_json,
        _validate_matrix,
    )


def _self_hosted_label_sets(
    matrix_path: Path,
    *,
    target_filter: str = "",
    runner_labels_json: str = "",
) -> list[tuple[str, set[str]]]:
    if runner_labels_json:
        labels = json.loads(runner_labels_json)
        if not isinstance(labels, list) or not all(isinstance(label, str) for label in labels):
            raise ValueError("runner label override must be a JSON array of strings")
        normalized = {label.lower() for label in labels}
        return [(target_filter or "focused target", normalized)] if "self-hosted" in normalized else []

    matrix = _load_json(matrix_path)
    platform_targets, browser_targets, issues = _validate_matrix(matrix)
    if issues:
        raise ValueError("release platform matrix is invalid: " + "; ".join(issues))

    selected: list[tuple[str, set[str]]] = []
    for target in [*platform_targets, *browser_targets]:
        if target_filter and target["id"] != target_filter:
            continue
        labels = {str(label).lower() for label in target["runner_labels"]}
        if "self-hosted" in labels:
            selected.append((str(target["id"]), labels))
    return selected


def _list_runners(repository: str, token: str) -> list[dict[str, Any]]:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/actions/runners?per_page=100",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "trading-bot-release-runner-check",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 403:
            raise RuntimeError(
                "GitHub denied access to the self-hosted runner inventory; configure "
                "the RELEASE_RUNNER_STATUS_TOKEN secret with Administration: read access "
                "for this repository"
            ) from error
        raise RuntimeError(f"could not query self-hosted runners: {error}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"could not query self-hosted runners: {error}") from error
    runners = payload.get("runners") if isinstance(payload, dict) else None
    if not isinstance(runners, list):
        raise RuntimeError("self-hosted runner API returned no runners list")
    return [runner for runner in runners if isinstance(runner, dict)]


def unavailable_targets(
    targets: list[tuple[str, set[str]]], runners: list[dict[str, Any]]
) -> list[tuple[str, set[str]]]:
    unavailable: list[tuple[str, set[str]]] = []
    for target_id, required_labels in targets:
        available = False
        for runner in runners:
            labels = runner.get("labels")
            runner_labels = {
                str(label.get("name", "")).lower()
                for label in labels
                if isinstance(label, dict)
            } if isinstance(labels, list) else set()
            if (
                runner.get("status") == "online"
                and runner.get("busy") is False
                and required_labels.issubset(runner_labels)
            ):
                available = True
                break
        if not available:
            unavailable.append((target_id, required_labels))
    return unavailable


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, help="owner/repository")
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX_PATH)
    parser.add_argument("--target-filter", default="")
    parser.add_argument("--runner-labels-json", default="")
    args = parser.parse_args(argv)

    try:
        targets = _self_hosted_label_sets(
            args.matrix,
            target_filter=args.target_filter,
            runner_labels_json=args.runner_labels_json,
        )
        if not targets:
            print("No self-hosted release targets selected.")
            return 0
        token = os.environ.get("GITHUB_TOKEN", "").strip()
        if not token:
            raise RuntimeError("GITHUB_TOKEN is required to check self-hosted runner availability")
        unavailable = unavailable_targets(targets, _list_runners(args.repository, token))
    except (RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    if unavailable:
        for target_id, labels in unavailable:
            print(
                f"error: no idle self-hosted runner is available for {target_id} "
                f"with labels: {', '.join(sorted(labels))}",
                file=sys.stderr,
            )
        print(
            "Start or free the matching runner before dispatching the real release matrix; "
            "this workflow stops here instead of leaving jobs queued.",
            file=sys.stderr,
        )
        return 1

    print("Required self-hosted release runners are online and idle.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
