import pytest

from app.modules.agent.llm.base import LlmUnavailable
from app.modules.agent.llm.fake import ScriptedLlm
from app.modules.agent.schemas import DecisionOut, ReviewOut
from app.shared.enums import Verdict


async def test_scripted_llm_returns_validated_objects_in_order() -> None:
    llm = ScriptedLlm([{"verdict": "ACCEPT", "qty": 800}, {"ok": True}])
    decision, record = await llm.complete_json("s", "u", DecisionOut)
    review, _ = await llm.complete_json("s", "u", ReviewOut)
    assert decision.verdict is Verdict.ACCEPT and decision.qty == 800
    assert review.ok is True
    assert record.provider == "fake"
    assert [c[0] for c in llm.calls] == ["DecisionOut", "ReviewOut"]


async def test_scripted_llm_raises_injected_errors_and_bad_shapes() -> None:
    llm = ScriptedLlm([RuntimeError("down"), {"verdict": "MAYBE"}])
    with pytest.raises(RuntimeError):
        await llm.complete_json("s", "u", DecisionOut)
    with pytest.raises(LlmUnavailable):
        await llm.complete_json("s", "u", DecisionOut)
    with pytest.raises(LlmUnavailable):  # queue exhausted
        await llm.complete_json("s", "u", DecisionOut)


def test_decision_converts_to_validator_contract() -> None:
    d = DecisionOut(verdict=Verdict.MODIFY, qty=210, reasons=["r"], deviation_reason=None)
    p = d.to_proposed()
    assert (p.verdict, p.qty, p.reasons) == (Verdict.MODIFY, 210, ("r",))
