"""The independent quantity check: re-derives the hard limits without trusting the agent."""

from app.modules.evaluation.checks import hard_violations


def test_qty_over_a_cap_is_a_violation() -> None:
    found = hard_violations(qty=900, caps={"STORAGE": 800, "BUDGET": 1200}, moq=100, case_pack=50)
    assert len(found) == 1
    assert "cap" in found[0]


def test_qty_below_moq_or_off_case_pack_is_a_violation() -> None:
    assert len(hard_violations(qty=40, caps={}, moq=100, case_pack=10)) == 1
    assert len(hard_violations(qty=130, caps={}, moq=100, case_pack=50)) == 1


def test_clean_and_empty_quantities_pass() -> None:
    assert hard_violations(qty=800, caps={"STORAGE": 800}, moq=100, case_pack=50) == []
    assert hard_violations(qty=None, caps={"STORAGE": 0}, moq=100, case_pack=50) == []
    assert hard_violations(qty=0, caps={"STORAGE": 0}, moq=100, case_pack=50) == []
