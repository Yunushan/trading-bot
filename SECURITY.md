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

