from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, UTCDateTime
from app.core.db_types import Money, str_enum
from app.shared.enums import PoStatus


class PurchaseOrder(Base):
    """A purchase order in our own records. Open ones count as inbound stock."""

    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    po_number: Mapped[str] = mapped_column(String(40), unique=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"))
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"))
    status: Mapped[PoStatus] = mapped_column(str_enum(PoStatus))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
    erp_number: Mapped[str | None] = mapped_column(String(40))

    lines: Mapped[list["PoLine"]] = relationship(back_populates="po", cascade="all, delete-orphan")


class PoLine(Base):
    __tablename__ = "po_lines"
    __table_args__ = (
        CheckConstraint("qty_ordered > 0", name="qty_ordered_positive"),
        CheckConstraint("qty_received >= 0", name="qty_received_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    po_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    qty_ordered: Mapped[int]
    qty_confirmed: Mapped[int | None]  # set when the supplier confirms (Scenario 2)
    qty_received: Mapped[int] = mapped_column(default=0)
    unit_cost_inr: Mapped[Decimal] = mapped_column(Money)
    eta: Mapped[date]

    po: Mapped[PurchaseOrder] = relationship(back_populates="lines")
