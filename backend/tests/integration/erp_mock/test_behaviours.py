"""Mock ERP surprise behaviours F1-F6."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import ErpTimeout
from app.modules.erp_mock import service
from app.modules.erp_mock.models import ErpBehaviour, ErpPurchaseOrder
from app.modules.erp_mock.schemas import ErpDraftRequest
from app.shared.enums import ErpPoStatus

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)


def make_req() -> ErpDraftRequest:
    return ErpDraftRequest(
        node_code="N1",
        sku="SKU1",
        supplier_code="SUP1",
        qty=240,
        case_pack=24,
        unit_price_inr=Decimal("100"),
        eta=date(2026, 10, 20),
    )


async def seed(session: AsyncSession, behaviour: str, params: dict[str, Any]) -> None:
    session.add(ErpBehaviour(node_code="N1", sku="SKU1", behaviour=behaviour, params=params))
    await session.commit()


async def fired(session: AsyncSession) -> int:
    stmt = select(ErpBehaviour.times_fired).where(ErpBehaviour.sku == "SKU1")
    return (await session.execute(stmt)).scalar_one()


async def test_price_change_at_create(session: AsyncSession) -> None:
    await seed(session, "price_change", {"pct": "8"})
    po = await service.create_draft(session, "k", make_req(), NOW)
    assert po.unit_price_inr == Decimal("108.00")
    assert po.total_inr == Decimal("25920.00")
    assert po.mock_behaviour == "price_change"
    assert po.status_reason
    assert await fired(session) == 1


async def test_case_pack_change_at_create(session: AsyncSession) -> None:
    await seed(session, "case_pack_change", {"case_pack": 12})
    po = await service.create_draft(session, "k", make_req(), NOW)
    assert po.case_pack == 12
    assert po.qty == 240
    assert po.mock_behaviour == "case_pack_change"
    assert await fired(session) == 1


async def test_case_pack_change_notes_non_multiple(session: AsyncSession) -> None:
    await seed(session, "case_pack_change", {"case_pack": 100})
    po = await service.create_draft(session, "k", make_req(), NOW)
    assert po.status_reason is not None
    assert "not a multiple" in po.status_reason


async def test_late_eta_at_create(session: AsyncSession) -> None:
    await seed(session, "late_eta", {"days": 3})
    po = await service.create_draft(session, "k", make_req(), NOW)
    assert po.eta == date(2026, 10, 23)
    assert po.mock_behaviour == "late_eta"


async def test_reject_on_submit(session: AsyncSession) -> None:
    await seed(session, "reject_on_submit", {"reason": "supplier out of stock"})
    po = await service.create_draft(session, "k", make_req(), NOW)
    assert po.status is ErpPoStatus.DRAFT
    out = await service.submit(session, po.erp_number, "s", NOW)
    assert out.status is ErpPoStatus.REJECTED
    assert out.status_reason == "supplier out of stock"
    assert out.mock_behaviour == "reject_on_submit"
    with pytest.raises(Exception, match="rejected"):
        await service.cancel(session, po.erp_number, "x", NOW)


async def test_mismatch_after_submit(session: AsyncSession) -> None:
    await seed(session, "mismatch_after_submit", {"qty": 200})
    po = await service.create_draft(session, "k", make_req(), NOW)
    out = await service.submit(session, po.erp_number, "s", NOW)
    assert out.status is ErpPoStatus.SUBMITTED
    assert out.qty == 200
    assert out.total_inr == Decimal("20000.00")
    assert out.status_reason
    assert out.mock_behaviour == "mismatch_after_submit"


async def test_timeout_after_create_then_retry_returns_same_po(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker() as s:
        await seed(s, "timeout_after_create", {})
    async with sessionmaker() as s:
        with pytest.raises(ErpTimeout):
            await service.create_draft(s, "k", make_req(), NOW)
    async with sessionmaker() as s:
        po = await service.create_draft(s, "k", make_req(), NOW)
        count = (await s.execute(select(func.count()).select_from(ErpPurchaseOrder))).scalar_one()
        assert count == 1
        assert po.erp_number.startswith("ERP-")
        assert await fired(s) == 1
        # a different key is not affected any more: the behaviour only fires once
        other = await service.create_draft(s, "k2", make_req(), NOW)
        assert other.mock_behaviour is None
