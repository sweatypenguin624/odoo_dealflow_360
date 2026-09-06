"""Deal-health alerts + actions, dashboard KPIs, reports/exports, search, audit."""

from datetime import date, datetime, timedelta, timezone

from app.models import AuditLog, DealHealthAlert, EmailMessage, Invoice, Quote, Stock, Warehouse
from tests.conftest import make_quote


def backdate(db, quote_id, days):
    quote = db.get(Quote, quote_id)
    quote.last_activity_at = datetime.now(timezone.utc) - timedelta(days=days)
    quote.created_at = quote.last_activity_at
    db.commit()


def test_engine_creates_dedupes_and_autoresolves_alerts(as_manager, as_rep, db):
    stalled = make_quote(db, [(1, 1, 0)], status="draft")
    backdate(db, stalled, 12)
    first = as_manager.post("/deal-health/run").json()
    assert first["created"] == 1
    again = as_manager.post("/deal-health/run").json()
    assert again["created"] == 0 and again["open"] == 1
    alerts = as_manager.get("/deal-health/alerts").json()
    assert alerts["total"] == 1
    alert = alerts["items"][0]
    assert alert["alert_type"] == "stalled" and alert["severity"] == "warning" and alert["link"].endswith(f"/quotations/{stalled}")
    assert "notify_rep" in alert["available_actions"]
    # rep was notified in-app
    assert any(n["type"] == "deal_stalled" for n in as_rep.get("/notifications").json()["items"])
    # activity clears the condition -> auto-resolved on the next run
    as_rep.patch(f"/quotes/{stalled}", json={"notes": "called them"})
    resolved = as_manager.post("/deal-health/run").json()
    assert resolved["resolved"] == 1
    assert as_manager.get("/deal-health/alerts", params={"status": "resolved"}).json()["total"] == 1


def test_discount_anomaly_delivery_slippage_and_approval_aging(as_manager, as_admin, db):
    # baseline: rep closes two deals at 5%
    for _ in range(2):
        make_quote(db, [(1, 1, 5)], status="confirmed")
    anomaly = make_quote(db, [(2, 1, 15)], status="approved")  # 15% vs 5% average -> critical (>2x)
    late = make_quote(db, [(1, 1, 0)], status="confirmed", promised_delivery_date=date.today() - timedelta(days=7), expected_delivery_date=date.today() + timedelta(days=1))
    aging = make_quote(db, [(1, 1, 18)], status="draft")
    from tests.conftest import login_as

    rep = login_as(as_manager.base, "rep")
    rep.post(f"/quotes/{aging}/submit")
    from app.models import ApprovalRequest

    req = db.query(ApprovalRequest).filter_by(quote_id=aging).one()
    req.created_at = datetime.now(timezone.utc) - timedelta(days=6)
    db.commit()

    as_manager.post("/deal-health/run")
    items = as_manager.get("/deal-health/alerts", params={"page_size": 50}).json()["items"]
    by_key = {(i["quote_id"], i["alert_type"]): i for i in items}
    assert by_key[(anomaly, "discount_anomaly")]["severity"] == "critical"
    assert by_key[(late, "delivery_slippage")]["severity"] == "critical"
    assert "8 day" in by_key[(late, "delivery_slippage")]["message"]
    assert by_key[(aging, "approval_aging")]["link"].endswith(f"/approvals/{aging}")
    assert (aging, "discount_anomaly") in by_key  # the 18% quote is also far above the rep's 5% baseline
    summary = as_manager.get("/deal-health/summary").json()
    assert summary["open"] == 4 and summary["by_severity"]["critical"] >= 2

    # thresholds are configurable: loosen slippage and it disappears
    as_admin.put("/settings/delivery_slippage_warning_days", json={"value": 30})
    as_manager.post("/deal-health/run")
    assert as_manager.get("/deal-health/alerts", params={"alert_type": "delivery_slippage"}).json()["total"] == 0


def test_alert_actions_create_real_notifications_and_emails(as_manager, as_rep, db):
    quote_id = make_quote(db, [(1, 1, 0)], status="sent")
    backdate(db, quote_id, 10)
    as_manager.post("/deal-health/run")
    alert_id = as_manager.get("/deal-health/alerts").json()["items"][0]["id"]

    nudge = as_manager.post(f"/deal-health/alerts/{alert_id}/actions", json={"action_type": "notify_rep", "note": "Please follow up today"})
    assert nudge.status_code == 200, nudge.text
    assert nudge.json()["status"] == "acknowledged"
    assert nudge.json()["actions"][0]["action_type"] == "notify_rep" and nudge.json()["actions"][0]["recipients"] == ["rep@test.local"]
    inbox = as_rep.get("/notifications").json()["items"]
    assert any(n["type"] == "deal_health_notify_rep" and "Please follow up today" in (n["body"] or "") for n in inbox)
    assert db.query(EmailMessage).filter(EmailMessage.to_address == "rep@test.local").count() >= 1

    remind = as_manager.post(f"/deal-health/alerts/{alert_id}/actions", json={"action_type": "remind_customer"})
    assert remind.status_code == 200
    assert db.query(EmailMessage).filter(EmailMessage.to_address == "buyer@testcorp.example").count() == 1

    escalate = as_manager.post(f"/deal-health/alerts/{alert_id}/actions", json={"action_type": "escalate", "note": "VIP account"})
    assert escalate.status_code == 200

    resolved = as_manager.post(f"/deal-health/alerts/{alert_id}/actions", json={"action_type": "resolve", "note": "customer signed"})
    assert resolved.json()["status"] == "resolved"
    assert as_manager.post(f"/deal-health/alerts/{alert_id}/actions", json={"action_type": "notify_rep"}).status_code == 409
    assert db.query(AuditLog).filter(AuditLog.action.like("deal_health_%")).count() >= 4
    # reps can't escalate, only nudge their manager
    other = make_quote(db, [(1, 1, 0)], status="draft")
    backdate(db, other, 10)
    as_manager.post("/deal-health/run")
    other_alert = as_rep.get("/deal-health/alerts").json()["items"][0]
    assert "escalate" not in other_alert["available_actions"] and "notify_manager" in other_alert["available_actions"]
    assert as_rep.post(f"/deal-health/alerts/{other_alert['id']}/actions", json={"action_type": "escalate"}).status_code == 403


def test_legacy_deal_health_view_and_rep_scoping(as_rep, as_rep2, db):
    quote_id = make_quote(db, [(1, 1, 0)], status="draft")
    backdate(db, quote_id, 9)
    mine = as_rep.get("/dashboard/deal-health").json()
    assert any(q["quote_id"] == quote_id and q["flags"][0]["flag_type"] == "stalled" for q in mine)
    assert as_rep2.get("/dashboard/deal-health").json() == []


def test_dashboard_summary_is_role_aware(as_rep, as_rep2, as_manager, as_finance, db):
    make_quote(db, [(1, 2, 0)], status="draft")
    make_quote(db, [(1, 1, 18)], status="draft")
    pending = make_quote(db, [(1, 1, 18)], status="draft")
    as_rep.post(f"/quotes/{pending}/submit")
    summary = as_rep.get("/dashboard/summary").json()
    assert summary["role"] == "sales_rep"
    assert summary["kpis"]["open_quotes"] == 3 and summary["kpis"]["pipeline_value"] == 3640  # 2000 + 820 + 820
    assert summary["kpis"]["pending_approvals"] == 1
    assert len(summary["recent_activity"]) >= 1
    assert as_rep2.get("/dashboard/summary").json()["kpis"]["open_quotes"] == 0
    assert as_manager.get("/dashboard/summary").json()["kpis"]["pending_approvals"] == 1
    assert as_finance.get("/dashboard/summary").json()["kpis"]["pending_approvals"] == 0


def test_reports_and_exports(as_manager, as_rep, as_finance, db):
    make_quote(db, [(1, 2, 12)], status="confirmed")
    make_quote(db, [(2, 1, 0)], status="rejected")
    make_quote(db, [(1, 1, 5)], status="draft")
    listing = as_manager.get("/reports").json()
    assert {r["name"] for r in listing} == {"sales", "discounts", "fulfillment", "billing", "deal-health"}
    sales = as_manager.get("/reports/sales").json()
    assert sales["summary"]["quote_count"] == 3 and sales["summary"]["won_count"] == 1 and sales["summary"]["conversion_rate"] == 50.0
    assert sales["rows"][0]["rep"] == "Rita Rep"
    filtered = as_manager.get("/reports/sales", params={"quote_status": "confirmed"}).json()
    assert filtered["summary"]["quote_count"] == 1
    assert as_manager.get("/reports/sales", params={"category_id": 2}).json()["summary"]["quote_count"] == 1
    discounts = as_manager.get("/reports/discounts").json()
    assert discounts["summary"]["average_discount_pct"] > 0 and any(r["label"] == "Hardware" for r in discounts["by_category"])
    billing = as_finance.get("/reports/billing").json()
    assert billing["summary"]["invoice_count"] == 0
    health = as_manager.get("/reports/deal-health").json()
    assert "stalled_deals" in health["summary"]

    for fmt, ctype in (("csv", "text/csv"), ("xlsx", "spreadsheetml"), ("pdf", "application/pdf")):
        res = as_manager.get("/reports/sales/export", params={"format": fmt, "quote_status": "confirmed"})
        assert res.status_code == 200, res.text
        assert ctype in res.headers["content-type"]
        assert f"sales-report.{fmt}" in res.headers["content-disposition"]
        assert len(res.content) > 50
    csv_text = as_manager.get("/reports/sales/export", params={"format": "csv"}).text
    assert csv_text.splitlines()[0] == "rep,team,quotes,quote_value,won,won_value,conversion_rate"
    assert as_manager.get("/reports/nope").status_code == 404
    assert as_rep.get("/reports/sales").status_code == 403


def test_global_search_is_scoped_and_finds_by_identifiers(as_rep, as_rep2, as_admin, db):
    quote_id = make_quote(db, [(1, 1, 0)], status="confirmed", order_number="SO-90001")
    number = db.get(Quote, quote_id).quote_number
    res = as_rep.get("/search", params={"q": number})
    assert res.status_code == 200
    assert res.json()["quotes"][0]["id"] == quote_id
    assert as_rep.get("/search", params={"q": "SO-90001"}).json()["orders"][0]["id"] == quote_id
    assert as_rep.get("/search", params={"q": "HW-LAP"}).json()["products"][0]["sku"] == "HW-LAPTOP"
    assert as_rep.get("/search", params={"q": "test corp"}).json()["customers"][0]["id"] == 1
    assert as_rep2.get("/search", params={"q": number}).json()["quotes"] == []
    assert as_rep.get("/search", params={"q": ""}).status_code == 422


def test_audit_log_listing_is_admin_only_and_filterable(as_admin, as_rep, db):
    quote_id = make_quote(db, [(1, 1, 5)])
    as_rep.patch(f"/quotes/{quote_id}", json={"notes": "hello"})
    detail = as_rep.get(f"/quotes/{quote_id}").json()
    as_rep.patch(f"/quotes/{quote_id}/lines/{detail['lines'][0]['id']}", json={"discount_pct": 8})
    assert as_rep.get("/audit-logs").status_code == 403
    logs = as_admin.get("/audit-logs", params={"quote_id": quote_id}).json()
    actions = {l["action"] for l in logs["items"]}
    assert {"quote_updated", "discount_changed"} <= actions
    changed = as_admin.get("/audit-logs", params={"action": "discount_changed"}).json()["items"][0]
    assert changed["before_data"]["discount_pct"] == "5.00" and changed["after_data"]["discount_pct"] == "8.00"
    assert changed["actor_user_id"] == as_rep.user_id


def test_internal_confirm_creates_order_and_subscriptions(as_rep, as_admin, db):
    plan = as_admin.post("/subscription-plans", json={"name": "Setup Monthly", "product_id": 2, "interval": "monthly", "price_per_interval": 50}).json()
    as_admin.patch("/products/2", json={"product_type": "both"})
    quote = as_rep.post("/quotes", json={"customer_id": 1, "lines": [{"product_id": 1, "quantity": 2, "discount_pct": 5}, {"product_id": 2, "quantity": 3, "subscription_plan_id": plan["id"]}]}).json()
    assert quote["lines"][1]["is_recurring"] is True and quote["lines"][1]["unit_price"] == 50
    assert quote["total"] == 2 * 1000 * 0.95 + 150
    assert as_rep.post(f"/quotes/{quote['id']}/confirm").status_code == 409  # must be approved first
    as_rep.post(f"/quotes/{quote['id']}/submit")
    confirmed = as_rep.post(f"/quotes/{quote['id']}/confirm", json={"reason": "PO #4711 received"})
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "confirmed" and confirmed.json()["order_number"].startswith("SO-")
    subs = as_rep.get("/subscriptions").json()
    assert subs["total"] == 1 and subs["items"][0]["quantity"] == 3 and subs["items"][0]["cycle_amount"] == 150
    assert "fulfill" in confirmed.json()["available_actions"]
