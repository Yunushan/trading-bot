# Dependency Reproducibility

This repository declares local runtime versions at the root:

- `.python-version`: Python used by CI and local service/Desktop development.
- `.node-version`: Node.js used by web and mobile client tests.

Run this preflight before packaging or reviewing dependency changes:

```bash
python tools/check_local_tool_versions.py --json
python tools/check_client_dependency_locks.py --json --strict
python tools/verify_all.py --skip-slow
```

Run the Python dependency vulnerability audit with the explicit security extra:

```bash
python -m venv .venv-security
# POSIX
.venv-security/bin/python -m pip install --upgrade pip==26.2.1 setuptools==83.0.0 wheel
.venv-security/bin/python -m pip install -e "Languages/Python[service,security]"
.venv-security/bin/python tools/run_python_security_audit.py --skip-editable --progress-spinner=off
# Windows: replace `.venv-security/bin/python` with `.venv-security\\Scripts\\python.exe`.
```

The launcher uses the operating system certificate store through `truststore`.
It does not disable TLS verification; this is important on Windows networks that
use a locally trusted inspection certificate.

The CI audit runs in an isolated environment so globally installed packages on a
runner cannot create unrelated findings. The `service` extra is installed before
the audit, so the shipped service dependency surface remains covered.

The scheduled supply-chain workflow also checks the Rust lockfile with pinned
`cargo-audit` 0.22.2. To run that check locally after Cargo can reach crates.io:

```bash
cargo install cargo-audit --version 0.22.2 --locked
cd experiments/rust-shells
audit_db="$(mktemp -d "${TMPDIR:-/tmp}/trading-bot-rustsec-db.XXXXXX")"
trap 'rm -rf "$audit_db"' EXIT
cargo audit --db "$audit_db" --file Cargo.lock
```

On Windows PowerShell, use a unique temporary database and remove it after the
audit:

```powershell
$auditDb = Join-Path $env:TEMP ("trading-bot-rustsec-db-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $auditDb | Out-Null
try {
    cargo audit --db $auditDb --file Cargo.lock
}
finally {
    Remove-Item -LiteralPath $auditDb -Recurse -Force -ErrorAction SilentlyContinue
}
```

The workflow uses a fresh temporary advisory database for every run. This
avoids stale or corrupted user-level RustSec caches while retaining the full
audit result; the database is removed when the step exits.

The Rust audit step also writes the machine-readable result to a temporary JSON
file and uploads it as `rust-dependency-audit-report`, including when the audit
fails. This makes the exact advisory set reviewable from the workflow run
instead of relying on truncated console output. The report is evidence only;
the command's exit status remains authoritative.

`cargo audit` can exit successfully while reporting informational warnings. The
current Tauri Linux dependency path may therefore still show upstream GTK/glib
unmaintained or unsound warnings even when no known vulnerable dependency is
reported. Those warnings are not hidden with an advisory ignore list. They must
be reviewed after every Tauri or GTK dependency update, and they remain a
release risk until the upstream dependency path has a compatible remediation.
Treat a clean audit report as necessary, not sufficient, for production
promotion.

The Tauri macOS dependency path temporarily patches `plist` to a reviewed,
immutable upstream commit. This is required because the published `plist` 1.8.0
release pins a vulnerable `quick-xml` range; remove the patch when a released
plist version contains the same `quick-xml >=0.41.0` remediation.

The supply-chain workflow also builds `docker/backend.Dockerfile` and fails on
known high- or critical-severity OS or Python-library vulnerabilities in the
resulting image. Run the same build locally when Docker Desktop is running:

```bash
docker build --pull --file docker/backend.Dockerfile --tag trading-bot-service:local .
```

The CI scan is intentionally pinned to an immutable Trivy Action commit and
does not suppress unfixed high- or critical-severity findings. Resolve those in
the base image or declared Python dependencies before treating a release image
as production-ready. The report summarizer is fail-closed as well: it rejects
malformed result/vulnerability records, missing vulnerability IDs or severities,
and severities outside Trivy's known set instead of silently under-counting a
report. A clean Trivy result may use `Vulnerabilities: null` and remains valid.

Every third-party action in the CI and release workflows is pinned to an
immutable commit. Dependabot proposes reviewed upgrades rather than allowing a
mutable action tag to change behavior during a security scan or release.

The service Dockerfile pins both its Chainguard Python builder and distroless
Wolfi runtime images by OCI digest. The Docker Dependabot entry proposes
deliberate base-image refreshes; do not replace either digest with a mutable
tag. Dependencies are installed in the `-dev` builder, while the production
stage copies only the virtual environment into the unprivileged runtime image.
This removes package-manager and compiler tooling from the release image. The
image bootstrap also pins `pip` 26.2.1, `setuptools` 84.0.0, and `msgpack` 1.2.1
rather than upgrading to unreviewed latest versions during a container build.

For a hard local setup gate, use:

```bash
python tools/check_local_tool_versions.py --strict
```

When more than one Python version is installed, point the checker at the same
interpreter you will use for the editable install:

```powershell
python tools/check_local_tool_versions.py --strict --skip-node --python-command "python"
```

For a complete contributor environment after the declared runtimes are
installed, preview and then run:

```bash
python tools/bootstrap_local_dev.py --dry-run
python tools/bootstrap_local_dev.py
```

When the active shell `python` is not the declared Python, pass the target
interpreter to the bootstrap. On Windows, this keeps installs in Python 3.14
even if the script itself was launched by another Python:

```powershell
python tools/bootstrap_local_dev.py --python-command "python" --dry-run
python tools/bootstrap_local_dev.py --python-command "python"
```

When a runtime is missing or mismatched, the checker prints a `fix:` line and
emits machine-readable `remediation` fields in JSON output. Use those steps
before debugging package or test failures. A Python mismatch usually means the
editable development install was created under the wrong interpreter; recreate
it with the Python version in `.python-version`. A Node mismatch means web and
mobile client tests are not running under the same major Node release as CI.

Use `--strict` in CI or release scripts. The Python CI job checks Python only,
and the Node CI jobs check Node after `actions/setup-node` has selected the
declared version.

The web dashboard has no external runtime dependencies today, but still declares
`packageManager` and Node `engines` so client tests run on the same major Node
release everywhere. The Expo mobile client also declares the same package manager
and Node engine. When mobile dependencies are installed for development, commit a
real `package-lock.json` generated by the same npm major before changing package
versions.

The mobile production audit has one explicit, time-boxed exception for the current
Expo/Metro build graph. `apps/mobile-client/package.json` pins `nanoid` to 3.3.18,
which is above its published security floor. Expo 57 currently resolves
`image-size` through Metro, and the registry still reports the two ICNS/JXL/HEIF
infinite-loop advisories (`GHSA-w3rx-r6r6-pgpr` and `GHSA-5p2g-fcmc-qvqq`) for the
latest 2.0.2 release. The only npm remediation currently offered is a breaking
Expo/React Native downgrade, so this build-time-only path is recorded in
`tools/node-audit-policy.json` until 2026-09-30. The policy checker is fail-closed:
new high/critical findings, critical findings inherited through the Metro chain,
unknown or malformed severity records, stale exceptions, changed advisory IDs, and
expired exceptions fail CI. Remove the exception as soon as Expo or `image-size`
provides a supported fixed path.

The workflow evaluates the JSON audit report with
`tools/check_node_audit_policy.cjs` after `npm audit`; the policy evaluation remains
authoritative even when npm exits non-zero for the documented, exact exception.

`tools/verify_all.py` also runs the worktree summary and workspace-hygiene
advisory checks so dependency drift, missing client lockfiles, generated
artifacts, and missing local tooling are visible in one report.

For the broader release-readiness checklist, including native C++/Rust gates,
backtest optimizer guardrails, connector evidence, platform promotion, and
manual product QA, see `docs/QUALITY_AND_EVIDENCE_GATES.md`.

Runtime version mismatches are reported as a blocking advisory in
`tools/verify_all.py`: the tool still prints the downstream check results, but
the overall report does not pass until Python and Node match the declared
runtime files.

The verification wrapper also disables common Python tool caches for its child
processes, so running the local gate should not leave `.ruff_cache`,
`.mypy_cache`, or `__pycache__` noise behind. Source compilation checks use
`tools/check_python_sources_compile.py`, which compiles files in memory instead
of using `compileall`.
