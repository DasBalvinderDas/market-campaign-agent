"""Approving inside the Gemini Enterprise app (APPROVAL_CHANNEL=gemini or both)."""
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
