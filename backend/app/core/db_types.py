"""Column helpers shared by every module's models (portable across Postgres and SQLite)."""

from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Dialect, Enum, Numeric
from sqlalchemy.types import TypeDecorator


class Money(TypeDecorator[Decimal]):
    """INR amount, NUMERIC(12,2). Quantized on read: SQLite stores NUMERIC as a float."""

    impl = Numeric(12, 2)
    cache_ok = True

    def process_result_value(self, value: Decimal | None, dialect: Dialect) -> Decimal | None:
        return None if value is None else Decimal(str(value)).quantize(Decimal("0.01"))


def str_enum(enum_cls: type[StrEnum]) -> Enum:
    """Store enums as VARCHAR (no native Postgres ENUM type to migrate or drop)."""
    return Enum(
        enum_cls,
        native_enum=False,
        length=20,
        values_callable=lambda cls: [member.value for member in cls],
        validate_strings=True,
    )
