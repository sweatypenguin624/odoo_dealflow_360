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
    ProductPairing,
    Quote,
    QuoteLine,
    QuoteStatus,
)
from app.routers.upsell import get_db as upsell_get_db

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


app.dependency_overrides[upsell_get_db] = override_get_db
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

    laptop = Product(id=1, name="Laptop", category_id=1, price=1000, unit_margin_pct=20)
    mouse = Product(id=2, name="Mouse", category_id=1, price=50, unit_margin_pct=40)
    cable = Product(id=3, name="Cable", category_id=1, price=10, unit_margin_pct=5)
    keyboard = Product(id=4, name="Keyboard", category_id=1, price=80, unit_margin_pct=30)
    db.add_all([laptop, mouse, cable, keyboard])

    db.commit()
    db.close()

    yield

    Base.metadata.drop_all(bind=engine)


def create_quote_with_line(db, product_id=1, quantity=1, discount_pct=0):
    quote = Quote(customer_id=1, status=QuoteStatus.draft)
    db.add(quote)
    db.commit()
    db.refresh(quote)

    product = db.get(Product, product_id)
    line = QuoteLine(
        quote_id=quote.id,
        product_id=product_id,
        quantity=quantity,
        discount_pct=discount_pct,
        line_value=product.price * quantity,
    )
    db.add(line)
    db.commit()
    db.refresh(line)

    return quote.id, line.id


def test_margin_summary_returns_correct_totals_for_seeded_quote():
    db = TestingSessionLocal()
    # Laptop: price 1000, qty 2, discount 10% -> line price 1800, margin 20% -> 360
    quote_id, _ = create_quote_with_line(db, product_id=1, quantity=2, discount_pct=10)
    db.close()

    response = client.get(f"/quotes/{quote_id}/margin-summary")

    assert response.status_code == 200
    data = response.json()
    assert data["total_price"] == 1800
    assert data["total_margin_amount"] == 360
    assert round(data["overall_margin_pct"], 4) == round(360 / 1800 * 100, 4)


def test_upsell_suggestions_excludes_product_already_on_quote():
    db = TestingSessionLocal()
    quote_id, _ = create_quote_with_line(db, product_id=1)
    # Laptop (1) pairs with Mouse (2), already on the quote in this scenario.
    second_line = QuoteLine(quote_id=quote_id, product_id=2, quantity=1, discount_pct=0, line_value=50)
    db.add(second_line)
    db.add(ProductPairing(base_product_id=1, suggested_product_id=2, co_purchase_score=90, is_promoted=False))
    db.add(ProductPairing(base_product_id=1, suggested_product_id=4, co_purchase_score=50, is_promoted=False))
    db.commit()
    db.close()

    response = client.get(f"/quotes/{quote_id}/upsell-suggestions")

    assert response.status_code == 200
    product_ids = [s["product_id"] for s in response.json()]
    assert 2 not in product_ids  # already on the quote
    assert 4 in product_ids


def test_upsell_suggestions_deduplicates_keeping_highest_score():
    db = TestingSessionLocal()
    quote_id, _ = create_quote_with_line(db, product_id=1)
    second_line = QuoteLine(quote_id=quote_id, product_id=4, quantity=1, discount_pct=0, line_value=80)
    db.add(second_line)
    # Keyboard (4) is also on the quote, and both Laptop (1) and Keyboard (4)
    # pair with Mouse (2) — the higher score (75) should win.
    db.add(ProductPairing(base_product_id=1, suggested_product_id=2, co_purchase_score=30, is_promoted=False))
    db.add(ProductPairing(base_product_id=4, suggested_product_id=2, co_purchase_score=75, is_promoted=False))
    db.commit()
    db.close()

    response = client.get(f"/quotes/{quote_id}/upsell-suggestions")

    assert response.status_code == 200
    data = response.json()
    mouse_entries = [s for s in data if s["product_id"] == 2]
    assert len(mouse_entries) == 1


def test_add_suggestion_creates_line_and_updates_margin_summary():
    db = TestingSessionLocal()
    quote_id, line_id = create_quote_with_line(db, product_id=1)
    db.close()

    before = client.get(f"/quotes/{quote_id}/margin-summary").json()

    response = client.post(
        f"/quotes/{quote_id}/lines/{line_id}/add-suggestion",
        json={"product_id": 2, "quantity": 1},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["lines"]) == 2
    assert any(line["product_id"] == 2 for line in data["lines"])

    after = client.get(f"/quotes/{quote_id}/margin-summary").json()
    assert data["margin_summary"]["total_price"] == after["total_price"]
    assert after["total_price"] > before["total_price"]
    assert after["total_margin_amount"] > before["total_margin_amount"]
