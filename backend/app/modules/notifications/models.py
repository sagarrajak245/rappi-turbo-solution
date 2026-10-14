"""A notification for one user, or for everyone when `user_id` is null (broadcast).

Read state is per user (`notification_reads`), so one user reading a broadcast leaves it
unread for everyone else.
"""

from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UTCDateTime


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())


class NotificationRead(Base):
    __tablename__ = "notification_reads"

    notification_id: Mapped[int] = mapped_column(ForeignKey("notifications.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    read_at: Mapped[datetime] = mapped_column(UTCDateTime())
