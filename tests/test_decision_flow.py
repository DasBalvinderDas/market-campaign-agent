from datetime import datetime, timedelta, timezone

import pytest

from launchkit_provisioner import config, decision_flow, planner

from conftest import FakeExecutor, BRIEF


def option(repo, rid, code):
    return next(s for s in repo.get_scenarios(rid) if s["option_code"] == code)


def test_options_resolve_from_how_people_say_them(repo, aurora):
    sc = repo.get_scenarios(aurora)
    r = lambda t: decision_flow.resolve_option(sc, t)["option_code"]  # noqa: E731
    assert r("Option 2") == "REBALANCE" and r("2") == "REBALANCE" and r("rebalance") == "REBALANCE"
    assert r("recommended") == "REBALANCE" and r("eco") == "ECO" and r("OPTION_1_FULL_NEW") == "FULL_NEW"
    assert r("full new") == "FULL_NEW" and r("sustainable") == "ECO"
    assert decision_flow.resolve_option(sc, "option 9") is None


def test_above_the_limit_a_human_must_sign_off_and_nothing_is_ordered(repo, aurora):
    repo.t["approvers"] = [{"approver_role": "VP Product Marketing", "email": "vp@example.com", "active": True}]
    ex = FakeExecutor()
    out = decision_flow.authorize(repo, ex, aurora, "option 2", "saves money")
    assert out["status"] == "pending_approval" and out["tier"] == "VP_SIGNOFF"
    assert "HUMAN APPROVAL REQUIRED" in out["announce"] and "vp@example.com" in out["announce"]
    trig, inputs = ex.calls[0]
    reb = option(repo, aurora, "REBALANCE")
    assert trig == config.APPROVAL_TRIGGER and inputs["amount"] == reb["total_cost"] and inputs["launch_id"] == "LAUNCH-SPRING"
    assert "Use our stock first, buy the rest" in inputs["approval_message"] and "If you approve we place" in inputs["approval_message"]
    assert repo.get_decision_for_request(aurora)["status"] == "PENDING"
    assert not repo.list_pos(aurora) and not repo.list_transfers(aurora)
    holds = [h for h in repo.t["depot_holds"] if h["status"] == "ACTIVE"]
    assert holds and sum(h["quantity"] for h in holds if h["sku"] == "GIFT-BOX-BLACK") == 60   # surplus is held while waiting


def test_choosing_eco_pushes_the_sign_off_to_the_cmo(repo, aurora):
    repo.t["approvers"] = [{"approver_role": "CMO", "email": "cmo@example.com", "active": True}]
    out = decision_flow.authorize(repo, FakeExecutor(), aurora, "eco", "")
    assert out["tier"] == "CMO_SIGNOFF" and out["approver_role"] == "CMO" and out["approver_emails"] == ["cmo@example.com"]


def test_small_amounts_run_on_autopilot(repo):
    rid = repo.create_request("LAUNCH-SPRING", "20 folders")
    repo.replace_requirement_lines(rid, planner.expand_bundles(
        repo, "LAUNCH-SPRING", [{"bundle_type": "SALES_PACK", "quantity": 20, "region": "EMEA"}]))
    sc, lines = planner.plan_scenarios(repo, rid)
    repo.replace_scenarios(rid, sc, lines)
    ex = FakeExecutor()
    out = decision_flow.authorize(repo, ex, rid, "recommended", "small")
    assert out["status"] == "approved" and out["approved_by"] == "autopilot" and "fulfilment_agent" in out["next_step"]
    assert not ex.calls                                  # no approval workflow was started
    assert repo.get_decision_for_request(rid)["status"] == "APPROVED"


def test_the_decision_is_idempotent_and_cannot_be_switched(repo, aurora):
    ex = FakeExecutor()
    decision_flow.authorize(repo, ex, aurora, "2", "")
    again = decision_flow.authorize(repo, ex, aurora, "2", "")
    other = decision_flow.authorize(repo, ex, aurora, "3", "")
    assert again["already"] and "already exists" in again["message"]
    assert other["already"] and "cannot be changed" in other["message"]
    assert len(repo.t["decisions"]) == 1 and len([c for c in ex.calls]) == 1


def test_an_option_that_misses_the_deadline_cannot_be_authorised(repo, aurora):
    for v in ("V-RAPIDDISPLAY", "V-DISPLAYCO"):
        repo.add_disruption(v, 10, "x")
    sc, lines = planner.plan_scenarios(repo, aurora)
    repo.replace_scenarios(aurora, sc, lines)
    out = decision_flow.authorize(repo, FakeExecutor(), aurora, "2", "")
    assert out["status"] == "error" and "misses the in-hand date" in out["message"] and not repo.t["decisions"]


def test_stock_taken_by_someone_else_is_detected(repo, aurora):
    repo.create_holds([{"request_id": "REQ-OTHER", "scenario_id": "S", "line_id": "L", "depot_id": "DEPOT-LON-01",
                        "sku": "GIFT-BOX-BLACK", "quantity": 50}])
    out = decision_flow.authorize(repo, FakeExecutor(), aurora, "2", "")
    assert out["status"] == "error" and "surplus stock changed" in out["message"] and "GIFT-BOX-BLACK" in out["message"]


def test_unknown_request_option_and_missing_scenarios(repo, aurora):
    ex = FakeExecutor()
    assert decision_flow.authorize(repo, ex, "REQ-NOPE", "2")["status"] == "error"
    bad = decision_flow.authorize(repo, ex, aurora, "option 7")
    assert bad["status"] == "error" and "Valid" in bad["message"]
    rid = repo.create_request("LAUNCH-SPRING", "empty")
    assert "sourcing" in decision_flow.authorize(repo, ex, rid, "1")["message"]


def test_a_workflow_that_cannot_start_leaves_nothing_behind(repo, aurora):
    class Down(FakeExecutor):
        def start(self, *a, **k):
            raise RuntimeError("403 no permission")
    out = decision_flow.authorize(repo, Down(), aurora, "2", "")
    assert out["status"] == "error" and "403" in out["message"]
    assert repo.get_decision_for_request(aurora)["status"] == "FAILED"
    assert not [h for h in repo.t["depot_holds"] if h["status"] == "ACTIVE"]      # the surplus is released again
    again = decision_flow.authorize(repo, FakeExecutor(), aurora, "2", "")       # and a new attempt is possible
    assert again["status"] == "pending_approval"


def start_pending(repo, rid, option="2"):
    ex = FakeExecutor()
    decision_flow.authorize(repo, ex, rid, option, "")
    return ex


def test_pending_stays_pending_until_the_approver_decides(repo, aurora):
    ex = start_pending(repo, aurora)
    out = decision_flow.status(repo, aurora, ex)
    assert out["status"] == "PENDING" and "next_step" not in out and out["lines_executed"] == 0


def test_approved_in_integration_is_recorded_once_and_unlocks_fulfilment(repo, aurora):
    ex = start_pending(repo, aurora)
    ex.execution = {"eventExecutionDetails": {"eventExecutionState": "SUCCEEDED"}}
    ex.suspensions = [{"state": "LIFTED", "taskId": "10"}]                 # the shape seen on a real project
    out = decision_flow.status(repo, aurora, ex)
    assert out["status"] == "APPROVED" and "fulfilment_agent" in out["next_step"]
    assert repo.get_decision_for_request(aurora)["decided_by"] == "Application Integration approval"
    assert [a["action"] for a in repo.list_audit(aurora)].count("launch_approved") == 1
    decision_flow.status(repo, aurora, ex)
    assert [a["action"] for a in repo.list_audit(aurora)].count("launch_approved") == 1


def test_the_decision_is_also_found_in_the_execution_output(repo, aurora):
    ex = start_pending(repo, aurora)
    ex.execution = {"executionDetails": {"state": "SUCCEEDED"}, "responseParameters": {"decision": {"stringValue": "APPROVED"}}}
    assert decision_flow.status(repo, aurora, ex)["status"] == "APPROVED"


def test_rejected_releases_the_held_surplus_and_allows_a_new_plan(repo, aurora):
    ex = start_pending(repo, aurora)
    ex.suspensions = [{"state": "REJECTED"}]
    out = decision_flow.status(repo, aurora, ex)
    assert out["status"] == "REJECTED" and "released" in out["next_step"]
    assert not [h for h in repo.t["depot_holds"] if h["status"] == "ACTIVE"]
    new = decision_flow.authorize(repo, FakeExecutor(), aurora, "3", "")        # another option is allowed after a rejection
    assert new["status"] == "pending_approval"


def test_a_failed_workflow_is_reported_and_releases_the_stock(repo, aurora):
    ex = start_pending(repo, aurora)
    ex.execution = {"executionDetails": {"state": "FAILED"}}
    out = decision_flow.status(repo, aurora, ex)
    assert out["status"] == "FAILED" and not [h for h in repo.t["depot_holds"] if h["status"] == "ACTIVE"]


def test_an_expired_sign_off_is_closed(repo, aurora):
    ex = start_pending(repo, aurora)
    repo.t["decisions"][0]["expires_at"] = datetime.now(timezone.utc) - timedelta(hours=1)
    out = decision_flow.status(repo, aurora, ex)
    assert out["status"] == "FAILED" and "expired" in out["note"]


def test_status_without_a_decision(repo, aurora):
    assert decision_flow.status(repo, aurora, FakeExecutor())["status"] == "none"
