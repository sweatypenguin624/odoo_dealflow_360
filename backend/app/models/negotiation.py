from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class LineComment(Base):
    __tablename__ = "line_comments"

    id = Column(Integer, primary_key=True)
    quote_line_id = Column(Integer, ForeignKey("quote_lines.id"), nullable=False, index=True)
    author_type = Column(String(16), nullable=False)  # "customer" | "rep"
    author_name = Column(String(255), nullable=False)
    author_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    comment = Column(Text, nullable=False)
    is_internal = Column(Boolean, nullable=False, default=False)  # rep-only note, hidden from customer
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    quote_line = relationship("QuoteLine")


class CounterProposal(Base):
    __tablename__ = "counter_proposals"

    id = Column(Integer, primary_key=True)
    quote_id = Column(Integer, ForeignKey("quotes.id"), nullable=False, index=True)
    submitted_by = Column(String(32), nullable=False, default="customer")
    proposed_lines = Column(JSON, nullable=False)  # [{quote_line_id, proposed_discount_pct, proposed_quantity?}]
    message = Column(Text, nullable=True)
    status = Column(String(16), nullable=False, default="pending", index=True)  # pending|accepted|rejected|superseded
    approval_request_id = Column(Integer, ForeignKey("approval_requests.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    quote = relationship("Quote")
