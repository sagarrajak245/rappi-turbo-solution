"""Wire schemas of the mock ERP."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.shared.enums import ErpPoStatus


class ErpDraftRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    node_code: str
    sku: str
    supplier_code: str
    qty: int = Field(gt=0)
    case_pack: int = Field(gt=0)
    unit_price_inr: Decimal
    eta: date


class ErpPurchaseOrderOut(BaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)

    erp_number: str
    idempotency_key: str
    node_code: str
    sku: str
    supplier_code: str
    qty: int
    case_pack: int
    unit_price_inr: Decimal
    total_inr: Decimal
    eta: date
    status: ErpPoStatus
    mock_behaviour: str | None
    status_reason: str | None
    created_at: datetime
    updated_at: datetime
