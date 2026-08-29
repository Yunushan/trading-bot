# Production read-only Kubernetes deployment

This provider-neutral baseline runs the standalone Service API as a stateless,
read-only observer. It gives the health, metadata, dashboard, metrics, and other
safe GET surfaces multiple replicas. It does not provide high availability for
trading execution: mutation methods are rejected, the local lifecycle executor
is disabled, every replica has independent ephemeral state, and no replica may
submit or manage exchange orders. Keep the desktop-owned trading runtime or a
future reviewed single-writer executor outside this deployment.

## External prerequisites

Before applying the stack, provide all of the following:

- A Kubernetes cluster with at least three schedulable worker nodes. Zone labels
  are recommended. Required host anti-affinity intentionally keeps replicas off
  the same node.
- Metrics Server (or an equivalent resource-metrics API) for the HPA.
- An image built from the exact candidate commit, pushed to an approved registry,
  scanned under the repository container policy, and referenced by immutable
  `sha256` digest.
- A Secret named `trading-bot-service-api` in the `trading-bot-readonly`
  namespace with a `token` value of at least 32 characters. Never commit it.
  The pod's explicit group-read opt-in accepts the projected `0440` file only
  because its group id must match the process `fsGroup` (`65532`); group write,
  group execute, and all other-user permissions remain rejected.
- A TLS-terminating ingress or gateway outside this manifest. The Service is
  deliberately `ClusterIP`; there is no plaintext public `Ingress` or
  `LoadBalancer` fallback.
- A NetworkPolicy-capable CNI. Label both the ingress namespace with
  `trading-bot-ingress-access=true` and only the ingress pods that should reach
  this service with `trading-bot-ingress-client=true`. Monitoring access uses
  the corresponding `trading-bot-monitoring-access=true` namespace and
  `trading-bot-monitoring-client=true` pod labels.

The egress policy is empty, so these API pods cannot reach exchanges, LLM
providers, metadata endpoints, or the public internet. That is intentional for
this observer-only topology.

## Render and validate

The checked-in JSON is a safe template. Its image points at the reserved
`.invalid` domain and its build commit is all zeroes, so it cannot accidentally
be treated as a release deployment. Render both values together:

```bash
python tools/render_production_deployment.py \
  --image registry.example.com/trading-bot/service@sha256:<64-hex-digest> \
  --build-commit <40-hex-git-commit> \
  --output artifacts/deployment/production-readonly.json
python tools/check_production_deployment.py \
  --manifest artifacts/deployment/production-readonly.json \
  --require-rendered --json
kubectl apply --dry-run=server -f artifacts/deployment/production-readonly.json
```

Create the token through your secret manager, External Secrets controller, or a
non-logged stdin flow. Confirm the resulting `token` key is at least 32
characters and is readable by uid/gid `65532`; do not place the value in a
manifest, shell history, CI output, or command-line argument.

After the server-side dry run and policy checks pass:

```bash
kubectl apply -f artifacts/deployment/production-readonly.json
kubectl -n trading-bot-readonly rollout status deployment/trading-bot-readonly-api --timeout=10m
kubectl -n trading-bot-readonly get deployment,pods,service,pdb,hpa,networkpolicy
```

Verify `/readyz` through the HTTPS origin and confirm its `build_commit` equals
the rendered commit and `read_only` is `true`. Then run the repository's
sustained deployed-service probe against that HTTPS origin before promotion.
Run `tools/run_service_capacity_probe.py --base-url https://<origin> --json`
with the token supplied only through `BOT_SERVICE_API_TOKEN` as a bounded
concurrency regression, then perform the deployment-specific load test used to
justify resource and HPA settings.

The repository also provides a protected manual workflow,
`.github/workflows/deploy-production-readonly.yml`. It accepts only a stable,
protected semantic-version tag, requires the exact tag commit in the image and
manifest, checks the image's `org.opencontainers.image.revision` label, performs
a Kubernetes server-side dry run, waits for rollout, and runs a post-deploy
HTTPS identity smoke. Configure `PRODUCTION_KUBECONFIG_B64` and
`BOT_SERVICE_API_TOKEN` as protected `production` environment secrets and
`PRODUCTION_SERVICE_API_ORIGIN` as its exact HTTPS origin variable. The image
publisher must pass the source commit when building, for example:

```bash
docker build --build-arg BUILD_COMMIT=<40-hex-git-commit> \
  --file docker/backend.Dockerfile \
  --tag registry.example.com/trading-bot/service:<tag> .
```

## Rollback and failure behavior

The Deployment retains ten ReplicaSet revisions and updates with
`maxUnavailable: 0`. Inspect and roll back the whole pod template—image digest,
commit identity, and safety flags together—with:

```bash
kubectl -n trading-bot-readonly rollout history deployment/trading-bot-readonly-api
kubectl -n trading-bot-readonly rollout undo deployment/trading-bot-readonly-api
kubectl -n trading-bot-readonly rollout status deployment/trading-bot-readonly-api --timeout=10m
```

After any rollout undo, re-check `/readyz`; the reported commit must match the
digest revision you intended to restore. A PDB keeps two of the three baseline
replicas available during voluntary disruption. Startup, readiness, and
liveness probes remove unhealthy pods from service and restart dead processes.

## Monitoring

The API exposes authenticated Prometheus metrics at
`/api/v1/metrics/prometheus`. Mount the same token into the monitoring system
from its secret manager; never copy it into scrape configuration. Load
`docker/monitoring/prometheus-alerts.json`, retain telemetry outside the pods,
and use `tools/import_production_slo_evidence.py` only with a real rolling
30-day production window. HPA resource thresholds are safety bounds, not
capacity proof; establish requests/limits with deployment-specific load tests.
