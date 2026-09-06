from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True)
    recipient_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    triggered_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    type = Column(String(64), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=True)
    entity_type = Column(String(32), nullable=True)
    entity_id = Column(Integer, nullable=True)
    is_read = Column(Boolean, nullable=False, default=False, index=True)
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    recipient = relationship("User", foreign_keys=[recipient_user_id])
    deliveries = relationship("NotificationDelivery", back_populates="notification", cascade="all, delete-orphan")


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"

    id = Column(Integer, primary_key=True)
    notification_id = Column(Integer, ForeignKey("notifications.id"), nullable=False, index=True)
    channel = Column(String(16), nullable=False)  # in_app | email
    status = Column(String(16), nullable=False)  # sent | failed | skipped
    recipient_address = Column(String(255), nullable=True)
    error = Column(Text, nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    notification = relationship("Notification", back_populates="deliveries")


class EmailMessage(Base):
    """Every outbound email, whatever provider actually delivered it."""

    __tablename__ = "email_messages"

    id = Column(Integer, primary_key=True)
    to_address = Column(String(255), nullable=False, index=True)
    subject = Column(String(255), nullable=False)
    body_text = Column(Text, nullable=False)
    template = Column(String(64), nullable=False, index=True)
    status = Column(String(16), nullable=False, index=True)  # sent | failed | skipped
    provider = Column(String(32), nullable=False)
    error = Column(Text, nullable=True)
    entity_type = Column(String(32), nullable=True)
    entity_id = Column(Integer, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
