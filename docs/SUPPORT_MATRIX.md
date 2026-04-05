# Support Matrix

This repository now spans multiple runtime shapes, so platform support is not a single yes/no answer.

## Support tiers

- `Official`: actively documented and represented in current release automation
- `Experimental`: architecture is intended to work, but release automation or full GUI validation is not in place
- `Scaffolded`: starter client/app exists, but it is not yet a complete end-user feature set
- `Not supported today`: not shipped as a working connector/runtime in the current repo
- `Not targeted`: no current packaging or support target

## Matrix

| Platform | Desktop PyQt GUI | Headless Service API | Thin Web GUI | Native Mobile Client |
| --- | --- | --- | --- | --- |
| Windows 10/11 | Official | Official | Official through service host or standalone API | N/A |
| macOS (Intel / Apple Silicon) | Official | Official | Official through standalone API | N/A |
| Linux (major distros) | Official | Official | Official through standalone API | N/A |
| FreeBSD | Official-ish via self-hosted workflow | Official-ish via source/manual setup | Official through service API when backend is running | N/A |
| BSD family (OpenBSD / NetBSD / DragonFly BSD / others) | Experimental | Experimental | Experimental | N/A |
| Solaris / illumos | Experimental | Experimental | Experimental | N/A |
| Android | N/A | N/A | Browser access available | Scaffolded native thin client via Expo |
| iOS | N/A | N/A | Browser access available | Scaffolded native thin client via Expo |

## Architecture coverage

| Architecture | Current status | Notes |
| --- | --- | --- |
| Windows x64 | Official | Release workflow builds Windows x64 binaries |
| Windows ARM64 | Official | Release workflow builds Windows ARM64 binaries |
| Linux x64 | Official | Release workflow builds on Ubuntu 24.04 x64 |
| Linux ARM64 | Official | Release workflow builds on Ubuntu 24.04 ARM |
| macOS Intel | Official | Release workflow includes Intel runners |
| macOS ARM64 | Official | Release workflow includes Apple Silicon runners |
| FreeBSD runner architecture (`uname -m`) | Experimental | Packaging follows the architecture of the available self-hosted runner |
| 32-bit x86 desktop | Not targeted | No current packaging or CI target |

## Market coverage

| Market / scope | Current status | Notes |
| --- | --- | --- |
| Crypto spot | Official | Current live implementation is Binance-led |
| Crypto futures | Official | Primary live/demo path today |
| Multi-exchange crypto expansion | Experimental | UI/service/catalog groundwork exists, but connector parity is incomplete |
| FX / broker integrations | Experimental | Architecture and UI placeholders exist; production live connectors are not shipped yet |
| Markets outside the current crypto/FX scope | Not targeted | Would require new connector design and validation |

## Venue / connector coverage

| Venue / connector group | Current status | Notes |
| --- | --- | --- |
| Binance | Official | Current primary live/demo connector |
| Bybit / OKX / Bitget / Gate / MEXC / KuCoin | Experimental | Listed in the exchange catalog, but not shipped as completed live connectors yet |
| HTX / Crypto.com Exchange / Kraken / Bitfinex | Experimental | Catalog presence only today |
| OANDA / FXCM / IG | Experimental | Broker placeholders exist; no shipped production connector yet |
| Unlisted venues | Not supported today | Requires new connector work |

## Practical interpretation

- The current desktop-first user path is still Windows, macOS, Linux, and FreeBSD.
- The headless backend and service API are the portability layer for BSD family and Solaris/illumos expansion.
- Android and iOS support means a native thin client that talks to the backend API only. It does not move trading execution or exchange/broker credentials onto the phone.

## Current automation notes

- FreeBSD is the only BSD target with a dedicated GitHub workflow today, and it still depends on a matching self-hosted runner.
- Other BSD variants and Solaris/illumos are currently `manual / best-effort` targets.
- Android and iOS currently start from the Expo app in `apps/mobile-client/`.
