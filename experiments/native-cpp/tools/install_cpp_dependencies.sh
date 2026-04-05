#!/usr/bin/env bash
set -euo pipefail

AQT_INSTALL_VERSION="${AQT_INSTALL_VERSION:-3.3.0}"
QT_VERSION="${QT_VERSION:-6.11.0}"
QT_OUTPUT_DIR="${QT_OUTPUT_DIR:-$HOME/Qt}"
QT_HOST="${QT_HOST:-}"
QT_ARCH="${QT_ARCH:-}"
TRIPLET="${TRIPLET:-}"
VCPKG_REF="${VCPKG_REF:-d0ba406f0e5352517386709dba49fbabf99a9e3c}"
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage: ./Languages/C++/tools/install_cpp_dependencies.sh [options]

Options:
  --aqt-install-version <ver>   Pin aqtinstall version (default: 3.3.0)
  --qt-version <ver>            Pin Qt version (default: 6.11.0)
  --qt-output-dir <path>        Qt install root (default: $HOME/Qt)
  --qt-host <host>              aqt host: mac|linux|linux_arm64 (auto-detected)
  --qt-arch <arch>              aqt architecture (auto-detected)
  --triplet <triplet>           vcpkg triplet (auto-detected)
  --vcpkg-ref <ref>             vcpkg git ref (default: pinned commit)
  --dry-run                     Print commands without executing
  -h, --help                    Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --aqt-install-version)
      AQT_INSTALL_VERSION="$2"
      shift 2
      ;;
    --qt-version)
      QT_VERSION="$2"
      shift 2
      ;;
    --qt-output-dir)
      QT_OUTPUT_DIR="$2"
      shift 2
      ;;
    --qt-host)
      QT_HOST="$2"
      shift 2
      ;;
    --qt-arch)
      QT_ARCH="$2"
      shift 2
      ;;
    --triplet)
      TRIPLET="$2"
      shift 2
      ;;
    --vcpkg-ref)
      VCPKG_REF="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

run() {
  echo "+ $*"
  if [[ "$DRY_RUN" -eq 0 ]]; then
    "$@"
  fi
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Required command not found: $1" >&2
    exit 1
  fi
}

require_cmd git
require_cmd uname
require_cmd find

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cpp_root="$(cd "$script_dir/.." && pwd)"
repo_root="$(cd "$cpp_root/../.." && pwd)"
local_vcpkg="$repo_root/.vcpkg"

venv_python="$repo_root/.venv/bin/python3"
if [[ -x "$venv_python" ]]; then
  python_exe="$venv_python"
elif command -v python3 >/dev/null 2>&1; then
  python_exe="python3"
elif command -v python >/dev/null 2>&1; then
  python_exe="python"
else
  echo "Python is required but was not found in PATH." >&2
  exit 1
fi

uname_s="$(uname -s)"
uname_m="$(uname -m)"
case "$uname_s" in
  Darwin)
    : "${QT_HOST:=mac}"
    : "${QT_ARCH:=clang_64}"
    if [[ "$uname_m" == "arm64" ]]; then
      : "${TRIPLET:=arm64-osx}"
    else
      : "${TRIPLET:=x64-osx}"
    fi
    ;;
  Linux)
    if [[ "$uname_m" == "aarch64" || "$uname_m" == "arm64" ]]; then
      : "${QT_HOST:=linux_arm64}"
      : "${QT_ARCH:=linux_gcc_arm64}"
      : "${TRIPLET:=arm64-linux}"
    else
      : "${QT_HOST:=linux}"
      : "${QT_ARCH:=linux_gcc_64}"
      : "${TRIPLET:=x64-linux}"
    fi
    ;;
  *)
    echo "Unsupported host OS '$uname_s'. Use install_cpp_dependencies.ps1 on Windows." >&2
    exit 1
    ;;
esac

echo "Using Python: $python_exe"
echo "Repository root: $repo_root"
echo "Qt host/arch: $QT_HOST / $QT_ARCH"
echo "Qt version: $QT_VERSION"
echo "Qt output dir: $QT_OUTPUT_DIR"
echo "vcpkg ref: $VCPKG_REF"
echo "vcpkg triplet: $TRIPLET"

aqt_spec="aqtinstall==$AQT_INSTALL_VERSION"
run "$python_exe" -m pip install --upgrade "$aqt_spec"

qt_modules=(qtwebengine qtwebsockets qtwebchannel qtpositioning)
run "$python_exe" -m aqt install-qt "$QT_HOST" desktop "$QT_VERSION" "$QT_ARCH" --outputdir "$QT_OUTPUT_DIR" -m "${qt_modules[@]}"

if [[ ! -x "$local_vcpkg/vcpkg" && ! -f "$local_vcpkg/vcpkg.exe" ]]; then
  run git clone https://github.com/microsoft/vcpkg.git "$local_vcpkg"
fi

run git -C "$local_vcpkg" fetch --tags --force
if [[ -z "$VCPKG_REF" ]]; then
  echo "VcpkgRef cannot be empty." >&2
  exit 1
fi
run git -C "$local_vcpkg" checkout "$VCPKG_REF"

run "$local_vcpkg/bootstrap-vcpkg.sh" -disableMetrics

ports=(
  "eigen3:$TRIPLET"
  "xtensor:$TRIPLET"
  "talib:$TRIPLET"
  "cpr:$TRIPLET"
  "curl[tool,ssl]:$TRIPLET"
  "vulkan-headers:$TRIPLET"
)
run "$local_vcpkg/vcpkg" install "${ports[@]}"

qt6_dir_hint=""
if [[ "$DRY_RUN" -eq 0 ]]; then
  while IFS= read -r config_path; do
    qt6_dir_hint="$(dirname "$config_path")"
    break
  done < <(find "$QT_OUTPUT_DIR/$QT_VERSION" -type f -path "*/lib/cmake/Qt6/Qt6Config.cmake" 2>/dev/null | sort)
fi

echo "Done."
echo "Qt root: $QT_OUTPUT_DIR/$QT_VERSION"
echo "vcpkg root: $local_vcpkg"
if [[ -n "$qt6_dir_hint" ]]; then
  echo "Qt6_DIR hint: $qt6_dir_hint"
fi
