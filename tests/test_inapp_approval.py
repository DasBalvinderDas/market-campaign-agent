"""Approving inside the Gemini Enterprise app (APPROVAL_CHANNEL=gemini or both)."""
import os

import pytest
from conftest import FakeExecutor
from launchkit_provisioner import config, decision_flow, execution


@pytest.fixture
def gemini(monkeypatch):
    monkeypatch.setattr(config, "APPROVAL_CHANNEL", "gemini")
    monkeypatch.setattr(config, "APPROVAL_CHECK_USER", True)


def _vp(repo):
    repo.t["approvers"] = [{"approver_role": "VP Product Marketing", "email": "vp@example.com", "active": True},
                           {"approver_role": "Launch Team", "email": "team@example.com", "active": True}]


def test_in_app_mode_sends_no_email_and_no_workflow(repo, aurora, gemini):
    _vp(repo)
    ex = FakeExecutor()
    out = decision_flow.authorize(repo, ex, aurora, "2", "saves money")
    assert out["status"] == "pending_approval" and out["channel"] == "gemini" and not ex.calls
    md = out["display_markdown"]
    assert "My approvals" in md and "email" not in md.lower() and "@" not in md
    assert repo.get_decision_for_request(aurora)["status"] == "PENDING"


def test_only_the_listed_approver_sees_and_decides_the_request(repo, aurora, gemini):
    _vp(repo)
    decision_flow.authorize(repo, FakeExecutor(), aurora, "2", "x")
    mine = decision_flow.my_approvals(repo, "VP@example.com")
    assert mine["status"] == "ok" and aurora in mine["display_markdown"] and "@" not in mine["display_markdown"]
    assert decision_flow.my_approvals(repo, "someone@example.com")["status"] == "none"
    refused = decision_flow.decide_in_app(repo, "someone@example.com", aurora, "approve")
    assert refused["status"] == "error" and repo.get_decision_for_request(aurora)["status"] == "PENDING"
    ok = decision_flow.decide_in_app(repo, "vp@example.com", aurora, "approve", "fine")
    assert ok["status"] == "approved" and "fulfilment_agent" in ok["next_step"]
    assert repo.get_decision_for_request(aurora)["status"] == "APPROVED"
    again = decision_flow.decide_in_app(repo, "vp@example.com", aurora, "reject")
    assert again["status"] == "error"                                        # decided once only


def test_reject_releases_the_stock(repo, aurora, gemini):
    _vp(repo)
    decision_flow.authorize(repo, FakeExecutor(), aurora, "2", "x")
    out = decision_flow.decide_in_app(repo, "vp@example.com", aurora, "reject")
    assert out["status"] == "rejected" and repo.get_decision_for_request(aurora)["status"] == "REJECTED"


def test_check_can_be_switched_off_for_a_demo(repo, aurora, gemini, monkeypatch):
    _vp(repo)
    monkeypatch.setattr(config, "APPROVAL_CHECK_USER", False)
    decision_flow.authorize(repo, FakeExecutor(), aurora, "2", "x")
    assert decision_flow.decide_in_app(repo, "anyone", aurora, "approve")["status"] == "approved"


def test_the_orders_send_no_launch_team_email_in_app_mode(repo, aurora, gemini):
    _vp(repo)
    ex = FakeExecutor()
    decision_flow.authorize(repo, ex, aurora, "2", "x")
    decision_flow.decide_in_app(repo, "vp@example.com", aurora, "approve")
    out = execution.execute_plan(repo, ex, aurora)
    assert out["status"] == "executed" and out["update_sent"] == 0
    assert not [i for t, i in ex.calls if t.endswith("send_launch_update")]


def test_email_mode_is_unchanged_and_refuses_in_app_decisions(repo, aurora, monkeypatch):
    monkeypatch.setattr(config, "APPROVAL_CHANNEL", "email")
    _vp(repo)
    assert decision_flow.my_approvals(repo, "vp@example.com")["status"] == "off"
    assert decision_flow.decide_in_app(repo, "vp@example.com", aurora, "approve")["status"] == "error"


@pytest.fixture
def workflow(monkeypatch):
    monkeypatch.setattr(config, "APPROVAL_CHANNEL", "workflow")
    monkeypatch.setattr(config, "APPROVAL_CHECK_USER", True)
    monkeypatch.setattr(config, "APPROVAL_NOTIFY_EMAIL", False)


def test_workflow_mode_waits_in_the_inbox_with_no_email(repo, aurora, workflow):
    _vp(repo)
    ex = FakeExecutor()
    out = decision_flow.authorize(repo, ex, aurora, "2", "x")
    md = out["display_markdown"]
    assert out["status"] == "pending_approval" and out["channel"] == "workflow" and not ex.calls
    assert "Inbox" in md and "Needs input" in md and "@" not in md


def test_workflow_answer_names_the_approver_who_clicked(repo, aurora, workflow):
    _vp(repo)
    decision_flow.authorize(repo, FakeExecutor(), aurora, "2", "x")
    # the workflow's last step runs as someone else: the named approver is what counts
    bad = decision_flow.decide_in_app(repo, "runner@example.com", aurora, "approve", approver="nobody@example.com")
    assert bad["status"] == "error" and repo.get_decision_for_request(aurora)["status"] == "PENDING"
    ok = decision_flow.decide_in_app(repo, "runner@example.com", aurora, "approve", approver="VP@example.com")
    assert ok["status"] == "approved" and repo.get_decision_for_request(aurora)["decided_by"] == "VP Product Marketing (Inbox)"


def test_notice_email_is_optional_and_has_no_buttons(repo, aurora, workflow, monkeypatch):
    _vp(repo)
    monkeypatch.setattr(config, "APPROVAL_NOTIFY_EMAIL", True)
    ex = FakeExecutor()
    out = decision_flow.authorize(repo, ex, aurora, "2", "x")
    sent = [i for t, i in ex.calls if t.endswith("send_launch_update")]
    assert out["approvers_notified"] == 1 and len(sent) == 1
    body = sent[0]["email_body"]
    assert "Inbox" in body and "Needs input" in body and "Approve</a>" not in body and "href" not in body
    assert sent[0]["recipient_email"] == "vp@example.com" and "Approval waiting" in sent[0]["email_subject"]


def test_the_shipped_defaults_are_the_inbox_workflow_with_notice_emails():
    import subprocess
    import sys
    env = {k: v for k, v in os.environ.items() if not k.startswith("APPROVAL_")}
    out = subprocess.run([sys.executable, "-c", "from launchkit_provisioner import config as c; "
                          "print(c.APPROVAL_CHANNEL, c.APPROVAL_NOTIFY_EMAIL, c.APPROVAL_CHECK_USER)"],
                         capture_output=True, text=True, env=env, cwd=os.path.dirname(os.path.dirname(__file__)))
    assert out.stdout.split() == ["workflow", "True", "True"], out.stderr


def test_the_workflow_probe_reads_a_discovery_document():
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts"))
    import probe_workflow_api as p

    doc = {"resources": {"projects": {"resources": {"locations": {"resources": {"agents": {"methods": {"get": {}, "list": {}}}}}}}},
           "schemas": {"GoogleCloudDiscoveryengineV1alphaAgent": {"properties": {"displayName": {}, "workflowAgentDefinition": {}}},
                       "WorkflowSpec": {"properties": {"steps": {}}}}}
    ok, lines = p.verdict(doc)
    assert not ok and "no create method" in lines[-1] and "WorkflowSpec: steps" in " ".join(lines)
    doc["resources"]["projects"]["resources"]["locations"]["resources"]["agents"]["methods"]["create"] = {}
    assert p.verdict(doc)[0]
    assert p.verdict({})[0] is False
    assert p.clean_for_create({"name": "x", "displayName": "A", "state": "PUBLISHED", "definition": {"a": 1}}) == {"displayName": "A", "definition": {"a": 1}}
    assert p.host("global") == "discoveryengine.googleapis.com" and p.host("us").startswith("us-")
    assert p.agents_path("p", "global", "e").endswith("/engines/e/assistants/default_assistant/agents")


def test_the_probe_prints_the_fields_of_a_schema():
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts"))
    import probe_workflow_api as p

    doc = {"schemas": {"V1alphaAgent": {"properties": {"displayName": {"type": "string"}, "workflowSpec": {"$ref": "WorkflowSpec"}}}}}
    lines = p.schema_lines(doc, "agent")
    assert lines[0] == "V1alphaAgent" and any("workflowSpec: WorkflowSpec" in x for x in lines)
    assert "no schema name contains" in p.schema_lines(doc, "zzz")[0]


def test_notices_go_to_one_address_and_approval_to_the_sign_in(repo, aurora, monkeypatch):
    """Notice email to the hcltech address; only the labgtm sign-in may approve."""
    monkeypatch.setattr(config, "APPROVAL_CHANNEL", "workflow")
    monkeypatch.setattr(config, "APPROVAL_NOTIFY_EMAIL", True)
    repo.t["approvers"] = [
        {"approver_role": "VP Product Marketing", "email": "me@hcltech.com", "signin_email": "me@labgtm.com", "active": True},
        {"approver_role": "Launch Team", "email": "me@hcltech.com", "signin_email": None, "active": True}]
    ex = FakeExecutor()
    out = decision_flow.authorize(repo, ex, aurora, "2", "x")
    sent = [i for t, i in ex.calls if t.endswith("send_launch_update")]
    assert out["status"] == "pending_approval" and [i["recipient_email"] for i in sent] == ["me@hcltech.com"]
    assert "href" not in sent[0]["email_body"] and "Approve</a>" not in sent[0]["email_body"]
    assert decision_flow.my_approvals(repo, "me@hcltech.com")["status"] == "none"          # the notice address cannot approve
    assert decision_flow.decide_in_app(repo, "me@hcltech.com", aurora, "approve")["status"] == "error"
    assert decision_flow.my_approvals(repo, "ME@labgtm.com")["status"] == "ok"
    assert decision_flow.decide_in_app(repo, "me@labgtm.com", aurora, "approve")["status"] == "approved"
    out = execution.execute_plan(repo, ex, aurora)                                          # the orders-placed email: hcltech only
    placed = [i for t, i in ex.calls if t.endswith("send_launch_update") and "Orders placed" in i["email_subject"]]
    assert out["status"] == "executed" and [i["recipient_email"] for i in placed] == ["me@hcltech.com"]


def test_set_approvers_pairs_a_notice_address_with_a_sign_in():
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts"))
    import set_approvers as sa
    rows = sa.build_rows(["Me@hcltech.com=me@labgtm.com", "me@hcltech.com=me@labgtm.com"])
    assert len(rows) == 3 and {r["email"] for r in rows} == {"me@hcltech.com"}
    by = {r["approver_role"]: r["signin_email"] for r in rows}
    assert by == {"VP Product Marketing": "me@labgtm.com", "CMO": "me@labgtm.com", "Launch Team": None}
    assert sa.build_rows(["a@x.com"])[0]["signin_email"] is None
    with pytest.raises(ValueError):
        sa.build_rows(["a@x.com=nope"])


def test_the_probe_finds_methods_by_word():
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts"))
    import probe_workflow_api as p
    doc = {"resources": {"assistants": {"methods": {"streamAssist": {"id": "x.streamAssist", "httpMethod": "POST", "path": "v1alpha/{name}:streamAssist",
                                                                   "description": "Runs an agent"}}, "resources": {}}}}
    assert "streamAssist" in p.find_methods(doc, "stream")[0] and "no method" in p.find_methods(doc, "zzz")[0]


def test_each_request_is_offered_once_to_the_scheduled_workflow(repo, aurora, monkeypatch):
    monkeypatch.setattr(config, "APPROVAL_CHANNEL", "workflow")
    monkeypatch.setattr(config, "APPROVAL_CHECK_USER", True)
    repo.t["approvers"] = [{"approver_role": "VP Product Marketing", "email": "me@hcltech.com", "signin_email": "me@labgtm.com", "active": True}]
    assert decision_flow.next_approval(repo, "me@labgtm.com")["display_markdown"] == "NONE"          # nothing waiting yet
    decision_flow.authorize(repo, FakeExecutor(), aurora, "2", "x")
    assert decision_flow.next_approval(repo, "other@labgtm.com")["display_markdown"] == "NONE"      # not for them
    first = decision_flow.next_approval(repo, "me@labgtm.com")
    assert first["status"] == "ok" and first["display_markdown"].startswith(aurora + " · ") and "$" in first["display_markdown"]
    assert decision_flow.next_approval(repo, "me@labgtm.com")["display_markdown"] == "NONE"         # offered once: no second Inbox item
    assert decision_flow.my_approvals(repo, "me@labgtm.com")["status"] == "ok"                      # still listed in My approvals
    assert decision_flow.decide_in_app(repo, "me@labgtm.com", aurora, "approve")["status"] == "approved"
    shown = decision_flow.status(repo, aurora, executor=FakeExecutor())["display_markdown"]
    assert "offered at" not in shown


class _Blob:
    def __init__(self, store, name):
        self.store, self.name = store, name

    def upload_from_string(self, data, content_type=None, if_generation_match=None):
        if if_generation_match == 0 and self.name in self.store:
            raise RuntimeError("412 already exists")
        self.store[self.name] = data


class _Bucket:
    def __init__(self, store):
        self.store = store

    def blob(self, name):
        return _Blob(self.store, name)


class _Storage:
    def __init__(self):
        self.store = {}

    def bucket(self, name):
        assert name == "b1"
        return _Bucket(self.store)


def test_a_waiting_request_drops_one_file_without_addresses(repo, aurora, monkeypatch):
    import json
    from launchkit_provisioner import trigger_drop
    monkeypatch.setattr(config, "APPROVAL_CHANNEL", "workflow")
    monkeypatch.setattr(config, "APPROVAL_TRIGGER_BUCKET", "b1")
    monkeypatch.setattr(config, "APPROVAL_TRIGGER_PREFIX", "approvals/")
    repo.t["approvers"] = [{"approver_role": "VP Product Marketing", "email": "me@hcltech.com", "signin_email": "me@labgtm.com", "active": True}]
    fake = _Storage()
    monkeypatch.setattr(trigger_drop, "_client", lambda: fake)
    out = decision_flow.authorize(repo, FakeExecutor(), aurora, "2", "x")
    assert out["trigger_file"] == f"approvals/{aurora}.json" and list(fake.store) == [f"approvals/{aurora}.json"]
    data = json.loads(fake.store[out["trigger_file"]])
    assert data["request_id"] == aurora and data["event"] == "approval_waiting" and data["amount_usd"] > 5000
    assert "@" not in fake.store[out["trigger_file"]]
    assert trigger_drop.drop(data, client=fake) == ""                        # the same request never writes a second file
    assert any(a["action"] == "approval_trigger_dropped" for a in repo.list_audit())


def test_the_drop_is_off_by_default_and_never_breaks_the_sign_off(repo, aurora, monkeypatch):
    from launchkit_provisioner import trigger_drop
    monkeypatch.setattr(config, "APPROVAL_CHANNEL", "workflow")
    repo.t["approvers"] = [{"approver_role": "VP Product Marketing", "email": "me@hcltech.com", "active": True}]
    monkeypatch.setattr(config, "APPROVAL_TRIGGER_BUCKET", "")
    assert trigger_drop.drop({"request_id": "REQ-1"}, client=_Storage()) == ""                  # off: nothing is written
    monkeypatch.setattr(config, "APPROVAL_TRIGGER_BUCKET", "b1")
    monkeypatch.setattr(trigger_drop, "_client", lambda: (_ for _ in ()).throw(RuntimeError("no storage")))
    out = decision_flow.authorize(repo, FakeExecutor(), aurora, "2", "x")
    assert out["status"] == "pending_approval" and out["trigger_file"] == ""


def test_the_bucket_script_plans_before_it_acts():
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts"))
    import setup_trigger_bucket as sb
    steps = sb.plan("p", "p-launchkit-approvals", "US", "svc@p.iam.gserviceaccount.com", 30)
    assert any("objectCreator" in s and "svc@p" in s for s in steps) and any("30 days" in s for s in steps)
    assert "AGENT_SERVICE_ACCOUNT is empty" in sb.plan("p", "b", "US", "", 30)[-1]


def test_offered_requests_can_be_offered_again_for_testing(repo, aurora, monkeypatch):
    monkeypatch.setattr(config, "APPROVAL_CHANNEL", "workflow")
    repo.t["approvers"] = [{"approver_role": "VP Product Marketing", "email": "me@hcltech.com", "signin_email": "me@labgtm.com", "active": True}]
    decision_flow.authorize(repo, FakeExecutor(), aurora, "2", "x")
    assert decision_flow.next_approval(repo, "me@labgtm.com")["status"] == "ok"
    assert decision_flow.next_approval(repo, "me@labgtm.com")["display_markdown"] == "NONE"
    assert decision_flow.reoffer(repo, "other@labgtm.com")["count"] == 0                      # not theirs
    again = decision_flow.reoffer(repo, "me@labgtm.com")
    assert again["count"] == 1 and aurora in again["display_markdown"]
    assert decision_flow.next_approval(repo, "me@labgtm.com")["display_markdown"].startswith(aurora)


def test_the_clean_script_empties_working_data_and_keeps_reference_data():
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts"))
    import clean_demo as cd
    names = cd.tables_to_empty()
    assert "launches" in names and "decisions" in names and "purchase_orders" in names and "audit_log" in names
    for kept in ("approvers", "guests", "vendors", "assets", "depot_stock", "vendor_offers", "planning_rules"):
        assert kept not in names
    assert "launches" not in cd.tables_to_empty(keep_campaigns=True)


def test_each_approver_is_offered_a_request_once(repo, aurora, monkeypatch):
    monkeypatch.setattr(config, "APPROVAL_CHANNEL", "workflow")
    repo.t["approvers"] = [
        {"approver_role": "VP Product Marketing", "email": "a@hcltech.com", "signin_email": "a@labgtm.com", "active": True},
        {"approver_role": "VP Product Marketing", "email": "b@labgtm.com", "signin_email": "b@labgtm.com", "active": True}]
    decision_flow.authorize(repo, FakeExecutor(), aurora, "2", "x")
    assert decision_flow.next_approval(repo, "a@labgtm.com")["display_markdown"].startswith(aurora)
    assert decision_flow.next_approval(repo, "a@labgtm.com")["display_markdown"] == "NONE"        # once for her
    assert decision_flow.next_approval(repo, "b@labgtm.com")["display_markdown"].startswith(aurora)  # and once for the other approver
    assert decision_flow.next_approval(repo, "b@labgtm.com")["display_markdown"] == "NONE"
    assert decision_flow.reoffer(repo, "b@labgtm.com")["count"] == 1                           # only b's offer is reset
    assert decision_flow.next_approval(repo, "a@labgtm.com")["display_markdown"] == "NONE"
    assert decision_flow.next_approval(repo, "b@labgtm.com")["display_markdown"].startswith(aurora)
    assert "offered at" not in decision_flow.status(repo, aurora, executor=FakeExecutor())["display_markdown"]
