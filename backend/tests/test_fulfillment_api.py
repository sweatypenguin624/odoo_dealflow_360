"""Fulfillment API: warehouse split, reservation, shipping, backorders.

Ported from the original suite (suggest guard, suggested plan, confirm
decrements available stock, 409 when stock dropped, override mismatch)
onto the reserve -> ship model, plus the new production scenarios:
concurrent orders competing for the same stock, backorder consolidation
after a receipt, and the one-query fulfillment list.
"""

from app.models import Stock, Warehouse
from tests.conftest import make_quote


def create_quote(db, status="confirmed", quantity=10, product_id=1):
    quote_id = make_quote(db, [(product_id, quantity, 0)], status=status)
    from app.models import QuoteLine

    line = db.query(QuoteLine).filter_by(quote_id=quote_id).first()
    return quote_id, line.id


def add_stock(db, warehouse_name, shipping_cost_weight, quantity_available, product_id=1):
    warehouse = Warehouse(name=warehouse_name, shipping_cost_weight=shipping_cost_weight)
    db.add(warehouse)
    db.flush()
    db.add(Stock(warehouse_id=warehouse.id, product_id=product_id, quantity_on_hand=quantity_available, quantity_reserved=0))
    db.commit()
    return warehouse.id


def stock_row(db, warehouse_id, product_id=1):
    db.expire_all()
    return db.query(Stock).filter_by(warehouse_id=warehouse_id, product_id=product_id).one()


def test_suggest_on_unconfirmed_quote_is_rejected(as_finance, db):
    quote_id, _ = create_quote(db, status="draft")
    add_stock(db, "Main WH", 1.0, 20)
    response = as_finance.post(f"/quotes/{quote_id}/fulfillment/suggest")
    assert response.status_code == 409
    assert "approved" in response.json()["detail"] and "confirmed" in response.json()["detail"]


def test_suggest_on_confirmed_quote_creates_suggested_plan(as_finance, db):
    quote_id, line_id = create_quote(db, quantity=10)
    warehouse_id = add_stock(db, "Main WH", 1.0, 20)
    response = as_finance.post(f"/quotes/{quote_id}/fulfillment/suggest")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "suggested"
    assert len(data["splits"]) == 1
    split = data["splits"][0]
    assert split["quote_line_id"] == line_id and split["warehouse_id"] == warehouse_id
    assert split["quantity_fulfilled"] == 10 and split["is_backorder"] is False and split["status"] == "planned"
    assert data["backorder_summary"] == []
    assert "confirm" in data["available_actions"]
    assert as_finance.get(f"/quotes/{quote_id}").json()["fulfillment_status"] == "planned"


def test_confirm_reserves_stock_and_ship_consumes_it(as_finance, db):
    quote_id, _ = create_quote(db, quantity=10)
    warehouse_id = add_stock(db, "Main WH", 1.0, 20)
    as_finance.post(f"/quotes/{quote_id}/fulfillment/suggest")
    response = as_finance.post(f"/quotes/{quote_id}/fulfillment/confirm")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "confirmed"
    assert response.json()["units_reserved"] == 10
    stock = stock_row(db, warehouse_id)
    assert stock.quantity_available == 10  # 20 - 10 reserved
    assert stock.quantity_on_hand == 20 and stock.quantity_reserved == 10

    shipped = as_finance.post(f"/quotes/{quote_id}/fulfillment/ship", json={"tracking_reference": "TRK-1"})
    assert shipped.status_code == 200, shipped.text
    body = shipped.json()
    assert body["status"] == "shipped" and body["units_shipped"] == 10
    assert len(body["shipments"]) == 1 and body["shipments"][0]["shipment_number"].startswith("SHP-")
    stock = stock_row(db, warehouse_id)
    assert stock.quantity_on_hand == 10 and stock.quantity_reserved == 0
    assert as_finance.get(f"/quotes/{quote_id}").json()["fulfillment_status"] == "shipped"

    movements = as_finance.get("/inventory/movements", params={"warehouse_id": warehouse_id}).json()["items"]
    assert [m["movement_type"] for m in movements] == ["consumption", "reservation"]

    delivered = as_finance.post(f"/quotes/{quote_id}/fulfillment/shipments/{body['shipments'][0]['id']}/deliver")
    assert delivered.status_code == 200
    assert as_finance.get(f"/quotes/{quote_id}").json()["fulfillment_status"] == "delivered"


def test_confirm_returns_409_when_stock_drops_before_confirm(as_finance, db):
    quote_id, _ = create_quote(db, quantity=10)
    warehouse_id = add_stock(db, "Main WH", 1.0, 20)
    as_finance.post(f"/quotes/{quote_id}/fulfillment/suggest")
    stock = stock_row(db, warehouse_id)
    stock.quantity_on_hand = 3
    db.commit()
    response = as_finance.post(f"/quotes/{quote_id}/fulfillment/confirm")
    assert response.status_code == 409
    assert "3" in response.json()["detail"]
    assert response.json()["code"] == "stock_shortage"
    assert stock_row(db, warehouse_id).quantity_available == 3  # untouched by the failed confirm


def test_two_orders_cannot_both_reserve_the_same_units(as_finance, db):
    """Warehouse A has 10 available; order 1 and order 2 each need 8."""
    warehouse_id = add_stock(db, "A", 1.0, 10)
    q1, _ = create_quote(db, quantity=8)
    q2, _ = create_quote(db, quantity=8)
    as_finance.post(f"/quotes/{q1}/fulfillment/suggest")
    as_finance.post(f"/quotes/{q2}/fulfillment/suggest")  # both plans were suggested against 10 available
    assert as_finance.post(f"/quotes/{q1}/fulfillment/confirm").status_code == 200
    second = as_finance.post(f"/quotes/{q2}/fulfillment/confirm")
    assert second.status_code == 409
    assert stock_row(db, warehouse_id).quantity_reserved == 8
    # Re-suggesting order 2 now correctly backorders the shortfall.
    replanned = as_finance.post(f"/quotes/{q2}/fulfillment/suggest").json()
    assert replanned["units_backordered"] == 6
    assert sum(s["quantity_fulfilled"] for s in replanned["splits"] if not s["is_backorder"]) == 2


def test_override_with_mismatched_quantities_returns_422(as_finance, db):
    quote_id, line_id = create_quote(db, quantity=10)
    warehouse_id = add_stock(db, "Main WH", 1.0, 20)
    as_finance.post(f"/quotes/{quote_id}/fulfillment/suggest")
    response = as_finance.patch(
        f"/quotes/{quote_id}/fulfillment/override",
        json={"allocations": [{"quote_line_id": line_id, "warehouse_id": warehouse_id, "quantity_fulfilled": 4}]},
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert str(line_id) in detail and "4" in detail and "10" in detail


def test_override_warns_when_exceeding_stock_and_reps_cannot_override(as_finance, as_rep, db):
    quote_id, line_id = create_quote(db, quantity=10)
    wh_a = add_stock(db, "A", 1.0, 4)
    wh_b = add_stock(db, "B", 2.0, 20)
    as_finance.post(f"/quotes/{quote_id}/fulfillment/suggest")
    payload = {"allocations": [{"quote_line_id": line_id, "warehouse_id": wh_a, "quantity_fulfilled": 6}, {"quote_line_id": line_id, "warehouse_id": wh_b, "quantity_fulfilled": 4}]}
    assert as_rep.patch(f"/quotes/{quote_id}/fulfillment/override", json=payload).status_code == 403
    res = as_finance.patch(f"/quotes/{quote_id}/fulfillment/override", json=payload)
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "manually_overridden"
    warned = [s for s in res.json()["splits"] if s["warning"]]
    assert len(warned) == 1 and "exceeds" in warned[0]["warning"]
    # confirming the over-allocated plan fails cleanly
    assert as_finance.post(f"/quotes/{quote_id}/fulfillment/confirm").status_code == 409


def test_multi_warehouse_split_and_backorder_consolidation(as_finance, as_admin, db):
    """Order 20 units: A has 6 (cheap), B has 8 -> 14 shipped from two warehouses,
    6 backordered. A receipt arrives at B, consolidation reserves the rest."""
    wh_a = add_stock(db, "A", 1.0, 6)
    wh_b = add_stock(db, "B", 1.5, 8)
    quote_id, line_id = create_quote(db, quantity=20)
    plan = as_finance.post(f"/quotes/{quote_id}/fulfillment/suggest").json()
    assert plan["total_shipments"] == 2 and plan["units_backordered"] == 6
    assert len(plan["backorder_summary"]) == 1 and "6 of 20" in plan["backorder_summary"][0]

    confirmed = as_finance.post(f"/quotes/{quote_id}/fulfillment/confirm").json()
    assert confirmed["units_reserved"] == 14 and confirmed["units_backordered"] == 6
    assert "consolidate" in confirmed["available_actions"]

    backorders = as_finance.get("/fulfillment/backorders").json()
    assert backorders["total"] == 1
    assert backorders["items"][0]["quantity"] == 6 and backorders["items"][0]["can_consolidate"] is False

    shipped = as_finance.post(f"/quotes/{quote_id}/fulfillment/ship").json()
    assert shipped["status"] == "partially_shipped" and len(shipped["shipments"]) == 2
    assert as_finance.get(f"/quotes/{quote_id}").json()["fulfillment_status"] == "partially_shipped"

    # Nothing to consolidate yet
    assert as_finance.post(f"/quotes/{quote_id}/fulfillment/consolidate-backorders").json()["units_reserved"] == 0

    # Incoming stock at B
    receipt = as_finance.post(f"/warehouses/{wh_b}/receipts", json={"product_id": 1, "quantity": 4, "note": "PO-77"})
    assert receipt.status_code == 201 and receipt.json()["quantity_available"] == 4
    assert as_finance.get("/fulfillment/backorders").json()["items"][0]["can_consolidate"] is True

    consolidated = as_finance.post(f"/quotes/{quote_id}/fulfillment/consolidate-backorders").json()
    assert consolidated["units_reserved"] == 4 and consolidated["units_still_backordered"] == 2
    assert stock_row(db, wh_b).quantity_reserved == 4

    as_finance.post(f"/warehouses/{wh_a}/receipts", json={"product_id": 1, "quantity": 10})
    final = as_finance.post(f"/quotes/{quote_id}/fulfillment/consolidate-backorders").json()
    assert final["units_still_backordered"] == 0
    assert as_finance.get("/fulfillment/backorders").json()["total"] == 0

    shipped_rest = as_finance.post(f"/quotes/{quote_id}/fulfillment/ship").json()
    assert shipped_rest["status"] == "shipped" and shipped_rest["units_shipped"] == 20

    listing = as_finance.get("/fulfillment").json()
    assert listing["total"] == 1
    row = listing["items"][0]
    assert row["fulfillment_status"] == "shipped" and row["shipment_count"] == 4 and row["units_backordered"] == 0


def test_release_gives_stock_back(as_finance, db):
    warehouse_id = add_stock(db, "A", 1.0, 10)
    quote_id, _ = create_quote(db, quantity=8)
    as_finance.post(f"/quotes/{quote_id}/fulfillment/suggest")
    as_finance.post(f"/quotes/{quote_id}/fulfillment/confirm")
    assert stock_row(db, warehouse_id).quantity_available == 2
    res = as_finance.post(f"/quotes/{quote_id}/fulfillment/release", params={"reason": "customer postponed"})
    assert res.status_code == 200 and res.json()["status"] == "cancelled"
    assert stock_row(db, warehouse_id).quantity_available == 10


def test_inventory_adjustment_and_low_stock(as_finance, as_rep, db):
    warehouse_id = add_stock(db, "A", 1.0, 10)
    assert as_rep.post(f"/warehouses/{warehouse_id}/adjustments", json={"product_id": 1, "quantity_on_hand": 5, "reason": "count"}).status_code == 403
    no_reason = as_finance.post(f"/warehouses/{warehouse_id}/adjustments", json={"product_id": 1, "quantity_on_hand": 5, "reason": " "})
    assert no_reason.status_code == 422
    ok = as_finance.post(f"/warehouses/{warehouse_id}/adjustments", json={"product_id": 1, "quantity_on_hand": 2, "reason": "cycle count", "reorder_point": 3})
    assert ok.status_code == 200 and ok.json()["needs_replenishment"] is True
    low = as_finance.get("/inventory", params={"low_stock": True}).json()
    assert low["total"] == 1 and low["items"][0]["quantity_available"] == 2
