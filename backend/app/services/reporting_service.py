"""Reporting: SQL aggregation with a shared filter set. Each report
returns {"summary": {...}, "rows": [...], "columns": [...]} so the same
result feeds the UI tables and the exporters."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session

from app.core.money import D
from app.core.permissions import Role
from app.models import (
    AlertStatus,
    ApprovalAction,
    ApprovalRequest,
    BillingInterval,
    Category,
    Customer,
    CustomerTier,
    DealHealthAlert,
    FulfillmentPlan,
    FulfillmentSplit,
    FulfillmentStatus,
    Invoice,
    InvoiceStatus,
    Product,
    Quote,
    QuoteLine,
    QuoteStatus,
    Shipment,
    ShipmentStatus,
    SplitStatus,
    Stock,
    Subscription,
    SubscriptionPlan,
    SubscriptionStatus,
    UNPAID_STATUSES,
    User,
    Warehouse,
)

CLOSED = [QuoteStatus.confirmed, QuoteStatus.rejected, QuoteStatus.cancelled, QuoteStatus.expired]


@dataclass
class ReportFilters:
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    owner_user_id: Optional[int] = None
    team: Optional[str] = None
    customer_id: Optional[int] = None
    tier_id: Optional[int] = None
    product_id: Optional[int] = None
    category_id: Optional[int] = None
    quote_status: Optional[str] = None
    approval_status: Optional[str] = None
    fulfillment_status: Optional[str] = None
    invoice_status: Optional[str] = None

    def describe(self) -> str:
        parts = []
        if self.date_from:
            parts.append(f"from {self.date_from}")
        if self.date_to:
            parts.append(f"to {self.date_to}")
        for k in ("owner_user_id", "team", "customer_id", "tier_id", "product_id", "category_id", "quote_status", "approval_status", "fulfillment_status", "invoice_status"):
            v = getattr(self, k)
            if v:
                parts.append(f"{k}={v}")
        return ", ".join(parts) or "all data"


def _f(v) -> float:
    return float(D(v or 0))


def _quote_query(db: Session, f: ReportFilters, user: User):
    q = db.query(Quote).join(Customer, Quote.customer_id == Customer.id).outerjoin(User, Quote.owner_user_id == User.id)
    if user.role == Role.sales_rep:
        q = q.filter(or_(Quote.owner_user_id == user.id, Customer.owner_user_id == user.id))
    if f.date_from:
        q = q.filter(Quote.created_at >= datetime.combine(f.date_from, datetime.min.time()))
    if f.date_to:
        q = q.filter(Quote.created_at < datetime.combine(f.date_to + timedelta(days=1), datetime.min.time()))
    if f.owner_user_id:
        q = q.filter(Quote.owner_user_id == f.owner_user_id)
    if f.team:
        q = q.filter(User.team == f.team)
    if f.customer_id:
        q = q.filter(Quote.customer_id == f.customer_id)
    if f.tier_id:
        q = q.filter(Customer.tier_id == f.tier_id)
    if f.quote_status:
        q = q.filter(Quote.status.in_([s.strip() for s in f.quote_status.split(",")]))
    if f.fulfillment_status:
        q = q.filter(Quote.fulfillment_status == f.fulfillment_status)
    if f.approval_status:
        if f.approval_status == "auto":
            q = q.filter(or_(Quote.required_approval_level == "none", Quote.required_approval_level.is_(None)))
        else:
            q = q.filter(Quote.required_approval_level == f.approval_status)
    if f.product_id or f.category_id:
        sub = db.query(QuoteLine.quote_id).join(Product, QuoteLine.product_id == Product.id)
        if f.product_id:
            sub = sub.filter(QuoteLine.product_id == f.product_id)
        if f.category_id:
            sub = sub.filter(Product.category_id == f.category_id)
        q = q.filter(Quote.id.in_(sub))
    return q


# ---------------------------------------------------------------- sales


def sales_report(db: Session, f: ReportFilters, user: User) -> dict:
    q = _quote_query(db, f, user)
    ids = q.with_entities(Quote.id)
    total_count = db.query(func.count(Quote.id)).filter(Quote.id.in_(ids)).scalar()
    total_value = db.query(func.coalesce(func.sum(Quote.total), 0)).filter(Quote.id.in_(ids)).scalar()
    won = db.query(func.count(Quote.id), func.coalesce(func.sum(Quote.total), 0)).filter(Quote.id.in_(ids), Quote.status == QuoteStatus.confirmed).one()
    closed = db.query(func.count(Quote.id)).filter(Quote.id.in_(ids), Quote.status.in_(CLOSED)).scalar()
    revenue = db.query(func.coalesce(func.sum(Invoice.amount_paid), 0)).filter(Invoice.quote_id.in_(ids), Invoice.status != InvoiceStatus.void).scalar()
    by_status = db.query(Quote.status, func.count(Quote.id), func.coalesce(func.sum(Quote.total), 0)).filter(Quote.id.in_(ids)).group_by(Quote.status).all()
    by_rep = (
        db.query(User.full_name, User.team, func.count(Quote.id), func.coalesce(func.sum(Quote.total), 0), func.sum(case((Quote.status == QuoteStatus.confirmed, 1), else_=0)), func.coalesce(func.sum(case((Quote.status == QuoteStatus.confirmed, Quote.total), else_=0)), 0))
        .select_from(Quote).outerjoin(User, Quote.owner_user_id == User.id).filter(Quote.id.in_(ids)).group_by(User.full_name, User.team).order_by(func.sum(Quote.total).desc()).all()
    )
    month_expr = func.strftime("%Y-%m", Quote.created_at) if db.bind.dialect.name == "sqlite" else func.to_char(Quote.created_at, "YYYY-MM")
    by_month = (
        db.query(month_expr, func.count(Quote.id), func.coalesce(func.sum(Quote.total), 0), func.coalesce(func.sum(case((Quote.status == QuoteStatus.confirmed, Quote.total), else_=0)), 0))
        .filter(Quote.id.in_(ids)).group_by(month_expr).order_by(month_expr).all()
    )
    rows = [
        {"rep": name or "Unassigned", "team": team, "quotes": int(c), "quote_value": _f(v), "won": int(w or 0), "won_value": _f(wv), "conversion_rate": round(float(w or 0) / float(c) * 100, 1) if c else 0.0}
        for name, team, c, v, w, wv in by_rep
    ]
    return {
        "summary": {
            "quote_count": int(total_count or 0), "quote_value": _f(total_value), "won_count": int(won[0] or 0), "order_value": _f(won[1]),
            "conversion_rate": round(float(won[0] or 0) / float(closed) * 100, 1) if closed else 0.0, "revenue_collected": _f(revenue),
            "average_quote_value": round(_f(total_value) / float(total_count), 2) if total_count else 0.0,
        },
        "by_status": [{"status": s.value, "count": int(c), "value": _f(v)} for s, c, v in by_status],
        "by_month": [{"month": m, "quotes": int(c), "value": _f(v), "won_value": _f(w)} for m, c, v, w in by_month],
        "columns": ["rep", "team", "quotes", "quote_value", "won", "won_value", "conversion_rate"],
        "rows": rows,
    }


# ---------------------------------------------------------------- discounts


def discount_report(db: Session, f: ReportFilters, user: User) -> dict:
    ids = _quote_query(db, f, user).with_entities(Quote.id)
    lines = db.query(QuoteLine).filter(QuoteLine.quote_id.in_(ids))
    weighted = db.query(func.coalesce(func.sum(QuoteLine.discount_pct * QuoteLine.line_value), 0), func.coalesce(func.sum(QuoteLine.line_value), 0), func.coalesce(func.sum(QuoteLine.line_value - QuoteLine.line_total), 0)).filter(QuoteLine.quote_id.in_(ids)).one()
    avg = float(D(weighted[0]) / D(weighted[1])) if weighted[1] else 0.0
    approval_counts = dict(db.query(Quote.required_approval_level, func.count(Quote.id)).filter(Quote.id.in_(ids)).group_by(Quote.required_approval_level).all())
    total = sum(approval_counts.values())
    needing = sum(v for k, v in approval_counts.items() if k and k != "none")
    high_risk = approval_counts.get("manager_then_finance", 0)

    def grouped(label_col, join):
        q = db.query(label_col, func.coalesce(func.sum(QuoteLine.discount_pct * QuoteLine.line_value), 0), func.coalesce(func.sum(QuoteLine.line_value), 0), func.coalesce(func.sum(QuoteLine.line_value - QuoteLine.line_total), 0), func.count(func.distinct(QuoteLine.quote_id))).select_from(QuoteLine).join(Quote, QuoteLine.quote_id == Quote.id)
        q = join(q).filter(QuoteLine.quote_id.in_(ids)).group_by(label_col)
        return [{"label": lbl or "Unassigned", "average_discount_pct": round(float(D(w) / D(v)), 2) if v else 0.0, "discount_amount": _f(d), "quote_count": int(c), "value": _f(v)} for lbl, w, v, d, c in q.all()]

    by_rep = grouped(User.full_name, lambda q: q.outerjoin(User, Quote.owner_user_id == User.id))
    by_customer = grouped(Customer.name, lambda q: q.join(Customer, Quote.customer_id == Customer.id))
    by_category = grouped(Category.name, lambda q: q.join(Product, QuoteLine.product_id == Product.id).join(Category, Product.category_id == Category.id))
    outcomes = dict(db.query(ApprovalAction.action, func.count(ApprovalAction.id)).filter(ApprovalAction.quote_id.in_(ids)).group_by(ApprovalAction.action).all())
    return {
        "summary": {
            "average_discount_pct": round(avg, 2), "total_discount_amount": _f(weighted[2]), "quotes": int(total), "quotes_requiring_approval": int(needing),
            "approval_frequency_pct": round(needing / total * 100, 1) if total else 0.0, "high_risk_quotes": int(high_risk),
            "approved": int(outcomes.get("approved", 0)), "rejected": int(outcomes.get("rejected", 0)), "returned": int(outcomes.get("returned_for_revision", 0)),
        },
        "by_rep": by_rep, "by_customer": sorted(by_customer, key=lambda r: -r["discount_amount"])[:50], "by_category": by_category,
        "columns": ["label", "average_discount_pct", "discount_amount", "quote_count", "value"], "rows": by_rep,
    }


# ---------------------------------------------------------------- fulfillment


def fulfillment_report(db: Session, f: ReportFilters, user: User) -> dict:
    ids = _quote_query(db, f, user).filter(Quote.status == QuoteStatus.confirmed).with_entities(Quote.id)
    orders = db.query(func.count(Quote.id)).filter(Quote.id.in_(ids)).scalar()
    by_status = dict(db.query(Quote.fulfillment_status, func.count(Quote.id)).filter(Quote.id.in_(ids)).group_by(Quote.fulfillment_status).all())
    fulfilled = by_status.get(FulfillmentStatus.shipped, 0) + by_status.get(FulfillmentStatus.delivered, 0)
    plan_ids = db.query(FulfillmentPlan.id).filter(FulfillmentPlan.quote_id.in_(ids))
    backordered_units = db.query(func.coalesce(func.sum(FulfillmentSplit.quantity_fulfilled), 0)).filter(FulfillmentSplit.fulfillment_plan_id.in_(plan_ids), FulfillmentSplit.status == SplitStatus.backordered).scalar()
    orders_with_backorders = db.query(func.count(func.distinct(FulfillmentPlan.quote_id))).join(FulfillmentSplit, FulfillmentSplit.fulfillment_plan_id == FulfillmentPlan.id).filter(FulfillmentPlan.id.in_(plan_ids), FulfillmentSplit.is_backorder.is_(True)).scalar()
    shipments = db.query(func.count(Shipment.id)).filter(Shipment.quote_id.in_(ids)).scalar()
    late = db.query(func.count(Shipment.id)).filter(Shipment.quote_id.in_(ids), Shipment.promised_date.isnot(None), or_(and_(Shipment.delivered_at.isnot(None), func.date(Shipment.delivered_at) > Shipment.promised_date), and_(Shipment.delivered_at.is_(None), Shipment.expected_date > Shipment.promised_date))).scalar()
    by_warehouse = (
        db.query(Warehouse.name, func.count(func.distinct(Shipment.id)), func.coalesce(func.sum(FulfillmentSplit.quantity_fulfilled), 0))
        .select_from(Warehouse).outerjoin(Shipment, and_(Shipment.warehouse_id == Warehouse.id, Shipment.quote_id.in_(ids))).outerjoin(FulfillmentSplit, FulfillmentSplit.shipment_id == Shipment.id)
        .group_by(Warehouse.name).all()
    )
    stock = {name: (int(oh or 0), int(r or 0)) for name, oh, r in db.query(Warehouse.name, func.sum(Stock.quantity_on_hand), func.sum(Stock.quantity_reserved)).select_from(Warehouse).outerjoin(Stock, Stock.warehouse_id == Warehouse.id).group_by(Warehouse.name).all()}
    rows = [{"warehouse": n, "shipments": int(s), "units_shipped": int(u), "units_on_hand": stock.get(n, (0, 0))[0], "units_reserved": stock.get(n, (0, 0))[1], "utilization_pct": round(stock.get(n, (0, 0))[1] / stock.get(n, (0, 0))[0] * 100, 1) if stock.get(n, (0, 0))[0] else 0.0} for n, s, u in by_warehouse]
    return {
        "summary": {
            "orders": int(orders or 0), "fulfillment_rate_pct": round(fulfilled / orders * 100, 1) if orders else 0.0,
            "backorder_rate_pct": round((orders_with_backorders or 0) / orders * 100, 1) if orders else 0.0, "units_backordered": int(backordered_units or 0),
            "shipment_count": int(shipments or 0), "late_shipments": int(late or 0), "orders_delivered": int(by_status.get(FulfillmentStatus.delivered, 0)),
        },
        "by_status": [{"status": s.value, "count": int(c)} for s, c in by_status.items()],
        "columns": ["warehouse", "shipments", "units_shipped", "units_on_hand", "units_reserved", "utilization_pct"], "rows": rows,
    }


# ---------------------------------------------------------------- billing


def billing_report(db: Session, f: ReportFilters, user: User) -> dict:
    ids = _quote_query(db, f, user).with_entities(Quote.id)
    inv = db.query(Invoice).filter(Invoice.quote_id.in_(ids), Invoice.status != InvoiceStatus.void)
    if f.invoice_status:
        inv = inv.filter(Invoice.status == f.invoice_status)
    today = date.today()
    totals = inv.with_entities(func.count(Invoice.id), func.coalesce(func.sum(Invoice.amount), 0), func.coalesce(func.sum(Invoice.amount_paid), 0)).one()
    outstanding = inv.filter(Invoice.status.in_(list(UNPAID_STATUSES))).with_entities(func.coalesce(func.sum(Invoice.amount - Invoice.amount_paid), 0)).scalar()
    overdue = inv.filter(Invoice.status.in_(list(UNPAID_STATUSES)), Invoice.due_date < today).with_entities(func.count(Invoice.id), func.coalesce(func.sum(Invoice.amount - Invoice.amount_paid), 0)).one()
    by_status = inv.with_entities(Invoice.status, func.count(Invoice.id), func.coalesce(func.sum(Invoice.amount), 0), func.coalesce(func.sum(Invoice.amount_paid), 0)).group_by(Invoice.status).all()
    subs = db.query(Subscription, SubscriptionPlan).join(SubscriptionPlan, Subscription.subscription_plan_id == SubscriptionPlan.id).filter(Subscription.quote_id.in_(ids)).all()
    factor = {BillingInterval.monthly: Decimal("1"), BillingInterval.quarterly: Decimal("1") / 3, BillingInterval.yearly: Decimal("1") / 12}
    active = [(s, p) for s, p in subs if s.status == SubscriptionStatus.active]
    mrr = sum((D(s.unit_price if s.unit_price is not None else p.price_per_interval) * s.quantity * factor[p.interval] for s, p in active), Decimal("0"))
    by_customer = (
        inv.join(Customer, Invoice.customer_id == Customer.id).with_entities(Customer.name, func.count(Invoice.id), func.coalesce(func.sum(Invoice.amount), 0), func.coalesce(func.sum(Invoice.amount_paid), 0), func.coalesce(func.sum(case((Invoice.status.in_(list(UNPAID_STATUSES)), Invoice.amount - Invoice.amount_paid), else_=0)), 0))
        .group_by(Customer.name).order_by(func.sum(Invoice.amount).desc()).limit(100).all()
    )
    rows = [{"customer": n, "invoices": int(c), "invoiced": _f(a), "paid": _f(p), "outstanding": _f(o)} for n, c, a, p, o in by_customer]
    return {
        "summary": {
            "invoice_count": int(totals[0] or 0), "invoice_value": _f(totals[1]), "paid": _f(totals[2]), "outstanding": _f(outstanding),
            "overdue_count": int(overdue[0] or 0), "overdue_value": _f(overdue[1]), "recurring_revenue_monthly": float(mrr.quantize(Decimal("0.01"))),
            "subscription_count": len(subs), "active_subscriptions": len(active),
        },
        "by_status": [{"status": s.value, "count": int(c), "value": _f(a), "paid": _f(p)} for s, c, a, p in by_status],
        "columns": ["customer", "invoices", "invoiced", "paid", "outstanding"], "rows": rows,
    }


# ---------------------------------------------------------------- deal health


def deal_health_report(db: Session, f: ReportFilters, user: User) -> dict:
    ids = _quote_query(db, f, user).with_entities(Quote.id)
    alerts = db.query(DealHealthAlert).filter(DealHealthAlert.quote_id.in_(ids))
    by_type = alerts.with_entities(DealHealthAlert.alert_type, DealHealthAlert.status, func.count(DealHealthAlert.id)).group_by(DealHealthAlert.alert_type, DealHealthAlert.status).all()
    counts = {}
    for t, s, c in by_type:
        counts.setdefault(t, {"open": 0, "acknowledged": 0, "resolved": 0})[s.value] = int(c)
    pending = db.query(ApprovalRequest).filter(ApprovalRequest.quote_id.in_(ids), ApprovalRequest.status == "pending").all()
    now = datetime.now()
    aging = [((now - (r.created_at.replace(tzinfo=None) if r.created_at.tzinfo else r.created_at)).days) for r in pending]
    by_rep = (
        db.query(User.full_name, DealHealthAlert.alert_type, func.count(DealHealthAlert.id)).select_from(DealHealthAlert).join(Quote, DealHealthAlert.quote_id == Quote.id).outerjoin(User, Quote.owner_user_id == User.id)
        .filter(DealHealthAlert.quote_id.in_(ids), DealHealthAlert.status != AlertStatus.resolved).group_by(User.full_name, DealHealthAlert.alert_type).all()
    )
    rep_rows = {}
    for name, t, c in by_rep:
        rep_rows.setdefault(name or "Unassigned", {"rep": name or "Unassigned", "stalled": 0, "discount_anomaly": 0, "delivery_slippage": 0, "approval_aging": 0, "other": 0})
        key = t if t in ("stalled", "discount_anomaly", "delivery_slippage", "approval_aging") else "other"
        rep_rows[name or "Unassigned"][key] += int(c)
    return {
        "summary": {
            "stalled_deals": counts.get("stalled", {}).get("open", 0) + counts.get("stalled", {}).get("acknowledged", 0),
            "discount_anomalies": counts.get("discount_anomaly", {}).get("open", 0) + counts.get("discount_anomaly", {}).get("acknowledged", 0),
            "delivery_slippage": counts.get("delivery_slippage", {}).get("open", 0) + counts.get("delivery_slippage", {}).get("acknowledged", 0),
            "pending_approvals": len(pending), "average_approval_age_days": round(sum(aging) / len(aging), 1) if aging else 0.0, "oldest_approval_days": max(aging) if aging else 0,
            "resolved_alerts": sum(v.get("resolved", 0) for v in counts.values()),
        },
        "by_type": [{"alert_type": t, **v} for t, v in counts.items()],
        "columns": ["rep", "stalled", "discount_anomaly", "delivery_slippage", "approval_aging", "other"], "rows": list(rep_rows.values()),
    }


REPORTS = {
    "sales": sales_report,
    "discounts": discount_report,
    "fulfillment": fulfillment_report,
    "billing": billing_report,
    "deal-health": deal_health_report,
}
