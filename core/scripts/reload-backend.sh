#!/usr/bin/env bash
set -euo pipefail

backend_unit="hexe-backend.service"

if [[ "${SKIP_FRONTEND_BUILD:-0}" != "1" ]]; then
  echo "[reload-backend] Rebuilding production frontend"
  "$(cd "$(dirname "$0")" && pwd)/build-frontend.sh"
fi

echo "[reload-backend] Reloading user systemd units"
systemctl --user daemon-reload

echo "[reload-backend] Restarting: ${backend_unit}"
systemctl --user restart "${backend_unit}"

echo "[reload-backend] Status"
systemctl --user --no-pager --full status "${backend_unit}" || true

echo "[reload-backend] Done"
