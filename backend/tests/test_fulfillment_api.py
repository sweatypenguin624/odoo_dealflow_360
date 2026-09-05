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
    Stock,
    Warehouse,
)
from app.routers.fulfillment import get_db as fulfillment_get_db

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


app.dependency_overrides[fulfillment_get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    tier = CustomerTier(id=1, name="Gold", max_discount_pct=15)
    db.add(tier)

    customer = Customer(id=1, name="Test Corp", tier_id=1)
    db.add(customer)

    category = Category(id=1, name="Hardware", max_discount_pct=15)
    db.add(category)

    product = Product(id=1, name="Widget", category_id=1, price=50, unit_margin_pct=20)
    db.add(product)

    db.commit()
    db.close()

    yield

    Base.metadata.drop_all(bind=engine)


def create_quote(db, status=QuoteStatus.draft, quantity=10):
    quote = Quote(customer_id=1, status=status)
    db.add(quote)
    db.commit()
    db.refresh(quote)

    line = QuoteLine(quote_id=quote.id, product_id=1, quantity=quantity, discount_pct=0, line_value=quantity * 50)
    db.add(line)
    db.commit()
    db.refresh(line)

    return quote.id, line.id


def add_stock(db, warehouse_name, shipping_cost_weight, quantity_available):
    warehouse = Warehouse(name=warehouse_name, shipping_cost_weight=shipping_cost_weight)
    db.add(warehouse)
    db.commit()
    db.refresh(warehouse)

    stock = Stock(warehouse_id=warehouse.id, product_id=1, quantity_available=quantity_available)
    db.add(stock)
    db.commit()

    return warehouse.id


def test_suggest_on_non_approved_quote_returns_400():
    db = TestingSessionLocal()
    quote_id, _ = create_quote(db, status=QuoteStatus.draft, quantity=5)
    db.close()

    response = client.post(f"/quotes/{quote_id}/fulfillment/suggest")

    assert response.status_code == 400
    assert "approved" in response.json()["detail"]


def test_suggest_on_approved_quote_creates_suggested_plan():
    db = TestingSessionLocal()
    quote_id, line_id = create_quote(db, status=QuoteStatus.approved, quantity=10)
    warehouse_id = add_stock(db, "Main WH", shipping_cost_weight=1.0, quantity_available=20)
    db.close()

    response = client.post(f"/quotes/{quote_id}/fulfillment/suggest")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "suggested"
    assert len(data["splits"]) == 1
    assert data["splits"][0]["quote_line_id"] == line_id
    assert data["splits"][0]["warehouse_id"] == warehouse_id
    assert data["splits"][0]["quantity_fulfilled"] == 10
    assert data["splits"][0]["is_backorder"] is False
    assert data["backorder_summary"] == []


def test_confirm_decrements_stock_and_marks_plan_confirmed():
    db = TestingSessionLocal()
    quote_id, _ = create_quote(db, status=QuoteStatus.approved, quantity=10)
    warehouse_id = add_stock(db, "Main WH", shipping_cost_weight=1.0, quantity_available=20)
    db.close()

    client.post(f"/quotes/{quote_id}/fulfillment/suggest")
    response = client.post(f"/quotes/{quote_id}/fulfillment/confirm")

    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"

    db = TestingSessionLocal()
    stock = db.query(Stock).filter_by(warehouse_id=warehouse_id, product_id=1).first()
    assert stock.quantity_available == 10  # 20 - 10
    db.close()


def test_confirm_returns_409_when_stock_drops_before_confirm():
    db = TestingSessionLocal()
    quote_id, _ = create_quote(db, status=QuoteStatus.approved, quantity=10)
    warehouse_id = add_stock(db, "Main WH", shipping_cost_weight=1.0, quantity_available=20)
    db.close()

    client.post(f"/quotes/{quote_id}/fulfillment/suggest")

    # Stock is reduced after the suggestion was made (e.g. sold elsewhere).
    db = TestingSessionLocal()
    stock = db.query(Stock).filter_by(warehouse_id=warehouse_id, product_id=1).first()
    stock.quantity_available = 3
    db.commit()
    db.close()

    response = client.post(f"/quotes/{quote_id}/fulfillment/confirm")

    assert response.status_code == 409
    assert "3" in response.json()["detail"]

    db = TestingSessionLocal()
    stock = db.query(Stock).filter_by(warehouse_id=warehouse_id, product_id=1).first()
    assert stock.quantity_available == 3  # untouched by the failed confirm
    db.close()


def test_override_with_mismatched_quantities_returns_400():
    db = TestingSessionLocal()
    quote_id, line_id = create_quote(db, status=QuoteStatus.approved, quantity=10)
    warehouse_id = add_stock(db, "Main WH", shipping_cost_weight=1.0, quantity_available=20)
    db.close()

    client.post(f"/quotes/{quote_id}/fulfillment/suggest")

    response = client.patch(
        f"/quotes/{quote_id}/fulfillment/override",
        json={
            "allocations": [
                {"quote_line_id": line_id, "warehouse_id": warehouse_id, "quantity_fulfilled": 4}
            ]
        },
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert str(line_id) in detail
    assert "4" in detail
    assert "10" in detail
