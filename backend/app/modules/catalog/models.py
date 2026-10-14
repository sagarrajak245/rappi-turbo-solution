from decimal import Decimal

from sqlalchemy import CheckConstraint, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Node(Base):
    """A dark store (fulfilment node), e.g. Andheri-W."""

    __tablename__ = "nodes"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    city: Mapped[str] = mapped_column(String(50))


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("unit_volume > 0", name="unit_volume_positive"),
        CheckConstraint(
            "shelf_life_days IS NULL OR shelf_life_days > 0", name="shelf_life_positive"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(50))
    storage_zone: Mapped[str] = mapped_column(String(20))  # ambient | chilled | frozen
    perishable: Mapped[bool] = mapped_column(default=False)
    shelf_life_days: Mapped[int | None]
    unit_volume: Mapped[Decimal] = mapped_column(Numeric(10, 3), default=Decimal("1"))
    notes: Mapped[str | None] = mapped_column(Text)
