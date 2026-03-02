import os
import subprocess
from pathlib import Path

def compose_up(compose_file: Path, project_name: str):
    subprocess.run(["docker","compose","-f",str(compose_file),"-p",project_name,"up","-d"], check=True)

def compose_down(compose_file: Path, project_name: str):
    subprocess.run(["docker","compose","-f",str(compose_file),"-p",project_name,"down"], check=True)

def ensure_extracted(artifact_path: Path, extracted_dir: Path):
    if extracted_dir.exists():
        return
    extracted_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["tar","-xzf",str(artifact_path),"-C",str(extracted_dir)], check=True)

def ensure_compose_files(desired, extracted_dir: Path, compose_file: Path, env_file: Path):
    env_values = dict(getattr(desired.config, "env", {}) or {})
    service_token = os.environ.get("SYNTHIA_SERVICE_TOKEN")
    if service_token:
        env_values.setdefault("SYNTHIA_SERVICE_TOKEN", service_token)
    env_lines = [f"{k}={v}" for k, v in sorted(env_values.items())]
    env_file.write_text("\n".join(env_lines) + ("\n" if env_lines else ""))

    if compose_file.exists():
        return
    network_name = desired.runtime.network or "synthia_net"
    ports_yaml = ""
    for item in list(getattr(desired.runtime, "ports", []) or []):
        if not isinstance(item, dict):
            continue
        host = item.get("host")
        container = item.get("container")
        if host is None or container is None:
            continue
        proto = str(item.get("proto") or "tcp").lower()
        ports_yaml += f"      - \"127.0.0.1:{int(host)}:{int(container)}/{proto}\"\n"
    ports_section = f"    ports:\n{ports_yaml}" if ports_yaml else ""
    compose_file.write_text(f"""
services:
  {desired.addon_id}:
    build: {extracted_dir}
    restart: unless-stopped
    privileged: false
    security_opt:
      - no-new-privileges:true
    env_file:
      - {env_file}
    networks:
      - {network_name}
{ports_section}

networks:
  {network_name}:
    name: {network_name}
""")
