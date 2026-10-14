from datetime import datetime

from sqlalchemy import ColumnElement, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.models import Notification, NotificationRead


def _visible_to(user_id: str) -> ColumnElement[bool]:
    return or_(Notification.user_id == user_id, Notification.user_id.is_(None))


async def list_for_user(
    session: AsyncSession, user_id: str, limit: int
) -> list[tuple[Notification, datetime | None]]:
    """The user's notifications (theirs and broadcasts), newest first, with their read time."""
    stmt = (
        select(Notification, NotificationRead.read_at)
        .outerjoin(
            NotificationRead,
            and_(
                NotificationRead.notification_id == Notification.id,
                NotificationRead.user_id == user_id,
            ),
        )
        .where(_visible_to(user_id))
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit)
    )
    return [(n, read_at) for n, read_at in (await session.execute(stmt)).all()]


async def get_visible(
    session: AsyncSession, notification_id: int, user_id: str
) -> Notification | None:
    row = await session.get(Notification, notification_id)
    if row is None or row.user_id not in (None, user_id):
        return None
    return row


async def get_read(
    session: AsyncSession, notification_id: int, user_id: str
) -> NotificationRead | None:
    return await session.get(NotificationRead, (notification_id, user_id))


def add_read(session: AsyncSession, read: NotificationRead) -> None:
    session.add(read)
