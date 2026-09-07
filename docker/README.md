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

The checked-in Compose service runs as the image's unprivileged `65532` user with a
read-only container filesystem, no Linux capabilities, and `no-new-privileges`.
Its only persistent writable location is the named
`trading-bot-service-data` volume at `/home/nonroot/.trading-bot`; the service
loads a saved configuration from that volume when it exists and uses safe defaults
on its first run. `/tmp` is an in-memory temporary filesystem. Do not add broad
host-path mounts or remove these restrictions unless the deployment has a reviewed
operational reason.

The final virtual environment does not include pip. Dependencies are checked and
pip is removed before the environment is copied from the builder, so its vendored
build/install dependencies are not shipped with the service. Rebuild the image to
change dependencies; do not install packages into a running container. Container
audit findings are not waived because a newer top-level Python package exists:
vendored copies can have different versions.

The supply-chain workflow records the immutable ID emitted by
`docker build --iidfile`, then runs runtime checks and Trivy against that ID, not a mutable
tag. The policy requires schema-v2 image reports with OS and Python package
inventories (`--list-all-pkgs`), successful runtime evidence, and matching build,
runtime and scan image IDs. Empty reports, missing OS/Python inventories,
runtime versions absent from the scan, duplicate JSON fields, unreviewed
suppressed findings and scanner execution failures cannot pass the gate.
These checks bind local CI evidence; they do not replace signed release
provenance or establish that a deployed image is the same candidate.

## What is included

- FastAPI service API
- SSE dashboard endpoint
- thin same-origin web dashboard at `/ui/`
- extracted service-owned backtest runner support

## Production monitoring

The authenticated Prometheus endpoint is
`http://trading-bot-service:8000/api/v1/metrics/prometheus` from another Compose
service, or `http://127.0.0.1:8000/api/v1/metrics/prometheus` from the host. Use
an `Authorization: Bearer ...` header sourced from a Prometheus
`credentials_file`; do not place the token in `prometheus.yml` or the scrape URL.

Load `docker/monitoring/prometheus-alerts.json` through Prometheus `rule_files`.
It contains the repository-owned availability, read error-rate, p95 latency,
snapshot freshness, connector circuit, unresolved order-intent, and order
preflight alerts. The file is JSON, which Prometheus accepts as YAML, so the
repository can validate it deterministically with the Python standard library.
The monitoring service is intentionally not added to the default Compose stack:
production retention, alert routing, TLS, authentication, and storage must be
owned by the deployment environment rather than hidden in a development stack.

## What is not included

- PyQt desktop GUI
- desktop-hosted API mode
- mobile build tooling
