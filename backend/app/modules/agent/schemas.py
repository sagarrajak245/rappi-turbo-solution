"""Structured LLM outputs (KB §3.2 nodes 5 and 7) and the agent API DTOs."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.execution.schemas import ExecutionResult
from app.modules.planning.schemas import Flag, ResolutionOption, StockProjection
from app.modules.validation.schemas import ProposedDecision, SoftOverride
from app.shared.enums import Outcome, RunStatus, Verdict


class DecisionOut(BaseModel):
    """What the decide node asks the LLM for. Converted to a ProposedDecision for validation."""

    model_config = ConfigDict(frozen=True)

    verdict: Verdict
    qty: int | None = Field(default=None, ge=0)
    reasons: list[str] = []
    facts_cited: list[str] = []
    deviation_reason: str | None = None
    overrides: list[SoftOverride] = []
    investigate_items: list[str] = []
    recommended_option: str | None = None

    def to_proposed(self) -> ProposedDecision:
        return ProposedDecision(
            verdict=self.verdict,
            qty=self.qty,
            outcome=Outcome.PROPOSE,
            reasons=tuple(self.reasons),
            deviation_reason=self.deviation_reason,
            overrides=tuple(self.overrides),
        )


class ReviewOut(BaseModel):
    """The reviewer LLM's groundedness check."""

    model_config = ConfigDict(frozen=True)

    ok: bool
    issues: list[str] = []


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class RunRequest(_Frozen):
    sku: str = Field(min_length=1)
    node: str = Field(min_length=1)


class ProposalOut(_Frozen):
    """What the buyer sees at the human gate (KB §3.2 node 9)."""

    thread_id: str
    sku: str
    node: str
    rec_qty: int
    baseline_qty: int | None
    verdict: Verdict | None
    qty: int | None
    outcome: Outcome
    valid: bool
    reasons: list[str] = []
    deviation_reason: str | None = None
    flags: list[Flag] = []
    options: list[ResolutionOption] = []
    issues: list[str] = []  # validator issues, or why the run escalated
    suggestions: list[int] = []  # nearest valid quantities when the case pack is off
    attempts: int = 0
    llm_calls: int = 0
    lessons_applied: list[int] = []  # lesson ids that reached the decide prompt
    facts: dict[str, Any] = {}  # the numbers behind the decision, for the review page
    projection: StockProjection | None = None  # 14-day stock: no order / system / agent qty


class HumanAction(StrEnum):
    APPROVE = "approve"
    MODIFY = "modify"
    REJECT = "reject"
    ACKNOWLEDGE = "acknowledge"


class HumanDecision(_Frozen):
    """Resume value of the human gate. A modified qty is re-validated before it counts."""

    action: HumanAction
    qty: int | None = Field(default=None, ge=0)
    reason: str | None = None


class RunSummary(_Frozen):
    """One row of a run list: enough to triage it without loading the full proposal."""

    id: str
    sku: str
    node: str
    status: RunStatus
    verdict: Verdict | None = None
    qty: int | None = None
    rec_qty: int | None = None
    outcome: Outcome | None = None
    reason: str | None = None  # the proposal's first reason
    error: str | None = None
    decided_by: str | None = None
    created_at: datetime
    updated_at: datetime


class RunOut(_Frozen):
    """One run as stored: the proposal waits here for the buyer, then the ERP outcome."""

    id: str
    sku: str
    node: str
    status: RunStatus
    proposal: ProposalOut | None = None
    execution: ExecutionResult | None = None
    replans_done: int = 0
    error: str | None = None  # why it failed, or why the last decision was not accepted
