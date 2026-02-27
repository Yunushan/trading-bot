#!/usr/bin/env bash
set -euo pipefail

mkdir -p release
arch="$(uname -m)"
python_bin="Languages/Python/dist/Trading-Bot-Python"
release_version="$(python -c 'import os,re; tag=(os.environ.get("TB_RELEASE_TAG") or "").strip(); m=re.search(r"(\d+(?:[._-]\d+){1,3}(?:[-_.]?(?:a|b|rc|post|dev)\d+)?)", tag); print((m.group(1).replace("_",".").replace("-",".") if m else "0.0.0"))')"

if [[ ! -f "${python_bin}" ]]; then
  echo "Python binary not found at ${python_bin}" >&2
  exit 1
fi

if [[ "${TB_PLATFORM:-}" == "linux" ]]; then
  linux_python_asset="release/Trading-Bot-Python-linux-${arch}"
  cp "${python_bin}" "${linux_python_asset}"
  chmod +x "${linux_python_asset}"
  tar -C release -czf "release/Trading-Bot-Python-linux-${arch}-${release_version}.tar.gz" "Trading-Bot-Python-linux-${arch}"
  # Keep only the archive in release assets to avoid duplicate standalone + tarball uploads.
  rm -f "${linux_python_asset}"
  tar -C release -czf "release/Trading-Bot-C++-linux-${arch}-${release_version}.tar.gz" "Trading-Bot-C++"

  deb_arch="amd64"
  rpm_arch="x86_64"
  case "${arch}" in
    aarch64|arm64)
      deb_arch="arm64"
      rpm_arch="aarch64"
      ;;
    x86_64|amd64)
      deb_arch="amd64"
      rpm_arch="x86_64"
      ;;
    *)
      deb_arch="${arch}"
      rpm_arch="${arch}"
      ;;
  esac

  pkg_root="build/package/linux-python"
  rm -rf "${pkg_root}"
  mkdir -p \
    "${pkg_root}/usr/local/bin" \
    "${pkg_root}/usr/share/applications" \
    "${pkg_root}/usr/share/icons/hicolor/256x256/apps"

  install -m 0755 "${python_bin}" "${pkg_root}/usr/local/bin/trading-bot-python"
  if [[ -f "assets/crypto_forex_logo.png" ]]; then
    install -m 0644 "assets/crypto_forex_logo.png" "${pkg_root}/usr/share/icons/hicolor/256x256/apps/trading-bot.png"
  fi

  desktop_file="${pkg_root}/usr/share/applications/trading-bot.desktop"
  {
    printf '%s\n' '[Desktop Entry]'
    printf '%s\n' 'Name=Trading Bot'
    printf '%s\n' 'Comment=Binance Trading Bot desktop application'
    printf '%s\n' 'Exec=/usr/local/bin/trading-bot-python'
    printf '%s\n' 'Terminal=false'
    printf '%s\n' 'Type=Application'
    printf '%s\n' 'Categories=Finance;'
    printf '%s\n' 'Icon=trading-bot'
  } > "${desktop_file}"

  fpm -s dir -t deb \
    -n trading-bot-python \
    -v "${release_version}" \
    --iteration 1 \
    --architecture "${deb_arch}" \
    --license MIT \
    --maintainer "Trading Bot Contributors" \
    --description "Binance Trading Bot desktop application" \
    --url "https://github.com/${GITHUB_REPOSITORY}" \
    -C "${pkg_root}" \
    -p "release/trading-bot-python_VERSION_ARCH.TYPE" \
    .

  fpm -s dir -t rpm \
    -n trading-bot-python \
    -v "${release_version}" \
    --iteration 1 \
    --architecture "${rpm_arch}" \
    --license MIT \
    --maintainer "Trading Bot Contributors" \
    --description "Binance Trading Bot desktop application" \
    --url "https://github.com/${GITHUB_REPOSITORY}" \
    -C "${pkg_root}" \
    -p "release/trading-bot-python_VERSION_ARCH.TYPE" \
    .
else
  macos_asset_label="${TB_ASSET_LABEL:-}"
  if [[ -z "${macos_asset_label}" ]]; then
    macos_asset_label="${arch}"
  fi
  macos_asset_label="$(printf '%s' "${macos_asset_label}" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9._-]+/-/g; s/^-+//; s/-+$//')"
  if [[ -z "${macos_asset_label}" ]]; then
    macos_asset_label="${arch}"
  fi

  macos_asset_suffix="${macos_asset_label}"
  if [[ "${macos_asset_suffix}" != macos-* ]]; then
    macos_asset_suffix="macos-${macos_asset_suffix}"
  fi

  macos_python_asset="release/Trading-Bot-Python-${macos_asset_suffix}-${release_version}"
  cp "${python_bin}" "${macos_python_asset}"
  chmod +x "${macos_python_asset}"
  ditto -c -k --sequesterRsrc --keepParent \
    "${macos_python_asset}" \
    "release/Trading-Bot-Python-${macos_asset_suffix}-${release_version}.zip"
  rm -f "${macos_python_asset}"
  ditto -c -k --sequesterRsrc --keepParent \
    "release/Trading-Bot-C++" \
    "release/Trading-Bot-C++-${macos_asset_suffix}-${release_version}.zip"
fi
