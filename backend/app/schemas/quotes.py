from datetime import date, datetime
from decimal import Decimal
from typing import Any, List, Optional

from pydantic import BaseModel, Field

from app.schemas.common import Num, ORMModel


class LineRiskOut(BaseModel):
    line_id: int
    applicable_limit: Num
    points_over: Num
    is_violating: bool
    reason: Optional[str]
    requested_pct: Num
    limit_source: str
    excess_amount: Num
    status: str
    approval_hint: str
    explanation: str


class RiskOut(BaseModel):
    line_results: List[LineRiskOut]
    blended_score: Num
    required_approval_level: str
    reasons: List[str]
    weighted_excess_pct: Num
    excess_discount_amount: Num
    worst_points_over: Num
    summary: str
    level_label: str


class QuoteLineCreate(BaseModel):
    product_id: int
    quantity: int = Field(ge=1, le=100000)
    discount_pct: Num = Field(default=Decimal("0"), ge=0, le=100)
    variant_id: Optional[int] = None
    subscription_plan_id: Optional[int] = None
    is_recurring: Optional[bool] = None
    description: Optional[str] = Field(default=None, max_length=255)


class QuoteLineUpdate(BaseModel):
    quantity: Optional[int] = Field(default=None, ge=1, le=100000)
    discount_pct: Optional[Num] = Field(default=None, ge=0, le=100)
    description: Optional[str] = Field(default=None, max_length=255)
    subscription_plan_id: Optional[int] = None
    is_recurring: Optional[bool] = None


class QuoteCreate(BaseModel):
    customer_id: int
    owner_user_id: Optional[int] = None
    lines: List[QuoteLineCreate] = []
    order_discount_pct: Num = Field(default=Decimal("0"), ge=0, le=100)
    valid_until: Optional[date] = None
    promised_delivery_date: Optional[date] = None
    notes: Optional[str] = None
    # accepted for backwards compatibility with the old client; ignored (owner comes from auth)
    rep_name: Optional[str] = None


class QuoteUpdate(BaseModel):
    order_discount_pct: Optional[Num] = Field(default=None, ge=0, le=100)
    valid_until: Optional[date] = None
    promised_delivery_date: Optional[date] = None
    notes: Optional[str] = None
    owner_user_id: Optional[int] = None


class QuoteLineOut(BaseModel):
    id: int
    product_id: int
    product_name: str
    sku: Optional[str] = None
    variant_id: Optional[int] = None
    variant_name: Optional[str] = None
    description: Optional[str] = None
    quantity: int
    unit_price: Num
    unit_cost: Num
    discount_pct: Num
    tax_rate_pct: Num
    line_value: Num
    line_total: Num
    tax_amount: Num
    margin_amount: Num
    margin_pct: Num
    is_recurring: bool
    subscription_plan_id: Optional[int] = None
    subscription_plan_name: Optional[str] = None
    billing_interval: Optional[str] = None
    allowed_discount_pct: Num = Decimal("0")
    limit_source: str = ""
    points_over: Num = Decimal("0")
    line_status: str = "within_limit"
    explanation: str = ""
    comment_count: int = 0
    stock_available: Optional[int] = None


class ApprovalRequestOut(ORMModel):
    id: int
    quote_id: int
    quote_version: int
    required_level: str
    status: str
    current_step: Optional[str]
    risk_summary: Optional[str]
    created_at: datetime
    resolved_at: Optional[datetime]
    expires_at: Optional[datetime]
    is_stale: bool = False


class ApprovalActionOut(ORMModel):
    id: int
    quote_id: int
    approval_request_id: Optional[int]
    step: str
    action: str
    actor: str
    actor_user_id: Optional[int]
    reason: Optional[str]
    timestamp: datetime


class CounterProposalOut(ORMModel):
    id: int
    quote_id: int
    submitted_by: str
    proposed_lines: List[Any]
    message: Optional[str]
    status: str
    approval_request_id: Optional[int]
    created_at: datetime
    resolved_at: Optional[datetime]


class LineCommentOut(ORMModel):
    id: int
    quote_line_id: int
    author_type: str
    author_name: str
    comment: str
    is_internal: bool
    created_at: datetime


class QuoteListItem(BaseModel):
    id: int
    quote_number: Optional[str]
    customer_id: int
    customer_name: str
    owner_user_id: Optional[int]
    owner_name: Optional[str]
    status: str
    version: int
    total: Num
    margin_pct: Num
    risk_score: Optional[Num]
    required_approval_level: Optional[str]
    current_approval_step: Optional[str]
    fulfillment_status: str
    billing_status: str
    order_number: Optional[str]
    valid_until: Optional[date]
    promised_delivery_date: Optional[date]
    created_at: Optional[datetime]
    last_activity_at: Optional[datetime]
    line_count: int = 0
    has_recurring: bool = False


class QuoteDetail(QuoteListItem):
    approved_version: Optional[int]
    approval_valid: bool
    currency: str
    order_discount_pct: Num
    subtotal: Num
    discount_total: Num
    tax_total: Num
    margin_amount: Num
    expected_delivery_date: Optional[date]
    actual_delivery_date: Optional[date]
    notes: Optional[str]
    sent_at: Optional[datetime]
    confirmed_at: Optional[datetime]
    risk_reasons: Optional[List[str]]
    lines: List[QuoteLineOut]
    risk: RiskOut
    approval_request: Optional[ApprovalRequestOut] = None
    counter_proposals: List[CounterProposalOut] = []
    portal_link_active: bool = False
    can_edit: bool = False
    available_actions: List[str] = []
    customer_email: Optional[str] = None
    customer_tier: Optional[str] = None


class SubmitResponse(BaseModel):
    quote: QuoteDetail
    risk_result: RiskOut


class ApprovalActionRequest(BaseModel):
    action: str = Field(pattern="^(approved|rejected|returned_for_revision)$")
    note: Optional[str] = Field(default=None, max_length=2000)
    actor: Optional[str] = None  # legacy field, ignored: the actor is the authenticated user


class ApprovalActionResponse(BaseModel):
    quote: QuoteDetail
    history: List[ApprovalActionOut]


class ApprovalHistoryOut(BaseModel):
    approval_actions: List[ApprovalActionOut]
    audit_logs: List[Any]
    requests: List[ApprovalRequestOut]


class ApprovalQueueItem(BaseModel):
    request_id: int
    quote_id: int
    quote_number: Optional[str]
    quote_version: int
    customer_name: str
    owner_name: Optional[str]
    required_level: str
    current_step: Optional[str]
    risk_summary: Optional[str]
    total: Num
    margin_pct: Num
    risk_score: Optional[Num]
    created_at: datetime
    expires_at: Optional[datetime]
    waiting_days: int


class SendQuoteResponse(BaseModel):
    quote: QuoteDetail
    portal_url: str
    token_expires_at: datetime
    email_status: str
    email_to: Optional[str]


class RevisionOut(ORMModel):
    id: int
    version: int
    reason: Optional[str]
    created_by_user_id: Optional[int]
    created_at: datetime
    snapshot: Any


class RepCommentCreate(BaseModel):
    comment: str = Field(min_length=1, max_length=4000)
    is_internal: bool = False


class NegotiationOut(BaseModel):
    comments: List[LineCommentOut]
    counter_proposals: List[CounterProposalOut]
