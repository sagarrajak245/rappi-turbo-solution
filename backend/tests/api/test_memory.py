"""HTTP surface of memory: list lessons, confirm ("Remember this?") or disable them."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_session
from app.main import create_app
from app.modules.memory.models import Lesson
from app.shared.enums import LessonStatus

NOW = datetime(2026, 10, 14, 6, 0, tzinfo=UTC)


@pytest.fixture
async def client(sessionmaker: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def _session() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as s:
            yield s

    app.dependency_overrides[get_session] = _session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def lesson_id(sessionmaker: async_sessionmaker[AsyncSession]) -> int:
    async with sessionmaker() as s:
        row = Lesson(
            sku="COKE-750",
            node_code="BANDRA",
            text="weekends slower",
            status=LessonStatus.PENDING,
            times_applied=0,
            created_at=NOW,
            updated_at=NOW,
        )
        s.add(row)
        await s.commit()
        return row.id


async def test_list_confirm_disable(client: AsyncClient, lesson_id: int) -> None:
    pending = (await client.get("/memory/lessons", params={"status": "pending"})).json()
    assert [x["id"] for x in pending] == [lesson_id]

    confirmed = await client.post(f"/memory/lessons/{lesson_id}/confirm")
    assert confirmed.status_code == 200 and confirmed.json()["status"] == "active"
    again = await client.post(f"/memory/lessons/{lesson_id}/confirm")
    assert again.status_code == 409

    disabled = await client.post(f"/memory/lessons/{lesson_id}/disable")
    assert disabled.json()["status"] == "disabled"
    assert (await client.get("/memory/lessons", params={"status": "active"})).json() == []


async def test_unknown_lesson_is_not_found(client: AsyncClient) -> None:
    r = await client.post("/memory/lessons/999/confirm")
    assert r.status_code == 404
