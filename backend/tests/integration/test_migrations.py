"""One migration history must build exactly the ORM schema, on SQLite (and Postgres in CI)."""

from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from alembic import command
from app.models import Base

BACKEND = Path(__file__).resolve().parents[2]

PURCHASING_TABLES = {
    "nodes",
    "products",
    "suppliers",
    "supplier_products",
    "inventory_snapshots",
    "sales_history",
    "demand_forecasts",
    "purchase_orders",
    "po_lines",
    "budgets",
    "storage_zones",
    "recommendations",
    "erp_purchase_orders",
    "erp_requests",
    "erp_behaviours",
    "agent_runs",
    "lessons",
    "llm_calls",
    "users",
    "notifications",
}


@pytest.fixture
def db_file(tmp_path: Path) -> Path:
    return tmp_path / "migrate.db"


def _alembic(db_file: Path) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_file.as_posix()}")
    cfg.attributes["configure_logger"] = False
    return cfg


def _tables(db_file: Path) -> set[str]:
    engine = create_engine(f"sqlite:///{db_file.as_posix()}")
    try:
        return set(inspect(engine).get_table_names()) - {"alembic_version"}
    finally:
        engine.dispose()


def test_upgrade_creates_every_purchasing_table(db_file: Path) -> None:
    command.upgrade(_alembic(db_file), "head")
    assert _tables(db_file) == PURCHASING_TABLES


def test_downgrade_to_base_removes_everything(db_file: Path) -> None:
    cfg = _alembic(db_file)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    assert _tables(db_file) == set()


def test_models_and_migrations_do_not_drift(db_file: Path) -> None:
    command.upgrade(_alembic(db_file), "head")
    engine = create_engine(f"sqlite:///{db_file.as_posix()}")
    try:
        with engine.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    finally:
        engine.dispose()
    assert diff == []
