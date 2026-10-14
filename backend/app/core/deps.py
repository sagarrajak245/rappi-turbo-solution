"""Shared FastAPI dependencies."""

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_sessionmaker


def get_sm(request: Request) -> async_sessionmaker[AsyncSession]:
    """The app's sessionmaker; tests pin one on `app.state.sessionmaker`."""
    pinned: async_sessionmaker[AsyncSession] | None = getattr(
        request.app.state, "sessionmaker", None
    )
    return pinned or get_sessionmaker()
