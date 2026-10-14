"""The buyer's screens: inbox, purchase orders and the home dashboard. Read only."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent import service as agent
from app.modules.agent.schemas import HumanAction, RunSummary
from app.modules.auth.schemas import UserOut
from app.modules.workspace import repository as repo
from app.modules.workspace.schemas import (
    BudgetBar,
    DashboardSummary,
    InboxRow,
    PurchaseOrderRow,
    StorageBar,
)
from app.shared.enums import RunStatus

# Only a run awaiting approval accepts a decision; these failed after execution and need a person
# to check the ERP, outside the approve flow.
NEEDS_ATTENTION = (RunStatus.NEEDS_HUMAN, RunStatus.ESCALATED)
_JUDGED = {HumanAction.APPROVE, HumanAction.MODIFY, HumanAction.REJECT}


async def inbox(
    session: AsyncSession, node: str | None, status: RunStatus | None
) -> list[InboxRow]:
    latest: dict[tuple[str, str], RunSummary] = {}
    for row in await repo.list_latest_runs(session):
        latest.setdefault((row.sku, row.node_code), agent.summarize(row))
    rows = []
    for rec, product, n in await repo.list_recommendations(session, node):
        run = latest.get((product.sku, n.code))
        if status is not None and (run is None or run.status is not status):
            continue
        rows.append(
            InboxRow(
                recommendation_id=rec.id,
                sku=product.sku,
                product_name=product.name,
                category=product.category,
                node=n.code,
                node_name=n.name,
                rec_qty=rec.qty,
                created_at=rec.created_at,
                run=run,
            )
        )
    return rows


async def purchase_orders(session: AsyncSession) -> list[PurchaseOrderRow]:
    return [
        PurchaseOrderRow(
            erp_number=po.erp_number,
            run_id=run.id,
            sku=po.sku,
            node=po.node_code,
            supplier_code=po.supplier_code,
            qty=po.qty,
            unit_price_inr=po.unit_price_inr,
            total_inr=po.total_inr,
            eta=po.eta,
            status=po.status,
            execution_status=(run.execution or {})["status"],
            decided_by=run.decided_by,
            created_at=po.created_at,
        )
        for run, po in await repo.list_executed_orders(session)
    ]


def _agreement_pct(actions: dict[str, int]) -> float | None:
    judged = sum(n for a, n in actions.items() if a in _JUDGED)
    if not judged:
        return None
    return round(100 * actions.get(HumanAction.APPROVE, 0) / judged, 1)


async def dashboard(session: AsyncSession, user: UserOut, now: datetime) -> DashboardSummary:
    nodes = await repo.list_nodes_in_city(session, user.branch)
    ids = [n.id for n in nodes]
    code = {n.id: n.code for n in nodes}

    budgets = {
        node_id: (used, limit)
        for node_id, used, limit in await repo.budget_totals(session, ids, now.strftime("%Y-%m"))
    }
    capacity = dict(await repo.storage_capacity(session, ids))
    used = await repo.used_volume(session, ids)
    waiting = (RunStatus.AWAITING_APPROVAL,)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return DashboardSummary(
        pending_approvals=await repo.count_runs(session, waiting),
        needs_attention=await repo.count_runs(session, NEEDS_ATTENTION),
        committed_today_inr=await repo.committed_since(session, list(code.values()), start_of_day),
        agreement_pct=_agreement_pct(await repo.decision_action_counts(session)),
        budgets=[
            BudgetBar(node=code[i], used_inr=budgets[i][0], limit_inr=budgets[i][1])
            for i in ids
            if i in budgets
        ],
        storage=[
            StorageBar(node=code[i], used=used.get(i, Decimal(0)), capacity=capacity[i])
            for i in ids
            if i in capacity
        ],
        needs_decision=[
            agent.summarize(r) for r in await repo.list_runs_by_status(session, waiting, limit=5)
        ],
    )
