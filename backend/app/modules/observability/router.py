"""Admin metrics: run outcomes and LLM spend."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_sessionmaker
from app.modules.auth.deps import require_role
from app.modules.observability import service
from app.modules.observability.schemas import Metrics
from app.shared.enums import UserRole

router = APIRouter(
    prefix="/admin", tags=["admin"], dependencies=[Depends(require_role(UserRole.ADMIN))]
)


def get_store() -> async_sessionmaker[AsyncSession]:
    return get_sessionmaker()


Store = Annotated[async_sessionmaker[AsyncSession], Depends(get_store)]


@router.get("/metrics")
async def get_metrics(store: Store) -> Metrics:
    async with store() as session:
        return await service.metrics(session)
