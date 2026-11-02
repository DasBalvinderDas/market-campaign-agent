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
