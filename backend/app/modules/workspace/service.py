"""The buyer's screens: inbox, purchase orders and the home dashboard. Read only."""

from collections.abc import Sequence
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

# Runs that wait on a person: approve/modify/reject, or acknowledge an escalation.
NEEDS_DECISION = (RunStatus.AWAITING_APPROVAL, RunStatus.NEEDS_HUMAN, RunStatus.ESCALATED)
_JUDGED = {HumanAction.APPROVE, HumanAction.MODIFY, HumanAction.REJECT}


async def inbox(
    session: AsyncSession, node: str | None, status: RunStatus | None
) -> list[InboxRow]:
    latest: dict[tuple[str, str], RunSummary] = {}
    for row in await repo.list_runs_newest_first(session):
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


def _agreement_pct(decisions: Sequence[dict[str, object]]) -> float | None:
    judged = [d["action"] for d in decisions if d.get("action") in _JUDGED]
    if not judged:
        return None
    return round(100 * judged.count(HumanAction.APPROVE) / len(judged), 1)


async def dashboard(session: AsyncSession, user: UserOut, now: datetime) -> DashboardSummary:
    nodes = await repo.list_nodes_in_city(session, user.branch)
    ids = [n.id for n in nodes]
    code = {n.id: n.code for n in nodes}

    budgets = {
        node_id: (used, limit)
        for node_id, used, limit in await repo.budget_totals(session, ids, now.strftime("%Y-%m"))
    }
    capacity = dict(await repo.storage_capacity(session, ids))
    on_hand: dict[tuple[int, int], Decimal] = {}
    for snap, volume in await repo.list_snapshots_with_volume(session, ids):
        on_hand[(snap.node_id, snap.product_id)] = max(0, snap.on_hand) * volume
    used: dict[int, Decimal] = {}
    for (node_id, _), vol in on_hand.items():
        used[node_id] = used.get(node_id, Decimal(0)) + vol

    waiting = await repo.list_runs_by_status(session, NEEDS_DECISION)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return DashboardSummary(
        pending_approvals=len(waiting),
        committed_today_inr=await repo.committed_since(session, list(code.values()), start_of_day),
        agreement_pct=_agreement_pct(await repo.list_decisions(session)),
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
        needs_decision=[agent.summarize(r) for r in waiting[:5]],
    )
