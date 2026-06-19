# Trading Bot C++ Workspace

This directory contains the native Qt/C++ desktop path for the trading-bot workspace.

Today it is a C++ desktop re-platforming path with source-contract parity against the Python/PyQt app in `Languages/Python`. Python remains the trading execution source of truth unless an explicitly tested native helper is being exercised.

## Current role

- Native Qt Widgets desktop shell
- C++23 / Qt 6 build target
- Dashboard, chart, positions, backtest, and web/runtime slices under active restructuring
- Native exchange connectivity experiments, with Binance as the current implemented connector path inside the C++ tree
- Dashboard LLM settings for cloud providers and local/private OpenAI-compatible endpoints

## Current status

| Area | Status | Notes |
| --- | --- | --- |
| Native desktop shell | Active development | Real source tree exists and builds locally |
| Python source-contract parity | Complete | All tracked Python-source parity domains have C++ helper coverage, UI/service delegation, or native regression tests |
| Standalone runtime/product parity | Not complete | Requires native execution ownership plus external release, platform, credential, and installer evidence |
| Primary exchange implementation | Binance | Current connector code in this workspace is Binance-specific |
| Cross-platform Qt build path | Supported for local builds | Windows, macOS, and Linux toolchains are expected |

## Python app contract parity audit

The Python app in `Languages/Python` remains the source of truth for trading
behavior. The C++ workspace has tracked source-contract parity coverage for every
audited domain through native helpers, Qt shell wiring, Service API delegation,
and regression tests. That does not claim standalone runtime/product parity:
release-grade parity still requires native execution ownership and external
platform/installer/credential-gated evidence.

| Python feature domain | C++ status | Contract completion / runtime boundary |
| --- | --- | --- |
| Desktop shell and tabs | Complete Qt tab order, lazy tab lifecycle, theme/startup contract, release ownership, and tab behavior tests | Complete for this domain |
| Service API contract | Complete for generated route/method/schema parity plus native request/response smoke coverage | Complete for this domain |
| Config persistence | Complete native service config schema, save/load, dirty-state, hydration, and redaction behavior | Complete for this domain |
| Strategy runtime | Complete indicator output keys, signal threshold/index semantics, controls normalization, override provenance, and worker lifecycle parity helpers/tests | Complete for this domain |
| Exchange connectors | Complete connector support metadata, Python backend catalog, non-Binance rejection reasons, rate-limit/backoff, and diagnostic health snapshots | Complete for this domain |
| Account, portfolio, and positions | Complete portfolio DTOs, history/allocation ledgers, close-all cache reconciliation, and native parity tests | Complete for this domain |
| Order execution and risk | Complete native order audit, preflight, circuit breaker, submit guards, stop/shutdown guards, and risk behavior | Complete for this domain |
| Backtest engine | Complete mirrored request shape, delegates run/stop to the Python Service API, scanner polling, dashboard import, and provenance coverage | Complete for this domain |
| Charts and heatmaps | Complete chart state payloads, TradingView interval aliases, lightweight asset fallbacks, safe-mode guards, and liquidation provider catalog tests | Complete for this domain |
| Logs, terminal, diagnostics | Complete service log/terminal DTOs, terminal route smoke coverage, and diagnostic redaction tests | Complete for this domain |
| LLM advisory | Complete prompt/config/local-model service route payloads, result redaction, output-policy checks, and local model status tests | Complete for this domain |
| Startup, packaging, platform | Complete canonical entrypoint contracts, startup suppression flags, AppUserModelID/icon metadata, and release smoke contract tests | Complete for this domain |

## Source layout

The `src/` folder is still being reorganized, but it already contains distinct slices such as:

- `TradingBotWindow.dashboard*.cpp`
- `TradingBotWindow.positions.cpp`
- `TradingBotWindow.chart.cpp`
- `TradingBotWindow.backtest.cpp`
- `TradingBotWindow.web.cpp`
- `TradingBotWindow.runtime.cpp`
- `BinanceRestClient.*`
- `BinanceWsClient.*`

## Build

Optional one-shot dependency setup:

```powershell
# Windows
./experiments/native-cpp/tools/install_cpp_dependencies.ps1
```

```bash
# macOS / Linux
chmod +x ./experiments/native-cpp/tools/install_cpp_dependencies.sh
./experiments/native-cpp/tools/install_cpp_dependencies.sh
```

Pinned versions used by the helper scripts:

```text
QtVersion         = 6.11.0
AqtInstallVersion = 3.3.0
VcpkgRef          = d0ba406f0e5352517386709dba49fbabf99a9e3c
```

Manual build:

```bash
cmake -S experiments/native-cpp -B build/binance_cpp
cmake --build build/binance_cpp
```

If Qt auto-detection fails, pass `-DQt6_DIR=/absolute/path/to/lib/cmake/Qt6`.

The helper scripts target `Qt 6.11.0` where the installer path supports it.
`CMakeLists.txt` keeps the minimum supported version at `Qt 6.10.3`, so existing
`6.10.3` kits still build while newer `6.11.x` kits are also accepted.

## Run

```bash
build/binance_cpp/Trading-Bot-C++
```

## Recommendation

Treat this workspace as the native-desktop experimentation and migration path. For day-to-day use, packaging, and the broadest current feature coverage, use the Python app in `Languages/Python`.
