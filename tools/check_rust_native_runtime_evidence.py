#!/usr/bin/env python3
"""Validate Rust native runtime readiness evidence declarations and artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

try:
    from check_release_assets import _build_expected_assets
    from check_release_platform_matrix import DEFAULT_MATRIX_PATH as RELEASE_PLATFORM_MATRIX_PATH
    from check_release_platform_matrix import REQUIRED_SUITE_RESULT_NAMES
    from check_release_platform_matrix import _load_json as _load_release_matrix_json
    from check_release_platform_matrix import _validate_matrix as _validate_release_matrix
except ModuleNotFoundError:  # pragma: no cover - exercised when imported as tools.*
    from tools.check_release_assets import _build_expected_assets
    from tools.check_release_platform_matrix import DEFAULT_MATRIX_PATH as RELEASE_PLATFORM_MATRIX_PATH
    from tools.check_release_platform_matrix import REQUIRED_SUITE_RESULT_NAMES
    from tools.check_release_platform_matrix import _load_json as _load_release_matrix_json
    from tools.check_release_platform_matrix import _validate_matrix as _validate_release_matrix


DEFAULT_MANIFEST_PATH = Path("docs/rust-native-runtime-evidence.json")
REQUIRED_REQUIREMENTS: dict[str, str] = {
    "rust-native-live-market-data-smoke": "live_smoke",
    "rust-native-live-account-read-smoke": "live_smoke",
    "rust-native-live-stream-recovery": "live_recovery",
    "rust-native-order-guard-recovery": "live_recovery",
    "rust-native-release-platform-evidence": "release_evidence",
}
ACCEPTED_EVIDENCE_SCOPES: dict[str, set[str]] = {
    "live_smoke": {"live_testnet", "live_production"},
    "live_recovery": {"deterministic_local", "controlled_live", "live_testnet", "live_production"},
    "release_evidence": {"release_platform"},
}
EXPECTED_LIVE_SMOKE_ENDPOINTS: dict[str, set[str]] = {
    "rust-native-live-market-data-smoke": {"exchangeInfo", "klines", "tickerPrice"},
    "rust-native-live-account-read-smoke": {
        "positionSideDual",
        "multiAssetsMargin",
        "balance",
        "positionRisk",
    },
}
EXPECTED_LIVE_SMOKE_SUITE_RESULTS: dict[str, set[str]] = {
    "rust-native-live-market-data-smoke": {
        "fetch_usdt_symbols",
        "fetch_klines",
        "fetch_ticker_price",
    },
    "rust-native-live-account-read-smoke": {
        "fetch_futures_position_mode",
        "fetch_futures_multi_assets_mode",
        "fetch_usdt_balance",
        "fetch_open_futures_positions",
    },
}
LIVE_SMOKE_SCOPE_BASE_URLS: dict[str, str] = {
    "live_testnet": "https://testnet.binancefuture.com",
    "live_production": "https://fapi.binance.com",
}
SAFE_REDACTED_VALUES = {"", "...", "<redacted>", "redacted", "***"}
SAFE_SECRET_METADATA_KEYS = {
    "api_key_present",
    "api_secret_present",
    "binance_api_key_present",
    "binance_api_secret_present",
    "github_token_present",
    "secrets_redacted",
}
SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|api[_-]?secret|llm[_-]?api[_-]?key|token|signature)\b\s*[:=]\s*([^\s,;&]+)"
)
BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+([^\s,;&]+)")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _repo_path(path: Path) -> Path:
    return path if path.is_absolute() else _repo_root() / path


def _current_git_commit() -> str | None:
    try:
        output = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_repo_root(),
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    commit = output.stdout.strip()
    return commit or None


def _current_source_tree_clean() -> bool | None:
    try:
        output = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=_repo_root(),
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return not output.stdout.strip()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc
    except OSError as exc:
        raise ValueError(f"Unable to read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _string_list(value: Any, *, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field} must be a non-empty list")
    result = [str(item).strip() for item in value if str(item).strip()]
    if len(result) != len(value):
        raise ValueError(f"{field} must contain only non-empty strings")
    return result


def _requirements(manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    issues: list[str] = []
    rows = manifest.get("requirements")
    if not isinstance(rows, list) or not rows:
        return [], ["requirements must be a non-empty list"]

    parsed: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            issues.append(f"requirements[{index}] must be an object")
            continue
        evidence_id = str(row.get("id") or "").strip()
        category = str(row.get("category") or "").strip()
        title = str(row.get("title") or "").strip()
        command = str(row.get("command") or "").strip()
        if not evidence_id:
            issues.append(f"requirements[{index}].id is required")
            continue
        if evidence_id in seen:
            issues.append(f"duplicate requirement id: {evidence_id}")
        seen.add(evidence_id)
        expected_category = REQUIRED_REQUIREMENTS.get(evidence_id)
        if not expected_category:
            issues.append(f"unexpected requirement id: {evidence_id}")
        elif category != expected_category:
            issues.append(f"{evidence_id}.category must be {expected_category}")
        if not title:
            issues.append(f"{evidence_id}.title is required")
        if not command:
            issues.append(f"{evidence_id}.command is required")
        if row.get("evidence_required_before_runtime_ready") is not True:
            issues.append(f"{evidence_id}.evidence_required_before_runtime_ready must be true")
        try:
            required_fields = _string_list(
                row.get("required_artifact_fields"),
                field=f"{evidence_id}.required_artifact_fields",
            )
        except ValueError as exc:
            required_fields = []
            issues.append(str(exc))
        for field in (
            "evidence_id",
            "status",
            "evidence_scope",
            "generated_at",
            "commit",
            "command",
            "environment",
            "secrets_redacted",
            "runtime_ready_claimed",
            "suite_results",
        ):
            if field not in required_fields:
                issues.append(f"{evidence_id}.required_artifact_fields must include {field}")
        if category == "live_smoke":
            for field in ("read_only", "order_submission_attempted", "endpoints"):
                if field not in required_fields:
                    issues.append(f"{evidence_id}.required_artifact_fields must include {field}")
        if category == "live_recovery" and "recovery_scenarios" not in required_fields:
            issues.append(f"{evidence_id}.required_artifact_fields must include recovery_scenarios")
        if category == "release_evidence":
            for field in ("release_artifacts", "platform_results"):
                if field not in required_fields:
                    issues.append(f"{evidence_id}.required_artifact_fields must include {field}")
        parsed.append(
            {
                "id": evidence_id,
                "category": category,
                "title": title,
                "command": command,
                "required_artifact_fields": required_fields,
            }
        )

    missing = sorted(set(REQUIRED_REQUIREMENTS) - seen)
    if missing:
        issues.append(f"missing required evidence ids: {', '.join(missing)}")
    return parsed, issues


def _suite_results_pass(payload: dict[str, Any], artifact_path: Path, issues: list[str]) -> None:
    suites = payload.get("suite_results")
    if not isinstance(suites, list) or not suites:
        issues.append(f"{artifact_path} must contain non-empty suite_results")
        return
    for index, item in enumerate(suites):
        if not isinstance(item, dict):
            issues.append(f"{artifact_path} suite_results[{index}] must be an object")
            continue
        if item.get("status") != "passed":
            issues.append(f"{artifact_path} suite_results[{index}].status must be passed")


def _list_of_passing_objects(
    payload: dict[str, Any],
    field: str,
    artifact_path: Path,
    issues: list[str],
) -> None:
    rows = payload.get(field)
    if not isinstance(rows, list) or not rows:
        issues.append(f"{artifact_path} must contain non-empty {field}")
        return
    for index, item in enumerate(rows):
        if not isinstance(item, dict):
            issues.append(f"{artifact_path} {field}[{index}] must be an object")
            continue
        if item.get("status") != "passed":
            issues.append(f"{artifact_path} {field}[{index}].status must be passed")


def _required_artifact_fields_present(
    requirement: dict[str, Any],
    payload: dict[str, Any],
    artifact_path: Path,
    issues: list[str],
) -> None:
    for field in requirement.get("required_artifact_fields", []):
        if field not in payload:
            issues.append(f"{artifact_path} missing required artifact field: {field}")
            continue
        value = payload.get(field)
        if value is None:
            issues.append(f"{artifact_path} required artifact field {field} cannot be null")
        elif isinstance(value, str) and not value.strip():
            issues.append(f"{artifact_path} required artifact field {field} cannot be empty")
        elif isinstance(value, (list, dict)) and not value:
            issues.append(f"{artifact_path} required artifact field {field} cannot be empty")


def _validate_generated_at(payload: dict[str, Any], artifact_path: Path, issues: list[str]) -> None:
    generated_at = str(payload.get("generated_at") or "").strip()
    if not generated_at:
        return
    prefix = "unix:"
    if not generated_at.startswith(prefix):
        issues.append(f"{artifact_path} generated_at must use unix:<seconds> format")
        return
    raw_seconds = generated_at[len(prefix) :]
    if not raw_seconds.isdigit() or int(raw_seconds) <= 0:
        issues.append(f"{artifact_path} generated_at must contain positive unix seconds")


def _is_safe_redacted_value(value: Any) -> bool:
    return str(value).strip().lower() in SAFE_REDACTED_VALUES


def _is_sensitive_key(key: str) -> bool:
    normalized = key.strip().lower().replace("-", "_")
    if normalized in SAFE_SECRET_METADATA_KEYS or normalized.endswith("_present"):
        return False
    return any(
        fragment in normalized
        for fragment in ("api_key", "apikey", "api_secret", "secret", "token", "signature", "authorization")
    )


def _validate_secret_free_text(value: str, artifact_path: Path, issues: list[str]) -> None:
    for match in SECRET_ASSIGNMENT_PATTERN.finditer(value):
        secret_value = match.group(2).strip().strip("\"'")
        if not _is_safe_redacted_value(secret_value):
            issues.append(f"{artifact_path} contains unredacted secret assignment for {match.group(1)}")
    for match in BEARER_PATTERN.finditer(value):
        bearer_value = match.group(1).strip().strip("\"'")
        if not _is_safe_redacted_value(bearer_value):
            issues.append(f"{artifact_path} contains unredacted bearer token text")


def _validate_no_secret_leaks(value: Any, artifact_path: Path, issues: list[str], *, key: str = "") -> None:
    if key and _is_sensitive_key(key):
        if isinstance(value, str):
            if value.strip() and not _is_safe_redacted_value(value):
                issues.append(f"{artifact_path} contains unredacted secret field: {key}")
        elif isinstance(value, bool):
            return
        elif value not in (None, ""):
            issues.append(f"{artifact_path} contains non-redacted secret field: {key}")
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            _validate_no_secret_leaks(child_value, artifact_path, issues, key=str(child_key))
    elif isinstance(value, list):
        for child_value in value:
            _validate_no_secret_leaks(child_value, artifact_path, issues)
    elif isinstance(value, str):
        _validate_secret_free_text(value, artifact_path, issues)


def _validate_live_smoke_endpoint_evidence(
    *,
    evidence_id: str,
    payload: dict[str, Any],
    artifact_path: Path,
    issues: list[str],
) -> None:
    endpoints = payload.get("endpoints")
    if not isinstance(endpoints, list) or not endpoints:
        issues.append(f"{artifact_path} endpoints must be a non-empty list")
        return

    expected_names = EXPECTED_LIVE_SMOKE_ENDPOINTS.get(evidence_id, set())
    observed_names: set[str] = set()
    evidence_scope = str(payload.get("evidence_scope") or "").strip()
    expected_base_url = LIVE_SMOKE_SCOPE_BASE_URLS.get(evidence_scope)
    for index, item in enumerate(endpoints):
        if not isinstance(item, dict):
            issues.append(f"{artifact_path} endpoints[{index}] must be an object")
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            issues.append(f"{artifact_path} endpoints[{index}].name is required")
        else:
            observed_names.add(name)
        if item.get("status") != "passed":
            issues.append(f"{artifact_path} endpoints[{index}].status must be passed")
        url = str(item.get("url") or "").strip()
        if not url:
            issues.append(f"{artifact_path} endpoints[{index}].url is required")
            continue
        if "?" in url:
            issues.append(f"{artifact_path} endpoints[{index}].url must not include query parameters")
        if expected_base_url and not url.startswith(f"{expected_base_url}/"):
            issues.append(f"{artifact_path} endpoints[{index}].url must start with {expected_base_url}/")

    missing = sorted(expected_names - observed_names)
    if missing:
        issues.append(f"{artifact_path} missing live-smoke endpoints: {', '.join(missing)}")
    unexpected = sorted(observed_names - expected_names)
    if unexpected:
        issues.append(f"{artifact_path} contains unexpected live-smoke endpoints: {', '.join(unexpected)}")

    environment = payload.get("environment")
    if isinstance(environment, dict) and expected_base_url:
        base_fields = ["market_base_url"]
        if evidence_id == "rust-native-live-account-read-smoke":
            base_fields.append("account_base_url")
        for field in base_fields:
            observed = str(environment.get(field) or "").strip()
            if observed != expected_base_url:
                issues.append(f"{artifact_path} environment.{field} must be {expected_base_url}")


def _validate_live_account_environment_evidence(
    *,
    evidence_id: str,
    payload: dict[str, Any],
    artifact_path: Path,
    issues: list[str],
) -> None:
    if evidence_id != "rust-native-live-account-read-smoke":
        return
    environment = payload.get("environment")
    if not isinstance(environment, dict):
        return
    if environment.get("api_key_present") is not True:
        issues.append(f"{artifact_path} environment.api_key_present must be true")
    if environment.get("api_secret_present") is not True:
        issues.append(f"{artifact_path} environment.api_secret_present must be true")
    if environment.get("signed_account_read") is not True:
        issues.append(f"{artifact_path} environment.signed_account_read must be true")
    if environment.get("secrets_in_artifact") is not False:
        issues.append(f"{artifact_path} environment.secrets_in_artifact must be false")


def _validate_live_smoke_suite_evidence(
    *,
    evidence_id: str,
    payload: dict[str, Any],
    artifact_path: Path,
    issues: list[str],
) -> None:
    suites = payload.get("suite_results")
    if not isinstance(suites, list) or not suites:
        return
    expected_names = EXPECTED_LIVE_SMOKE_SUITE_RESULTS.get(evidence_id, set())
    observed_names: set[str] = set()
    rows_by_name: dict[str, dict[str, Any]] = {}
    duplicate_names: set[str] = set()
    for index, item in enumerate(suites):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            issues.append(f"{artifact_path} suite_results[{index}].name is required")
            continue
        if name in rows_by_name:
            duplicate_names.add(name)
        rows_by_name[name] = item
        observed_names.add(name)

    missing = sorted(expected_names - observed_names)
    if missing:
        issues.append(f"{artifact_path} missing live-smoke suite results: {', '.join(missing)}")
    unexpected = sorted(observed_names - expected_names)
    if unexpected:
        issues.append(f"{artifact_path} contains unexpected live-smoke suite results: {', '.join(unexpected)}")
    if duplicate_names:
        issues.append(f"{artifact_path} contains duplicate live-smoke suite results: {', '.join(sorted(duplicate_names))}")

    if evidence_id == "rust-native-live-market-data-smoke":
        for name in ("fetch_usdt_symbols", "fetch_klines"):
            row = rows_by_name.get(name)
            if row is not None and not isinstance(row.get("observed_count"), int):
                issues.append(f"{artifact_path} suite_results[{name}].observed_count must be an integer")
        ticker_row = rows_by_name.get("fetch_ticker_price")
        if ticker_row is not None and not str(ticker_row.get("symbol") or "").strip():
            issues.append(f"{artifact_path} suite_results[fetch_ticker_price].symbol is required")
    elif evidence_id == "rust-native-live-account-read-smoke":
        position_row = rows_by_name.get("fetch_futures_position_mode")
        if position_row is not None:
            if not str(position_row.get("position_mode") or "").strip():
                issues.append(f"{artifact_path} suite_results[fetch_futures_position_mode].position_mode is required")
            if not isinstance(position_row.get("dual_side_position"), bool):
                issues.append(
                    f"{artifact_path} suite_results[fetch_futures_position_mode].dual_side_position must be boolean"
                )
        multi_assets_row = rows_by_name.get("fetch_futures_multi_assets_mode")
        if multi_assets_row is not None and not isinstance(multi_assets_row.get("multi_assets_margin"), bool):
            issues.append(
                f"{artifact_path} suite_results[fetch_futures_multi_assets_mode].multi_assets_margin must be boolean"
            )
        balance_row = rows_by_name.get("fetch_usdt_balance")
        if balance_row is not None:
            if not str(balance_row.get("asset") or "").strip():
                issues.append(f"{artifact_path} suite_results[fetch_usdt_balance].asset is required")
            if balance_row.get("balances_redacted") is not True:
                issues.append(f"{artifact_path} suite_results[fetch_usdt_balance].balances_redacted must be true")
        positions_row = rows_by_name.get("fetch_open_futures_positions")
        if positions_row is not None and not isinstance(positions_row.get("observed_count"), int):
            issues.append(f"{artifact_path} suite_results[fetch_open_futures_positions].observed_count must be an integer")


def _release_evidence_environment(payload: dict[str, Any], artifact_path: Path, issues: list[str]) -> dict[str, Any]:
    environment = payload.get("environment")
    if not isinstance(environment, dict):
        issues.append(f"{artifact_path} environment must be an object for release evidence")
        return {}
    for field in ("tag", "owner", "repo", "matrix", "platform_evidence_dir"):
        if not str(environment.get(field) or "").strip():
            issues.append(f"{artifact_path} environment.{field} is required for release evidence")
    return environment


def _validate_release_artifact_contract(payload: dict[str, Any], artifact_path: Path, issues: list[str]) -> None:
    environment = _release_evidence_environment(payload, artifact_path, issues)
    tag = str(environment.get("tag") or "").strip()
    release_artifacts = payload.get("release_artifacts")
    if not isinstance(release_artifacts, list):
        return
    observed_names = {
        str(item.get("name") or "").strip()
        for item in release_artifacts
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    }
    duplicates = sorted(
        name
        for name in observed_names
        if sum(
            1
            for item in release_artifacts
            if isinstance(item, dict) and str(item.get("name") or "").strip() == name
        )
        > 1
    )
    if duplicates:
        issues.append(f"{artifact_path} release_artifacts contains duplicate assets: {', '.join(duplicates)}")
    if not tag:
        return

    _, expected_assets = _build_expected_assets(tag)
    expected_rust_assets = {
        asset.name: asset
        for asset in expected_assets
        if asset.name.startswith("Trading-Bot-Rust-")
    }
    required_rust_assets = sorted(
        asset.name
        for asset in expected_rust_assets.values()
        if asset.required
    )
    missing = sorted(set(required_rust_assets) - observed_names)
    if missing:
        issues.append(f"{artifact_path} missing required Rust release assets: {', '.join(missing)}")
    for index, item in enumerate(release_artifacts):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if name not in expected_rust_assets:
            issues.append(f"{artifact_path} release_artifacts[{index}].name must be an expected Rust release asset")
            continue
        expected_asset = expected_rust_assets[name]
        if item.get("required") is not expected_asset.required:
            issues.append(
                f"{artifact_path} release_artifacts[{index}].required must be "
                f"{str(expected_asset.required).lower()} for {name}"
            )
        if item.get("group") != expected_asset.group:
            issues.append(f"{artifact_path} release_artifacts[{index}].group must be {expected_asset.group}")


def _release_matrix_targets(matrix_path: Path, artifact_path: Path, issues: list[str]) -> dict[str, dict[str, Any]]:
    try:
        matrix = _load_release_matrix_json(matrix_path)
    except ValueError as exc:
        issues.append(f"{artifact_path} release matrix could not be loaded: {exc}")
        return {}
    platform_targets, browser_targets, matrix_issues = _validate_release_matrix(matrix)
    if matrix_issues:
        issues.extend(f"{artifact_path} release matrix issue: {issue}" for issue in matrix_issues)
        return {}
    targets = platform_targets + browser_targets
    return {str(target["id"]): target for target in targets}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_release_platform_evidence_hash(
    *,
    platform_result: dict[str, Any],
    target_id: str,
    platform_evidence_dir: Path,
    index: int,
    artifact_path: Path,
    issues: list[str],
) -> None:
    evidence_file = str(platform_result.get("evidence_file") or "").strip()
    expected_file = f"{target_id}.json"
    if evidence_file != expected_file:
        issues.append(f"{artifact_path} platform_results[{index}].evidence_file must be {expected_file}")
        return

    evidence_sha256 = str(platform_result.get("evidence_sha256") or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", evidence_sha256):
        issues.append(f"{artifact_path} platform_results[{index}].evidence_sha256 must be a SHA-256 hex digest")
        return

    target_path = platform_evidence_dir / evidence_file
    if target_path.is_file():
        actual_sha256 = _sha256_file(target_path)
        if evidence_sha256 != actual_sha256:
            issues.append(f"{artifact_path} platform_results[{index}].evidence_sha256 does not match {target_path}")


def _validate_release_platform_suite_results(
    *,
    platform_result: dict[str, Any],
    target: dict[str, Any],
    index: int,
    artifact_path: Path,
    issues: list[str],
) -> None:
    suite_results = platform_result.get("suite_results")
    if not isinstance(suite_results, list) or not suite_results:
        issues.append(f"{artifact_path} platform_results[{index}].suite_results must be a non-empty list")
        return

    expected_suites = [str(item) for item in target.get("test_suites", [])]
    accepted_names_by_suite = {
        suite: REQUIRED_SUITE_RESULT_NAMES.get(suite, (suite,))
        for suite in expected_suites
    }
    accepted_names = {
        accepted_name
        for names in accepted_names_by_suite.values()
        for accepted_name in names
    }
    observed_names: list[str] = []
    rows_by_name: dict[str, dict[str, Any]] = {}
    for suite_index, row in enumerate(suite_results):
        if not isinstance(row, dict):
            issues.append(f"{artifact_path} platform_results[{index}].suite_results[{suite_index}] must be an object")
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            issues.append(f"{artifact_path} platform_results[{index}].suite_results[{suite_index}].name is required")
            continue
        observed_names.append(name)
        rows_by_name[name] = row
        if name not in accepted_names:
            issues.append(
                f"{artifact_path} platform_results[{index}].suite_results[{suite_index}].name "
                "must match a release matrix suite"
            )
        if row.get("status") != "passed":
            issues.append(f"{artifact_path} platform_results[{index}].suite_results[{suite_index}].status must be passed")

    duplicate_names = sorted({name for name in observed_names if observed_names.count(name) > 1})
    if duplicate_names:
        issues.append(
            f"{artifact_path} platform_results[{index}].suite_results contains duplicate suite names: "
            f"{', '.join(duplicate_names)}"
        )
    for suite, accepted_names_for_suite in accepted_names_by_suite.items():
        if not any(name in rows_by_name for name in accepted_names_for_suite):
            issues.append(
                f"{artifact_path} platform_results[{index}].suite_results missing required suite result for {suite}"
            )

    if target.get("kind") == "platform" and "platform-probe" in expected_suites:
        platform_probe = rows_by_name.get("platform-probe")
        if not isinstance(platform_probe, dict):
            issues.append(f"{artifact_path} platform_results[{index}].suite_results must include platform-probe")
        else:
            target_match = platform_probe.get("target_match")
            if not isinstance(target_match, dict) or target_match.get("matched") is not True:
                issues.append(
                    f"{artifact_path} platform_results[{index}].suite_results[platform-probe].target_match.matched must be true"
                )


def _validate_release_platform_results(payload: dict[str, Any], artifact_path: Path, issues: list[str]) -> None:
    environment = _release_evidence_environment(payload, artifact_path, issues)
    raw_matrix_path = str(environment.get("matrix") or "").strip()
    matrix_path = _repo_path(Path(raw_matrix_path)) if raw_matrix_path else _repo_path(RELEASE_PLATFORM_MATRIX_PATH)
    raw_platform_evidence_dir = str(environment.get("platform_evidence_dir") or "").strip()
    platform_evidence_dir = (
        _repo_path(Path(raw_platform_evidence_dir))
        if raw_platform_evidence_dir
        else _repo_path(Path("release-platform-evidence"))
    )
    targets_by_id = _release_matrix_targets(matrix_path, artifact_path, issues)
    if not targets_by_id:
        return

    platform_results = payload.get("platform_results")
    if not isinstance(platform_results, list):
        return
    observed_ids: list[str] = []
    for index, item in enumerate(platform_results):
        if not isinstance(item, dict):
            continue
        target_id = str(item.get("target_id") or "").strip()
        if not target_id:
            issues.append(f"{artifact_path} platform_results[{index}].target_id is required")
            continue
        observed_ids.append(target_id)
        target = targets_by_id.get(target_id)
        if target is None:
            issues.append(f"{artifact_path} platform_results[{index}] references unknown target_id {target_id}")
            continue
        _validate_release_platform_evidence_hash(
            platform_result=item,
            target_id=target_id,
            platform_evidence_dir=platform_evidence_dir,
            index=index,
            artifact_path=artifact_path,
            issues=issues,
        )
        if item.get("kind") != target.get("kind"):
            issues.append(f"{artifact_path} platform_results[{index}].kind must be {target.get('kind')}")
        if item.get("runner_kind") != target.get("runner_kind"):
            issues.append(f"{artifact_path} platform_results[{index}].runner_kind must be {target.get('runner_kind')}")
        expected_suites = [str(item) for item in target.get("test_suites", [])]
        observed_suites = item.get("test_suites")
        if not isinstance(observed_suites, list) or [str(suite) for suite in observed_suites] != expected_suites:
            issues.append(f"{artifact_path} platform_results[{index}].test_suites must match the release matrix")
        expected_suite_count = len(expected_suites)
        if item.get("expected_suite_count") != expected_suite_count:
            issues.append(
                f"{artifact_path} platform_results[{index}].expected_suite_count must be {expected_suite_count}"
            )
        suite_count = item.get("suite_count")
        if not isinstance(suite_count, int) or suite_count <= 0:
            issues.append(f"{artifact_path} platform_results[{index}].suite_count must be a positive integer")
        elif suite_count < expected_suite_count:
            issues.append(
                f"{artifact_path} platform_results[{index}].suite_count must be at least {expected_suite_count}"
            )
        suite_results = item.get("suite_results")
        if isinstance(suite_results, list) and isinstance(suite_count, int) and suite_count != len(suite_results):
            issues.append(
                f"{artifact_path} platform_results[{index}].suite_count must match embedded suite_results count"
            )
        _validate_release_platform_suite_results(
            platform_result=item,
            target=target,
            index=index,
            artifact_path=artifact_path,
            issues=issues,
        )

    duplicate_ids = sorted({target_id for target_id in observed_ids if observed_ids.count(target_id) > 1})
    if duplicate_ids:
        issues.append(f"{artifact_path} platform_results contains duplicate target ids: {', '.join(duplicate_ids)}")
    missing_ids = sorted(set(targets_by_id) - set(observed_ids))
    if missing_ids:
        issues.append(
            f"{artifact_path} missing release platform results for {len(missing_ids)} target(s): "
            f"{', '.join(missing_ids[:10])}"
        )


def _validate_artifact(
    requirement: dict[str, Any],
    artifact_path: Path,
    *,
    expected_commit: str | None = None,
    require_clean_source: bool = False,
) -> list[str]:
    issues: list[str] = []
    if not artifact_path.is_file():
        return [f"missing evidence artifact: {artifact_path}"]
    try:
        payload = _load_json(artifact_path)
    except ValueError as exc:
        return [str(exc)]

    evidence_id = str(requirement["id"])
    _required_artifact_fields_present(requirement, payload, artifact_path, issues)
    _validate_generated_at(payload, artifact_path, issues)
    _validate_no_secret_leaks(payload, artifact_path, issues)
    if payload.get("evidence_id") != evidence_id:
        issues.append(f"{artifact_path} evidence_id must be {evidence_id}")
    if payload.get("status") != "passed":
        issues.append(f"{artifact_path} status must be passed")
    for field in ("generated_at", "commit", "command"):
        if not str(payload.get(field) or "").strip():
            issues.append(f"{artifact_path} {field} is required")
    artifact_commit = str(payload.get("commit") or "").strip()
    if expected_commit and artifact_commit != expected_commit:
        issues.append(
            f"{artifact_path} commit must match current git commit {expected_commit}; "
            f"observed {artifact_commit or '<empty>'}"
        )
    if require_clean_source and payload.get("source_tree_clean") is not True:
        issues.append(f"{artifact_path} source_tree_clean must be true for promotion evidence")
    environment = payload.get("environment")
    if not isinstance(environment, dict) or not environment:
        issues.append(f"{artifact_path} environment must be a non-empty object")
    _suite_results_pass(payload, artifact_path, issues)

    category = str(requirement["category"])
    evidence_scope = str(payload.get("evidence_scope") or "").strip()
    accepted_scopes = ACCEPTED_EVIDENCE_SCOPES.get(category, set())
    if evidence_scope not in accepted_scopes:
        issues.append(
            f"{artifact_path} evidence_scope must be one of {sorted(accepted_scopes)} "
            f"for {category}"
        )
    if payload.get("secrets_redacted") is not True:
        issues.append(f"{artifact_path} secrets_redacted must be true")
    if payload.get("runtime_ready_claimed") is not False:
        issues.append(f"{artifact_path} runtime_ready_claimed must be false")

    if category == "live_smoke":
        if payload.get("read_only") is not True:
            issues.append(f"{artifact_path} read_only must be true")
        if payload.get("order_submission_attempted") is not False:
            issues.append(f"{artifact_path} order_submission_attempted must be false")
        _validate_live_smoke_endpoint_evidence(
            evidence_id=evidence_id,
            payload=payload,
            artifact_path=artifact_path,
            issues=issues,
        )
        _validate_live_account_environment_evidence(
            evidence_id=evidence_id,
            payload=payload,
            artifact_path=artifact_path,
            issues=issues,
        )
        _validate_live_smoke_suite_evidence(
            evidence_id=evidence_id,
            payload=payload,
            artifact_path=artifact_path,
            issues=issues,
        )
    elif category == "live_recovery":
        _list_of_passing_objects(payload, "recovery_scenarios", artifact_path, issues)
    elif category == "release_evidence":
        _list_of_passing_objects(payload, "release_artifacts", artifact_path, issues)
        _list_of_passing_objects(payload, "platform_results", artifact_path, issues)
        release_artifacts = payload.get("release_artifacts")
        if isinstance(release_artifacts, list) and not any(
            isinstance(item, dict) and str(item.get("name") or "").startswith("Trading-Bot-Rust-")
            for item in release_artifacts
        ):
            issues.append(f"{artifact_path} release_artifacts must include Rust release assets")
        _validate_release_artifact_contract(payload, artifact_path, issues)
        _validate_release_platform_results(payload, artifact_path, issues)

    return issues


def validate(
    manifest_path: Path,
    *,
    require_evidence: bool,
    require_current_commit: bool = False,
    require_clean_source: bool = False,
    evidence_dir_override: Path | None = None,
    requirement_ids: set[str] | None = None,
) -> dict[str, Any]:
    issues: list[str] = []
    manifest_path = _repo_path(manifest_path)
    try:
        manifest = _load_json(manifest_path)
    except ValueError as exc:
        return {
            "ok": False,
            "manifest_path": str(manifest_path),
            "require_evidence": bool(require_evidence),
            "require_current_commit": bool(require_current_commit),
            "require_clean_source": bool(require_clean_source),
            "current_commit": None,
            "current_source_tree_clean": None,
            "issues": [str(exc)],
            "requirements": [],
        }

    if manifest.get("schema_version") != 1:
        issues.append("schema_version must be 1")
    policy = manifest.get("policy")
    if not isinstance(policy, dict):
        issues.append("policy must be an object")
        evidence_dir = Path("artifacts/rust-native-runtime-evidence")
    else:
        if policy.get("no_assumed_passes") is not True:
            issues.append("policy.no_assumed_passes must be true")
        if policy.get("runtime_ready_flag") != "rust_native_trading_runtime_ready() == false":
            issues.append("policy.runtime_ready_flag must keep Rust native runtime readiness false")
        if policy.get("order_submission_forbidden") is not True:
            issues.append("policy.order_submission_forbidden must be true")
        if policy.get("secrets_must_be_redacted") is not True:
            issues.append("policy.secrets_must_be_redacted must be true")
        if policy.get("clean_source_tree_required_for_promotion") is not True:
            issues.append("policy.clean_source_tree_required_for_promotion must be true")
        evidence_dir = Path(str(policy.get("evidence_artifact_dir") or "artifacts/rust-native-runtime-evidence"))
    if evidence_dir_override is not None:
        evidence_dir = evidence_dir_override

    requirements, requirement_issues = _requirements(manifest)
    issues.extend(requirement_issues)
    if requirement_ids is not None:
        unknown_ids = sorted(requirement_ids - set(REQUIRED_REQUIREMENTS))
        if unknown_ids:
            issues.append(f"unknown requested evidence ids: {', '.join(unknown_ids)}")
        requirements = [
            requirement
            for requirement in requirements
            if str(requirement["id"]) in requirement_ids
        ]
        missing_requested = sorted(requirement_ids - {str(requirement["id"]) for requirement in requirements})
        if missing_requested and not unknown_ids:
            issues.append(f"requested evidence ids are not declared in manifest: {', '.join(missing_requested)}")

    current_commit: str | None = None
    if require_evidence and require_current_commit:
        current_commit = _current_git_commit()
        if not current_commit:
            issues.append("current git commit could not be determined for evidence freshness validation")
    current_source_tree_clean: bool | None = None
    if require_evidence and require_clean_source:
        current_source_tree_clean = _current_source_tree_clean()
        if current_source_tree_clean is None:
            issues.append("current source tree cleanliness could not be determined for evidence validation")
        elif not current_source_tree_clean:
            issues.append("current tracked source tree must be clean for promotion evidence validation")

    artifact_status: list[dict[str, Any]] = []
    if require_evidence and requirements:
        root = _repo_root()
        artifact_dir = evidence_dir if evidence_dir.is_absolute() else root / evidence_dir
        for requirement in requirements:
            artifact_path = artifact_dir / f"{requirement['id']}.json"
            artifact_issues = _validate_artifact(
                requirement,
                artifact_path,
                expected_commit=current_commit,
                require_clean_source=require_clean_source,
            )
            artifact_status.append(
                {
                    "id": str(requirement["id"]),
                    "category": str(requirement["category"]),
                    "path": str(artifact_path),
                    "ok": not artifact_issues,
                    "issues": artifact_issues,
                }
            )
            issues.extend(artifact_issues)

    return {
        "ok": not issues,
        "manifest_path": str(manifest_path),
        "require_evidence": bool(require_evidence),
        "require_current_commit": bool(require_current_commit),
        "require_clean_source": bool(require_clean_source),
        "current_commit": current_commit,
        "current_source_tree_clean": current_source_tree_clean,
        "evidence_dir": str(evidence_dir),
        "requirement_count": len(requirements),
        "validated_evidence_ids": [str(requirement["id"]) for requirement in requirements],
        "artifact_status": artifact_status,
        "issues": issues,
        "requirements": requirements,
    }


def _parse_only_values(values: list[str] | None) -> set[str] | None:
    if not values:
        return None
    parsed = {
        item.strip()
        for value in values
        for item in value.split(",")
        if item.strip()
    }
    return parsed or None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST_PATH), help="Rust runtime evidence manifest path.")
    parser.add_argument("--schema-only", action="store_true", help="Validate declarations without requiring artifacts.")
    parser.add_argument("--require-evidence", action="store_true", help="Require passed evidence artifacts.")
    parser.add_argument(
        "--require-current-commit",
        action="store_true",
        help="Require evidence artifacts to match the current committed source revision.",
    )
    parser.add_argument(
        "--require-clean-source",
        action="store_true",
        help="Require a clean tracked source tree and artifacts generated from a clean source tree.",
    )
    parser.add_argument("--evidence-dir", help="Override artifact directory for local or CI evidence validation.")
    parser.add_argument(
        "--only",
        action="append",
        help="Validate only selected evidence ids. Repeat or pass a comma-separated list.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    require_evidence = bool(args.require_evidence and not args.schema_only)
    result = validate(
        Path(args.manifest),
        require_evidence=require_evidence,
        require_current_commit=bool(args.require_current_commit),
        require_clean_source=bool(args.require_clean_source),
        evidence_dir_override=Path(args.evidence_dir) if args.evidence_dir else None,
        requirement_ids=_parse_only_values(args.only),
    )
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result["ok"]:
        print(f"Rust native runtime evidence contract ok: {result['requirement_count']} requirements")
    else:
        print("Rust native runtime evidence contract failed:")
        for issue in result["issues"]:
            print(f"- {issue}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
