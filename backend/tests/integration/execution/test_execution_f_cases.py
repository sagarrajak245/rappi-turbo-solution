"""ERP execution loop against the seeded mock ERP: clean path and surprises F1-F6 (KB §7.4)."""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.erp_mock.models import ErpPurchaseOrder
from app.modules.execution import service
from app.modules.execution.schemas import ApprovedOrder, ExecutionResult, ExecutionStatus
from app.scenarios.inputs import planning_input_from_case
from app.scenarios.scenario1 import CASES_BY_ID
from app.seed.scenario1 import seed_scenario1
from app.shared.enums import ErpPoStatus, FlagCode, Verdict

TODAY = date(2026, 10, 14)
NOW = datetime(2026, 10, 14, 6, 0, tzinfo=UTC)


def order_for(case_id: str, replans: int = 0) -> ApprovedOrder:
    case = CASES_BY_ID[case_id]
    inp = planning_input_from_case(case, TODAY, NOW)
    return ApprovedOrder(
        proposal_id=f"prop-{case_id}",
        node_code=inp.node,
        sku=inp.sku,
        supplier_code=inp.supplier_code,
        qty=case.expected.qty or 0,
        case_pack=inp.case_pack,
        unit_price_inr=inp.unit_cost_inr,
        eta=TODAY + timedelta(days=inp.lead_time_days),
        replans_done=replans,
    )


async def run(session: AsyncSession, case_id: str, replans: int = 0) -> ExecutionResult:
    await seed_scenario1(session, today=TODAY, now=NOW)
    return await service.execute(session, order_for(case_id, replans), TODAY, NOW, get_settings())


async def po_count(session: AsyncSession) -> int:
    return (await session.execute(select(func.count()).select_from(ErpPurchaseOrder))).scalar_one()


async def test_clean_order_is_drafted_verified_submitted(session: AsyncSession) -> None:
    result = await run(session, "C1")
    assert result.status is ExecutionStatus.COMPLETED
    assert result.final_status is ErpPoStatus.SUBMITTED
    assert result.deviations == ()


async def test_rerun_with_same_proposal_creates_no_duplicate(session: AsyncSession) -> None:
    first = await run(session, "C1")
    again = await service.execute(session, order_for("C1"), TODAY, NOW, get_settings())
    assert again.erp_number == first.erp_number
    assert await po_count(session) == 1


async def test_f1_price_rise_cancels_draft_and_replans_to_210(session: AsyncSession) -> None:
    result = await run(session, "F1")
    assert result.status is ExecutionStatus.REPLAN_REQUIRED
    assert result.final_status is ErpPoStatus.CANCELLED
    assert result.replan is not None
    assert (result.replan.verdict, result.replan.qty) == (Verdict.MODIFY, 210)


async def test_f2_case_pack_change_replans_to_144(session: AsyncSession) -> None:
    result = await run(session, "F2")
    assert result.status is ExecutionStatus.REPLAN_REQUIRED
    assert result.replan is not None and result.replan.qty == 144


async def test_material_deviation_after_max_replans_escalates(session: AsyncSession) -> None:
    result = await run(session, "F1", replans=1)
    assert result.status is ExecutionStatus.ESCALATED
    assert result.final_status is ErpPoStatus.CANCELLED


async def test_f3_timeout_retries_same_key_without_duplicate(session: AsyncSession) -> None:
    result = await run(session, "F3")
    assert result.status is ExecutionStatus.COMPLETED
    assert await po_count(session) == 1
    assert any("timed out" in n for n in result.notes)


async def test_f4_rejection_escalates(session: AsyncSession) -> None:
    result = await run(session, "F4")
    assert result.status is ExecutionStatus.ESCALATED
    assert result.final_status is ErpPoStatus.REJECTED
    assert any("credit hold" in n for n in result.notes)


async def test_f5_late_eta_is_accepted_with_stockout_flag(session: AsyncSession) -> None:
    result = await run(session, "F5")
    assert result.status is ExecutionStatus.COMPLETED
    assert FlagCode.STOCKOUT_BEFORE_ARRIVAL in result.flags
    assert [d.field for d in result.deviations] == ["eta"]


async def test_f6_mismatch_after_submit_needs_human_and_is_not_cancelled(
    session: AsyncSession,
) -> None:
    result = await run(session, "F6")
    assert result.status is ExecutionStatus.NEEDS_HUMAN
    assert result.final_status is ErpPoStatus.SUBMITTED  # never cancelled silently
    assert [(d.field, d.actual) for d in result.deviations] == [("qty", "240")]


async def test_rerun_after_submit_mismatch_never_cancels_the_submitted_po(
    session: AsyncSession,
) -> None:
    # A client retry (e.g. lost response) must not let the draft handlers cancel a submitted PO.
    first = await run(session, "F6")
    again = await service.execute(session, order_for("F6"), TODAY, NOW, get_settings())
    assert again.erp_number == first.erp_number
    assert again.status is ExecutionStatus.NEEDS_HUMAN
    assert again.final_status is ErpPoStatus.SUBMITTED


async def test_replanned_order_reuses_proposal_id_as_a_new_erp_request(
    session: AsyncSession,
) -> None:
    first = await run(session, "F1")
    assert first.replan is not None
    replanned = order_for("F1", replans=1).model_copy(update={"qty": first.replan.qty})
    second = await service.execute(session, replanned, TODAY, NOW, get_settings())
    assert second.erp_number != first.erp_number
    assert await po_count(session) == 2
