from __future__ import annotations

import os


def ensure_runtime_dirs(base_dir: str) -> dict[str, str]:
    root = os.path.abspath(os.path.join(base_dir, "var", "mqtt_runtime"))
    staged = os.path.join(root, "staged")
    live = os.path.join(root, "live")
    data = os.path.join(root, "data")
    logs = os.path.join(root, "logs")
    for path in [root, staged, live, data, logs]:
        os.makedirs(path, mode=0o755, exist_ok=True)
    return {
        "root": root,
        "staged": staged,
        "live": live,
        "data": data,
        "logs": logs,
    }
