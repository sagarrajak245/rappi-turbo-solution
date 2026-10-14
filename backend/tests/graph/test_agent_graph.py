"""Every route through the decision graph (KB §3.2), driven by scripted LLM answers."""

from app.shared.enums import Outcome, Verdict
from tests.graph.conftest import MakeService

OK = {"ok": True}
ACCEPT_800 = {"verdict": "ACCEPT", "qty": 800, "reasons": ["rec matches the calculated need"]}


async def test_c1_accept_is_proposed_for_approval(make_service: MakeService) -> None:
    svc, decide, review = await make_service([ACCEPT_800], [OK])
    p = (await svc.propose("t", "COKE-750", "BANDRA"))[0]
    assert (p.verdict, p.qty, p.outcome, p.valid) == (Verdict.ACCEPT, 800, Outcome.PROPOSE, True)
    assert p.baseline_qty == 800
    assert len(decide.calls) + len(review.calls) == 2


async def test_q1_blocking_flag_investigates_without_the_llm(make_service: MakeService) -> None:
    svc, decide, review = await make_service([], [])
    p = (await svc.propose("t", "BRITANNIA-BREAD-400", "POWAI"))[0]
    assert (p.verdict, p.qty, p.outcome) == (Verdict.INVESTIGATE, None, Outcome.PROPOSE)
    assert "stale_snapshot" in {f.code.value for f in p.flags}
    assert decide.calls == [] and review.calls == []


async def test_c9_no_valid_po_escalates_with_options_without_the_llm(
    make_service: MakeService,
) -> None:
    svc, decide, review = await make_service([], [])
    p = (await svc.propose("t", "HALDIRAM-BHUJIA-200", "POWAI"))[0]
    assert (p.verdict, p.qty, p.outcome) == (None, None, Outcome.ESCALATE)
    assert "raise_budget" in {o.kind for o in p.options}
    assert decide.calls == [] and review.calls == []


async def test_r4_constraint_breaking_qty_is_fed_back_and_revised(
    make_service: MakeService,
) -> None:
    svc, decide, _ = await make_service(
        [
            {"verdict": "MODIFY", "qty": 480, "deviation_reason": "promo next week"},
            {"verdict": "MODIFY", "qty": 400, "reasons": ["storage fits 400"]},
        ],
        [OK],
    )
    p = (await svc.propose("t", "SURF-1KG", "BANDRA"))[0]
    assert (p.verdict, p.qty, p.valid) == (Verdict.MODIFY, 400, True)
    assert len(decide.calls) == 2
    assert "storage" in decide.calls[1][1]  # the validator's violation reached the LLM


async def test_deviation_without_reason_is_sent_back(make_service: MakeService) -> None:
    svc, decide, _ = await make_service(
        [{"verdict": "MODIFY", "qty": 300}, {"verdict": "MODIFY", "qty": 210}], [OK]
    )
    p = (await svc.propose("t", "AASHIRVAAD-ATTA-5KG", "ANDHERI-W"))[0]
    assert (p.qty, p.valid) == (210, True)
    assert "deviation reason" in decide.calls[1][1]


async def test_r7_reviewer_failing_twice_escalates(make_service: MakeService) -> None:
    bad = {"ok": False, "issues": ["reason cites a number not in the facts"]}
    svc, decide, review = await make_service([ACCEPT_800, ACCEPT_800], [bad, bad])
    p = (await svc.propose("t", "COKE-750", "BANDRA"))[0]
    assert (p.verdict, p.qty, p.outcome) == (None, None, Outcome.ESCALATE)
    assert len(decide.calls) == 2 and len(review.calls) == 2
    assert "not in the facts" in decide.calls[1][1]


async def test_q7_notes_never_reach_the_llm(make_service: MakeService) -> None:
    svc, decide, _ = await make_service([{"verdict": "MODIFY", "qty": 180}], [OK])
    (await svc.propose("t", "DETTOL-SOAP-75", "BANDRA"))[0]
    prompt = decide.calls[0][1].lower()
    assert "ignore all previous" not in prompt and "5000" not in prompt
    assert "suspicious_text" in prompt
