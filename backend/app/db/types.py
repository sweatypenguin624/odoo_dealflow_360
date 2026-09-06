"""Column helpers shared by the models."""

from sqlalchemy import Enum, Numeric


def enum_column(enum_cls, length: int = 32):
    """Store enums as plain VARCHAR (portable, extensible without ALTER TYPE)."""
    return Enum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda e: [m.value for m in e],
        name=f"{enum_cls.__name__.lower()}_str",
    )


def money_column():
    return Numeric(14, 2)


def pct_column():
    return Numeric(6, 2)
