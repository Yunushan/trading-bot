# Trading Bot C++ Workspace

This directory contains the native Qt/C++ desktop path for the trading-bot workspace.

Today it is a C++ desktop re-platforming path with source-contract parity against the Python/PyQt app in `Languages/Python`. Python remains the shared contract source of truth. The C++ dashboard owns its implemented Binance USD-M Futures, Coin-M Futures, and Spot account/order paths directly; other venues remain unsupported or evidence-gated.

## Current role

- Native Qt Widgets desktop shell
- C++23 / Qt 6 build target by default
- Explicit optional C++26 preview-mode build path with compiler-mode validation
- Dashboard, chart, positions, backtest, and web/runtime slices under active restructuring
- Native exchange connectivity experiments, with Binance USD-M Futures, Coin-M Futures, and Spot as the current implemented connector paths inside the C++ tree, including signed account settings, force-order history, position-margin cleanup, and Spot trade history
- Dashboard LLM settings for cloud providers and local/private OpenAI-compatible endpoints

## Current status

| Area | Status | Notes |
| --- | --- | --- |
| Native desktop shell | Active development | Real source tree exists and builds locally |
| Python source-contract parity | Complete | All tracked Python-source parity domains have C++ helper coverage, UI/service delegation, or native regression tests |
| Standalone runtime/product parity | Not complete | Requires native execution ownership plus external release, platform, credential, and installer evidence |
| Primary exchange implementation | Binance markets | Current connector code covers USD-M Futures, Coin-M Futures, and Spot; other venues remain Python-owned or evidence-gated |
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
| Account, portfolio, and positions | Portfolio DTOs, history/allocation helpers, reconciliation, and selected native parity tests | Runtime qualification incomplete: manual close-all and stop-sweep allocation accounting still have known gaps |
| Order execution and risk | Native Binance USD-M/Coin-M Futures and Spot order audit, preflight, circuit breaker, exchange filters, signed submission, account settings, and validated fill-result contracts | Qualification incomplete: durable pending-order recovery and all caller accounting/retry paths still require validation; other venues remain gated |
| Backtest engine | Native C++ historical simulator and batch optimizer are the default local backend, with generated Python indicator defaults, paginated Binance candle loading, cancellation, bounded ranking, dashboard import, and a Python Service API compatibility backend | Complete for the implemented Binance backtest domain; live-trading ownership remains separate |
| Charts and heatmaps | Complete chart state payloads, TradingView interval aliases, lightweight asset fallbacks, safe-mode guards, and liquidation provider catalog tests | Complete for this domain |
| Logs, terminal, diagnostics | Complete controlled terminal UI delegated to the Python Service API, service log/terminal DTOs, terminal route smoke coverage, and diagnostic redaction tests | Complete for this domain |
| LLM advisory | Complete prompt/config/local-model service route payloads, result redaction, output-policy checks, and local model status tests | Complete for this domain |
| Startup, packaging, platform | Complete canonical entrypoint contracts, startup suppression flags, AppUserModelID/icon metadata, and release smoke contract tests | Complete for this domain |

Native REST order results distinguish `executionConfirmed` from `ok`: a valid
partial fill, including one on a canceled or expired order, retains the confirmed
quantity and identity without being reported as a full fill. Invalid identities
or execution quantities never supply a confirmed fill. The chunking wrappers
stop on incomplete outcomes and preserve confirmed quantities in their audit
payloads. Dashboard entry, close and stop submission paths share a UI-thread
session barrier: incomplete or uncertain results retain their identity and block
later submissions, including close sweeps. Confirmed partial quantities are not
replaced by requested quantities, and blocked retries never replay prior fills.
Manual selected-close and close-all submissions use the same session barrier;
an uncertain result stops later closes rather than allowing a retry from another
button. Close actions are serialized against strategy cycles and runtime start/stop,
including events delivered while a confirmation dialog or network request is open.
Chunk helpers check stop state between requests while retaining earlier fills.
Stop requests during a strategy cycle or manual close are deferred until that
action has finished accounting. This ordering does not establish that all native
partial-fill allocation and shared-symbol accounting paths are complete.
Allocation-specific stop closes retain the recorded quantity and cost basis,
cap the submitted quantity to live exposure, and subtract only confirmed execution.
Residual margin is scaled from the allocation even when no table row is present.
The stop path updates a table row only when symbol, direction, interval, and exact
connector key identify a unique match; ambiguous rows await reconciliation.
This does not complete the separate account-wide sweep or manual-close accounting.
The session barrier is not a durable intent store or an account-wide
executor lease; it cannot qualify crash/restart recovery. Complete native position
allocation/accounting and restart reconciliation still need validation. Keep
native live-execution promotion blocked until those requirements are verified.

`native_position_close_tests` exercises the actual Qt close buttons and stop lifecycle
with an isolated loopback exchange fixture, rejecting external proxy, and temporary profile.
It covers blocked and healthy paths,
confirmed-partial identity retention, repeated manual submission after an unknown
Spot result, modal reentrancy and deferred stop. Stop-accounting cases cover unequal
live/allocation quantities, partial and full fills, HTTP/snapshot failures, absent
table rows, and successive allocations sharing one exchange position. It does not
submit real exchange orders or qualify all allocation paths, durable recovery,
or every platform.

## Managed Python execution host

When the C++ dashboard selects a connector or venue outside its direct Binance
runtime boundary, it uses the canonical Python Service API. If the configured
endpoint is loopback and unavailable, C++ automatically starts
`apps/desktop-pyqt/main.py --headless-service`, waits for the Python `status`
route, and stops only the child process it started. Set
`BOT_DESKTOP_SERVICE_API_AUTOSTART=0` to require an already-running service.
Remote endpoints continue to use `BOT_DESKTOP_SERVICE_API_BASE_URL` (or the
host/port variables) and `BOT_SERVICE_API_TOKEN`; C++ never launches a local
process for a non-loopback endpoint.

This is a real Python-owned execution path for feature coverage, not a claim
that C++ has standalone native execution ownership. Native runtime promotion
still requires the separate release, platform, and credential evidence gates.

## Source layout

The `src/` folder is still being reorganized, but it already contains distinct slices such as:

- `TradingBotWindow.dashboard*.cpp`
- `TradingBotWindow.positions.cpp`
- `TradingBotWindow.chart.cpp`
- `TradingBotWindow.backtest.cpp`
- `NativeBacktestRuntime.*`
- `NativeBacktestBatchRuntime.*`
- `NativeIndicatorRuntime.*`
- `NativeStrategyRuntime.*`
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

The native build defaults to strict C++23. C++26 is an explicit opt-in and
never changes the default:

```bash
cmake -S experiments/native-cpp -B build/binance_cpp26 \
  -DTB_CXX_STANDARD=26 \
  -DTB_ENABLE_QT_WEBENGINE=OFF \
  -DTB_REQUIRE_QT_WEBENGINE=OFF
cmake --build build/binance_cpp26
ctest --test-dir build/binance_cpp26 --output-on-failure
```

C++26 requires CMake 3.25 or newer and a compiler preview mode that can build
the complete native test surface: GCC 14+ (`-std=c++26`), Clang/AppleClang
with C++2c support (`-std=c++2c`), or current MSVC (`/std:c++latest`). The
configuration fails closed when the compiler is not recognized, and
`native_cxx_standard_contract_tests` verifies the selected language mode. CI
checks both the GCC 14 and Clang Unix paths; the Windows MSVC path is locally
verified through the same contract and full desktop smoke surface.

If Qt auto-detection fails, pass `-DQt6_DIR=/absolute/path/to/lib/cmake/Qt6`.

The helper scripts target `Qt 6.11.0` where the installer path supports it.
`CMakeLists.txt` keeps the minimum supported version at `Qt 6.10.3`, so existing
`6.10.3` kits still build while newer `6.11.x` kits are also accepted.

## Run

```bash
build/binance_cpp/Trading-Bot-C++
```

## Verify a Windows release bundle

After `windeployqt` has populated a staging directory, copy the matching
app-local MSVC runtime and run the isolated product smoke:

```powershell
./tools/Copy-MsvcRuntimeToBundle.ps1 `
  -BundleDir build/cpp-package/bin `
  -Architecture x64
./tools/Test-NativeCppWindowsBundle.ps1 `
  -BundleDir build/cpp-package/bin `
  -RequireCompilerRuntime
```

The verifier requires the executable, direct Qt libraries, the Windows platform
plugin, WebEngine process/resources/locales, and the MSVC runtime. It removes Qt
development paths from the child process environment and rejects any smoke-test
stderr diagnostics, so a build machine installation cannot hide an incomplete
customer bundle.

## Recommendation

Treat this workspace as the native-desktop experimentation and migration path. For day-to-day use, packaging, and the broadest current feature coverage, use the Python app in `Languages/Python`.
