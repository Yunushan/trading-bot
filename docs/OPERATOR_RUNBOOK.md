# Operator Runbook

This runbook is the short checklist for running the project safely.

## Before Live Trading

1. Run the app in `Demo/Testnet` first with the same symbols, intervals, indicators, leverage, margin mode, and position percent you plan to use live.
2. Confirm `Preflight` is `ok` in the desktop app or service dashboard.
3. Confirm the exchange connector is `Trading Supported`, not only selected in the UI.
4. Confirm order audit logging is writable.
5. Keep `live_allow_auto_bump_to_min_order` off unless you intentionally accept exchange-minimum auto-bumped orders.
6. Confirm stop-loss and take-profit behavior is deterministic strategy/runtime behavior, not LLM output.
7. Set `live_trading_max_session_orders` or `BOT_LIVE_MAX_SESSION_ORDERS` low for first live sessions.
8. Use small live size first and verify order, close, reduce-only, and emergency-close behavior.

## Order Intent Storage

The canonical Python runtime persists order intents beside the configured audit
log as `<audit-stem>.intents.json`, or uses `~/.trading-bot/order_intents.json`
when no audit path is configured. Keep this ledger on a local filesystem.

### Initialize or Upgrade Storage

Order submission never creates, repairs, resets or migrates a ledger. Missing,
malformed, legacy or differently bound storage fails closed and appears as
`order_intent_storage_unavailable` in connector/preflight health. This applies
to testnet as well as live execution, including protective close submissions.
Provision before enabling the runtime; do not discover a missing store during
an emergency exit. Maintain an independently tested exchange-side emergency
procedure while execution is stopped for maintenance.

Before any storage administration, stop every executor using the account and
back up the ledger and audit files together. Reconcile exchange open orders,
recent fills and positions through a trusted read-only exchange view. Confirm
which credentials and environment own the history. The acknowledgement below
is an operator prerequisite, not proof that the tool performed those checks.
The tool is offline and never sends orders or resolves an uncertain intent.

Use the exact configured `order_audit_log_path` (normally
`~/.trading-bot/order_audit.jsonl`) and provide the API key through an environment
variable populated by your credential manager. Do not put its value in command
arguments, shell history, documentation or support logs. No API secret is
needed. For an installed Python package:

```bash
trading-bot-order-store status --audit-log-path /state/order_audit.jsonl --mode Live --api-key-env BOT_BINANCE_API_KEY
```

For genuinely first-use storage, after confirming there is no prior history:

```bash
trading-bot-order-store initialize --audit-log-path /state/order_audit.jsonl --mode Live --api-key-env BOT_BINANCE_API_KEY --acknowledgement I_HAVE_STOPPED_EXECUTORS_AND_RECONCILED_EXCHANGE_STATE
```

For an existing version-one ledger, use `migrate` instead of `initialize` with
the same arguments. Migration writes a uniquely named `.v1-<id>.backup` beside
the ledger before publishing version two. It preserves every intent and state;
pending, submitted and unknown records remain blocked. Never delete the legacy
ledger to get around migration. Keep all old-version executors stopped: they
do not implement the new binding and provisioning protocol.

Initialization refuses existing storage and any nonempty active or numbered
rotated audit history. A failed first submission can itself produce an audit
record; do not erase it to make initialization pass. Investigate and establish
the exchange state before planning recovery. If established storage is lost,
restore the known matching backup with executors stopped, retain all audit
history, and reconcile the gap against the exchange before resuming. Restoring
a backup alone does not prove it contains the latest submitted intent.

Version two binds the ledger to the Binance environment and a fingerprint of
the API key, not to a verified exchange-account-wide identifier. Changing the
key or moving from testnet to live blocks the store. The command deliberately
has no reset or rebind option. Credential rotation of an established store
requires a reviewed, history-preserving account-identity/reconciliation
procedure; it is not yet automated. Do not initialize a new empty path to
silently discard history during rotation.

The same administration code is available without a console launcher:

```bash
python -m app.integrations.exchanges.binance.orders.order_intent_admin status --audit-log-path /state/order_audit.jsonl --mode Live --api-key-env BOT_BINANCE_API_KEY
```

This module is included in the Python package and service container. Run it
using the container's `/opt/venv/bin/python`, the same UID and persistent volume
as the stopped executor; do not initialize ephemeral replica-local history.
The read-only observer deployment does not submit orders and must not be
converted into an executor by provisioning a ledger. Source checkouts also
provide `python tools/manage_order_intent_store.py` with identical arguments.
Standalone frozen executables need an operator environment with the matching
Python package to administer their external state directory.

`--default-intent-path` is only for the runtime fallback where no audit path was
configured at all. It selects `~/.trading-bot/order_intents.json`; it is not the
normal audit-configured path and must not be used to bypass another store.
After administration, verify `status`, unresolved intents and preflight before
starting the single intended executor. Storage failure after a previous
successful status must still block a new submission.

### Transaction and Recovery Guarantees

Each read/check/write transaction uses a persistent sibling `.lock` file and
an OS-level exclusive lock with a bounded wait. Do not delete or replace the
lock file to clear a busy error: its existence does not mean a process owns
the lock, and removing it can defeat exclusion. Stop all old-version runtimes
before upgrading; older builds do not participate in this locking protocol.

Writes use unique same-directory temporary files, flush and synchronize their
contents, then publish by replacement. POSIX publication also synchronizes the
parent directory; Windows requests write-through replacement. A lock, read,
write or synchronization error blocks submission. Interrupted writes must not
be treated as evidence that an exchange rejected an order.

Pending, submitted and unknown intents continue to block new submissions until
exchange reconciliation succeeds. Never clear these records, invent an accepted
status or change the audit path to bypass the block. Preserve the ledger and
audit log together for investigation. An accepted response whose local update
fails is still ambiguous locally and must not be resubmitted with a new ID.

Both initial order acknowledgements and reconciliation queries require a
documented status, matching client order ID and symbol, and a valid exchange
order ID. Once observed, that exchange ID must remain consistent. Errors,
not-found responses, unknown statuses and mismatched identities keep the
unresolved block. An acknowledgement validation or storage safety failure
stops the fallback chain, including on testnet; it is not permission to POST
again through a different connector. Late confirmations cannot overwrite a
record that changed during validation or while a query was running.
Canceled and expired orders retain duplicate-ID protection because they may
have partial fills; only an explicit rejection with zero executed quantity
can mark an intent rejected. A resolved intent does not mean a position is
closed or that placing another order is safe: normal risk and freshness
checks still apply.

Futures market entries and closes request `RESULT` and submit only once. If the
response is missing, malformed, NEW, or PARTIALLY_FILLED, the runtime makes at
most three read-only queries for the persisted client order ID. It never uses
another connector or API prefix to POST that uncertain market order again.
An unresolved query keeps the durable submission barrier, including after a
restart. Older accepted market records without execution proof also require
reconciliation after upgrading.

Entry accounting and trade events use only validated `executedQty`, not sizing,
`origQty`, or a fill-summary fallback. A partial entry records the confirmed
quantity and pauses automatic trading while the remaining quantity is pending.
The intent ledger retains both submitted and executed quantities and the exact
order identity. Terminal partial fills remain recorded but are not reported as
fully completed orders. Unknown results never create a local position.

After an unresolved entry, reconcile that order's identity and cumulative fills,
refresh the exchange account/positions, and reconcile local allocations and fees
before explicitly resuming. An order-status query alone does not unpause the
strategy or rebuild its local position allocations. Do not clear the pause or
delete intent history to bypass this account-reconciliation step.

These locks serialize cooperating processes using the same local ledger. They
are not an account-wide executor lease across different ledger paths, hosts,
native runtimes or network filesystems. Do not run competing trading executors
for an account. Cross-host fencing and hardware/power-loss recovery still need
separate production validation; local process-kill tests do not certify them.

## LLM Usage

LLM assistance is advisory-only. It can explain risk, summarize state, or review signals, but it must not directly submit orders, override risk controls, or claim that a trade was executed.
The app blocks LLM responses that contain direct order-action output or risk-control override claims; treat a blocked response as a model/prompt issue, not as trading advice.

LLM requests, model discovery, local-model status, and Ollama pull/delete calls
reject HTTP redirects, including same-origin redirects. Configure the final
approved endpoint URL explicitly. Public-network opt-in does not authorize a
redirect target. A redirect is an error, not a successful response; its body
and destination are not included in diagnostics because they may contain
credentials or private context. Discovery retains catalog and user-selected
model IDs when an upstream endpoint redirects.

For local models, Ollama stores model files outside this repository, commonly:

- Windows: `%USERPROFILE%\.ollama\models`
- Linux/macOS: `~/.ollama/models`
- Custom Ollama cache: `OLLAMA_MODELS`

The project repository does not store downloaded model weights and Git should never track them.
Use the desktop LLM panel to check/download, cancel an in-progress download, or remove Ollama models after reading the shown size and storage-path warning.
The local-model status probe accepts loopback endpoints by default. Remote model status checks require an HTTPS URL and the explicit `Allow public network endpoint` setting; never place credentials or query-string tokens in the endpoint URL. Automatic Ollama start, download, and removal remain restricted to the local Ollama endpoint.

## Service API Safety

Use a bearer token for any exposed or write-capable API session. These flags are development-only escape hatches and are exposed in service API metadata when active:

- `BOT_SERVICE_API_ALLOW_UNAUTHENTICATED_WRITES`
- `BOT_SERVICE_CONFIG_ALLOW_INLINE_SECRETS`
- `BOT_SERVICE_CONFIG_ALLOW_UNSAFE_PATH`

If any unsafe write/config escape hatch is active, treat the service as unsafe
for normal operation.

`BOT_SERVICE_CONFIG_ALLOW_UNSAFE_PATH` affects only trusted callers running on
the service host. Remote API save/load requests always use the server-configured
path and reject request-selected paths, even when this flag is active. Remote
config and terminal routes also reject credential and audit/incident-log path
fields; provision those values on the host.

These values are operational exposure limits, not unsafe bypasses:

- `BOT_SERVICE_API_MAX_REQUEST_BYTES`
- `BOT_SERVICE_API_WRITE_RATE_LIMIT_PER_MINUTE`

Review request-size and write-rate-limit values before exposing the service
beyond loopback.

Scrape authenticated production metrics from
`/api/v1/metrics/prometheus`; keep the bearer token in the monitoring platform's
secret store or credential file. Load
`docker/monitoring/prometheus-alerts.json` as a Prometheus rule file and route
critical alerts to an actively monitored channel. Confirm that unavailable,
read-error-rate, stale-snapshot, metric-cardinality-overflow, open-circuit, and
unresolved-order-intent alerts reach the operator before declaring a deployment
ready. Use `X-Request-ID` from
service responses to correlate proxy and application incidents without placing
credentials or query values in logs or labels.

## Operational Readiness

The source of truth for SLOs, RTO/RPO targets, probe thresholds, and required
promotion evidence is `docs/operational-readiness-policy.json`. Run the local
regression checks before every release candidate:

```bash
python tools/check_operational_readiness.py --schema-only
python tools/run_service_sustained_probe.py --profile quick
python tools/run_operational_recovery_drill.py
python tools/run_incident_audit_continuity_drill.py
```

These checks are read-only with respect to trading and cannot submit orders.
The configuration recovery drill starts an authenticated read-only child from
a temporary configuration, verifies its API settings, forcibly exits that
process, observes the endpoint becoming unavailable, corrupts only the temporary
configuration, and atomically restores the exact backup. A distinct replacement
must become ready at the same loopback endpoint with matching editable settings,
read-only mode and working authentication. Child processes receive fresh tokens
and an isolated environment, not inherited trading credentials or proxy settings.
A successful drill requires both processes to be stopped before it returns;
cleanup failure makes the evidence fail.

The recovery interval runs from the forced-exit request through verified
replacement readiness, including exit, restoration and startup. Backup age is
measured at failure time. Evidence includes process identities, endpoint equality,
backup digests and an ordered monotonic timeline; cold-start-only or internally
inconsistent records are rejected. Host-specific LLM catalog locations and model
suggestions are not persisted settings and are excluded from API configuration
comparison; configured model and credential presence are still checked.
This is a local process/configuration drill, not proof of host power-loss,
multi-host failover, exchange reconciliation or deployed production availability.

The quick probe is not production evidence. A production promotion also
requires a passing 30-minute sustained probe against an external HTTPS service
running the exact candidate commit, a real rolling 30-day telemetry
window, config/restart recovery evidence, and incident/audit continuity
evidence from the same clean candidate commit. The raw telemetry export must
include a full `deployed_commit` SHA matching that candidate. Convert the raw
telemetry export
with `python tools/import_production_slo_evidence.py --input production-slo-telemetry.json --json`;
the importer writes no artifact unless counts, freshness, source binding, and
all SLO thresholds pass. Validate the complete evidence set with:

```bash
python tools/check_operational_readiness.py --require-evidence --require-current-commit --require-clean-source --json
```

For a reproducible hosted collection, dispatch the `Operational Readiness
Evidence` workflow from GitHub Actions. Before dispatching it, configure the
protected GitHub `production` environment variable
`PRODUCTION_SERVICE_API_ORIGIN` to the exact deployed HTTPS origin without a
path, for example `https://service.example.com`. The `service_base_url` input must exactly match
that environment variable; this prevents an operator from
accidentally sending `BOT_SERVICE_API_TOKEN` to an unapproved endpoint.
Configure the `BOT_SERVICE_API_TOKEN` secret in the same protected environment
when the service requires authentication. The workflow runs the sustained probe and
both recovery drills, uploads their JSON evidence even when a step fails, and
downloads and imports the required raw telemetry JSON from a prior Actions
artifact using `slo_telemetry_run_id`, `slo_telemetry_artifact`, and
`slo_telemetry_file`, and uploads the complete evidence directory even when a
later step fails. The telemetry run ID is required at dispatch time so an
incomplete collection fails before the 30-minute probe starts. Before the
download, the workflow also verifies that the referenced Actions run completed
successfully and that its `headSha` is the exact current promotion commit; an
artifact from another revision is rejected even if its JSON claims the right
commit. It still deliberately fails strict validation when the downloaded
telemetry or any other promotion evidence is missing; a failed collection must
not be treated as a production approval.

Missing evidence is a failed promotion gate, not an assumed pass. See
`docs/SERVICE_LEVEL_OBJECTIVES.md` and `docs/DISASTER_RECOVERY.md` for the
collection boundaries and operator drills.

The signed Rust native live-smoke job, release-platform evidence collector, and
strict Rust native promotion audit also target the protected `production`
environment. Configure any Binance testnet/mainnet credentials and the
reviewer rules there; do not store those credentials only as unprotected
repository secrets. Public market-data smoke does not require credentials and
remains separate from the signed job.

## Release Publication Protection

The binary release workflows keep platform builds separate from publication.
Each `publish-release` job targets the GitHub `production` environment and
shares a non-cancelling lock across the Windows, Linux/macOS, and FreeBSD
publishers for the same tag. Configure that environment in repository settings
before publishing a release:

- require at least one independent reviewer;
- restrict deployment branches/tags to version tags such as `v*`;
- configure an active repository tag ruleset for version tags such as `v*`, so
  `github.ref_protected` is true for stable publication;
- require platform publishers to finish their prerelease candidate uploads,
  then dispatch `Finalize Stable Release` from that same protected tag;
- keep release credentials and signing material in environment secrets, never
  in workflow inputs or committed files; and
- review the platform evidence and release manifest before approving the job.

An environment reference in YAML is not itself an approval policy; reviewers
and branch rules must be configured in GitHub repository settings.

## Release Smoke

Before packaging or tagging:

```bash
python tools/check_local_tool_versions.py --json
python tools/check_client_dependency_locks.py --json --strict
python tools/summarize_worktree_changes.py
python tools/audit_workspace_hygiene.py
python tools/audit_risky_patterns.py
python tools/verify_all.py --skip-slow
cd Languages/Python && python tools/run_python_tests.py
cd ../../apps/web-dashboard && npm test
cd ../mobile-client && npm test
```

On Windows machines with multiple Python installs, validate the intended
interpreter explicitly:

```powershell
python tools/check_local_tool_versions.py --json --skip-node --python-command "python"
```

For the service API:

```bash
python apps/service-api/main.py --healthcheck
python Languages/Python/tools/check_service_api_contracts.py
```

For a fresh contributor machine, preview the complete local setup plan first:

```bash
python tools/bootstrap_local_dev.py --dry-run
```

If the default `python` command is not the declared Python, target the install
interpreter explicitly:

```powershell
python tools/bootstrap_local_dev.py --python-command "python" --dry-run
```
