"""Validator: hard constraints never bend, soft policies bend only with a recorded reason."""

from datetime import UTC, date, datetime

from app.core.config import PlanningSettings
from app.modules.planning.calculator import calculate
from app.modules.planning.schemas import Flag
from app.modules.validation.validator import (
    ProposedDecision,
    SoftOverride,
    baseline_decision,
    validate,
)
from app.scenarios.inputs import planning_input_from_case
from app.scenarios.scenario1 import CASES_BY_ID
from app.shared.enums import ConstraintCode, FlagCode, FlagSeverity, Outcome, Verdict

TODAY = date(2026, 10, 14)
NOW = datetime(2026, 10, 14, 6, 0, tzinfo=UTC)
SETTINGS = PlanningSettings()


def _run(case_id: str, decision: ProposedDecision, flags: tuple[Flag, ...] = ()):  # type: ignore[no-untyped-def]
    inp = planning_input_from_case(CASES_BY_ID[case_id], TODAY, NOW)
    calc = calculate(inp, SETTINGS)
    return validate(decision, inp, calc, flags, SETTINGS)


def _modify(qty: int, **kw) -> ProposedDecision:  # type: ignore[no-untyped-def]
    return ProposedDecision(verdict=Verdict.MODIFY, qty=qty, reasons=("r",), **kw)


def test_baseline_decision_is_valid() -> None:
    inp = planning_input_from_case(CASES_BY_ID["C10"], TODAY, NOW)
    calc = calculate(inp, SETTINGS)
    r = validate(baseline_decision(calc), inp, calc, (), SETTINGS)
    assert r.valid and (r.verdict, r.qty) == (Verdict.MODIFY, 210)


def test_x2_qty_off_case_pack_is_invalid_with_nearest_suggestions() -> None:
    r = _run("C6", _modify(805, deviation_reason="round number"))
    assert not r.valid
    assert ConstraintCode.CASE_PACK in {v.code for v in r.violations}
    assert r.suggestions == (768, 816)


def test_x3_soft_override_with_reason_is_valid_and_audited() -> None:
    # C1: 2400 units is 25+ days of cover (> 21 max): soft, allowed with a reason.
    d = _modify(
        2400,
        deviation_reason="Diwali promo next week",
        overrides=(SoftOverride(policy="max_cover_days", reason="Diwali promo next week"),),
    )
    r = _run("C1", d)
    assert r.valid, r.issues
    assert [o.policy for o in r.overrides_applied] == ["max_cover_days"]


def test_soft_breach_without_override_is_invalid() -> None:
    r = _run("C1", _modify(2400, deviation_reason="promo"))
    assert not r.valid
    assert "max_cover_days" in {b.policy for b in r.soft_breaches}


def test_x4_reason_never_bypasses_budget() -> None:
    d = _modify(
        590,
        deviation_reason="the buyer says it is urgent",
        overrides=(SoftOverride(policy="budget", reason="urgent"),),
    )
    r = _run("C7", d)
    assert not r.valid
    assert ConstraintCode.BUDGET in {v.code for v in r.violations}
    assert r.overrides_applied == ()


def test_r4_storage_violation_is_machine_readable() -> None:
    r = _run("C8", _modify(450, deviation_reason="full need"))
    assert not r.valid
    (v,) = [v for v in r.violations if v.code is ConstraintCode.STORAGE]
    assert (v.qty, v.limit) == (450, 400)


def test_reject_with_positive_qty_is_inconsistent() -> None:
    r = _run("C2", ProposedDecision(verdict=Verdict.REJECT, qty=100, reasons=("r",)))
    assert not r.valid


def test_accept_must_order_the_recommendation() -> None:
    r = _run("C1", ProposedDecision(verdict=Verdict.ACCEPT, qty=760, reasons=("r",)))
    assert not r.valid


def test_deviation_from_baseline_needs_a_reason() -> None:
    r = _run("C10", _modify(220))
    assert not r.valid
    assert r.verdict is Verdict.MODIFY  # nothing forced; the agent must add a reason


def test_blocking_flag_forces_investigate() -> None:
    flag = Flag(code=FlagCode.STALE_SNAPSHOT, severity=FlagSeverity.BLOCKING, message="old")
    r = _run("C10", _modify(210), (flag,))
    assert not r.valid
    assert (r.verdict, r.qty, r.outcome) == (Verdict.INVESTIGATE, None, Outcome.PROPOSE)


def test_escalate_flag_forces_escalation() -> None:
    flag = Flag(code=FlagCode.SUPPLIER_INACTIVE, severity=FlagSeverity.ESCALATE, message="x")
    r = _run("C10", _modify(210), (flag,))
    assert (r.verdict, r.qty, r.outcome) == (None, None, Outcome.ESCALATE)
