from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db, require_permission
from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.core.pagination import Page, PageParams, paginate_query
from app.core.permissions import Permission, Role
from app.models import (
    AuditLog,
    Customer,
    CustomerTier,
    DealHealthAlert,
    Invoice,
    InvoiceStatus,
    Payment,
    Quote,
    QuoteStatus,
    Subscription,
    OPEN_STATUSES,
    UNPAID_STATUSES,
    User,
)
from app.schemas.customers import CustomerCreate, CustomerDetailOut, CustomerHistoryOut, CustomerOut, CustomerUpdate
from app.services import audit_service, search_service
from app.services.numbering import next_number

router = APIRouter(prefix="/customers", tags=["customers"])


def _base_out(c: Customer, open_quotes: int = 0, outstanding: Decimal = Decimal("0")) -> dict:
    return dict(
        id=c.id,
        code=c.code,
        name=c.name,
        tier_id=c.tier_id,
        tier_name=c.tier.name,
        max_discount_pct=c.tier.max_discount_pct,
        owner_user_id=c.owner_user_id,
        owner_name=c.owner.full_name if c.owner else None,
        industry=c.industry,
        email=c.email,
        phone=c.phone,
        contact_name=c.contact_name,
        currency=c.currency,
        payment_terms_days=c.payment_terms_days,
        is_active=c.is_active,
        created_at=c.created_at,
        open_quote_count=open_quotes,
        outstanding_balance=outstanding,
    )


def _detail_out(c: Customer, open_quotes: int, outstanding: Decimal) -> CustomerDetailOut:
    base = _base_out(c, open_quotes, outstanding)
    return CustomerDetailOut(
        **base,
        website=c.website,
        notes=c.notes,
        billing_address_line1=c.billing_address_line1,
        billing_city=c.billing_city,
        billing_state=c.billing_state,
        billing_postal_code=c.billing_postal_code,
        billing_country=c.billing_country,
        shipping_address_line1=c.shipping_address_line1,
        shipping_city=c.shipping_city,
        shipping_state=c.shipping_state,
        shipping_postal_code=c.shipping_postal_code,
        shipping_country=c.shipping_country,
        updated_at=c.updated_at,
    )


def _get_customer(db: Session, customer_id: int) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise NotFoundError("Customer not found")
    return customer


def _stats(db: Session, customer_ids: list[int]):
    if not customer_ids:
        return {}, {}
    open_counts = dict(
        db.query(Quote.customer_id, func.count(Quote.id))
        .filter(Quote.customer_id.in_(customer_ids), Quote.status.in_(list(OPEN_STATUSES)))
        .group_by(Quote.customer_id)
        .all()
    )
    outstanding = dict(
        db.query(Invoice.customer_id, func.coalesce(func.sum(Invoice.amount - Invoice.amount_paid), 0))
        .filter(Invoice.customer_id.in_(customer_ids), Invoice.status.in_(list(UNPAID_STATUSES)))
        .group_by(Invoice.customer_id)
        .all()
    )
    return open_counts, {k: Decimal(v or 0) for k, v in outstanding.items()}


@router.get("", response_model=Page[CustomerOut])
def list_customers(
    params: PageParams = Depends(),
    q: Optional[str] = Query(None, description="Search name, code, email or contact"),
    tier_id: Optional[int] = None,
    owner_user_id: Optional[int] = None,
    is_active: Optional[bool] = True,
    mine: bool = Query(False, description="Only customers owned by the current user"),
    sort: str = Query("name", pattern="^(name|created_at|-name|-created_at)$"),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.customer_read)),
):
    query = db.query(Customer).options(joinedload(Customer.tier), joinedload(Customer.owner))
    if q:
        query = query.filter(search_service.customer_match(db, f"%{q.strip()}%"))
    if tier_id is not None:
        query = query.filter(Customer.tier_id == tier_id)
    if owner_user_id is not None:
        query = query.filter(Customer.owner_user_id == owner_user_id)
    if mine:
        query = query.filter(Customer.owner_user_id == user.id)
    if is_active is not None:
        query = query.filter(Customer.is_active.is_(is_active))
    column = getattr(Customer, sort.lstrip("-"))
    query = query.order_by(column.desc() if sort.startswith("-") else column.asc(), Customer.id)
    rows, total = paginate_query(query, params)
    open_counts, outstanding = _stats(db, [c.id for c in rows])
    items = [CustomerOut(**_base_out(c, open_counts.get(c.id, 0), outstanding.get(c.id, Decimal("0")))) for c in rows]
    return Page.build(items, total, params)


@router.post("", response_model=CustomerDetailOut, status_code=201)
def create_customer(payload: CustomerCreate, db: Session = Depends(get_db), actor: User = Depends(require_permission(Permission.customer_manage))):
    if db.get(CustomerTier, payload.tier_id) is None:
        raise NotFoundError("Customer tier not found")
    if payload.owner_user_id is not None and db.get(User, payload.owner_user_id) is None:
        raise NotFoundError("Owner user not found")
    if db.query(Customer).filter(func.lower(Customer.name) == payload.name.strip().lower()).first():
        raise ConflictError(f"A customer named '{payload.name}' already exists.")
    data = payload.model_dump()
    if data.get("owner_user_id") is None and actor.role == Role.sales_rep:
        data["owner_user_id"] = actor.id
    customer = Customer(**data, code=next_number(db, "customer"))
    db.add(customer)
    db.flush()
    audit_service.record(db, "customer_created", actor=actor, entity_type="customer", entity_id=customer.id, after={"name": customer.name, "tier_id": customer.tier_id})
    db.commit()
    db.refresh(customer)
    return _detail_out(customer, 0, Decimal("0"))


@router.get("/{customer_id}", response_model=CustomerDetailOut)
def get_customer(customer_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission(Permission.customer_read))):
    customer = _get_customer(db, customer_id)
    open_counts, outstanding = _stats(db, [customer.id])
    return _detail_out(customer, open_counts.get(customer.id, 0), outstanding.get(customer.id, Decimal("0")))


@router.patch("/{customer_id}", response_model=CustomerDetailOut)
def update_customer(
    customer_id: int, payload: CustomerUpdate, db: Session = Depends(get_db), actor: User = Depends(require_permission(Permission.customer_manage))
):
    customer = _get_customer(db, customer_id)
    if actor.role == Role.sales_rep and customer.owner_user_id not in (None, actor.id):
        raise PermissionDeniedError("You can only edit customers you own.")
    data = payload.model_dump(exclude_unset=True)
    if "tier_id" in data and db.get(CustomerTier, data["tier_id"]) is None:
        raise NotFoundError("Customer tier not found")
    if "owner_user_id" in data and data["owner_user_id"] is not None and db.get(User, data["owner_user_id"]) is None:
        raise NotFoundError("Owner user not found")
    before = {"name": customer.name, "tier_id": customer.tier_id, "owner_user_id": customer.owner_user_id, "is_active": customer.is_active}
    for key, value in data.items():
        setattr(customer, key, value)
    after = {"name": customer.name, "tier_id": customer.tier_id, "owner_user_id": customer.owner_user_id, "is_active": customer.is_active}
    audit_service.record(db, "customer_updated", actor=actor, entity_type="customer", entity_id=customer.id, before=before, after=after)
    db.commit()
    db.refresh(customer)
    open_counts, outstanding = _stats(db, [customer.id])
    return _detail_out(customer, open_counts.get(customer.id, 0), outstanding.get(customer.id, Decimal("0")))


@router.post("/{customer_id}/archive", response_model=CustomerDetailOut)
def archive_customer(customer_id: int, db: Session = Depends(get_db), actor: User = Depends(require_permission(Permission.customer_manage))):
    customer = _get_customer(db, customer_id)
    customer.is_active = False
    audit_service.record(db, "customer_archived", actor=actor, entity_type="customer", entity_id=customer.id)
    db.commit()
    return _detail_out(customer, 0, Decimal("0"))


@router.post("/{customer_id}/restore", response_model=CustomerDetailOut)
def restore_customer(customer_id: int, db: Session = Depends(get_db), actor: User = Depends(require_permission(Permission.customer_manage))):
    customer = _get_customer(db, customer_id)
    customer.is_active = True
    audit_service.record(db, "customer_restored", actor=actor, entity_type="customer", entity_id=customer.id)
    db.commit()
    return _detail_out(customer, 0, Decimal("0"))


@router.get("/{customer_id}/history", response_model=CustomerHistoryOut)
def customer_history(customer_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission(Permission.customer_read))):
    customer = _get_customer(db, customer_id)
    quotes = (
        db.query(Quote).options(joinedload(Quote.owner)).filter(Quote.customer_id == customer.id).order_by(Quote.id.desc()).limit(100).all()
    )
    quote_ids = [q.id for q in quotes]
    invoices = db.query(Invoice).filter(Invoice.customer_id == customer.id).order_by(Invoice.id.desc()).limit(100).all()
    invoice_ids = [i.id for i in invoices]
    payments = db.query(Payment).filter(Payment.invoice_id.in_(invoice_ids or [0])).order_by(Payment.id.desc()).limit(100).all()
    invoice_number = {i.id: i.invoice_number for i in invoices}
    subscriptions = (
        db.query(Subscription).options(joinedload(Subscription.plan)).filter(Subscription.customer_id == customer.id).order_by(Subscription.id.desc()).all()
    )
    alerts = db.query(DealHealthAlert).filter(DealHealthAlert.quote_id.in_(quote_ids or [0])).order_by(DealHealthAlert.id.desc()).limit(50).all()
    activity = (
        db.query(AuditLog)
        .filter(or_(AuditLog.quote_id.in_(quote_ids or [0]), (AuditLog.entity_type == "customer") & (AuditLog.entity_id == customer.id)))
        .order_by(AuditLog.timestamp.desc())
        .limit(50)
        .all()
    )
    total_revenue = sum((Decimal(i.amount_paid or 0) for i in invoices), Decimal("0"))
    outstanding = sum((i.outstanding for i in invoices if i.status in UNPAID_STATUSES), Decimal("0"))
    return CustomerHistoryOut(
        quotes=[
            {
                "id": q.id, "quote_number": q.quote_number, "status": q.status.value, "total": float(q.total or 0),
                "owner_name": q.owner.full_name if q.owner else None, "created_at": q.created_at, "order_number": q.order_number,
                "fulfillment_status": q.fulfillment_status.value, "billing_status": q.billing_status.value,
            }
            for q in quotes
        ],
        orders=[
            {"id": q.id, "order_number": q.order_number, "quote_number": q.quote_number, "total": float(q.total or 0), "confirmed_at": q.confirmed_at,
             "fulfillment_status": q.fulfillment_status.value, "billing_status": q.billing_status.value}
            for q in quotes
            if q.order_number
        ],
        invoices=[
            {"id": i.id, "invoice_number": i.invoice_number, "status": i.status.value, "amount": float(i.amount), "amount_paid": float(i.amount_paid),
             "due_date": i.due_date, "invoice_type": i.invoice_type.value, "quote_id": i.quote_id}
            for i in invoices
        ],
        payments=[
            {"id": p.id, "invoice_id": p.invoice_id, "invoice_number": invoice_number.get(p.invoice_id), "amount": float(p.amount),
             "direction": p.direction.value, "method": p.method, "paid_at": p.paid_at, "status": p.status.value}
            for p in payments
        ],
        subscriptions=[
            {"id": s.id, "plan_name": s.plan.name if s.plan else None, "quantity": s.quantity, "status": s.status.value,
             "next_billing_date": s.next_billing_date, "quote_id": s.quote_id}
            for s in subscriptions
        ],
        alerts=[
            {"id": a.id, "quote_id": a.quote_id, "alert_type": a.alert_type, "severity": a.severity, "status": a.status.value, "message": a.message, "created_at": a.created_at}
            for a in alerts
        ],
        activity=[
            {"id": l.id, "action": l.action, "user": l.user, "reason": l.reason, "quote_id": l.quote_id, "timestamp": l.timestamp}
            for l in activity
        ],
        totals={
            "quote_count": len(quotes),
            "order_count": sum(1 for q in quotes if q.order_number),
            "invoice_count": len(invoices),
            "revenue_collected": float(total_revenue),
            "outstanding_balance": float(outstanding),
            "active_subscriptions": sum(1 for s in subscriptions if s.status.value == "active"),
            "open_alerts": sum(1 for a in alerts if a.status.value != "resolved"),
        },
    )
