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
- A protected, published stable release tag. Dispatch
  `.github/workflows/publish-production-readonly-image.yml` on that tag. It
  builds and publishes one GHCR candidate, scans the pulled digest, generates
  an SPDX SBOM, and signs build, SBOM, and passing-scan attestations for that
  exact digest. Use the resulting `ghcr.io/<owner>/<repo>/service@sha256:...`
  reference. A locally built or merely revision-labeled image is insufficient.
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
  --image ghcr.io/<owner>/<repo>/service@sha256:<64-hex-digest> \
  --build-commit <40-hex-git-commit> \
  --output artifacts/deployment/production-readonly.json
python tools/check_production_deployment.py \
  --manifest artifacts/deployment/production-readonly.json \
  --require-rendered --json
python tools/verify_production_container_provenance.py \
  --image ghcr.io/<owner>/<repo>/service@sha256:<64-hex-digest> \
  --repository <owner>/<repo> \
  --commit <40-hex-git-commit> \
  --release-tag <protected-vX.Y.Z-tag> \
  --output artifacts/deployment/production-readonly-provenance.json
kubectl apply --dry-run=server -f artifacts/deployment/production-readonly.json
```

The provenance verifier needs GitHub CLI access to attestations through
`GH_TOKEN` and registry authentication for the OCI image. It verifies GitHub's
OIDC issuer, the repository and publishing workflow, the protected tag ref,
the exact source commit and image digest, hosted-runner identity, and one
publisher run shared by all three attestations. Each attestation must have a
verified timestamp within seven days of deployment. The scan result must be a pass under
`tools/check_container_vulnerability_policy.py`; the SBOM must include a
non-empty SPDX package inventory. Run this verifier for a rollback candidate
as well as a forward deployment. Do not trust the saved JSON summary alone;
it records a successful live verification for review.

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
the rendered commit, `read_only` is `true`, and
`trading_execution_supported` is `false`, and the versioned
`standalone-readonly-observer/v1` contract declares
`trading_observation_supported=false` with source `none`. Run the
`observer-smoke` profile against that HTTPS origin to verify service health.
Its passing result is not sustained operational or trading-monitor promotion
evidence. The existing quick and sustained profiles still require four fresh
trading snapshot samples and cannot pass on this unseeded topology; active
trading additionally requires evidence that those samples came from the owner.
Run `tools/run_service_capacity_probe.py --base-url https://<origin> --json`
with the token supplied only through `BOT_SERVICE_API_TOKEN` as a bounded
concurrency regression, then perform the deployment-specific load test used to
justify resource and HPA settings.

The repository also provides a protected manual workflow,
`.github/workflows/deploy-production-readonly.yml`. It accepts only a stable,
protected semantic-version tag, requires the exact tag commit in the image and
manifest, checks the image's `org.opencontainers.image.revision` label, and
verifies signed exact-digest build, SBOM, and scan evidence **before obtaining
Kubernetes credentials or applying anything**. It then performs a Kubernetes
server-side dry run, waits for rollout, and runs a post-deploy
HTTPS observer service-health smoke. The post-deploy probe compares every
observed `/readyz`
`build_commit` with the rendered deployment commit and requires the server's
`read_only` flag to be `true` and `trading_execution_supported` to be `false`;
the probe's own GET-only `read_only` field is not used as proof of server
configuration. The observer contract reports trading observations unavailable;
it does not establish exchange/account data freshness or active-trading
readiness. Load-balanced HTTPS requests sample responding replicas; verify
every pod's build and configuration separately through cluster evidence.
Its JSON evidence is written beneath
the repository's canonical, ignored `artifacts/operational-readiness/` path and
uploaded with the rendered manifest. Configure `PRODUCTION_KUBECONFIG_B64` and
`BOT_SERVICE_API_TOKEN` as protected `production` environment secrets and
`PRODUCTION_SERVICE_API_ORIGIN` as its exact HTTPS origin variable. The
publisher uses the release tag, run ID, and run attempt for a unique registry
tag; deployment accepts only the immutable digest, never that mutable tag.

Retain the GHCR image and its registry attestations for at least the agreed
release and rollback window (at least 90 days, matching the uploaded Trivy,
runtime, scan-predicate, and SBOM evidence artifact). Protect image deletion
and package administration separately from the deployment role. An expired
seven-day attestation requires a new publisher run, yielding a new candidate
digest that must pass all checks again; do not relabel an old digest or widen
the verifier's age policy. For a revoked or newly vulnerable digest, delete or
disable its attestations and registry access, stop promotion, and use only a
previous digest that still passes verification. Operator review of already
running replicas and the incident response remains necessary. GitHub's
attestation and registry retention policies are external production settings
and must be confirmed before an actual rollout.

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
