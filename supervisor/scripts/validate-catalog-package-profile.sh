#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/validate-catalog-package-profile.sh <package_profile> <artifact_path>

Examples:
  scripts/validate-catalog-package-profile.sh embedded_addon ./addon.tgz
  scripts/validate-catalog-package-profile.sh standalone_service ./addon.zip

Validation rules:
  - embedded_addon requires backend/addon.py in artifact
  - standalone_service requires app/main.py and must not include backend/addon.py
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -ne 2 ]]; then
  usage
  exit 2
fi

profile="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
artifact="$2"

if [[ ! -f "$artifact" ]]; then
  echo "error: artifact_not_found: $artifact" >&2
  exit 2
fi

if [[ "$profile" != "embedded_addon" && "$profile" != "standalone_service" ]]; then
  echo "error: unsupported_package_profile: $profile" >&2
  exit 2
fi

tmp_list="$(mktemp)"
trap 'rm -f "$tmp_list"' EXIT

if unzip -Z1 "$artifact" >"$tmp_list" 2>/dev/null; then
  :
elif tar -tf "$artifact" >"$tmp_list" 2>/dev/null; then
  :
else
  echo "error: unsupported_artifact_format: expected zip/tar/tgz" >&2
  exit 2
fi

has_backend_addon=0
has_app_main=0
if grep -qE '(^|/)(backend/addon\.py)$' "$tmp_list"; then
  has_backend_addon=1
fi
if grep -qE '(^|/)(app/main\.py)$' "$tmp_list"; then
  has_app_main=1
fi

if [[ "$profile" == "embedded_addon" ]]; then
  if [[ "$has_backend_addon" -ne 1 ]]; then
    echo "error: profile_layout_mismatch: embedded_addon requires backend/addon.py" >&2
    exit 1
  fi
  echo "ok: embedded_addon layout validated"
  exit 0
fi

if [[ "$has_app_main" -ne 1 ]]; then
  echo "error: profile_layout_mismatch: standalone_service requires app/main.py" >&2
  exit 1
fi
if [[ "$has_backend_addon" -eq 1 ]]; then
  echo "error: profile_layout_mismatch: standalone_service artifact must not include backend/addon.py" >&2
  exit 1
fi
echo "ok: standalone_service layout validated"
