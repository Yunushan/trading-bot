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
| `tools/import_policy.py` | Canonical-import registry and deprecated-wrapper policy used by architecture tests |
| `tools/manual_smoke.py` | Local manual smoke check for desktop imports, service health/API auth/config validation, and a fake exchange order flow |
| `tools/configure_margin.py` | Quick CLI helper for Binance futures leverage and margin-mode setup |
| `tools/hold.py` | Small strategy harness for exercising indicator close/hold behavior without launching the full GUI |
| `tools/lot_cli_demo.py` | CLI-oriented sizing/lot-step demo helper |
| `tools/scan_backtest_2025.py` | Batch-style backtest scanning helper |
| `tools/dump_snippet.py` | Small extraction/debug helper for local code or text snippets |

## Common examples

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
