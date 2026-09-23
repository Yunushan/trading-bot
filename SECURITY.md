# Security Policy

This repository handles exchange and broker connectivity, API tokens, and automation flows that can affect live trading accounts. Treat security reports with operational discipline.

## Supported versions

| Version | Status |
| --- | --- |
| `main` branch | Active development, best-effort fixes |
| Latest GitHub release | Supported |
| Older releases | Best-effort only, upgrade may be required |

## Reporting a vulnerability

Do not open a public GitHub issue for security vulnerabilities.

Preferred reporting path:

1. Use GitHub private vulnerability reporting for this repository if it is available.
2. If that is not available, contact the maintainer privately through GitHub: `@Yunushan`

Include:

- affected area or file path
- impact summary
- reproduction steps or proof of concept
- version, branch, or commit
- whether real credentials or funds could be affected

## Sensitive data rules

- Never include real API keys, secrets, session tokens, account identifiers, or wallet addresses in a report.
- If you believe credentials were exposed, rotate them immediately before reporting.
- Sanitize logs, screenshots, and request payloads before sending them.

## In-scope examples

- authentication or authorization bypass in the service API
- credential leakage in logs, config output, or packaged artifacts
- arbitrary code execution, injection, or unsafe subprocess behavior
- unsafe default settings that can expose live trading credentials
- dependency or packaging issues that materially affect application integrity

## Out-of-scope examples

- feature requests
- support requests about exchange outages or rate limits
- issues caused only by unsupported or heavily modified local environments
- reports that require access to real funded accounts when a safe reproduction is possible without them

## Disclosure process

- Best-effort acknowledgment target: within 7 calendar days
- Best-effort status updates: as fixes are triaged and prepared
- Public disclosure should wait until a fix, mitigation, or clear operator guidance exists

Because this project is still marked beta, some reports may lead to hardening guidance or support-matrix adjustments rather than an immediate patch.

## Production threat boundaries (reviewed 2026-09-23)

- The current service bearer token is a shared operator credential. A token holder
  has the service capabilities enabled on that host; the token does not identify
  individual people or provide roles. Restrict write-capable service access to
  one trusted operator and execution host. Multi-user administration needs a
  separate identity, authorization, and audit design before it is supported.
- Generate an independent, random service token of at least 32 characters for
  each exposed service. Supply it from the host secret store or a protected
  token file; never put it in Git, URLs, browser storage, or logs. Rotate by
  replacing the host secret, restarting every service replica, and updating
  authorized clients. Revoke a compromised token by removing it from the host
  secret source and restarting all replicas; verify the old token is rejected.
  A shared token cannot revoke one user's access while retaining another's.
- Exchange and LLM credential references, provider bindings, destinations, and
  public-network consent belong to the service host. Remote config and terminal
  mutations cannot choose these values. LLM calls remain advisory; strategy,
  risk, and exchange execution stay in the deterministic runtime. Approve each
  external endpoint on the host, use HTTPS except for explicit loopback HTTP,
  and reject redirects. Network consent alone does not establish endpoint trust.
- Promote the read-only container by immutable registry digest after verifying
  the release source, publisher identity, build attestation, SBOM, and scan-pass
  attestation for that same digest. Treat a failed, expired, or revoked
  attestation as a stop to promotion. The read-only API flag does not stop a
  separate trading executor or provide account-wide execution ownership.
- On suspected credential exposure, stop affected promotion or API access,
  rotate the service token and any exposed upstream credentials at their
  issuers, preserve sanitized incident/audit evidence, and reconcile account
  orders and positions before restoring execution. Follow the operator runbook
  for kill, recovery, and rollback; never put raw credentials in an incident
  ticket or evidence artifact.

The pull-request `Secret Scan` check scans fetched Git history with Gitleaks
v8.30.1 and proves detection of a synthetic credential removed from the working
tree. It captures and suppresses scanner findings in public CI logs. Eleven
reviewed historical false positives have exact fingerprint exceptions in
`.gitleaksignore`; new commits and changed lines remain in scope. This scanner
cannot prove that a credential was never exposed outside repository history.

The 2026-09-23 RustSec review found no reported vulnerabilities. Updating
`chacha20` from yanked 0.10.1 to 0.10.2 removed one of seven exceptions. Six
unmaintained transitive exceptions remain in `tools/rust-audit-policy.json`, all
expiring **2026-10-10**: `RUSTSEC-2024-0370` for `proc-macro-error` through
Tauri's Linux GTK3 macros, and `RUSTSEC-2025-0075`, `-0080`, `-0081`, `-0098`,
`-0100` for the UNIC crates through Tauri Utils 2.9.3 and `urlpattern` 0.3.0.
The currently released Tauri Utils line still requires that `urlpattern` path;
the published `proc-macro-error` advisory has no patched version. Remove these
exceptions when a verified upstream or vendor migration is available. They
must not be silently extended past expiry. A named owner for each remaining
exception and candidate-build dependency evidence still need approval before
production security sign-off.
