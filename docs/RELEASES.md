# Trading Bot Release Guide

This document keeps GitHub release workflow details out of the root README.

## Release workflows

This repo includes automated release workflows:

- `.github/workflows/release-windows.yml`
- `.github/workflows/release-linux-macos.yml`
- `.github/workflows/release-freebsd.yml`

When you push a tag that starts with `v` such as `v1.0.0`, GitHub Actions will build and publish platform assets:

- **Windows**: x64 and ARM64 assets for Python, the native C++ preview, the Rust workspace binary, and the Tauri desktop shell
- **Linux**: Python/native-C++ tarballs, Linux packages (`.deb`, `.rpm`), plus tarballs for the Rust workspace binary and the Tauri desktop shell on `x86_64` and `arm64`
- **macOS**: Python/native-C++ zip bundles plus zip bundles for the Rust workspace binary and the Tauri desktop shell on Intel and ARM64 runners
- **FreeBSD**: Python/C++ tarballs when a matching self-hosted runner is available
- **Other BSD variants / Solaris / illumos**: backend/service API support is currently manual and best-effort

The Python desktop release asset is built from the canonical product wrapper at `apps/desktop-pyqt/main.py`, while `Languages/Python/main.py` remains the compatibility launcher for source-based workflows.

Tauri is the only Rust desktop shell release target unless another Rust shell is explicitly promoted.

> FreeBSD release workflow depends on a matching self-hosted runner and is explicitly opt-in through workflow dispatch; tag releases skip it when no runner is configured. Other BSD-family systems and Solaris/illumos currently rely on manual validation against the service/backend path.

## Release preflight

Create a versioned QA note from `docs/release-qa/TEMPLATE.md` after committing
the tested product changes. The note must use the future tag as its filename,
record that tested product commit SHA, date, accountable operator, approved
outcome, a release-platform evidence scope, the positive GitHub Actions run ID
for that scope, and all required completed checks. Releases from v1.0.41 also
require the native signing and notarization review item. The cited matrix run must have
passed for the tested product commit. Use `full` for a standard release; it
requires every declared target. Use `hosted-only` only for an explicitly labeled
prerelease when self-hosted Windows evidence is intentionally unavailable; it
requires every GitHub-hosted target and must not be presented as full Windows 11
runtime coverage. Platform publishers always create or update a non-latest
prerelease candidate, regardless of scope. A `hosted-only` candidate must remain
a prerelease and can never become the repository's latest release. Only the
manually dispatched `Finalize Stable Release` workflow may promote a candidate;
it requires `full` evidence and the complete required Windows, Linux, and macOS
asset matrix before making the release stable/latest. Commit only this QA note,
then tag that metadata-only commit.
Tagged Windows, Linux, macOS, and FreeBSD release workflows reject publication
unless the note records the immediate parent revision, the tagged commit changes
only that versioned note, and the cited evidence artifact passes the selected
scope validation for that product commit. Starting with v1.0.41, publication also
fetches the QA note's candidate CI, CodeQL, and supply-chain workflow runs through
the GitHub Actions API and requires each run to be completed successfully in this
repository, from the expected workflow file, at that exact product source revision.
For a `full` stable/latest release, that tested source revision must also already
be contained in the repository's default branch and the triggering version tag
must be protected by an active GitHub tag ruleset. Hosted-only prereleases do not
make those stable-channel claims.

Validate the note locally before tagging. Replace the SHA with the tested
product commit, which will be the parent of the QA-note commit:

```bash
python tools/check_release_qa.py --tag v1.0.0 --note docs/release-qa/v1.0.0.md --require-platform-evidence-run
```

## Native trust gate (v1.0.41 and later)

Tagged Windows assets are Authenticode-signed with SHA-256 and an RFC 3161
timestamp. Tagged macOS assets are Developer ID-signed with Hardened Runtime and
a secure timestamp; the C++ application ticket is stapled, and all four macOS
asset families are accepted by Apple's notary service before publication.
Signing happens before digest manifests, SBOM generation, and provenance
attestation. The publication jobs re-download and validate hash-bound,
commit-bound `release-signing-*.json` evidence before creating the GitHub
Release.

Configure these repository or organization secrets before creating a release
tag:

- `WINDOWS_CODESIGN_PFX_B64`
- `WINDOWS_CODESIGN_PFX_PASSWORD`
- `MACOS_CODESIGN_P12_B64`
- `MACOS_CODESIGN_P12_PASSWORD`
- `MACOS_CODESIGN_IDENTITY`
- `APPLE_NOTARY_KEY_B64`
- `APPLE_NOTARY_KEY_ID`
- `APPLE_NOTARY_ISSUER_ID`

The workflows expose credentials only to their signing/notarization steps and
clean temporary certificate material. A missing, invalid, expired, or
non-matching credential fails a tagged build; it is never treated as an unsigned
fallback. Manual `workflow_dispatch` builds remain non-publishable and do not
claim native trust. The exact machine-readable contract is
`docs/release-signing-policy.json`; validate it with:

```bash
python tools/check_release_signing_policy.py --json
```

The gate starts at v1.0.41. It deliberately does not retroactively label or
require new signing evidence for the already-published v1.0.40 assets.

Run the local release smoke before creating a tag:

```bash
python tools/release_smoke.py
```

That command checks the declared Python/Node toolchain, verifies web/mobile
client lockfile metadata, compiles canonical entrypoints and tool scripts, runs
Ruff, checks dependency metadata and requirement shims, runs the configured mypy
targets, checks the service launcher healthcheck, runs the desktop/service
manual smoke, and runs the Python test suite.

The source compilation phase uses `tools/check_python_sources_compile.py` so the
preflight checks syntax in memory without writing `__pycache__` files.
The full Python test phase uses `Languages/Python/tools/run_python_tests.py` so
missing desktop/service/dev test dependencies fail with one setup hint before
the suite starts.

For a faster local pass when the full test suite already ran separately:

```bash
python tools/release_smoke.py --skip-full-tests --manual-smoke-mode fast
```

Use `--dry-run` to print the planned checks without executing them. If the
active shell `python` is not the declared release runtime, target the intended
interpreter explicitly:

```powershell
python tools/release_smoke.py --python-command "python" --skip-full-tests --manual-smoke-mode fast
```

## Release steps

1. Commit and push your tested source changes.
2. Create, validate, commit, and push the versioned QA note as a metadata-only
   commit.
3. Create and push a version tag on that QA-note commit:

```bash
git tag v1.0.0
git push origin v1.0.0
```

4. Open the Actions tab and wait for the tagged Windows and Linux/macOS release
   workflows to finish. They publish only a non-latest prerelease candidate.
5. For a standard release with `full` evidence, manually dispatch
   `Finalize Stable Release` from the same version tag. The protected production
   job revalidates exact-source CI/security/platform evidence, requires successful
   Windows and Linux/macOS packaging runs for the exact tagged build SHA, and
   refuses stable promotion until the entire required asset matrix is present, uniquely uploaded,
   non-empty, and backed by GitHub SHA-256 digest metadata. It also downloads the
   small per-target manifests, requires their source revision to equal the tagged
   build checkout, and matches every manifest-listed artifact size and SHA-256 to
   GitHub's release metadata. The QA gate separately proves that this tagged
   checkout differs from the exact tested product revision only by its versioned
   QA note. A `hosted-only`
   candidate is not eligible for this finalization and remains a prerelease.
6. Check the new GitHub Release assets, including:
   - `Trading-Bot-Python-*`
   - `Trading-Bot-C++-*`
   - `Trading-Bot-Rust-*`
   - Tauri Rust desktop assets
   - Linux and macOS artifacts from their respective tagged workflows
   - optional FreeBSD artifacts when the explicitly configured self-hosted
     FreeBSD release workflow is dispatched
   - Per-platform `release-manifest-*.json` SHA-256 manifests and
     `release-sbom-*.spdx.json` software bills of materials
   - For v1.0.41 and later, two Windows and four macOS
     `release-signing-*.json` native-trust evidence files
7. Verify the published release automatically:

```bash
python tools/check_release_assets.py v1.0.30
```

Add `--list-expected` if you only want to preview the expected asset matrix.
The verifier requires every asset published by the tagged Windows, Linux, and
macOS workflows, including ARM64 and the required Tauri desktop shell. It also
requires the per-build SHA-256 `release-manifest-*.json` and SPDX
`release-sbom-*.spdx.json` files, so a release cannot appear complete when its
integrity metadata is missing. It does not treat a smaller tier-one evidence
lab as a substitute for release assets.

All publisher jobs share a queued concurrency group for the version tag. This
serializes release mutation without dropping pending platform publishers. The
stable finalizer joins that same queue and must be dispatched only after the
candidate publisher workflows have succeeded. A publisher also checks the
existing release immediately before upload: it may create or update a prerelease
candidate, but it fails closed if the tag is already stable so a workflow rerun
cannot demote a finalized release.

## Integrity and provenance

Each Windows, Linux, macOS, and FreeBSD release job writes a SHA-256 digest
manifest, generates an SPDX SBOM, and creates GitHub Artifact Attestations for
both the built files and their SBOM. The provenance and SBOM attestations use
the GitHub Actions OIDC identity and are signed by Sigstore through
`actions/attest`.

Windows and Linux/macOS build jobs receive only read, OIDC, and attestation
permissions. Repository write permission is isolated to the final publication
job after artifacts have been built and attested.

After downloading a release asset, verify its provenance with GitHub CLI:

```bash
gh attestation verify PATH/TO/ASSET -R Yunushan/trading-bot
```

Verify the asset's SPDX SBOM attestation with:

```bash
gh attestation verify PATH/TO/ASSET -R Yunushan/trading-bot \
  --predicate-type https://spdx.dev/Document/v2.3
```
