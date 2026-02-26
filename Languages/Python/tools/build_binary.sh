#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: build_binary.sh [options]

Options:
  --python <exe>                  Python executable (default: python3)
  --name <name>                   Output binary name (default: Trading-Bot-Python)
  --icon <path>                   Icon file path (optional)
  --console                       Build console app (default: windowed)
  --skip-dependency-install       Skip pip install steps
  --release-tag <tag>             Release tag for embedded metadata
  -h, --help                      Show this help
EOF
}

PYTHON_BIN="${PYTHON_BIN:-python3}"
NAME="${NAME:-Trading-Bot-Python}"
ICON_PATH="${ICON_PATH:-}"
CONSOLE=0
SKIP_DEPENDENCY_INSTALL=0
RELEASE_TAG="${RELEASE_TAG:-${TB_RELEASE_TAG:-}}"
UNAME_S="$(uname -s)"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --python)
      PYTHON_BIN="$2"
      shift 2
      ;;
    --name)
      NAME="$2"
      shift 2
      ;;
    --icon)
      ICON_PATH="$2"
      shift 2
      ;;
    --console)
      CONSOLE=1
      shift
      ;;
    --skip-dependency-install)
      SKIP_DEPENDENCY_INSTALL=1
      shift
      ;;
    --release-tag)
      RELEASE_TAG="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${PYTHON_ROOT}/../.." && pwd)"

release_info_path=""

cleanup() {
  if [[ -n "${release_info_path}" && -f "${release_info_path}" ]]; then
    rm -f "${release_info_path}"
  fi
  popd >/dev/null || true
}
trap cleanup EXIT

pushd "${PYTHON_ROOT}" >/dev/null

if [[ "${SKIP_DEPENDENCY_INSTALL}" -eq 0 ]]; then
  if [[ ! -f "requirements.txt" ]]; then
    echo "requirements.txt not found in ${PYTHON_ROOT}" >&2
    exit 1
  fi
  "${PYTHON_BIN}" -m pip install --upgrade pip
  "${PYTHON_BIN}" -m pip install --upgrade pyinstaller
  "${PYTHON_BIN}" -m pip install -r requirements.txt
fi

if [[ -n "${RELEASE_TAG// }" ]]; then
  normalized_tag="$("${PYTHON_BIN}" - "${RELEASE_TAG}" <<'PY'
import re
import sys

tag = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
match = re.search(r"(\d+(?:[._-]\d+){1,3}(?:[-_.]?(?:a|b|rc|post|dev)\d+)?)", tag)
if match:
    print(match.group(1).replace("_", "."))
PY
)"
  if [[ -n "${normalized_tag}" ]]; then
    RELEASE_TAG="${normalized_tag}"
  fi
fi

if [[ -n "${RELEASE_TAG// }" ]]; then
  release_info_path="${PYTHON_ROOT}/build/release-info.json"
  mkdir -p "$(dirname "${release_info_path}")"
  "${PYTHON_BIN}" - "${release_info_path}" "${RELEASE_TAG}" <<'PY'
import datetime as dt
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
release_tag = sys.argv[2]
payload = {
    "release_tag": release_tag,
    "built_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
}
path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
PY
fi

if [[ -z "${ICON_PATH}" ]]; then
  if [[ "${UNAME_S}" == "Darwin" ]]; then
    candidate="${REPO_ROOT}/assets/crypto_forex_logo.icns"
    if [[ -f "${candidate}" ]]; then
      ICON_PATH="${candidate}"
    fi
  else
    for candidate in \
      "${REPO_ROOT}/assets/crypto_forex_logo.png" \
      "${REPO_ROOT}/assets/crypto_forex_logo.ico"; do
      if [[ -f "${candidate}" ]]; then
        ICON_PATH="${candidate}"
        break
      fi
    done
  fi
fi

data_sep=":"
case "${UNAME_S}" in
  MSYS*|MINGW*|CYGWIN*)
    data_sep=";"
    ;;
esac

pyinstaller_args=(
  -m PyInstaller
  main.py
  --name "${NAME}"
  --onefile
  --clean
  --noconfirm
  --specpath build
  --collect-submodules binance_sdk_derivatives_trading_usds_futures
  --collect-submodules binance_sdk_derivatives_trading_coin_futures
  --collect-submodules binance_sdk_spot
  --copy-metadata python-binance
  --copy-metadata binance-connector
  --copy-metadata ccxt
  --copy-metadata binance-sdk-derivatives-trading-usds-futures
  --copy-metadata binance-sdk-derivatives-trading-coin-futures
  --copy-metadata binance-sdk-spot
  --hidden-import binance.client
  --hidden-import binance.spot
)

if [[ "${CONSOLE}" -eq 1 ]]; then
  pyinstaller_args+=(--console)
else
  pyinstaller_args+=(--windowed)
fi

if [[ -n "${ICON_PATH}" && -f "${ICON_PATH}" ]]; then
  if [[ "${UNAME_S}" == "Darwin" && "${ICON_PATH##*.}" != "icns" ]]; then
    echo "Skipping icon '${ICON_PATH}' on macOS because PyInstaller expects a .icns file." >&2
  else
    pyinstaller_args+=(--icon "${ICON_PATH}")
  fi
else
  ICON_PATH=""
fi

assets_dir="${REPO_ROOT}/assets"
if [[ -d "${assets_dir}" ]]; then
  pyinstaller_args+=(--add-data "${assets_dir}${data_sep}assets")
fi

if [[ -n "${release_info_path}" && -f "${release_info_path}" ]]; then
  pyinstaller_args+=(--add-data "${release_info_path}${data_sep}app")
fi

"${PYTHON_BIN}" "${pyinstaller_args[@]}"

binary_path="dist/${NAME}"
case "${UNAME_S}" in
  MSYS*|MINGW*|CYGWIN*)
    binary_path="${binary_path}.exe"
    ;;
esac

echo "Done. Binary at: ${binary_path}"
