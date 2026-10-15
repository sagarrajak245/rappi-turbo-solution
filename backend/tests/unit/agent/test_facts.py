"""The fact pack the LLM decides from: every number must say what unit it is in."""

from app.core.config import get_settings
from app.modules.agent.graph import facts
from app.modules.planning.service import calculate
from tests.unit.planning.test_projection import INP


def test_caps_are_named_as_unit_quantities_not_rupees() -> None:
    # A live run read "caps": {"budget": 10100} as ₹10,100 and cut a ₹14,850 order to 100 units.
    calc = calculate(INP, get_settings().planning)
    pack = facts(INP, calc, ())
    assert "caps" not in pack
    assert pack["max_qty_units_by_cap"] == {code.value: cap for code, cap in calc.caps.items()}
    assert pack["max_qty_units_by_cap"]["budget"] == 10_000  # ₹100,000 / ₹10, not rupees
