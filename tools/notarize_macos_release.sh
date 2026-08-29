#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Apple notarization must run on macOS." >&2
  exit 1
fi

phase="${1:-}"
target_id="${2:-}"
source_revision="${3:-}"
if [[ "${phase}" != "staple-app" && "${phase}" != "archives" ]]; then
  echo "Usage: tools/notarize_macos_release.sh <staple-app|archives> <macos-target-id> <40-char-commit>" >&2
  exit 1
fi
if [[ ! "${target_id}" =~ ^macos-[a-z0-9._-]+$ || ! "${source_revision}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Notarization target or source revision is invalid." >&2
  exit 1
fi
if [[ -z "${APPLE_NOTARY_KEY_B64:-}" || -z "${APPLE_NOTARY_KEY_ID:-}" || -z "${APPLE_NOTARY_ISSUER_ID:-}" ]]; then
  echo "Required Apple notarization credentials are unavailable. Tagged releases must fail closed." >&2
  exit 1
fi
if [[ "${#APPLE_NOTARY_KEY_B64}" -gt 200000 ]]; then
  echo "Apple notarization key payload exceeds the 200,000 character limit." >&2
  exit 1
fi
if [[ ! "${APPLE_NOTARY_KEY_ID}" =~ ^[A-Z0-9]{6,32}$ || \
      ! "${APPLE_NOTARY_ISSUER_ID}" =~ ^[0-9a-fA-F-]{16,64}$ ]]; then
  echo "Apple notarization key metadata is malformed." >&2
  exit 1
fi

umask 077
mkdir -p release
work_dir="$(mktemp -d "${RUNNER_TEMP:-/tmp}/trading-bot-notary.XXXXXX")"
api_key_path="${work_dir}/AuthKey_${APPLE_NOTARY_KEY_ID}.p8"
printf '%s' "${APPLE_NOTARY_KEY_B64}" | /usr/bin/base64 -D > "${api_key_path}"
if [[ ! -s "${api_key_path}" || "$(stat -f '%z' "${api_key_path}")" -gt 100000 ]]; then
  echo "Apple notarization private key must be between 1 byte and 100 KB." >&2
  rm -rf "${work_dir}"
  exit 1
fi

cleanup() {
  rm -rf "${work_dir}"
}
trap cleanup EXIT

notary_credentials=(
  --key "${api_key_path}"
  --key-id "${APPLE_NOTARY_KEY_ID}"
  --issuer "${APPLE_NOTARY_ISSUER_ID}"
)

validate_notary_result() {
  local receipt="$1"
  local log="$2"
  python -c '
import json, sys
receipt = json.load(open(sys.argv[1], encoding="utf-8"))
log = json.load(open(sys.argv[2], encoding="utf-8"))
if str(receipt.get("status", "")).lower() != "accepted":
    raise SystemExit("notary submission was not Accepted")
issues = log.get("issues")
if issues is None:
    issues = []
if not isinstance(issues, list):
    raise SystemExit("notary log issues must be an array or null")
errors = [item for item in issues if isinstance(item, dict) and str(item.get("severity", "")).lower() == "error"]
if errors:
    raise SystemExit(f"notary log contains {len(errors)} error(s)")
' "${receipt}" "${log}"
}

submit_archive() {
  local archive="$1"
  local receipt="$2"
  local log="$3"
  if [[ ! -f "${archive}" ]]; then
    echo "Notarization archive is missing: ${archive}" >&2
    exit 1
  fi
  xcrun notarytool submit "${archive}" \
    "${notary_credentials[@]}" \
    --wait \
    --output-format json > "${receipt}"
  submission_id="$(python -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8")).get("id", ""))' "${receipt}")"
  if [[ ! "${submission_id}" =~ ^[0-9a-fA-F-]{16,64}$ ]]; then
    echo "Apple notarytool returned an invalid submission id." >&2
    exit 1
  fi
  xcrun notarytool log "${submission_id}" \
    "${notary_credentials[@]}" \
    "${log}"
  validate_notary_result "${receipt}" "${log}"
}

app_bundle="${GITHUB_WORKSPACE:-$(pwd)}/release/Trading-Bot-C++/Trading-Bot-C++.app"
app_zip="release/.notary-cpp-${target_id}.zip"
app_receipt="release/.notary-cpp-${target_id}-receipt.json"
app_log="release/.notary-cpp-${target_id}-log.json"

if [[ "${phase}" == "staple-app" ]]; then
  if [[ ! -d "${app_bundle}" ]]; then
    echo "Signed C++ app bundle is missing: ${app_bundle}" >&2
    exit 1
  fi
  /usr/bin/codesign --verify --deep --strict --verbose=2 "${app_bundle}"
  rm -f "${app_zip}" "${app_receipt}" "${app_log}"
  /usr/bin/ditto -c -k --sequesterRsrc --keepParent "${app_bundle}" "${app_zip}"
  submit_archive "${app_zip}" "${app_receipt}" "${app_log}"
  xcrun stapler staple "${app_bundle}"
  xcrun stapler validate "${app_bundle}"
  echo "macOS app notarization and stapling passed for ${target_id}."
  exit 0
fi

for state_path in "${app_zip}" "${app_receipt}" "${app_log}"; do
  if [[ ! -f "${state_path}" ]]; then
    echo "Required pre-package app notarization state is missing: ${state_path}" >&2
    exit 1
  fi
done
xcrun stapler validate "${app_bundle}"

one_asset() {
  local pattern="$1"
  local matches=()
  for candidate in ${pattern}; do
    [[ -f "${candidate}" ]] || continue
    matches+=("${candidate}")
  done
  if [[ "${#matches[@]}" -ne 1 ]]; then
    echo "Expected exactly one release asset matching ${pattern}; found ${#matches[@]}." >&2
    exit 1
  fi
  printf '%s\n' "${matches[0]}"
}

python_asset="$(one_asset "release/Trading-Bot-Python-${target_id}-*.zip")"
rust_asset="$(one_asset "release/Trading-Bot-Rust-${target_id}-*.zip")"
tauri_asset="$(one_asset "release/Trading-Bot-Rust-tauri-${target_id}-*.zip")"
cpp_asset="$(one_asset "release/Trading-Bot-C++-${target_id}-*.zip")"

receipts=("${app_receipt}")
logs=("${app_log}")
notarized_archives=("${app_zip}")
for archive in "${python_asset}" "${rust_asset}" "${tauri_asset}"; do
  stem="$(basename "${archive}" .zip)"
  receipt="${work_dir}/${stem}-receipt.json"
  log="${work_dir}/${stem}-log.json"
  submit_archive "${archive}" "${receipt}" "${log}"
  receipts+=("${receipt}")
  logs+=("${log}")
  notarized_archives+=("${archive}")
done

python_bin="Languages/Python/dist/Trading-Bot-Python"
rust_bin="experiments/rust-shells/target/release/trading-bot-rust"
tauri_bin="experiments/rust-shells/target/release/trading-bot-tauri-desktop"
cpp_bin="${app_bundle}/Contents/MacOS/Trading-Bot-C++"
for path in "${python_bin}" "${rust_bin}" "${tauri_bin}"; do
  /usr/bin/codesign --verify --strict --verbose=2 "${path}"
done
/usr/bin/codesign --verify --deep --strict --verbose=2 "${app_bundle}"

evidence_path="release/release-signing-${target_id}.json"
writer_args=(
  tools/write_release_signing_evidence.py
  --platform macos
  --target-id "${target_id}"
  --source-revision "${source_revision}"
  --output "${evidence_path}"
  --cpp-app-stapled
)
for asset in "${python_asset}" "${rust_asset}" "${tauri_asset}" "${cpp_asset}"; do
  writer_args+=(--asset "${asset}")
done
for target in "${python_bin}" "${rust_bin}" "${tauri_bin}" "${cpp_bin}"; do
  writer_args+=(--signature-target "${target}")
done
for index in "${!receipts[@]}"; do
  writer_args+=(
    --notary-receipt "${receipts[$index]}"
    --notary-log "${logs[$index]}"
    --notarized-archive "${notarized_archives[$index]}"
  )
done
python "${writer_args[@]}"
python tools/check_release_signing_evidence.py \
  "${evidence_path}" \
  --asset-dir release \
  --require-current-revision

rm -f "${app_zip}" "${app_receipt}" "${app_log}"
echo "macOS archive notarization passed for ${target_id}."
