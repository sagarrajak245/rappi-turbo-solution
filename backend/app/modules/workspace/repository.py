"""Cross-module reads for the buyer's screens. No business rules here."""

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Row, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AgentRun,
    Budget,
    ErpPurchaseOrder,
    InventorySnapshot,
    Node,
    Product,
    Recommendation,
    StorageZone,
)
from app.shared.enums import ErpPoStatus, RunStatus


async def list_recommendations(
    session: AsyncSession, node: str | None
) -> Sequence[Row[Recommendation, Product, Node]]:
    stmt = (
        select(Recommendation, Product, Node)
        .join(Product, Recommendation.product_id == Product.id)
        .join(Node, Recommendation.node_id == Node.id)
        .order_by(Node.code, Product.sku, Recommendation.id)
    )
    if node is not None:
        stmt = stmt.where(Node.code == node)
    return (await session.execute(stmt)).all()


async def list_runs_newest_first(session: AsyncSession) -> Sequence[AgentRun]:
    stmt = select(AgentRun).order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
    return (await session.execute(stmt)).scalars().all()


async def list_runs_by_status(
    session: AsyncSession, statuses: Sequence[RunStatus]
) -> Sequence[AgentRun]:
    stmt = (
        select(AgentRun)
        .where(AgentRun.status.in_(statuses))
        .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
    )
    return (await session.execute(stmt)).scalars().all()


async def list_decisions(session: AsyncSession) -> Sequence[dict[str, object]]:
    stmt = select(AgentRun.decision).where(AgentRun.decision.is_not(None))
    return [d for d in (await session.execute(stmt)).scalars().all() if d]


async def list_executed_orders(
    session: AsyncSession,
) -> Sequence[Row[AgentRun, ErpPurchaseOrder]]:
    """Runs whose execution placed an ERP order, newest order first."""
    stmt = (
        select(AgentRun, ErpPurchaseOrder)
        .join(
            ErpPurchaseOrder,
            ErpPurchaseOrder.erp_number == AgentRun.execution["erp_number"].as_string(),
        )
        .order_by(ErpPurchaseOrder.created_at.desc(), ErpPurchaseOrder.id.desc())
    )
    return (await session.execute(stmt)).all()


async def committed_since(session: AsyncSession, nodes: Sequence[str], since: datetime) -> Decimal:
    stmt = select(func.coalesce(func.sum(ErpPurchaseOrder.total_inr), 0)).where(
        ErpPurchaseOrder.node_code.in_(nodes),
        ErpPurchaseOrder.created_at >= since,
        ErpPurchaseOrder.status.not_in((ErpPoStatus.CANCELLED, ErpPoStatus.REJECTED)),
    )
    return Decimal((await session.execute(stmt)).scalar_one())


async def list_nodes_in_city(session: AsyncSession, city: str) -> Sequence[Node]:
    stmt = select(Node).where(Node.city == city).order_by(Node.code)
    return (await session.execute(stmt)).scalars().all()


async def budget_totals(
    session: AsyncSession, node_ids: Sequence[int], period: str
) -> Sequence[Row[int, Decimal, Decimal]]:
    """(node_id, committed, amount) summed over categories for one period."""
    stmt = (
        select(Budget.node_id, func.sum(Budget.committed_inr), func.sum(Budget.amount_inr))
        .where(Budget.node_id.in_(node_ids), Budget.period == period)
        .group_by(Budget.node_id)
    )
    return (await session.execute(stmt)).all()


async def storage_capacity(
    session: AsyncSession, node_ids: Sequence[int]
) -> Sequence[Row[int, Decimal]]:
    stmt = (
        select(StorageZone.node_id, func.sum(StorageZone.capacity_units))
        .where(StorageZone.node_id.in_(node_ids))
        .group_by(StorageZone.node_id)
    )
    return (await session.execute(stmt)).all()


async def list_snapshots_with_volume(
    session: AsyncSession, node_ids: Sequence[int]
) -> Sequence[Row[InventorySnapshot, Decimal]]:
    """(snapshot, unit_volume) oldest first, so the last one per node x product is current."""
    stmt = (
        select(InventorySnapshot, Product.unit_volume)
        .join(Product, InventorySnapshot.product_id == Product.id)
        .where(InventorySnapshot.node_id.in_(node_ids))
        .order_by(InventorySnapshot.as_of, InventorySnapshot.id)
    )
    return (await session.execute(stmt)).all()
