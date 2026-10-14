import logging

from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import get_engine, resolve_database

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    db_status = "ok"
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        logger.exception("health: database check failed")
        db_status = "error"
    return {
        "status": "ok",
        "db": db_status,
        "db_mode": resolve_database(get_settings()).mode.value,
    }
