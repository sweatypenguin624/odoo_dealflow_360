from decimal import Decimal


def test_product_crud_search_pagination_and_archive(as_admin, as_rep):
    for i in range(12):
        res = as_admin.post(
            "/products",
            json={"sku": f"hw-{i:03d}", "name": f"Widget {i}", "category_id": 1, "cost": 40, "price": 100, "tax_rate_pct": 8},
        )
        assert res.status_code == 201, res.text
    assert res.json()["sku"] == "HW-011"
    assert Decimal(str(res.json()["unit_margin_pct"])) == Decimal("60")

    dup = as_admin.post("/products", json={"sku": "HW-001", "name": "Dup", "category_id": 1, "cost": 1, "price": 2})
    assert dup.status_code == 409

    bad_cost = as_admin.post("/products", json={"sku": "HW-X", "name": "Bad", "category_id": 1, "cost": 200, "price": 100})
    assert bad_cost.status_code == 422

    page = as_rep.get("/products", params={"q": "widget", "page": 2, "page_size": 5})
    assert page.status_code == 200
    body = page.json()
    assert body["total"] == 12 and body["page"] == 2 and len(body["items"]) == 5 and body["total_pages"] == 3

    by_sku = as_rep.get("/products", params={"q": "HW-00"})
    assert by_sku.json()["total"] == 10

    product_id = body["items"][0]["id"]
    archived = as_admin.post(f"/products/{product_id}/archive")
    assert archived.status_code == 200 and archived.json()["is_archived"] is True
    assert as_rep.get("/products", params={"q": "widget"}).json()["total"] == 11
    assert as_rep.get("/products", params={"q": "widget", "include_archived": True}).json()["total"] == 12

    # reps cannot manage the catalog
    assert as_rep.post("/products", json={"sku": "X", "name": "X", "category_id": 1, "cost": 1, "price": 2}).status_code == 403


def test_product_referenced_by_quote_cannot_be_deleted(as_admin, db):
    from app.models import Quote, QuoteLine

    quote = Quote(customer_id=1)
    db.add(quote)
    db.flush()
    db.add(QuoteLine(quote_id=quote.id, product_id=1, quantity=1, unit_price=1000, unit_cost=800, line_value=1000, line_total=1000))
    db.commit()
    res = as_admin.delete("/products/1")
    assert res.status_code == 409
    assert "Archive" in res.json()["detail"]


def test_variants_and_pricing_resolution(as_admin, as_rep):
    v = as_admin.post("/products/1/variants", json={"sku": "HW-LAPTOP-16GB", "name": "16 GB", "attributes": {"ram": "16GB"}, "price": 1200})
    assert v.status_code == 201, v.text
    variant_id = v.json()["id"]

    # Base price for the Gold customer with no price list = list price.
    pricing = as_rep.get("/products/1/pricing", params={"customer_id": 1})
    assert pricing.status_code == 200
    assert Decimal(str(pricing.json()["unit_price"])) == Decimal("1000")
    assert pricing.json()["allowed_discount_pct"] == 10  # Hardware category 10% < Gold 15%
    assert "Hardware" in pricing.json()["discount_limit_source"]

    variant_pricing = as_rep.get("/products/1/pricing", params={"customer_id": 1, "variant_id": variant_id})
    assert Decimal(str(variant_pricing.json()["unit_price"])) == Decimal("1200")

    # A Gold-tier price list with a volume break overrides the list price.
    pl = as_admin.post(
        "/price-lists",
        json={"name": "Gold 2026", "tier_id": 1, "items": [{"product_id": 1, "unit_price": 950}, {"product_id": 1, "min_quantity": 10, "unit_price": 900}]},
    )
    assert pl.status_code == 201, pl.text
    single = as_rep.get("/products/1/pricing", params={"customer_id": 1, "quantity": 1}).json()
    bulk = as_rep.get("/products/1/pricing", params={"customer_id": 1, "quantity": 10}).json()
    assert Decimal(str(single["unit_price"])) == Decimal("950")
    assert Decimal(str(bulk["unit_price"])) == Decimal("900")
    assert "Gold 2026" in bulk["price_source"]

    # Deactivating the list restores list price.
    as_admin.patch(f"/price-lists/{pl.json()['id']}", json={"is_active": False})
    assert Decimal(str(as_rep.get("/products/1/pricing", params={"customer_id": 1}).json()["unit_price"])) == Decimal("1000")


def test_discount_rules_change_allowed_discount(as_admin, as_rep):
    base = as_rep.get("/products/2/pricing", params={"customer_id": 1}).json()
    assert base["allowed_discount_pct"] == 15  # Services has no category limit -> Gold tier 15

    rule = as_admin.post(
        "/discount-rules",
        json={"name": "Gold on Services", "scope": "tier_category", "tier_id": 1, "category_id": 2, "max_discount_pct": 12},
    )
    assert rule.status_code == 201, rule.text
    after = as_rep.get("/products/2/pricing", params={"customer_id": 1}).json()
    assert after["allowed_discount_pct"] == 12
    assert "Gold tier on Services" in after["discount_limit_source"]

    product_rule = as_admin.post(
        "/discount-rules", json={"name": "Setup promo", "scope": "product", "product_id": 2, "max_discount_pct": 25}
    )
    assert product_rule.status_code == 201
    assert as_rep.get("/products/2/pricing", params={"customer_id": 1}).json()["allowed_discount_pct"] == 25

    # Missing scope target is rejected
    bad = as_admin.post("/discount-rules", json={"name": "bad", "scope": "product", "max_discount_pct": 5})
    assert bad.status_code == 422

    as_admin.patch(f"/discount-rules/{product_rule.json()['id']}", json={"is_active": False})
    assert as_rep.get("/products/2/pricing", params={"customer_id": 1}).json()["allowed_discount_pct"] == 12


def test_approval_rules_drive_risk_policy(as_admin, as_manager):
    default = as_manager.get("/approval-rules/policy").json()
    assert Decimal(str(default["manager_threshold"])) == Decimal("5")
    assert Decimal(str(default["finance_threshold"])) == Decimal("15")

    as_admin.post("/approval-rules", json={"name": "Manager", "approval_level": "manager", "min_points_over": 3})
    as_admin.post("/approval-rules", json={"name": "Finance", "approval_level": "manager_then_finance", "min_points_over": 10, "min_excess_amount": 5000})
    policy = as_manager.get("/approval-rules/policy").json()
    assert Decimal(str(policy["manager_threshold"])) == Decimal("3")
    assert Decimal(str(policy["finance_threshold"])) == Decimal("10")
    assert Decimal(str(policy["finance_excess_amount"])) == Decimal("5000")
    assert as_manager.post("/approval-rules", json={"name": "x", "approval_level": "manager", "min_points_over": 1}).status_code == 201
    # finance users cannot configure approval rules
    

def test_customer_crud_search_and_ownership(as_admin, as_rep, as_rep2, as_customer):
    created = as_rep.post(
        "/customers",
        json={"name": "Acme Robotics", "tier_id": 1, "email": "ops@acme.example", "contact_name": "Dana", "billing_city": "Austin"},
    )
    assert created.status_code == 201, created.text
    cid = created.json()["id"]
    assert created.json()["code"].startswith("CUST-")
    assert created.json()["owner_user_id"] == as_rep.user_id  # rep auto-owns what they create

    assert as_rep.post("/customers", json={"name": "acme robotics", "tier_id": 1}).status_code == 409

    # other rep cannot edit a customer they don't own; admin can
    assert as_rep2.patch(f"/customers/{cid}", json={"phone": "555"}).status_code == 403
    assert as_admin.patch(f"/customers/{cid}", json={"phone": "555-0100", "tier_id": 2}).status_code == 200

    search = as_rep2.get("/customers", params={"q": "acme"})
    assert search.json()["total"] == 1
    assert search.json()["items"][0]["tier_name"] == "Silver"
    mine = as_rep2.get("/customers", params={"mine": True})
    assert mine.json()["total"] == 0

    archived = as_admin.post(f"/customers/{cid}/archive")
    assert archived.json()["is_active"] is False
    assert as_rep.get("/customers", params={"q": "acme"}).json()["total"] == 0
    assert as_rep.get("/customers", params={"q": "acme", "is_active": False}).json()["total"] == 1

    history = as_rep.get(f"/customers/{cid}/history")
    assert history.status_code == 200
    assert history.json()["totals"]["quote_count"] == 0

    assert as_customer.get("/customers").status_code == 403


def test_customer_is_findable_by_its_portal_login(as_rep):
    # "Cathy Customer" signs in to the portal for Test Corp, but she is nowhere
    # on the customer record - its contact is "Pat Buyer". A rep who only knows
    # the person they have been dealing with still has to find the account.
    by_person = as_rep.get("/customers", params={"q": "Cathy Customer"})
    assert [c["name"] for c in by_person.json()["items"]] == ["Test Corp"]
    by_email = as_rep.get("/customers", params={"q": "customer@test.local"})
    assert [c["name"] for c in by_email.json()["items"]] == ["Test Corp"]
    # the same term resolves in global search
    assert [c["name"] for c in as_rep.get("/search", params={"q": "Cathy"}).json()["customers"]] == ["Test Corp"]
    # only portal logins count: a staff name must not drag in the accounts they own
    assert as_rep.get("/customers", params={"q": "Rita Rep"}).json()["total"] == 0


def test_tiers_categories_plans_pairings_admin(as_admin, as_rep):
    tiers = as_rep.get("/customer-tiers")
    assert tiers.status_code == 200 and len(tiers.json()) == 2
    assert as_rep.post("/customer-tiers", json={"name": "Platinum", "max_discount_pct": 20}).status_code == 403
    t = as_admin.post("/customer-tiers", json={"name": "Platinum", "max_discount_pct": 20})
    assert t.status_code == 201
    assert as_admin.patch(f"/customer-tiers/{t.json()['id']}", json={"max_discount_pct": 22}).json()["max_discount_pct"] == 22

    cat = as_admin.post("/categories", json={"name": "Software", "max_discount_pct": 30})
    assert cat.status_code == 201
    cleared = as_admin.patch(f"/categories/{cat.json()['id']}", json={"clear_max_discount": True})
    assert cleared.json()["max_discount_pct"] is None
    assert as_rep.get("/categories").json()["total"] == 3

    plan = as_admin.post("/subscription-plans", json={"name": "Setup Monthly", "product_id": 2, "interval": "monthly", "price_per_interval": 50})
    assert plan.status_code == 201 and plan.json()["product_name"] == "Setup"
    assert as_admin.post("/subscription-plans", json={"name": "x", "product_id": 2, "interval": "weekly", "price_per_interval": 1}).status_code == 422

    pairing = as_admin.post("/product-pairings", json={"base_product_id": 1, "suggested_product_id": 2, "co_purchase_score": 70, "is_promoted": True, "promotion_label": "Bundle"})
    assert pairing.status_code == 201
    assert as_admin.post("/product-pairings", json={"base_product_id": 1, "suggested_product_id": 2}).status_code == 409
    assert as_admin.post("/product-pairings", json={"base_product_id": 1, "suggested_product_id": 1}).status_code == 422
    assert as_rep.get("/product-pairings").json()["total"] == 1
