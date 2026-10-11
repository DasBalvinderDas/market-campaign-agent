from datetime import date

import pytest

from launchkit_provisioner import planner
from launchkit_provisioner.data.seed_data import EMBARGO_DAYS, IN_HAND_DAYS

from conftest import BRIEF


def lines_for(repo, bundles):
    return planner.expand_bundles(repo, "LAUNCH-AURORA", bundles)


def test_creator_kits_are_personalised_from_the_creator_list(repo):
    lines = lines_for(repo, [{"bundle_type": "CREATOR_KIT", "quantity": 150}])
    units = {}
    for ln in lines:
        units[ln["sku"]] = units.get(ln["sku"], 0) + ln["quantity"]
    assert units["PKG-LUX-BOX-BLACK"] == 150 and units["CARD-ENGRAVED"] == 150
    assert [units[f"HOODIE-AURORA-{s}"] for s in ("S", "M", "L", "XL")] == [20, 45, 60, 25]
    assert units["PWR-US-A"] == 85 and units["PWR-UK-G"] == 30 and units["PWR-EU-C"] == 15
    assert units["PWR-JP-A"] == 12 and units["PWR-AU-I"] == 8
    box_by_region = {ln["region"]: ln["quantity"] for ln in lines if ln["sku"] == "PKG-LUX-BOX-BLACK"}
    assert box_by_region == {"US": 85, "EMEA": 45, "APAC": 20}


def test_smaller_quantities_keep_the_mix_and_the_exact_total(repo):
    lines = lines_for(repo, [{"bundle_type": "CREATOR_KIT", "quantity": 37}])
    boxes = sum(ln["quantity"] for ln in lines if ln["sku"] == "PKG-LUX-BOX-BLACK")
    hoodies = sum(ln["quantity"] for ln in lines if ln["sku"].startswith("HOODIE"))
    assert boxes == 37 and hoodies == 37


def test_showroom_and_sales_follow_the_regional_split_or_a_single_region(repo):
    lines = lines_for(repo, [{"bundle_type": "SHOWROOM_DISPLAY", "quantity": 10}, {"bundle_type": "SALES_FOLIO", "quantity": 300}])
    disp = {ln["region"]: ln["quantity"] for ln in lines if ln["sku"] == "DISPLAY-COUNTER-AURORA"}
    folio = {ln["region"]: ln["quantity"] for ln in lines if ln["sku"] == "FOLIO-LEATHER-EXEC"}
    assert disp == {"US": 4, "EMEA": 4, "APAC": 2} and sum(folio.values()) == 300 and folio["US"] == 150
    emea = lines_for(repo, [{"bundle_type": "SALES_FOLIO", "quantity": 20, "region": "emea"}])
    assert {(ln["sku"], ln["region"], ln["quantity"]) for ln in emea} == {
        ("FOLIO-LEATHER-EXEC", "EMEA", 20), ("BROCHURE-AURORA", "EMEA", 20)}
    kits = lines_for(repo, [{"bundle_type": "CREATOR_KIT", "quantity": 10, "region": "APAC"}])
    assert {ln["region"] for ln in kits} == {"APAC"} and sum(ln["quantity"] for ln in kits if ln["sku"].startswith("HOODIE")) == 10


def test_unknown_bundle_or_bad_quantity_is_refused(repo):
    with pytest.raises(planner.PlanError, match="Valid types"):
        lines_for(repo, [{"bundle_type": "TENT", "quantity": 1}])
    with pytest.raises(planner.PlanError):
        lines_for(repo, [{"bundle_type": "SALES_FOLIO", "quantity": 0}])


def scenarios(repo, aurora):
    return {s["option_code"]: s for s in repo.get_scenarios(aurora)}


def test_three_scenarios_are_computed_from_the_data(repo, aurora):
    sc = scenarios(repo, aurora)
    assert set(sc) == {"FULL_NEW", "REBALANCE", "ECO"}
    assert sc["FULL_NEW"]["savings_usd"] == 0
    assert sc["REBALANCE"]["total_cost"] < sc["FULL_NEW"]["total_cost"] < sc["ECO"]["total_cost"]
    assert sc["REBALANCE"]["savings_usd"] == pytest.approx(sc["FULL_NEW"]["total_cost"] - sc["REBALANCE"]["total_cost"])
    assert sc["ECO"]["carbon_kg"] < sc["REBALANCE"]["carbon_kg"] < sc["FULL_NEW"]["carbon_kg"]


def test_deadline_buffers_and_recommendation(repo, aurora):
    sc = scenarios(repo, aurora)
    assert sc["FULL_NEW"]["buffer_hours"] == 0 and sc["FULL_NEW"]["risk"].startswith("MODERATE")
    assert sc["REBALANCE"]["buffer_hours"] >= 48 and sc["REBALANCE"]["recommended"]
    assert not sc["FULL_NEW"]["recommended"] and not sc["ECO"]["recommended"]
    assert all(s["feasible"] for s in sc.values())


def test_rebalance_reuses_depot_stock_nearest_first(repo, aurora):
    sc = scenarios(repo, aurora)
    lines = repo.get_scenario_lines(sc["REBALANCE"]["scenario_id"])
    depot = [ln for ln in lines if ln["source_type"] == "DEPOT"]
    by = {}
    for ln in depot:
        by[(ln["sku"], ln["source_id"], ln["region"])] = ln["quantity"]
    assert by[("PKG-LUX-BOX-BLACK", "DEPOT-LON-01", "EMEA")] == 45      # London serves EMEA first
    assert sum(q for (sku, d, _r), q in by.items() if sku == "PKG-LUX-BOX-BLACK") == 60   # all 60 boxes reused
    assert sum(q for (sku, d, _r), q in by.items() if sku == "FOLIO-LEATHER-EXEC") == 120
    assert all(ln["unit_price"] == 0 for ln in depot)
    # the other two options never touch depot stock
    for code in ("FULL_NEW", "ECO"):
        assert not [ln for ln in repo.get_scenario_lines(sc[code]["scenario_id"]) if ln["source_type"] == "DEPOT"]


def test_every_requirement_is_covered_exactly_once_in_every_scenario(repo, aurora):
    need = {}
    for ln in repo.get_requirement_lines(aurora):
        need[(ln["sku"], ln["region"])] = ln["quantity"]
    for s in repo.get_scenarios(aurora):
        got = {}
        for ln in repo.get_scenario_lines(s["scenario_id"]):
            got[(ln["sku"], ln["region"])] = got.get((ln["sku"], ln["region"]), 0) + ln["quantity"]
        assert got == need, s["option_code"]


def test_deadline_aware_vendor_choice_pays_for_speed_only_where_needed(repo, aurora):
    sc = scenarios(repo, aurora)
    def displays(code):
        return {ln["region"]: ln["source_id"] for ln in repo.get_scenario_lines(sc[code]["scenario_id"])
                if ln["sku"] == "DISPLAY-COUNTER-AURORA"}
    assert set(displays("FULL_NEW").values()) == {"V-DISPLAYCO"}        # cheapest, whatever the date
    assert displays("REBALANCE")["APAC"] == "V-RAPIDDISPLAY"            # only the far region gets the fast vendor
    assert displays("REBALANCE")["US"] == "V-DISPLAYCO"


def test_a_vendor_delay_replans_and_can_change_the_recommendation(repo, aurora):
    repo.add_disruption("V-RAPIDDISPLAY", 10, "factory fire")
    repo.add_disruption("V-DISPLAYCO", 10, "port strike")
    scenarios2, lines2 = planner.plan_scenarios(repo, aurora)
    by = {s["option_code"]: s for s in scenarios2}
    assert all(s["buffer_hours"] < 0 and not s["feasible"] for s in by.values())   # nobody can make the date
    assert sum(1 for s in scenarios2 if s["recommended"]) == 1                      # the least bad is still flagged
    assert all("HIGH" in s["risk"] for s in by.values())


def test_a_smaller_delay_shrinks_the_buffer_but_keeps_the_plan_feasible(repo, aurora):
    repo.add_disruption("V-LUXPACK", 2, "late board")
    sc, _ = planner.plan_scenarios(repo, aurora)
    by = {s["option_code"]: s for s in sc}
    assert by["FULL_NEW"]["buffer_hours"] <= 0
    assert by["REBALANCE"]["feasible"]


def test_delay_impact_on_a_chosen_scenario(repo, aurora):
    reb = scenarios(repo, aurora)["REBALANCE"]
    impact = planner.delay_impact(repo, reb, 10, "V-RAPIDDISPLAY")
    assert impact["affected_lines"] >= 1 and impact["new_buffer_hours"] < reb["buffer_hours"]
    none = planner.delay_impact(repo, reb, 10, "V-PRINTCO-NOT-USED")
    assert none["affected_lines"] == 0 and none["new_buffer_hours"] == reb["buffer_hours"]


def test_vendor_names_resolve(repo):
    assert planner.resolve_vendor(repo, "rapiddisplay")["vendor_id"] == "V-RAPIDDISPLAY"
    assert planner.resolve_vendor(repo, "V-PRINTCO")["vendor_name"] == "PrintCo"
    assert planner.resolve_vendor(repo, "Display") is None      # ambiguous: two vendors
    assert planner.resolve_vendor(repo, "nobody") is None


def test_small_request_fits_autopilot(repo):
    rid = repo.create_request("LAUNCH-AURORA", "20 folios for EMEA")
    repo.replace_requirement_lines(rid, planner.expand_bundles(
        repo, "LAUNCH-AURORA", [{"bundle_type": "SALES_FOLIO", "quantity": 20, "region": "EMEA"}]))
    sc, _ = planner.plan_scenarios(repo, rid)
    best = next(s for s in sc if s["recommended"])
    assert best["total_cost"] <= 5000


def test_decision_card_shows_only_computed_numbers(repo, aurora):
    card = planner.decision_card(aurora, repo.get_launch("LAUNCH-AURORA"), repo.get_scenarios(aurora), 5000)
    for s in repo.get_scenarios(aurora):
        assert f"${s['total_cost']:,.2f}" in card
    assert "RECOMMENDED" in card and card.count("**Option") == 3


def test_launch_dates_are_relative_to_setup_day(repo):
    launch = repo.get_launch("LAUNCH-AURORA")
    today = date.today()
    assert (launch["in_hand_by"] - today).days == IN_HAND_DAYS and (launch["embargo_date"] - today).days == EMBARGO_DAYS


def test_when_the_cheap_display_vendor_is_late_the_planner_switches_and_flags_the_old_plan(repo, aurora):
    repo.add_disruption("V-DISPLAYCO", 6, "port strike")
    sc, lines = planner.plan_scenarios(repo, aurora)
    by = {s["option_code"]: s for s in sc}
    assert not by["FULL_NEW"]["feasible"] and by["FULL_NEW"]["buffer_hours"] == -144       # cheapest vendor can no longer make it
    assert by["REBALANCE"]["feasible"] and by["REBALANCE"]["recommended"] and by["REBALANCE"]["buffer_hours"] >= 48
    reb_displays = {ln["source_id"] for ln in lines if ln["scenario_id"].endswith("-RB") and ln["sku"] == "DISPLAY-COUNTER-AURORA"}
    assert reb_displays == {"V-RAPIDDISPLAY"}                                               # switched to the fast vendor


def test_when_nothing_meets_the_minimum_buffer_the_least_bad_cheapest_option_is_flagged(repo, aurora):
    repo.add_disruption("V-LUXPACK", 5, "late board")                                       # boxes: no option can make the date
    sc, _ = planner.plan_scenarios(repo, aurora)
    assert not any(s["feasible"] for s in sc) and [s["option_code"] for s in sc if s["recommended"]] == ["REBALANCE"]
