"""Lessons learned from buyer feedback, scoped to one SKU x node (KB §3.4, D25)."""

from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UTCDateTime
from app.core.db_types import str_enum
from app.shared.enums import LessonStatus


class Lesson(Base):
    __tablename__ = "lessons"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(40))
    node_code: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[LessonStatus] = mapped_column(str_enum(LessonStatus), index=True)
    source_run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"))
    times_applied: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime())
