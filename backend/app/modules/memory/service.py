"""Learning loop (D25): buyer feedback -> pending lesson -> buyer confirms -> next runs use it.

Lessons only reach the decide prompt; the deterministic validator keeps the final say, so a
lesson can change soft choices but never a hard constraint.
"""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, NotFound
from app.modules.memory import repository as repo
from app.modules.memory.models import Lesson
from app.modules.memory.schemas import LessonOut
from app.shared.enums import LessonStatus


def _out(row: Lesson) -> LessonOut:
    return LessonOut(
        id=row.id,
        sku=row.sku,
        node=row.node_code,
        text=row.text,
        status=row.status,
        source_run_id=row.source_run_id,
        times_applied=row.times_applied,
    )


def record_feedback(
    session: AsyncSession, run_id: str, sku: str, node: str, reason: str, now: datetime
) -> None:
    """Store the buyer's reason as a pending lesson. The caller commits with its decision."""
    repo.add(
        session,
        Lesson(
            sku=sku,
            node_code=node,
            text=reason.strip(),
            status=LessonStatus.PENDING,
            source_run_id=run_id,
            times_applied=0,
            created_at=now,
            updated_at=now,
        ),
    )


async def active_for(session: AsyncSession, sku: str, node: str) -> list[LessonOut]:
    return [_out(r) for r in await repo.list_by(session, LessonStatus.ACTIVE, sku, node)]


async def mark_applied(session: AsyncSession, ids: Sequence[int], now: datetime) -> None:
    """Count one use of each lesson. The caller commits."""
    if ids:
        await repo.increment_applied(session, ids, now)


async def list_lessons(session: AsyncSession, status: LessonStatus | None) -> list[LessonOut]:
    return [_out(r) for r in await repo.list_by(session, status)]


async def _move(
    session: AsyncSession,
    lesson_id: int,
    allowed: tuple[LessonStatus, ...],
    new: LessonStatus,
    now: datetime,
) -> LessonOut:
    row = await repo.get(session, lesson_id)
    if row is None:
        raise NotFound(f"Lesson {lesson_id} not found", {"lesson_id": lesson_id})
    if row.status not in allowed:
        raise Conflict(f"Lesson {lesson_id} is {row.status}", {"lesson_id": lesson_id})
    row.status, row.updated_at = new, now
    await session.commit()
    return _out(row)


async def confirm(session: AsyncSession, lesson_id: int, now: datetime) -> LessonOut:
    """The buyer said "remember this": the lesson applies from the next run."""
    return await _move(session, lesson_id, (LessonStatus.PENDING,), LessonStatus.ACTIVE, now)


async def disable(session: AsyncSession, lesson_id: int, now: datetime) -> LessonOut:
    allowed = (LessonStatus.PENDING, LessonStatus.ACTIVE)
    return await _move(session, lesson_id, allowed, LessonStatus.DISABLED, now)
