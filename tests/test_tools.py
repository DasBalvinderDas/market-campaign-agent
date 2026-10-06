import pytest
import types

from campaign_provisioner.tools import budget_tools, inventory_tools, orchestration_tools, procurement_tools
from campaign_provisioner.workflow import guard
from campaign_provisioner.workflow.integration import create_purchase_order, notify_approver


def run_before(tool, args, ctx):
    import asyncio
    return asyncio.run(guard.before_tool(tool, args, ctx))


def new_request(campaign="NEXT27-MAIN"):
    return orchestration_tools.register_campaign_request(campaign, "test")["request_id"]


# ---- inventory
def test_find_sku_and_unknown_sku_hint():
    assert inventory_tools.find_sku("hoodies")["matches"][0]["sku"] == "HOODIE-NEXT"
    assert inventory_tools.find_sku("zeppelin")["status"] == "no_match"
    r = inventory_tools.check_inventory("LED-WALL", 1)
    assert r["status"] == "error" and r["valid_skus"][0]["sku"] == "BOOTH-LEDWALL"


def test_reserve_shortfall_and_release():
    rid = new_request()
    r = inventory_tools.reserve_inventory(rid, "DEMO-KIOSK", 6)
    assert r["reserved"] == 2 and r["shortfall_to_procure"] == 4
    assert inventory_tools.check_inventory("DEMO-KIOSK", 1)["free_stock"] == 0
    assert inventory_tools.release_inventory(rid)["units_released"] == 2
    assert inventory_tools.check_inventory("DEMO-KIOSK", 1)["free_stock"] == 2


def test_quotes_cheapest_first():
    q = procurement_tools.get_vendor_quotes("WATER-BOTTLE", 600)["quotes"]
    assert q[0]["vendor"] == "SwagHub" and q[0]["total"] == 3540.0


# ---- budget / policy
def test_policy_tiers():
    assert budget_tools.get_approval_policy(3540)["requires_human"] is False
    assert budget_tools.get_approval_policy(18000)["approver_role"] == "Marketing Director"
    assert budget_tools.get_approval_policy(72000)["tier"] == "EXECUTIVE"


def test_small_spend_auto_approved():
    rid = new_request("NEXT27-PARTNER")
    a = budget_tools.approve_budget(rid, "NEXT27-PARTNER", 3540.0, "bottles")
    assert a["approved_by"] == "auto-policy"
    assert budget_tools.check_budget("NEXT27-PARTNER")["committed"] == 3540.0


def test_high_value_requires_human_unless_unfundable():
    assert budget_tools.requires_human(18000, "NEXT27-MAIN") is True
    assert budget_tools.requires_human(3540, "NEXT27-MAIN") is False
    assert budget_tools.requires_human(18000, "NEXT27-DEVLOUNGE") is False  # exceeds $9,000 remaining


def test_insufficient_budget_rejected():
    rid = new_request("NEXT27-DEVLOUNGE")
    r = budget_tools.approve_budget(rid, "NEXT27-DEVLOUNGE", 18000.0, "led")
    assert r["status"] == "rejected" and r["remaining"] == 9000.0


def test_human_tier_recorded_with_role():
    rid = new_request()
    a = budget_tools.approve_budget(rid, "NEXT27-MAIN", 18000.0, "led wall")
    assert a["approved_by"] == "human:Marketing Director"


# ---- guard
TOOL = types.SimpleNamespace(name="create_purchase_order")


def po_args(rid, qty=1, sku="BOOTH-LEDWALL", vendor="V-EXPOVISION"):
    return {"request_id": rid, "sku": sku, "quantity": qty, "vendor_id": vendor, "total_amount": 1.0}


def test_po_blocked_without_approval():
    rid = new_request()
    assert run_before(TOOL, po_args(rid), None)["status"] == "BLOCKED"


def test_po_allowed_with_approval_amount_overridden_and_recorded(repo):
    rid = new_request()
    budget_tools.approve_budget(rid, "NEXT27-MAIN", 18000.0, "led wall")
    args = po_args(rid)
    assert run_before(TOOL, args, None) is None
    assert args["total_amount"] == 18000.0 and args["campaign_id"] == "NEXT27-MAIN"  # model value ignored
    resp = guard.after_tool(TOOL, args, None, create_purchase_order(**args))
    assert resp["recorded"] and repo.t["purchase_orders"][0]["total_amount"] == 18000.0
    # a second PO now exceeds the approval
    assert run_before(TOOL, po_args(rid), None)["status"] == "BLOCKED"


def test_po_cannot_exceed_approval():
    rid = new_request()
    budget_tools.approve_budget(rid, "NEXT27-MAIN", 4000.0, "x")
    assert run_before(TOOL, po_args(rid), None)["status"] == "BLOCKED"


def test_after_tool_notify_is_audited(repo):
    guard.after_tool(types.SimpleNamespace(name="notify_approver"),
                     {"request_id": "R", "approver_role": "Marketing Director", "amount": 1.0}, None,
                     notify_approver("R", "C", 1.0, "Marketing Director", "s"))
    assert repo.t["audit_log"][-1]["action"] == "approver_notified"


def test_audit_trail_filter():
    rid = new_request()
    inventory_tools.reserve_inventory(rid, "STICKER-PACK", 10)
    events = orchestration_tools.get_audit_trail(rid)["events"]
    assert [e["action"] for e in events] == ["request_registered", "stock_reserved"]


def test_unknown_campaign_lists_known():
    r = orchestration_tools.register_campaign_request("NOPE", "x")
    assert r["status"] == "error" and len(r["known_campaigns"]) == 3


def test_agent_wiring():
    from campaign_provisioner.agent import root_agent
    assert [a.name for a in root_agent.sub_agents] == ["inventory_agent", "procurement_agent", "budget_agent"]


def test_adk_confirmation_predicate_receives_args():
    import asyncio
    tool = budget_tools.approve_budget_tool
    ask = lambda amt, cid: asyncio.run(tool.check_require_confirmation(
        {"request_id": "R", "campaign_id": cid, "amount": amt, "justification": "j"}, types.SimpleNamespace()))
    assert ask(18000.0, "NEXT27-MAIN") is True
    assert ask(3540.0, "NEXT27-MAIN") is False
    assert ask(18000.0, "NEXT27-DEVLOUNGE") is False


# ---- approver notification
class FakeNotifyTool:
    name = "notify_approver"

    def __init__(self):
        self.calls = []

    async def run_async(self, *, args, tool_context):
        self.calls.append(dict(args))
        return {"status": "SUCCEEDED"}


def test_notify_recipients_come_from_data_not_model(repo):
    repo.t["approvers"] = [{"approver_role": "Marketing Director", "email": "md@example.com", "active": True},
                           {"approver_role": "Marketing Director", "email": "md2@example.com", "active": True},
                           {"approver_role": "Marketing Director", "email": "old@example.com", "active": False}]
    tool = FakeNotifyTool()
    args = {"request_id": "R", "campaign_id": "C", "summary": "1 wall, $18,000", "approver_role": "Marketing Director",
            "approver_email": "attacker@evil.com", "email_subject": "model subject"}
    assert run_before(tool, args, None) is None
    # first address goes through the normal call, every extra address gets its own call
    assert args["approver_email"] == "md@example.com"
    assert [c["approver_email"] for c in tool.calls] == ["md2@example.com"]
    assert args["email_subject"] == "Approval needed: R - C (Marketing Director)" and "1 wall" in args["email_body"]
    assert "attacker" not in str(args) + str(tool.calls)


def test_notify_without_recipients_is_reported_not_blocking(repo):
    repo.t["approvers"] = []
    tool = FakeNotifyTool()
    out = run_before(tool, {"request_id": "R", "approver_role": "VP Marketing + Finance Controller"}, None)
    assert out["status"] == "NO_APPROVERS" and "no email was sent" in out["reason"]
    assert repo.t["audit_log"][-1]["action"] == "approver_email_skipped_no_recipients"


def test_notification_failure_is_audited(repo):
    tool = types.SimpleNamespace(name="notify_approver")
    guard.after_tool(tool, {"request_id": "R", "approver_email": "a@x.com"}, None, {"executionFailed": True})
    assert repo.t["audit_log"][-1]["action"] == "approver_notification_failed"


def test_approver_config_parsing():
    from campaign_provisioner import approvers as a
    cfg = a.parse("Marketing Director=a@x.com,b@x.com;VP Marketing + Finance Controller=c@x.com;z@x.com")
    rows = a.expand(cfg, ["Marketing Director", "VP Marketing + Finance Controller"])
    assert [r["email"] for r in rows if r["approver_role"] == "Marketing Director"] == ["a@x.com", "b@x.com", "z@x.com"]
    assert a.parse("me@x.com") == {"*": ["me@x.com"]}
    with pytest.raises(ValueError):
        a.parse("Marketing Director=not-an-email")


def test_budget_agent_registers_the_guard_before_tool():
    from campaign_provisioner.sub_agents.budget_agent import budget_agent
    from campaign_provisioner.sub_agents.procurement_agent import procurement_agent
    assert guard.before_tool in (budget_agent.before_tool_callback
                                 if isinstance(budget_agent.before_tool_callback, list)
                                 else [budget_agent.before_tool_callback])
    assert procurement_agent.before_tool_callback is not None


def test_the_orchestrator_holds_the_approval_gate_not_the_budget_agent():
    from campaign_provisioner.agent import root_agent
    from campaign_provisioner.sub_agents.budget_agent import budget_agent
    root_tools = [getattr(t, "name", getattr(t, "__name__", "")) for t in root_agent.tools]
    budget_tools_names = [getattr(t, "name", getattr(t, "__name__", "")) for t in budget_agent.tools]
    assert "approve_budget" in root_tools and "approve_budget" not in budget_tools_names


def test_vendor_quotes_accept_an_item_description():
    from campaign_provisioner.tools.procurement_tools import get_vendor_quotes
    out = get_vendor_quotes("hoodies", 30)
    assert out["status"] == "ok" and out["sku"] == "HOODIE-NEXT" and out["quotes"]
    assert get_vendor_quotes("unicorn", 1)["status"] == "error"
