from datetime import date, datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field

from app.schemas.common import Num


class PortalComment(BaseModel):
    id: int
    quote_line_id: int
    author_type: str
    author_name: str
    comment: str
    created_at: datetime


class PortalLine(BaseModel):
    id: int
    product_id: int
    product_name: str
    description: Optional[str]
    sku: Optional[str]
    quantity: int
    unit_price: Num
    discount_pct: Num
    line_value: Num
    line_total: Num
    tax_rate_pct: Num
    is_recurring: bool
    billing_interval: Optional[str]
    comments: List[PortalComment]


class PortalHistoryItem(BaseModel):
    id: int
    status: str
    message: Optional[str]
    proposed_lines: Any
    created_at: datetime
    resolved_at: Optional[datetime]


class PortalQuote(BaseModel):
    quote_id: int
    quote_number: Optional[str]
    status: str
    customer_name: str
    rep_name: Optional[str]
    currency: str
    subtotal: Num
    discount_total: Num
    tax_total: Num
    total: Num
    order_discount_pct: Num
    valid_until: Optional[date]
    promised_delivery_date: Optional[date]
    order_number: Optional[str]
    can_confirm: bool
    can_negotiate: bool
    pending_review: bool
    lines: List[PortalLine]
    history: List[PortalHistoryItem]


class PortalQuoteSummary(BaseModel):
    quote_id: int
    quote_number: Optional[str]
    status: str
    total: Num
    currency: str
    valid_until: Optional[date]
    created_at: Optional[datetime]
    order_number: Optional[str]


class CommentCreate(BaseModel):
    comment: str = Field(min_length=1, max_length=4000)


class ProposedLine(BaseModel):
    quote_line_id: int
    proposed_discount_pct: Optional[Num] = Field(default=None, ge=0, le=100)
    proposed_quantity: Optional[int] = Field(default=None, ge=1)


class CounterProposalRequest(BaseModel):
    proposed_lines: List[ProposedLine] = Field(min_length=1)
    message: Optional[str] = Field(default=None, max_length=2000)


class PortalCounterProposal(BaseModel):
    id: int
    quote_id: int
    submitted_by: str
    proposed_lines: Any
    status: str
    created_at: datetime


class PortalQuoteState(BaseModel):
    quote_id: int
    status: str  # internal status value; the customer UI uses PortalQuote.status
    required_approval_level: Optional[str]
    current_approval_step: Optional[str]


class CounterProposalResult(BaseModel):
    quote: PortalQuoteState
    counter_proposal: PortalCounterProposal
    # Only whether re-approval is needed is exposed - never the internal reasons.
    risk_result: Optional[dict] = None
    customer_status: str


class PortalConfirmResult(BaseModel):
    quote_id: int
    status: str
    order_number: Optional[str]
