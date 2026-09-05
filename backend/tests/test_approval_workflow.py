import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import Base
from app.models import CustomerTier, Customer, Category, Product, Quote, QuoteLine, QuoteStatus, AuditLog, ApprovalAction
from app.routers.quotes import get_db

from sqlalchemy.pool import StaticPool

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    
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


def create_test_quote(db, discount_laptop=0, discount_setup=0):
    quote = Quote(customer_id=1, status=QuoteStatus.draft)
    db.add(quote)
    db.commit()
    db.refresh(quote)
    
    if discount_laptop > 0 or discount_setup >= 0: # just to add some lines
        line1 = QuoteLine(quote_id=quote.id, product_id=1, quantity=1, discount_pct=discount_laptop, line_value=1000)
        line2 = QuoteLine(quote_id=quote.id, product_id=2, quantity=1, discount_pct=discount_setup, line_value=200)
        db.add_all([line1, line2])
        db.commit()
        
    return quote.id


def test_submit_no_violations_auto_approves():
    db = TestingSessionLocal()
    quote_id = create_test_quote(db, discount_laptop=5, discount_setup=5) # 5 <= 10, 5 <= 15
    db.close()
    
    response = client.post(f"/quotes/{quote_id}/submit")
    assert response.status_code == 200
    data = response.json()["quote"]
    
    assert data["status"] == "approved"
    assert data["current_approval_step"] is None
    
    db = TestingSessionLocal()
    logs = db.query(AuditLog).filter_by(quote_id=quote_id, action="auto_approved").all()
    assert len(logs) == 1
    db.close()


def test_submit_manager_only():
    db = TestingSessionLocal()
    # laptop discount 18, limit 10 -> 8 points over. Severity = 8 -> manager (5 <= 8 < 15)
    quote_id = create_test_quote(db, discount_laptop=18, discount_setup=0)
    db.close()
    
    response = client.post(f"/quotes/{quote_id}/submit")
    assert response.status_code == 200
    data = response.json()["quote"]
    assert data["status"] == "pending_approval"
    assert data["current_approval_step"] == "manager"
    
    # Manager approves
    res_approve = client.post(f"/quotes/{quote_id}/approval-action", json={
        "actor": "Manager Bob",
        "action": "approved",
        "note": "looks fine"
    })
    assert res_approve.status_code == 200
    approve_data = res_approve.json()["quote"]
    assert approve_data["status"] == "approved"
    assert approve_data["current_approval_step"] is None


def test_submit_manager_then_finance():
    db = TestingSessionLocal()
    # laptop discount 30, limit 10 -> 20 points over. Severity = 20 -> manager_then_finance
    quote_id = create_test_quote(db, discount_laptop=30, discount_setup=0)
    db.close()
    
    response = client.post(f"/quotes/{quote_id}/submit")
    assert response.status_code == 200
    data = response.json()["quote"]
    assert data["status"] == "pending_approval"
    assert data["current_approval_step"] == "manager"
    
    # Manager approves
    res_approve_mgr = client.post(f"/quotes/{quote_id}/approval-action", json={
        "actor": "Manager Bob",
        "action": "approved"
    })
    mgr_data = res_approve_mgr.json()["quote"]
    assert mgr_data["status"] == "pending_approval"
    assert mgr_data["current_approval_step"] == "finance"
    
    # Finance approves
    res_approve_fin = client.post(f"/quotes/{quote_id}/approval-action", json={
        "actor": "Finance Alice",
        "action": "approved"
    })
    fin_data = res_approve_fin.json()["quote"]
    assert fin_data["status"] == "approved"
    assert fin_data["current_approval_step"] is None


def test_rejection_stops_chain():
    db = TestingSessionLocal()
    quote_id = create_test_quote(db, discount_laptop=30, discount_setup=0) # manager_then_finance
    db.close()
    
    client.post(f"/quotes/{quote_id}/submit")
    
    # Manager rejects
    res_reject = client.post(f"/quotes/{quote_id}/approval-action", json={
        "actor": "Manager Bob",
        "action": "rejected"
    })
    reject_data = res_reject.json()["quote"]
    assert reject_data["status"] == "rejected"
    assert reject_data["current_approval_step"] is None


def test_returned_for_revision_resets_quote():
    db = TestingSessionLocal()
    quote_id = create_test_quote(db, discount_laptop=18, discount_setup=0) # manager
    db.close()
    
    client.post(f"/quotes/{quote_id}/submit")
    
    res_revise = client.post(f"/quotes/{quote_id}/approval-action", json={
        "actor": "Manager Bob",
        "action": "returned_for_revision"
    })
    revise_data = res_revise.json()["quote"]
    assert revise_data["status"] == "draft"
    assert revise_data["current_approval_step"] is None
    assert revise_data["required_approval_level"] is None


def test_approval_action_when_not_pending_fails():
    db = TestingSessionLocal()
    quote_id = create_test_quote(db, discount_laptop=18, discount_setup=0) # draft
    db.close()
    
    # Try to approve without submitting
    res_approve = client.post(f"/quotes/{quote_id}/approval-action", json={
        "actor": "Manager Bob",
        "action": "approved"
    })
    assert res_approve.status_code == 400
    assert "not pending approval" in res_approve.json()["detail"]


def test_pending_approval_queue_and_history():
    db = TestingSessionLocal()
    quote_id1 = create_test_quote(db, discount_laptop=18, discount_setup=0) # manager
    quote_id2 = create_test_quote(db, discount_laptop=30, discount_setup=0) # manager_then_finance (currently manager)
    db.close()
    
    client.post(f"/quotes/{quote_id1}/submit")
    client.post(f"/quotes/{quote_id2}/submit")
    
    # Both are at 'manager' step
    res_queue = client.get("/quotes/pending-approval?step=manager")
    assert res_queue.status_code == 200
    assert len(res_queue.json()) >= 2
    
    # Manager approves quote_id2
    client.post(f"/quotes/{quote_id2}/approval-action", json={"actor": "Manager Bob", "action": "approved"})
    
    # Now quote_id2 is at finance step
    res_queue_fin = client.get("/quotes/pending-approval?step=finance")
    assert len(res_queue_fin.json()) >= 1
    
    # History for quote_id2
    res_history = client.get(f"/quotes/{quote_id2}/approval-history")
    assert res_history.status_code == 200
    history = res_history.json()
    assert len(history["approval_actions"]) == 1
    assert len(history["audit_logs"]) >= 2 # submitted, manager approved
