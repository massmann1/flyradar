from __future__ import annotations

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from app.api.routers import admin, health
from app.core.config import get_settings
from app.core.container import create_container
from app.core.logging import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings)
    container = create_container(settings)
    app.state.container = container
    try:
        yield
    finally:
        await container.close()


def create_app() -> FastAPI:
    app = FastAPI(title="Flight Alerts Admin API", lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(admin.router)
    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run("app.main_api:app", host="0.0.0.0", port=8000)
