from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.db_types import Money


class Budget(Base):
    """Purchasing budget per node and category for one period (e.g. "2026-10")."""

    __tablename__ = "budgets"
    __table_args__ = (
        UniqueConstraint("node_id", "category", "period"),
        CheckConstraint("amount_inr >= 0", name="amount_non_negative"),
        CheckConstraint("committed_inr >= 0", name="committed_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"))
    category: Mapped[str] = mapped_column(String(50))
    period: Mapped[str] = mapped_column(String(7))
    amount_inr: Mapped[Decimal] = mapped_column(Money)
    committed_inr: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
