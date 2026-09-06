"""Global search across the main entities. Server-side ILIKE with LIMITs;
respects the caller's quote visibility."""

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.core.permissions import Role
from app.models import Customer, Invoice, Product, Quote, Subscription, SubscriptionPlan, User
from app.services import quote_service


def customer_match(db: Session, like: str):
    """Predicate for "which customers does this term name?".

    A customer's own fields are only half of its identity: the people who sign
    in to the portal are User rows, and their names need not appear anywhere on
    the account (the contact_name is whoever was on the paperwork). A rep who
    has been dealing with "Hannah Park" has to be able to find her account, so
    portal logins count as part of the customer's searchable identity.
    """
    portal_users = db.query(User.customer_id).filter(
        User.role == Role.customer,
        User.customer_id.isnot(None),
        or_(User.full_name.ilike(like), User.email.ilike(like)),
    )
    return or_(
        Customer.name.ilike(like),
        Customer.code.ilike(like),
        Customer.email.ilike(like),
        Customer.contact_name.ilike(like),
        Customer.id.in_(portal_users),
    )


def search(db: Session, user: User, q: str, limit: int = 5) -> dict:
    term = q.strip()
    if not term:
        return {"customers": [], "quotes": [], "orders": [], "products": [], "invoices": [], "subscriptions": []}
    like = f"%{term}%"
    customers = (
        db.query(Customer).options(joinedload(Customer.tier))
        .filter(customer_match(db, like))
        .order_by(Customer.name).limit(limit).all()
    )
    quotes_q = quote_service.visible_quotes_query(db, user).join(Customer, Quote.customer_id == Customer.id)
    quotes = quotes_q.filter(or_(Quote.quote_number.ilike(like), Customer.name.ilike(like))).order_by(Quote.id.desc()).limit(limit).all()
    orders = quotes_q.filter(Quote.order_number.isnot(None)).filter(or_(Quote.order_number.ilike(like), Customer.name.ilike(like))).order_by(Quote.id.desc()).limit(limit).all()
    products = (
        db.query(Product).options(joinedload(Product.category)).filter(Product.is_archived.is_(False)).filter(or_(Product.name.ilike(like), Product.sku.ilike(like))).order_by(Product.name).limit(limit).all()
    )
    invoices_q = db.query(Invoice).options(joinedload(Invoice.quote).joinedload(Quote.customer)).join(Quote, Invoice.quote_id == Quote.id).join(Customer, Quote.customer_id == Customer.id)
    if user.role == Role.sales_rep:
        invoices_q = invoices_q.filter(or_(Quote.owner_user_id == user.id, Customer.owner_user_id == user.id))
    invoices = invoices_q.filter(or_(Invoice.invoice_number.ilike(like), Customer.name.ilike(like))).order_by(Invoice.id.desc()).limit(limit).all()
    subs_q = (
        db.query(Subscription).options(joinedload(Subscription.plan), joinedload(Subscription.customer))
        .join(SubscriptionPlan, Subscription.subscription_plan_id == SubscriptionPlan.id).join(Customer, Subscription.customer_id == Customer.id)
    )
    if user.role == Role.sales_rep:
        subs_q = subs_q.join(Quote, Subscription.quote_id == Quote.id).filter(or_(Quote.owner_user_id == user.id, Customer.owner_user_id == user.id))
    subscriptions = subs_q.filter(or_(SubscriptionPlan.name.ilike(like), Customer.name.ilike(like))).order_by(Subscription.id.desc()).limit(limit).all()
    return {
        "customers": [{"id": c.id, "name": c.name, "code": c.code, "tier": c.tier.name, "link": f"/workspace/customers/{c.id}"} for c in customers],
        "quotes": [{"id": q.id, "quote_number": q.quote_number, "customer_name": q.customer.name, "status": q.status.value, "total": float(q.total), "link": f"/workspace/quotations/{q.id}"} for q in quotes],
        "orders": [{"id": q.id, "order_number": q.order_number, "customer_name": q.customer.name, "fulfillment_status": q.fulfillment_status.value, "total": float(q.total), "link": f"/workspace/quotations/{q.id}"} for q in orders],
        "products": [{"id": p.id, "name": p.name, "sku": p.sku, "category": p.category.name, "price": float(p.price), "link": f"/admin/products/{p.id}"} for p in products],
        "invoices": [{"id": i.id, "invoice_number": i.invoice_number, "customer_name": i.quote.customer.name, "status": i.status.value, "amount": float(i.amount), "link": f"/workspace/invoices/{i.id}"} for i in invoices],
        "subscriptions": [{"id": s.id, "plan_name": s.plan.name, "customer_name": s.customer.name if s.customer else None, "status": s.status.value, "link": f"/workspace/subscriptions/{s.id}"} for s in subscriptions],
    }
