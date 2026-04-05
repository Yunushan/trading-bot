# Applications

Top-level product apps live here instead of under the language-specific
desktop workspace.

- `desktop-pyqt/`: canonical PyQt desktop launcher boundary
- `service-api/`: canonical headless FastAPI launcher boundary
- `web-dashboard/`: thin browser dashboard served by the service API at `/ui/`
- `mobile-client/`: Expo-based Android/iOS thin client

The desktop and service wrappers currently delegate into `Languages/Python/`
while the repo finishes its product-first migration. The thin web and mobile
clients should talk to the backend API only. Exchange credentials and trading
execution stay on the backend/desktop side.
