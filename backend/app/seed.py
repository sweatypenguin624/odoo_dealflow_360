"""Seed script for local/demo data.

Wipes every table this script touches (in FK-safe order) and inserts a
small, realistic dataset: two customer tiers, three customers, two
categories with different discount ceilings, five products split
across them, two warehouses with stock, one subscription plan, a
couple of product pairings for upsell suggestions, and three quotes:
  - Quote 1 (draft): a Laptop line discount well over its Hardware
    category limit, so submitting it for approval actually routes to
    "manager" - the same Laptop/8-points-over shape used throughout
    the backend's own test suite.
  - Quote 2 (draft): entirely within limits, so submitting it
    auto-approves - a contrast case.
  - Quote 3 (approved): one one-time line and one recurring line with
    an active Subscription and an initial invoice BillingEvent
    already attached, so the billing screen has something to render
    without having to drive an entire approval chain first.

Run with: python -m app.seed (from the backend/ directory, venv active)
"""

from datetime import date

from app.database import SessionLocal, engine, Base
from app.models import (
    ApprovalAction,
    AuditLog,
    BillingEvent,
    Category,
    CounterProposal,
    Customer,
    CustomerTier,
    FulfillmentPlan,
    FulfillmentSplit,
    LineComment,
    PortalToken,
    Product,
    ProductPairing,
    Quote,
    QuoteLine,
    QuoteStatus,
    Stock,
    Subscription,
    SubscriptionPlan,
    SubscriptionStatus,
    Warehouse,
)


def wipe(db):
    # FK-safe order: children before parents.
    for model in [
        BillingEvent,
        Subscription,
        SubscriptionPlan,
        CounterProposal,
        LineComment,
        PortalToken,
        FulfillmentSplit,
        FulfillmentPlan,
        ApprovalAction,
        AuditLog,
        ProductPairing,
        Stock,
        Warehouse,
        QuoteLine,
        Quote,
        Product,
        Category,
        Customer,
        CustomerTier,
    ]:
        db.query(model).delete()
    db.commit()


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    wipe(db)

    gold = CustomerTier(name="Gold", max_discount_pct=15)
    silver = CustomerTier(name="Silver", max_discount_pct=8)
    db.add_all([gold, silver])
    db.flush()

    acme = Customer(name="Acme Corp", tier_id=gold.id)
    beta = Customer(name="Beta LLC", tier_id=gold.id)
    gamma = Customer(name="Gamma Inc", tier_id=silver.id)
    db.add_all([acme, beta, gamma])
    db.flush()

    hardware = Category(name="Hardware", max_discount_pct=10)
    services = Category(name="Services", max_discount_pct=None)  # falls back to tier limit
    db.add_all([hardware, services])
    db.flush()

    laptop = Product(name="Laptop", category_id=hardware.id, price=1000, unit_margin_pct=20)
    monitor = Product(name="Monitor", category_id=hardware.id, price=300, unit_margin_pct=25)
    cable = Product(name="Cable", category_id=hardware.id, price=20, unit_margin_pct=10)
    setup_service = Product(name="Setup Service", category_id=services.id, price=200, unit_margin_pct=50)
    support_plan = Product(name="Support Plan", category_id=services.id, price=150, unit_margin_pct=60)
    db.add_all([laptop, monitor, cable, setup_service, support_plan])
    db.flush()

    warehouse_east = Warehouse(name="East DC", shipping_cost_weight=1.0)
    warehouse_west = Warehouse(name="West DC", shipping_cost_weight=1.8)
    db.add_all([warehouse_east, warehouse_west])
    db.flush()

    db.add_all(
        [
            Stock(warehouse_id=warehouse_east.id, product_id=laptop.id, quantity_available=5),
            Stock(warehouse_id=warehouse_west.id, product_id=laptop.id, quantity_available=10),
            Stock(warehouse_id=warehouse_east.id, product_id=monitor.id, quantity_available=20),
            Stock(warehouse_id=warehouse_east.id, product_id=cable.id, quantity_available=100),
        ]
    )

    support_plan_monthly = SubscriptionPlan(
        name="Support Plan Monthly",
        product_id=support_plan.id,
        interval="monthly",
        price_per_interval=150,
    )
    db.add(support_plan_monthly)
    db.flush()

    db.add_all(
        [
            ProductPairing(
                base_product_id=laptop.id,
                suggested_product_id=monitor.id,
                co_purchase_score=40,
                is_promoted=False,
            ),
            ProductPairing(
                base_product_id=laptop.id,
                suggested_product_id=setup_service.id,
                co_purchase_score=10,
                is_promoted=True,
            ),
            ProductPairing(
                base_product_id=laptop.id,
                suggested_product_id=cable.id,
                co_purchase_score=90,
                is_promoted=False,
            ),
        ]
    )

    # Quote 1: Laptop discount 18% vs Hardware's 10% limit -> 8 points
    # over -> submitting routes to "manager" (same shape as the backend's
    # own risk_engine/approval_workflow tests).
    quote1 = Quote(customer_id=acme.id, status=QuoteStatus.draft, rep_name="Alice")
    db.add(quote1)
    db.flush()
    db.add_all(
        [
            QuoteLine(
                quote_id=quote1.id, product_id=laptop.id, quantity=1, discount_pct=18, line_value=1000
            ),
            QuoteLine(
                quote_id=quote1.id, product_id=setup_service.id, quantity=1, discount_pct=5, line_value=200
            ),
        ]
    )

    # Quote 2: everything within limits -> submitting auto-approves.
    quote2 = Quote(customer_id=beta.id, status=QuoteStatus.draft, rep_name="Bob")
    db.add(quote2)
    db.flush()
    db.add_all(
        [
            QuoteLine(
                quote_id=quote2.id, product_id=monitor.id, quantity=2, discount_pct=5, line_value=600
            ),
            QuoteLine(
                quote_id=quote2.id, product_id=cable.id, quantity=3, discount_pct=0, line_value=60
            ),
        ]
    )

    # Quote 3: already approved, one one-time line + one recurring line
    # with an active subscription, so the billing screen (B7) has real
    # data without having to drive an entire approval chain first.
    quote3 = Quote(customer_id=gamma.id, status=QuoteStatus.approved, rep_name="Alice")
    db.add(quote3)
    db.flush()
    onetime_line = QuoteLine(
        quote_id=quote3.id, product_id=laptop.id, quantity=1, discount_pct=5, line_value=1000
    )
    recurring_line = QuoteLine(
        quote_id=quote3.id,
        product_id=support_plan.id,
        quantity=2,
        discount_pct=0,
        line_value=300,
        is_recurring=True,
    )
    db.add_all([onetime_line, recurring_line])
    db.flush()

    cycle_start = date.today().replace(day=1)
    if cycle_start.month == 12:
        cycle_end = cycle_start.replace(year=cycle_start.year + 1, month=1)
    else:
        cycle_end = cycle_start.replace(month=cycle_start.month + 1)

    subscription = Subscription(
        quote_line_id=recurring_line.id,
        subscription_plan_id=support_plan_monthly.id,
        quantity=2,
        status=SubscriptionStatus.active,
        current_cycle_start=cycle_start,
        current_cycle_end=cycle_end,
    )
    db.add(subscription)
    db.flush()

    db.add(
        BillingEvent(
            subscription_id=subscription.id,
            event_type="invoice",
            amount=support_plan_monthly.price_per_interval * subscription.quantity,
            description="Initial subscription invoice",
            event_date=cycle_start,
        )
    )

    db.commit()

    print("Seed complete:")
    print(f"  quote1 (draft, over-limit Laptop):   id={quote1.id}")
    print(f"  quote2 (draft, within limits):        id={quote2.id}")
    print(f"  quote3 (approved, has subscription):  id={quote3.id}")

    db.close()


if __name__ == "__main__":
    seed()
