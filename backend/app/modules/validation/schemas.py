"""Decision and validation DTOs: the contract Session B's LLM output plugs into."""

from pydantic import BaseModel, ConfigDict

from app.modules.planning.schemas import Flag, Violation
from app.shared.enums import Outcome, Verdict


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class SoftOverride(_Frozen):
    policy: str
    reason: str


class ProposedDecision(_Frozen):
    verdict: Verdict | None
    qty: int | None
    outcome: Outcome = Outcome.PROPOSE
    reasons: tuple[str, ...] = ()
    deviation_reason: str | None = None  # required when qty differs from the baseline
    overrides: tuple[SoftOverride, ...] = ()


class SoftBreach(_Frozen):
    policy: str
    message: str


class ValidationResult(_Frozen):
    valid: bool
    verdict: Verdict | None  # final, after forced precedence
    qty: int | None
    outcome: Outcome
    violations: tuple[Violation, ...] = ()
    soft_breaches: tuple[SoftBreach, ...] = ()  # breaches without a valid override
    overrides_applied: tuple[SoftOverride, ...] = ()
    issues: tuple[str, ...] = ()
    suggestions: tuple[int, ...] = ()  # nearest valid quantities, when the case pack is off
    flags: tuple[Flag, ...] = ()
