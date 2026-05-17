from fastapi import FastAPI
import uvicorn

from node_template.config.settings import Settings
from node_template.runtime.service import NodeRuntimeService


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or Settings()
    service = NodeRuntimeService(settings=app_settings)
    app = FastAPI(title="Hexe Node Template")

    @app.get("/health/live")
    async def health_live():
        return {"live": True}

    @app.get("/health/ready")
    async def health_ready():
        return {"ready": True}

    @app.get("/api/health")
    async def api_health():
        return {"status": "ok", "version": app_settings.node_software_version}

    @app.get("/api/node/status")
    async def node_status():
        return service.status_payload()

    return app


def main() -> None:
    settings = Settings()
    uvicorn.run(create_app(settings), host=settings.api_host, port=settings.api_port)


if __name__ == "__main__":
    main()
