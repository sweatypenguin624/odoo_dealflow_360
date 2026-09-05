from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


class LineComment(Base):
    __tablename__ = "line_comments"

    id = Column(Integer, primary_key=True)
    quote_line_id = Column(Integer, ForeignKey("quote_lines.id"), nullable=False)
    author_type = Column(String, nullable=False)  # "customer" | "rep"
    author_name = Column(String, nullable=False)
    comment = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    quote_line = relationship("QuoteLine")


class CounterProposal(Base):
    __tablename__ = "counter_proposals"

    id = Column(Integer, primary_key=True)
    quote_id = Column(Integer, ForeignKey("quotes.id"), nullable=False)
    submitted_by = Column(String, nullable=False, default="customer")
    proposed_lines = Column(JSON, nullable=False)  # [{quote_line_id, proposed_discount_pct}]
    status = Column(String, nullable=False, default="pending")  # pending|accepted|superseded
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    quote = relationship("Quote")
