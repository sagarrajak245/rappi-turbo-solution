"""Record a notification and push it to live subscribers."""

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import NotFound
from app.modules.notifications import repository as repo
from app.modules.notifications.broadcaster import Broadcaster
from app.modules.notifications.models import Notification, NotificationRead
from app.modules.notifications.schemas import NotificationOut


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _out(row: Notification, read_at: datetime | None) -> NotificationOut:
    """`read_at` is the calling user's own read time."""
    return NotificationOut(
        id=row.id,
        user_id=row.user_id,
        kind=row.kind,
        run_id=row.run_id,
        message=row.message,
        read_at=read_at,
        created_at=row.created_at,
    )


class NotificationService:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        broadcaster: Broadcaster,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._sm = sessionmaker
        self.broadcaster = broadcaster
        self._clock = clock

    async def notify(self, run_id: str, kind: str, message: str) -> None:
        """Broadcast (all buyers) notification about a run. Matches AgentService's `notify` hook."""
        row = Notification(
            user_id=None, kind=kind, run_id=run_id, message=message, created_at=self._clock()
        )
        async with self._sm() as session:
            session.add(row)
            await session.commit()
            out = _out(row, None)
        await self.broadcaster.publish(out.model_dump(mode="json"))

    async def list_for(self, user_id: str, limit: int = 50) -> list[NotificationOut]:
        async with self._sm() as session:
            rows = await repo.list_for_user(session, user_id, limit)
            return [_out(row, read_at) for row, read_at in rows]

    async def mark_read(self, notification_id: int, user_id: str) -> NotificationOut:
        async with self._sm() as session:
            row = await repo.get_visible(session, notification_id, user_id)
            if row is None:
                raise NotFound(f"Notification {notification_id} not found")
            read = await repo.get_read(session, notification_id, user_id)
            if read is None:
                read = NotificationRead(
                    notification_id=notification_id, user_id=user_id, read_at=self._clock()
                )
                repo.add_read(session, read)
                await session.commit()
            return _out(row, read.read_at)
