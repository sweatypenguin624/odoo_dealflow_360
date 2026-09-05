from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base
from app.models import (
    AuditLog,
    Category,
    CounterProposal,
    Customer,
    CustomerTier,
    PortalToken,
    Product,
    Quote,
    QuoteLine,
    QuoteStatus,
)
from app.dependencies.portal import get_db as portal_get_db
from app.routers.quotes import get_db as quotes_get_db
from app.services.portal_auth import generate_portal_token

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


# Only override this file's own dependency key at module scope. The
# internal quotes router's get_db is borrowed only within the one test
# that needs it (test 6), and popped immediately after, so it never
# leaks into other test files that also use quotes.get_db.
app.dependency_overrides[portal_get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    # Same numbers as Phase 2/3's existing risk_engine / approval_workflow
    # tests, reused deliberately to prove this phase calls the same engine.
    tier = CustomerTier(id=1, name="Gold", max_discount_pct=15)
    db.add(tier)

    customer = Customer(id=1, name="Test Corp", tier_id=1)
    db.add(customer)

    cat_hardware = Category(id=1, name="Hardware", max_discount_pct=10)
    cat_services = Category(id=2, name="Services", max_discount_pct=None)
    db.add_all([cat_hardware, cat_services])

    prod_laptop = Product(id=1, name="Laptop", category_id=1, price=1000, unit_margin_pct=20)
    prod_setup = Product(id=2, name="Setup", category_id=2, price=200, unit_margin_pct=50)
    db.add_all([prod_laptop, prod_setup])

    db.commit()
    db.close()

    yield

    Base.metadata.drop_all(bind=engine)


def create_quote(db, status=QuoteStatus.approved, laptop_discount=5, setup_discount=5):
    quote = Quote(customer_id=1, status=status)
    db.add(quote)
    db.commit()
    db.refresh(quote)

    laptop_line = QuoteLine(
        quote_id=quote.id, product_id=1, quantity=1, discount_pct=laptop_discount, line_value=1000
    )
    setup_line = QuoteLine(
        quote_id=quote.id, product_id=2, quantity=1, discount_pct=setup_discount, line_value=200
    )
    db.add_all([laptop_line, setup_line])
    db.commit()
    db.refresh(laptop_line)
    db.refresh(setup_line)

    return quote.id, laptop_line.id, setup_line.id


def make_token(db, quote_id, customer_id=1):
    portal_token = generate_portal_token(quote_id, customer_id, db)
    return portal_token.token


def test_valid_token_grants_access_invalid_token_401():
    db = TestingSessionLocal()
    quote_id, _, _ = create_quote(db)
    token = make_token(db, quote_id)
    db.close()

    ok_response = client.get("/portal/quote", headers={"X-Portal-Token": token})
    assert ok_response.status_code == 200
    assert ok_response.json()["quote_id"] == quote_id

    bad_response = client.get("/portal/quote", headers={"X-Portal-Token": "not-a-real-token"})
    assert bad_response.status_code == 401


def test_expired_token_401():
    db = TestingSessionLocal()
    quote_id, _, _ = create_quote(db)
    portal_token = PortalToken(
        quote_id=quote_id,
        token="expired-token-value",
        customer_id=1,
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db.add(portal_token)
    db.commit()
    db.close()

    response = client.get("/portal/quote", headers={"X-Portal-Token": "expired-token-value"})
    assert response.status_code == 401


def test_draft_quote_returns_403():
    db = TestingSessionLocal()
    quote_id, _, _ = create_quote(db, status=QuoteStatus.draft)
    token = make_token(db, quote_id)
    db.close()

    response = client.get("/portal/quote", headers={"X-Portal-Token": token})
    assert response.status_code == 403


def test_downgrade_only_counter_proposal_auto_applies_without_reapproval():
    db = TestingSessionLocal()
    quote_id, laptop_line_id, setup_line_id = create_quote(
        db, status=QuoteStatus.approved, laptop_discount=8, setup_discount=5
    )
    token = make_token(db, quote_id)
    db.close()

    response = client.post(
        "/portal/counter-proposal",
        headers={"X-Portal-Token": token},
        json={
            "proposed_lines": [
                {"quote_line_id": laptop_line_id, "proposed_discount_pct": 6},
                {"quote_line_id": setup_line_id, "proposed_discount_pct": 5},
            ]
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["counter_proposal"]["status"] == "accepted"
    assert data["quote"]["status"] == "approved"  # never touched pending_approval
    assert data["risk_result"] is None

    db = TestingSessionLocal()
    laptop_line = db.get(QuoteLine, laptop_line_id)
    assert laptop_line.discount_pct == 6
    proposal = db.query(CounterProposal).filter_by(quote_id=quote_id).one()
    assert proposal.status == "accepted"
    db.close()


def test_bigger_discount_within_limits_auto_applies():
    db = TestingSessionLocal()
    # Laptop limit is 10 (Hardware category); starting at 5, proposing 9 -
    # bigger than current but still within the category limit.
    quote_id, laptop_line_id, setup_line_id = create_quote(
        db, status=QuoteStatus.approved, laptop_discount=5, setup_discount=5
    )
    token = make_token(db, quote_id)
    db.close()

    response = client.post(
        "/portal/counter-proposal",
        headers={"X-Portal-Token": token},
        json={
            "proposed_lines": [
                {"quote_line_id": laptop_line_id, "proposed_discount_pct": 9},
                {"quote_line_id": setup_line_id, "proposed_discount_pct": 5},
            ]
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["risk_result"]["required_approval_level"] == "none"
    assert data["counter_proposal"]["status"] == "accepted"
    assert data["quote"]["status"] == "approved"


def test_bigger_discount_crossing_limit_triggers_reapproval():
    # Same numbers as the Phase 2/3 Laptop/Setup example: Setup Service
    # (Services category, no explicit limit -> falls back to the Gold
    # tier's 15%) proposed at 18% is 3 points over... use the Hardware
    # line instead to reuse the *exact* "8 points over" example: Laptop
    # (Hardware, limit 10) proposed at 18% -> 8 points over -> "manager".
    db = TestingSessionLocal()
    quote_id, laptop_line_id, setup_line_id = create_quote(
        db, status=QuoteStatus.approved, laptop_discount=5, setup_discount=0
    )
    token = make_token(db, quote_id)
    db.close()

    response = client.post(
        "/portal/counter-proposal",
        headers={"X-Portal-Token": token},
        json={
            "proposed_lines": [
                {"quote_line_id": laptop_line_id, "proposed_discount_pct": 18},
                {"quote_line_id": setup_line_id, "proposed_discount_pct": 0},
            ]
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["risk_result"]["required_approval_level"] == "manager"
    assert any("8" in reason for reason in data["risk_result"]["reasons"])
    assert data["quote"]["status"] == "pending_approval"
    assert data["quote"]["current_approval_step"] == "manager"
    assert data["counter_proposal"]["status"] == "pending"

    db = TestingSessionLocal()
    logs = db.query(AuditLog).filter_by(
        quote_id=quote_id, action="counter_proposal_triggered_reapproval"
    ).all()
    assert len(logs) == 1
    assert "8" in logs[0].reason
    # The live document reflects the negotiation even while re-approval pends.
    laptop_line = db.get(QuoteLine, laptop_line_id)
    assert laptop_line.discount_pct == 18
    db.close()


def test_internal_manager_approval_then_portal_confirm():
    db = TestingSessionLocal()
    quote_id, laptop_line_id, setup_line_id = create_quote(
        db, status=QuoteStatus.approved, laptop_discount=5, setup_discount=0
    )
    token = make_token(db, quote_id)
    db.close()

    client.post(
        "/portal/counter-proposal",
        headers={"X-Portal-Token": token},
        json={
            "proposed_lines": [
                {"quote_line_id": laptop_line_id, "proposed_discount_pct": 18},
                {"quote_line_id": setup_line_id, "proposed_discount_pct": 0},
            ]
        },
    )

    # Borrow the internal quotes router's db dependency for just this one
    # call to the pre-existing Phase 3 approval-action endpoint.
    app.dependency_overrides[quotes_get_db] = override_get_db
    try:
        approval_response = client.post(
            f"/quotes/{quote_id}/approval-action",
            json={"actor": "Manager Bob", "action": "approved"},
        )
    finally:
        app.dependency_overrides.pop(quotes_get_db, None)

    assert approval_response.status_code == 200
    assert approval_response.json()["quote"]["status"] == "approved"

    confirm_response = client.post("/portal/confirm", headers={"X-Portal-Token": token})
    assert confirm_response.status_code == 200
    assert confirm_response.json()["status"] == "confirmed"


def test_confirm_while_pending_approval_returns_400():
    db = TestingSessionLocal()
    quote_id, laptop_line_id, setup_line_id = create_quote(
        db, status=QuoteStatus.approved, laptop_discount=5, setup_discount=0
    )
    token = make_token(db, quote_id)
    db.close()

    client.post(
        "/portal/counter-proposal",
        headers={"X-Portal-Token": token},
        json={
            "proposed_lines": [
                {"quote_line_id": laptop_line_id, "proposed_discount_pct": 18},
                {"quote_line_id": setup_line_id, "proposed_discount_pct": 0},
            ]
        },
    )

    response = client.post("/portal/confirm", headers={"X-Portal-Token": token})
    assert response.status_code == 400


def test_counter_proposal_and_comment_reject_foreign_line():
    db = TestingSessionLocal()
    quote_id, _, _ = create_quote(db)
    token = make_token(db, quote_id)

    other_quote_id, other_line_id, _ = create_quote(db)
    db.close()

    proposal_response = client.post(
        "/portal/counter-proposal",
        headers={"X-Portal-Token": token},
        json={"proposed_lines": [{"quote_line_id": other_line_id, "proposed_discount_pct": 5}]},
    )
    assert proposal_response.status_code == 403

    comment_response = client.post(
        f"/portal/lines/{other_line_id}/comment",
        headers={"X-Portal-Token": token},
        json={"comment": "not my line"},
    )
    assert comment_response.status_code == 403
