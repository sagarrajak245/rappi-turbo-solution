"""HTTP surface of the execution loop. Thin: parse, call the service, return its result."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.modules.execution import service
from app.modules.execution.schemas import ApprovedOrder, ExecutionResult

router = APIRouter(prefix="/execution", tags=["execution"])

Session = Annotated[AsyncSession, Depends(get_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]


@router.post("/orders", response_model=ExecutionResult)
async def execute_order(
    body: ApprovedOrder, session: Session, settings: AppSettings
) -> ExecutionResult:
    now = datetime.now(UTC)
    return await service.execute(session, body, now.date(), now, settings)
