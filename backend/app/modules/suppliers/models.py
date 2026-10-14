from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.db_types import Money


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(default=True)
    reliability: Mapped[Decimal] = mapped_column(Numeric(4, 3), default=Decimal("1"))  # 0..1
    # Free text from the supplier. Treated as data only, never as instructions (Q7).
    notes: Mapped[str | None] = mapped_column(Text)


class SupplierProduct(Base):
    """Commercial terms for one product from one supplier."""

    __tablename__ = "supplier_products"
    __table_args__ = (
        UniqueConstraint("supplier_id", "product_id"),
        CheckConstraint("unit_cost_inr >= 0", name="unit_cost_non_negative"),
        CheckConstraint("moq >= 0", name="moq_non_negative"),
        CheckConstraint("case_pack > 0", name="case_pack_positive"),
        CheckConstraint("lead_time_days >= 0", name="lead_time_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    unit_cost_inr: Mapped[Decimal] = mapped_column(Money)
    moq: Mapped[int]
    case_pack: Mapped[int]
    lead_time_days: Mapped[int]
    order_cycle_days: Mapped[int | None]  # None -> planning.order_cycle_days from config
    active: Mapped[bool] = mapped_column(default=True)
