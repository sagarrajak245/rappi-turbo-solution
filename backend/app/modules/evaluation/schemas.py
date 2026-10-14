from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)


class EvalResultOut(_Frozen):
    id: int
    case_id: str
    sku: str
    node: str
    expected: dict[str, Any]
    actual: dict[str, Any]
    passed: bool
    checks: dict[str, Any]
    hard_violations: int
    cost_usd: float
    latency_ms: int


class EvalRunHeader(_Frozen):
    id: int
    scenario: str
    mode: str
    started_at: datetime
    finished_at: datetime | None
    summary: dict[str, Any]


class EvalRunOut(EvalRunHeader):
    results: list[EvalResultOut]
