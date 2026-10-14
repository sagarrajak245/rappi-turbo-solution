"""Read models for the buyer's screens. Shapes only; nothing here is written back."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.modules.agent.schemas import RunSummary
from app.modules.execution.schemas import ExecutionStatus
from app.shared.enums import ErpPoStatus


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class InboxRow(_Frozen):
    """One upstream recommendation with the latest agent run for its SKU x node, if any."""

    recommendation_id: int
    sku: str
    product_name: str
    category: str
    node: str
    node_name: str
    rec_qty: int
    created_at: datetime
    run: RunSummary | None = None


class PurchaseOrderRow(_Frozen):
    erp_number: str
    run_id: str
    sku: str
    node: str
    supplier_code: str
    qty: int
    unit_price_inr: Decimal
    total_inr: Decimal
    eta: date
    status: ErpPoStatus  # what the ERP holds now
    execution_status: ExecutionStatus  # what the agent verified after placing it
    decided_by: str | None
    created_at: datetime


class BudgetBar(_Frozen):
    node: str
    used_inr: Decimal
    limit_inr: Decimal


class StorageBar(_Frozen):
    node: str
    used: Decimal  # volume units on hand now
    capacity: Decimal


class DashboardSummary(_Frozen):
    pending_approvals: int
    needs_attention: int  # executed runs that failed and need a person to check the ERP
    committed_today_inr: Decimal
    agreement_pct: float | None  # approved as proposed / decided; None before any decision
    budgets: list[BudgetBar]
    storage: list[StorageBar]
    needs_decision: list[RunSummary]
