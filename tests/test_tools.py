import copy
import types

import pytest

from campaign_provisioner import data
from campaign_provisioner.tools import budget_tools, inventory_tools, procurement_tools


@pytest.fixture(autouse=True)
def fresh_data():
    snap = (copy.deepcopy(data.INVENTORY), copy.deepcopy(data.BUDGETS))
    yield
    data.INVENTORY.clear(); data.INVENTORY.update(snap[0])
    data.BUDGETS.clear(); data.BUDGETS.update(snap[1])


def ctx():
    return types.SimpleNamespace(state={})


def test_inventory_shortfall_and_reserve():
    assert inventory_tools.check_inventory("TOTE-01", 80)["shortfall"] == 30
    c = ctx()
    r = inventory_tools.reserve_inventory("REQ-001", "TOTE-01", 80, c)
    assert r["reserved"] == 50 and r["shortfall_to_procure"] == 30


def test_quotes_sorted_cheapest_first():
    q = procurement_tools.get_vendor_quotes("TSHIRT-M", 100)["quotes"]
    assert q[0]["vendor"] == "SwagHub"


def test_po_blocked_without_approval():
    r = procurement_tools.place_purchase_order("REQ-001", "TSHIRT-M", 10, "V-PRINTCO", ctx())
    assert r["status"] == "blocked"


def test_small_spend_auto_approved_then_po_placed():
    c = ctx()
    a = budget_tools.approve_budget("REQ-001", "CMP-LOCAL-POPUP", 800.0, "tote", c)
    assert a["approved_by"] == "auto-policy"
    p = procurement_tools.place_purchase_order("REQ-001", "TOTE-01", 100, "V-SWAGHUB", c)
    assert p["status"] == "placed"


def test_po_cannot_exceed_approved_amount():
    c = ctx()
    budget_tools.approve_budget("REQ-001", "CMP-LOCAL-POPUP", 100.0, "x", c)
    p = procurement_tools.place_purchase_order("REQ-001", "BANNER-XL", 5, "V-PRINTCO", c)
    assert p["status"] == "blocked"


def test_insufficient_budget_rejected():
    r = budget_tools.approve_budget("REQ-002", "CMP-LOCAL-POPUP", 9000.0, "x", ctx())
    assert r["status"] == "rejected"


def test_high_value_requires_human():
    assert budget_tools.requires_human(5000.01) is True
    assert budget_tools.requires_human(5000.0) is False


def test_agent_wiring():
    from campaign_provisioner.agent import root_agent
    assert [a.name for a in root_agent.sub_agents] == [
        "inventory_agent", "procurement_agent", "budget_agent"]
