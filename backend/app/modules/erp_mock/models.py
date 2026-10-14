"""Tables owned by the mock ERP. It is a separate system, so it stores codes, not our FKs."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, CheckConstraint, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UTCDateTime
from app.core.db_types import Money, str_enum
from app.shared.enums import ErpPoStatus


class ErpPurchaseOrder(Base):
    __tablename__ = "erp_purchase_orders"
    __table_args__ = (CheckConstraint("qty > 0", name="qty_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    erp_number: Mapped[str] = mapped_column(String(40), unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True)  # the create key
    node_code: Mapped[str] = mapped_column(String(20))
    sku: Mapped[str] = mapped_column(String(40))
    supplier_code: Mapped[str] = mapped_column(String(20))
    qty: Mapped[int]
    case_pack: Mapped[int]
    unit_price_inr: Mapped[Decimal] = mapped_column(Money)
    total_inr: Mapped[Decimal] = mapped_column(Money)
    eta: Mapped[date]
    status: Mapped[ErpPoStatus] = mapped_column(str_enum(ErpPoStatus))
    mock_behaviour: Mapped[str | None] = mapped_column(String(40))
    status_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime())


class ErpRequest(Base):
    """Idempotency ledger: a replayed (key, operation) returns the stored response."""

    __tablename__ = "erp_requests"
    __table_args__ = (UniqueConstraint("idempotency_key", "operation"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(100))
    operation: Mapped[str] = mapped_column(String(20))  # create | submit | cancel
    request_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())


class ErpBehaviour(Base):
    """Seeded surprise for one SKU at one node (feedback-loop cases F1-F6)."""

    __tablename__ = "erp_behaviours"
    __table_args__ = (UniqueConstraint("node_code", "sku"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    node_code: Mapped[str] = mapped_column(String(20))
    sku: Mapped[str] = mapped_column(String(40))
    behaviour: Mapped[str] = mapped_column(String(40))
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    times_fired: Mapped[int] = mapped_column(default=0)
