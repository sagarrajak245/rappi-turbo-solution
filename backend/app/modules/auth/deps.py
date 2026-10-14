"""Auth dependencies: `current_user` (401) and `require_role(...)` (403)."""

from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.deps import get_sm
from app.core.errors import Forbidden
from app.modules.auth import service
from app.modules.auth.schemas import UserOut
from app.shared.enums import UserRole


async def current_user(
    request: Request, sm: Annotated[async_sessionmaker[AsyncSession], Depends(get_sm)]
) -> UserOut:
    auth = get_settings().auth
    async with sm() as session:
        return await service.user_for_token(session, request.cookies.get(auth.cookie_name), auth)


CurrentUser = Annotated[UserOut, Depends(current_user)]


def require_role(*roles: UserRole) -> Callable[..., Coroutine[Any, Any, UserOut]]:
    async def _check(user: CurrentUser) -> UserOut:
        if user.role not in roles:
            raise Forbidden("Your role cannot do this", {"required": [r.value for r in roles]})
        return user

    return _check
