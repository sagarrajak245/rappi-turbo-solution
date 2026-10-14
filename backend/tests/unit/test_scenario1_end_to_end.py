"""Every Scenario 1 case, end to end without an LLM: data quality -> calculator -> validator."""

from datetime import UTC, date, datetime

import pytest

from app.core.config import DataQualitySettings, PlanningSettings
from app.modules.planning.calculator import calculate
from app.modules.validation.service import baseline_decision, check_data_quality, validate
from app.scenarios.inputs import planning_input_from_case
from app.scenarios.scenario1 import CASES
from app.scenarios.types import CaseSpec

TODAY = date(2026, 10, 14)
NOW = datetime(2026, 10, 14, 6, 0, tzinfo=UTC)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_case_end_to_end(case: CaseSpec) -> None:
    inp = planning_input_from_case(case, TODAY, NOW)
    flags = check_data_quality(inp, NOW, DataQualitySettings())
    calc = calculate(inp, PlanningSettings())
    decision = baseline_decision(calc)
    r = validate(decision, inp, calc, flags, PlanningSettings())

    assert (r.verdict, r.qty, r.outcome) == (
        case.expected.verdict,
        case.expected.qty,
        case.expected.outcome,
    )
    assert {f.code for f in r.flags} == set(case.expected.flags)
    # The baseline itself must always pass when data quality does not override it.
    forced = r.verdict != decision.verdict or r.outcome != decision.outcome
    assert r.valid or forced, (r.issues, r.violations, r.soft_breaches)
