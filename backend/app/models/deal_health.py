import enum

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base
from app.db.mixins import TimestampMixin
from app.db.types import enum_column


class AlertStatus(str, enum.Enum):
    open = "open"
    acknowledged = "acknowledged"
    resolved = "resolved"


class DealHealthAlert(Base, TimestampMixin):
    __tablename__ = "deal_health_alerts"

    id = Column(Integer, primary_key=True)
    quote_id = Column(Integer, ForeignKey("quotes.id"), nullable=False, index=True)
    alert_type = Column(String(32), nullable=False, index=True)
    severity = Column(String(16), nullable=False, index=True)
    message = Column(Text, nullable=False)
    status = Column(enum_column(AlertStatus), nullable=False, default=AlertStatus.open, index=True)
    dedupe_key = Column(String(128), nullable=False, index=True)
    entity_type = Column(String(32), nullable=False, default="quote")
    entity_id = Column(Integer, nullable=False)
    details = Column(JSON, nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    resolution_note = Column(Text, nullable=True)

    quote = relationship("Quote")
    actions = relationship("DealHealthAction", back_populates="alert", cascade="all, delete-orphan", order_by="DealHealthAction.id")


class DealHealthAction(Base):
    __tablename__ = "deal_health_actions"

    id = Column(Integer, primary_key=True)
    alert_id = Column(Integer, ForeignKey("deal_health_alerts.id"), nullable=False, index=True)
    action_type = Column(String(32), nullable=False)
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    actor_label = Column(String(255), nullable=False)
    note = Column(Text, nullable=True)
    recipients = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    alert = relationship("DealHealthAlert", back_populates="actions")
