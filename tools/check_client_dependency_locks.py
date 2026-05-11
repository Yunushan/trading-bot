from __future__ import annotations

import argparse
import json
from pathlib import Path


EXPECTED_PACKAGE_MANAGER = "npm@11.6.2"
EXPECTED_NODE_ENGINE = ">=24 <25"
CLIENTS = ("apps/web-dashboard", "apps/mobile-client")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def check_client_dependency_locks(root: Path | None = None) -> dict[str, object]:
    repo_root = root or _repo_root()
    clients: list[dict[str, object]] = []
    errors: list[str] = []
    for rel_path in CLIENTS:
        client_dir = repo_root / rel_path
        package_path = client_dir / "package.json"
        lock_path = client_dir / "package-lock.json"
        try:
            package = _load_json(package_path)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            clients.append(
                {
                    "path": rel_path,
                    "package_json": f"{rel_path}/package.json",
                    "package_json_ok": False,
                    "lockfile": f"{rel_path}/package-lock.json",
                    "lockfile_exists": lock_path.is_file(),
                }
            )
            errors.append(f"{rel_path}/package.json is unreadable: {exc}")
            continue
        package_manager = str(package.get("packageManager") or "")
        engines = package.get("engines") if isinstance(package.get("engines"), dict) else {}
        node_engine = str(engines.get("node") or "")
        lock_exists = lock_path.is_file()
        client = {
            "path": rel_path,
            "package_manager": package_manager,
            "expected_package_manager": EXPECTED_PACKAGE_MANAGER,
            "package_manager_ok": package_manager == EXPECTED_PACKAGE_MANAGER,
            "node_engine": node_engine,
            "expected_node_engine": EXPECTED_NODE_ENGINE,
            "node_engine_ok": node_engine == EXPECTED_NODE_ENGINE,
            "lockfile": f"{rel_path}/package-lock.json",
            "lockfile_exists": lock_exists,
        }
        clients.append(client)
        if not client["package_manager_ok"]:
            errors.append(f"{rel_path} packageManager is {package_manager!r}; expected {EXPECTED_PACKAGE_MANAGER!r}")
        if not client["node_engine_ok"]:
            errors.append(f"{rel_path} engines.node is {node_engine!r}; expected {EXPECTED_NODE_ENGINE!r}")
        if not lock_exists:
            errors.append(f"{rel_path}/package-lock.json is missing")
    return {"ok": not errors, "clients": clients, "errors": errors}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check web/mobile package manager metadata and lockfiles.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when metadata or lockfiles are missing.")
    args = parser.parse_args(argv)
    report = check_client_dependency_locks()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        status = "ok" if report["ok"] else "needs attention"
        print(f"Client dependency locks: {status}")
        for error in report["errors"]:
            print(f"- {error}")
    return 1 if args.strict and not report["ok"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
