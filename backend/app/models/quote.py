import enum
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base
from app.db.mixins import TimestampMixin
from app.db.types import enum_column, money_column, pct_column


class QuoteStatus(str, enum.Enum):
    draft = "draft"
    pending_approval = "pending_approval"
    approved = "approved"
    rejected = "rejected"
    revision_required = "revision_required"
    sent = "sent"
    under_negotiation = "under_negotiation"
    confirmed = "confirmed"
    expired = "expired"
    cancelled = "cancelled"


EDITABLE_STATUSES = frozenset({QuoteStatus.draft, QuoteStatus.revision_required})
OPEN_STATUSES = frozenset(
    {
        QuoteStatus.draft,
        QuoteStatus.pending_approval,
        QuoteStatus.approved,
        QuoteStatus.revision_required,
        QuoteStatus.sent,
        QuoteStatus.under_negotiation,
    }
)
TERMINAL_STATUSES = frozenset({QuoteStatus.rejected, QuoteStatus.expired, QuoteStatus.cancelled})


class FulfillmentStatus(str, enum.Enum):
    not_started = "not_started"
    planned = "planned"
    reserved = "reserved"
    partially_shipped = "partially_shipped"
    shipped = "shipped"
    delivered = "delivered"


class BillingStatus(str, enum.Enum):
    not_billed = "not_billed"
    partially_billed = "partially_billed"
    billed = "billed"
    paid = "paid"


class Quote(Base, TimestampMixin):
    __tablename__ = "quotes"

    id = Column(Integer, primary_key=True)
    quote_number = Column(String(32), nullable=True, unique=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    status = Column(enum_column(QuoteStatus), nullable=False, default=QuoteStatus.draft, index=True)
    version = Column(Integer, nullable=False, default=1)
    approved_version = Column(Integer, nullable=True)
    required_approval_level = Column(String(32), nullable=True)
    current_approval_step = Column(String(32), nullable=True, index=True)
    risk_score = Column(pct_column(), nullable=True)
    risk_reasons = Column(JSON, nullable=True)
    currency = Column(String(3), nullable=False, default="USD")
    order_discount_pct = Column(pct_column(), nullable=False, default=Decimal("0"))
    subtotal = Column(money_column(), nullable=False, default=Decimal("0"))
    discount_total = Column(money_column(), nullable=False, default=Decimal("0"))
    tax_total = Column(money_column(), nullable=False, default=Decimal("0"))
    total = Column(money_column(), nullable=False, default=Decimal("0"))
    margin_amount = Column(money_column(), nullable=False, default=Decimal("0"))
    margin_pct = Column(pct_column(), nullable=False, default=Decimal("0"))
    valid_until = Column(Date, nullable=True)
    promised_delivery_date = Column(Date, nullable=True)
    expected_delivery_date = Column(Date, nullable=True)
    actual_delivery_date = Column(Date, nullable=True)
    order_number = Column(String(32), nullable=True, unique=True)
    fulfillment_status = Column(
        enum_column(FulfillmentStatus), nullable=False, default=FulfillmentStatus.not_started, index=True
    )
    billing_status = Column(enum_column(BillingStatus), nullable=False, default=BillingStatus.not_billed, index=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    last_activity_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    notes = Column(Text, nullable=True)

    customer = relationship("Customer")
    owner = relationship("User", foreign_keys=[owner_user_id])
    lines = relationship(
        "QuoteLine", back_populates="quote", cascade="all, delete-orphan", order_by="QuoteLine.id"
    )
    revisions = relationship("QuoteRevision", back_populates="quote", cascade="all, delete-orphan")

    @property
    def is_editable(self) -> bool:
        return self.status in EDITABLE_STATUSES


class QuoteLine(Base, TimestampMixin):
    __tablename__ = "quote_lines"

    id = Column(Integer, primary_key=True)
    quote_id = Column(Integer, ForeignKey("quotes.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    variant_id = Column(Integer, ForeignKey("product_variants.id"), nullable=True)
    description = Column(String(255), nullable=True)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(money_column(), nullable=False, default=Decimal("0"))
    unit_cost = Column(money_column(), nullable=False, default=Decimal("0"))
    discount_pct = Column(pct_column(), nullable=False, default=Decimal("0"))
    tax_rate_pct = Column(pct_column(), nullable=False, default=Decimal("0"))
    # Pre-discount value (unit_price * quantity); kept for compatibility.
    line_value = Column(money_column(), nullable=False, default=Decimal("0"))
    # Post-discount, pre-tax value.
    line_total = Column(money_column(), nullable=False, default=Decimal("0"))
    is_recurring = Column(Boolean, nullable=False, default=False)
    subscription_plan_id = Column(Integer, ForeignKey("subscription_plans.id"), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)

    quote = relationship("Quote", back_populates="lines")
    product = relationship("Product")
    variant = relationship("ProductVariant")
    subscription_plan = relationship("SubscriptionPlan")


class QuoteRevision(Base):
    """Immutable snapshot taken whenever a quote's version increments."""

    __tablename__ = "quote_revisions"

    id = Column(Integer, primary_key=True)
    quote_id = Column(Integer, ForeignKey("quotes.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    snapshot = Column(JSON, nullable=False)
    reason = Column(String(255), nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    quote = relationship("Quote", back_populates="revisions")
