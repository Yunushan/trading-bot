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
| FX / broker integrations | Order-routing supported / evidence-gated | OANDA REST-v20, FXCM fxcmpy, and IG REST connector paths are implemented with guarded live submission; official live support requires broker evidence |
| Markets outside the current crypto/FX scope | Not targeted | Would require new connector design and validation |

## Venue / connector coverage

| Venue / connector group | Current status | Notes |
| --- | --- | --- |
| Binance | Official | Current primary live/demo connector |
| Bybit / OKX / Bitget / Gate / MEXC / KuCoin | Order-routing supported / evidence-gated | Python, C++, and Rust support metadata accept these through ccxt for market/account/order routing; official live support remains evidence-gated |
| HTX / Crypto.com Exchange / Kraken / Bitfinex | Order-routing supported / evidence-gated | Python, C++, and Rust support metadata accept these through ccxt for market/account/order routing; official live support remains evidence-gated |
| OANDA / FXCM / IG | Order-routing supported / evidence-gated | Broker connector paths exist for OANDA REST-v20, FXCM fxcmpy, and IG REST; official live support remains evidence-gated |
| Unlisted venues | Not supported today | Requires new connector work |

## Practical interpretation

- The current release-eligible desktop path is Windows 11 x64, macOS 15 ARM64, and Ubuntu 24.04 x64; each remains evidence-gated until a matching release artifact is verified.
- Other platforms may work through the source/manual service path, but are not release-supported until the matrix and real evidence are expanded.
- Android and iOS support means a native thin client that talks to the backend API only. It does not move trading execution or exchange/broker credentials onto the phone.
- Multi-exchange crypto support currently means ccxt market/account/order-routing support with official live support gated on venue evidence.

## Current automation notes

- Main CI now includes a lightweight Windows/macOS/Linux service/runtime smoke in addition to the full Ubuntu quality jobs.
- `docs/release-platform-test-matrix.json` and `tools/check_release_platform_matrix.py` are the source of truth for OS/browser evidence targets.
- `docs/connector-support-matrix.json` and `tools/check_connector_support_matrix.py` are the source of truth for venue/broker connector evidence targets.
- The matrix intentionally excludes legacy operating systems, Internet Explorer, mobile device releases, and unprovisioned external labs; they must be explicitly reintroduced with matching evidence before any support claim is made.
- Android and iOS currently start from the Expo app in `apps/mobile-client/`.
