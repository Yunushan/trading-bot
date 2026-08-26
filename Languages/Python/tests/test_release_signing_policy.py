from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[3]
CHECKER_PATH = REPO_ROOT / "tools" / "check_release_signing_policy.py"
POLICY_PATH = REPO_ROOT / "docs" / "release-signing-policy.json"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_release_signing_policy", CHECKER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_canonical_release_signing_policy_passes() -> None:
    checker = _load_checker()

    report = checker.audit_policy(root=REPO_ROOT)

    assert report["ok"] is True
    assert report["issues"] == []
    assert report["external_credentials_configured"] is None
    assert report["external_signing_evidence_collected"] is False


def test_release_signing_policy_rejects_disabled_fail_closed_flag() -> None:
    checker = _load_checker()
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    policy["policy"]["missing_credentials_fail_closed"] = False

    with tempfile.TemporaryDirectory() as temp_dir:
        mutated_policy = Path(temp_dir) / "release-signing-policy.json"
        mutated_policy.write_text(json.dumps(policy), encoding="utf-8")
        report = checker.audit_policy(root=REPO_ROOT, policy_path=mutated_policy)

    assert report["ok"] is False
    assert report["checks"]["policy_missing_credentials_fail_closed"] is False
    assert "policy.missing_credentials_fail_closed must be true" in report["issues"]


def test_release_signing_policy_rejects_timestamp_host_prefix_bypass() -> None:
    checker = _load_checker()
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    policy["windows"]["timestamp_url"] = "http://timestamp.digicert.com.attacker.invalid"

    with tempfile.TemporaryDirectory() as temp_dir:
        mutated_policy = Path(temp_dir) / "release-signing-policy.json"
        mutated_policy.write_text(json.dumps(policy), encoding="utf-8")
        report = checker.audit_policy(root=REPO_ROOT, policy_path=mutated_policy)

    assert report["ok"] is False
    assert report["checks"]["windows_crypto"] is False
