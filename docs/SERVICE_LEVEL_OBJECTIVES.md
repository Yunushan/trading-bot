# Service Level Objectives

The machine-readable source of truth is `docs/operational-readiness-policy.json`. These objectives apply to a production deployment of the Python-owned service API. A local quick probe is a regression gate, not proof that a rolling production objective has been met.

## Objectives

| Objective | Target | Window | Evidence |
| --- | ---: | --- | --- |
| Successful read requests | >= 99.9% | Rolling 30 days | `production-service-slo-window.json` |
| Failed read requests | <= 0.1% | Rolling 30 days | `production-service-slo-window.json` |
| Read latency p95 | <= 500 ms | Rolling 30 days | `production-service-slo-window.json` |
| Operational snapshot age | <= 120 seconds | Continuous while the runtime is active | `production-service-slo-window.json` |

The availability and latency targets cover `/livez`, `/readyz`, and authenticated read-only API routes. They do not authorize order submission and do not convert the LLM advisory boundary into an execution boundary.

The service exports the raw counters, duration histogram, runtime state, and
snapshot-age gauges needed to calculate these objectives at authenticated
`/api/v1/metrics/prometheus`. The checked-in alert rules at
`docker/monitoring/prometheus-alerts.json` apply the 0.1% error-rate, 500 ms p95,
and 120-second freshness thresholds. Alerts are an operational response surface;
they do not replace the required rolling 30-day evidence artifact.

## Error Budget

The monthly error budget is 0.1% of eligible read requests. Exhausting the budget blocks production promotion and non-essential releases until the responsible failure mode is corrected and a new current-commit evidence set passes.

Excluded from the SLO denominator:

- Requests rejected by documented authentication policy.
- Explicit operator cancellation.
- Exchange-originated failures reported separately as connector health failures.
- Planned maintenance announced before the measurement window.

Do not exclude application crashes, stale operational data, dependency failures, or malformed successful responses.

## Verification

Fast local regression gate:

```powershell
python tools/run_service_sustained_probe.py --profile quick --json
python tools/run_service_capacity_probe.py --json
```

The capacity command starts the canonical service as a separate read-only child
process and sends 600 concurrent, bounded GET requests across health, runtime,
status, and metrics routes. It enforces zero errors, a 500 ms local p95 ceiling,
and at least 10 requests/second. CI repeats the same shape against the hardened
container image. This is a deterministic regression floor, not production
capacity or promotion evidence; size real resource limits and HPA targets from
load tests in the actual cluster and retain those results with the deployment.

For a deployed HTTPS target, provide its bearer token through an environment
variable and never in the URL or command line:

```powershell
$env:BOT_SERVICE_API_TOKEN = '<secret-manager-value>'
python tools/run_service_capacity_probe.py --base-url https://service.example.test --json
```

Promotion evidence gate:

```powershell
$env:TRADING_BOT_BUILD_COMMIT = (git rev-parse HEAD)
python tools/run_service_sustained_probe.py --profile sustained --base-url https://service.example.test --output service-api-sustained-runtime.json --json
python tools/import_production_slo_evidence.py --input production-slo-telemetry.json --json
python tools/check_operational_readiness.py --require-evidence --require-current-commit --require-clean-source --json
```

The sustained profile must run for at least 30 minutes and 18,000 requests.
It accepts only an external HTTPS deployment whose `/readyz` and API metadata
report the exact candidate commit through `TRADING_BOT_BUILD_COMMIT`. The local
FastAPI `TestClient` transport is deliberately limited to the quick,
non-promotional regression profile.
Every successful operational-preflight request must also contain a valid,
timezone-aware `generated_at` timestamp. The probe records both expected and
valid sample counts; missing or malformed samples fail the freshness gate
instead of being interpreted as zero age.
Even a passing sustained-probe artifact does not by itself prove the rolling
30-day SLO. Export raw production telemetry using the exact schema in
`apps/service-api/contracts/production-slo-telemetry.sample.json`, then run the
importer from a clean candidate checkout. The sample values are illustrative
and are not valid production evidence.

The importer derives the success and failure ratios from the integer request
counts, verifies that the counts reconcile, requires the raw export's
`deployed_commit` to be the full candidate commit SHA, binds the evidence to the
raw input with SHA-256, enforces the current telemetry window and policy
thresholds, and writes the canonical artifact only after every check passes.
Keep the raw
telemetry export in the controlled operational evidence store; do not commit it
or place credentials, query strings, or tokens in `telemetry_source`.

For Prometheus, derive the raw telemetry counts from
`trading_bot_service_http_requests_total` using eligible `GET`/`HEAD` routes,
derive p95 from
`trading_bot_service_http_request_duration_seconds_bucket`, and derive snapshot
age from the maximum `trading_bot_service_operational_snapshot_age_seconds`
series while `trading_bot_service_runtime_active == 1`. Preserve the external
monitoring system's immutable query/export record with the raw evidence.

The local recovery drill writes synthetic exchange and LLM credentials through
the normal persistence boundary, verifies that their literal values are absent
from the backup, removes any corresponding OS credential-store entries, and
then starts the canonical `apps/service-api/main.py` launcher as a separate
loopback child process. Only `/livez`, `/readyz`, and authenticated
`/api/v1/runtime` GET requests are used; the drill never calls an order route.
