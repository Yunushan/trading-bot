import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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
        self.assertIn("gpt-5.5-pro", provider_by_key["openai"]["model_suggestions"])
        self.assertIn("gpt-5.4-pro", provider_by_key["openai"]["model_suggestions"])
        self.assertIn("gpt-5.4-mini", provider_by_key["openai"]["model_suggestions"])
        self.assertIn("gpt-5.4-nano-2026-03-17", provider_by_key["openai"]["model_suggestions"])
        self.assertIn("gpt-4.1-mini", provider_by_key["openai"]["model_suggestions"])
        self.assertIn("gpt-5.3-codex", provider_by_key["openai"]["model_suggestions"])
        self.assertIn("high", provider_by_key["openai"]["reasoning_efforts"])
        self.assertIn("claude-opus-4-5-20251101", provider_by_key["anthropic"]["model_suggestions"])
        self.assertIn("gemini-3.1-pro-preview", provider_by_key["gemini"]["model_suggestions"])
        self.assertNotIn("gemini-3-pro-preview", provider_by_key["gemini"]["model_suggestions"])
        self.assertIn("deepseek-v4-flash", provider_by_key["deepseek"]["model_suggestions"])
        self.assertIn("max", provider_by_key["deepseek"]["reasoning_efforts"])
        self.assertEqual("https://api.mistral.ai/v1", provider_by_key["mistral"]["default_base_url"])
        self.assertIn("mistral-small-latest", provider_by_key["mistral"]["model_suggestions"])
        self.assertEqual("MISTRAL_API_KEY", provider_by_key["mistral"]["api_key_env"])
        self.assertEqual("grok-4.3", provider_by_key["grok"]["default_model"])
        self.assertIn("grok-4.3", provider_by_key["grok"]["model_suggestions"])
        self.assertIn("qwen3.6-plus", provider_by_key["qwen"]["model_suggestions"])
        self.assertIn("qwen3.6-flash-2026-04-16", provider_by_key["qwen"]["model_suggestions"])
        self.assertEqual("http://127.0.0.1:11434/v1", provider_by_key["local"]["default_base_url"])
        self.assertEqual("qwen3:8b", provider_by_key["local"]["default_model"])
        self.assertIn("qwen3:8b", provider_by_key["local"]["model_suggestions"])
        self.assertIn("qwen3:4b", provider_by_key["local"]["model_suggestions"])
        self.assertIn("qwen3:1.7b", provider_by_key["local"]["model_suggestions"])
        self.assertIn("qwen3:32b", provider_by_key["local"]["model_suggestions"])
        self.assertEqual("BOT_LLM_EXTRA_MODELS_LOCAL", provider_by_key["local"]["custom_models_env"])
        self.assertEqual("BOT_LLM_MODEL_CATALOG_PATH", provider_by_key["local"]["custom_models_path_env"])
        self.assertIn("catalog_revision", provider_by_key["local"])

        with mock.patch.dict(os.environ, {"BOT_LLM_EXTRA_MODELS_LOCAL": "qwen3:32b,my-local-model"}, clear=False):
            override_catalog = service.get_llm_provider_catalog()
        override_local = {str(item["key"]): item for item in override_catalog}["local"]
        self.assertIn("qwen3:32b", override_local["model_suggestions"])
        self.assertIn("my-local-model", override_local["model_suggestions"])
        self.assertTrue(service.get_llm_config_payload()["execution_policy"]["advisory_only"])
        self.assertFalse(service.get_llm_config_payload()["execution_policy"]["can_execute_orders"])
        self.assertIn("catalog_revision", service.get_llm_config_payload())
        self.assertEqual("BOT_LLM_MODEL_CATALOG_PATH", service.get_llm_config_payload()["custom_models_path_env"])

        with tempfile.TemporaryDirectory() as tmp:
            catalog_path = Path(tmp) / "llm-models.json"
            catalog_path.write_text(
                json.dumps({"providers": {"local": ["qwen3:32b"], "openai": ["gpt-custom"]}}),
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {"BOT_LLM_MODEL_CATALOG_PATH": str(catalog_path)}, clear=False):
                file_catalog = service.get_llm_provider_catalog()
        file_provider_by_key = {str(item["key"]): item for item in file_catalog}
        self.assertIn("qwen3:32b", file_provider_by_key["local"]["model_suggestions"])
        self.assertIn("gpt-custom", file_provider_by_key["openai"]["model_suggestions"])

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
