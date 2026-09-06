"""Invoicing + payments (ported: invoiceable amount pure function, ship-gated
one-time invoice, nothing-shipped guard, draft guard, partial/full payment,
pipeline stage, list filter, recurring invoice link) plus overpayment,
refund, void, idempotent payment and sequence numbering."""

from datetime import date
from decimal import Decimal

import pytest

from app.models import Invoice, Payment, Stock, Subscription, SubscriptionPlan, SubscriptionStatus, Warehouse
from app.services.invoice_service import InvoiceableLine, ShippedQuantity, calculate_invoiceable_amount
from tests.conftest import make_quote


@pytest.fixture
def widget(as_admin):
    return as_admin.post("/products", json={"sku": "HW-WIDGET", "name": "Widget", "category_id": 1, "cost": 80, "price": 100}).json()["id"]


def create_quote(db, product_id, status="confirmed", quantity=10, discount_pct=0):
    from app.models import QuoteLine

    quote_id = make_quote(db, [(product_id, quantity, discount_pct)], status=status)
    return quote_id, db.query(QuoteLine).filter_by(quote_id=quote_id).first().id


def add_stock(db, product_id, quantity_available, name="Main"):
    wh = Warehouse(name=name, shipping_cost_weight=1.0)
    db.add(wh)
    db.flush()
    db.add(Stock(warehouse_id=wh.id, product_id=product_id, quantity_on_hand=quantity_available))
    db.commit()
    return wh.id


def ship_via_api(client, quote_id):
    client.post(f"/quotes/{quote_id}/fulfillment/suggest")
    client.post(f"/quotes/{quote_id}/fulfillment/confirm")
    return client.post(f"/quotes/{quote_id}/fulfillment/ship")


# ---- 1. calculate_invoiceable_amount (pure function) ----


def test_calculate_invoiceable_amount_excludes_backordered_lines():
    amount = calculate_invoiceable_amount(
        [ShippedQuantity(quote_line_id=1, quantity_shipped=8)],
        [InvoiceableLine(quote_line_id=1, unit_price=100, discount_pct=10), InvoiceableLine(quote_line_id=2, unit_price=50, discount_pct=0)],
    )
    assert amount == Decimal("720.00")


def test_calculate_invoiceable_amount_bills_only_the_shipped_quantity():
    amount = calculate_invoiceable_amount([ShippedQuantity(1, 6)], [InvoiceableLine(1, 100, 0)])
    assert amount == Decimal("600.00")


# ---- 2. generation ----


def test_generate_invoice_on_shipped_fulfillment_produces_correct_issued_invoice(as_finance, widget, db):
    quote_id, _ = create_quote(db, widget, quantity=10, discount_pct=10)
    add_stock(db, widget, 20)
    assert ship_via_api(as_finance, quote_id).status_code == 200
    response = as_finance.post(f"/quotes/{quote_id}/invoices/generate")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "issued" and data["invoice_type"] == "one_time" and data["quote_id"] == quote_id
    assert data["amount"] == 900  # 100 * 10 * 0.9
    assert data["outstanding"] == 900
    assert data["invoice_number"].startswith("INV-")
    assert as_finance.get(f"/quotes/{quote_id}").json()["billing_status"] == "billed"
    # everything shipped is now invoiced -> a second call is rejected, no duplicate
    dup = as_finance.post(f"/quotes/{quote_id}/invoices/generate")
    assert dup.status_code == 422 and "already invoiced" in dup.json()["detail"]
    assert db.query(Invoice).count() == 1


def test_partial_shipment_bills_only_shipped_then_the_remainder(as_finance, widget, db):
    quote_id, _ = create_quote(db, widget, quantity=10)
    wh = add_stock(db, widget, 6)
    ship_via_api(as_finance, quote_id)
    first = as_finance.post(f"/quotes/{quote_id}/invoices/generate").json()
    assert first["amount"] == 600
    assert as_finance.get(f"/quotes/{quote_id}").json()["billing_status"] == "billed"
    as_finance.post(f"/warehouses/{wh}/receipts", json={"product_id": widget, "quantity": 10})
    as_finance.post(f"/quotes/{quote_id}/fulfillment/consolidate-backorders")
    as_finance.post(f"/quotes/{quote_id}/fulfillment/ship")
    assert as_finance.get(f"/quotes/{quote_id}").json()["billing_status"] == "partially_billed"
    second = as_finance.post(f"/quotes/{quote_id}/invoices/generate").json()
    assert second["amount"] == 400


def test_generate_invoice_with_nothing_shipped_returns_422(as_finance, widget, db):
    quote_id, _ = create_quote(db, widget, quantity=10)
    add_stock(db, widget, 20)
    as_finance.post(f"/quotes/{quote_id}/fulfillment/suggest")
    as_finance.post(f"/quotes/{quote_id}/fulfillment/confirm")  # reserved, not shipped
    response = as_finance.post(f"/quotes/{quote_id}/invoices/generate")
    assert response.status_code == 422
    assert "shipped" in response.json()["detail"].lower()


def test_generate_invoice_on_draft_quote_returns_422(as_finance, widget, db):
    quote_id, _ = create_quote(db, widget, status="draft")
    response = as_finance.post(f"/quotes/{quote_id}/invoices/generate")
    assert response.status_code == 422


# ---- 3. payments ----


def issued_invoice(client, db, product_id, quantity=10):
    quote_id, _ = create_quote(db, product_id, quantity=quantity)
    add_stock(db, product_id, quantity + 10)
    ship_via_api(client, quote_id)
    return client.post(f"/quotes/{quote_id}/invoices/generate").json()["id"], quote_id


def test_partial_payment_then_full_payment_marks_paid(as_finance, widget, db):
    invoice_id, quote_id = issued_invoice(as_finance, db, widget)  # 1000
    partial = as_finance.post(f"/invoices/{invoice_id}/payments", json={"amount": 400, "method": "Bank Transfer", "reference": "TX-1"})
    assert partial.status_code == 200, partial.text
    assert partial.json()["status"] == "partially_paid" and partial.json()["outstanding"] == 600
    assert len(partial.json()["payments"]) == 1
    assert partial.json()["payments"][0]["recorded_by"] == "Finn Finance"
    remainder = as_finance.post(f"/invoices/{invoice_id}/payments", json={"amount": 600, "method": "Bank Transfer"})
    assert remainder.json()["status"] == "paid" and remainder.json()["outstanding"] == 0
    assert len(remainder.json()["payments"]) == 2
    assert as_finance.get(f"/quotes/{quote_id}").json()["billing_status"] == "paid"
    assert as_finance.post(f"/invoices/{invoice_id}/payments", json={"amount": 1, "method": "Cash"}).status_code == 409


def test_overpayment_is_rejected(as_finance, widget, db):
    invoice_id, _ = issued_invoice(as_finance, db, widget)
    res = as_finance.post(f"/invoices/{invoice_id}/payments", json={"amount": 1000.01, "method": "Card"})
    assert res.status_code == 422
    assert res.json()["code"] == "overpayment"
    assert as_finance.post(f"/invoices/{invoice_id}/payments", json={"amount": 0, "method": "Card"}).status_code == 422


def test_payment_with_idempotency_key_is_not_duplicated(as_finance, widget, db):
    invoice_id, _ = issued_invoice(as_finance, db, widget)
    headers = {"Idempotency-Key": "pay-abc-123"}
    first = as_finance.post(f"/invoices/{invoice_id}/payments", json={"amount": 300, "method": "Card"}, headers=headers)
    second = as_finance.post(f"/invoices/{invoice_id}/payments", json={"amount": 300, "method": "Card"}, headers=headers)
    assert first.status_code == 200 and second.status_code == 200
    assert second.json()["amount_paid"] == 300
    assert db.query(Payment).filter_by(invoice_id=invoice_id).count() == 1


def test_refund_reduces_paid_amount_and_cannot_exceed_it(as_finance, widget, db):
    invoice_id, _ = issued_invoice(as_finance, db, widget)
    as_finance.post(f"/invoices/{invoice_id}/payments", json={"amount": 1000, "method": "Card"})
    too_much = as_finance.post(f"/invoices/{invoice_id}/refunds", json={"amount": 1500, "method": "Card"})
    assert too_much.status_code == 422
    refund = as_finance.post(f"/invoices/{invoice_id}/refunds", json={"amount": 250, "method": "Card", "reason": "damaged unit"})
    assert refund.status_code == 200
    assert refund.json()["amount_paid"] == 750 and refund.json()["status"] == "partially_paid"
    assert [p["direction"] for p in refund.json()["payments"]] == ["payment", "refund"]
    payments = as_finance.get("/payments", params={"direction": "refund"}).json()
    assert payments["total"] == 1


def test_void_requires_no_payments_and_a_reason(as_finance, widget, db):
    invoice_id, quote_id = issued_invoice(as_finance, db, widget)
    assert as_finance.post(f"/invoices/{invoice_id}/void", json={"reason": ""}).status_code == 422
    as_finance.post(f"/invoices/{invoice_id}/payments", json={"amount": 100, "method": "Card"})
    assert as_finance.post(f"/invoices/{invoice_id}/void", json={"reason": "wrong customer"}).status_code == 409
    as_finance.post(f"/invoices/{invoice_id}/refunds", json={"amount": 100, "method": "Card"})
    voided = as_finance.post(f"/invoices/{invoice_id}/void", json={"reason": "wrong customer"})
    assert voided.status_code == 200 and voided.json()["status"] == "void"
    # the shipped quantity becomes invoiceable again
    assert as_finance.post(f"/quotes/{quote_id}/invoices/generate").status_code == 200


def test_pipeline_stage_and_list_filters(as_finance, as_rep, widget, db):
    invoice_id, _ = issued_invoice(as_finance, db, widget, quantity=5)
    unpaid = as_finance.get(f"/invoices/{invoice_id}").json()
    assert unpaid["pipeline_stage"] == "Invoiced" and unpaid["one_time_lines"][0]["quantity"] == 5
    assert unpaid["lines"][0]["quantity"] == 5
    assert as_rep.post(f"/invoices/{invoice_id}/payments", json={"amount": 500, "method": "Card"}).status_code == 403
    as_finance.post(f"/invoices/{invoice_id}/payments", json={"amount": 500, "method": "Card"})
    assert as_finance.get(f"/invoices/{invoice_id}").json()["pipeline_stage"] == "Paid"
    assert as_finance.get("/invoices", params={"status": "paid"}).json()["total"] == 1
    assert as_finance.get("/invoices", params={"status": "unpaid"}).json()["total"] == 0
    assert as_finance.get("/invoices", params={"status": "bogus"}).status_code == 422


def test_overdue_marking(as_finance, widget, db):
    invoice_id, _ = issued_invoice(as_finance, db, widget)
    invoice = db.get(Invoice, invoice_id)
    invoice.due_date = date(2020, 1, 1)
    db.commit()
    assert as_finance.get(f"/invoices/{invoice_id}").json()["is_overdue"] is True
    assert as_finance.post("/invoices/refresh-overdue").json()["marked_overdue"] == 1
    assert as_finance.get("/invoices", params={"status": "overdue"}).json()["total"] == 1


def test_invoice_numbers_are_unique_and_sequential(as_finance, widget, db):
    numbers = []
    for _ in range(3):
        invoice_id, _ = issued_invoice(as_finance, db, widget, quantity=1)
        numbers.append(db.get(Invoice, invoice_id).invoice_number)
    assert len(set(numbers)) == 3
    values = [int(n.split("-")[1]) for n in numbers]
    assert values == sorted(values) and values[2] - values[0] == 2


def test_generate_recurring_invoice_links_to_subscription(as_finance, db):
    support = SubscriptionPlan(name="Support Monthly", product_id=2, interval="monthly", price_per_interval=50)
    db.add(support)
    db.commit()
    quote_id, line_id = create_quote(db, 2, quantity=1)
    from app.models import QuoteLine

    db.get(QuoteLine, line_id).is_recurring = True
    subscription = Subscription(quote_line_id=line_id, quote_id=quote_id, customer_id=1, subscription_plan_id=support.id, quantity=3, status=SubscriptionStatus.active, current_cycle_start=date(2026, 1, 1), current_cycle_end=date(2026, 2, 1), next_billing_date=date(2026, 2, 1))
    db.add(subscription)
    db.commit()
    response = as_finance.post(f"/subscriptions/{subscription.id}/invoices/generate")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["invoice_type"] == "recurring" and data["subscription_id"] == subscription.id
    assert data["amount"] == 150  # 50 * 3
    assert data["quote_id"] == quote_id and data["billing_period_start"] == "2026-01-01"
    dup = as_finance.post(f"/subscriptions/{subscription.id}/invoices/generate")
    assert dup.status_code == 409
