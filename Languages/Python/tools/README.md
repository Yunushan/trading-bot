# Python Tools

Utility scripts for the Python workspace live here.

Run all commands from `Languages/Python/` unless a script says otherwise.

## Launchers and packaging

| File | Purpose |
| --- | --- |
| `Trading-Bot-Python.bat` | Windows launcher that bootstraps the virtual environment and starts the desktop app |
| `tools/build_exe.ps1` | Windows PyInstaller build script for `Trading-Bot-Python.exe`, packaging the canonical desktop wrapper in `apps/desktop-pyqt/` |
| `tools/build_binary.sh` | Unix shell build wrapper for standalone Python binary packaging, packaging the canonical desktop wrapper in `apps/desktop-pyqt/` |

## Runtime and strategy helpers

| File | Purpose |
| --- | --- |
| `tools/check_dependency_metadata.py` | Verifies Python version metadata, dependency pin policy, requirement shim files, and CI install surface |
| `tools/check_service_api_contracts.py` | Checks `apps/service-api/contracts/*` and can refresh the generated route contract with `--write` |
| `tools/run_python_tests.py` | Runs the full Python test suite after checking desktop/service/dev dependencies |
| `tools/run_service_tests.py` | Runs the focused service API/unit/integration test modules as one stable command |
| `tools/import_policy.py` | Canonical-import registry and deprecated-wrapper policy used by architecture tests |
| `tools/manual_smoke.py` | Local manual smoke check for desktop imports, service health/API auth/config validation, and a fake exchange order flow |
| `tools/configure_margin.py` | Quick CLI helper for Binance futures leverage and margin-mode setup |
| `tools/hold.py` | Small strategy harness for exercising indicator close/hold behavior without launching the full GUI |
| `tools/lot_cli_demo.py` | CLI-oriented sizing/lot-step demo helper |
| `tools/scan_backtest_2025.py` | Batch-style backtest scanning helper |
| `tools/dump_snippet.py` | Small extraction/debug helper for local code or text snippets |

## Common examples

Full local dev/test install:

```bash
python ../../tools/bootstrap_local_dev.py --dry-run
python -m pip install -e ".[desktop,service,dev]"
python tools/run_python_tests.py
```

If the active shell Python is not the repository Python, pass the target command:

```powershell
python ../../tools/check_local_tool_versions.py --strict --skip-node --python-command "python"
python ../../tools/bootstrap_local_dev.py --python-command "python" --dry-run
```

Focused service suite:

```bash
python tools/run_service_tests.py
python tools/run_service_tests.py --check-list
python tools/run_service_tests.py --check-docs
python tools/run_service_tests.py --print-markdown
```

Full Python suite:

```bash
python tools/run_python_tests.py
python tools/run_python_tests.py --runner unittest
python tools/run_python_tests.py --check-deps
```

Focused service test map:

| Module | Use when checking |
| --- | --- |
| `tests.test_service_api_http_contract` | HTTP route contracts, auth behavior, SSE auth, and runtime/dashboard responses |
| `tests.test_service_schema_contracts` | service response schema builders, payload normalization, and secret redaction contracts |
| `tests.test_service_config_runtime` | service config validation and durable config persistence |
| `tests.test_service_operational_runtime` | operational health snapshots, connector incidents, JSONL rotation, and redaction |
| `tests.test_service_lifecycle_runtime` | lifecycle control, control-plane descriptors, runtime samples, and live preflight gates |
| `tests.test_service_client_integration` | desktop service client selection and service terminal/LLM commands |
| `tests.test_service_background_host_integration` | embedded background host and background-hosted backtest API flows |
| `tests.test_service_product_main` | canonical service CLI commands, remote requests, validation, and error boundaries |

Windows launcher:

```text
Double-click Trading-Bot-Python.bat
```

Windows standalone build:

```powershell
./tools/build_exe.ps1
```

Unix standalone build:

```bash
./tools/build_binary.sh
```

Margin helper:

```bash
python tools/configure_margin.py <api_key> <api_secret> <mode> <leverage> <ISOLATED|CROSS> BTCUSDT ETHUSDT
```

Manual desktop/service smoke check:

```bash
python tools/manual_smoke.py
```

Fast no-server variant:

```bash
python tools/manual_smoke.py --skip-http
```

Dependency metadata check:

```bash
python tools/check_dependency_metadata.py
```

Service API contract check:

```bash
python tools/check_service_api_contracts.py
python tools/check_service_api_contracts.py --write
```
