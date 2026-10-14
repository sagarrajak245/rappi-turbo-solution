from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UTCDateTime


class InventorySnapshot(Base):
    """Stock at a node at a point in time. The latest snapshot is the current position.

    on_hand may be negative on purpose: bad source data must be storable so the
    data-quality check can flag it (Q2) instead of the insert failing.
    """

    __tablename__ = "inventory_snapshots"
    __table_args__ = (Index("ix_inventory_snapshots_latest", "node_id", "product_id", "as_of"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    on_hand: Mapped[int]
    reserved: Mapped[int] = mapped_column(default=0)
    as_of: Mapped[datetime] = mapped_column(UTCDateTime())


class SalesHistory(Base):
    __tablename__ = "sales_history"
    __table_args__ = (UniqueConstraint("node_id", "product_id", "day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    day: Mapped[date]
    qty: Mapped[int]


class DemandForecast(Base):
    __tablename__ = "demand_forecasts"
    __table_args__ = (UniqueConstraint("node_id", "product_id", "day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    day: Mapped[date]
    qty: Mapped[Decimal] = mapped_column(Numeric(12, 2))
