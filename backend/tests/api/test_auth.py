"""Login sets an httpOnly JWT cookie; protected routes answer 401, role-gated ones 403."""

from collections.abc import AsyncIterator

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.main import create_app
from app.modules.auth.deps import current_user, require_role
from app.modules.auth.schemas import UserOut
from app.modules.auth.seed import ADMIN_EMAIL, BUYER_EMAIL, seed_users
from app.shared.enums import UserRole


@pytest.fixture
async def client(sessionmaker: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncClient]:
    async with sessionmaker() as s:
        await seed_users(s, get_settings())
    app = create_app()
    app.state.sessionmaker = sessionmaker

    @app.get("/admin-only")
    async def admin_only(user: UserOut = Depends(require_role(UserRole.ADMIN))) -> dict[str, str]:  # noqa: B008
        return {"id": user.id}

    @app.get("/whoami")
    async def whoami(user: UserOut = Depends(current_user)) -> dict[str, str]:  # noqa: B008
        return {"id": user.id}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _login(client: AsyncClient, email: str, password: str) -> int:
    r = await client.post("/auth/login", json={"email": email, "password": password})
    return r.status_code


async def test_login_sets_httponly_cookie_and_me_works(client: AsyncClient) -> None:
    auth = get_settings().auth
    r = await client.post(
        "/auth/login", json={"email": BUYER_EMAIL, "password": auth.seed_buyer_password}
    )
    assert r.status_code == 200
    assert r.json()["role"] == "buyer"
    assert "password" not in r.text
    cookie = r.headers["set-cookie"].lower()
    assert auth.cookie_name in cookie
    assert "httponly" in cookie

    me = await client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == BUYER_EMAIL
    assert me.json()["branch"] == "Mumbai"


async def test_bad_password_is_unauthorized(client: AsyncClient) -> None:
    r = await client.post("/auth/login", json={"email": BUYER_EMAIL, "password": "nope"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"
    assert await _login(client, "ghost@example.com", "nope") == 401


async def test_protected_routes_need_a_session(client: AsyncClient) -> None:
    assert (await client.get("/auth/me")).status_code == 401
    assert (await client.get("/whoami")).status_code == 401
    assert (await client.get("/agent/runs/x")).status_code == 401
    assert (await client.get("/notifications")).status_code == 401


async def test_logout_clears_the_session(client: AsyncClient) -> None:
    await _login(client, BUYER_EMAIL, get_settings().auth.seed_buyer_password)
    assert (await client.post("/auth/logout")).status_code == 200
    assert (await client.get("/auth/me")).status_code == 401


async def test_tampered_token_is_unauthorized(client: AsyncClient) -> None:
    client.cookies.set(get_settings().auth.cookie_name, "not.a.jwt")
    assert (await client.get("/auth/me")).status_code == 401


async def test_require_role_forbids_a_buyer_and_admits_an_admin(client: AsyncClient) -> None:
    auth = get_settings().auth
    await _login(client, BUYER_EMAIL, auth.seed_buyer_password)
    assert (await client.get("/admin-only")).status_code == 403
    await _login(client, ADMIN_EMAIL, auth.seed_admin_password)
    assert (await client.get("/admin-only")).status_code == 200
