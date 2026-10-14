"""Read endpoints behind the buyer's screens. Every route needs a signed-in user."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.modules.auth.deps import CurrentUser, current_user
from app.modules.workspace import service
from app.modules.workspace.schemas import DashboardSummary, InboxRow, PurchaseOrderRow
from app.shared.enums import RunStatus

router = APIRouter(tags=["workspace"], dependencies=[Depends(current_user)])

Session = Annotated[AsyncSession, Depends(get_session)]


def get_clock() -> Callable[[], datetime]:
    return lambda: datetime.now(UTC)


@router.get("/recommendations")
async def list_recommendations(
    session: Session,
    node: str | None = None,
    run_status: Annotated[RunStatus | None, Query(alias="status")] = None,
) -> list[InboxRow]:
    return await service.inbox(session, node, run_status)


@router.get("/purchase-orders")
async def list_purchase_orders(session: Session) -> list[PurchaseOrderRow]:
    return await service.purchase_orders(session)


@router.get("/dashboard/summary")
async def dashboard_summary(
    session: Session,
    user: CurrentUser,
    clock: Annotated[Callable[[], datetime], Depends(get_clock)],
) -> DashboardSummary:
    return await service.dashboard(session, user, clock())
