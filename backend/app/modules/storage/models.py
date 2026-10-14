from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class StorageZone(Base):
    """Physical capacity of one zone (ambient/chilled/frozen) at a node, in volume units."""

    __tablename__ = "storage_zones"
    __table_args__ = (
        UniqueConstraint("node_id", "zone"),
        CheckConstraint("capacity_units >= 0", name="capacity_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"))
    zone: Mapped[str] = mapped_column(String(20))
    capacity_units: Mapped[Decimal] = mapped_column(Numeric(12, 3))
