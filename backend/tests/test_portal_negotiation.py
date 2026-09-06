"""Customer portal + negotiation loop.

Ported from the original suite (token validation, 403 for unsent quotes,
downgrade auto-apply, within-limit auto-apply, over-limit re-approval,
manager approval then confirm, confirm-while-pending guard, foreign-line
rejection) with the new state machine: quotes must be *sent* to be
visible, negotiated terms return the quote to the customer, and the
customer view never exposes internal data.
"""

from datetime import datetime, timedelta, timezone

from app.models import AuditLog, CounterProposal, PortalToken, QuoteLine, QuoteStatus
from app.services.portal_auth import generate_portal_token
from tests.conftest import make_quote


def sent_quote(db, discount_laptop=5, discount_setup=0, status="sent"):
    return make_quote(db, [(1, 1, discount_laptop), (2, 1, discount_setup)], status=status)


def token_for(db, quote_id, **kwargs):
    return generate_portal_token(quote_id, 1, db, **kwargs).token


def headers(token):
    return {"X-Portal-Token": token}


def test_valid_token_grants_access_invalid_token_401(client, db):
    quote_id = sent_quote(db)
    token = token_for(db, quote_id)
    ok = client.get("/portal/quote", headers=headers(token))
    assert ok.status_code == 200, ok.text
    assert ok.json()["quote_id"] == quote_id
    assert ok.json()["status"] == "Sent"
    assert client.get("/portal/quote", headers=headers("garbage")).status_code == 401
    assert client.get("/portal/quote").status_code == 401


def test_portal_view_never_leaks_internal_data(client, db):
    quote_id = sent_quote(db, discount_laptop=18)
    token = token_for(db, quote_id)
    body = client.get("/portal/quote", headers=headers(token)).text
    for forbidden in ("unit_cost", "margin", "risk", "points_over", "applicable_limit", "approval"):
        assert forbidden not in body
    data = client.get("/portal/quote", headers=headers(token)).json()
    assert data["lines"][0]["product_name"] == "Laptop"


def test_expired_and_revoked_tokens_401(client, db):
    quote_id = sent_quote(db)
    expired = token_for(db, quote_id, expires_in_hours=-1)
    assert client.get("/portal/quote", headers=headers(expired)).status_code == 401
    token = token_for(db, quote_id)
    row = db.query(PortalToken).filter(PortalToken.token == token).one()
    row.revoked_at = datetime.now(timezone.utc)
    db.commit()
    assert client.get("/portal/quote", headers=headers(token)).status_code == 401


def test_unsent_quote_returns_403(client, db):
    for status in ("draft", "approved", "pending_approval"):
        quote_id = sent_quote(db, status=status)
        token = token_for(db, quote_id)
        res = client.get("/portal/quote", headers=headers(token))
        if status == "pending_approval":
            assert res.status_code == 200 and res.json()["status"] == "Under Review"
        else:
            assert res.status_code == 403


def test_downgrade_only_counter_proposal_auto_applies_without_reapproval(client, db):
    quote_id = sent_quote(db, discount_laptop=8, discount_setup=0)
    token = token_for(db, quote_id)
    laptop_line = db.query(QuoteLine).filter_by(quote_id=quote_id, product_id=1).one()
    res = client.post(
        "/portal/counter-proposal", headers=headers(token),
        json={"proposed_lines": [{"quote_line_id": laptop_line.id, "proposed_discount_pct": 6}]},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["counter_proposal"]["status"] == "accepted"
    assert data["quote"]["status"] == "under_negotiation"  # never touched pending_approval
    assert data["risk_result"] is None
    db.expire_all()
    assert float(db.get(QuoteLine, laptop_line.id).discount_pct) == 6
    assert db.query(CounterProposal).filter_by(quote_id=quote_id).one().status == "accepted"
    view = client.get("/portal/quote", headers=headers(token)).json()
    assert view["can_confirm"] is True and view["status"] == "Under Negotiation"


def test_bigger_discount_within_limits_auto_applies(client, db):
    quote_id = sent_quote(db, discount_laptop=5)
    token = token_for(db, quote_id)
    laptop_line = db.query(QuoteLine).filter_by(quote_id=quote_id, product_id=1).one()
    res = client.post(
        "/portal/counter-proposal", headers=headers(token),
        json={"proposed_lines": [{"quote_line_id": laptop_line.id, "proposed_discount_pct": 9}]},
    )
    data = res.json()
    assert data["risk_result"]["required_approval_level"] == "none"
    assert data["counter_proposal"]["status"] == "accepted"
    assert data["quote"]["status"] == "under_negotiation"
    assert client.get("/portal/quote", headers=headers(token)).json()["can_confirm"] is True


def test_bigger_discount_crossing_limit_triggers_reapproval(client, as_manager, db):
    quote_id = sent_quote(db, discount_laptop=5)
    token = token_for(db, quote_id)
    laptop_line = db.query(QuoteLine).filter_by(quote_id=quote_id, product_id=1).one()
    res = client.post(
        "/portal/counter-proposal", headers=headers(token),
        json={"proposed_lines": [{"quote_line_id": laptop_line.id, "proposed_discount_pct": 18}], "message": "Budget is tight"},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["risk_result"]["required_approval_level"] == "manager"
    assert any("8" in reason for reason in data["risk_result"]["reasons"])
    assert data["quote"]["status"] == "pending_approval"
    assert data["quote"]["current_approval_step"] == "manager"
    assert data["counter_proposal"]["status"] == "pending"
    assert data["customer_status"] == "Under Review"

    logs = db.query(AuditLog).filter_by(quote_id=quote_id, action="counter_proposal_triggered_reapproval").all()
    assert len(logs) == 1 and "8" in logs[0].reason
    db.expire_all()
    assert float(db.get(QuoteLine, laptop_line.id).discount_pct) == 18

    # the manager was notified and sees it in the queue
    assert as_manager.get("/approvals").json()["total"] == 1
    inbox = as_manager.get("/notifications").json()["items"]
    assert any(n["type"] == "approval_required" for n in inbox)
    # the customer cannot confirm nor submit another proposal meanwhile
    assert client.post("/portal/confirm", headers=headers(token)).status_code == 409
    again = client.post("/portal/counter-proposal", headers=headers(token), json={"proposed_lines": [{"quote_line_id": laptop_line.id, "proposed_discount_pct": 12}]})
    assert again.status_code == 409


def test_internal_manager_approval_then_portal_confirm(client, as_manager, as_rep, db):
    quote_id = sent_quote(db, discount_laptop=5)
    token = token_for(db, quote_id)
    laptop_line = db.query(QuoteLine).filter_by(quote_id=quote_id, product_id=1).one()
    client.post("/portal/counter-proposal", headers=headers(token), json={"proposed_lines": [{"quote_line_id": laptop_line.id, "proposed_discount_pct": 18}]})

    approval = as_manager.post(f"/quotes/{quote_id}/approval-action", json={"action": "approved", "note": "strategic account"})
    assert approval.status_code == 200, approval.text
    assert approval.json()["quote"]["status"] == "under_negotiation"  # back with the customer
    assert approval.json()["quote"]["approval_valid"] is True

    view = client.get("/portal/quote", headers=headers(token)).json()
    assert view["can_confirm"] is True
    assert view["lines"][0]["discount_pct"] == 18
    assert view["history"][0]["status"] == "accepted"

    confirm = client.post("/portal/confirm", headers=headers(token))
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["status"] == "confirmed"
    assert confirm.json()["order_number"].startswith("SO-")
    # the rep and finance were notified
    assert any(n["type"] == "customer_confirmation" for n in as_rep.get("/notifications").json()["items"])


def test_manager_rejecting_counter_proposal_restores_original_terms(client, as_manager, db):
    quote_id = sent_quote(db, discount_laptop=5)
    token = token_for(db, quote_id)
    laptop_line = db.query(QuoteLine).filter_by(quote_id=quote_id, product_id=1).one()
    client.post("/portal/counter-proposal", headers=headers(token), json={"proposed_lines": [{"quote_line_id": laptop_line.id, "proposed_discount_pct": 18}]})
    res = as_manager.post(f"/quotes/{quote_id}/approval-action", json={"action": "rejected", "note": "cannot go that deep"})
    assert res.status_code == 200
    assert res.json()["quote"]["status"] == "under_negotiation"
    db.expire_all()
    assert float(db.get(QuoteLine, laptop_line.id).discount_pct) == 5
    assert db.query(CounterProposal).filter_by(quote_id=quote_id).one().status == "rejected"
    view = client.get("/portal/quote", headers=headers(token)).json()
    assert view["can_confirm"] is True and view["lines"][0]["discount_pct"] == 5
    assert client.post("/portal/confirm", headers=headers(token)).status_code == 200


def test_confirm_while_pending_approval_returns_409(client, db):
    quote_id = sent_quote(db, status="pending_approval")
    token = token_for(db, quote_id)
    res = client.post("/portal/confirm", headers=headers(token))
    assert res.status_code == 409
    assert "pending approval" in res.json()["detail"]


def test_counter_proposal_and_comment_reject_foreign_line(client, db):
    quote_id = sent_quote(db)
    other_id = sent_quote(db)
    token = token_for(db, quote_id)
    foreign_line = db.query(QuoteLine).filter_by(quote_id=other_id).first()
    assert client.post("/portal/counter-proposal", headers=headers(token), json={"proposed_lines": [{"quote_line_id": foreign_line.id, "proposed_discount_pct": 1}]}).status_code == 403
    assert client.post(f"/portal/lines/{foreign_line.id}/comment", headers=headers(token), json={"comment": "hi"}).status_code == 403


def test_customer_comment_moves_quote_to_negotiation_and_rep_can_reply(client, as_rep, db):
    quote_id = sent_quote(db)
    token = token_for(db, quote_id)
    line = db.query(QuoteLine).filter_by(quote_id=quote_id, product_id=1).one()
    res = client.post(f"/portal/lines/{line.id}/comment", headers=headers(token), json={"comment": "Can this ship by Friday?"})
    assert res.status_code == 201
    assert client.get("/portal/quote", headers=headers(token)).json()["status"] == "Under Negotiation"
    assert any(n["type"] == "customer_comment" for n in as_rep.get("/notifications").json()["items"])

    reply = as_rep.post(f"/quotes/{quote_id}/lines/{line.id}/comments", json={"comment": "Yes, Friday works."})
    note = as_rep.post(f"/quotes/{quote_id}/lines/{line.id}/comments", json={"comment": "margin is thin here", "is_internal": True})
    assert reply.status_code == 201 and note.status_code == 201
    visible = client.get("/portal/quote", headers=headers(token)).json()["lines"][0]["comments"]
    assert [c["comment"] for c in visible] == ["Can this ship by Friday?", "Yes, Friday works."]
    internal = as_rep.get(f"/quotes/{quote_id}/negotiation").json()["comments"]
    assert len(internal) == 3


def test_customer_login_sees_only_own_quotes(client, as_customer, as_admin, db):
    mine = sent_quote(db)
    tier2_customer = as_admin.post("/customers", json={"name": "Other Co", "tier_id": 1}).json()["id"]
    theirs = make_quote(db, [(1, 1, 0)], status="sent", customer_id=tier2_customer)
    listing = as_customer.get("/portal/quotes")
    assert listing.status_code == 200
    assert [q["quote_id"] for q in listing.json()["items"]] == [mine]
    assert as_customer.get(f"/portal/quotes/{mine}").status_code == 200
    assert as_customer.get(f"/portal/quotes/{theirs}").status_code == 403
    assert as_customer.get(f"/quotes/{mine}").status_code == 403  # internal API stays closed
    confirm = as_customer.post(f"/portal/quotes/{mine}/confirm")
    assert confirm.status_code == 200 and confirm.json()["status"] == "confirmed"


def test_send_quote_mints_link_and_emails_customer(as_rep, client, db):
    from app.models import EmailMessage

    quote_id = make_quote(db, [(1, 1, 5)], status="approved")
    res = as_rep.post(f"/quotes/{quote_id}/send")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["quote"]["status"] == "sent"
    assert body["email_status"] == "sent" and body["email_to"] == "buyer@testcorp.example"
    assert "/portal/" in body["portal_url"]
    email = db.query(EmailMessage).filter(EmailMessage.template == "quote_sent").one()
    assert body["portal_url"] in email.body_text
    token = body["portal_url"].rsplit("/", 1)[1]
    assert client.get("/portal/quote", headers=headers(token)).status_code == 200
    # re-sending revokes the old link
    again = as_rep.post(f"/quotes/{quote_id}/send").json()
    assert client.get("/portal/quote", headers=headers(token)).status_code == 401
    assert client.get("/portal/quote", headers=headers(again["portal_url"].rsplit("/", 1)[1])).status_code == 200
