"""FastAPI application factory. Run with: uvicorn app.main:create_app --factory"""

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.health import router as health_router
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.logging.level, settings.logging.json_format)

    app = FastAPI(title="Rappi Turbo — AI Purchasing Agent", version="0.1.0")
    register_error_handlers(app)
    app.include_router(health_router)
    return app
