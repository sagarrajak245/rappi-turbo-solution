"""HTTP surface of the execution loop. Thin: parse, call the service, return its result."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.modules.auth.deps import require_role
from app.modules.execution import service
from app.modules.execution.schemas import ApprovedOrder, ExecutionResult
from app.shared.enums import UserRole

# Buyers order through the agent's decision gate; placing an order directly is an admin tool.
router = APIRouter(
    prefix="/execution",
    tags=["execution"],
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)

Session = Annotated[AsyncSession, Depends(get_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]


@router.post("/orders", response_model=ExecutionResult)
async def execute_order(
    body: ApprovedOrder, session: Session, settings: AppSettings
) -> ExecutionResult:
    now = datetime.now(UTC)
    return await service.execute(session, body, now.date(), now, settings)
