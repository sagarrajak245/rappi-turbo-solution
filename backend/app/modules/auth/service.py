from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import AuthSettings
from app.core.errors import Unauthorized
from app.modules.auth import repository as repo
from app.modules.auth.schemas import UserOut
from app.modules.auth.security import (
    DUMMY_HASH,
    issue_token,
    read_token,
    verify_password,
)


async def login(
    session: AsyncSession, email: str, password: str, auth: AuthSettings
) -> tuple[UserOut, str]:
    """Check credentials; return the user and a session token. The error never says which part."""
    user = await repo.get_by_email(session, email.strip().lower())
    ok = verify_password(password, user.password_hash if user else DUMMY_HASH)
    if user is None or not ok:
        raise Unauthorized("Invalid email or password")
    return UserOut.model_validate(user), issue_token(user.id, auth)


async def user_for_token(session: AsyncSession, token: str | None, auth: AuthSettings) -> UserOut:
    user_id = read_token(token, auth) if token else None
    user = await repo.get_by_id(session, user_id) if user_id else None
    if user is None:
        raise Unauthorized("Not signed in")
    return UserOut.model_validate(user)
