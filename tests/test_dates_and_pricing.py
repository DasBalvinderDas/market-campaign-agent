"""Natural dates, vendor prices by date, and the 'another date' comparison."""
from datetime import date, timedelta

from launchkit_provisioner import planner, presentation
from launchkit_provisioner.dates import parse_date
from launchkit_provisioner.tools import brief_tools, sourcing_tools

TODAY = date(2026, 10, 12)


def test_dates_the_way_people_say_them():
    assert parse_date("31st Oct", TODAY) == date(2026, 10, 31)
    assert parse_date("31 October 2026", TODAY) == date(2026, 10, 31)
    assert parse_date("Oct 31", TODAY) == date(2026, 10, 31)
    assert parse_date("31/10", TODAY) == date(2026, 10, 31)
    assert parse_date("31.10.2027", TODAY) == date(2027, 10, 31)
    assert parse_date("2026-12-24", TODAY) == date(2026, 12, 24)
    assert parse_date("the 1st of March", TODAY) == date(2026, 3, 1)           # no year: this year
    assert parse_date("12 Oct", TODAY) == date(2026, 10, 12)                   # even if it has passed (the caller says so)


def test_things_that_are_not_dates_are_none():
    assert parse_date("soon", TODAY) is None and parse_date("", TODAY) is None and parse_date("31 Febtober", TODAY) is None
    assert parse_date("30 Feb", TODAY) is None


def test_price_factor_follows_the_days_ahead_and_a_vendor_can_have_its_own_bands(repo):
    rules = repo.list_date_pricing()
    assert planner.price_factor(rules, "V-APPAREL", 25) == (1.00, "Standard price")
    assert planner.price_factor(rules, "V-APPAREL", 40)[0] == 0.95 and planner.price_factor(rules, "V-APPAREL", 50)[0] == 0.92
    assert planner.price_factor(rules, "V-APPAREL", 10)[0] == 1.12 and planner.price_factor(rules, "V-APPAREL", 3)[0] == 1.20
    assert planner.price_factor(rules, "V-DISPLAYCO", 31)[0] == 0.93 and planner.price_factor(rules, "V-APPAREL", 31)[0] == 1.00


def _request(repo, days):
    repo.update_launch_dates("LAUNCH-SPRING", date.today() + timedelta(days=days), date.today() + timedelta(days=days + 7))
    rid = repo.create_request("LAUNCH-SPRING", "x")
    repo.replace_requirement_lines(rid, planner.expand_items(repo, [{"item": "steel water bottle", "quantity": 100, "region": "EMEA"},
                                                                    {"item": "canvas tote bag", "quantity": 100, "region": "EMEA"}]))
    return rid


def test_a_rush_costs_more_and_an_early_order_costs_less(repo):
    totals = {}
    for days in (10, 25, 50):
        rid = _request(repo, days)
        sc, _ = planner.plan_scenarios(repo, rid)
        totals[days] = next(s["total_cost"] for s in sc if s["option_code"] == "FULL_NEW")
    assert totals[10] > totals[25] > totals[50]


def test_the_demo_date_keeps_the_standard_price_so_the_demo_numbers_do_not_change(repo, aurora):
    totals = {s["option_code"]: s["total_cost"] for s in repo.get_scenarios(aurora)}
    assert totals == {"FULL_NEW": 46075.5, "REBALANCE": 37399.5, "ECO": 51905.5}


def test_plan_dates_plans_the_same_list_for_other_dates_and_stores_nothing(repo, aurora):
    before = [s["total_cost"] for s in repo.get_scenarios(aurora)]
    rows = planner.plan_dates(repo, aurora, [-7, 0, 14, 28])
    assert [r["offset"] for r in rows] == [-7, 0, 14, 28] and rows[1]["best"]["total_cost"] == 37399.5
    assert rows[1]["band"] == "Standard price" and rows[3]["band"].startswith("Early bird")
    assert rows[3]["best"]["total_cost"] < rows[1]["best"]["total_cost"] < rows[0]["best"]["total_cost"]
    assert [s["total_cost"] for s in repo.get_scenarios(aurora)] == before
    assert repo.get_launch("LAUNCH-SPRING")["in_hand_by"] == rows[1]["deadline"]


def test_dates_less_than_a_day_away_are_left_out(repo, aurora):
    assert all(r["window"] >= 1 for r in planner.plan_dates(repo, aurora, [-60, -30, 0]))


def test_the_plan_comes_with_a_table_of_other_dates_and_the_cheapest_is_suggested(repo):
    rid = brief_tools.register_launch_request("LAUNCH-SPRING", "x")["request_id"]
    brief_tools.build_requirements(rid, [brief_tools.BundleRequest(bundle_type="SALES_PACK", quantity=300)])
    md = sourcing_tools.build_scenarios(rid)["date_options"]
    assert "Could another date save you money?" in md and "👈 **your date**" in md
    assert "Early bird" in md and "Rush" in md and "Say *move it to" in md and "Save $" in md


def test_a_date_table_says_when_your_date_is_already_the_best(repo, aurora):
    rows = planner.plan_dates(repo, aurora, [-14, -7, 0])
    assert "Your date is a good one" in presentation.date_options_markdown(rows, repo.list_policies())


def test_moving_the_campaign_date_re_plans_with_the_new_price_band(repo):
    rid = brief_tools.register_launch_request("Spring Product Launch Event", "x", (date.today() + timedelta(days=60)).isoformat())["request_id"]
    brief_tools.build_requirements(rid, [brief_tools.BundleRequest(bundle_type="SALES_PACK", quantity=300)])
    early = sourcing_tools.build_scenarios(rid)["options"][0]["total_usd"]
    rid2 = brief_tools.register_launch_request("Spring Product Launch Event", "x", (date.today() + timedelta(days=12)).isoformat())["request_id"]
    brief_tools.build_requirements(rid2, [brief_tools.BundleRequest(bundle_type="SALES_PACK", quantity=300)])
    assert sourcing_tools.build_scenarios(rid2)["options"][0]["total_usd"] > early


def test_a_year_the_assistant_guessed_from_the_past_is_this_year():
    assert parse_date("2025-10-24", TODAY) == date(2026, 10, 24)           # "October 24" with last year's year added
    assert parse_date("2024-10-24", TODAY) == date(2026, 10, 24)
    assert parse_date("2027-10-24", TODAY) == date(2027, 10, 24)           # a later year is kept
    assert parse_date("2026-12-24", TODAY) == date(2026, 12, 24)
