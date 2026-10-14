"""Sign in (httpOnly JWT cookie), sign out, and who am I."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.deps import get_sm
from app.modules.auth import service
from app.modules.auth.deps import CurrentUser
from app.modules.auth.schemas import LoginIn, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login(
    body: LoginIn,
    response: Response,
    sm: Annotated[async_sessionmaker[AsyncSession], Depends(get_sm)],
) -> UserOut:
    auth = get_settings().auth
    async with sm() as session:
        user, token = await service.login(session, body.email, body.password, auth)
    response.set_cookie(
        auth.cookie_name,
        token,
        max_age=auth.token_ttl_minutes * 60,
        httponly=True,
        secure=auth.cookie_secure,
        samesite="lax",
    )
    return user


@router.post("/logout")
async def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(get_settings().auth.cookie_name)
    return {"ok": True}


@router.get("/me")
async def me(user: CurrentUser) -> UserOut:
    return user
