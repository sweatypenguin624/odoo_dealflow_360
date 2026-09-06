from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.db.base import Base


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key = Column(String(64), primary_key=True)
    value = Column(String(255), nullable=False)
    value_type = Column(String(16), nullable=False, default="str")  # str|int|float|bool
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    updated_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)


class NumberSequence(Base):
    """Concurrency-safe document numbering (SELECT ... FOR UPDATE per row)."""

    __tablename__ = "number_sequences"

    name = Column(String(32), primary_key=True)
    prefix = Column(String(16), nullable=False)
    next_value = Column(Integer, nullable=False)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("key", "scope", name="uq_idempotency_key_scope"),)

    id = Column(Integer, primary_key=True)
    key = Column(String(128), nullable=False)
    scope = Column(String(128), nullable=False)
    user_id = Column(Integer, nullable=True)
    response_status = Column(Integer, nullable=False)
    response_body = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
