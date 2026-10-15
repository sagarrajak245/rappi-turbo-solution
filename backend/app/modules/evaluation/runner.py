"""Run scenario-1 cases through the agent's propose step and score them.

`work_sm` is a database seeded with the scenario (the runner seeds it; use a throwaway one),
`store_sm` is where the evaluation run and its results are persisted. Offline mode answers every
case with an oracle LLM that returns the case's expected decision, so it tests the deterministic
pipeline around the LLM (data quality, calculator, validator, reviewer wiring) with no network.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.modules.agent.llm.base import LlmClient
from app.modules.agent.llm.factory import build_llm
from app.modules.agent.llm.fake import ScriptedLlm
from app.modules.agent.service import AgentService
from app.modules.evaluation import service
from app.modules.evaluation.checks import hard_violations
from app.modules.evaluation.models import EvalResult, EvalRun
from app.modules.evaluation.schemas import EvalRunOut
from app.modules.planning import service as planning
from app.scenarios.scenario1 import CASES
from app.scenarios.types import CaseSpec
from app.seed.scenario1 import seed_scenario1
from app.shared.enums import Outcome

_ORACLE_REPEATS = 4  # enough answers to cover validator-driven retries


def _oracle_decision(case: CaseSpec) -> dict[str, Any]:
    exp = case.expected
    answer: dict[str, Any] = {
        "verdict": exp.verdict.value if exp.verdict else "INVESTIGATE",
        "qty": exp.qty,
        "reasons": ["oracle: the case's expected decision"],
        "investigate_items": ["oracle"] if exp.qty is None else [],
    }
    if exp.qty is not None and exp.qty != case.rec:
        answer["deviation_reason"] = "oracle: expected quantity differs from the recommendation"
    return answer


def _oracle_llms(case: CaseSpec) -> tuple[LlmClient, LlmClient]:
    decide = ScriptedLlm([_oracle_decision(case)] * _ORACLE_REPEATS)
    review = ScriptedLlm([{"ok": True, "issues": []}] * _ORACLE_REPEATS)
    return decide, review


async def _run_case(
    case: CaseSpec,
    work_sm: async_sessionmaker[AsyncSession],
    settings: Settings,
    llms: tuple[LlmClient, LlmClient],
    now: datetime,
) -> EvalResult:
    svc = AgentService(work_sm, llms[0], llms[1], settings, clock=lambda: now)
    proposal, state = await svc.propose(uuid.uuid4().hex, case.sku, case.node)

    # Independent re-check: re-derive the limits from the planning core, not from the agent.
    async with work_sm() as session:
        inp = await planning.load_planning_input(
            session, case.sku, case.node, now.date(), settings=settings.planning
        )
    calc = planning.calculate(inp, settings.planning)
    violations = hard_violations(
        qty=proposal.qty, caps=calc.caps, moq=inp.moq, case_pack=inp.case_pack
    )

    exp = case.expected
    checks: dict[str, Any] = {
        "verdict": proposal.verdict == exp.verdict,
        "qty": proposal.qty == exp.qty,
        "outcome": proposal.outcome == exp.outcome,
        "hard_limits": not violations,
        "violations": violations,
    }
    records = state.get("llm_records", [])
    return EvalResult(
        case_id=case.id,
        sku=case.sku,
        node=case.node,
        expected={
            "verdict": exp.verdict.value if exp.verdict else None,
            "qty": exp.qty,
            "outcome": exp.outcome.value,
        },
        actual={
            "verdict": proposal.verdict.value if proposal.verdict else None,
            "qty": proposal.qty,
            "outcome": proposal.outcome.value,
            "valid": proposal.valid,
            "issues": proposal.issues,
        },
        passed=all(checks[k] for k in ("verdict", "qty", "outcome", "hard_limits")),
        checks=checks,
        hard_violations=len(violations),
        cost_usd=Decimal(str(sum(r.cost_usd for r in records))),
        latency_ms=sum(r.latency_ms for r in records),
    )


def _summary(results: list[EvalResult], escalated: int) -> dict[str, Any]:
    n = len(results)
    cost = sum((r.cost_usd for r in results), Decimal(0))
    return {
        "cases": n,
        "passed": sum(1 for r in results if r.passed),
        "accuracy": sum(1 for r in results if r.passed) / n if n else 0.0,
        "hard_violations": sum(r.hard_violations for r in results),
        "escalation_rate": escalated / n if n else 0.0,
        "avg_cost_usd_per_run": float(cost / n) if n else 0.0,
        "total_latency_ms": sum(r.latency_ms for r in results),
    }


async def run_evaluation(
    work_sm: async_sessionmaker[AsyncSession],
    store_sm: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    live: bool = False,
    repeat: int = 1,
    http: httpx.AsyncClient | None = None,
    run_id: int | None = None,
) -> EvalRunOut:
    started = datetime.now(UTC)
    async with work_sm() as session:
        await seed_scenario1(session, today=started.date(), now=started)

    live_llms: tuple[LlmClient, LlmClient] | None = None
    if live:
        if http is None:
            raise ValueError("live evaluation needs an httpx client")
        live_llms = (build_llm("decision", settings, http), build_llm("reviewer", settings, http))

    results: list[EvalResult] = []
    escalated = 0
    for _ in range(repeat):
        for case in CASES:
            result = await _run_case(
                case, work_sm, settings, live_llms or _oracle_llms(case), started
            )
            escalated += result.actual["outcome"] != Outcome.PROPOSE.value
            results.append(result)

    async with store_sm() as session:
        # A run the API opened up front (shown as running) is completed in place.
        row = (await session.get(EvalRun, run_id)) if run_id is not None else None
        if row is None:
            row = EvalRun(scenario="1", mode="live" if live else "offline", started_at=started)
            session.add(row)
        row.finished_at = datetime.now(UTC)
        row.summary = _summary(results, escalated)
        await session.flush()
        for r in results:
            r.eval_run_id = row.id
        session.add_all(results)
        await session.commit()
        run_id = row.id
    async with store_sm() as session:
        return await service.get_run(session, run_id)
