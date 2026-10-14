"""Evaluation tables: one row per runner invocation and one per case run inside it."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UTCDateTime


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    scenario: Mapped[str] = mapped_column(String(20))
    mode: Mapped[str] = mapped_column(String(10))  # offline | live
    started_at: Mapped[datetime] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class EvalResult(Base):
    __tablename__ = "eval_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    eval_run_id: Mapped[int] = mapped_column(ForeignKey("eval_runs.id"), index=True)
    case_id: Mapped[str] = mapped_column(String(40))
    sku: Mapped[str] = mapped_column(String(40))
    node: Mapped[str] = mapped_column(String(20))
    expected: Mapped[dict[str, Any]] = mapped_column(JSON)
    actual: Mapped[dict[str, Any]] = mapped_column(JSON)
    passed: Mapped[bool]
    checks: Mapped[dict[str, Any]] = mapped_column(JSON)
    hard_violations: Mapped[int]
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    latency_ms: Mapped[int]
