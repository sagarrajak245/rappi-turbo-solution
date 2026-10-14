"""LangGraph state for one Scenario 1 run (one SKU x node). Keys are filled node by node."""

from datetime import date, datetime
from typing import TypedDict

from app.modules.agent.llm.base import LlmCallRecord
from app.modules.agent.schemas import DecisionOut, ProposalOut
from app.modules.planning.schemas import CalcResult, Flag, PlanningInput
from app.modules.validation.schemas import ProposedDecision, ValidationResult


class AgentState(TypedDict, total=False):
    thread_id: str
    sku: str
    node: str
    today: date
    now: datetime

    inp: PlanningInput
    flags: tuple[Flag, ...]
    calc: CalcResult
    baseline: ProposedDecision
    lessons: list[str]  # recall_memory: active lesson texts for this SKU x node
    lesson_ids: list[int]

    skip_llm: bool  # blocking/escalate data: decided deterministically, no LLM call
    decision_out: DecisionOut
    decision: ProposedDecision
    validation: ValidationResult
    feedback: list[str]  # validator/reviewer issues sent back to decide
    review_ok: bool
    attempts: int
    escalate_reason: str
    llm_records: list[LlmCallRecord]

    proposal: ProposalOut
