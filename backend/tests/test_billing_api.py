import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base
from app.models import (
    Category,
    Customer,
    CustomerTier,
    Product,
    Quote,
    QuoteLine,
    QuoteStatus,
    SubscriptionPlan,
)
from app.routers.billing import get_db as billing_get_db

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


app.dependency_overrides[billing_get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    tier = CustomerTier(id=1, name="Gold", max_discount_pct=15)
    db.add(tier)

    customer = Customer(id=1, name="Test Corp", tier_id=1)
    db.add(customer)

    category = Category(id=1, name="Services", max_discount_pct=15)
    db.add(category)

    seats_product = Product(id=1, name="Seats", category_id=1, price=100, unit_margin_pct=50)
    onetime_product = Product(id=2, name="Onboarding", category_id=1, price=200, unit_margin_pct=40)
    db.add_all([seats_product, onetime_product])

    plan = SubscriptionPlan(
        id=1, name="Seats Monthly", product_id=1, interval="monthly", price_per_interval=100
    )
    db.add(plan)

    db.commit()
    db.close()

    yield

    Base.metadata.drop_all(bind=engine)


def create_quote_with_line(db, product_id=1, quantity=5, is_recurring=False):
    quote = Quote(customer_id=1, status=QuoteStatus.draft)
    db.add(quote)
    db.commit()
    db.refresh(quote)

    product = db.get(Product, product_id)
    line = QuoteLine(
        quote_id=quote.id,
        product_id=product_id,
        quantity=quantity,
        discount_pct=0,
        line_value=product.price * quantity,
        is_recurring=is_recurring,
    )
    db.add(line)
    db.commit()
    db.refresh(line)

    return quote.id, line.id


def test_subscribe_creates_subscription_and_initial_invoice_event():
    db = TestingSessionLocal()
    quote_id, line_id = create_quote_with_line(db, product_id=1, quantity=5)
    db.close()

    response = client.post(
        f"/quotes/{quote_id}/lines/{line_id}/subscribe",
        json={"subscription_plan_id": 1, "quantity": 5, "start_date": "2026-01-01"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["subscription"]["quantity"] == 5
    assert data["subscription"]["status"] == "active"
    assert data["subscription"]["current_cycle_start"] == "2026-01-01"
    assert data["billing_event"]["event_type"] == "invoice"
    assert data["billing_event"]["amount"] == 500  # 100 * 5


def test_quantity_change_creates_proration_event_and_updates_quantity():
    db = TestingSessionLocal()
    quote_id, line_id = create_quote_with_line(db, product_id=1, quantity=5)
    db.close()

    subscribe_response = client.post(
        f"/quotes/{quote_id}/lines/{line_id}/subscribe",
        json={"subscription_plan_id": 1, "quantity": 5, "start_date": "2026-01-01"},
    )
    subscription_id = subscribe_response.json()["subscription"]["id"]

    response = client.patch(
        f"/subscriptions/{subscription_id}/quantity",
        json={"new_quantity": 8, "change_date": "2026-01-16"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["subscription"]["quantity"] == 8
    assert data["billing_event"]["event_type"] == "proration_charge"
    assert data["billing_event"]["amount"] > 0


def test_cancel_sets_cancelled_writes_credit_event_and_audit_log():
    db = TestingSessionLocal()
    quote_id, line_id = create_quote_with_line(db, product_id=1, quantity=5)
    db.close()

    subscribe_response = client.post(
        f"/quotes/{quote_id}/lines/{line_id}/subscribe",
        json={"subscription_plan_id": 1, "quantity": 5, "start_date": "2026-01-01"},
    )
    subscription_id = subscribe_response.json()["subscription"]["id"]

    response = client.post(
        f"/subscriptions/{subscription_id}/cancel",
        json={"cancellation_date": "2026-01-16"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["subscription"]["status"] == "cancelled"
    assert data["billing_event"]["event_type"] == "cancellation_credit"
    assert data["billing_event"]["amount"] > 0

    from app.models import AuditLog

    db = TestingSessionLocal()
    logs = db.query(AuditLog).filter_by(quote_id=quote_id, action="subscription_cancelled").all()
    assert len(logs) == 1
    db.close()


def test_billing_summary_separates_onetime_and_recurring_lines():
    db = TestingSessionLocal()
    quote_id, onetime_line_id = create_quote_with_line(db, product_id=2, quantity=1)
    _, recurring_line_id = create_quote_with_line(db, product_id=1, quantity=5)
    db.close()

    # The two lines above were created on separate quotes; put both on one quote.
    db = TestingSessionLocal()
    onetime_line = db.get(QuoteLine, onetime_line_id)
    recurring_line = db.get(QuoteLine, recurring_line_id)
    recurring_line.quote_id = onetime_line.quote_id
    quote_id = onetime_line.quote_id
    db.commit()
    db.close()

    subscribe_response = client.post(
        f"/quotes/{quote_id}/lines/{recurring_line_id}/subscribe",
        json={"subscription_plan_id": 1, "quantity": 5, "start_date": "2026-01-01"},
    )
    subscription_id = subscribe_response.json()["subscription"]["id"]
    client.patch(
        f"/subscriptions/{subscription_id}/quantity",
        json={"new_quantity": 8, "change_date": "2026-01-16"},
    )

    response = client.get(f"/quotes/{quote_id}/billing-summary")

    assert response.status_code == 200
    data = response.json()

    assert len(data["one_time_lines"]) == 1
    assert data["one_time_lines"][0]["quote_line_id"] == onetime_line_id

    assert len(data["recurring_lines"]) == 1
    recurring = data["recurring_lines"][0]
    assert recurring["quote_line_id"] == recurring_line_id
    assert recurring["quantity"] == 8
    event_types = [e["event_type"] for e in recurring["billing_events"]]
    assert event_types == ["invoice", "proration_charge"]
