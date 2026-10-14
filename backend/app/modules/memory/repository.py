"""Queries for lessons. No business rules here."""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.memory.models import Lesson
from app.shared.enums import LessonStatus


def add(session: AsyncSession, lesson: Lesson) -> None:
    session.add(lesson)


async def get(session: AsyncSession, lesson_id: int) -> Lesson | None:
    return await session.get(Lesson, lesson_id)


async def list_by(
    session: AsyncSession,
    status: LessonStatus | None = None,
    sku: str | None = None,
    node_code: str | None = None,
) -> Sequence[Lesson]:
    stmt = select(Lesson).order_by(Lesson.id)
    if status is not None:
        stmt = stmt.where(Lesson.status == status)
    if sku is not None:
        stmt = stmt.where(Lesson.sku == sku)
    if node_code is not None:
        stmt = stmt.where(Lesson.node_code == node_code)
    return (await session.execute(stmt)).scalars().all()


async def increment_applied(session: AsyncSession, ids: Sequence[int], now: datetime) -> None:
    await session.execute(
        update(Lesson)
        .where(Lesson.id.in_(ids))
        .values(times_applied=Lesson.times_applied + 1, updated_at=now)
    )
