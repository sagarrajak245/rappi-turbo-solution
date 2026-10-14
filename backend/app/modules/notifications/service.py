"""Record a notification and push it to live subscribers."""

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import NotFound
from app.modules.notifications import repository as repo
from app.modules.notifications.broadcaster import Broadcaster
from app.modules.notifications.models import Notification
from app.modules.notifications.schemas import NotificationOut


def _utcnow() -> datetime:
    return datetime.now(UTC)


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
            out = NotificationOut.model_validate(row)
        await self.broadcaster.publish(out.model_dump(mode="json"))

    async def list_for(self, user_id: str, limit: int = 50) -> list[NotificationOut]:
        async with self._sm() as session:
            rows = await repo.list_for_user(session, user_id, limit)
            return [NotificationOut.model_validate(r) for r in rows]

    async def mark_read(self, notification_id: int, user_id: str) -> NotificationOut:
        async with self._sm() as session:
            row = await repo.get_visible(session, notification_id, user_id)
            if row is None:
                raise NotFound(f"Notification {notification_id} not found")
            if row.read_at is None:
                row.read_at = self._clock()
                await session.commit()
            return NotificationOut.model_validate(row)
