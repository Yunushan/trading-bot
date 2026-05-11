# Architecture Boundaries

The current app is still desktop-first, but shared behavior should keep moving into testable runtime and domain modules.

## Current Boundaries

- `apps/desktop-pyqt/`: product launcher for the PyQt desktop app.
- `apps/service-api/`: product launcher for the headless API service.
- `apps/web-dashboard/`: thin browser client for the service API.
- `apps/mobile-client/`: Expo thin client scaffold.
- `Languages/Python/app/`: current desktop/service runtime implementation.
- `Languages/Python/trading_core/`: reusable trading-domain package boundary.

## Direction

- GUI modules should own presentation, user input, and view refresh only.
- Service modules should own API schemas, transport, runtime coordination, and persistence.
- `trading_core` should own deterministic trading-domain logic such as order intent validation, sizing constraints, risk calculations, and backtest/live parity helpers.
- LLM integrations must stay advisory. Strategy, risk, take-profit, stop-loss, and order execution remain deterministic runtime responsibilities. LLM client code should reject output that looks like direct execution, not route around runtime guards.

## Review Rule

When adding a feature, first decide whether it is UI behavior, service transport, exchange integration, or trading-domain behavior. Prefer the narrowest layer. Avoid putting reusable order/risk logic directly inside PyQt widgets.
