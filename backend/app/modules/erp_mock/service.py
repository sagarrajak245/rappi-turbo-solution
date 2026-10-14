"""Mock ERP service. Every mutating call goes through the request ledger so a retried
idempotency key can never create a second PO or repeat a transition."""

import hashlib
import json
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, ErpTimeout, NotFound
from app.modules.erp_mock import behaviours
from app.modules.erp_mock.models import ErpBehaviour, ErpPurchaseOrder, ErpRequest
from app.modules.erp_mock.schemas import ErpDraftRequest, ErpPurchaseOrderOut
from app.shared.enums import ErpPoStatus
from app.shared.money import to_inr


def _canonical(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(to_inr(value))
    if isinstance(value, dict):
        return {k: _canonical(v) for k, v in value.items()}
    return value


def request_hash(payload: dict[str, Any]) -> str:
    """sha256 of canonical JSON; 240 and 240.00 hash the same."""
    body = json.dumps(
        _canonical(payload), sort_keys=True, separators=(",", ":"), default=lambda o: o.isoformat()
    )
    return hashlib.sha256(body.encode()).hexdigest()


async def _ledger(session: AsyncSession, key: str, op: str) -> ErpRequest | None:
    stmt = select(ErpRequest).where(ErpRequest.idempotency_key == key, ErpRequest.operation == op)
    return (await session.execute(stmt)).scalar_one_or_none()


def _replay(row: ErpRequest, digest: str) -> ErpPurchaseOrderOut:
    if row.request_hash != digest:
        raise Conflict(
            "Idempotency key was already used with a different request",
            {"idempotency_key": row.idempotency_key, "operation": row.operation},
        )
    return ErpPurchaseOrderOut.model_validate(row.response)


def _record(
    session: AsyncSession, key: str, op: str, digest: str, po: ErpPurchaseOrder, now: datetime
) -> ErpPurchaseOrderOut:
    out = ErpPurchaseOrderOut.model_validate(po)
    session.add(
        ErpRequest(
            idempotency_key=key,
            operation=op,
            request_hash=digest,
            response=out.model_dump(mode="json"),
            created_at=now,
        )
    )
    return out


async def _behaviour(session: AsyncSession, node_code: str, sku: str) -> ErpBehaviour | None:
    stmt = select(ErpBehaviour).where(ErpBehaviour.node_code == node_code, ErpBehaviour.sku == sku)
    return (await session.execute(stmt)).scalar_one_or_none()


async def create_draft(
    session: AsyncSession, key: str, req: ErpDraftRequest, now: datetime
) -> ErpPurchaseOrderOut:
    digest = request_hash({**req.model_dump(), "op": "create"})
    if (row := await _ledger(session, key, "create")) is not None:
        return _replay(row, digest)

    po = ErpPurchaseOrder(
        erp_number=f"ERP-{uuid.uuid4().hex[:10].upper()}",
        idempotency_key=key,
        node_code=req.node_code,
        sku=req.sku,
        supplier_code=req.supplier_code,
        qty=req.qty,
        case_pack=req.case_pack,
        unit_price_inr=to_inr(req.unit_price_inr),
        total_inr=to_inr(req.unit_price_inr * req.qty),
        eta=req.eta,
        status=ErpPoStatus.DRAFT,
        created_at=now,
        updated_at=now,
    )
    behaviour = await _behaviour(session, req.node_code, req.sku)  # before add: avoids autoflush
    session.add(po)
    timeout = behaviours.apply("create", po, behaviour)
    out = _record(session, key, "create", digest, po, now)
    try:
        await session.commit()
    except IntegrityError:
        # A concurrent request with the same key won the race: return its result.
        await session.rollback()
        row = await _ledger(session, key, "create")
        if row is None:
            raise
        return _replay(row, digest)
    if timeout:
        # The PO and ledger row are committed; the client just never sees the answer.
        raise ErpTimeout("ERP timed out after creating the purchase order", {"key": key})
    return out


async def get(session: AsyncSession, erp_number: str) -> ErpPurchaseOrderOut:
    return ErpPurchaseOrderOut.model_validate(await _load(session, erp_number))


async def _load(session: AsyncSession, erp_number: str) -> ErpPurchaseOrder:
    stmt = select(ErpPurchaseOrder).where(ErpPurchaseOrder.erp_number == erp_number)
    po = (await session.execute(stmt)).scalar_one_or_none()
    if po is None:
        raise NotFound(f"Purchase order {erp_number} not found", {"erp_number": erp_number})
    return po


async def _transition(
    session: AsyncSession,
    erp_number: str,
    key: str,
    op: str,
    allowed_from: set[ErpPoStatus],
    target: ErpPoStatus,
    now: datetime,
) -> ErpPurchaseOrderOut:
    digest = request_hash({"erp_number": erp_number, "op": op})
    if (row := await _ledger(session, key, op)) is not None:
        return _replay(row, digest)

    po = await _load(session, erp_number)
    if po.status not in allowed_from:
        raise Conflict(
            f"Cannot {op} a purchase order in status {po.status.value}",
            {"erp_number": erp_number, "status": po.status.value},
        )
    po.status = target
    po.updated_at = now
    behaviours.apply(op, po, await _behaviour(session, po.node_code, po.sku))
    out = _record(session, key, op, digest, po, now)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        row = await _ledger(session, key, op)
        if row is None:
            raise
        return _replay(row, digest)
    return out


async def submit(
    session: AsyncSession, erp_number: str, key: str, now: datetime
) -> ErpPurchaseOrderOut:
    return await _transition(
        session, erp_number, key, "submit", {ErpPoStatus.DRAFT}, ErpPoStatus.SUBMITTED, now
    )


async def cancel(
    session: AsyncSession, erp_number: str, key: str, now: datetime
) -> ErpPurchaseOrderOut:
    return await _transition(
        session,
        erp_number,
        key,
        "cancel",
        {ErpPoStatus.DRAFT, ErpPoStatus.SUBMITTED},
        ErpPoStatus.CANCELLED,
        now,
    )
