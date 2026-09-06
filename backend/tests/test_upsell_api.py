"""Upsell / margin API (ported: pairing CRUD, margin summary, ranked
suggestions, accept suggestion) plus stock/promotion awareness and the
server-side recalculation of totals/risk after adding a line."""

from app.models import Stock, Warehouse
from tests.conftest import make_quote


def seed_catalog(as_admin, db):
    monitor = as_admin.post("/products", json={"sku": "HW-MON", "name": "Monitor", "category_id": 1, "cost": 225, "price": 300}).json()
    cable = as_admin.post("/products", json={"sku": "HW-CABLE", "name": "Cable", "category_id": 1, "cost": 18, "price": 20}).json()  # 10% margin
    as_admin.post("/product-pairings", json={"base_product_id": 1, "suggested_product_id": monitor["id"], "co_purchase_score": 40})
    as_admin.post("/product-pairings", json={"base_product_id": 1, "suggested_product_id": 2, "co_purchase_score": 10, "is_promoted": True, "promotion_label": "Setup bundle"})
    as_admin.post("/product-pairings", json={"base_product_id": 1, "suggested_product_id": cable["id"], "co_purchase_score": 90})
    return monitor, cable


def test_product_pairing_crud(as_admin):
    res = as_admin.post("/product-pairings", json={"base_product_id": 1, "suggested_product_id": 2, "co_purchase_score": 55, "is_promoted": True})
    assert res.status_code == 201
    assert res.json()["co_purchase_score"] == 55 and res.json()["is_promoted"] is True
    listing = as_admin.get("/product-pairings", params={"base_product_id": 1}).json()
    assert listing["total"] == 1


def test_margin_summary_uses_snapshotted_cost(as_rep, db):
    quote_id = make_quote(db, [(1, 2, 10), (2, 1, 0)])
    res = as_rep.get(f"/quotes/{quote_id}/margin-summary")
    assert res.status_code == 200
    body = res.json()
    # Laptop: 1000*2*0.9 = 1800 net, cost 1600 -> 200 margin; Setup: 200 net, cost 100 -> 100
    assert body["total_price"] == 2000
    assert body["total_margin_amount"] == 300
    assert body["overall_margin_pct"] == 15


def test_suggestions_are_ranked_filtered_and_stock_aware(as_admin, as_rep, db):
    monitor, cable = seed_catalog(as_admin, db)
    wh = Warehouse(name="Main", shipping_cost_weight=1)
    db.add(wh)
    db.flush()
    db.add(Stock(warehouse_id=wh.id, product_id=monitor["id"], quantity_on_hand=5, quantity_reserved=5))
    db.commit()
    quote_id = make_quote(db, [(1, 1, 0)])
    res = as_rep.get(f"/quotes/{quote_id}/upsell-suggestions")
    assert res.status_code == 200
    names = [s["name"] for s in res.json()]
    # Cable (10% margin) is dropped by the default 10% threshold? No: >= threshold keeps it. Promoted Setup first,
    # then in-stock-unknown Cable (score 90) before the out-of-stock Monitor.
    assert names == ["Setup", "Cable", "Monitor"]
    setup = res.json()[0]
    assert setup["is_promoted"] and setup["promotion_label"] == "Setup bundle" and setup["reason"] == "Setup bundle"
    monitor_row = res.json()[2]
    assert monitor_row["in_stock"] is False and monitor_row["stock_available"] == 0
    assert "out of stock" in monitor_row["reason"]
    assert setup["margin_delta_if_added"] > 0 and setup["price_impact"] == 200

    strict = as_rep.get(f"/quotes/{quote_id}/upsell-suggestions", params={"min_margin_pct_threshold": 20})
    assert [s["name"] for s in strict.json()] == ["Setup", "Monitor"]


def test_add_suggestion_recalculates_totals_and_risk(as_admin, as_rep, db):
    seed_catalog(as_admin, db)
    quote_id = make_quote(db, [(1, 1, 0)])
    detail = as_rep.get(f"/quotes/{quote_id}").json()
    line_id = detail["lines"][0]["id"]
    res = as_rep.post(f"/quotes/{quote_id}/lines/{line_id}/add-suggestion", json={"product_id": 2, "quantity": 1})
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body["lines"]) == 2
    assert body["quote"]["total"] == 1200
    assert body["margin_summary"]["total_price"] == 1200
    assert body["quote"]["risk"]["required_approval_level"] == "none"
    # The suggestion is no longer offered once it's on the quote
    assert all(s["product_id"] != 2 for s in as_rep.get(f"/quotes/{quote_id}/upsell-suggestions").json())
    # Adding through the modern endpoint respects state restrictions
    approved = make_quote(db, [(1, 1, 0)], status="approved")
    assert as_rep.post(f"/quotes/{approved}/upsell/add", json={"product_id": 2}).status_code == 409
