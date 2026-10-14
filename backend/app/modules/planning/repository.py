"""SQLAlchemy queries behind the planning loader. No business rules live here."""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Row, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Budget,
    DemandForecast,
    InventorySnapshot,
    Node,
    PoLine,
    Product,
    PurchaseOrder,
    Recommendation,
    SalesHistory,
    StorageZone,
    Supplier,
    SupplierProduct,
)
from app.shared.enums import PoStatus

OPEN_PO_STATUSES = (PoStatus.PLACED, PoStatus.CONFIRMED)


async def get_product_by_sku(session: AsyncSession, sku: str) -> Product | None:
    return (await session.execute(select(Product).filter_by(sku=sku))).scalar_one_or_none()


async def get_node_by_code(session: AsyncSession, code: str) -> Node | None:
    return (await session.execute(select(Node).filter_by(code=code))).scalar_one_or_none()


async def get_latest_snapshot(
    session: AsyncSession, node_id: int, product_id: int
) -> InventorySnapshot | None:
    return (
        await session.execute(
            select(InventorySnapshot)
            .filter_by(node_id=node_id, product_id=product_id)
            .order_by(InventorySnapshot.as_of.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def get_latest_recommendation(
    session: AsyncSession, node_id: int, product_id: int
) -> Recommendation | None:
    return (
        await session.execute(
            select(Recommendation)
            .filter_by(node_id=node_id, product_id=product_id)
            .order_by(Recommendation.created_at.desc(), Recommendation.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def get_supplier_terms(
    session: AsyncSession, supplier_id: int, product_id: int
) -> Row[Supplier, SupplierProduct]:
    """The (supplier, terms) pair; raises if the supplier does not carry the product."""
    return (
        await session.execute(
            select(Supplier, SupplierProduct)
            .join(SupplierProduct, SupplierProduct.supplier_id == Supplier.id)
            .where(Supplier.id == supplier_id, SupplierProduct.product_id == product_id)
        )
    ).one()


async def list_forecast_qtys_after(
    session: AsyncSession, node_id: int, product_id: int, day: date
) -> Sequence[Any]:
    return (
        (
            await session.execute(
                select(DemandForecast.qty)
                .filter_by(node_id=node_id, product_id=product_id)
                .where(DemandForecast.day > day)
                .order_by(DemandForecast.day)
            )
        )
        .scalars()
        .all()
    )


async def list_sales_qtys(
    session: AsyncSession, node_id: int, product_id: int, start: date, end: date
) -> Sequence[Any]:
    """Daily sales qty for start <= day < end, oldest first."""
    return (
        (
            await session.execute(
                select(SalesHistory.qty)
                .filter_by(node_id=node_id, product_id=product_id)
                .where(SalesHistory.day >= start, SalesHistory.day < end)
                .order_by(SalesHistory.day)
            )
        )
        .scalars()
        .all()
    )


async def list_open_inbound(
    session: AsyncSession, node_id: int, product_id: int
) -> Sequence[Row[str, int, date]]:
    """(po_number, open qty, eta) for open POs carrying the product."""
    return (
        await session.execute(
            select(PurchaseOrder.po_number, PoLine.qty_ordered - PoLine.qty_received, PoLine.eta)
            .join(PurchaseOrder)
            .where(
                PurchaseOrder.node_id == node_id,
                PurchaseOrder.status.in_(OPEN_PO_STATUSES),
                PoLine.product_id == product_id,
            )
            .order_by(PurchaseOrder.po_number)
        )
    ).all()


async def get_budget(
    session: AsyncSession, node_id: int, category: Any, period: str
) -> Budget | None:
    return (
        await session.execute(
            select(Budget).filter_by(node_id=node_id, category=category, period=period)
        )
    ).scalar_one_or_none()


async def get_storage_zone(session: AsyncSession, node_id: int, zone: Any) -> StorageZone | None:
    return (
        await session.execute(select(StorageZone).filter_by(node_id=node_id, zone=zone))
    ).scalar_one_or_none()


async def list_zone_other_snapshots(
    session: AsyncSession, node_id: int, zone: Any, product_id: int
) -> Sequence[Row[InventorySnapshot, Decimal]]:
    """(snapshot, unit_volume) of every other product in the zone, oldest snapshot first."""
    return (
        await session.execute(
            select(InventorySnapshot, Product.unit_volume)
            .join(Product, InventorySnapshot.product_id == Product.id)
            .where(
                InventorySnapshot.node_id == node_id,
                Product.storage_zone == zone,
                Product.id != product_id,
            )
            .order_by(InventorySnapshot.as_of)
        )
    ).all()


async def list_forecast_totals(
    session: AsyncSession, node_id: int, product_ids: list[int], after: date, until: date
) -> Sequence[Row[int, Decimal]]:
    """(product_id, summed qty) for after < day <= until."""
    return (
        await session.execute(
            select(DemandForecast.product_id, func.sum(DemandForecast.qty))
            .where(
                DemandForecast.node_id == node_id,
                DemandForecast.product_id.in_(product_ids),
                DemandForecast.day > after,
                DemandForecast.day <= until,
            )
            .group_by(DemandForecast.product_id)
        )
    ).all()


async def list_open_po_qtys(
    session: AsyncSession, node_id: int, product_ids: list[int], start: date, end: date
) -> Sequence[Row[int, int]]:
    """(product_id, open qty) of open PO lines with start <= eta <= end."""
    return (
        await session.execute(
            select(PoLine.product_id, PoLine.qty_ordered - PoLine.qty_received)
            .join(PurchaseOrder)
            .where(
                PurchaseOrder.node_id == node_id,
                PurchaseOrder.status.in_(OPEN_PO_STATUSES),
                PoLine.product_id.in_(product_ids),
                PoLine.eta >= start,
                PoLine.eta <= end,
            )
        )
    ).all()
