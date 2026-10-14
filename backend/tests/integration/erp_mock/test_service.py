"""Mock ERP service: idempotency ledger and status machine."""

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import Conflict, NotFound
from app.modules.erp_mock import service
from app.modules.erp_mock.models import ErpPurchaseOrder
from app.modules.erp_mock.schemas import ErpDraftRequest
from app.shared.enums import ErpPoStatus

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)


def make_req(**over: object) -> ErpDraftRequest:
    data: dict[str, object] = {
        "node_code": "N1",
        "sku": "SKU1",
        "supplier_code": "SUP1",
        "qty": 240,
        "case_pack": 24,
        "unit_price_inr": Decimal("10"),
        "eta": date(2026, 10, 20),
    }
    data.update(over)
    return ErpDraftRequest.model_validate(data)


async def count_pos(session: AsyncSession) -> int:
    return (await session.execute(select(func.count()).select_from(ErpPurchaseOrder))).scalar_one()


async def test_create_same_key_twice_returns_one_po(session: AsyncSession) -> None:
    a = await service.create_draft(session, "k1", make_req(), NOW)
    b = await service.create_draft(session, "k1", make_req(), NOW)
    assert a.erp_number == b.erp_number
    assert a.status is ErpPoStatus.draft
    assert a.total_inr == Decimal("2400.00")
    assert a.erp_number.startswith("ERP-")
    assert await count_pos(session) == 1


async def test_decimal_representation_does_not_change_hash(session: AsyncSession) -> None:
    a = await service.create_draft(session, "k1", make_req(unit_price_inr=Decimal("10")), NOW)
    b = await service.create_draft(session, "k1", make_req(unit_price_inr=Decimal("10.00")), NOW)
    assert a.erp_number == b.erp_number


async def test_same_key_different_payload_conflicts(session: AsyncSession) -> None:
    await service.create_draft(session, "k1", make_req(), NOW)
    with pytest.raises(Conflict):
        await service.create_draft(session, "k1", make_req(qty=480), NOW)


async def test_replayed_submit_returns_stored_response(session: AsyncSession) -> None:
    po = await service.create_draft(session, "c1", make_req(), NOW)
    first = await service.submit(session, po.erp_number, "s1", NOW)
    again = await service.submit(session, po.erp_number, "s1", NOW)
    assert first.status is ErpPoStatus.submitted
    assert again.status is ErpPoStatus.submitted
    assert again.updated_at == first.updated_at


async def test_concurrent_create_same_key_yields_one_po(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async def go() -> str:
        async with sessionmaker() as s:
            return (await service.create_draft(s, "k1", make_req(), NOW)).erp_number

    results = await asyncio.gather(go(), go())
    assert results[0] == results[1]
    async with sessionmaker() as s:
        assert await count_pos(s) == 1


async def test_create_recovers_when_po_inserted_by_racer(
    session: AsyncSession, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    async with sessionmaker() as other:
        existing = await service.create_draft(other, "k1", make_req(), NOW)
    again = await service.create_draft(session, "k1", make_req(), NOW)
    assert again.erp_number == existing.erp_number


async def test_draft_submit_cancel_path(session: AsyncSession) -> None:
    po = await service.create_draft(session, "c1", make_req(), NOW)
    sub = await service.submit(session, po.erp_number, "s1", NOW)
    assert sub.status is ErpPoStatus.submitted
    can = await service.cancel(session, po.erp_number, "x1", NOW)
    assert can.status is ErpPoStatus.cancelled


async def test_second_submit_with_new_key_conflicts(session: AsyncSession) -> None:
    po = await service.create_draft(session, "c1", make_req(), NOW)
    await service.submit(session, po.erp_number, "s1", NOW)
    with pytest.raises(Conflict):
        await service.submit(session, po.erp_number, "s2", NOW)


async def test_cancel_after_rejected_conflicts(session: AsyncSession) -> None:
    po = await service.create_draft(session, "c1", make_req(), NOW)
    po.status = ErpPoStatus.rejected
    await session.commit()
    with pytest.raises(Conflict):
        await service.cancel(session, po.erp_number, "x1", NOW)


async def test_get_unknown_is_not_found(session: AsyncSession) -> None:
    with pytest.raises(NotFound):
        await service.get(session, "ERP-NOPE")
