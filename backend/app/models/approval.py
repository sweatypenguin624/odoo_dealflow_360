import enum

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base
from app.db.types import enum_column


class ApprovalRequestStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    returned = "returned"
    superseded = "superseded"
    expired = "expired"


class ApprovalRequest(Base):
    """One approval workflow instance, bound to a specific quote version.

    Any change to the quote after the request was raised bumps the quote
    version; the request is then superseded and a new one raised on
    resubmission, so stale versions can never be approved.
    """

    __tablename__ = "approval_requests"

    id = Column(Integer, primary_key=True)
    quote_id = Column(Integer, ForeignKey("quotes.id"), nullable=False, index=True)
    quote_version = Column(Integer, nullable=False)
    required_level = Column(String(32), nullable=False)
    status = Column(
        enum_column(ApprovalRequestStatus), nullable=False, default=ApprovalRequestStatus.pending, index=True
    )
    current_step = Column(String(32), nullable=True)
    risk_summary = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    quote = relationship("Quote")
    actions = relationship("ApprovalAction", back_populates="request", order_by="ApprovalAction.timestamp")


class ApprovalAction(Base):
    __tablename__ = "approval_actions"

    id = Column(Integer, primary_key=True)
    quote_id = Column(Integer, ForeignKey("quotes.id"), nullable=False, index=True)
    approval_request_id = Column(Integer, ForeignKey("approval_requests.id"), nullable=True, index=True)
    step = Column(String(32), nullable=False)
    action = Column(String(32), nullable=False)
    actor = Column(String(255), nullable=False)
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    reason = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    quote = relationship("Quote")
    request = relationship("ApprovalRequest", back_populates="actions")
    actor_user = relationship("User")
