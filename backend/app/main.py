"""FastAPI application factory. Run with: uvicorn app.main:create_app --factory"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app.core.config import get_settings
from app.core.db import dispose_engine, get_sessionmaker
from app.core.errors import register_error_handlers
from app.core.health import router as health_router
from app.core.logging import configure_logging
from app.modules.agent.llm.factory import build_llm
from app.modules.agent.router import router as agent_router
from app.modules.agent.service import AgentService
from app.modules.erp_mock.router import router as erp_router
from app.modules.execution.router import router as execution_router


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    # One shared HTTP client for every LLM call; the service owns the run checkpointer.
    settings = get_settings()
    async with httpx.AsyncClient() as http:
        app.state.agent_service = AgentService(
            get_sessionmaker(),
            build_llm("decision", settings, http),
            build_llm("reviewer", settings, http),
            settings,
        )
        yield
        app.state.agent_service = None
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
    return app
