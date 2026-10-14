"""DTOs of the execution loop: an approved order in, an observed outcome out (KB D21)."""

from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.modules.planning.schemas import CalcResult
from app.shared.enums import ErpPoStatus, FlagCode


class Severity(StrEnum):
    MINOR = "minor"  # accept with a note
    MATERIAL = "material"  # cancel the draft, re-plan, back to the human
    UNFIXABLE = "unfixable"  # cancel the draft, escalate


class ExecutionStatus(StrEnum):
    COMPLETED = "completed"
    REPLAN_REQUIRED = "replan_required"
    ESCALATED = "escalated"
    NEEDS_HUMAN = "needs_human"  # failure after submit: cancel/amend needs approval


class ApprovedOrder(BaseModel):
    """What the human approved. proposal_id keys every ERP call, so re-runs are idempotent."""

    model_config = ConfigDict(frozen=True)

    proposal_id: str = Field(min_length=1, max_length=80)
    node_code: str
    sku: str
    supplier_code: str
    qty: int = Field(gt=0)
    case_pack: int = Field(gt=0)
    unit_price_inr: Decimal
    eta: date
    replans_done: int = Field(default=0, ge=0)


class Deviation(BaseModel):
    model_config = ConfigDict(frozen=True)

    field: str
    expected: str
    actual: str
    severity: Severity


class ExecutionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: ExecutionStatus
    erp_number: str | None
    final_status: ErpPoStatus | None
    deviations: tuple[Deviation, ...] = ()
    flags: tuple[FlagCode, ...] = ()
    notes: tuple[str, ...] = ()
    replan: CalcResult | None = None  # new baseline when a material change needs re-approval
