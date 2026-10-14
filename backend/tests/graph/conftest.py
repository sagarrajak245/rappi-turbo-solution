"""Graph tests: the real graph over a seeded database, with scripted LLMs (no network)."""

from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.modules.agent.llm.fake import ScriptedLlm
from app.modules.agent.service import AgentService
from app.seed.scenario1 import seed_scenario1

TODAY = date(2026, 10, 14)
NOW = datetime(2026, 10, 14, 6, 0, tzinfo=UTC)

Script = list[dict[str, Any] | Exception]
MakeService = Callable[[Script, Script], Awaitable[tuple[AgentService, ScriptedLlm, ScriptedLlm]]]


@pytest.fixture
def make_service(sessionmaker: async_sessionmaker[AsyncSession]) -> MakeService:
    async def _make(
        decide: Script, review: Script
    ) -> tuple[AgentService, ScriptedLlm, ScriptedLlm]:
        async with sessionmaker() as s:
            await seed_scenario1(s, today=TODAY, now=NOW)
        decide_llm, review_llm = ScriptedLlm(decide), ScriptedLlm(review)
        svc = AgentService(sessionmaker, decide_llm, review_llm, get_settings(), clock=lambda: NOW)
        return svc, decide_llm, review_llm

    return _make
