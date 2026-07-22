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

> FreeBSD release workflow depends on a matching self-hosted runner. Other BSD-family systems and Solaris/illumos currently rely on manual validation against the service/backend path.

## Release preflight

Create a versioned QA note from `docs/release-qa/TEMPLATE.md` after committing
the tested product changes. The note must use the future tag as its filename,
record that tested product commit SHA, date, accountable operator, approved
outcome, the positive GitHub Actions run ID for the full release-platform test
matrix, and all four completed checks. The cited matrix run must have passed for
the tested product commit. Commit only this QA note, then tag that metadata-only
commit. Tagged Windows, Linux, macOS, and FreeBSD release workflows reject
publication unless the note records the immediate parent revision, the tagged
commit changes only that versioned note, and the cited evidence artifact passes
the full matrix validation for that product commit.

Validate the note locally before tagging. Replace the SHA with the tested
product commit, which will be the parent of the QA-note commit:

```bash
python tools/check_release_qa.py --tag v1.0.0 --note docs/release-qa/v1.0.0.md --require-platform-evidence-run
```

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

4. Open the Actions tab and wait for release workflows to finish.
5. Check the new GitHub Release assets, including:
   - `Trading-Bot-Python-*`
   - `Trading-Bot-C++-*`
   - `Trading-Bot-Rust-*`
   - Tauri Rust desktop assets
   - Linux, macOS, and FreeBSD artifacts from their respective workflows
   - Per-platform `release-manifest-*.json` SHA-256 manifests and
     `release-sbom-*.spdx.json` software bills of materials
6. Verify the published release automatically:

```bash
python tools/check_release_assets.py v1.0.30
```

Add `--list-expected` if you only want to preview the expected asset matrix.
The verifier requires every asset published by the tagged Windows, Linux, and
macOS workflows, including ARM64 and the required Tauri desktop shell; it does
not treat a smaller tier-one evidence lab as a substitute for release assets.

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
