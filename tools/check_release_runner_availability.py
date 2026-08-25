#!/usr/bin/env python3
"""Fail fast when selected self-hosted release targets have no ready runner."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable, Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_TOKEN_ENV = "RELEASE_RUNNER_STATUS_TOKEN"


def _as_labels(value: Any, *, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field} must be a non-empty list")
    labels = [str(item).strip() for item in value]
    if any(not label for label in labels):
        raise ValueError(f"{field} must contain only non-empty strings")
    return labels


def _target_labels(target: Mapping[str, Any]) -> list[str]:
    raw = target.get("runner_labels_json")
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"target {target.get('target_id', '<unknown>')} is missing runner_labels_json")
    try:
        return _as_labels(json.loads(raw), field="runner_labels_json")
    except json.JSONDecodeError as exc:
        raise ValueError(f"target {target.get('target_id', '<unknown>')} has invalid runner_labels_json: {exc}") from exc


def _is_self_hosted(target: Mapping[str, Any]) -> bool:
    labels = {label.lower() for label in _target_labels(target)}
    runner_kind = str(target.get("runner_kind") or "").strip().lower()
    return "self-hosted" in labels or runner_kind.startswith("self-hosted")


def parse_target_matrix(raw: str) -> list[dict[str, Any]]:
    """Parse the compact matrix emitted by check_release_platform_matrix.py."""

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"TARGETS_JSON is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("include"), list):
        raise ValueError("TARGETS_JSON must be a matrix object with an include list")
    targets: list[dict[str, Any]] = []
    for item in payload["include"]:
        if not isinstance(item, dict):
            raise ValueError("TARGETS_JSON include entries must be objects")
        target = dict(item)
        target_id = str(target.get("target_id") or "").strip()
        if not target_id:
            raise ValueError("TARGETS_JSON targets must contain target_id")
        _target_labels(target)
        targets.append(target)
    return targets


def _runner_labels(runner: Mapping[str, Any]) -> set[str]:
    labels = runner.get("labels")
    if not isinstance(labels, list):
        return set()
    return {
        str(label.get("name") or "").strip().lower()
        for label in labels
        if isinstance(label, Mapping) and str(label.get("name") or "").strip()
    }


def availability_issues(targets: list[Mapping[str, Any]], runners: list[Mapping[str, Any]]) -> list[str]:
    """Return actionable issues for self-hosted targets without changing runner state."""

    ready_runners = [
        runner
        for runner in runners
        if str(runner.get("status") or "").lower() == "online" and not bool(runner.get("busy"))
    ]
    issues: list[str] = []
    for target in targets:
        if not _is_self_hosted(target):
            continue
        target_id = str(target.get("target_id") or "<unknown>")
        required = {label.lower() for label in _target_labels(target)}
        if any(required.issubset(_runner_labels(runner)) for runner in ready_runners):
            continue
        matching = [runner for runner in runners if required.issubset(_runner_labels(runner))]
        if matching:
            states = ", ".join(
                f"{runner.get('name', '<unnamed>')}={runner.get('status', 'unknown')}"
                f"{'/busy' if runner.get('busy') else ''}"
                for runner in matching
            )
            issues.append(f"{target_id} has matching runners but none are ready: {states}")
        else:
            labels = ", ".join(sorted(required))
            issues.append(f"{target_id} has no runner advertising all required labels: {labels}")
    return issues


def fetch_runners(
    repository: str,
    token: str,
    *,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    opener: Callable[..., Any] = urlopen,
) -> list[dict[str, Any]]:
    repository = repository.strip().strip("/")
    if repository.count("/") != 1:
        raise ValueError("repository must have the owner/name form")
    if not token.strip():
        raise ValueError("a non-empty runner inventory token is required")
    url = f"https://api.github.com/repos/{quote(repository, safe='/')}/actions/runners?per_page=100"
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "trading-bot-release-runner-preflight",
        },
    )
    try:
        with opener(request, timeout=timeout) as response:
            payload = json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f"GitHub runner inventory request failed with HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"GitHub runner inventory request failed: {exc.reason}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("runners"), list):
        raise RuntimeError("GitHub runner inventory response did not contain a runners list")
    return [dict(item) for item in payload["runners"] if isinstance(item, Mapping)]


def _json_report(*, ok: bool, issues: list[str], target_count: int, runner_count: int) -> None:
    print(
        json.dumps(
            {"ok": ok, "issues": issues, "self_hosted_target_count": target_count, "runner_count": runner_count},
            indent=2,
            sort_keys=True,
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets-json", default=os.environ.get("TARGETS_JSON", ""))
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--token-env", default=DEFAULT_TOKEN_ENV)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    issues: list[str] = []
    target_count = 0
    runner_count = 0
    try:
        targets = parse_target_matrix(args.targets_json)
        self_hosted_targets = [target for target in targets if _is_self_hosted(target)]
        target_count = len(self_hosted_targets)
        if not self_hosted_targets:
            issues = ["selected matrix contains no self-hosted targets"]
        else:
            token = os.environ.get(args.token_env, "")
            if not token.strip():
                issues = [
                    f"{args.token_env} is required to check self-hosted runner availability; "
                    "the job was stopped before any runner target could queue"
                ]
            else:
                runners = fetch_runners(args.repository, token, timeout=args.timeout)
                runner_count = len(runners)
                issues = availability_issues(self_hosted_targets, runners)
    except (RuntimeError, ValueError) as exc:
        issues = [str(exc)]

    ok = not issues
    if args.json:
        _json_report(ok=ok, issues=issues, target_count=target_count, runner_count=runner_count)
    elif ok:
        print(f"release runner availability: ready ({target_count} self-hosted target(s), {runner_count} runner(s))")
    else:
        print("release runner availability: not ready")
        for issue in issues:
            print(f"- {issue}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
