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
```

Promotion evidence gate:

```powershell
$env:TRADING_BOT_BUILD_COMMIT = (git rev-parse HEAD)
python tools/run_service_sustained_probe.py --profile sustained --base-url https://service.example.test --output service-api-sustained-runtime.json --json
python tools/check_operational_readiness.py --require-evidence --require-current-commit --require-clean-source --json
```

The sustained profile must run for at least 30 minutes and 18,000 requests.
It accepts only an external HTTPS deployment whose `/readyz` and API metadata
report the exact candidate commit through `TRADING_BOT_BUILD_COMMIT`. The local
FastAPI `TestClient` transport is deliberately limited to the quick,
non-promotional regression profile.
Even a passing artifact does not by itself prove the rolling 30-day SLO. Export
the production telemetry window to
`artifacts/operational-readiness/production-service-slo-window.json` with the
policy-required fields. `window_start` and `window_end` must cover at least 30
days, and every metric must meet its objective. The validator intentionally
rejects a shorter synthetic window.
