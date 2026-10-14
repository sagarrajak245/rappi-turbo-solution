"""Tables owned by the agent: one row per run (the human gate lives here) and its LLM calls."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UTCDateTime
from app.core.db_types import Money, str_enum
from app.shared.enums import RunStatus


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # also the LangGraph thread
    sku: Mapped[str] = mapped_column(String(40))
    node_code: Mapped[str] = mapped_column(String(20))
    status: Mapped[RunStatus] = mapped_column(str_enum(RunStatus), index=True)
    proposal: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    decision: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    execution: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # Server-side re-plan state: the client never supplies these (KB §12 review finding).
    replans_done: Mapped[int] = mapped_column(default=0)
    unit_price_override: Mapped[Decimal | None] = mapped_column(Money)
    case_pack_override: Mapped[int | None]
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime())


class LlmCall(Base):
    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(80))
    tokens_in: Mapped[int]
    tokens_out: Mapped[int]
    latency_ms: Mapped[int]
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    fallback_used: Mapped[bool]
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
