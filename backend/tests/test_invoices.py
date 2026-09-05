from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base
from app.models import (
    BillingInterval,
    Category,
    Customer,
    CustomerTier,
    Product,
    Quote,
    QuoteLine,
    QuoteStatus,
    Stock,
    Subscription,
    SubscriptionPlan,
    SubscriptionStatus,
    Warehouse,
)
from app.routers.fulfillment import get_db as fulfillment_get_db
from app.routers.invoices import get_db as invoices_get_db
from app.services.invoice_service import (
    InvoiceableLine,
    ShippedQuantity,
    calculate_invoiceable_amount,
)

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


# Only this file's own dependency key is overridden at module scope. Tests
# that need to drive the real fulfillment endpoints (to get a genuinely
# confirmed FulfillmentPlan) borrow fulfillment's get_db for the duration of
# that one test only (see setup_db below) and restore it afterwards, so it
# never leaks into test_fulfillment_api.py's own tests when run in the same
# session - the same convention test_portal_negotiation.py established.
app.dependency_overrides[invoices_get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    previous_fulfillment_override = app.dependency_overrides.get(fulfillment_get_db)
    app.dependency_overrides[fulfillment_get_db] = override_get_db

    db = TestingSessionLocal()

    tier = CustomerTier(id=1, name="Gold", max_discount_pct=15)
    db.add(tier)

    customer = Customer(id=1, name="Test Corp", tier_id=1)
    db.add(customer)

    category = Category(id=1, name="Hardware", max_discount_pct=15)
    db.add(category)

    product = Product(id=1, name="Widget", category_id=1, price=100, unit_margin_pct=20)
    db.add(product)

    support = Product(id=2, name="Support Plan", category_id=1, price=50, unit_margin_pct=60)
    db.add(support)

    plan = SubscriptionPlan(
        id=1, name="Support Monthly", product_id=2, interval=BillingInterval.monthly, price_per_interval=50
    )
    db.add(plan)

    db.commit()
    db.close()

    yield

    Base.metadata.drop_all(bind=engine)
    if previous_fulfillment_override is None:
        app.dependency_overrides.pop(fulfillment_get_db, None)
    else:
        app.dependency_overrides[fulfillment_get_db] = previous_fulfillment_override


def create_quote(db, status=QuoteStatus.approved, quantity=10, discount_pct=0):
    quote = Quote(customer_id=1, status=status)
    db.add(quote)
    db.commit()
    db.refresh(quote)

    line = QuoteLine(
        quote_id=quote.id, product_id=1, quantity=quantity, discount_pct=discount_pct, line_value=quantity * 100
    )
    db.add(line)
    db.commit()
    db.refresh(line)

    return quote.id, line.id


def add_stock(db, warehouse_name, quantity_available):
    warehouse = Warehouse(name=warehouse_name, shipping_cost_weight=1.0)
    db.add(warehouse)
    db.commit()
    db.refresh(warehouse)

    stock = Stock(warehouse_id=warehouse.id, product_id=1, quantity_available=quantity_available)
    db.add(stock)
    db.commit()

    return warehouse.id


def ship_via_api(quote_id):
    """Drives the real fulfillment suggest+confirm endpoints so tests use a
    genuinely confirmed FulfillmentPlan, the same way the real app does."""
    client.post(f"/quotes/{quote_id}/fulfillment/suggest")
    return client.post(f"/quotes/{quote_id}/fulfillment/confirm")


# ---- 1. calculate_invoiceable_amount (pure function) ----


def test_calculate_invoiceable_amount_excludes_backordered_lines():
    shipped = [ShippedQuantity(quote_line_id=1, quantity_shipped=8)]  # line 2 never shipped
    quote_lines = [
        InvoiceableLine(quote_line_id=1, unit_price=100, discount_pct=10),
        InvoiceableLine(quote_line_id=2, unit_price=50, discount_pct=0),
    ]

    amount = calculate_invoiceable_amount(shipped, quote_lines)

    # Only line 1's shipped 8 units count: 100 * 8 * 0.9 = 720. Line 2
    # contributes nothing since it has no shipped quantity at all.
    assert amount == pytest.approx(720.0)


def test_calculate_invoiceable_amount_bills_only_the_shipped_quantity():
    # Line 1 ordered 10, only 6 shipped (rest backordered/split elsewhere).
    shipped = [ShippedQuantity(quote_line_id=1, quantity_shipped=6)]
    quote_lines = [InvoiceableLine(quote_line_id=1, unit_price=100, discount_pct=0)]

    amount = calculate_invoiceable_amount(shipped, quote_lines)

    assert amount == pytest.approx(600.0)


# ---- 2 & 3. generate_invoice_for_confirmed_fulfillment via the API ----


def test_generate_invoice_on_confirmed_fulfillment_produces_correct_unpaid_invoice():
    db = TestingSessionLocal()
    quote_id, line_id = create_quote(db, quantity=10, discount_pct=10)
    add_stock(db, "Main WH", quantity_available=20)
    db.close()

    ship_response = ship_via_api(quote_id)
    assert ship_response.status_code == 200

    response = client.post(f"/quotes/{quote_id}/invoices/generate")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "unpaid"
    assert data["invoice_type"] == "one_time"
    assert data["quote_id"] == quote_id
    assert data["amount"] == pytest.approx(900.0)  # 100 * 10 * 0.9
    assert data["invoice_number"].startswith("INV-")


def test_generate_invoice_with_nothing_shipped_returns_400():
    db = TestingSessionLocal()
    quote_id, _ = create_quote(db, quantity=10)
    db.close()
    # Approved, but fulfillment was never suggested/confirmed - nothing shipped.

    response = client.post(f"/quotes/{quote_id}/invoices/generate")

    assert response.status_code == 400
    assert "shipped" in response.json()["detail"].lower()


def test_generate_invoice_on_draft_quote_returns_400():
    db = TestingSessionLocal()
    quote_id, _ = create_quote(db, status=QuoteStatus.draft, quantity=10)
    db.close()

    response = client.post(f"/quotes/{quote_id}/invoices/generate")

    assert response.status_code == 400


# ---- 4. Payment recording and status transitions ----


def test_partial_payment_keeps_unpaid_full_payment_marks_paid():
    db = TestingSessionLocal()
    quote_id, _ = create_quote(db, quantity=10, discount_pct=0)
    add_stock(db, "Main WH", quantity_available=20)
    db.close()
    ship_via_api(quote_id)
    invoice_id = client.post(f"/quotes/{quote_id}/invoices/generate").json()["id"]

    partial = client.post(
        f"/invoices/{invoice_id}/payments",
        json={"amount": 400, "method": "Bank Transfer", "recorded_by": "Alice"},
    )
    assert partial.status_code == 200
    assert partial.json()["status"] == "unpaid"
    assert len(partial.json()["payments"]) == 1

    remainder = client.post(
        f"/invoices/{invoice_id}/payments",
        json={"amount": 600, "method": "Bank Transfer", "recorded_by": "Alice"},
    )
    assert remainder.status_code == 200
    assert remainder.json()["status"] == "paid"
    assert len(remainder.json()["payments"]) == 2


# ---- 5. GET /invoices/{id} pipeline_stage across states ----


def test_pipeline_stage_is_invoiced_when_unpaid_and_paid_once_settled():
    db = TestingSessionLocal()
    quote_id, _ = create_quote(db, quantity=5, discount_pct=0)
    add_stock(db, "Main WH", quantity_available=20)
    db.close()
    ship_via_api(quote_id)
    invoice_id = client.post(f"/quotes/{quote_id}/invoices/generate").json()["id"]

    unpaid_detail = client.get(f"/invoices/{invoice_id}")
    assert unpaid_detail.status_code == 200
    assert unpaid_detail.json()["pipeline_stage"] == "Invoiced"
    assert unpaid_detail.json()["one_time_lines"][0]["quantity"] == 5

    client.post(
        f"/invoices/{invoice_id}/payments",
        json={"amount": 500, "method": "Cash", "recorded_by": "Bob"},
    )

    paid_detail = client.get(f"/invoices/{invoice_id}")
    assert paid_detail.json()["pipeline_stage"] == "Paid"


def test_get_invoice_list_filters_by_status():
    db = TestingSessionLocal()
    quote_id, _ = create_quote(db, quantity=5, discount_pct=0)
    add_stock(db, "Main WH", quantity_available=20)
    db.close()
    ship_via_api(quote_id)
    client.post(f"/quotes/{quote_id}/invoices/generate")

    unpaid = client.get("/invoices", params={"status": "unpaid"})
    paid = client.get("/invoices", params={"status": "paid"})

    assert len(unpaid.json()) == 1
    assert unpaid.json()[0]["customer_name"] == "Test Corp"
    assert len(paid.json()) == 0


# ---- 6. generate_recurring_invoice ----


def test_generate_recurring_invoice_links_to_subscription():
    db = TestingSessionLocal()
    quote_id, line_id = create_quote(db, quantity=1, discount_pct=0)
    quote_line = db.get(QuoteLine, line_id)
    quote_line.product_id = 2
    quote_line.is_recurring = True
    db.commit()

    subscription = Subscription(
        quote_line_id=line_id,
        subscription_plan_id=1,
        quantity=3,
        status=SubscriptionStatus.active,
        current_cycle_start=date(2026, 1, 1),
        current_cycle_end=date(2026, 2, 1),
    )
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    subscription_id = subscription.id
    db.close()

    response = client.post(f"/subscriptions/{subscription_id}/invoices/generate")

    assert response.status_code == 200
    data = response.json()
    assert data["invoice_type"] == "recurring"
    assert data["subscription_id"] == subscription_id
    assert data["amount"] == pytest.approx(150.0)  # 50 * 3
    assert data["quote_id"] == quote_id
