"""Imports every module's ORM models so Base.metadata is complete (Alembic, create_all)."""

from app.core.db import Base

__all__ = ["Base"]
