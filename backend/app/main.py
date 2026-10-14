"""FastAPI application factory. Run with: uvicorn app.main:create_app --factory"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.core.db import dispose_engine, get_sessionmaker
from app.core.errors import register_error_handlers
from app.core.health import router as health_router
from app.core.logging import configure_logging
from app.modules.agent.llm.factory import build_llm
from app.modules.agent.router import router as agent_router
from app.modules.agent.service import AgentService
from app.modules.erp_mock.router import router as erp_router
from app.modules.evaluation.router import router as evaluation_router
from app.modules.execution.router import router as execution_router
from app.modules.observability.router import router as observability_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    # One shared HTTP client for every LLM call; the service owns the background run tasks.
    settings = get_settings()
    async with httpx.AsyncClient() as http:
        svc = AgentService(
            get_sessionmaker(),
            build_llm("decision", settings, http),
            build_llm("reviewer", settings, http),
            settings,
        )
        try:
            await svc.recover()  # runs a restart interrupted before they reached the buyer
        except SQLAlchemyError:  # e.g. migrations not applied yet: serve, but say so
            logger.exception("could not recover interrupted agent runs")
        app.state.agent_service = svc
        yield
        app.state.agent_service = None
        await svc.shutdown()
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.logging.level, settings.logging.json_format)

    app = FastAPI(title="Rappi Turbo — AI Purchasing Agent", version="0.1.0", lifespan=_lifespan)
    register_error_handlers(app)
    app.include_router(health_router)
    app.include_router(erp_router)
    app.include_router(execution_router)
    app.include_router(agent_router)
    app.include_router(observability_router)
    app.include_router(evaluation_router)
    return app
