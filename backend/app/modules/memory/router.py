"""HTTP surface of memory: the buyer reviews lessons drawn from their feedback."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.modules.auth.deps import current_user, require_role
from app.modules.memory import service
from app.modules.memory.schemas import LessonOut
from app.shared.enums import LessonStatus, UserRole

router = APIRouter(prefix="/memory", tags=["memory"], dependencies=[Depends(current_user)])

Session = Annotated[AsyncSession, Depends(get_session)]
# A confirmed lesson steers the agent's choices, so only buyers may confirm or disable one.
BUYERS = [Depends(require_role(UserRole.BUYER))]


@router.get("/lessons")
async def list_lessons(session: Session, status: LessonStatus | None = None) -> list[LessonOut]:
    return await service.list_lessons(session, status)


@router.post("/lessons/{lesson_id}/confirm", dependencies=BUYERS)
async def confirm(lesson_id: int, session: Session) -> LessonOut:
    return await service.confirm(session, lesson_id, datetime.now(UTC))


@router.post("/lessons/{lesson_id}/disable", dependencies=BUYERS)
async def disable(lesson_id: int, session: Session) -> LessonOut:
    return await service.disable(session, lesson_id, datetime.now(UTC))
