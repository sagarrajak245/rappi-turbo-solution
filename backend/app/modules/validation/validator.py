"""Validate a proposed decision against data quality, hard constraints and soft policies.

The decision is a plain DTO so the same validator checks the deterministic baseline today and
the LLM's proposal in Session B. Precedence (KB §7.1a): a blocking flag forces INVESTIGATE, an
escalate flag forces ESCALATE, otherwise the proposal stands or falls on its own merits.
"""

from pydantic import BaseModel, ConfigDict

from app.core.config import PlanningSettings
from app.modules.planning.constraints import check_hard, nearest_case_qtys
from app.modules.planning.schemas import CalcResult, Flag, PlanningInput, Violation
from app.modules.validation.policy import HARD, SOFT
from app.shared.enums import ConstraintCode, FlagSeverity, Outcome, Verdict


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


def baseline_decision(calc: CalcResult) -> ProposedDecision:
    return ProposedDecision(
        verdict=calc.verdict, qty=calc.qty, outcome=calc.outcome, reasons=("calculated baseline",)
    )


def _consistency(d: ProposedDecision, rec: int) -> list[str]:
    rules = {
        Verdict.REJECT: (d.qty == 0, "REJECT must order 0"),
        Verdict.ACCEPT: (d.qty == rec, f"ACCEPT must order the recommended {rec}"),
        Verdict.MODIFY: (
            d.qty is not None and d.qty > 0 and d.qty != rec,
            "MODIFY must order a positive quantity different from the recommendation",
        ),
        Verdict.INVESTIGATE: (d.qty is None, "INVESTIGATE proposes no quantity"),
    }
    if d.verdict is None:
        ok = d.outcome is Outcome.ESCALATE and d.qty is None
        return [] if ok else ["only an escalation may omit the verdict"]
    ok, message = rules[d.verdict]
    return [] if ok else [message]


def _forced(
    flags: tuple[Flag, ...], d: ProposedDecision, flags_out: tuple[Flag, ...]
) -> ValidationResult | None:
    severities = {f.severity for f in flags}
    if FlagSeverity.BLOCKING in severities:
        target: tuple[Verdict | None, Outcome] = (Verdict.INVESTIGATE, Outcome.PROPOSE)
    elif FlagSeverity.ESCALATE in severities:
        target = (None, Outcome.ESCALATE)
    else:
        return None
    matches = (d.verdict, d.outcome) == target and d.qty is None
    issues = () if matches else (f"data-quality flags require {target[0] or target[1].value}",)
    return ValidationResult(
        valid=matches,
        verdict=target[0],
        qty=None,
        outcome=target[1],
        issues=issues,
        flags=flags_out,
    )


def validate(
    decision: ProposedDecision,
    inp: PlanningInput,
    calc: CalcResult,
    flags: tuple[Flag, ...],
    settings: PlanningSettings,
) -> ValidationResult:
    all_flags = flags + calc.flags
    forced = _forced(flags, decision, all_flags)
    if forced is not None:
        return forced

    issues = _consistency(decision, inp.rec_qty)
    qty = decision.qty
    if qty is not None and qty != calc.qty and not decision.deviation_reason:
        issues.append(f"{qty} differs from the calculated {calc.qty}: a deviation reason is needed")
    violations = check_hard(qty, inp, calc.caps) if qty is not None else []
    suggestions: tuple[int, ...] = ()
    if any(v.code is ConstraintCode.CASE_PACK for v in violations) and qty is not None:
        suggestions = nearest_case_qtys(qty, inp)

    overrides = {o.policy: o for o in decision.overrides if o.policy not in HARD and o.reason}
    breaches, applied = [], []
    for policy, check in SOFT.items():
        message = check(qty, inp, calc, settings) if qty else None
        if message is None:
            continue
        if policy in overrides:
            applied.append(overrides[policy])
        else:
            breaches.append(SoftBreach(policy=policy, message=message))

    return ValidationResult(
        valid=not (issues or violations or breaches),
        verdict=decision.verdict,
        qty=qty,
        outcome=decision.outcome,
        violations=tuple(violations),
        soft_breaches=tuple(breaches),
        overrides_applied=tuple(applied),
        issues=tuple(issues),
        suggestions=suggestions,
        flags=all_flags,
    )
