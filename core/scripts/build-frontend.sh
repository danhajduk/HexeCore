#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "[frontend-build] Installing frontend dependencies"
cd "$REPO_DIR/frontend"
npm install

echo "[frontend-build] Building production frontend"
npm run build

echo "[frontend-build] Production frontend ready: $REPO_DIR/frontend/dist"
