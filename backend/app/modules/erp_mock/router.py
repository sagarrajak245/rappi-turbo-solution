"""HTTP surface of the mock ERP. Mounted under /mock-erp, as a stand-in for the real system."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.modules.erp_mock import service
from app.modules.erp_mock.schemas import ErpDraftRequest, ErpPurchaseOrderOut

router = APIRouter(prefix="/mock-erp/purchase-orders", tags=["mock-erp"])

Session = Annotated[AsyncSession, Depends(get_session)]
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=100)]


@router.post("", status_code=201, response_model=ErpPurchaseOrderOut)
async def create_purchase_order(
    body: ErpDraftRequest, session: Session, key: IdempotencyKey
) -> ErpPurchaseOrderOut:
    return await service.create_draft(session, key, body, datetime.now(UTC))


@router.get("/{erp_number}", response_model=ErpPurchaseOrderOut)
async def get_purchase_order(erp_number: str, session: Session) -> ErpPurchaseOrderOut:
    return await service.get(session, erp_number)


@router.post("/{erp_number}/submit", response_model=ErpPurchaseOrderOut)
async def submit_purchase_order(
    erp_number: str, session: Session, key: IdempotencyKey
) -> ErpPurchaseOrderOut:
    return await service.submit(session, erp_number, key, datetime.now(UTC))


@router.post("/{erp_number}/cancel", response_model=ErpPurchaseOrderOut)
async def cancel_purchase_order(
    erp_number: str, session: Session, key: IdempotencyKey
) -> ErpPurchaseOrderOut:
    return await service.cancel(session, erp_number, key, datetime.now(UTC))
