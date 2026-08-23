#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_DIR="${HEXE_CLOUDFLARED_INSTALL_DIR:-$ROOT_DIR/.runtime/bin}"
VERSION="${HEXE_CLOUDFLARED_VERSION:-latest}"

usage() {
  cat <<EOF
Usage: install-cloudflared-native.sh

Installs the cloudflared binary into the repo-local runtime directory.

Environment:
  HEXE_CLOUDFLARED_INSTALL_DIR  Target directory. Defaults to .runtime/bin.
  HEXE_CLOUDFLARED_VERSION      Release tag such as 2026.8.2, or latest.
  HEXE_CLOUDFLARED_DOWNLOAD_URL Fully override the download URL.
EOF
}

case "${1:-}" in
  -h|--help)
    usage
    exit 0
    ;;
  "")
    ;;
  *)
    echo "Unknown arg: $1" >&2
    usage >&2
    exit 1
    ;;
esac

if ! command -v curl >/dev/null 2>&1; then
  echo "[cloudflared-native] ERROR: curl is required" >&2
  exit 1
fi

arch="$(uname -m)"
case "$arch" in
  x86_64|amd64) asset_arch="amd64" ;;
  aarch64|arm64) asset_arch="arm64" ;;
  armv7l|armhf) asset_arch="arm" ;;
  i386|i686) asset_arch="386" ;;
  *)
    echo "[cloudflared-native] ERROR: unsupported architecture: $arch" >&2
    exit 1
    ;;
esac

if [[ -n "${HEXE_CLOUDFLARED_DOWNLOAD_URL:-}" ]]; then
  url="$HEXE_CLOUDFLARED_DOWNLOAD_URL"
elif [[ "$VERSION" == "latest" ]]; then
  url="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${asset_arch}"
else
  url="https://github.com/cloudflare/cloudflared/releases/download/${VERSION}/cloudflared-linux-${asset_arch}"
fi

mkdir -p "$INSTALL_DIR"
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

echo "[cloudflared-native] Downloading $url"
curl -fL --retry 3 --retry-delay 2 -o "$tmp" "$url"
chmod 0755 "$tmp"

echo "[cloudflared-native] Validating downloaded binary"
"$tmp" --version

install -m 0755 "$tmp" "$INSTALL_DIR/cloudflared"

echo "[cloudflared-native] Installed: $INSTALL_DIR/cloudflared"
echo "[cloudflared-native] Supervisor env:"
echo "  HEXE_CLOUDFLARED_PROVIDER=binary"
echo "  HEXE_CLOUDFLARED_BINARY=$INSTALL_DIR/cloudflared"
