"""Read-model for the buyer's screens: read-only queries across modules. No business rules here.

Aggregation and "latest per key" selection happen in SQL so the cost stays bounded as history grows.
"""

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Row, case, func, select
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


async def list_latest_runs(session: AsyncSession) -> Sequence[AgentRun]:
    """The newest run per (sku, node)."""
    rank = (
        func.row_number()
        .over(
            partition_by=(AgentRun.sku, AgentRun.node_code),
            order_by=(AgentRun.created_at.desc(), AgentRun.id.desc()),
        )
        .label("rank")
    )
    ranked = select(AgentRun.id, rank).subquery()
    stmt = select(AgentRun).join(ranked, AgentRun.id == ranked.c.id).where(ranked.c.rank == 1)
    return (await session.execute(stmt)).scalars().all()


async def count_runs(session: AsyncSession, statuses: Sequence[RunStatus]) -> int:
    stmt = select(func.count()).select_from(AgentRun).where(AgentRun.status.in_(statuses))
    return int((await session.execute(stmt)).scalar_one())


async def list_runs_by_status(
    session: AsyncSession, statuses: Sequence[RunStatus], limit: int
) -> Sequence[AgentRun]:
    stmt = (
        select(AgentRun)
        .where(AgentRun.status.in_(statuses))
        .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
        .limit(limit)
    )
    return (await session.execute(stmt)).scalars().all()


async def decision_action_counts(session: AsyncSession) -> dict[str, int]:
    action = AgentRun.decision["action"].as_string()
    stmt = select(action, func.count()).where(AgentRun.decision.is_not(None)).group_by(action)
    return {a: int(n) for a, n in (await session.execute(stmt)).all() if a is not None}


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


async def used_volume(session: AsyncSession, node_ids: Sequence[int]) -> dict[int, Decimal]:
    """(node_id, volume) of current stock: latest snapshot per node x product, negatives as 0."""
    rank = (
        func.row_number()
        .over(
            partition_by=(InventorySnapshot.node_id, InventorySnapshot.product_id),
            order_by=(InventorySnapshot.as_of.desc(), InventorySnapshot.id.desc()),
        )
        .label("rank")
    )
    ranked = (
        select(InventorySnapshot.id, rank).where(InventorySnapshot.node_id.in_(node_ids)).subquery()
    )
    stock = case((InventorySnapshot.on_hand > 0, InventorySnapshot.on_hand), else_=0)
    stmt = (
        select(InventorySnapshot.node_id, func.sum(stock * Product.unit_volume))
        .join(ranked, InventorySnapshot.id == ranked.c.id)
        .join(Product, InventorySnapshot.product_id == Product.id)
        .where(ranked.c.rank == 1)
        .group_by(InventorySnapshot.node_id)
    )
    return {node_id: Decimal(str(vol)) for node_id, vol in (await session.execute(stmt)).all()}
