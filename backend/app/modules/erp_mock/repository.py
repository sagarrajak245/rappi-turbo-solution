"""Queries of the mock ERP. Rows in, rows out: decisions stay in service.py."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.erp_mock.models import ErpBehaviour, ErpPurchaseOrder, ErpRequest


async def get_request(session: AsyncSession, key: str, op: str) -> ErpRequest | None:
    stmt = select(ErpRequest).where(ErpRequest.idempotency_key == key, ErpRequest.operation == op)
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_behaviour(session: AsyncSession, node_code: str, sku: str) -> ErpBehaviour | None:
    stmt = select(ErpBehaviour).where(ErpBehaviour.node_code == node_code, ErpBehaviour.sku == sku)
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_po(session: AsyncSession, erp_number: str) -> ErpPurchaseOrder | None:
    stmt = select(ErpPurchaseOrder).where(ErpPurchaseOrder.erp_number == erp_number)
    return (await session.execute(stmt)).scalar_one_or_none()
