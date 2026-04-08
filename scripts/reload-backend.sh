#!/usr/bin/env bash
set -euo pipefail

backend_unit="hexe-backend.service"

echo "[reload-backend] Reloading user systemd units"
systemctl --user daemon-reload

echo "[reload-backend] Restarting: ${backend_unit}"
systemctl --user restart "${backend_unit}"

echo "[reload-backend] Status"
systemctl --user --no-pager --full status "${backend_unit}" || true

echo "[reload-backend] Done"
