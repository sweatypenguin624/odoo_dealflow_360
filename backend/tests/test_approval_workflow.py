"""Approval workflow through the authenticated API.

Ported from the original suite: the same scenarios (auto-approve, manager
only, manager→finance, rejection, return for revision, not-pending
guard, queue + history) plus the production guards that were added:
stale versions, double approval, self-approval, RBAC per step.
"""

from app.models import AuditLog, QuoteStatus
from tests.conftest import TestingSessionLocal, make_quote


def create_test_quote(db, discount_laptop=0, discount_setup=0, owner_key="rep"):
    return make_quote(db, [(1, 1, discount_laptop), (2, 1, discount_setup)], owner_key=owner_key)


def test_submit_no_violations_auto_approves(as_rep, db):
    quote_id = create_test_quote(db, discount_laptop=5, discount_setup=5)  # 5 <= 10, 5 <= 15
    response = as_rep.post(f"/quotes/{quote_id}/submit")
    assert response.status_code == 200, response.text
    data = response.json()["quote"]
    assert data["status"] == "approved"
    assert data["current_approval_step"] is None
    assert data["approval_valid"] is True
    assert response.json()["risk_result"]["required_approval_level"] == "none"
    logs = db.query(AuditLog).filter_by(quote_id=quote_id, action="auto_approved").all()
    assert len(logs) == 1


def test_submit_manager_only(as_rep, as_manager, db):
    # laptop discount 18, limit 10 -> 8 points over. Severity = 8 -> manager (5 <= 8 < 15)
    quote_id = create_test_quote(db, discount_laptop=18, discount_setup=0)
    response = as_rep.post(f"/quotes/{quote_id}/submit")
    assert response.status_code == 200
    data = response.json()["quote"]
    assert data["status"] == "pending_approval"
    assert data["current_approval_step"] == "manager"
    assert data["required_approval_level"] == "manager"
    assert any("8" in r for r in response.json()["risk_result"]["reasons"])

    res_approve = as_manager.post(f"/quotes/{quote_id}/approval-action", json={"action": "approved", "note": "looks fine"})
    assert res_approve.status_code == 200, res_approve.text
    approve_data = res_approve.json()["quote"]
    assert approve_data["status"] == "approved"
    assert approve_data["current_approval_step"] is None
    history = res_approve.json()["history"]
    assert history[-1]["actor"] == "Mona Manager" and history[-1]["reason"] == "looks fine"


def test_submit_manager_then_finance(as_rep, as_manager, as_finance, db):
    # laptop discount 30, limit 10 -> 20 points over -> manager_then_finance
    quote_id = create_test_quote(db, discount_laptop=30, discount_setup=0)
    response = as_rep.post(f"/quotes/{quote_id}/submit")
    data = response.json()["quote"]
    assert data["status"] == "pending_approval"
    assert data["current_approval_step"] == "manager"

    # finance cannot act on the manager step
    assert as_finance.post(f"/quotes/{quote_id}/approval-action", json={"action": "approved"}).status_code == 403

    mgr = as_manager.post(f"/quotes/{quote_id}/approval-action", json={"action": "approved"}).json()["quote"]
    assert mgr["status"] == "pending_approval"
    assert mgr["current_approval_step"] == "finance"

    # manager cannot act on the finance step, and cannot approve twice
    assert as_manager.post(f"/quotes/{quote_id}/approval-action", json={"action": "approved"}).status_code == 403

    fin = as_finance.post(f"/quotes/{quote_id}/approval-action", json={"action": "approved"}).json()["quote"]
    assert fin["status"] == "approved"
    assert fin["current_approval_step"] is None


def test_rejection_stops_chain(as_rep, as_manager, db):
    quote_id = create_test_quote(db, discount_laptop=30, discount_setup=0)
    as_rep.post(f"/quotes/{quote_id}/submit")
    res = as_manager.post(f"/quotes/{quote_id}/approval-action", json={"action": "rejected", "note": "too deep"})
    assert res.status_code == 200
    assert res.json()["quote"]["status"] == "rejected"
    assert res.json()["quote"]["current_approval_step"] is None


def test_returned_for_revision_reopens_quote_as_new_version(as_rep, as_manager, db):
    quote_id = create_test_quote(db, discount_laptop=18, discount_setup=0)
    as_rep.post(f"/quotes/{quote_id}/submit")
    res = as_manager.post(f"/quotes/{quote_id}/approval-action", json={"action": "returned_for_revision", "note": "trim the laptop discount"})
    data = res.json()["quote"]
    assert data["status"] == "revision_required"
    assert data["current_approval_step"] is None
    assert data["required_approval_level"] is None
    assert data["version"] == 2
    assert data["can_edit"] is True

    # rep fixes the discount and resubmits -> auto-approved this time
    line_id = data["lines"][0]["id"]
    assert as_rep.patch(f"/quotes/{quote_id}/lines/{line_id}", json={"discount_pct": 10}).status_code == 200
    again = as_rep.post(f"/quotes/{quote_id}/submit")
    assert again.json()["quote"]["status"] == "approved"
    assert again.json()["quote"]["approved_version"] == 2


def test_approval_action_when_not_pending_fails(as_manager, db):
    quote_id = create_test_quote(db, discount_laptop=18, discount_setup=0)
    res = as_manager.post(f"/quotes/{quote_id}/approval-action", json={"action": "approved"})
    assert res.status_code == 409
    assert "not awaiting approval" in res.json()["detail"]


def test_pending_approval_queue_and_history(as_rep, as_manager, as_finance, db):
    quote_id1 = create_test_quote(db, discount_laptop=18, discount_setup=0)  # manager
    quote_id2 = create_test_quote(db, discount_laptop=30, discount_setup=0)  # manager_then_finance
    as_rep.post(f"/quotes/{quote_id1}/submit")
    as_rep.post(f"/quotes/{quote_id2}/submit")

    queue = as_manager.get("/approvals")
    assert queue.status_code == 200
    assert {i["quote_id"] for i in queue.json()["items"]} == {quote_id1, quote_id2}
    assert queue.json()["items"][0]["current_step"] == "manager"

    # finance sees nothing until a manager passes something along
    assert as_finance.get("/approvals").json()["total"] == 0
    as_manager.post(f"/quotes/{quote_id2}/approval-action", json={"action": "approved"})
    finance_queue = as_finance.get("/approvals").json()
    assert [i["quote_id"] for i in finance_queue["items"]] == [quote_id2]

    legacy = as_manager.get("/quotes/pending-approval", params={"step": "manager"})
    assert [q["id"] for q in legacy.json()] == [quote_id1]

    history = as_rep.get(f"/quotes/{quote_id2}/approval-history").json()
    assert len(history["approval_actions"]) == 1
    assert history["approval_actions"][0]["actor_user_id"] == as_manager.user_id
    assert any(l["action"] == "submitted" for l in history["audit_logs"])
    assert history["requests"][0]["status"] == "pending" and history["requests"][0]["current_step"] == "finance"


# ---- production guards ----


def test_rep_cannot_approve_and_owner_cannot_self_approve(as_rep, as_manager, as_admin, db):
    quote_id = create_test_quote(db, discount_laptop=18, owner_key="manager")
    submit = as_manager.post(f"/quotes/{quote_id}/submit")
    assert submit.status_code == 200
    assert as_rep.post(f"/quotes/{quote_id}/approval-action", json={"action": "approved"}).status_code == 403
    self_approve = as_manager.post(f"/quotes/{quote_id}/approval-action", json={"action": "approved"})
    assert self_approve.status_code == 403
    assert self_approve.json()["code"] == "self_approval"
    assert as_admin.post(f"/quotes/{quote_id}/approval-action", json={"action": "approved"}).status_code == 200


def test_editing_after_approval_requires_revise_and_invalidates_approval(as_rep, as_manager, db):
    quote_id = create_test_quote(db, discount_laptop=18, discount_setup=0)
    as_rep.post(f"/quotes/{quote_id}/submit")
    as_manager.post(f"/quotes/{quote_id}/approval-action", json={"action": "approved"})
    detail = as_rep.get(f"/quotes/{quote_id}").json()
    assert detail["status"] == "approved" and detail["approval_valid"] is True
    line_id = detail["lines"][0]["id"]

    # Direct edit after approval is refused
    blocked = as_rep.patch(f"/quotes/{quote_id}/lines/{line_id}", json={"discount_pct": 25})
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "not_editable"

    # Revise -> new version, approval no longer valid, must re-submit
    revised = as_rep.post(f"/quotes/{quote_id}/revise", json={"reason": "customer wants more"})
    assert revised.status_code == 200
    body = revised.json()
    assert body["status"] == "draft" and body["version"] == 2 and body["approval_valid"] is False
    assert as_rep.patch(f"/quotes/{quote_id}/lines/{line_id}", json={"discount_pct": 25}).status_code == 200
    assert as_rep.post(f"/quotes/{quote_id}/send").status_code == 409  # cannot send an unapproved version
    resubmitted = as_rep.post(f"/quotes/{quote_id}/submit").json()["quote"]
    assert resubmitted["status"] == "pending_approval"
    assert resubmitted["required_approval_level"] == "manager_then_finance"  # 25 vs 10 -> 15 points


def test_stale_approval_request_cannot_be_actioned(as_rep, as_manager, db):
    from app.models import ApprovalRequest, Quote

    quote_id = create_test_quote(db, discount_laptop=18)
    as_rep.post(f"/quotes/{quote_id}/submit")
    # Simulate a version bump that left an old pending request behind.
    quote = db.get(Quote, quote_id)
    quote.version += 1
    db.commit()
    res = as_manager.post(f"/quotes/{quote_id}/approval-action", json={"action": "approved"})
    assert res.status_code == 409
    assert res.json()["code"] == "stale_approval"


def test_approval_thresholds_come_from_configuration(as_admin, as_rep, db):
    # Tighten policy: 3 points -> manager; laptop at 12% is 2 points over -> still auto
    as_admin.post("/approval-rules", json={"name": "Strict manager", "approval_level": "manager", "min_points_over": 2})
    quote_id = create_test_quote(db, discount_laptop=12)
    res = as_rep.post(f"/quotes/{quote_id}/submit")
    assert res.json()["quote"]["status"] == "pending_approval"


def test_notifications_are_created_for_approvers_and_owner(as_rep, as_manager, db):
    from app.models import EmailMessage, Notification

    quote_id = create_test_quote(db, discount_laptop=18)
    as_rep.post(f"/quotes/{quote_id}/submit")
    manager_inbox = as_manager.get("/notifications", params={"unread_only": True}).json()
    assert manager_inbox["total"] == 1
    assert manager_inbox["items"][0]["type"] == "approval_required"
    assert manager_inbox["items"][0]["entity_id"] == quote_id
    assert db.query(EmailMessage).filter(EmailMessage.template == "approval_request").count() >= 1

    as_manager.post(f"/quotes/{quote_id}/approval-action", json={"action": "approved"})
    rep_inbox = as_rep.get("/notifications").json()
    assert rep_inbox["items"][0]["type"] == "approval_completed"
    assert as_rep.get("/notifications/unread-count").json()["unread"] == 1
    as_rep.post("/notifications/mark-read", json={})
    assert as_rep.get("/notifications/unread-count").json()["unread"] == 0
