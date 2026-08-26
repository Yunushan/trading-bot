#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "macOS Developer ID signing must run on macOS." >&2
  exit 1
fi

target_id="${1:-}"
if [[ ! "${target_id}" =~ ^macos-[a-z0-9._-]+$ ]]; then
  echo "Usage: tools/sign_macos_release.sh <macos-target-id>" >&2
  exit 1
fi

if [[ -z "${MACOS_CODESIGN_P12_B64:-}" || -z "${MACOS_CODESIGN_P12_PASSWORD:-}" || -z "${MACOS_CODESIGN_IDENTITY:-}" ]]; then
  echo "Required macOS Developer ID signing credentials are unavailable. Tagged releases must fail closed." >&2
  exit 1
fi
if [[ ! "${MACOS_CODESIGN_IDENTITY}" =~ ^Developer\ ID\ Application:\ .+\ \([A-Z0-9]{10}\)$ ]]; then
  echo "MACOS_CODESIGN_IDENTITY must name an exact Developer ID Application identity and team id." >&2
  exit 1
fi
if [[ "${#MACOS_CODESIGN_P12_B64}" -gt 4000000 ]]; then
  echo "macOS signing certificate payload exceeds the 4,000,000 character limit." >&2
  exit 1
fi

umask 077
work_dir="$(mktemp -d "${RUNNER_TEMP:-/tmp}/trading-bot-macos-sign.XXXXXX")"
keychain_path="${work_dir}/release-signing.keychain-db"
p12_path="${work_dir}/developer-id.p12"
keychain_password="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
original_keychains=()
while IFS= read -r keychain; do
  [[ -n "${keychain}" ]] && original_keychains+=("${keychain}")
done < <(security list-keychains -d user | sed -E 's/^[[:space:]]*"//; s/"[[:space:]]*$//')

cleanup() {
  if [[ "${#original_keychains[@]}" -gt 0 ]]; then
    security list-keychains -d user -s "${original_keychains[@]}" >/dev/null 2>&1 || true
  fi
  security delete-keychain "${keychain_path}" >/dev/null 2>&1 || true
  rm -rf "${work_dir}"
}
trap cleanup EXIT

printf '%s' "${MACOS_CODESIGN_P12_B64}" | /usr/bin/base64 -D > "${p12_path}"
if [[ ! -s "${p12_path}" || "$(stat -f '%z' "${p12_path}")" -gt 2000000 ]]; then
  echo "macOS signing certificate must be between 1 byte and 2 MB." >&2
  exit 1
fi

security create-keychain -p "${keychain_password}" "${keychain_path}"
security set-keychain-settings -lut 21600 "${keychain_path}"
security unlock-keychain -p "${keychain_password}" "${keychain_path}"
security import "${p12_path}" \
  -k "${keychain_path}" \
  -P "${MACOS_CODESIGN_P12_PASSWORD}" \
  -T /usr/bin/codesign \
  -T /usr/bin/security >/dev/null
security set-key-partition-list \
  -S apple-tool:,apple:,codesign: \
  -s \
  -k "${keychain_password}" \
  "${keychain_path}" >/dev/null
security list-keychains -d user -s \
  "${keychain_path}" \
  "${original_keychains[@]}"
if ! security find-identity -v -p codesigning "${keychain_path}" | grep -Fq -- "${MACOS_CODESIGN_IDENTITY}"; then
  echo "The imported P12 does not contain the requested Developer ID Application identity." >&2
  exit 1
fi

python_bin="Languages/Python/dist/Trading-Bot-Python"
rust_bin="experiments/rust-shells/target/release/trading-bot-rust"
tauri_bin="experiments/rust-shells/target/release/trading-bot-tauri-desktop"
app_bundle="${GITHUB_WORKSPACE:-$(pwd)}/release/Trading-Bot-C++/Trading-Bot-C++.app"
cpp_bin="${app_bundle}/Contents/MacOS/Trading-Bot-C++"
for path in "${python_bin}" "${rust_bin}" "${tauri_bin}" "${app_bundle}" "${cpp_bin}"; do
  if [[ ! -e "${path}" ]]; then
    echo "Required macOS signing target is missing: ${path}" >&2
    exit 1
  fi
done

qt_prefix="$(qmake -query QT_INSTALL_PREFIX)"
macdeployqt="${qt_prefix}/bin/macdeployqt"
if [[ ! -x "${macdeployqt}" ]]; then
  echo "macdeployqt was not found at ${macdeployqt}." >&2
  exit 1
fi

# macdeployqt applies the QtWebEngineProcess entitlement file shipped inside
# QtWebEngineCore and signs nested Qt code before the outer app bundle.
"${macdeployqt}" "${app_bundle}" \
  "-libpath=${qt_prefix}/lib" \
  "-sign-for-notarization=${MACOS_CODESIGN_IDENTITY}" \
  -verbose=2

for path in "${python_bin}" "${rust_bin}" "${tauri_bin}"; do
  /usr/bin/codesign \
    --force \
    --options runtime \
    --timestamp \
    --keychain "${keychain_path}" \
    --sign "${MACOS_CODESIGN_IDENTITY}" \
    "${path}"
done

verify_signed_target() {
  local path="$1"
  local deep_flag="${2:-}"
  if [[ "${deep_flag}" == "deep" ]]; then
    /usr/bin/codesign --verify --deep --strict --verbose=2 "${path}"
  else
    /usr/bin/codesign --verify --strict --verbose=2 "${path}"
  fi
  details="$(/usr/bin/codesign --display --verbose=4 "${path}" 2>&1)"
  if ! grep -Eq '^flags=.*runtime' <<<"${details}"; then
    echo "Hardened Runtime is missing from the signature for ${path}." >&2
    exit 1
  fi
  if ! grep -Eq '^Timestamp=' <<<"${details}"; then
    echo "A secure signing timestamp is missing for ${path}." >&2
    exit 1
  fi
}

verify_signed_target "${python_bin}"
verify_signed_target "${rust_bin}"
verify_signed_target "${tauri_bin}"
verify_signed_target "${app_bundle}" deep

entitlements_path="${work_dir}/app-entitlements.plist"
/usr/bin/codesign --display --entitlements :- "${app_bundle}" > "${entitlements_path}" 2>/dev/null || true
if [[ -s "${entitlements_path}" ]] && \
   /usr/libexec/PlistBuddy -c 'Print :com.apple.security.get-task-allow' "${entitlements_path}" 2>/dev/null | grep -Fqx 'true'; then
  echo "The release app must not contain com.apple.security.get-task-allow=true." >&2
  exit 1
fi

echo "macOS Developer ID signing passed for ${target_id}."
