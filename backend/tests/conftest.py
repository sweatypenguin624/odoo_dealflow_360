"""Shared fixtures.

One in-memory SQLite engine for the whole session; every test gets a
freshly created schema plus a small baseline dataset (tiers, one
customer, two categories, two products, one user per role). Legacy tests
reference these baseline ids directly (customer 1, products 1/2), so the
ids are pinned.
"""

import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("EMAIL_PROVIDER", "console")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production-use")
os.environ.setdefault("PASSWORD_HASH_ROUNDS", "4")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.permissions import Role
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Category, Customer, CustomerTier, Product, User
from app.api.routes.auth import login_limiter, reset_limiter

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)


@event.listens_for(engine, "connect")
def _fk_on(dbapi_connection, _):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestingSessionLocal = sessionmaker(autocommit=False, autoflush=True, bind=engine, expire_on_commit=False)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

PASSWORD = "Passw0rd!2026"

USER_SPECS = {
    "admin": ("admin@test.local", "Ada Admin", Role.admin, None),
    "manager": ("manager@test.local", "Mona Manager", Role.sales_manager, "East"),
    "rep": ("rep@test.local", "Rita Rep", Role.sales_rep, "East"),
    "rep2": ("rep2@test.local", "Ravi Rep", Role.sales_rep, "West"),
    "finance": ("finance@test.local", "Finn Finance", Role.finance, None),
    "customer": ("customer@test.local", "Cathy Customer", Role.customer, None),
}


def seed_baseline(db):
    tier = CustomerTier(id=1, name="Gold", max_discount_pct=15)
    silver = CustomerTier(id=2, name="Silver", max_discount_pct=8)
    db.add_all([tier, silver])
    db.flush()
    customer = Customer(id=1, name="Test Corp", tier_id=1, email="buyer@testcorp.example", contact_name="Pat Buyer")
    db.add(customer)
    db.flush()
    hardware = Category(id=1, name="Hardware", max_discount_pct=10)
    services = Category(id=2, name="Services", max_discount_pct=None)
    db.add_all([hardware, services])
    db.flush()
    # unit_margin_pct is derived from cost: Laptop 20% margin, Setup 50%.
    laptop = Product(id=1, sku="HW-LAPTOP", name="Laptop", category_id=1, price=1000, cost=800)
    setup = Product(id=2, sku="SV-SETUP", name="Setup", category_id=2, price=200, cost=100)
    db.add_all([laptop, setup])
    db.flush()

    users = {}
    for key, (email, name, role, team) in USER_SPECS.items():
        user = User(
            email=email,
            full_name=name,
            hashed_password=hash_password(PASSWORD),
            role=role,
            team=team,
            customer_id=customer.id if role == Role.customer else None,
        )
        db.add(user)
        users[key] = user
    db.flush()
    customer.owner_user_id = users["rep"].id
    db.commit()
    return {k: u.id for k, u in users.items()}


@pytest.fixture(autouse=True)
def db_schema():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    ids = seed_baseline(db)
    db.close()
    login_limiter.reset()
    reset_limiter.reset()
    yield ids
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
        Base.metadata.drop_all(bind=conn)
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")
        conn.commit()


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    return TestClient(app)


class AuthClient:
    """Thin wrapper around TestClient that sends a bearer token."""

    def __init__(self, base: TestClient, token: str, user_id: int):
        self.base = base
        self.token = token
        self.user_id = user_id
        self.headers = {"Authorization": f"Bearer {token}"}

    def _call(self, method, url, **kwargs):
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.update(self.headers)
        return getattr(self.base, method)(url, headers=headers, **kwargs)

    def get(self, url, **kw):
        return self._call("get", url, **kw)

    def post(self, url, **kw):
        return self._call("post", url, **kw)

    def patch(self, url, **kw):
        return self._call("patch", url, **kw)

    def put(self, url, **kw):
        return self._call("put", url, **kw)

    def delete(self, url, **kw):
        return self._call("delete", url, **kw)


def login_as(client: TestClient, key: str) -> AuthClient:
    email = USER_SPECS[key][0]
    response = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    data = response.json()
    return AuthClient(client, data["access_token"], data["user"]["id"])


@pytest.fixture
def as_admin(client):
    return login_as(client, "admin")


@pytest.fixture
def as_manager(client):
    return login_as(client, "manager")


@pytest.fixture
def as_rep(client):
    return login_as(client, "rep")


@pytest.fixture
def as_rep2(client):
    return login_as(client, "rep2")


@pytest.fixture
def as_finance(client):
    return login_as(client, "finance")


@pytest.fixture
def as_customer(client):
    return login_as(client, "customer")


# ---- data helpers shared by the API tests ----


def make_quote(db, lines, *, status=None, owner_key="rep", customer_id=1, user_ids=None, **quote_fields):
    """Insert a quote directly (bypassing the API) with snapshotted prices.

    `lines` is a list of (product_id, quantity, discount_pct[, is_recurring]).
    Returns the quote id. Totals are computed by the domain service so the
    row is indistinguishable from one created through the API.
    """
    from app.models import Product, Quote, QuoteLine, QuoteStatus
    from app.services import quote_service
    from app.services.numbering import next_number

    owner = db.query(User).filter(User.email == USER_SPECS[owner_key][0]).one() if owner_key else None
    quote = Quote(
        quote_number=next_number(db, "quote"),
        customer_id=customer_id,
        owner_user_id=owner.id if owner else None,
        status=QuoteStatus(status) if status else QuoteStatus.draft,
        **quote_fields,
    )
    db.add(quote)
    db.flush()
    for spec in lines:
        product_id, quantity, discount = spec[0], spec[1], spec[2]
        is_recurring = spec[3] if len(spec) > 3 else False
        product = db.get(Product, product_id)
        db.add(
            QuoteLine(
                quote_id=quote.id,
                product_id=product_id,
                description=product.name,
                quantity=quantity,
                unit_price=product.price,
                unit_cost=product.cost,
                discount_pct=discount,
                tax_rate_pct=product.tax_rate_pct,
                is_recurring=is_recurring,
            )
        )
    db.flush()
    quote = quote_service.load_quote(db, quote.id)
    quote_service.recalculate(db, quote)
    if quote.status in (QuoteStatus.approved, QuoteStatus.sent, QuoteStatus.under_negotiation, QuoteStatus.confirmed):
        quote.approved_version = quote.version
    db.commit()
    return quote.id
