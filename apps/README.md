# Applications

Top-level product apps live here instead of under the language-specific
desktop workspace.

- `desktop-pyqt/`: canonical PyQt desktop launcher boundary
- `service-api/`: canonical headless FastAPI launcher boundary
- `web-dashboard/`: thin browser dashboard served by the service API at `/ui/`
- `mobile-client/`: Expo-based Android/iOS thin client
- Mobile and web clients can use the service terminal API for controlled
  commands, but raw OS shell access should stay disabled for remote users.
- Mobile clients expose the shared LLM config surface for cloud providers
  and local/private OpenAI-compatible endpoints; execution stays backend-side.

The desktop and service wrappers currently delegate into `Languages/Python/`
while the repo finishes its product-first migration. The thin web and mobile
clients should talk to the backend API only. Exchange credentials and trading
execution stay on the backend/desktop side.
