import asyncio
import pytest

from launchkit_provisioner import config
from launchkit_provisioner.tools import (brief_tools, decision_tools, fulfilment_tools, orchestration_tools,
                                         sourcing_tools)
from launchkit_provisioner.tools.brief_tools import BundleRequest

from conftest import FakeExecutor


def bundles(*pairs):
    return [BundleRequest(bundle_type=b, quantity=q, region=r) for b, q, r in pairs]


def test_register_validates_the_launch(repo):
    out = brief_tools.register_launch_request("LAUNCH-SPRING", "kits")
    assert out["status"] == "ok" and out["request_id"].startswith("REQ-") and out["launch_name"].startswith("Spring Product Launch Event")
    bad = brief_tools.register_launch_request("LAUNCH-NOPE", "x")
    assert bad["status"] == "error" and "Spring Product Launch Event" in bad["message"]


def test_build_requirements_in_one_call_with_a_guest_breakdown(repo):
    rid = brief_tools.register_launch_request("LAUNCH-SPRING", "kits")["request_id"]
    out = brief_tools.build_requirements(rid, bundles(("GUEST_KIT", 150, ""), ("VENUE_DISPLAY", 10, ""), ("SALES_PACK", 300, "")))
    assert out["status"] == "ok" and set(out["channels"]) == {"GUESTS", "VENUES", "SALES"}
    assert out["channels"]["VENUES"]["units"] == 10 and out["guest_hoodie_sizes"] == {"S": 20, "M": 45, "L": 60, "XL": 25}
    assert out["guest_power_plugs"]["US-A"] == 85 and out["requirement_lines"] == len(repo.get_requirement_lines(rid))
    again = brief_tools.build_requirements(rid, bundles(("SALES_PACK", 20, "EMEA")))     # a new brief replaces the old lines
    assert again["total_units"] == 40 and len(repo.get_requirement_lines(rid)) == 2


def test_build_requirements_errors_are_explained(repo):
    rid = brief_tools.register_launch_request("LAUNCH-SPRING", "kits")["request_id"]
    assert "Valid types" in brief_tools.build_requirements(rid, bundles(("TENT", 3, "")))["message"]
    assert brief_tools.build_requirements("REQ-NOPE", bundles(("SALES_PACK", 1, "")))["status"] == "error"


def test_build_scenarios_returns_the_card_and_the_decision_mode(repo):
    rid = brief_tools.register_launch_request("LAUNCH-SPRING", "kits")["request_id"]
    assert sourcing_tools.build_scenarios(rid)["status"] == "error"          # no requirements yet
    brief_tools.build_requirements(rid, bundles(("GUEST_KIT", 150, ""), ("VENUE_DISPLAY", 10, ""), ("SALES_PACK", 300, "")))
    out = sourcing_tools.build_scenarios(rid)
    assert out["status"] == "ok" and out["decision_mode"] == "CHOOSE" and out["autopilot_limit_usd"] == 5000.0
    assert [o["option"] for o in out["options"]] == [1, 2, 3] and out["recommended_option"] == "Use our stock first, buy the rest"
    assert out["decision_card"].count("**Option") == 3
    assert len(repo.get_scenarios(rid)) == 3 and "scenarios_built" in [a["action"] for a in repo.list_audit(rid)]


def test_a_small_brief_is_autopilot(repo):
    rid = brief_tools.register_launch_request("LAUNCH-SPRING", "20 folders")["request_id"]
    brief_tools.build_requirements(rid, bundles(("SALES_PACK", 20, "EMEA")))
    assert sourcing_tools.build_scenarios(rid)["decision_mode"] == "AUTOPILOT"


def test_vendor_delay_before_a_decision_asks_for_a_re_plan(repo):
    rid = brief_tools.register_launch_request("LAUNCH-SPRING", "kits")["request_id"]
    brief_tools.build_requirements(rid, bundles(("VENUE_DISPLAY", 10, "")))
    before = sourcing_tools.build_scenarios(rid)
    out = sourcing_tools.report_vendor_delay(rid, "displayco", 8, "late")
    assert out["status"] == "ok" and out["vendor"] == "DisplayCo" and out["delay_days"] == 8 and "build_scenarios" in out["next_step"]
    after = sourcing_tools.build_scenarios(rid)
    assert after["active_vendor_delays"][0]["vendor_id"] == "V-DISPLAYCO"
    assert [o["buffer_hours"] for o in after["options"]] != [o["buffer_hours"] for o in before["options"]]


def test_vendor_delay_errors(repo):
    rid = brief_tools.register_launch_request("LAUNCH-SPRING", "kits")["request_id"]
    assert "vendors" in sourcing_tools.report_vendor_delay(rid, "nobody", 3)
    assert sourcing_tools.report_vendor_delay(rid, "PrintCo", 0)["status"] == "error"


def test_delay_after_sign_off_reports_the_impact_and_does_not_replan(repo, monkeypatch):
    monkeypatch.setattr(decision_tools, "IntegrationExecutor", lambda: FakeExecutor())
    rid = brief_tools.register_launch_request("LAUNCH-SPRING", "kits")["request_id"]
    brief_tools.build_requirements(rid, bundles(("GUEST_KIT", 150, ""), ("VENUE_DISPLAY", 10, ""), ("SALES_PACK", 300, "")))
    sourcing_tools.build_scenarios(rid)
    assert asyncio.run(decision_tools.authorize_launch(rid, "2", "go"))["status"] == "pending_approval"
    out = sourcing_tools.report_vendor_delay(rid, "RapidDisplay", 12)
    assert out["impact"]["affected_lines"] >= 1 and out["impact"]["still_on_time"] is False
    assert "not re-planned" in out["next_step"]
    assert sourcing_tools.build_scenarios(rid)["status"] == "error"          # the plan is frozen once signed off or pending


def test_the_gate_and_the_status_tools_go_through_the_flow(repo, monkeypatch):
    ex = FakeExecutor()
    monkeypatch.setattr(decision_tools, "IntegrationExecutor", lambda: ex)
    monkeypatch.setattr(fulfilment_tools, "IntegrationExecutor", lambda: ex)
    import launchkit_provisioner.decision_flow as flow
    monkeypatch.setattr(flow, "_default_executor", lambda: ex)
    rid = brief_tools.register_launch_request("LAUNCH-SPRING", "kits")["request_id"]
    brief_tools.build_requirements(rid, bundles(("GUEST_KIT", 150, ""), ("VENUE_DISPLAY", 10, ""), ("SALES_PACK", 300, "")))
    sourcing_tools.build_scenarios(rid)
    assert fulfilment_tools.execute_plan(rid)["status"] == "error"                 # nothing signed off yet
    assert asyncio.run(decision_tools.authorize_launch(rid, "Option 2", "saves 19%"))["status"] == "pending_approval"
    assert fulfilment_tools.execute_plan(rid)["status"] == "BLOCKED"
    assert decision_tools.get_launch_status(rid)["status"] == "PENDING"
    ex.execution = {"eventExecutionDetails": {"eventExecutionState": "SUCCEEDED"}}
    ex.suspensions = [{"state": "LIFTED"}]
    st = decision_tools.get_launch_status(rid)
    assert st["status"] == "APPROVED" and st["request_id"] == rid
    done = fulfilment_tools.execute_plan(rid)
    assert done["status"] == "executed" and done["purchase_orders"] and done["depot_transfers"]
    board = orchestration_tools.get_launch_overview()
    assert board["requests"][0]["readiness"] == "GREEN" and board["requests"][0]["lines_executed"] == board["requests"][0]["lines_total"]
    assert not any(d["sku"] == "GIFT-BOX-BLACK" and d["free"] for d in board["depot_surplus"])     # all 60 boxes used up
    trail = [e["action"] for e in orchestration_tools.get_audit_trail(rid)["events"]]
    for expected in ("request_registered", "scenarios_built", "approval_requested", "launch_approved", "po_created",
                     "transfer_created"):
        assert expected in trail


def test_overview_lists_launches_and_surplus(repo):
    out = orchestration_tools.get_launch_overview()
    assert out["launches"][0]["launch_id"] == "LAUNCH-SPRING" and out["requests"] == []
    assert {"London EMEA Marketing Hub", "Dallas Marketing Depot"} <= {d["depot"] for d in out["depot_surplus"]}


def test_the_order_pack_is_attached_when_the_choice_is_made(repo, monkeypatch):
    monkeypatch.setattr(decision_tools, "IntegrationExecutor", lambda: FakeExecutor())

    class Ctx:
        saved = []

        async def save_artifact(self, name, part):
            Ctx.saved.append((name, part.inline_data.mime_type))
    rid = brief_tools.register_launch_request("LAUNCH-SPRING", "kits")["request_id"]
    brief_tools.build_requirements(rid, bundles(("GUEST_KIT", 150, ""), ("VENUE_DISPLAY", 10, ""), ("SALES_PACK", 300, "")))
    sourcing_tools.build_scenarios(rid)
    out = asyncio.run(decision_tools.authorize_launch(rid, "2", "go", tool_context=Ctx()))
    assert out["status"] == "pending_approval"
    assert Ctx.saved == [(f"order-pack-{rid}.pdf", "application/pdf")] and "Order pack PDF" in out["display_markdown"]
