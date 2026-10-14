"""Metrics and evaluation are admin-only: a buyer gets 403, nobody signed in gets 401."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.modules.auth.deps import current_user
from app.modules.auth.schemas import UserOut
from app.shared.enums import UserRole

PATHS = ["/admin/metrics", "/evaluation/runs", "/evaluation/runs/1"]


@pytest.mark.parametrize("path", PATHS)
async def test_buyer_is_forbidden(path: str) -> None:
    app = create_app()
    app.dependency_overrides[current_user] = lambda: UserOut(
        id="u", name="n", email="e", role=UserRole.BUYER, branch="Mumbai"
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.get(path)).status_code == 403


@pytest.mark.parametrize("path", PATHS)
async def test_anonymous_is_unauthorized(path: str) -> None:
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.get(path)).status_code == 401
