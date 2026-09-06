"""Build API DTOs for quotes. Kept out of the router so the same detail
shape is returned from every endpoint that touches a quote."""

from typing import Dict, List, Optional

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.core.money import D, HUNDRED, money, ratio_pct
from app.models import CounterProposal, LineComment, Quote, QuoteLine, Stock, User
from app.schemas.quotes import (
    ApprovalRequestOut,
    CounterProposalOut,
    LineRiskOut,
    QuoteDetail,
    QuoteLineOut,
    QuoteListItem,
    RiskOut,
)
from app.services import approval_service, portal_service, quote_service
from app.services.risk_engine import LEVEL_LABELS, QuoteRiskResult


def risk_out(result: QuoteRiskResult) -> RiskOut:
    return RiskOut(
        line_results=[LineRiskOut(**r.__dict__) for r in result.line_results],
        blended_score=result.blended_score,
        required_approval_level=result.required_approval_level,
        reasons=result.reasons,
        weighted_excess_pct=result.weighted_excess_pct,
        excess_discount_amount=result.excess_discount_amount,
        worst_points_over=result.worst_points_over,
        summary=result.summary,
        level_label=LEVEL_LABELS.get(result.required_approval_level, result.required_approval_level),
    )


def list_item(quote: Quote, line_count: int = 0, has_recurring: bool = False) -> QuoteListItem:
    return QuoteListItem(
        id=quote.id,
        quote_number=quote.quote_number,
        customer_id=quote.customer_id,
        customer_name=quote.customer.name,
        owner_user_id=quote.owner_user_id,
        owner_name=quote.owner.full_name if quote.owner else None,
        status=quote.status.value,
        version=quote.version,
        total=D(quote.total),
        margin_pct=D(quote.margin_pct),
        risk_score=D(quote.risk_score) if quote.risk_score is not None else None,
        required_approval_level=quote.required_approval_level,
        current_approval_step=quote.current_approval_step,
        fulfillment_status=quote.fulfillment_status.value,
        billing_status=quote.billing_status.value,
        order_number=quote.order_number,
        valid_until=quote.valid_until,
        promised_delivery_date=quote.promised_delivery_date,
        created_at=quote.created_at,
        last_activity_at=quote.last_activity_at,
        line_count=line_count,
        has_recurring=has_recurring,
    )


def line_stats(db: Session, quote_ids: List[int]) -> Dict[int, tuple]:
    if not quote_ids:
        return {}
    # Count recurring lines rather than aggregating the boolean itself:
    # Postgres has no max(boolean), and this reads the same on every engine.
    rows = (
        db.query(
            QuoteLine.quote_id,
            func.count(QuoteLine.id),
            func.sum(case((QuoteLine.is_recurring.is_(True), 1), else_=0)),
        )
        .filter(QuoteLine.quote_id.in_(quote_ids))
        .group_by(QuoteLine.quote_id)
        .all()
    )
    return {qid: (count, bool(rec)) for qid, count, rec in rows}


def detail(db: Session, quote: Quote, user: User) -> QuoteDetail:
    risk = quote_service.evaluate_risk(db, quote)
    risk_by_line = {r.line_id: r for r in risk.line_results}
    line_ids = [l.id for l in quote.lines]
    comment_counts = dict(
        db.query(LineComment.quote_line_id, func.count(LineComment.id))
        .filter(LineComment.quote_line_id.in_(line_ids or [0]))
        .group_by(LineComment.quote_line_id)
        .all()
    )
    stock = dict(
        db.query(Stock.product_id, func.coalesce(func.sum(Stock.quantity_on_hand - Stock.quantity_reserved), 0))
        .filter(Stock.product_id.in_([l.product_id for l in quote.lines] or [0]))
        .group_by(Stock.product_id)
        .all()
    )
    order_disc = D(quote.order_discount_pct)
    lines = []
    for l in quote.lines:
        r = risk_by_line.get(l.id)
        tax = quote_service.line_tax_amount(l, order_disc)
        margin = quote_service.line_margin_amount(l, order_disc)
        net = money(D(l.line_total) * (HUNDRED - order_disc) / HUNDRED)
        lines.append(
            QuoteLineOut(
                id=l.id,
                product_id=l.product_id,
                product_name=l.product.name,
                sku=l.product.sku,
                variant_id=l.variant_id,
                variant_name=l.variant.name if l.variant else None,
                description=l.description,
                quantity=l.quantity,
                unit_price=D(l.unit_price),
                unit_cost=D(l.unit_cost),
                discount_pct=D(l.discount_pct),
                tax_rate_pct=D(l.tax_rate_pct),
                line_value=D(l.line_value),
                line_total=D(l.line_total),
                tax_amount=tax,
                margin_amount=margin,
                margin_pct=ratio_pct(margin, net),
                is_recurring=l.is_recurring,
                subscription_plan_id=l.subscription_plan_id,
                subscription_plan_name=l.subscription_plan.name if l.subscription_plan else None,
                billing_interval=l.subscription_plan.interval.value if l.subscription_plan else None,
                allowed_discount_pct=r.applicable_limit if r else D(0),
                limit_source=r.limit_source if r else "",
                points_over=r.points_over if r else D(0),
                line_status=r.status if r else "within_limit",
                explanation=r.explanation if r else "",
                comment_count=comment_counts.get(l.id, 0),
                # None means "stock doesn't apply" (subscriptions, licences,
                # services) so the UI can tell that apart from genuinely zero.
                stock_available=(int(stock.get(l.product_id, 0)) if not l.is_recurring and l.product.is_stocked else None),
            )
        )
    request = approval_service.latest_request(db, quote)
    request_out = None
    if request is not None:
        request_out = ApprovalRequestOut.model_validate(request)
        request_out.is_stale = request.quote_version != quote.version
    proposals = db.query(CounterProposal).filter(CounterProposal.quote_id == quote.id).order_by(CounterProposal.id.desc()).all()
    base = list_item(quote, len(quote.lines), any(l.is_recurring for l in quote.lines)).model_dump()
    return QuoteDetail(
        **base,
        approved_version=quote.approved_version,
        approval_valid=quote_service.approval_is_valid(quote),
        currency=quote.currency,
        order_discount_pct=D(quote.order_discount_pct),
        subtotal=D(quote.subtotal),
        discount_total=D(quote.discount_total),
        tax_total=D(quote.tax_total),
        margin_amount=D(quote.margin_amount),
        expected_delivery_date=quote.expected_delivery_date,
        actual_delivery_date=quote.actual_delivery_date,
        notes=quote.notes,
        sent_at=quote.sent_at,
        confirmed_at=quote.confirmed_at,
        risk_reasons=quote.risk_reasons,
        lines=lines,
        risk=risk_out(risk),
        approval_request=request_out,
        counter_proposals=[CounterProposalOut.model_validate(p) for p in proposals],
        portal_link_active=portal_service.active_token(db, quote) is not None,
        can_edit="edit" in quote_service.available_actions(quote, user),
        available_actions=quote_service.available_actions(quote, user),
        customer_email=quote.customer.email,
        customer_tier=quote.customer.tier.name if quote.customer.tier else None,
    )
