# Trading Bot Release Guide

This document keeps GitHub release workflow details out of the root README.

## Release workflows

This repo includes automated release workflows:

- `.github/workflows/release-windows.yml`
- `.github/workflows/release-linux-macos.yml`
- `.github/workflows/release-freebsd.yml`

When you push a tag that starts with `v` such as `v1.0.0`, GitHub Actions will build and publish platform assets:

- **Windows**: x64 and ARM64 assets for Python, C++, the Rust workspace binary, and every Rust desktop framework shell
- **Linux**: Python/C++ tarballs, Linux packages (`.deb`, `.rpm`), plus tarballs for the Rust workspace binary and every Rust desktop framework shell on `x86_64` and `arm64`
- **macOS**: Python/C++ zip bundles plus zip bundles for the Rust workspace binary and every Rust desktop framework shell on Intel and ARM64 runners
- **FreeBSD**: Python/C++ tarballs when a matching self-hosted runner is available
- **Other BSD variants / Solaris / illumos**: backend/service API support is currently manual and best-effort

Rust framework shell assets are best-effort. If one optional framework fails to compile on a runner, the rest of the release can still publish.

> FreeBSD release workflow depends on a matching self-hosted runner. Other BSD-family systems and Solaris/illumos currently rely on manual validation against the service/backend path.

## Release steps

1. Commit and push your source changes.
2. Create and push a version tag:

```bash
git tag v1.0.0
git push origin v1.0.0
```

3. Open the Actions tab and wait for release workflows to finish.
4. Check the new GitHub Release assets, including:
   - `Trading-Bot-Python-*`
   - `Trading-Bot-C++-*`
   - `Trading-Bot-Rust-*`
   - framework-specific Rust desktop assets
   - Linux, macOS, and FreeBSD artifacts from their respective workflows
5. Verify the published release automatically:

```bash
python tools/check_release_assets.py v1.0.30
```

Add `--list-expected` if you only want to preview the expected asset matrix.
