"""Alembic environment: async, portable between Postgres and SQLite.

The URL comes from DATABASE_URL_DIRECT (preferred for migrations) or DATABASE_URL,
unless a caller (e.g. a test) sets ``sqlalchemy.url`` on the Alembic config explicitly.
"""

import asyncio
from logging.config import fileConfig
from pathlib import Path
from typing import Any

from sqlalchemy.engine import Connection
from sqlalchemy.types import TypeDecorator

from alembic import context
from app.core.config import get_settings
from app.core.db import DbConfig, DbMode, create_engine, resolve_database
from app.models import Base

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _render_item(type_: str, obj: Any, autogen_context: Any) -> str | bool:
    """Render our TypeDecorators (Money, UTCDateTime) as their plain SQL type.

    Migrations then never import app code, so old revisions keep working when models change.
    """
    if type_ == "type" and isinstance(obj, TypeDecorator):
        return f"sa.{obj.impl!r}"
    return False


def _db_config() -> DbConfig:
    explicit = config.get_main_option("sqlalchemy.url")
    if explicit:
        mode = DbMode.SQLITE if explicit.startswith("sqlite") else DbMode.POSTGRES
        return DbConfig(url=explicit, mode=mode)
    return resolve_database(get_settings(), direct=True)


def _configure(connection: Connection | None, url: str | None, is_sqlite: bool) -> None:
    context.configure(
        connection=connection,
        url=url,
        target_metadata=target_metadata,
        render_as_batch=is_sqlite,  # SQLite cannot ALTER most things; batch mode recreates tables
        compare_type=True,
        render_item=_render_item,
        literal_binds=connection is None,
    )


def run_migrations_offline() -> None:
    cfg = _db_config()
    _configure(None, cfg.url, cfg.mode is DbMode.SQLITE)
    with context.begin_transaction():
        context.run_migrations()


def _run_sync(connection: Connection, is_sqlite: bool) -> None:
    _configure(connection, None, is_sqlite)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    cfg = _db_config()
    if cfg.mode is DbMode.SQLITE:
        Path(cfg.url.split(":///", 1)[1]).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(cfg)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_run_sync, cfg.mode is DbMode.SQLITE)
            await connection.commit()
    finally:
        await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
