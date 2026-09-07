"""Offline order-intent storage administration; never contacts an exchange."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from types import SimpleNamespace

from app.settings.live_safety import LiveTradingSafetyError

from .order_intent_provisioning import provision_order_intent_store
from .order_intent_runtime import get_order_intent_status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "initialize", "migrate"))
    paths = parser.add_mutually_exclusive_group(required=True)
    paths.add_argument("--audit-log-path", type=Path, help="The exact audit path used by the runtime.")
    paths.add_argument("--default-intent-path", action="store_true", help="Use only when no audit path is configured.")
    parser.add_argument("--mode", choices=("Live", "Demo/Testnet"), required=True)
    parser.add_argument("--api-key-env", required=True, help="Environment variable containing the runtime API key; never pass its value.")
    parser.add_argument("--acknowledgement", default="")
    args = parser.parse_args(argv)
    owner = SimpleNamespace(_order_audit_log_path=args.audit_log_path, mode=args.mode, api_key=os.environ.get(args.api_key_env))
    try:
        if args.action == "status":
            result = get_order_intent_status(owner)
        else:
            result = provision_order_intent_store(owner, acknowledgement=args.acknowledgement, migrate=args.action == "migrate")
    except LiveTradingSafetyError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps({"ok": True, **result}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
