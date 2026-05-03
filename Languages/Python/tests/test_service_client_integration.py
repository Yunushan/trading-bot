import os
import subprocess
import sys
import unittest
from pathlib import Path

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from app.desktop import EmbeddedDesktopServiceClient, RemoteDesktopServiceClient, create_desktop_service_client  # noqa: E402
from app.service.runtime import TradingBotService  # noqa: E402


class ServiceClientIntegrationTests(unittest.TestCase):
    def test_desktop_service_client_defaults_to_embedded_mode(self):
        client = create_desktop_service_client(config={"mode": "Paper"})
        self.assertIsInstance(client, EmbeddedDesktopServiceClient)
        descriptor = client.describe()
        self.assertEqual(descriptor.get("client_mode"), "embedded")
        preflight = client.get_operational_preflight()
        self.assertIsInstance(preflight, dict)
        self.assertIn("start", preflight)
        self.assertIn("orders", preflight)

    def test_desktop_service_client_can_be_forced_to_remote_mode(self):
        client = create_desktop_service_client(
            client_mode="remote",
            base_url="http://127.0.0.1:9000",
        )
        self.assertIsInstance(client, RemoteDesktopServiceClient)
        descriptor = client.describe()
        self.assertEqual(descriptor.get("client_mode"), "remote")
        self.assertEqual(descriptor.get("base_url"), "http://127.0.0.1:9000")
        self.assertTrue(callable(getattr(client, "get_operational_preflight", None)))

    def test_service_runtime_imports_without_optional_backtest_or_llm_clients(self):
        script = r'''
import importlib.abc

BLOCKED_PACKAGES = {"pandas", "requests"}

class BlockOptionalClients(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        package_name = fullname.split(".", 1)[0]
        if package_name in BLOCKED_PACKAGES:
            raise ModuleNotFoundError(f"No module named '{package_name}'")
        return None

import sys
sys.meta_path.insert(0, BlockOptionalClients())

from app.core.backtest import normalize_backtest_interval
from app.integrations.llm import build_llm_config_payload
from app.service.runtime import TradingBotService
from app.service.schemas.backtest import build_backtest_snapshot

service = TradingBotService()
assert service.get_config_summary().mode == "Demo/Testnet"
assert normalize_backtest_interval("1 minute") == "1m"
assert build_llm_config_payload({})["provider"] == "openai"
assert build_backtest_snapshot(intervals=["1 minute"]).to_dict()["intervals"] == ["1m"]

try:
    from app.core.backtest import BacktestEngine  # noqa: F401
except ModuleNotFoundError as exc:
    if "pandas" not in str(exc):
        raise
else:
    raise SystemExit("BacktestEngine imported while pandas was blocked")

try:
    from app.integrations.llm import call_llm  # noqa: F401
except ModuleNotFoundError as exc:
    if "requests" not in str(exc):
        raise
else:
    raise SystemExit("call_llm imported while requests was blocked")

print("ok")
'''
        env = dict(os.environ)
        env["PYTHONPATH"] = str(PYTHON_ROOT)
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=PYTHON_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("ok", result.stdout)

    def test_service_terminal_and_llm_config_commands(self):
        service = TradingBotService()

        providers = service.get_llm_provider_catalog()
        provider_by_key = {str(item["key"]): item for item in providers}
        self.assertIn("openai", provider_by_key)
        self.assertIn("anthropic", provider_by_key)
        self.assertIn("gemini", provider_by_key)
        self.assertIn("local", provider_by_key)
        self.assertIn("gpt-5.4-mini", provider_by_key["openai"]["model_suggestions"])
        self.assertIn("gpt-5.3-codex", provider_by_key["openai"]["model_suggestions"])
        self.assertIn("high", provider_by_key["openai"]["reasoning_efforts"])
        self.assertIn("deepseek-v4-flash", provider_by_key["deepseek"]["model_suggestions"])
        self.assertIn("max", provider_by_key["deepseek"]["reasoning_efforts"])
        self.assertEqual("http://127.0.0.1:11434/v1", provider_by_key["local"]["default_base_url"])
        self.assertIn("qwen3:8b", provider_by_key["local"]["model_suggestions"])

        status_result = service.run_terminal_command("status", source="test-terminal").to_dict()
        self.assertTrue(status_result["accepted"])
        self.assertEqual(status_result["exit_code"], 0)
        self.assertIn("lifecycle_phase", status_result["output"])

        llm_result = service.run_terminal_command(
            "llm set llm_provider=deepseek llm_model=deepseek-v4-flash llm_enabled=true llm_reasoning_effort=max",
            source="test-terminal",
        ).to_dict()
        self.assertTrue(llm_result["accepted"])
        llm_config = service.get_llm_config_payload()
        self.assertTrue(llm_config["enabled"])
        self.assertEqual(llm_config["provider"], "deepseek")
        self.assertEqual(llm_config["model"], "deepseek-v4-flash")
        self.assertEqual(llm_config["reasoning_effort"], "max")

        prompt_result = service.run_terminal_command("llm prompt Explain BTC risk", source="test-terminal").to_dict()
        self.assertTrue(prompt_result["accepted"])
        self.assertIn('"dry_run": true', prompt_result["output"])
