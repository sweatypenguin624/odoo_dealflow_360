from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


class ApprovalAction(Base):
    __tablename__ = "approval_actions"

    id = Column(Integer, primary_key=True)
    quote_id = Column(Integer, ForeignKey("quotes.id"), nullable=False)
    step = Column(String, nullable=False)
    action = Column(String, nullable=False)
    actor = Column(String, nullable=False)
    reason = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    quote = relationship("Quote")
