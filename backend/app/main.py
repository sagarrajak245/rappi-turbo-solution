"""FastAPI application factory. Run with: uvicorn app.main:create_app --factory"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.db import dispose_engine
from app.core.errors import register_error_handlers
from app.core.health import router as health_router
from app.core.logging import configure_logging
from app.modules.erp_mock.router import router as erp_router
from app.modules.execution.router import router as execution_router


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.logging.level, settings.logging.json_format)

    app = FastAPI(title="Rappi Turbo — AI Purchasing Agent", version="0.1.0", lifespan=_lifespan)
    register_error_handlers(app)
    app.include_router(health_router)
    app.include_router(erp_router)
    app.include_router(execution_router)
    return app
