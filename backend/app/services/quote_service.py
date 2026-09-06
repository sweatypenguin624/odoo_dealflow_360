"""Quotation domain service: creation, editing, totals, versioning and
the state machine. Approval routing lives in approval_service; the
customer side lives in portal_service. Everything here is authoritative -
prices, discounts limits and totals are never accepted from a client.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable, List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Query, Session, joinedload, selectinload

from app.core.errors import NotFoundError, PermissionDeniedError, StateTransitionError, ValidationError
from app.core.money import D, HUNDRED, money, pct, ratio_pct
from app.core.permissions import Permission, Role, has_permission
from app.models import (
    ApprovalRequest,
    ApprovalRequestStatus,
    BillingStatus,
    Customer,
    EDITABLE_STATUSES,
    FulfillmentStatus,
    Product,
    ProductType,
    ProductVariant,
    Quote,
    QuoteLine,
    QuoteRevision,
    QuoteStatus,
    SubscriptionPlan,
    User,
)
from app.services import audit_service, discount_service, pricing_service, settings_service
from app.services.numbering import next_number
from app.services.risk_engine import QuoteRiskResult, evaluate_quote

# Legal transitions. Anything not listed is rejected with a 409.
TRANSITIONS = {
    QuoteStatus.draft: {QuoteStatus.pending_approval, QuoteStatus.approved, QuoteStatus.cancelled, QuoteStatus.expired},
    QuoteStatus.revision_required: {QuoteStatus.pending_approval, QuoteStatus.approved, QuoteStatus.cancelled, QuoteStatus.expired},
    QuoteStatus.pending_approval: {
        QuoteStatus.approved, QuoteStatus.rejected, QuoteStatus.revision_required, QuoteStatus.sent, QuoteStatus.cancelled,
        QuoteStatus.expired, QuoteStatus.draft,
    },
    QuoteStatus.approved: {QuoteStatus.sent, QuoteStatus.draft, QuoteStatus.cancelled, QuoteStatus.expired, QuoteStatus.confirmed},
    QuoteStatus.sent: {QuoteStatus.under_negotiation, QuoteStatus.pending_approval, QuoteStatus.confirmed, QuoteStatus.draft, QuoteStatus.cancelled, QuoteStatus.expired},
    QuoteStatus.under_negotiation: {QuoteStatus.pending_approval, QuoteStatus.sent, QuoteStatus.confirmed, QuoteStatus.draft, QuoteStatus.cancelled, QuoteStatus.expired},
    QuoteStatus.rejected: {QuoteStatus.draft},
    QuoteStatus.expired: {QuoteStatus.draft},
    QuoteStatus.cancelled: set(),
    QuoteStatus.confirmed: set(),
}


def now() -> datetime:
    return datetime.now(timezone.utc)


def transition(quote: Quote, new_status: QuoteStatus) -> None:
    if new_status == quote.status:
        return
    allowed = TRANSITIONS.get(quote.status, set())
    if new_status not in allowed:
        raise StateTransitionError(
            f"A quotation that is {quote.status.value.replace('_', ' ')} cannot move to {new_status.value.replace('_', ' ')}.",
            code="invalid_transition",
        )
    quote.status = new_status
    quote.last_activity_at = now()


# ---------------------------------------------------------------- loading / visibility


def load_quote(db: Session, quote_id: int) -> Quote:
    quote = (
        db.query(Quote)
        .options(
            joinedload(Quote.customer).joinedload(Customer.tier),
            joinedload(Quote.owner),
            selectinload(Quote.lines).joinedload(QuoteLine.product).joinedload(Product.category),
            selectinload(Quote.lines).joinedload(QuoteLine.variant),
            selectinload(Quote.lines).joinedload(QuoteLine.subscription_plan),
        )
        .populate_existing()
        .filter(Quote.id == quote_id)
        .first()
    )
    if quote is None:
        raise NotFoundError("Quotation not found")
    return quote


def can_view(quote: Quote, user: User) -> bool:
    if user.role in (Role.admin, Role.sales_manager, Role.finance):
        return True
    if user.role == Role.sales_rep:
        return quote.owner_user_id == user.id or (quote.customer and quote.customer.owner_user_id == user.id)
    return False


def assert_can_view(quote: Quote, user: User) -> None:
    if not can_view(quote, user):
        raise PermissionDeniedError("You don't have access to this quotation.")


def visible_quotes_query(db: Session, user: User) -> Query:
    query = db.query(Quote).options(joinedload(Quote.customer), joinedload(Quote.owner))
    if user.role == Role.sales_rep:
        owned_customers = db.query(Customer.id).filter(Customer.owner_user_id == user.id)
        query = query.filter(or_(Quote.owner_user_id == user.id, Quote.customer_id.in_(owned_customers)))
    return query


def assert_editable(quote: Quote, user: User) -> None:
    if quote.status not in EDITABLE_STATUSES:
        raise StateTransitionError(
            f"This quotation is {quote.status.value.replace('_', ' ')} and can no longer be edited. "
            "Use 'Revise' to open a new version.",
            code="not_editable",
        )
    if not has_permission(user.role, Permission.quote_edit):
        raise PermissionDeniedError("You don't have permission to edit quotations.")
    if user.role == Role.sales_rep and quote.owner_user_id not in (None, user.id):
        raise PermissionDeniedError("You can only edit quotations you own.")


# ---------------------------------------------------------------- totals & risk


def line_tax_amount(line: QuoteLine, order_discount_pct: Decimal) -> Decimal:
    net = D(line.line_total) * (HUNDRED - D(order_discount_pct)) / HUNDRED
    return money(net * D(line.tax_rate_pct) / HUNDRED)


def line_margin_amount(line: QuoteLine, order_discount_pct: Decimal) -> Decimal:
    net = D(line.line_total) * (HUNDRED - D(order_discount_pct)) / HUNDRED
    return money(net - D(line.unit_cost) * line.quantity)


def recalculate(db: Session, quote: Quote) -> None:
    subtotal = Decimal("0")
    after_line_discounts = Decimal("0")
    tax_total = Decimal("0")
    margin = Decimal("0")
    order_disc = D(quote.order_discount_pct)
    for line in quote.lines:
        line.line_value = money(D(line.unit_price) * line.quantity)
        line.line_total = money(D(line.line_value) * (HUNDRED - D(line.discount_pct)) / HUNDRED)
        subtotal += line.line_value
        after_line_discounts += line.line_total
        tax_total += line_tax_amount(line, order_disc)
        margin += line_margin_amount(line, order_disc)
    net = money(after_line_discounts * (HUNDRED - order_disc) / HUNDRED)
    quote.subtotal = money(subtotal)
    quote.discount_total = money(subtotal - net)
    quote.tax_total = money(tax_total)
    quote.total = money(net + tax_total)
    quote.margin_amount = money(margin)
    quote.margin_pct = ratio_pct(margin, net)
    risk = evaluate_risk(db, quote)
    quote.risk_score = risk.blended_score
    quote.last_activity_at = now()


def evaluate_risk(db: Session, quote: Quote) -> QuoteRiskResult:
    inputs = discount_service.build_line_inputs(db, quote)
    return evaluate_quote(inputs, settings_service.risk_policy(db))


# ---------------------------------------------------------------- snapshots / versions


def snapshot(quote: Quote) -> dict:
    return {
        "quote_number": quote.quote_number,
        "version": quote.version,
        "status": quote.status.value,
        "customer_id": quote.customer_id,
        "order_discount_pct": str(quote.order_discount_pct),
        "subtotal": str(quote.subtotal),
        "total": str(quote.total),
        "margin_pct": str(quote.margin_pct),
        "promised_delivery_date": quote.promised_delivery_date.isoformat() if quote.promised_delivery_date else None,
        "lines": [
            {
                "id": l.id,
                "product_id": l.product_id,
                "variant_id": l.variant_id,
                "description": l.description,
                "quantity": l.quantity,
                "unit_price": str(l.unit_price),
                "discount_pct": str(l.discount_pct),
                "line_total": str(l.line_total),
                "is_recurring": l.is_recurring,
                "subscription_plan_id": l.subscription_plan_id,
            }
            for l in quote.lines
        ],
    }


def save_revision(db: Session, quote: Quote, actor: Optional[User], reason: str) -> QuoteRevision:
    revision = QuoteRevision(
        quote_id=quote.id, version=quote.version, snapshot=snapshot(quote), reason=reason,
        created_by_user_id=actor.id if actor else None,
    )
    db.add(revision)
    return revision


def supersede_pending_approvals(db: Session, quote: Quote, reason: str) -> None:
    pending = (
        db.query(ApprovalRequest)
        .filter(ApprovalRequest.quote_id == quote.id, ApprovalRequest.status == ApprovalRequestStatus.pending)
        .all()
    )
    for request in pending:
        request.status = ApprovalRequestStatus.superseded
        request.resolved_at = now()
        request.risk_summary = (request.risk_summary or "") + f" [superseded: {reason}]"


def open_new_version(db: Session, quote: Quote, actor: Optional[User], reason: str) -> None:
    """A material change after approval: bump the version so any approval
    that referenced the old version is no longer valid, and drop pending
    requests. The quote must then be re-evaluated and re-approved."""
    quote.version += 1
    supersede_pending_approvals(db, quote, reason)
    quote.required_approval_level = None
    quote.current_approval_step = None
    quote.risk_reasons = None
    quote.last_activity_at = now()


def approval_is_valid(quote: Quote) -> bool:
    return quote.approved_version is not None and quote.approved_version == quote.version


# ---------------------------------------------------------------- create / edit


def _resolve_owner(db: Session, actor: User, owner_user_id: Optional[int]) -> int:
    if owner_user_id is None or actor.role == Role.sales_rep:
        return actor.id
    owner = db.get(User, owner_user_id)
    if owner is None or not owner.is_active:
        raise NotFoundError("Owner user not found")
    return owner.id


def create_quote(
    db: Session,
    actor: User,
    *,
    customer_id: int,
    lines: Iterable,
    owner_user_id: Optional[int] = None,
    order_discount_pct: Decimal = Decimal("0"),
    valid_until: Optional[date] = None,
    promised_delivery_date: Optional[date] = None,
    notes: Optional[str] = None,
) -> Quote:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise NotFoundError("Customer not found")
    if not customer.is_active:
        raise ValidationError("This customer is archived. Restore it before quoting.")
    quote = Quote(
        quote_number=next_number(db, "quote"),
        customer_id=customer.id,
        owner_user_id=_resolve_owner(db, actor, owner_user_id),
        status=QuoteStatus.draft,
        currency=customer.currency or "USD",
        order_discount_pct=pct(order_discount_pct),
        valid_until=valid_until or (date.today() + timedelta(days=settings_service.get_setting(db, "quote_valid_days"))),
        promised_delivery_date=promised_delivery_date,
        notes=notes,
        last_activity_at=now(),
    )
    db.add(quote)
    db.flush()
    for spec in lines:
        _add_line(db, quote, customer, spec)
    quote = load_quote(db, quote.id)
    recalculate(db, quote)
    audit_service.record(
        db, "quote_created", actor=actor, quote_id=quote.id, entity_type="quote", entity_id=quote.id,
        after={"quote_number": quote.quote_number, "customer_id": customer.id, "lines": len(quote.lines), "total": str(quote.total)},
    )
    return quote


def _add_line(db: Session, quote: Quote, customer: Customer, spec) -> QuoteLine:
    product = db.get(Product, spec.product_id)
    if product is None:
        raise NotFoundError(f"Product {spec.product_id} not found")
    if not product.is_sellable:
        raise ValidationError(f"{product.name} is not available for sale.")
    variant = None
    if getattr(spec, "variant_id", None):
        variant = db.get(ProductVariant, spec.variant_id)
        if variant is None or variant.product_id != product.id or not variant.is_active:
            raise NotFoundError("Variant not found on this product")
    plan = None
    if getattr(spec, "subscription_plan_id", None):
        plan = db.get(SubscriptionPlan, spec.subscription_plan_id)
        if plan is None or plan.product_id != product.id or not plan.is_active:
            raise NotFoundError("Subscription plan not found for this product")
    is_recurring = spec.is_recurring if getattr(spec, "is_recurring", None) is not None else (plan is not None or product.product_type == ProductType.recurring)
    if is_recurring and plan is None:
        plan = (
            db.query(SubscriptionPlan)
            .filter(SubscriptionPlan.product_id == product.id, SubscriptionPlan.is_active.is_(True))
            .order_by(SubscriptionPlan.id)
            .first()
        )
        if plan is None and product.product_type == ProductType.recurring:
            raise ValidationError(f"{product.name} is a recurring product but has no active subscription plan.")
    if plan is not None:
        is_recurring = True
    if is_recurring and product.product_type == ProductType.one_time:
        raise ValidationError(f"{product.name} cannot be sold as a subscription.")

    resolved = pricing_service.resolve_price(db, product, customer, spec.quantity, variant)
    unit_price = money(plan.price_per_interval) if plan is not None else resolved.unit_price
    line = QuoteLine(
        quote_id=quote.id,
        product_id=product.id,
        variant_id=variant.id if variant else None,
        description=getattr(spec, "description", None) or (f"{product.name} — {variant.name}" if variant else product.name),
        quantity=spec.quantity,
        unit_price=unit_price,
        unit_cost=resolved.unit_cost,
        discount_pct=pct(spec.discount_pct),
        tax_rate_pct=D(product.tax_rate_pct),
        is_recurring=bool(is_recurring),
        subscription_plan_id=plan.id if plan else None,
        sort_order=len(quote.lines),
    )
    line.line_value = money(D(unit_price) * line.quantity)
    line.line_total = money(D(line.line_value) * (HUNDRED - D(line.discount_pct)) / HUNDRED)
    quote.lines.append(line)
    db.flush()
    return line


def add_line(db: Session, quote: Quote, actor: User, spec) -> QuoteLine:
    assert_editable(quote, actor)
    line = _add_line(db, quote, quote.customer, spec)
    db.refresh(quote)
    quote = load_quote(db, quote.id)
    recalculate(db, quote)
    audit_service.record(
        db, "quote_line_added", actor=actor, quote_id=quote.id, entity_type="quote_line", entity_id=line.id,
        after={"product_id": line.product_id, "quantity": line.quantity, "discount_pct": str(line.discount_pct), "unit_price": str(line.unit_price)},
    )
    return line


def update_line(db: Session, quote: Quote, actor: User, line_id: int, changes: dict) -> QuoteLine:
    assert_editable(quote, actor)
    line = next((l for l in quote.lines if l.id == line_id), None)
    if line is None:
        raise NotFoundError("Quote line not found on this quote")
    before = {"quantity": line.quantity, "discount_pct": str(line.discount_pct)}
    if changes.get("quantity") is not None and changes["quantity"] != line.quantity:
        line.quantity = changes["quantity"]
        # Volume price breaks may apply at the new quantity.
        resolved = pricing_service.resolve_price(db, line.product, quote.customer, line.quantity, line.variant)
        if not line.is_recurring:
            line.unit_price = resolved.unit_price
    if changes.get("discount_pct") is not None:
        line.discount_pct = pct(changes["discount_pct"])
    if changes.get("description") is not None:
        line.description = changes["description"]
    if changes.get("subscription_plan_id") is not None:
        plan = db.get(SubscriptionPlan, changes["subscription_plan_id"])
        if plan is None or plan.product_id != line.product_id:
            raise NotFoundError("Subscription plan not found for this product")
        line.subscription_plan_id = plan.id
        line.is_recurring = True
        line.unit_price = money(plan.price_per_interval)
    if changes.get("is_recurring") is False:
        line.is_recurring = False
        line.subscription_plan_id = None
        line.unit_price = pricing_service.resolve_price(db, line.product, quote.customer, line.quantity, line.variant).unit_price
    recalculate(db, quote)
    after = {"quantity": line.quantity, "discount_pct": str(line.discount_pct)}
    action = "discount_changed" if before["discount_pct"] != after["discount_pct"] else "quote_line_updated"
    audit_service.record(db, action, actor=actor, quote_id=quote.id, entity_type="quote_line", entity_id=line.id, before=before, after=after)
    return line


def remove_line(db: Session, quote: Quote, actor: User, line_id: int) -> None:
    assert_editable(quote, actor)
    line = next((l for l in quote.lines if l.id == line_id), None)
    if line is None:
        raise NotFoundError("Quote line not found on this quote")
    audit_service.record(
        db, "quote_line_removed", actor=actor, quote_id=quote.id, entity_type="quote_line", entity_id=line.id,
        before={"product_id": line.product_id, "quantity": line.quantity, "discount_pct": str(line.discount_pct)},
    )
    quote.lines.remove(line)
    db.delete(line)
    db.flush()
    recalculate(db, quote)


def update_header(db: Session, quote: Quote, actor: User, changes: dict) -> None:
    editable_keys = {"order_discount_pct", "valid_until", "promised_delivery_date", "notes", "owner_user_id"}
    material = {"order_discount_pct"} & set(k for k, v in changes.items() if v is not None)
    if material:
        assert_editable(quote, actor)
    elif quote.status in (QuoteStatus.cancelled, QuoteStatus.confirmed) and any(
        changes.get(k) is not None for k in ("valid_until", "owner_user_id")
    ):
        raise StateTransitionError("This quotation is closed and cannot be changed.", code="not_editable")
    if not has_permission(actor.role, Permission.quote_edit):
        raise PermissionDeniedError("You don't have permission to edit quotations.")
    if actor.role == Role.sales_rep and quote.owner_user_id not in (None, actor.id):
        raise PermissionDeniedError("You can only edit quotations you own.")
    before = {k: str(getattr(quote, k)) for k in editable_keys}
    for key in editable_keys:
        if key in changes and changes[key] is not None:
            if key == "owner_user_id":
                if actor.role == Role.sales_rep:
                    continue
                if db.get(User, changes[key]) is None:
                    raise NotFoundError("Owner user not found")
            setattr(quote, key, pct(changes[key]) if key == "order_discount_pct" else changes[key])
    recalculate(db, quote)
    after = {k: str(getattr(quote, k)) for k in editable_keys}
    audit_service.record(db, "quote_updated", actor=actor, quote_id=quote.id, entity_type="quote", entity_id=quote.id, before=before, after=after)


# ---------------------------------------------------------------- lifecycle actions


def revise(db: Session, quote: Quote, actor: User, reason: Optional[str] = None) -> None:
    """Reopen an approved / sent / rejected / expired quote for editing as
    a new version. Prior approvals are invalidated."""
    if not has_permission(actor.role, Permission.quote_edit):
        raise PermissionDeniedError("You don't have permission to edit quotations.")
    if actor.role == Role.sales_rep and quote.owner_user_id not in (None, actor.id):
        raise PermissionDeniedError("You can only revise quotations you own.")
    if quote.status in EDITABLE_STATUSES:
        raise StateTransitionError("This quotation is already open for editing.", code="already_editable")
    transition(quote, QuoteStatus.draft)
    open_new_version(db, quote, actor, reason or "revised")
    recalculate(db, quote)
    audit_service.record(
        db, "quote_revised", actor=actor, quote_id=quote.id, entity_type="quote", entity_id=quote.id,
        reason=reason or f"Opened version {quote.version} for editing; prior approval invalidated",
    )


def cancel(db: Session, quote: Quote, actor: User, reason: Optional[str] = None) -> None:
    if not has_permission(actor.role, Permission.quote_cancel):
        raise PermissionDeniedError("You don't have permission to cancel quotations.")
    if actor.role == Role.sales_rep and quote.owner_user_id not in (None, actor.id):
        raise PermissionDeniedError("You can only cancel quotations you own.")
    transition(quote, QuoteStatus.cancelled)
    supersede_pending_approvals(db, quote, "quote cancelled")
    audit_service.record(db, "quote_cancelled", actor=actor, quote_id=quote.id, entity_type="quote", entity_id=quote.id, reason=reason)


def expire_stale_quotes(db: Session, as_of: Optional[date] = None) -> int:
    as_of = as_of or date.today()
    expirable = (
        db.query(Quote)
        .filter(
            Quote.valid_until.isnot(None),
            Quote.valid_until < as_of,
            Quote.status.in_([QuoteStatus.draft, QuoteStatus.approved, QuoteStatus.sent, QuoteStatus.under_negotiation, QuoteStatus.revision_required, QuoteStatus.pending_approval]),
        )
        .all()
    )
    for quote in expirable:
        transition(quote, QuoteStatus.expired)
        supersede_pending_approvals(db, quote, "quote expired")
        audit_service.record(db, "quote_expired", quote_id=quote.id, entity_type="quote", entity_id=quote.id, reason=f"Valid until {quote.valid_until.isoformat()}")
    return len(expirable)


def available_actions(quote: Quote, user: User) -> List[str]:
    actions: List[str] = []
    owner_ok = user.role != Role.sales_rep or quote.owner_user_id in (None, user.id)
    if quote.status in EDITABLE_STATUSES and owner_ok and has_permission(user.role, Permission.quote_submit):
        actions.append("submit")
    if quote.status in EDITABLE_STATUSES and owner_ok:
        actions.append("edit")
    if quote.status == QuoteStatus.approved and owner_ok and has_permission(user.role, Permission.quote_send):
        actions.append("send")
    if quote.status in (QuoteStatus.sent, QuoteStatus.under_negotiation) and owner_ok and has_permission(user.role, Permission.quote_send):
        actions.append("resend")
    if quote.status in (QuoteStatus.approved, QuoteStatus.sent, QuoteStatus.under_negotiation, QuoteStatus.rejected, QuoteStatus.expired, QuoteStatus.pending_approval) and owner_ok and has_permission(user.role, Permission.quote_edit):
        actions.append("revise")
    if quote.status not in (QuoteStatus.cancelled, QuoteStatus.confirmed) and owner_ok and has_permission(user.role, Permission.quote_cancel):
        actions.append("cancel")
    if quote.status == QuoteStatus.pending_approval:
        step = quote.current_approval_step
        if (step == "manager" and has_permission(user.role, Permission.approval_manager)) or (
            step == "finance" and has_permission(user.role, Permission.approval_finance)
        ):
            if quote.owner_user_id != user.id or user.role == Role.admin:
                actions.append("approve")
    if quote.status == QuoteStatus.confirmed:
        actions.append("fulfill")
    return actions
