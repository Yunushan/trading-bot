# Docker Backend

Optional container packaging for the Trading Bot service API.

`backend.Dockerfile` pins its Python base image by digest for reproducible
builds. Refresh that digest through the reviewed Docker Dependabot update path.

This Docker path packages the headless backend only. It does **not** try to run the PyQt desktop GUI. The container now boots the canonical product wrapper at `apps/service-api/main.py` and includes the thin dashboard assets from `apps/web-dashboard/`.

## Build and run

From the repository root:

```bash
docker compose -f docker/compose.yaml up --build
```

The API will listen on:

```text
http://127.0.0.1:8000
```

## Required bearer token

The container binds the app inside Docker to `0.0.0.0` and publishes it on host-local
`127.0.0.1:8000`, so a bearer token is required before launch:

```bash
export BOT_SERVICE_API_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
docker compose -f docker/compose.yaml up --build
```

PowerShell:

```powershell
$env:BOT_SERVICE_API_TOKEN=(python -c "import secrets; print(secrets.token_urlsafe(32))")
docker compose -f docker/compose.yaml up --build
```

For a production orchestrator, prefer a mounted secret file over an environment
variable. Leave `BOT_SERVICE_API_TOKEN` unset and configure
`BOT_SERVICE_API_TOKEN_FILE=/run/secrets/service_api_token`; the file must be
readable by the container user and no larger than 4 KiB. The explicit CLI token
takes precedence, followed by `BOT_SERVICE_API_TOKEN`, then the file value.
For Docker Compose, mount a `secrets:` entry at that path in a deployment
override rather than committing a secret file to this repository.

### Enterprise TLS inspection

The image preserves normal PyPI TLS verification. If your network intercepts
TLS, pass the organization-approved CA bundle as a BuildKit secret rather than
using `--trusted-host` or disabling certificate checks:

```bash
docker build --secret id=pip_ca,src=/path/to/organization-ca.pem \
  --file docker/backend.Dockerfile --tag trading-bot-service:local .
```

`pip_ca` is mounted only while Python dependencies are installed and is not
copied into the resulting image.

Non-loopback service bindings require a bearer token of at least 32 characters.
The checked-in Compose mapping is host-loopback only and sets
`BOT_SERVICE_API_TRUST_LOOPBACK_PROXY=1` for that specific deployment shape.
Do not publish the container on a LAN/public interface with that variable set;
configure direct TLS or a trusted TLS-terminating reverse proxy instead. See
[`docs/SERVICE_API.md`](../docs/SERVICE_API.md) for the required environment
variables.

## Runtime hardening

The checked-in Compose service runs as an unprivileged `tradingbot` user with a
read-only container filesystem, no Linux capabilities, and `no-new-privileges`.
Its only persistent writable location is the named
`trading-bot-service-data` volume at `/home/tradingbot/.trading-bot`; `/tmp` is
an in-memory temporary filesystem. Do not add broad host-path mounts or remove
these restrictions unless the deployment has a reviewed operational reason.

## What is included

- FastAPI service API
- SSE dashboard endpoint
- thin same-origin web dashboard at `/ui/`
- extracted service-owned backtest runner support

## What is not included

- PyQt desktop GUI
- desktop-hosted API mode
- mobile build tooling
