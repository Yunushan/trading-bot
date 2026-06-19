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
| Windows 10/11 | Official | Official | Official through service host or standalone API | N/A |
| macOS (Intel / Apple Silicon) | Official | Official | Official through standalone API | N/A |
| Linux (major distros) | Official | Official | Official through standalone API | N/A |
| FreeBSD | Evidence-gated via self-hosted workflow | Evidence-gated via source/manual setup | Official through service API when backend is running | N/A |
| BSD family (OpenBSD / NetBSD / DragonFly BSD / others) | Evidence-gated | Evidence-gated | Evidence-gated | N/A |
| Solaris / illumos | Evidence-gated | Evidence-gated | Evidence-gated | N/A |
| Android | N/A | N/A | Browser access available | Scaffolded and evidence-gated native thin client via Expo |
| iOS | N/A | N/A | Browser access available | Scaffolded and evidence-gated native thin client via Expo |

## Architecture coverage

| Architecture | Current status | Notes |
| --- | --- | --- |
| Windows x64 | Official | Release workflow builds Windows x64 binaries |
| Windows ARM64 | Official | Release workflow builds Windows ARM64 binaries |
| Linux x64 | Official | Release workflow builds on Ubuntu 24.04 x64 |
| Linux ARM64 | Official | Release workflow builds on Ubuntu 24.04 ARM |
| macOS Intel | Official | Release workflow includes Intel runners |
| macOS ARM64 | Official | Release workflow includes Apple Silicon runners |
| FreeBSD runner architecture (`uname -m`) | Evidence-gated | Packaging follows the architecture of the available self-hosted runner and must emit release-platform evidence |
| 32-bit x86 desktop | Evidence-gated test target | No official release artifact until matching x86 evidence exists |

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

- The current desktop-first user path is still Windows, macOS, Linux, and FreeBSD.
- The headless backend and service API are the portability layer for BSD family and Solaris/illumos expansion.
- Android and iOS support means a native thin client that talks to the backend API only. It does not move trading execution or exchange/broker credentials onto the phone.
- Multi-exchange crypto support currently means ccxt market/account/order-routing support with official live support gated on venue evidence.

## Current automation notes

- Main CI now includes a lightweight Windows/macOS/Linux service/runtime smoke in addition to the full Ubuntu quality jobs.
- `docs/release-platform-test-matrix.json` and `tools/check_release_platform_matrix.py` are the source of truth for OS/browser evidence targets.
- `docs/connector-support-matrix.json` and `tools/check_connector_support_matrix.py` are the source of truth for venue/broker connector evidence targets.
- FreeBSD and other non-hosted platforms depend on matching self-hosted or external-lab runners before they can be called official.
- Android and iOS currently start from the Expo app in `apps/mobile-client/`.
