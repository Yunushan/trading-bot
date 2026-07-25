# Support Matrix

This repository now spans multiple runtime shapes, so platform support is not a single yes/no answer.

## Support tiers

- `Official`: actively documented and represented in current release automation
- `Experimental`: architecture is intended to work, but release automation or full GUI validation is not in place
- `Evidence-gated`: target is declared and checkable, but it must provide a passed evidence artifact before it is official
- `Scaffolded`: starter client/app exists, but it is not yet a complete end-user feature set
- `Not supported today`: not shipped as a working connector/runtime in the current repo
- `Not targeted`: no current packaging or support target

## Matrix

| Platform | Desktop PyQt GUI | Headless Service API | Thin Web GUI | Native Mobile Client |
| --- | --- | --- | --- | --- |
| Windows 11 x64 | Evidence-gated | Supported through service host or standalone API | Supported through service host or standalone API | N/A |
| macOS 15 ARM64 | Evidence-gated | Supported through standalone API | Supported through standalone API | N/A |
| Ubuntu 24.04 x64 | Evidence-gated | Supported through standalone API | Supported through standalone API | N/A |
| Other Windows, macOS, and Linux variants | Experimental | Experimental | Browser access where supported | N/A |
| BSD / Solaris | Not targeted for desktop release | Experimental source/manual service path only | Browser access requires an externally operated backend | N/A |
| Android | N/A | N/A | Browser access available | Scaffolded native thin client via Expo |
| iOS | N/A | N/A | Browser access available | Scaffolded native thin client via Expo |

## Architecture coverage

| Architecture | Current status | Notes |
| --- | --- | --- |
| Windows 11 x64 | Evidence-gated | Tier-1 release target; official status requires current release evidence |
| Ubuntu 24.04 x64 | Evidence-gated | Tier-1 release target; official status requires current release evidence |
| macOS 15 ARM64 | Evidence-gated | Tier-1 release target; official status requires current release evidence |
| Windows ARM64 / x86, Linux ARM64, macOS Intel | Experimental | No release claim until explicitly added to the matrix with passing evidence |
| FreeBSD and other BSD architectures | Not targeted for desktop release | Source/manual service path does not imply a packaged desktop release |

## Market coverage

| Market / scope | Current status | Notes |
| --- | --- | --- |
| Crypto spot | Official | Current live implementation is Binance-led |
| Crypto futures | Official | Primary live/demo path today |
| Multi-exchange crypto expansion | Order-routing supported / evidence-gated | ccxt market/account diagnostics and guarded order routing are implemented for the listed venues; official live support requires venue evidence |
| FX / broker integrations | Order-routing supported / evidence-gated | OANDA REST-v20, FXCM fxcmpy, IG REST, and official MetaTrader 5 connector paths are implemented with guarded live submission; official live support requires per-broker evidence |
| Scoped non-forex broker APIs | Order-routing supported / evidence-gated | Trading 212 supports Invest/Stocks ISA equities, moomoo OpenD supports its documented multi-market scope, and CITIC Futures CTP supports China futures/options; none claims forex routing |
| Markets outside the current crypto/FX scope | Not targeted | Would require new connector design and validation |

## Venue / connector coverage

| Venue / connector group | Current status | Notes |
| --- | --- | --- |
| Binance | Official | Current primary live/demo connector |
| Bybit / OKX / Bitget / Gate / MEXC / KuCoin | Order-routing supported / evidence-gated | Python, C++, and Rust support metadata accept these through ccxt for market/account/order routing; official live support remains evidence-gated |
| HTX / Crypto.com Exchange / Kraken / Bitfinex | Order-routing supported / evidence-gated | Python, C++, and Rust support metadata accept these through ccxt for market/account/order routing; official live support remains evidence-gated |
| OANDA / FXCM / IG | Order-routing supported / evidence-gated | Broker connector paths exist for OANDA REST-v20, FXCM fxcmpy, and IG REST; official live support remains evidence-gated |
| Trade Nation / FXTF / FOREX EXCHANGE | MT4 bridge order-routing supported / evidence-gated | The included token-authenticated local/remote bridge and `TradingBotBridge.mq4` Expert Advisor implement account/market/open-order/open-position reads plus independently guarded submit, cancel, and close operations; each broker still requires terminal/account evidence |
| 36 official-source MT5 brokers | Order-routing supported / evidence-gated | AvaTrade, EC Markets, GTCFX, Finalto, ATFX, Vantage, STARTRADER, XM, TMGM, Capital.com, IC Markets Global, Hantec Financial, GO Markets, VT Markets, Neex, ACY Securities, Fortune Prime Global, DecodeFX, CPT Markets, PU Prime, AIMS, ETO Markets, D Prime, Fusion Markets, Exness, Valetax, CXM, DBG Markets, FXT, Plotio, FOREX.com, CMC Markets, SBCFX, PhillipCapital (Phillip Nova), StoneX, and AI Gold Securities share the Python-owned MT5 terminal connector; StoneX is futures/options-on-futures scoped, AI Gold Securities is OTC-commodity scoped, and each broker requires its own evidence artifact |
| Trading 212 | Equity order-routing supported / forex unavailable / evidence-gated | The official beta Public API supports Invest/Stocks ISA account, instrument, position, pending-order, cancellation, and market/limit/stop/stop-limit operations; CFD/forex routing is not exposed |
| moomoo | Multi-market order-routing supported / forex unavailable / evidence-gated | The official `moomoo-api` SDK uses a local or remote OpenD gateway for account, market, position, open-order, cancellation, and advanced order operations; OpenD and per-account evidence are required |
| CITIC Futures | Futures/options order-routing supported / forex unavailable / evidence-gated | The official CTP interface and published test fronts are implemented through `openctp-ctp`, including authentication, settlement confirmation, account/position/order/instrument/market queries, guarded submission, and cancellation; production access remains evidence-gated |
| Unlisted venues | Not supported today | Requires new connector work |

## Requested broker accounting

The named broker request contains 49 targets. Python's `REQUESTED_BROKER_TARGETS` registry and the connector matrix account for every spelling, including `philipsecurities` and `cmc markes`: 44 have implemented connector routes, of which 39 expose forex order routing and 5 expose only a verified non-forex scope. All 44 remain individually live-evidence-gated.

The other five targets cannot be implemented from a public protocol contract. They are intentionally not added to `SUPPORTED_BROKERS`:

| Broker | Recorded disposition | Required external input |
| --- | --- | --- |
| Mitrade | Proprietary web/desktop/mobile platform; no public order API contract identified | Provider-authorized order API contract |
| AXPM | Proprietary web/desktop/mobile platform; no public order API contract identified | Provider-authorized order API contract |
| Spreadex | Proprietary web/mobile platform; no public order API contract identified | Provider-authorized order API contract |
| Jefferies | Electronic access is private client FIX/web access | Onboarded client FIX contract and test session |
| Marex | API and FIX connectivity is offered to clients | Onboarded client API/FIX contract and test session |

These are external prerequisites, not passing support claims. `tools/check_connector_support_matrix.py --schema-only` fails if a requested name becomes unclassified, loses its official source, is falsely marked supported, or drifts from these counts.

## Practical interpretation

- The current release-eligible desktop path is Windows 11 x64, macOS 15 ARM64, and Ubuntu 24.04 x64; each remains evidence-gated until a matching release artifact is verified.
- Other platforms may work through the source/manual service path, but are not release-supported until the matrix and real evidence are expanded.
- Android and iOS support means a native thin client that talks to the backend API only. It does not move trading execution or exchange/broker credentials onto the phone.
- Multi-exchange crypto support currently means ccxt market/account/order-routing support with official live support gated on venue evidence.
- Trade Nation, FXTF, and FOREX EXCHANGE currently expose MT4 rather than an active public REST/MT5 order API. Their connector uses the included `Languages/MQL4/Experts/TradingBotBridge.mq4` agent and Python bridge host. Loopback HTTP is allowed; remote bridge URLs must use HTTPS. Python and the EA have separate live-order switches, and the EA persists mutation receipts before execution to prevent acknowledgement loss from replaying an order.
- The official `MetaTrader5` Python package currently ships Windows x64 wheels. MT5 broker execution therefore requires a local Windows x64 MT5 terminal (or the Python service hosted on such a machine); macOS/Linux/mobile clients use the service API and do not execute MT5 locally.
- Trading 212 support is deliberately listed in the general broker catalog but excluded from the forex-capable broker catalog. Its public API can use official demo/live endpoints or an explicit remote base URL, and every network order remains opt-in and evidence-gated.
- moomoo is also in the general broker catalog rather than the forex-capable list. The connector accepts a local or remote OpenD hostname/IP and port, closes SDK contexts deterministically, and requires explicit opt-in before any SDK order or cancellation call.
- StoneX is in the general MT5 broker catalog but not the forex-capable catalog: the verified public MT5 route is StoneX Futures, while institutional StoneX Pro FX/FIX connectivity remains onboarding-gated and is not claimed as implemented.
- AI Gold Securities is in the general MT5 broker catalog but not the forex-capable catalog: its official MTcX route exposes OTC commodity derivatives through MT5. `AI Gold` is accepted as an alias.
- PhillipCapital's active retail MT5 route is offered by Phillip Nova. `Phillip Securities` and the common one-l spelling `Philip Securities` are accepted aliases, but the connector reports the operating MT5 provider name.
- CITIC Futures is in the general broker catalog but outside the forex-capable list. Its connector accepts an official or custom `tcp://host:port` CTP front and requires explicit live-order opt-in; production AppID/AuthCode approval and a passed account artifact remain mandatory.

## Current automation notes

- Main CI now includes a lightweight Windows/macOS/Linux service/runtime smoke in addition to the full Ubuntu quality jobs.
- `docs/release-platform-test-matrix.json` and `tools/check_release_platform_matrix.py` are the source of truth for OS/browser evidence targets.
- `docs/connector-support-matrix.json` and `tools/check_connector_support_matrix.py` are the source of truth for venue/broker connector evidence targets.
- The matrix intentionally excludes legacy operating systems, Internet Explorer, mobile device releases, and unprovisioned external labs; they must be explicitly reintroduced with matching evidence before any support claim is made.
- Android and iOS currently start from the Expo app in `apps/mobile-client/`.
