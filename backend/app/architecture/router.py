from __future__ import annotations

from fastapi import APIRouter


def build_architecture_router() -> APIRouter:
    router = APIRouter(tags=["architecture"])

    @router.get("/architecture")
    def get_architecture() -> dict[str, object]:
        return {
            "target_architecture": "core-supervisor-nodes",
            "status": "foundation",
            "domains": [
                {
                    "id": "core",
                    "name": "Core",
                    "role": "control_plane",
                    "module_paths": ["backend/app/core", "backend/app/api", "backend/app/system"],
                    "docs_path": "docs/core",
                    "routes": ["/api/architecture"],
                },
                {
                    "id": "supervisor",
                    "name": "Supervisor",
                    "role": "host_runtime_authority",
                    "module_paths": ["backend/app/supervisor", "backend/synthia_supervisor"],
                    "docs_path": "docs/supervisor",
                    "routes": ["/api/supervisor/health", "/api/supervisor/info"],
                },
                {
                    "id": "nodes",
                    "name": "Nodes",
                    "role": "external_execution_layer",
                    "module_paths": ["backend/app/nodes", "backend/app/system/onboarding"],
                    "docs_path": "docs/nodes",
                    "routes": ["/api/nodes", "/api/nodes/{node_id}"],
                },
            ],
        }

    return router
