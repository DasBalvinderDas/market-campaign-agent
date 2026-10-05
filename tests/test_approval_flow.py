import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest

from campaign_provisioner import approval_flow, config
from campaign_provisioner.approval_links import ApprovalLinkError, make_token, verify_token
from campaign_provisioner.tools import budget_tools, inventory_tools, orchestration_tools

SECRET = "test-secret"


class FakeExecutor:
    def __init__(self, fail_po=False):
        self.calls, self.fail_po = [], fail_po

    def execute(self, trigger_id, inputs):
        self.calls.append((trigger_id, inputs))
        if trigger_id == config.PO_TRIGGER:
            if self.fail_po:
                raise RuntimeError("workflow down")
            return {"po_number": f"PO-{inputs['sku']}", "execution_id": "exec-1"}
        return {"status": "NOTIFIED"}


@pytest.fixture
def email_channel(monkeypatch, repo):
    monkeypatch.setattr(config, "APPROVAL_CHANNEL", "email")
    monkeypatch.setattr(config, "APPROVAL_BASE_URL", "https://approve.example.run.app")
    monkeypatch.setattr(config, "APPROVAL_LINK_SECRET", SECRET)
    repo.t["approvers"] = [{"approver_role": "Marketing Director", "email": "md@example.com", "active": True}]
    return repo


def wall_request(repo):
    rid = orchestration_tools.register_campaign_request("NEXT27-MAIN", "1 wall")["request_id"]
    inventory_tools.reserve_inventory(rid, "BOOTH-LEDWALL", 1)  # 0 free -> shortfall 1
    return rid


# ---- tokens
def test_token_roundtrip_tamper_and_expiry():
    t = make_token(SECRET, "APR-1", "A@X.com", "approve", 2_000_000_000)
    c = verify_token(SECRET, t, now=1_900_000_000)
    assert c == {"approval_id": "APR-1", "email": "a@x.com", "action": "approve", "expires_at": 2_000_000_000}
    with pytest.raises(ApprovalLinkError, match="expired"):
        verify_token(SECRET, t, now=2_000_000_001)
    body, sig = t.split(".")
    with pytest.raises(ApprovalLinkError):
        verify_token(SECRET, body + "." + sig[:-2] + "xx")
    with pytest.raises(ApprovalLinkError):
        verify_token("other-secret", t, now=1)
    with pytest.raises(ApprovalLinkError):
        verify_token(SECRET, "garbage")


# ---- requesting approval
def test_plan_comes_from_the_database_not_the_model(repo):
    rid = wall_request(repo)
    plan = approval_flow.build_plan(repo, rid)
    assert plan["total"] == 18000.0 and plan["lines"][0]["vendor_id"] == "V-EXPOVISION"


def test_high_value_request_emails_links_and_does_not_commit(email_channel):
    repo = email_channel
    rid = wall_request(repo)
    ex = FakeExecutor()
    out = approval_flow.request_human_approval(repo, ex, rid, "NEXT27-MAIN", "1 wall",
                                               repo.get_policy(18000))
    assert out["status"] == "pending_approval" and out["emailed"] == ["md@example.com"]
    trig, inputs = ex.calls[0]
    assert trig == config.NOTIFY_TRIGGER and inputs["approver_email"] == "md@example.com"
    assert "APPROVE: https://approve.example.run.app/decide?t=" in inputs["email_body"]
    assert "REJECT:  https://approve.example.run.app/decide?t=" in inputs["email_body"]
    assert repo.get_budget("NEXT27-MAIN")["committed"] == 30000.0  # nothing committed yet
    assert repo.get_approval_for_request(rid)["status"] == "PENDING"


def test_approve_budget_in_email_channel_returns_pending_for_human_tiers(email_channel, monkeypatch):
    repo = email_channel
    rid = wall_request(repo)
    monkeypatch.setattr(budget_tools, "IntegrationExecutor", FakeExecutor)
    out = budget_tools.approve_budget(rid, "NEXT27-MAIN", 1.0, "1 wall")  # the model's amount is ignored
    assert out["status"] == "pending_approval" and out["amount"] == 18000.0
    assert budget_tools.requires_human(18000, "NEXT27-MAIN") is False  # no chat pause in this channel


def test_small_amount_is_still_auto_approved_in_email_channel(email_channel):
    repo = email_channel
    rid = orchestration_tools.register_campaign_request("NEXT27-PARTNER", "bottles")["request_id"]
    inventory_tools.reserve_inventory(rid, "WATER-BOTTLE", 600)
    out = budget_tools.approve_budget(rid, "NEXT27-PARTNER", 3540.0, "bottles")
    assert out["status"] == "approved" and out["approved_by"] == "auto-policy"


def test_no_approver_email_means_no_request(email_channel):
    repo = email_channel
    repo.t["approvers"] = []
    rid = wall_request(repo)
    out = approval_flow.request_human_approval(repo, FakeExecutor(), rid, "NEXT27-MAIN", "x", repo.get_policy(18000))
    assert out["status"] == "NO_APPROVERS" and repo.get_approval_for_request(rid) is None


# ---- the click
def _links(repo, rid, ex):
    approval = repo.get_approval_for_request(rid)
    body = next(i["email_body"] for t, i in ex.calls if t == config.NOTIFY_TRIGGER)
    urls = [ln.split(": ", 1)[1].strip() for ln in body.splitlines() if ln.startswith(("APPROVE:", "REJECT:"))]
    return approval, [parse_qs(urlparse(u).query)["t"][0] for u in urls]


@pytest.fixture
def client(email_channel, monkeypatch):
    from approval_service import main
    ex = FakeExecutor()
    monkeypatch.setattr(main, "_executor", lambda: ex)
    main.app.testing = True
    return main.app.test_client(), email_channel, ex


def request_and_links(repo, ex):
    rid = wall_request(repo)
    approval_flow.request_human_approval(repo, ex, rid, "NEXT27-MAIN", "1 wall", repo.get_policy(18000))
    approval, (approve, reject) = _links(repo, rid, ex)
    return rid, approval, approve, reject


def test_opening_the_link_only_shows_a_confirmation_page(client):
    c, repo, ex = client
    rid, approval, approve, _ = request_and_links(repo, ex)
    r = c.get("/decide", query_string={"t": approve})
    assert r.status_code == 200 and b"Approve this request?" in r.data and b"18,000.00" in r.data
    assert repo.get_approval_for_request(rid)["status"] == "PENDING"   # a scanner opening the link changes nothing


def test_clicking_approve_commits_budget_and_creates_the_purchase_order(client):
    c, repo, ex = client
    rid, approval, approve, _ = request_and_links(repo, ex)
    r = c.post("/decide", data={"t": approve})
    assert r.status_code == 200 and b"PO-BOOTH-LEDWALL" in r.data
    a = repo.get_approval_for_request(rid)
    assert a["status"] == "APPROVED" and a["decided_by"] == "md@example.com"
    assert repo.get_budget("NEXT27-MAIN")["committed"] == 48000.0
    assert repo.list_purchase_orders(rid)[0]["total_amount"] == 18000.0
    actions = [e["action"] for e in repo.t["audit_log"]]
    assert {"approval_requested", "budget_approved", "po_created"} <= set(actions)


def test_a_link_works_once(client):
    c, repo, ex = client
    rid, _, approve, reject = request_and_links(repo, ex)
    assert c.post("/decide", data={"t": approve}).status_code == 200
    again = c.post("/decide", data={"t": approve})
    other = c.post("/decide", data={"t": reject})
    assert again.status_code == 409 and other.status_code == 409 and len(repo.list_purchase_orders(rid)) == 1


def test_clicking_reject_releases_stock_and_orders_nothing(client):
    c, repo, ex = client
    rid = orchestration_tools.register_campaign_request("NEXT27-MAIN", "kiosks")["request_id"]
    inventory_tools.reserve_inventory(rid, "DEMO-KIOSK", 6)   # 2 reserved, 4 short -> $12,800 (human tier)
    approval_flow.request_human_approval(repo, ex, rid, "NEXT27-MAIN", "kiosks", repo.get_policy(12800))
    _, (approve, reject) = _links(repo, rid, ex)
    r = c.post("/decide", data={"t": reject})
    assert r.status_code == 200 and b"Rejected" in r.data
    assert repo.list_purchase_orders(rid) == []
    assert inventory_tools.check_inventory("DEMO-KIOSK", 1)["free_stock"] == 2   # released
    assert repo.get_approval_for_request(rid)["status"] == "REJECTED"


def test_bad_expired_and_foreign_links_are_refused(client):
    c, repo, ex = client
    rid, approval, approve, _ = request_and_links(repo, ex)
    assert c.get("/decide", query_string={"t": "nonsense"}).status_code == 400
    foreign = make_token(SECRET, approval["approval_id"], "stranger@evil.com", "approve", 2_000_000_000)
    assert c.post("/decide", data={"t": foreign}).status_code == 400
    assert repo.get_approval_for_request(rid)["status"] == "PENDING"
    expired = make_token(SECRET, approval["approval_id"], "md@example.com", "approve", 1)
    assert c.get("/decide", query_string={"t": expired}).status_code == 400


def test_expired_approval_row_cannot_be_decided(client):
    c, repo, ex = client
    rid, approval, approve, _ = request_and_links(repo, ex)
    repo.t["approval_requests"][-1]["expires_at"] = datetime.now(timezone.utc) - timedelta(minutes=1)
    assert c.post("/decide", data={"t": approve}).status_code == 410
    assert repo.list_purchase_orders(rid) == []


def test_a_failed_po_is_reported_and_budget_stays_committed(client, monkeypatch):
    from approval_service import main
    c, repo, _ = client
    ex = FakeExecutor()
    rid, approval, approve, _ = request_and_links(repo, ex)
    monkeypatch.setattr(main, "_executor", lambda: FakeExecutor(fail_po=True))
    r = c.post("/decide", data={"t": approve})
    assert r.status_code == 200 and b"need attention" in r.data
    assert "po_failed" in [e["action"] for e in repo.t["audit_log"]]


def test_status_tool(email_channel):
    repo = email_channel
    rid = wall_request(repo)
    approval_flow.request_human_approval(repo, FakeExecutor(), rid, "NEXT27-MAIN", "x", repo.get_policy(18000))
    assert orchestration_tools.get_approval_status(rid)["status"] == "PENDING"
    assert orchestration_tools.get_approval_status("REQ-NONE")["status"] == "none"


# ---------------------------------------------------------------- native Application Integration approval
class IntegrationExecutorFake(FakeExecutor):
    def __init__(self):
        super().__init__()
        self.execution = {"executionDetails": {"state": "SUSPENDED"}}

    def start(self, trigger_id, inputs):
        self.calls.append((trigger_id, inputs))
        return {"executionId": "exec-9", "executionFailed": False}

    def get_execution(self, execution_id):
        assert execution_id == "exec-9"
        return self.execution


@pytest.fixture
def integration_channel(monkeypatch, repo):
    monkeypatch.setattr(config, "APPROVAL_CHANNEL", "integration")
    repo.t["approvers"] = [{"approver_role": "Marketing Director", "email": "md@example.com", "active": True}]
    ex = IntegrationExecutorFake()
    monkeypatch.setattr(budget_tools, "IntegrationExecutor", lambda: ex)
    monkeypatch.setattr(approval_flow, "_default_executor", lambda: ex)
    return repo, ex


def test_integration_channel_starts_the_workflow_and_commits_nothing(integration_channel):
    repo, ex = integration_channel
    rid = wall_request(repo)
    assert budget_tools.requires_human(18000, "NEXT27-MAIN") is False  # no chat pause
    out = budget_tools.approve_budget(rid, "NEXT27-MAIN", 18000, "booth wall")
    assert out["status"] == "pending_approval" and out["channel"] == "application_integration"
    assert "Procurement" in out["announce"] and "md@example.com" in out["announce"]
    trig, inputs = ex.calls[0]
    assert trig == config.APPROVAL_TRIGGER and inputs["amount"] == 18000.0 and "ExpoVision" in inputs["approval_message"]
    assert repo.get_approval_for_request(rid)["status"] == "PENDING"
    assert repo.get_budget("NEXT27-MAIN")["committed"] == 30000.0 and not repo.list_purchase_orders(rid)
    assert approval_flow.approval_status(repo, rid)["status"] == "PENDING"  # still suspended: nothing happens


def test_approved_in_integration_creates_the_po_once(integration_channel):
    repo, ex = integration_channel
    rid = wall_request(repo)
    budget_tools.approve_budget(rid, "NEXT27-MAIN", 18000, "booth wall")
    ex.execution = {"executionDetails": {"state": "SUCCEEDED"}, "responseParameters": {"decision": {"stringValue": "APPROVED"}}}
    out = approval_flow.approval_status(repo, rid)
    assert out["status"] == "APPROVED" and [p["po_number"] for p in out["purchase_orders"]] == ["PO-BOOTH-LEDWALL"]
    assert repo.get_budget("NEXT27-MAIN")["committed"] == 48000.0
    approval_flow.approval_status(repo, rid)  # asking again must not order again
    assert len(repo.list_purchase_orders(rid)) == 1


def test_rejected_in_integration_releases_stock(integration_channel):
    repo, ex = integration_channel
    rid = wall_request(repo)
    budget_tools.approve_budget(rid, "NEXT27-MAIN", 18000, "booth wall")
    ex.execution = {"executionDetails": {"state": "SUCCEEDED"}, "responseParameters": {"decision": "REJECTED"}}
    out = approval_flow.approval_status(repo, rid)
    assert out["status"] == "REJECTED" and not out["purchase_orders"]
    assert repo.get_budget("NEXT27-MAIN")["committed"] == 30000.0


def test_workflow_start_failure_is_reported(integration_channel):
    repo, ex = integration_channel
    ex.start = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("403 no permission"))
    rid = wall_request(repo)
    out = budget_tools.approve_budget(rid, "NEXT27-MAIN", 18000, "booth wall")
    assert out["status"] == "error" and "403" in out["message"]
    assert repo.get_approval_for_request(rid)["status"] == "FAILED"


def test_decision_is_found_in_other_places_of_the_execution(integration_channel):
    repo, ex = integration_channel
    rid = wall_request(repo)
    budget_tools.approve_budget(rid, "NEXT27-MAIN", 18000, "booth wall")
    ex.execution = {"executionDetails": {"state": "SUCCEEDED", "executionSnapshots": [
        {"executionSnapshotMetadata": {}, "checkpointTaskNumber": "1",
         "taskExecutionDetails": [{"x": {"decision": {"stringValue": "APPROVED"}}}]}]}}
    assert approval_flow.approval_status(repo, rid)["status"] == "APPROVED"


def test_suspension_record_is_the_fallback(integration_channel):
    repo, ex = integration_channel
    rid = wall_request(repo)
    budget_tools.approve_budget(rid, "NEXT27-MAIN", 18000, "booth wall")
    ex.execution = {"executionDetails": {"state": "SUCCEEDED"}}
    ex.list_suspensions = lambda _id: [{"state": "LIFTED"}]
    assert approval_flow.approval_status(repo, rid)["status"] == "APPROVED"
