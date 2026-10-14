from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.models import Notification


async def list_for_user(session: AsyncSession, user_id: str, limit: int) -> list[Notification]:
    stmt = (
        select(Notification)
        .where(or_(Notification.user_id == user_id, Notification.user_id.is_(None)))
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars())


async def get_visible(
    session: AsyncSession, notification_id: int, user_id: str
) -> Notification | None:
    row = await session.get(Notification, notification_id)
    if row is None or row.user_id not in (None, user_id):
        return None
    return row
