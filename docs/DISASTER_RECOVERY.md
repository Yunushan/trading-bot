# Disaster Recovery

Recovery requirements are defined in `docs/operational-readiness-policy.json`. Evidence is accepted for production promotion only when it is current, generated from a clean candidate commit, redacted, and reports no order submission attempt.

## Objectives

| Asset | RTO | RPO | Required evidence |
| --- | ---: | ---: | --- |
| Service configuration without credentials | 15 minutes | 24 hours | Config backup and restore drill |
| Service process and read-only API | 5 minutes | 5 minutes | Config restore plus process restart drill |
| Connector incidents and order audit trail | 30 minutes | 5 minutes | Incident/audit continuity drill |

Credentials are not part of JSON backup material. They must be restored through environment variables or the operating-system credential store. Never add credentials, tokens, signed requests, or raw exception payloads to recovery evidence.

## Config And Restart Drill

The deterministic drill uses the real `TradingBotService` persistence path. It saves a validated config, creates a backup, mutates the primary copy, restores the backup atomically, reloads a new service instance, then checks `/livez`, `/readyz`, and the authenticated runtime read route.

```powershell
python tools/run_operational_recovery_drill.py --json
```

To write candidate evidence from a clean commit:

```powershell
python tools/run_operational_recovery_drill.py --output service-config-backup-restore.json --json
```

The drill writes only inside a temporary directory except for an explicitly requested ignored evidence artifact. `read_only` means read-only with respect to trading and external exchange state; the drill necessarily writes temporary local backup files.

## Incident And Audit Continuity Drill

Run the deterministic continuity drill before production promotion:

```powershell
python tools/run_incident_audit_continuity_drill.py --json
python tools/run_incident_audit_continuity_drill.py --output incident-audit-continuity.json --json
```

The drill:

1. Rotates connector incident and order-audit JSONL files at the configured byte limit.
2. Restarts the service and confirms the newest complete records remain parseable.
3. Injects one malformed incident line and confirms valid records remain readable.
4. Confirms synthetic credentials are redacted from both audit streams.
5. Measures RTO and RPO and records an explicit zero-order-submission assertion.

The drill uses only a temporary directory unless `--output` requests an ignored
artifact under `artifacts/operational-readiness/`. Run it on the clean release
candidate host so filesystem and runtime behavior belong to that candidate.

## Promotion Decision

Run the strict gate only after downloading or generating all evidence for the same candidate commit:

```powershell
python tools/check_operational_readiness.py --require-evidence --require-current-commit --require-clean-source --json
```

Any missing, stale, dirty-source, mismatched-commit, unsafe, or failed artifact blocks production promotion.
