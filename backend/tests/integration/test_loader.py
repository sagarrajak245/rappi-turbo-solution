from datetime import UTC, date, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import NotFound
from app.modules.planning.loader import load_planning_input
from app.scenarios.inputs import planning_input_from_case
from app.scenarios.scenario1 import CASES
from app.seed.scenario1 import seed_scenario1

TODAY = date(2026, 10, 14)
NOW = datetime(2026, 10, 14, 6, 0, tzinfo=UTC)


async def test_loaded_input_equals_case_spec_for_every_case(session: AsyncSession) -> None:
    await seed_scenario1(session, today=TODAY, now=NOW)
    settings = get_settings().planning
    for case in CASES:
        loaded = await load_planning_input(session, case.sku, case.node, TODAY, settings=settings)
        assert loaded == planning_input_from_case(case, TODAY, NOW), case.id


async def test_unknown_pair_is_not_found(session: AsyncSession) -> None:
    await seed_scenario1(session, today=TODAY, now=NOW)
    with pytest.raises(NotFound):
        await load_planning_input(
            session, "COKE-750", "THANE", TODAY, settings=get_settings().planning
        )
